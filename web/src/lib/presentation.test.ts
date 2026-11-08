import { describe, expect, it } from "vitest";
import { assistantPresence, conversationPresentation, replyToRead } from "./presentation";
import { parseAssistantPreferences } from "../ui/useAssistantPreferences";

describe("a conversation contains exchanges, not transport diagnostics", () => {
  it("moves only known informational streaming notices to details and preserves real warnings/errors", () => {
    const result = conversationPresentation([
      { id: "stream-unavailable:r:structured_output", role: "system", level: "info", content: "Delivered at completion" },
      { id: "error:r", role: "system", level: "error", content: "The model failed" },
      { id: "history:r", role: "system", level: "warn", content: "History is unavailable" },
      { id: "r:final", runId: "r", role: "assistant", content: "Hello" },
    ]);
    expect(result.diagnostics.map((m) => m.id)).toEqual(["stream-unavailable:r:structured_output"]);
    expect(result.conversation.map((m) => m.content)).toEqual(["The model failed", "History is unavailable", "Hello"]);
    expect(result.conversation.at(-1)?.title).toBe("Assistant");
  });
  it("reads only a finished, written reply belonging to the requested turn", () => {
    const messages = [
      { id: "old", runId: "previous", role: "assistant", content: "Old answer" },
      { id: "live", runId: "r", role: "assistant", content: "Working", live: { callId: "c", reasoning: "" } },
      { id: "final", runId: "r", role: "assistant", content: "New answer" },
    ];
    expect(replyToRead(messages, "r")?.id).toBe("final");
    expect(replyToRead(messages, "another")).toBeUndefined();
  });
});

describe("who answered (the gateway's turn author)", () => {
  const castor = { kind: "entity" as const, name: "Castor", entity_id: "entity:castor", identity_ref: "entity:castor#3", avatar: { style: "watch-halo", color: "#336699" } };
  const agent = { kind: "agent" as const, name: "Basic agent", entity_id: null, identity_ref: null, avatar: null };
  const person = { kind: "person" as const, name: "Laurent", entity_id: null, identity_ref: null, avatar: null };

  it("shows a mention turn's answer, not its prompt (the message already shown in the person's turn)", () => {
    const { conversation } = conversationPresentation([
      { id: "r:input", runId: "r", role: "user", kind: "prompt", content: "Which plan?", author: person },
      { id: "r:final", runId: "r", role: "assistant", kind: "final", content: "The second.", author: agent },
      { id: "m:input", runId: "m", role: "user", kind: "prompt", content: "Which plan?", author: person },
      { id: "m:final", runId: "m", role: "assistant", kind: "final", content: "Agreed.", author: castor },
    ], { mentionTurns: new Set(["m"]) });
    expect(conversation.map((m) => m.id)).toEqual(["r:input", "r:final", "m:final"]);
    expect(conversation.at(-1)?.author).toEqual(castor);
    // Without the mention turn known, every prompt stays.
    expect(conversationPresentation([{ id: "m:input", runId: "m", role: "user", content: "Which plan?" }]).conversation).toHaveLength(1);
  });

  it("names the followed turn's live reply by the run's author; other runs and authored messages are left alone", () => {
    const { conversation } = conversationPresentation([
      { id: "live:r:c1", runId: "r", role: "assistant", content: "Writ", live: { callId: "c1", reasoning: "" } },
      { id: "live:child:c2", runId: "child", role: "assistant", content: "sub", live: { callId: "c2", reasoning: "", caption: "sub-agent · x" } },
      { id: "old:final", runId: "old", role: "assistant", content: "Before", author: null },
    ], { liveAuthor: { runId: "r", author: agent } });
    expect(conversation.map((m) => m.author)).toEqual([agent, undefined, null]);
  });

  it("an older gateway (no author anywhere) keeps today's 'Assistant' header", () => {
    const { conversation } = conversationPresentation([
      { id: "live:r:c1", runId: "r", role: "assistant", content: "Writ", live: { callId: "c1", reasoning: "" } },
      { id: "r:final", runId: "r", role: "assistant", content: "Done" },
    ], { liveAuthor: { runId: "r", author: null } });
    expect(conversation.map((m) => [m.title, "author" in m])).toEqual([["Assistant", false], ["Assistant", false]]);
  });
});

describe("the avatar reflects the current job", () => {
  const ready = { recording: false, transcribing: false, playback: "idle", pending: false, busy: false, working: false, failed: false, loading: false };
  it("gives user interaction and new work priority over old speech", () => {
    expect(assistantPresence({ ...ready, recording: true, playback: "playing" }).pose).toBe("listening");
    expect(assistantPresence({ ...ready, pending: true, busy: true }).pose).toBe("waiting");
    expect(assistantPresence({ ...ready, busy: true, working: true, playback: "playing" }).pose).toBe("working");
    expect(assistantPresence({ ...ready, busy: true }).pose).toBe("thinking");
  });
  it("distinguishes paused speech, failures, ready and transcribing", () => {
    expect(assistantPresence({ ...ready, playback: "paused" }).label).toBe("Paused");
    expect(assistantPresence({ ...ready, failed: true }).pose).toBe("error");
    expect(assistantPresence({ ...ready, transcribing: true }).label).toMatch(/Writing down/);
    expect(assistantPresence(ready).pose).toBe("ready");
  });
});

describe("browser avatar preferences", () => {
  it("recovers from broken storage and refuses unsafe design identifiers", () => {
    expect(parseAssistantPreferences("{broken")).toEqual({ design: "watch-hover", animated: true });
    expect(parseAssistantPreferences('{"design":"../../file","animated":"false"}')).toEqual({ design: "watch-hover", animated: true });
    expect(parseAssistantPreferences('{"design":"vortex","animated":false}')).toEqual({ design: "vortex", animated: false });
  });
});
