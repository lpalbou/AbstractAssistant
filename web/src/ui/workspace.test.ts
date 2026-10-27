import { describe, expect, it } from "vitest";

import { themeGroup } from "../lib/theme";
import { seenMatches, toolsetsFromDiscovery } from "./Workspace";

describe("the approval panel's inputs", () => {
  it("toolsets are the served ones; a row without one gets none (never guessed)", () => {
    const m = toolsetsFromDiscovery({ items: [{ name: "fetch_url", toolset: "web" }, { name: "mystery" }, { name: "x", toolset: "  " }, null] });
    expect([...m]).toEqual([["fetch_url", "web"]]);
    expect(toolsetsFromDiscovery({}).size).toBe(0);
  });

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
