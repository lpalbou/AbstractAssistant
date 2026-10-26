// The SAME fixture and the SAME expectations as the Python fold's tests
// (tests/basic/test_gateway_session_fold.py): a divergence fails here.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { foldSessionRows, promptFromInputData, type SessionRow } from "./session_fold";

const FIXTURES = resolve(__dirname, "../../../tests/basic/fixtures/gateway_runs");
const page = () => JSON.parse(readFileSync(resolve(FIXTURES, "runs_page.json"), "utf8"));
const byId = (rows: SessionRow[]) => Object.fromEntries(rows.map((r) => [r.session_id, r]));

describe("foldSessionRows (parity with core/gateway_sessions.py)", () => {
  it("one row per session, newest first by updated_at", () => {
    const { rows, truncated } = foldSessionRows(page());
    expect(truncated).toBe(false);
    expect(rows.map((r) => r.session_id)).toEqual(["sess_hot", "sess_alpha", "sess_cold", "sess_beta", "sess_unknown"]);
    expect(byId(rows).sess_no_run_id).toBeUndefined();
  });

  it("turns are root runs; first and latest runs come from created_at", () => {
    const rows = byId(foldSessionRows(page()).rows);
    expect(rows.sess_alpha.turns).toBe(3);
    expect(rows.sess_alpha.first_run_id).toBe("run_alpha_1");
    expect(rows.sess_alpha.latest_run_id).toBe("run_alpha_3");
    expect(rows.sess_alpha.updated_at).toBe("2026-09-26T08:05:00+00:00");
    expect(rows.sess_alpha.created_at).toBe("2026-09-20T09:00:00+00:00");
    expect(rows.sess_beta.turns).toBe(2);
    expect(rows.sess_beta.first_run_id).toBe("run_beta_1");
    expect(rows.sess_beta.latest_run_id).toBe("run_beta_2");
  });

  it("state is the liveliest run; unknown is never done", () => {
    const rows = byId(foldSessionRows(page()).rows);
    expect(rows.sess_alpha.state).toBe("waiting");
    expect(rows.sess_beta.state).toBe("running");
    expect(rows.sess_cold.state).toBe("done");
    expect(rows.sess_unknown.state).toBe("unknown");
    expect(rows.sess_unknown.updated_at).toBe("2026-09-23T09:00:00+00:00");
  });

  it("an unknown status loses to any real one", () => {
    const { rows } = foldSessionRows({
      items: [
        { run_id: "a", session_id: "S", status: "queued", updated_at: "2026-08-28T10:00:00Z" },
        { run_id: "b", session_id: "S", status: "waiting", updated_at: "2026-08-28T09:00:00Z" },
      ],
      has_more: false,
    });
    expect(rows[0].state).toBe("waiting");
  });

  it("a page without an explicit has_more false is truncated", () => {
    const p = page();
    p.has_more = true;
    expect(foldSessionRows(p).truncated).toBe(true);
    delete p.has_more;
    expect(foldSessionRows(p).truncated).toBe(true);
  });

  it("automation and occurrence turns are not regular sessions; child runs are not turns", () => {
    const { rows } = foldSessionRows({
      items: [
        { run_id: "o1", session_id: "auto", session_kind: "occurrence", status: "completed" },
        { run_id: "c1", session_id: "chat", session_kind: "chat", status: "completed", created_at: "2026-10-01T00:00:00Z" },
        { run_id: "c2", session_id: "chat", session_kind: "chat", parent_run_id: "c1", status: "waiting" },
        { run_id: "d1", session_id: "disc", session_kind: "discussion", automation_id: "a7", status: "completed" },
      ],
      has_more: false,
    });
    expect(rows.map((r) => r.session_id).sort()).toEqual(["chat", "disc"]);
    const r = byId(rows);
    expect(r.chat.turns).toBe(1);
    expect(r.chat.state).toBe("done");
    expect(r.disc.automation_id).toBe("a7");
  });

  it("the opening prompt reads input_data.prompt, a bare prompt, or context.task", () => {
    const answers = JSON.parse(readFileSync(resolve(FIXTURES, "input_data.json"), "utf8"));
    expect(promptFromInputData(answers.run_alpha_1)).toBe("Plan the Q3 launch checklist");
    expect(promptFromInputData(answers.run_hot_1)).toBe("Refactor the router module");
    expect(promptFromInputData(answers.run_unknown_1)).toBe("");
    expect(promptFromInputData({ input_data: { context: { task: "from the task" } } })).toBe("from the task");
  });
});
