/**
 * Voice in the browser, on the gateway's engines (no local model):
 * - read aloud: `POST runs/{id}/voice/tts/stream` (JSON Lines; `audio` lines
 *   carry a WAV in `audio_b64`, the terminal line is `done`, `cancelled` or
 *   `error`; a first `queued` line says the engine is busy — api.md
 *   "Optional multimodal scope"), played in order through Web Audio;
 * - dictation: MediaRecorder -> `attachments/upload` -> `runs/{owner}/audio/transcribe`
 *   (the iPhone's path, GatewayClient.swift transcribe). The gateway's STT
 *   contract lists audio/webm, audio/mp4 and audio/ogg among its accepted
 *   types (discovery capabilities, contracts.assistant.voice.stt.content_types).
 * Both are frontend code on purpose: a Tauri WebView has the same APIs.
 */

export type TtsLine = Record<string, unknown>;

/** What one JSON Lines event means for playback. Unknown types are skipped (engine events). */
export function interpretTtsLine(line: TtsLine):
  | { kind: "audio"; wav_b64: string; sequence: number | null }
  | { kind: "queued"; message: string }
  | { kind: "done" }
  | { kind: "cancelled" }
  | { kind: "error"; message: string }
  | { kind: "other" } {
  const type = String(line.type || "");
  if (type === "audio") {
    const b64 = typeof line.audio_b64 === "string" ? line.audio_b64 : "";
    if (!b64) return { kind: "error", message: "The voice engine sent an audio line without audio." };
    return { kind: "audio", wav_b64: b64, sequence: typeof line.sequence === "number" ? line.sequence : null };
  }
  if (type === "queued") return { kind: "queued", message: String(line.message || "Waiting for the voice engine…") };
  if (type === "done") return { kind: "done" };
  if (type === "cancelled") return { kind: "cancelled" };
  if (type === "error") return { kind: "error", message: String(line.error || "Read aloud failed.") };
  return { kind: "other" };
}

export function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Plays WAV chunks back to back, in arrival order (sequence is the gateway's order). */
export class ChunkPlayer {
  private ctx: AudioContext;
  private at = 0;
  private sources: AudioBufferSourceNode[] = [];
  constructor() {
    const C = (globalThis as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext }).AudioContext
      ?? (globalThis as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!C) throw new Error("This browser has no Web Audio: read aloud is unavailable.");
    this.ctx = new C();
  }
  async enqueue(wav: Uint8Array): Promise<void> {
    const buf = await this.ctx.decodeAudioData(wav.buffer.slice(wav.byteOffset, wav.byteOffset + wav.byteLength) as ArrayBuffer);
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.ctx.destination);
    const start = Math.max(this.ctx.currentTime + 0.02, this.at);
    src.start(start);
    this.at = start + buf.duration;
    this.sources.push(src);
  }
  /** Resolves when everything queued so far has played. */
  drained(): Promise<void> {
    const ms = Math.max(0, (this.at - this.ctx.currentTime) * 1000);
    return new Promise((r) => setTimeout(r, ms));
  }
  stop(): void {
    for (const s of this.sources) {
      try {
        s.stop();
      } catch {
        /* already stopped */
      }
    }
    this.sources = [];
    void this.ctx.close();
  }
}

/** The recording type this browser can make that the gateway STT accepts. */
export function pickRecordingType(isSupported: (t: string) => boolean): string {
  for (const t of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]) {
    if (isSupported(t)) return t;
  }
  throw new Error("This browser records no audio format the gateway accepts (webm, mp4 or ogg).");
}

export function extensionFor(mime: string): string {
  if (mime.startsWith("audio/webm")) return "webm";
  if (mime.startsWith("audio/mp4")) return "m4a";
  if (mime.startsWith("audio/ogg")) return "ogg";
  throw new Error(`No file extension for ${mime}`);
}

/** One push-to-talk recording. `stop()` resolves with the audio. */
export async function startRecording(): Promise<{ stop: () => Promise<{ blob: Blob; type: string }>; cancel: () => void }> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const type = pickRecordingType((t) => MediaRecorder.isTypeSupported(t));
  const rec = new MediaRecorder(stream, { mimeType: type });
  const parts: Blob[] = [];
  rec.ondataavailable = (e) => {
    if (e.data.size) parts.push(e.data);
  };
  rec.start();
  const release = () => stream.getTracks().forEach((t) => t.stop());
  return {
    stop: () =>
      new Promise((resolve, reject) => {
        rec.onstop = () => {
          release();
          const blob = new Blob(parts, { type: type.split(";")[0] });
          if (!blob.size) reject(new Error("Nothing was recorded."));
          else resolve({ blob, type: type.split(";")[0] });
        };
        rec.stop();
      }),
    cancel: () => {
      rec.onstop = release;
      rec.stop();
    },
  };
}
