import { describe, expect, it } from "vitest";

import { themeGroup } from "../lib/theme";
import { seenMatches, turnOutcome } from "./Workspace";

describe("the approval panel's inputs", () => {
  it("an attention.seen closes only the wait it names (run, key, and step when both have one)", () => {
    const wait = { runId: "r", waitKey: "k", stepId: "s1" };
    expect(seenMatches({ run_id: "r", wait_key: "k", step_id: "s1", outcome: "approved" }, wait)).toBe(true);
    expect(seenMatches({ run_id: "r", wait_key: "k", outcome: "approved" }, wait)).toBe(true);
    expect(seenMatches({ run_id: "r", wait_key: "k", step_id: "s2", outcome: "approved" }, wait)).toBe(false);
    expect(seenMatches({ run_id: "other", wait_key: "k", outcome: "approved" }, wait)).toBe(false);
    expect(seenMatches(null, wait)).toBe(false);
    expect(seenMatches({ run_id: "r", wait_key: "k", outcome: "x" }, null)).toBe(false);
  });
});

describe("appearance", () => {
  it("the design palette follows the kit theme's group", () => {
    expect(themeGroup("dark")).toBe("dark");
    expect(themeGroup("light")).toBe("light");
    expect(themeGroup("catppuccin-latte")).toBe("light");
    expect(themeGroup("nord")).toBe("dark");
    expect(themeGroup("no-such-theme")).toBe("dark");
  });
});

describe("an ended turn says what happened when the transcript cannot", () => {
  it("a failure gives its reason; no reply is said; an answered or stopped turn says nothing", () => {
    expect(turnOutcome("r", "failed", { error: "provider down" }, [])).toBe("The run failed: provider down");
    expect(turnOutcome("r", "failed", {}, [])).toMatch(/no reason/);
    expect(turnOutcome("r", "completed", {}, [])).toBe("The run ended without a written reply.");
    expect(turnOutcome("r", "completed", {}, [{ id: "final:r", role: "assistant" }])).toBe("");
    expect(turnOutcome("r", "completed", {}, [{ id: "answer:r:3", role: "assistant" }])).toBe("");
    expect(turnOutcome("r", "completed", {}, [{ id: "r:final", runId: "r", role: "assistant", content: "A replay-view answer" }])).toBe("");
    expect(turnOutcome("r", "completed", {}, [{ id: "r:live", runId: "r", role: "assistant", content: "Still writing", live: {} }])).toMatch(/without a written reply/);
    expect(turnOutcome("r", "completed", {}, [{ id: "final:other", role: "assistant" }])).toMatch(/without a written reply/);
    expect(turnOutcome("r", "cancelled", {}, [])).toBe("");
    expect(turnOutcome("r", "running", {}, [])).toBe("");
    expect(turnOutcome("", "completed", {}, [])).toBe("");
  });
  it("a turn addressed to entities whose agent said nothing shows no line; its failure still does", () => {
    // AbstractGateway c26d38a2: an empty reply is served as no answer (the view holds only the words).
    const words = [{ id: "r:user", runId: "r", role: "user", content: "@Castor does the bridge hold?" }];
    expect(turnOutcome("r", "completed", {}, words, { entitiesAnswer: true })).toBe("");
    expect(turnOutcome("r", "completed", {}, words, { entitiesAnswer: false })).toBe("The run ended without a written reply.");
    expect(turnOutcome("r", "completed", {}, words)).toBe("The run ended without a written reply.");
    expect(turnOutcome("r", "failed", { error: "provider down" }, words, { entitiesAnswer: true })).toBe("The run failed: provider down");
  });
});
