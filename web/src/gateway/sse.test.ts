import { describe, expect, it } from "vitest";

import { resumeWaitCommand } from "./client";
import { SseParser } from "./sse";

describe("SseParser", () => {
  it("frames events across chunk boundaries, joins data lines, keeps ids, skips comments", () => {
    const p = new SseParser();
    expect(p.push("event: step\nid: 3\ndata: {\"cursor\":3,")).toEqual([]);
    const evs = p.push("\"record\":{}}\n\n: keep-alive\n\nevent: llm.delta\ndata: a\ndata: b\r\n\r\nevent: done\ndata: {}\n\n");
    expect(evs).toEqual([
      { event: "step", data: '{"cursor":3,"record":{}}', id: "3" },
      { event: "llm.delta", data: "a\nb", id: "3" },
      { event: "done", data: "{}", id: "3" },
    ]);
  });
});

describe("resumeWaitCommand", () => {
  it("is the desktop's resume command shape (client.py wait_response_command)", () => {
    const c = resumeWaitCommand("sub-1", "tool_approval:sub-1:act:bbbb", { approved: true });
    expect(c).toMatchObject({ run_id: "sub-1", type: "resume", payload: { wait_key: "tool_approval:sub-1:act:bbbb", payload: { approved: true } } });
    expect(String(c.command_id)).toMatch(/^resume_/);
  });
  it("refuses a command without a run or a key", () => {
    expect(() => resumeWaitCommand("", "k", {})).toThrow();
    expect(() => resumeWaitCommand("r", " ", {})).toThrow();
  });
});
