import { describe, expect, it } from "vitest";
import { assistantPresence, conversationPresentation, replyToRead } from "./presentation";
import type { ChatMessage } from "../vendor/abstractchat/conversation.js";
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
  const pollux = { kind: "entity" as const, name: "Pollux", entity_id: "entity:pollux", identity_ref: null, avatar: null };
  const agent = { kind: "agent" as const, name: "Basic agent", entity_id: null, identity_ref: null, avatar: null };
  const person = { kind: "person" as const, name: "Laurent", entity_id: null, identity_ref: null, avatar: null };
  const turn: ChatMessage[] = [
    { id: "r:input", runId: "r", role: "user", kind: "prompt", content: "Which plan?", author: person, ts: "2026-11-08T10:00:00Z" },
    { id: "r:final", runId: "r", role: "assistant", kind: "final", content: "The second.", author: agent, ts: "2026-11-08T10:00:20Z" },
    { id: "m:input", runId: "m", role: "user", kind: "prompt", content: "Which plan?", author: person, ts: "2026-11-08T10:00:01Z" },
    { id: "m:final", runId: "m", role: "assistant", kind: "final", content: "Agreed.", author: castor, ts: "2026-11-08T10:00:30Z" },
  ];

  it("folds a mention's repeated words into the turn it repeats (repeat_of): the message shows once", () => {
    const { conversation } = conversationPresentation(turn, { repeats: new Map([["m", "r"]]) });
    expect(conversation.map((m) => m.id)).toEqual(["r:input", "r:final", "m:final"]);
    expect(conversation.at(-1)?.author).toEqual(castor);
  });

  it("keeps the words of a mention sent on its own, or whose repeated turn is not on screen", () => {
    expect(conversationPresentation(turn).conversation).toHaveLength(4);
    expect(conversationPresentation(turn.slice(2), { repeats: new Map([["m", "r"]]) }).conversation.map((m) => m.id)).toEqual(["m:input", "m:final"]);
  });

  it("orders the answers to one message by when each came", () => {
    const fast = [...turn, { id: "p:input", runId: "p", role: "user", kind: "prompt", content: "Which plan?", author: person, ts: "2026-11-08T10:00:02Z" },
      { id: "p:final", runId: "p", role: "assistant", kind: "final", content: "Pollux first.", author: pollux, ts: "2026-11-08T10:00:10Z" }] as ChatMessage[];
    const { conversation } = conversationPresentation(fast, { repeats: new Map([["m", "r"], ["p", "r"]]) });
    expect(conversation.map((m) => m.id)).toEqual(["r:input", "p:final", "r:final", "m:final"]);
    // An answer without a time leaves the order as listed.
    const untimed = fast.map((m) => (m.id === "r:final" ? { ...m, ts: undefined } : m));
    expect(conversationPresentation(untimed, { repeats: new Map([["m", "r"], ["p", "r"]]) }).conversation.map((m) => m.id)).toEqual(["r:input", "r:final", "m:final", "p:final"]);
  });

  it("names a live reply by its frames' author; authored messages and unnamed runs are left alone", () => {
    const { conversation } = conversationPresentation([
      { id: "live:r:c1", runId: "r", role: "assistant", content: "Writ", live: { callId: "c1", reasoning: "" } },
      { id: "live:other:c2", runId: "other", role: "assistant", content: "sub", live: { callId: "c2", reasoning: "" } },
      { id: "old:final", runId: "old", role: "assistant", content: "Before", author: null },
    ], { liveAuthors: new Map([["r", agent], ["old", castor]]) });
    expect(conversation.map((m) => m.author)).toEqual([agent, undefined, null]);
  });

  it("an entity answer without a name is never titled 'Assistant' (review 2026-11-09 N7); an agent's still is", () => {
    const { conversation } = conversationPresentation([
      { id: "m:final", runId: "m", role: "assistant", content: "Hi", author: { ...castor, name: null } },
      { id: "a:final", runId: "a", role: "assistant", content: "Done", author: { kind: "agent", name: null, entity_id: null, identity_ref: null, avatar: null } },
    ]);
    expect(conversation.map((m) => m.title)).toEqual([undefined, "Assistant"]);
  });

  it("an older gateway (no author anywhere) keeps today's 'Assistant' header", () => {
    const { conversation } = conversationPresentation([
      { id: "live:r:c1", runId: "r", role: "assistant", content: "Writ", live: { callId: "c1", reasoning: "" } },
      { id: "r:final", runId: "r", role: "assistant", content: "Done" },
    ], { liveAuthors: new Map([["r", null]]) });
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
