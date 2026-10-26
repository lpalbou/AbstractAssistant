/**
 * The live state of ONE turn (a root run and the child runs it delegates
 * to), folded from gateway ledger records and live reply frames. Pure: the
 * follower (src/gateway/follow.ts) feeds it; tests feed it fixtures.
 *
 * The record readings are PORTS of the desktop's
 * abstractassistant/gateway/events.py and adapter.py:
 * - a wait lives at `record.result.wait` (events.py extract_wait_from_record);
 * - tool approval = `details.mode == "approval_required"`, or
 *   `details.executor.kind == "tool_approval"`, or a `tool_approval…` key,
 *   or tool calls in the details (events.py is_tool_approval_wait);
 * - a question = `reason == "user"`, or an event wait whose key
 *   `evt:{scope}:{scope_id}:{name}` names `abstract.ask` (events.py
 *   event_name_from_wait_key; the name is the FOURTH segment);
 * - a `subworkflow` wait (or a `subworkflow:<child>` key) names the child
 *   run to follow (run_controller.py extract_subworkflow_run_id);
 * - wait identity is (run_id, wait_key, step_id), never the key alone: the
 *   runtime reuses one key per node for every approval batch
 *   (adapter.py:42-58, the 2026-07-28 stall). A `resume` record answers the
 *   open waits of its key on that run;
 * - the answer is the ROOT run's flow-end output (events.py
 *   extract_flow_end_output); a child's end is not the answer.
 * Live replies (api.md "Live replies"): `llm.delta` text per `call_id` and
 * channel; a snapshot replaces; the durable `llm_call` record with the same
 * step id ends the live text, and later deltas of that call are ignored.
 */
import type { PendingWait } from "./types";

type Json = Record<string, unknown>;
const isObj = (v: unknown): v is Json => Boolean(v) && typeof v === "object" && !Array.isArray(v);
const str = (v: unknown) => (typeof v === "string" ? v.trim() : v === undefined || v === null ? "" : String(v).trim());

export type TurnStatus = "starting" | "running" | "waiting" | "completed" | "failed" | "cancelled";

export type LiveCall = { run_id: string; content: string; reasoning: string; ended: boolean };

export type TurnState = {
  root_run_id: string;
  status: TurnStatus;
  /** One line saying what is happening ("Thinking — step 2", "Using web_search"). */
  activity: string;
  /** Child runs to follow, in discovery order. */
  child_runs: string[];
  cursors: Record<string, number>;
  waits: PendingWait[];
  live: Record<string, LiveCall>;
  live_order: string[];
  closed_calls: string[];
  /** Intermediate messages a flow emitted (`abstract.message`). */
  notes: string[];
  answer: string | null;
  error: string | null;
  cycles: Record<string, number>;
  /** The follower: reading live, reconnecting after a drop, or given up (cards are then disabled). */
  follow: "live" | "reconnecting" | "lost";
};

export type TurnAction =
  | { type: "step"; run_id: string; cursor: number; record: Json }
  | { type: "delta"; event: "llm.delta" | "llm.delta_end"; data: Json }
  | { type: "stream_open"; run_id: string }
  | { type: "wait_sending"; run_id: string; wait_key: string; step_id: string }
  | { type: "wait_failed"; run_id: string; wait_key: string; step_id: string; note: string }
  | { type: "wait_closed"; run_id: string; wait_key: string; step_id?: string; note?: string; stale?: boolean }
  | { type: "run_status"; run_id: string; status: string; error?: string }
  | { type: "follow_state"; state: "live" | "reconnecting" | "lost"; note?: string };

export function initialTurn(rootRunId: string): TurnState {
  return {
    root_run_id: rootRunId,
    status: "starting",
    activity: "",
    child_runs: [],
    cursors: {},
    waits: [],
    live: {},
    live_order: [],
    closed_calls: [],
    notes: [],
    answer: null,
    error: null,
    cycles: {},
    follow: "live",
  };
}

/** `evt:{scope}:{scope_id}:{name}` -> name; legacy `evt:<name>` -> name. */
export function eventNameFromWaitKey(waitKey: string): string {
  const wk = str(waitKey);
  if (!wk.startsWith("evt:")) return wk;
  const parts = wk.split(":");
  if (parts.length >= 4) return parts.slice(3).join(":").trim();
  return str(parts[1]);
}

export function isToolApprovalWait(wait: Json): boolean {
  const key = str(wait.wait_key).toLowerCase();
  const details = wait.details;
  if (!isObj(details)) return key.startsWith("tool_approval");
  if (str(details.mode).toLowerCase() === "approval_required") return true;
  if (isObj(details.executor) && str(details.executor.kind).toLowerCase() === "tool_approval") return true;
  return key.startsWith("tool_approval");
}

function toolCallsOf(wait: Json): PendingWait["tool_calls"] {
  const d = isObj(wait.details) ? wait.details : {};
  const raw = Array.isArray(d.tool_calls) ? d.tool_calls : Array.isArray(d.tool_calls_for_evidence) ? d.tool_calls_for_evidence : [];
  return raw
    .filter(isObj)
    .map((tc) => {
      const id = str(tc.call_id) || str(tc.id) || str(tc.runtime_call_id);
      return { name: str(tc.name) || "tool", arguments: tc.arguments, ...(id ? { call_id: id } : {}) };
    });
}

/** Stable JSON (sorted keys) for comparing tool arguments. */
function stableJson(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(stableJson).join(",")}]`;
  if (isObj(v)) return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${stableJson(v[k])}`).join(",")}}`;
  return JSON.stringify(v ?? null);
}

/**
 * What a wait ASKS: for an approval the batch of calls (id, name and
 * arguments), for a question its prompt. The runtime reuses one wait key per
 * node for every approval batch (adapter.py:42-58), and `GET /runs/{id}`
 * carries no step id (abstractgateway service.py run_summary), so the key
 * alone cannot tell this card's question from a newer one.
 */
export function waitFingerprint(kind: PendingWait["kind"], prompt: string, calls: PendingWait["tool_calls"]): string {
  if (kind === "ask_user") return `ask|${prompt.trim()}`;
  return `tools|${calls
    .map((c) => `${c.call_id || ""}|${c.name}|${stableJson(c.arguments)}`)
    .sort()
    .join("||")}`;
}

/**
 * Whether the run, as `GET /runs/{id}` shows it now, still waits on the
 * question this card shows. Anything else — not waiting, another key, a
 * different batch or prompt, or a waiting record with nothing to compare —
 * is "no": the card must not answer a question the person never saw.
 */
export function waitStillMatches(card: PendingWait, run: Record<string, unknown>): { ok: true } | { ok: false; why: string } {
  if (str(run.status).toLowerCase() !== "waiting" || !isObj(run.waiting)) return { ok: false, why: "The run is no longer waiting: already answered, or stopped." };
  const w = run.waiting;
  if (str(w.wait_key) !== card.wait_key) return { ok: false, why: "The run is waiting on something else now." };
  if (card.kind === "tool_approval") {
    const now = toolCallsOf(w);
    if (!now.length) return { ok: false, why: "The gateway did not say which tools wait for approval; reopen the conversation." };
    if (waitFingerprint("tool_approval", "", now) !== waitFingerprint("tool_approval", "", card.tool_calls)) {
      return { ok: false, why: "A newer request is waiting on the same step: this one was already answered." };
    }
    return { ok: true };
  }
  if (waitFingerprint("ask_user", str(w.prompt), []) !== waitFingerprint("ask_user", card.prompt, [])) {
    return { ok: false, why: "A newer question is waiting: this one was already answered." };
  }
  return { ok: true };
}

/** The child run a delegation wait names, or "". A `subworkflow:<child>` key
 * is a delegation whatever its `reason` says (the desktop's production
 * fixture carries `reason: "user"` on it, tests/basic/test_gateway_worker.py
 * test_attach_reprompts_a_pending_approval_that_belongs_to_a_SUBRUN; the
 * kit's workflow_runtime.ts reads it the same way). */
export function subworkflowRunId(wait: Json): string {
  const key = str(wait.wait_key);
  const delegation = str(wait.reason).toLowerCase() === "subworkflow" || key.startsWith("subworkflow:");
  if (!delegation) return "";
  if (isObj(wait.details) && str(wait.details.sub_run_id)) return str(wait.details.sub_run_id);
  return key.startsWith("subworkflow:") ? str(key.slice("subworkflow:".length)) : "";
}

/** events.py extract_flow_end_output, text half (media metadata is v1.1). */
export function flowEndText(record: Json): string | null {
  const result = record.result;
  if (!isObj(result) || !("output" in result)) return null;
  const out = result.output;
  if (typeof out === "string") return out.trim() || null;
  if (!isObj(out)) return null;
  for (const k of ["answer", "response", "message", "text", "content"]) {
    const v = out[k];
    if (typeof v === "string" && v.trim()) return v.trim();
    if (typeof v === "number" || typeof v === "boolean") return String(v);
  }
  return null;
}

const sameWait = (w: PendingWait, run: string, key: string, step?: string) =>
  w.run_id === run && w.wait_key === key && (step === undefined || !step || w.step_id === step);

function stepAction(s: TurnState, run: string, cursor: number, rec: Json): TurnState {
  const next: TurnState = { ...s, cursors: { ...s.cursors, [run]: Math.max(cursor, s.cursors[run] ?? 0) } };
  const status = str(rec.status).toLowerCase();
  const effect = isObj(rec.effect) ? rec.effect : {};
  const etype = str(effect.type).toLowerCase();
  const stepId = str(rec.step_id);
  if (next.status === "starting") next.status = "running";

  if (etype === "llm_call" && str(rec.node_id) === "reason" && status === "started") {
    const n = (next.cycles[run] ?? 0) + 1;
    next.cycles = { ...next.cycles, [run]: n };
    next.activity = n > 1 ? `Thinking — step ${n}` : "Thinking";
  }
  if (etype === "llm_call" && status !== "started" && stepId && next.live[stepId]) {
    // The durable record replaces the live text (api.md "Live replies").
    const { [stepId]: _gone, ...rest } = next.live;
    next.live = rest;
    next.live_order = next.live_order.filter((c) => c !== stepId);
  }
  if (etype === "llm_call" && status !== "started" && stepId && !next.closed_calls.includes(stepId)) {
    next.closed_calls = [...next.closed_calls, stepId];
  }
  if (etype === "tool_calls" && status === "started") {
    const payload = isObj(effect.payload) ? effect.payload : {};
    const names = (Array.isArray(payload.tool_calls) ? payload.tool_calls : []).filter(isObj).map((t) => str(t.name)).filter(Boolean);
    if (names.length) next.activity = `Using ${names.join(", ")}`;
  }
  if (etype === "emit_event" && isObj(effect.payload)) {
    const p = effect.payload;
    const name = str(p.name || p.event_name).replace(/^abstractcode\./, "abstract.");
    const body = p.payload;
    if (name === "abstract.status") {
      const t = typeof body === "string" ? body.trim() : isObj(body) ? str(body.text || body.value) : "";
      if (t && !["ready", "completed"].includes(t.toLowerCase())) next.activity = t;
    } else if (name === "abstract.message") {
      const t = typeof body === "string" ? body.trim() : isObj(body) ? str(body.text || body.message) : "";
      if (t) next.notes = [...next.notes, t];
    }
  }
  if (etype === "resume" && isObj(effect.payload)) {
    const key = str(effect.payload.wait_key);
    if (key) next.waits = next.waits.filter((w) => !(w.run_id === run && w.wait_key === key));
  }

  const result = isObj(rec.result) ? rec.result : {};
  const wait = isObj(result.wait) ? result.wait : null;
  if (wait) {
    const key = str(wait.wait_key);
    const child = subworkflowRunId(wait);
    if (child) {
      if (!next.child_runs.includes(child)) next.child_runs = [...next.child_runs, child];
    } else if (key && !next.waits.some((w) => w.run_id === run && w.wait_key === key && (w.step_id === stepId || !w.step_id || !stepId))) {
      // One occurrence = one waiting record (step id). A record without a
      // step id (a synthetic rehydration) is the same pending question.
      const reason = str(wait.reason).toLowerCase();
      const calls = toolCallsOf(wait);
      let kind: PendingWait["kind"] | null = null;
      if (calls.length || isToolApprovalWait(wait)) kind = "tool_approval";
      else if (reason === "user") kind = "ask_user";
      else if (reason === "event" && eventNameFromWaitKey(key).replace(/^abstractcode\./, "abstract.") === "abstract.ask") kind = "ask_user";
      if (kind) {
        next.waits = [
          ...next.waits,
          { kind, run_id: run, wait_key: key, step_id: stepId, prompt: str(wait.prompt) || (kind === "ask_user" ? "Input required:" : ""), tool_calls: calls, state: "open" },
        ];
        next.status = "waiting";
        next.activity = kind === "tool_approval" ? "Waiting for your approval" : "Waiting for your answer";
      }
    }
  }

  if (run === next.root_run_id) {
    const text = flowEndText(rec);
    if (text !== null) next.answer = text;
  }
  if (status === "failed") {
    const r = isObj(rec.result) ? rec.result : {};
    next.error = str(rec.error) || str(r.error) || "A step failed.";
  }
  if (next.status === "waiting" && !next.waits.some((w) => w.state === "open" || w.state === "sending")) next.status = "running";
  return next;
}

function deltaAction(s: TurnState, event: string, data: Json): TurnState {
  const call = str(data.call_id);
  if (!call || s.closed_calls.includes(call)) return s;
  const prev = s.live[call] ?? { run_id: str(data.run_id), content: "", reasoning: "", ended: false };
  let cur: LiveCall = { ...prev };
  if (event === "llm.delta") {
    const channel = str(data.channel) === "reasoning" ? "reasoning" : "content";
    const t = typeof data.text === "string" ? data.text : "";
    cur = { ...cur, [channel]: data.snapshot === true ? t : cur[channel] + t };
  } else {
    cur.ended = true;
  }
  const order = s.live_order.includes(call) ? s.live_order : [...s.live_order, call];
  return { ...s, live: { ...s.live, [call]: cur }, live_order: order, status: s.status === "starting" ? "running" : s.status };
}

export function turnReducer(s: TurnState, a: TurnAction): TurnState {
  switch (a.type) {
    case "step":
      return stepAction(s, a.run_id, a.cursor, a.record);
    case "delta":
      return deltaAction(s, a.event, a.data);
    case "stream_open":
      // Every (re)connect re-sends the open calls as snapshots (api.md
      // "Snapshots"), whichever run of the turn the stream belongs to.
      return { ...s, live: {}, live_order: [] };
    case "wait_sending":
      return { ...s, waits: s.waits.map((w) => (sameWait(w, a.run_id, a.wait_key, a.step_id) ? { ...w, state: "sending" } : w)) };
    case "wait_failed":
      return { ...s, waits: s.waits.map((w) => (sameWait(w, a.run_id, a.wait_key, a.step_id) ? { ...w, state: "open", note: a.note } : w)) };
    case "wait_closed": {
      const waits = s.waits.map((w) =>
        sameWait(w, a.run_id, a.wait_key, a.step_id) ? { ...w, state: a.stale ? ("stale" as const) : ("answered" as const), note: a.note } : w,
      );
      const open = waits.some((w) => w.state === "open" || w.state === "sending");
      return { ...s, waits, status: s.status === "waiting" && !open ? "running" : s.status };
    }
    case "follow_state":
      return s.follow === a.state ? s : { ...s, follow: a.state, error: a.state === "lost" && a.note ? a.note : s.error };
    case "run_status": {
      if (a.run_id !== s.root_run_id) return s;
      const st = str(a.status).toLowerCase();
      if (st === "completed" || st === "failed" || st === "cancelled") {
        return { ...s, status: st, activity: "", live: {}, live_order: [], error: a.error ?? s.error };
      }
      return s;
    }
  }
}

/** The text to show while the answer is being written: the newest call's content. */
export function liveAnswerText(s: TurnState): string {
  for (let i = s.live_order.length - 1; i >= 0; i--) {
    const c = s.live[s.live_order[i]];
    if (c && c.content.trim()) return c.content;
  }
  return "";
}
