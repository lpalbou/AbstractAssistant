import { describe, expect, it } from "vitest";

import { eventNameFromWaitKey, flowEndText, initialTurn, liveAnswerText, turnReducer, type TurnAction, type TurnState } from "./run_events";

const fold = (s: TurnState, actions: TurnAction[]) => actions.reduce(turnReducer, s);
const step = (run_id: string, cursor: number, record: Record<string, unknown>): TurnAction => ({ type: "step", run_id, cursor, record });

// The production shape of the desktop's 16-minute stall (CLAUDE.md
// 2026-09-07; records copied from tests/basic/test_gateway_worker.py
// test_attach_reprompts_a_pending_approval_that_belongs_to_a_SUBRUN): the
// root waits on `subworkflow:sub-1`; the child holds one answered and one
// unanswered approval on keys of the same node.
const rootWait = {
  run_id: "run-root",
  node_id: "assistant_agent",
  step_id: "root-step",
  status: "waiting",
  effect: { type: "start_subworkflow", payload: {} },
  result: { wait: { reason: "user", wait_key: "subworkflow:sub-1" } },
};
const approval = (step_id: string, key: string) => ({
  run_id: "sub-1",
  node_id: "act",
  step_id,
  status: "waiting",
  effect: { type: "tool_calls", payload: {} },
  result: {
    wait: {
      reason: "user",
      wait_key: key,
      details: { mode: "approval_required", tool_calls: [{ name: "execute_command", arguments: { command: "ioreg -r" } }] },
    },
  },
});
const resume = (step_id: string, key: string) => ({
  run_id: "sub-1",
  node_id: "act",
  step_id,
  status: "completed",
  effect: { type: "resume", payload: { wait_key: key } },
  result: { resumed: true },
});

describe("turnReducer", () => {
  it("follows the child a subworkflow wait names, and never asks a question for it", () => {
    const s = fold(initialTurn("run-root"), [step("run-root", 1, rootWait)]);
    expect(s.child_runs).toEqual(["sub-1"]);
    expect(s.waits).toEqual([]);
  });

  it("replaying the child ledger leaves exactly the unanswered approval", () => {
    const answered = "tool_approval:sub-1:act:aaaa";
    const pending = "tool_approval:sub-1:act:bbbb";
    const s = fold(initialTurn("run-root"), [
      step("run-root", 1, rootWait),
      step("sub-1", 1, approval("step-a", answered)),
      step("sub-1", 2, resume("resume-a", answered)),
      step("sub-1", 3, approval("step-b", pending)),
    ]);
    expect(s.waits.map((w) => [w.kind, w.run_id, w.wait_key, w.step_id])).toEqual([["tool_approval", "sub-1", pending, "step-b"]]);
    expect(s.waits[0].tool_calls[0]).toEqual({ name: "execute_command", arguments: { command: "ioreg -r" } });
    expect(s.status).toBe("waiting");
    expect(s.cursors).toEqual({ "run-root": 1, "sub-1": 3 });
  });

  it("a second approval on the SAME key after a resume prompts again (identity is key + step)", () => {
    const key = "tool_calls:sub-1:act";
    const s = fold(initialTurn("run-root"), [
      step("sub-1", 1, approval("s1", key)),
      step("sub-1", 2, resume("r1", key)),
      step("sub-1", 3, approval("s2", key)),
    ]);
    expect(s.waits.map((w) => w.step_id)).toEqual(["s2"]);
  });

  it("the same waiting record replayed twice is one card", () => {
    const key = "tool_calls:sub-1:act";
    const s = fold(initialTurn("run-root"), [step("sub-1", 1, approval("s1", key)), step("sub-1", 1, approval("s1", key))]);
    expect(s.waits).toHaveLength(1);
  });

  it("an ask_user event wait is recognised by the fourth segment of its key", () => {
    expect(eventNameFromWaitKey("evt:run:r1:abstract.ask")).toBe("abstract.ask");
    expect(eventNameFromWaitKey("evt:abstract.ask")).toBe("abstract.ask");
    const s = fold(initialTurn("r1"), [
      step("r1", 1, { run_id: "r1", step_id: "q1", status: "waiting", result: { wait: { reason: "event", wait_key: "evt:run:r1:abstract.ask", prompt: "Which city?" } } }),
    ]);
    expect(s.waits.map((w) => [w.kind, w.prompt])).toEqual([["ask_user", "Which city?"]]);
  });

  it("an event wait for some other event is not a question", () => {
    const s = fold(initialTurn("r1"), [step("r1", 1, { run_id: "r1", step_id: "e1", status: "waiting", result: { wait: { reason: "event", wait_key: "evt:run:r1:mail.arrived" } } })]);
    expect(s.waits).toEqual([]);
  });

  it("the answer is the ROOT run's flow end, not a child's", () => {
    const s = fold(initialTurn("root"), [
      step("child", 5, { run_id: "child", status: "completed", result: { output: { response: "child text" } } }),
      step("root", 9, { run_id: "root", status: "completed", result: { output: { response: "The answer.", meta: {} } } }),
    ]);
    expect(s.answer).toBe("The answer.");
    expect(flowEndText({ result: { output: "  plain  " } })).toBe("plain");
    expect(flowEndText({ result: {} })).toBeNull();
  });

  it("live deltas build the answer; a snapshot replaces; the durable record ends the call", () => {
    let s = initialTurn("root");
    s = turnReducer(s, { type: "delta", event: "llm.delta", data: { call_id: "c1", run_id: "child", text: "Hel", channel: "content" } });
    s = turnReducer(s, { type: "delta", event: "llm.delta", data: { call_id: "c1", text: "lo", channel: "content" } });
    s = turnReducer(s, { type: "delta", event: "llm.delta", data: { call_id: "c1", text: "hmm", channel: "reasoning" } });
    expect(liveAnswerText(s)).toBe("Hello");
    s = turnReducer(s, { type: "stream_open", run_id: "root" });
    expect(liveAnswerText(s)).toBe("");
    s = turnReducer(s, { type: "delta", event: "llm.delta", data: { call_id: "c1", text: "Hello wor", channel: "content", snapshot: true } });
    expect(liveAnswerText(s)).toBe("Hello wor");
    s = turnReducer(s, step("child", 3, { run_id: "child", step_id: "c1", status: "completed", effect: { type: "llm_call" }, result: { content: "Hello world" } }));
    expect(liveAnswerText(s)).toBe("");
    s = turnReducer(s, { type: "delta", event: "llm.delta", data: { call_id: "c1", text: " late", channel: "content" } });
    expect(liveAnswerText(s)).toBe("");
  });

  it("activity follows reasoning cycles, tools and abstract.status", () => {
    let s = initialTurn("r");
    s = turnReducer(s, step("r", 1, { run_id: "r", node_id: "reason", status: "started", effect: { type: "llm_call" } }));
    expect(s.activity).toBe("Thinking");
    s = turnReducer(s, step("r", 2, { run_id: "r", status: "started", effect: { type: "tool_calls", payload: { tool_calls: [{ name: "web_search" }] } } }));
    expect(s.activity).toBe("Using web_search");
    s = turnReducer(s, step("r", 3, { run_id: "r", status: "completed", effect: { type: "emit_event", payload: { name: "abstract.status", payload: { text: "Reading sources" } } } }));
    expect(s.activity).toBe("Reading sources");
    s = turnReducer(s, step("r", 4, { run_id: "r", node_id: "reason", status: "started", effect: { type: "llm_call" } }));
    expect(s.activity).toBe("Thinking — step 2");
  });

  it("a wait closed elsewhere (or found stale) stops blocking the turn", () => {
    const key = "tool_calls:sub-1:act";
    let s = fold(initialTurn("run-root"), [step("sub-1", 1, approval("s1", key))]);
    expect(s.status).toBe("waiting");
    s = turnReducer(s, { type: "wait_closed", run_id: "sub-1", wait_key: key, step_id: "s1", stale: true, note: "Already answered" });
    expect(s.waits[0].state).toBe("stale");
    expect(s.status).toBe("running");
  });

  it("a terminal root status ends the turn and drops live text", () => {
    let s = turnReducer(initialTurn("root"), { type: "delta", event: "llm.delta", data: { call_id: "c", text: "x" } });
    s = turnReducer(s, { type: "run_status", run_id: "root", status: "cancelled" });
    expect(s.status).toBe("cancelled");
    expect(liveAnswerText(s)).toBe("");
    expect(turnReducer(s, { type: "run_status", run_id: "other", status: "failed" })).toBe(s);
  });

  it("a failed step carries its error", () => {
    const s = turnReducer(initialTurn("r"), step("r", 1, { run_id: "r", status: "failed", error: "provider down" }));
    expect(s.error).toBe("provider down");
  });
});
