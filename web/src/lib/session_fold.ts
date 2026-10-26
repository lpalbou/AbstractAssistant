/**
 * The session list, as the gateway knows it: one row per `session_id` over
 * one `GET /api/gateway/runs?root_only=true` page.
 *
 * A PORT of this repository's abstractassistant/core/gateway_sessions.py
 * `fold_session_rows` (backlog 0853), itself aligned with AbstractCode's
 * `fold_session_rows` (abstractcode/tui/src/runner.rs). Divergence between
 * the three is a bug; the tests run this fold on the SAME fixture as the
 * Python tests (tests/basic/fixtures/gateway_runs/runs_page.json).
 *
 * - no `session_id` or no `run_id`: not a session;
 * - `session_kind` other than chat / discussion / unstamped: not a regular
 *   session (automations list their occurrences elsewhere);
 * - a child run (`parent_run_id`) is never a turn;
 * - recency = newest `updated_at` (else `created_at`), the paging field;
 * - state = the liveliest run: waiting > running > failed/cancelled > completed;
 *   an unreported status is "unknown", never "done";
 * - first run (oldest `created_at`) holds the opening prompt; latest run
 *   (newest `created_at`) anchors the transcript (its history bundle carries
 *   every turn up to it);
 * - `has_more` other than an explicit `false` = truncated.
 */

export type SessionState = "waiting" | "running" | "failed" | "done" | "unknown";

export type SessionRow = {
  session_id: string;
  state: SessionState;
  updated_at: string;
  created_at: string;
  first_run_id: string;
  latest_run_id: string;
  turns: number;
  session_kind: string;
  automation_id: string;
  workspace_root: string;
  workspace_reported: boolean;
};

const STATE_RANK: Record<SessionState, number> = { waiting: 4, running: 3, failed: 2, done: 1, unknown: 0 };
const STATUS_TO_STATE: Record<string, SessionState> = {
  waiting: "waiting",
  running: "running",
  failed: "failed",
  cancelled: "failed",
  completed: "done",
};
// abstractassistant/core/automations.py REGULAR_SESSION_KINDS (+ "" = unstamped).
const REGULAR_KINDS = new Set(["", "chat", "discussion"]);

type Run = Record<string, unknown>;

const text = (v: unknown): string => (typeof v === "string" ? v.trim() : "");
const activity = (r: Run) => text(r.updated_at) || text(r.created_at);
const created = (r: Run) => text(r.created_at) || activity(r);
const stateFor = (r: Run): SessionState => STATUS_TO_STATE[text(r.status).toLowerCase()] ?? "unknown";

/** Milliseconds; an unparseable or missing stamp sorts as the oldest possible. */
function when(stamp: string): number {
  const t = Date.parse(stamp);
  return Number.isFinite(t) ? t : Number.NEGATIVE_INFINITY;
}

export function foldSessionRows(payload: unknown): { rows: SessionRow[]; truncated: boolean } {
  const body = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
  const items = Array.isArray(body.items) ? body.items : Array.isArray(body.runs) ? body.runs : [];
  const truncated = body.has_more !== false;

  const groups = new Map<string, Array<[number, Run]>>();
  items.forEach((run, index) => {
    if (!run || typeof run !== "object") return;
    const r = run as Run;
    if (!REGULAR_KINDS.has(text(r.session_kind))) return;
    if (text(r.parent_run_id)) return;
    const sid = text(r.session_id);
    const rid = text(r.run_id);
    if (!sid || !rid) return;
    const g = groups.get(sid) ?? [];
    g.push([index, r]);
    groups.set(sid, g);
  });

  const pick = (group: Array<[number, Run]>, key: (r: Run) => string, newest: boolean): Run => {
    // Ties go to the earlier position in the page (newest-first listing).
    let best = group[0];
    for (const entry of group.slice(1)) {
      const a = when(key(entry[1]));
      const b = when(key(best[1]));
      if (newest ? a > b || (a === b && entry[0] < best[0]) : a < b || (a === b && entry[0] < best[0])) best = entry;
    }
    return best[1];
  };

  const rows: SessionRow[] = [];
  for (const [sid, group] of groups) {
    let state: SessionState = "unknown";
    for (const [, r] of group) {
      const c = stateFor(r);
      if (STATE_RANK[c] > STATE_RANK[state]) state = c;
    }
    const newest = pick(group, activity, true);
    const oldest = pick(group, created, false);
    const latest = pick(group, created, true);
    const kind = group.map(([, r]) => text(r.session_kind)).find(Boolean) ?? "";
    const automation = group.map(([, r]) => text(r.automation_id)).find(Boolean) ?? "";
    rows.push({
      session_id: sid,
      state,
      updated_at: activity(newest),
      created_at: created(oldest),
      first_run_id: text(oldest.run_id),
      latest_run_id: text(latest.run_id),
      turns: group.length,
      session_kind: kind,
      automation_id: kind === "discussion" ? automation : "",
      workspace_root: text(latest.workspace_root),
      workspace_reported: "workspace_root" in latest,
    });
  }
  // Newest first by the paging field; ties by id (stable), as the Python fold.
  rows.sort((a, b) => (a.session_id < b.session_id ? -1 : a.session_id > b.session_id ? 1 : 0));
  rows.sort((a, b) => {
    const x = when(a.updated_at);
    const y = when(b.updated_at);
    return x === y ? 0 : x > y ? -1 : 1;
  });
  return { rows, truncated };
}

/** The prompt a run started with, from `GET /runs/{id}/input_data` (gateway_sessions.py prompt_from_input_data). */
export function promptFromInputData(payload: unknown): string {
  const body = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
  for (const node of [body.input_data, body]) {
    if (!node || typeof node !== "object") continue;
    const n = node as Record<string, unknown>;
    const prompt = text(n.prompt);
    if (prompt) return prompt;
    const ctx = n.context;
    if (ctx && typeof ctx === "object") {
      const task = text((ctx as Record<string, unknown>).task);
      if (task) return task;
    }
  }
  return "";
}
