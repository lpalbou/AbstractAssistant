// Fix 3 (adversary finding 4): the runtime reuses ONE wait key per node for
// every approval batch, and GET /runs/{id} has no step id, so before a card
// answers, the run's CURRENT waiting record must still show the same batch.
import { describe, expect, it } from "vitest";

import { initialTurn, turnReducer, waitStillMatches } from "./run_events";
import type { PendingWait } from "./types";

const KEY = "tool_calls:sub-1:act";
const card = (calls: PendingWait["tool_calls"], kind: PendingWait["kind"] = "tool_approval", prompt = ""): PendingWait => ({
  kind,
  run_id: "sub-1",
  wait_key: KEY,
  step_id: "s1",
  prompt,
  tool_calls: calls,
  state: "open",
});
const running = (calls: unknown[], extra: Record<string, unknown> = {}) => ({
  status: "waiting",
  waiting: { reason: "user", wait_key: KEY, details: { mode: "approval_required", tool_calls: calls }, ...extra },
});

describe("waitStillMatches", () => {
  const seen = [{ name: "execute_command", arguments: { command: "ls" }, call_id: "0" }];

  it("the same batch on the same key may be answered (argument key order does not matter)", () => {
    expect(waitStillMatches(card(seen), running([{ name: "execute_command", call_id: "0", arguments: { command: "ls" } }]))).toEqual({ ok: true });
    const two = [{ name: "a", arguments: { x: 1, y: 2 }, call_id: "1" }];
    expect(waitStillMatches(card(two), running([{ name: "a", arguments: { y: 2, x: 1 }, call_id: "1" }]))).toEqual({ ok: true });
  });

  it("a NEWER batch on the reused key is refused: the person never saw it", () => {
    const r = waitStillMatches(card(seen), running([{ name: "execute_command", arguments: { command: "rm -rf build" }, call_id: "0" }]));
    expect(r.ok).toBe(false);
  });

  it("a waiting record that names no calls is refused, not trusted", () => {
    expect(waitStillMatches(card(seen), running([])).ok).toBe(false);
    // Nothing on either side is not "the same batch": an empty card never approves blind.
    expect(waitStillMatches(card([]), running([])).ok).toBe(false);
  });

  it("not waiting, or waiting on another key, is refused", () => {
    expect(waitStillMatches(card(seen), { status: "running", waiting: null }).ok).toBe(false);
    expect(waitStillMatches(card(seen), { status: "waiting", waiting: { wait_key: "other", details: { tool_calls: seen } } }).ok).toBe(false);
  });

  it("a question compares its prompt", () => {
    const q = card([], "ask_user", "Which city?");
    expect(waitStillMatches(q, { status: "waiting", waiting: { wait_key: KEY, prompt: "Which city?" } })).toEqual({ ok: true });
    expect(waitStillMatches(q, { status: "waiting", waiting: { wait_key: KEY, prompt: "Which date?" } }).ok).toBe(false);
  });
});

describe("a turn whose follower gave up", () => {
  it("is marked lost with the reason (the UI then disables its cards)", () => {
    const s = turnReducer(initialTurn("r"), { type: "follow_state", state: "lost", note: "Live updates stopped" });
    expect(s.follow).toBe("lost");
    expect(s.error).toBe("Live updates stopped");
  });
});
