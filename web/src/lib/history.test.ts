import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { messagesFromHistoryBundle } from "./history";

describe("messagesFromHistoryBundle (history_seed.py _seed_from_session_turns)", () => {
  it("one user line per prompt (with attachment refs), one assistant line per answer", () => {
    const seed = messagesFromHistoryBundle({
      session: {
        turns: [
          { run_id: "r1", created_at: "t1", updated_at: "t2", prompt: "Look at this", answer: "A cat.", attachments: [{ $artifact: "a1", filename: "cat.png", content_type: "image/png" }, { filename: "no ref" }] },
          { run_id: "r2", created_at: "t3", prompt: "And now?", answer: "" },
        ],
      },
      warnings: [{ code: "ledger_tail_window", detail: "truncated" }],
    });
    expect(seed.messages.map((m) => [m.id, m.role, m.text])).toEqual([
      ["r1:user", "user", "Look at this"],
      ["r1:answer", "assistant", "A cat."],
      ["r2:user", "user", "And now?"],
    ]);
    expect(seed.messages[0].attachments).toEqual([{ $artifact: "a1", filename: "cat.png", content_type: "image/png" }]);
    expect(seed.warnings).toEqual(["ledger_tail_window: truncated"]);
  });

  it("reads the Python fixture's bundles", () => {
    const bundles = JSON.parse(readFileSync(resolve(__dirname, "../../../tests/basic/fixtures/gateway_runs/history_bundles.json"), "utf8"));
    for (const b of Object.values(bundles) as unknown[]) {
      if (b && typeof b === "object" && "session" in (b as object)) expect(() => messagesFromHistoryBundle(b)).not.toThrow();
    }
  });

  it("a bundle without session turns is an error, not an empty conversation", () => {
    expect(() => messagesFromHistoryBundle({ root_run_id: "r" })).toThrow(/no session turns/);
  });
});
