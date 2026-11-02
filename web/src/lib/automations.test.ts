import { describe, expect, it } from "vitest";
import type { AutomationSummary, OccurrenceRow, RunToolPlan } from "@abstractframework/ui-kit";

import {
  AUTOMATION_INTERFACE,
  RUNS_SHOWN,
  automationSections,
  everyChoices,
  everyLabel,
  latestDiscussable,
  newAutomationBody,
  runMessages,
  titleAfterTask,
  titleOfTask,
  tokensOf,
  waitingRun,
  type AutomationsListing,
} from "./automations";

const row = (id: string, status: string, section?: string): AutomationSummary =>
  ({ automation_id: id, title: id, status, ...(section ? { section } : {}) }) as unknown as AutomationSummary;

const run = (index: number, status: string, extra: Partial<OccurrenceRow> = {}): OccurrenceRow => ({
  run_id: `r${index}`, index, attempts: 1, fired_at: `2026-11-0${Math.min(index, 9)}T08:00:00Z`, status,
  trigger: { source_id: "schedule", summary: "" }, user_turn: `Check ${index}`, answer: status === "completed" ? `Answer ${index}` : "",
  notify: null, artifacts: [], waits: [], ledger_url: "", ...extra,
});

const tools: RunToolPlan = { tools: ["web_search", "write_file"], allowed_tools: ["web_search", "write_file"], tool_policy: { auto_approve_tools: ["web_search"], require_approval_tools: [] } };

describe("the list (ADR 0048)", () => {
  it("draws the served order and folds the paused ones with the gateway's count", () => {
    const page: AutomationsListing = { items: [row("b", "active", "active"), row("a", "completed", "active"), row("p", "paused", "paused")], next_cursor: null,
      paused_automations_count: 4, archived_automations_count: 2, archived_automations: 2 };
    const s = automationSections(page);
    expect(s.main.map((r) => r.automation_id)).toEqual(["b", "a"]);
    expect(s.paused.map((r) => r.automation_id)).toEqual(["p"]);
    expect([s.pausedCount, s.archivedCount]).toEqual([4, 2]);
  });

  it("an older gateway (no section) gets every row as served and no Paused section", () => {
    const s = automationSections({ items: [row("p", "paused"), row("a", "active")], next_cursor: null, archived_automations: 3 });
    expect(s.main.map((r) => r.automation_id)).toEqual(["p", "a"]);
    expect([s.paused.length, s.pausedCount, s.archivedCount]).toEqual([0, 0, 3]);
  });
});

describe("a new automation, as the watch writes it", () => {
  it("the gateway's default workflow, every 12 hours, its tools and no memory", () => {
    const body = newAutomationBody({ requestId: "q1", task: "  Check the news\nand summarize  ", workflow: null, when: { kind: "every", every: "12h" },
      buildsOnEarlierRuns: false, growingMaxTokens: 30_000, tools });
    expect(body).toEqual({
      request_id: "q1",
      title: "Check the news",
      target: { flow_id: "@default", interface: AUTOMATION_INTERFACE, input_data: { prompt: "Check the news\nand summarize", tools: ["web_search", "write_file"],
        _runtime: { allowed_tools: ["web_search", "write_file"], tool_policy: { auto_approve_tools: ["web_search"], require_approval_tools: [] } } } },
      trigger: { source_id: "schedule", source_version: 2, config: { kind: "every", every: "12h" } },
      context: { mode: "independent" },
      policy: { tool_approval: "auto" },
    });
  });

  it("a chosen workflow keeps its inputs; daily at a time; memory with its budget; ask when a tool asks", () => {
    const body = newAutomationBody({ requestId: "q2", task: "Digest", workflow: { bundle_ref: "digest@1.0.0", flow_id: "main", input_data: { prompt: "Digest", lang: "fr", _runtime: { keep: true } } },
      when: { kind: "daily", at: "08:00" }, buildsOnEarlierRuns: true, growingMaxTokens: 40_000,
      tools: { ...tools, tool_policy: { auto_approve_tools: [], require_approval_tools: ["write_file"] } } });
    expect(body.target).toEqual({ bundle_ref: "digest@1.0.0", flow_id: "main", input_data: { prompt: "Digest", lang: "fr", tools: ["web_search", "write_file"],
      _runtime: { keep: true, allowed_tools: ["web_search", "write_file"], tool_policy: { auto_approve_tools: [], require_approval_tools: ["write_file"] } } } });
    expect(body.trigger).toEqual({ source_id: "schedule", source_version: 2, config: { kind: "daily", at: "08:00" } });
    expect(body.context).toEqual({ mode: "growing", growing: { max_tokens: 40_000 } });
    expect(body.policy).toEqual({ tool_approval: "ask" });
  });

  it("titles: the task's first line, at most 120 characters; a title named by its task follows it", () => {
    expect(titleOfTask("x".repeat(130))).toBe(`${"x".repeat(119)}…`);
    expect(titleAfterTask("New task", "Old task", "Old task")).toBe("New task");
    expect(titleAfterTask("New task", "My own name", "Old task")).toBeNull();
    expect(titleAfterTask("y".repeat(200), "x".repeat(120), "x".repeat(130))).toBe("y".repeat(120));
  });
});

describe("choices and typed numbers", () => {
  it("the watch's intervals, its own first when none is it", () => {
    expect(everyLabel("1h")).toBe("Every hour");
    expect(everyLabel("12h")).toBe("Every 12 hours");
    expect(everyChoices("60m")[0]).toBe("30s");
    expect(everyChoices("90m")[0]).toBe("90m");
  });

  it("tokens: whole numbers, separators allowed", () => {
    expect(tokensOf("50,000")).toBe(50_000);
    expect(tokensOf("50 000")).toBe(50_000);
    expect(tokensOf("lots")).toBeNull();
    expect(tokensOf("0")).toBeNull();
  });
});

describe("its runs as the conversation's messages", () => {
  it("oldest first: what its trigger sent, then the answer, a failure, a wait, a run in progress", () => {
    const rows = [run(4, "running"), run(3, "waiting", { waits: [{ run_id: "r3", wait_key: "k", kind: "tool_approval", reason: "user" }] }),
      run(2, "failed", { failure: { reason_code: "x", message: "the provider timed out", attempts: 1 } }), run(1, "completed")];
    const m = runMessages(rows);
    expect(m.map((x) => [x.role, x.content])).toEqual([
      ["user", "Check 1"], ["assistant", "Answer 1"],
      ["user", "Check 2"], ["assistant", "It failed: the provider timed out"],
      ["user", "Check 3"], ["assistant", "Waiting for you."],
      ["user", "Check 4"], ["assistant", "Working…"],
    ]);
    expect(m[3].level).toBe("error");
    expect(waitingRun(rows)?.run_id).toBe("r3");
    expect(latestDiscussable(rows)).toBe(2);
  });

  it("the latest ten only", () => {
    const rows = Array.from({ length: 12 }, (_, i) => run(12 - i, "completed"));
    const answers = runMessages(rows).filter((x) => x.role === "assistant");
    expect(answers).toHaveLength(RUNS_SHOWN);
    expect(answers[0].content).toBe("Answer 3");
    expect(latestDiscussable([])).toBeNull();
  });
});
