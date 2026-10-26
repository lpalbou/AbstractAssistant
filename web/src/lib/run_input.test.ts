// Shape parity with the desktop's builder: every case in the fixture was
// produced BY abstractassistant/gateway/run_input.py
// (web/scripts/gen_run_input_parity.py); the web builder must return the
// same JSON for the same arguments.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { buildRunInputData, type RunInputArgs } from "./run_input";

type Case = { name: string; args: RunInputArgs; expected: unknown };
const cases: Case[] = JSON.parse(readFileSync(resolve(__dirname, "__fixtures__/run_input_parity.json"), "utf8"));

describe("buildRunInputData (parity with gateway/run_input.py)", () => {
  it("the fixture has cases", () => {
    expect(cases.length).toBeGreaterThanOrEqual(10);
  });
  for (const c of cases) {
    it(c.name, () => {
      expect(JSON.parse(JSON.stringify(buildRunInputData(c.args)))).toEqual(c.expected);
    });
  }
  it("refuses a stream switch that is not a boolean", () => {
    expect(() => buildRunInputData({ prompt: "x", stream: "yes" as unknown as boolean })).toThrow(/stream must be/);
  });
});
