// Shape parity with the desktop's builder: every case in the fixture was
// produced BY abstractassistant/gateway/run_input.py
// (web/scripts/gen_run_input_parity.py); the web builder must return the
// same JSON for the same arguments.
//
// The tool part is the kit's now (ui-kit `withRunTools`, backlog 0033): a case with
// `allowed_tools` composes `buildRunInputData` + `withRunTools` and must still equal the
// desktop's output. A case with `tool_policy` and no tool list has no web equivalent (the web
// always sends its tool list), so it is not a web case.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { withRunTools } from "@abstractframework/ui-kit";
import { describe, expect, it } from "vitest";

import { buildRunInputData, type RunInputArgs } from "./run_input";

type Args = RunInputArgs & { allowed_tools?: string[] | null; tool_policy?: unknown };
type Case = { name: string; args: Args; expected: unknown };
const cases: Case[] = JSON.parse(readFileSync(resolve(__dirname, "__fixtures__/run_input_parity.json"), "utf8"));

function webInput(args: Args): unknown {
  const { allowed_tools, tool_policy: _tp, ...rest } = args;
  const base = buildRunInputData(rest);
  if (allowed_tools === undefined || allowed_tools === null) return base;
  const tools = allowed_tools.map((t) => String(t).trim()).filter(Boolean);
  return withRunTools(base, { tools, allowed_tools: tools, approval: { auto: [], ask: [] } });
}

describe("buildRunInputData (parity with gateway/run_input.py)", () => {
  const webCases = cases.filter((c) => !(c.args.tool_policy && !c.args.allowed_tools));
  it("the fixture has cases", () => {
    expect(webCases.length).toBeGreaterThanOrEqual(10);
  });
  for (const c of webCases) {
    it(c.name, () => {
      expect(JSON.parse(JSON.stringify(webInput(c.args)))).toEqual(c.expected);
    });
  }
  it("refuses a stream switch that is not a boolean", () => {
    expect(() => buildRunInputData({ prompt: "x", stream: "yes" as unknown as boolean })).toThrow(/stream must be/);
  });
});
