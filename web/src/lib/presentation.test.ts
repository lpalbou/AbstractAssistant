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
    expect(parseAssistantPreferences("{broken")).toEqual({ design: "halo", animated: true });
    expect(parseAssistantPreferences('{"design":"../../file","animated":"false"}')).toEqual({ design: "halo", animated: true });
    expect(parseAssistantPreferences('{"design":"vortex","animated":false}')).toEqual({ design: "vortex", animated: false });
  });
});
