/**
 * Follow one turn live, as the desktop does (abstractassistant/gateway/
 * run_controller.py follow_run :385-432 and stream_run :202-317): a STACK of
 * runs, ONE ledger stream at a time.
 *
 * - A `subworkflow` wait on the active run pushes the child it names (the
 *   approval the person must answer lives on the CHILD ledger — the
 *   desktop's 2026-09-07 finding in CLAUDE.md).
 * - Whenever a stream ends — with `event: done` or without it (a proxy idle
 *   timeout, a gateway restart: the stream then says NOTHING about the run) —
 *   the follower asks the run (`GET /runs/{id}`). Terminal: drain the
 *   remaining ledger rows with `GET /runs/{id}/ledger` until two reads in a
 *   row bring nothing (run_controller.py replay_ledger_until_quiet), then pop.
 *   Not terminal: reconnect from the cursor after a backoff (1, 2, 4, 5 s),
 *   for as long as the turn is open.
 * - A failing connection (HTTP error, network) is retried with the same
 *   backoff; after 4 failures in a row the follower gives up, marks the turn
 *   `lost` (approval cards are disabled) and says so.
 *
 * One stream at a time matters in a browser: over HTTP/1.1 a page gets six
 * connections per origin, and a real turn nests three to four child runs
 * (measured on the local gateway, W3 report). Live reply frames come from the
 * active stream: a run's stream carries the deltas of every run below it
 * (api.md "Sub-runs"), and a parent parked on its child writes none.
 */
import { subworkflowRunId, type TurnAction, type TurnState } from "../lib/run_events";
import type { GatewayClient } from "./client";

export type FollowOptions = {
  client: GatewayClient;
  rootRunId: string;
  dispatch: (a: TurnAction) => void;
  /** The state the dispatches just produced (a synchronous store). */
  getState: () => TurnState;
  onError: (message: string) => void;
  /** Backoff steps in ms (tests shorten them). */
  backoffMs?: number[];
  /** Pause between two drain reads of a terminal run, in ms. */
  drainIntervalMs?: number;
};

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const DEFAULT_BACKOFF = [1000, 2000, 4000, 5000];
const MAX_FAILURES = 4;

export function followTurn(opts: FollowOptions): () => void {
  const stopAll = new AbortController();
  void run(opts, stopAll.signal);
  return () => stopAll.abort();
}

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => (clearTimeout(t), resolve()), { once: true });
  });

/** Read the rest of a finished run's ledger until it is quiet. Returns a new child, if one shows up. */
async function drain(opts: FollowOptions, runId: string, seen: Set<string>, stopAll: AbortSignal): Promise<string> {
  let quiet = 0;
  let child = "";
  while (quiet < 2 && !stopAll.aborted) {
    const after = opts.getState().cursors[runId] ?? 0;
    const page = await opts.client.ledgerPage(runId, after);
    page.items.forEach((record, i) => {
      // `after` counts records consumed; the page's next_after is the authority for the last one.
      opts.dispatch({ type: "step", run_id: runId, cursor: i === page.items.length - 1 ? page.next_after : after + i + 1, record });
      const result = record.result as Record<string, unknown> | undefined;
      const wait = result && typeof result === "object" ? (result.wait as Record<string, unknown> | undefined) : undefined;
      const c = wait && typeof wait === "object" ? subworkflowRunId(wait) : "";
      if (c && !seen.has(c) && !child) child = c;
    });
    quiet = page.items.length ? 0 : quiet + 1;
    if (quiet < 2) await sleep(opts.drainIntervalMs ?? 250, stopAll);
  }
  return child;
}

async function run(opts: FollowOptions, stopAll: AbortSignal): Promise<void> {
  const backoff = opts.backoffMs ?? DEFAULT_BACKOFF;
  const stack = [opts.rootRunId];
  const seen = new Set(stack);
  let failures = 0;
  let quietCloses = 0;
  while (stack.length && !stopAll.aborted) {
    const active = stack[stack.length - 1];
    const one = new AbortController();
    const onStop = () => one.abort();
    stopAll.addEventListener("abort", onStop, { once: true });
    let child = "";
    try {
      try {
        // `done` or not, the run is asked below: a close without `done` proves nothing.
        await opts.client.streamLedger(
          active,
          opts.getState().cursors[active] ?? 0,
          {
            onOpen: () => {
              opts.dispatch({ type: "stream_open", run_id: active });
              opts.dispatch({ type: "follow_state", state: "live" });
            },
            onStep: (step) => {
              quietCloses = 0;
              opts.dispatch({ type: "step", run_id: active, cursor: step.cursor, record: step.record });
              const next = opts.getState().child_runs.find((c) => !seen.has(c));
              if (next && !child) {
                child = next;
                one.abort();
              }
            },
            onDelta: (event, data) => opts.dispatch({ type: "delta", event, data }),
          },
          one.signal,
        );
      } catch (err) {
        if (stopAll.aborted) return;
        if (!child) throw err;
      }
      failures = 0;
      if (child) {
        seen.add(child);
        stack.push(child);
        continue;
      }
      // The stream ended (done or not): the RUN says whether it is over.
      const r = await opts.client.getRun(active);
      const status = String(r.status || "").toLowerCase();
      if (TERMINAL.has(status)) {
        const late = await drain(opts, active, seen, stopAll);
        if (late) {
          seen.add(late);
          stack.push(late);
          continue;
        }
        stack.pop();
        quietCloses = 0;
        if (active === opts.rootRunId) {
          opts.dispatch({ type: "run_status", run_id: active, status, error: typeof r.error === "string" ? r.error : undefined });
        }
        continue;
      }
      // Not over: the connection was closed under us (or `done` came early). Reconnect from the cursor.
      opts.dispatch({ type: "follow_state", state: "reconnecting" });
      await sleep(backoff[Math.min(quietCloses++, backoff.length - 1)], stopAll);
    } catch (err) {
      if (stopAll.aborted) return;
      failures += 1;
      if (failures >= MAX_FAILURES) {
        const note = `Live updates stopped (${err instanceof Error ? err.message : String(err)}). The run goes on on the gateway; reopen the conversation to see it.`;
        opts.dispatch({ type: "follow_state", state: "lost", note });
        opts.onError(note);
        return;
      }
      opts.dispatch({ type: "follow_state", state: "reconnecting" });
      await sleep(backoff[Math.min(failures - 1, backoff.length - 1)], stopAll);
    } finally {
      stopAll.removeEventListener("abort", onStop);
    }
  }
}
