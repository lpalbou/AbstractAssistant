import { describe, expect, it } from "vitest";

import { base64ToBytes, extensionFor, interpretTtsLine, pickRecordingType } from "./voice";

describe("read aloud stream lines (api.md voice/tts/stream)", () => {
  it("maps each line type", () => {
    expect(interpretTtsLine({ type: "runtime_start", run_id: "r", child_run_id: "c" })).toEqual({ kind: "other" });
    expect(interpretTtsLine({ type: "queued", message: "Waiting for the voice engine: busy" })).toEqual({ kind: "queued", message: "Waiting for the voice engine: busy" });
    expect(interpretTtsLine({ type: "audio", sequence: 0, audio_b64: "UklGRg==" })).toEqual({ kind: "audio", wav_b64: "UklGRg==", sequence: 0 });
    expect(interpretTtsLine({ type: "audio" }).kind).toBe("error");
    expect(interpretTtsLine({ type: "done", audio_artifact: {} })).toEqual({ kind: "done" });
    expect(interpretTtsLine({ type: "error", error: "engine gone" })).toEqual({ kind: "error", message: "engine gone" });
  });
  it("decodes base64 audio", () => {
    expect(Array.from(base64ToBytes("UklGRg=="))).toEqual([82, 73, 70, 70]);
  });
});

describe("dictation format", () => {
  it("prefers webm/opus, then mp4 (Safari), and refuses when nothing the gateway accepts records", () => {
    expect(pickRecordingType(() => true)).toBe("audio/webm;codecs=opus");
    expect(pickRecordingType((t) => t === "audio/mp4")).toBe("audio/mp4");
    expect(() => pickRecordingType(() => false)).toThrow(/no audio format/);
    expect(extensionFor("audio/mp4")).toBe("m4a");
  });
});
