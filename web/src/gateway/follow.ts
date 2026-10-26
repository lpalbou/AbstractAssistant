/**
 * Follow one turn live, as the desktop does (abstractassistant/gateway/
 * run_controller.py follow_run): a STACK of runs, ONE ledger stream at a
 * time. A `subworkflow` wait on the active run pushes the child it names
 * (the approval the person must answer lives on the CHILD ledger — the
 * desktop's 2026-09-07 finding in CLAUDE.md); the child's `event: done` pops
 * it and the parent resumes from its own cursor.
 *
 * One stream at a time matters in a browser: over HTTP/1.1 a page gets six
 * connections per origin, and a real turn nests three to four child runs
 * (measured on the local gateway, W3 report). Streams side by side would
 * leave no connection for the approval POST.
 *
 * Live reply frames come from the active stream: a run's stream carries the
 * deltas of every run below it (api.md "Sub-runs"), and a parent parked on
 * its child writes none of its own.
 *
 * A dropped stream is resumed from its cursor (1 s, 2 s, 4 s), then the turn
 * reports the failure; the run itself goes on on the gateway.
 */
import type { TurnAction, TurnState } from "../lib/run_events";
import type { GatewayClient } from "./client";

export type FollowOptions = {
  client: GatewayClient;
  rootRunId: string;
  dispatch: (a: TurnAction) => void;
  /** The state the dispatches just produced (a synchronous store). */
  getState: () => TurnState;
  onError: (message: string) => void;
};

const RETRY_MS = [1000, 2000, 4000];

export function followTurn(opts: FollowOptions): () => void {
  const stopAll = new AbortController();
  void run(opts, stopAll.signal);
  return () => stopAll.abort();
}

async function run(opts: FollowOptions, stopAll: AbortSignal): Promise<void> {
  const stack = [opts.rootRunId];
  const seen = new Set(stack);
  let attempt = 0;
  while (stack.length && !stopAll.aborted) {
    const active = stack[stack.length - 1];
    const one = new AbortController();
    const onStop = () => one.abort();
    stopAll.addEventListener("abort", onStop, { once: true });
    let child = "";
    try {
      await opts.client.streamLedger(
        active,
        opts.getState().cursors[active] ?? 0,
        {
          onOpen: () => opts.dispatch({ type: "stream_open", run_id: active }),
          onStep: (step) => {
            attempt = 0;
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
      // `event: done`: this run is finished and fully sent.
      stack.pop();
      if (active === opts.rootRunId) {
        const r = await opts.client.getRun(active);
        opts.dispatch({ type: "run_status", run_id: active, status: String(r.status || ""), error: typeof r.error === "string" ? r.error : undefined });
      }
    } catch (err) {
      if (stopAll.aborted) return;
      if (child) {
        seen.add(child);
        stack.push(child);
        continue;
      }
      if (attempt >= RETRY_MS.length) {
        opts.onError(`Live updates stopped (${err instanceof Error ? err.message : String(err)}). The run goes on on the gateway; reopen the conversation to see it.`);
        return;
      }
      await new Promise((r) => setTimeout(r, RETRY_MS[attempt++]));
    } finally {
      stopAll.removeEventListener("abort", onStop);
    }
  }
}
