import { describe, expect, it } from "vitest";

import type { SessionRow } from "./session_fold";
import { eventTouchesList, loadTitles, mapLimit, TITLE_CONCURRENCY } from "./titles";

const row = (n: number): SessionRow => ({
  session_id: `s${n}`,
  state: "done",
  updated_at: "",
  created_at: "",
  first_run_id: `r${n}`,
  latest_run_id: `r${n}`,
  turns: 1,
  session_kind: "chat",
  automation_id: "",
  workspace_root: "",
  workspace_reported: true,
});

describe("titles (fix 14)", () => {
  it("are fetched in parallel, never more than the limit at once, and in order", async () => {
    let inFlight = 0;
    let peak = 0;
    const out = await mapLimit([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 3, async (n) => {
      inFlight++;
      peak = Math.max(peak, inFlight);
      await new Promise((r) => setTimeout(r, 5));
      inFlight--;
      return n * 2;
    });
    expect(out).toEqual([2, 4, 6, 8, 10, 12, 14, 16, 18, 20]);
    expect(peak).toBe(3);
  });

  it("are cached: a second refresh asks nothing; a failure is retried next time and counted", async () => {
    const asked: string[] = [];
    let fail = true;
    const inputData = async (rid: string) => {
      asked.push(rid);
      if (rid === "r2" && fail) throw new Error("502");
      return { input_data: { prompt: `title ${rid}` } };
    };
    const cache = new Map<string, string>();
    const rows = [row(1), row(2), row(3)];
    expect(await loadTitles(rows, cache, inputData)).toEqual({ fetched: 2, failed: 1 });
    expect(cache.get("s1")).toBe("title r1");
    expect(cache.has("s2")).toBe(false);
    fail = false;
    asked.length = 0;
    expect(await loadTitles(rows, cache, inputData)).toEqual({ fetched: 1, failed: 0 });
    expect(asked).toEqual(["r2"]);
    expect(TITLE_CONCURRENCY).toBeLessThanOrEqual(4);
  });

  it("only events of listed sessions, or a person's new run, refresh the list", () => {
    const visible = new Set(["s1"]);
    expect(eventTouchesList({ session_id: "s1", origin: { kind: "system" } }, visible)).toBe(true);
    expect(eventTouchesList({ session_id: "new", origin: { kind: "person" } }, visible)).toBe(true);
    expect(eventTouchesList({ session_id: "occ", origin: { kind: "automation" } }, visible)).toBe(false);
  });
});
