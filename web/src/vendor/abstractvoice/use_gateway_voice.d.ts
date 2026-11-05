export type TtsPlaybackStatus = "idle" | "loading" | "playing" | "paused";
export type GatewayVoiceOptions = {
    /**
     * Speaker to play on (a `MediaDeviceInfo.deviceId` of kind "audiooutput";
     * "" = the system default). Applied with `AudioContext.setSinkId` where the
     * browser supports it (`audioOutputSelectable()`); ignored elsewhere.
     */
    output_device_id?: string;
    /** Reply volume 0..1 (absent = 1), applied to every spoken reply. */
    volume?: number;
    /**
     * Replies muted (the `reply_muted` preference): playback gain 0, the volume kept for when the
     * mute is lifted. Applied at once, also to a reply that is playing.
     */
    muted?: boolean;
    /**
     * Microphone to record from (a `MediaDeviceInfo.deviceId` of kind
     * "audioinput"; "" = the system default). A saved device that is gone fails
     * with a sentence — the hook never records from another microphone silently.
     */
    input_device_id?: string;
    /** Input gain applied to recordings (1 = unchanged; needs Web Audio). */
    input_gain?: number;
    /**
     * Stop recording on any pointer release in the window (default true: the
     * hold-to-talk shape). A host with tap-to-start/tap-to-stop sets false and
     * stops recording itself.
     */
    stop_on_pointerup?: boolean;
    /**
     * How the microphone button records (the `capture_mode` preference): "hold" (default) = hold to
     * talk, a release anywhere stops; "toggle" = tap to start, tap again to stop (no pointerup
     * stop). An explicit `stop_on_pointerup` wins. `AfVoiceMicButton` refuses a different mode.
     */
    capture_mode?: VoiceCaptureMode;
    /** Synthesize text to audio bytes (absent = TTS unsupported). */
    tts?: (text: string) => Promise<ArrayBuffer>;
    /**
     * Streaming synthesis (operator item 3, 2026-07-13): yields decodable audio
     * segments (each a complete WAV — the gateway's tts/stream JSONL events
     * carry standalone wav-segments) as synthesis progresses. When present it
     * is PREFERRED over `tts`: long messages start speaking on the first
     * segment instead of waiting for full synthesis. `streamTtsJsonl` is the
     * ready-made transport for the gateway endpoint.
     */
    tts_stream?: (text: string, signal?: AbortSignal) => AsyncIterable<ArrayBuffer>;
    /**
     * The voice `tts` / `tts_stream` speak with: the request's speech fields (`voiceTtsRequest(prefs)`:
     * provider, model, voice, profile, speed, ...; `gatewayVoiceOptions(prefs)` passes it). The audio
     * the hook keeps for a message (to resume a paused one) is tied to (message, text, this voice):
     * after a voice change the message is spoken again in the new voice, never resumed in the old one
     * (operator, 2026-10-29). Absent: kept audio is never reused (a paused message starts over).
     */
    tts_voice?: Record<string, unknown> | string | null;
    /**
     * Transcribe a recorded blob (absent = PTT unsupported). Returns the text,
     * or the text with the route that ran (shown beside the transcript).
     */
    transcribe?: (blob: Blob, mime: string) => Promise<string | VoiceTranscription>;
    on_error?: (message: string) => void;
    on_transcript?: (text: string, info?: VoiceTranscription) => void;
};
/** The microphone button's way of recording: hold to talk, or tap to talk (tap again to stop). */
export type VoiceCaptureMode = "hold" | "toggle";
/**
 * The ONE reading of a capture mode (a stored preference, a prop, the preferences object):
 * "toggle" only when it is exactly "toggle", "hold" for anything else (absent, stale, foreign,
 * corrupt). The hook, `gatewayVoiceOptions` and `AfVoiceMicButton` all read it this way, so a
 * stored value can never make them disagree.
 */
export declare function voiceCaptureMode(value: unknown): VoiceCaptureMode;
/**
 * A stable key for a TTS voice (`GatewayVoiceOptions.tts_voice`): the same fields in any order give
 * the same key; absent gives "" (no voice known).
 */
export declare function ttsVoiceKey(voice: GatewayVoiceOptions["tts_voice"]): string;
/** A transcription result with the route that ran (`provider`/`model` from the gateway response). */
export type VoiceTranscription = {
    text: string;
    provider?: string | null;
    model?: string | null;
};
/**
 * Transport helper for the gateway streaming TTS endpoint
 * (`POST /api/gateway/runs/{run_id}/voice/tts/stream`, JSON-Lines): parses
 * events, decodes `audio_b64` wav-segments, ends on the terminal
 * done/cancelled event, throws on error events. Aborts the HTTP request when
 * the consumer stops iterating (pause keeps the stream; stop kills it).
 */
export declare function streamTtsJsonl(opts: {
    path: string;
    body: Record<string, unknown>;
    /** CSRF twin for the app-origin proxy (mutating POST). */
    csrfToken?: string;
    /** Extra headers — the direct-bearer posture passes Authorization here (entity c1242). */
    headers?: Record<string, string>;
    /** Abort immediately on stop or owner changes, even before the first segment. */
    signal?: AbortSignal;
}): AsyncGenerator<ArrayBuffer>;
export type GatewayVoice = {
    tts_supported: boolean;
    /** Audio is scheduled on a running context with nonzero output gain (false while buffering). */
    tts_speaking: boolean;
    tts_playback: {
        key: string;
        status: TtsPlaybackStatus;
    };
    toggle_tts: (msg_key: string, text: string) => Promise<void>;
    stop_tts: () => void;
    voice_ptt_supported: boolean;
    voice_ptt_recording: boolean;
    voice_ptt_busy: boolean;
    start_voice_ptt_recording: () => Promise<void>;
    stop_voice_ptt_recording: () => void;
    /** Discard recording / pending permission / transcription on owner changes. */
    cancel_voice_ptt_recording?: () => void;
    /** When the current recording or transcription began (ms epoch; 0 = idle) — for "Transcribing… 12 s". */
    voice_ptt_since: number;
    /**
     * Hear the live microphone level 0..1 while recording (0 otherwise; called at once with the
     * current level, then on each 5 % step). A subscription, not state: only the meter that
     * subscribes re-renders (`useVoiceLevel`, `AfVoiceLevelMeter`), never the hook's owner.
     * Returns the unsubscribe function. Stable identity.
     */
    subscribe_level?: (fn: (level: number) => void) => () => void;
    /** Measured reply output after volume/mute, 0 while paused, stopped or starved.
     * Stable subscription; no microphone access and no owner re-renders per sample. */
    subscribe_playback_level?: (fn: (level: number) => void) => () => void;
    /** The capture mode this hook was created with ("hold" unless `capture_mode: "toggle"`). */
    voice_capture_mode?: VoiceCaptureMode;
    /**
     * Hear every transcript this hook delivers (besides `on_transcript`); returns the unsubscribe
     * function. Stable identity. `AfVoiceMicButton`'s `onTranscript` uses it.
     */
    add_transcript_listener?: (fn: (text: string, info?: VoiceTranscription) => void) => () => void;
};
/**
 * The words of a failed TTS answer: `detail` as a string, or a typed answer's `detail.message`
 * (`{reason_code, message, ...}`), never "[object Object]"; `HTTP <status>` when there is neither.
 */
export declare function ttsErrorDetail(data: unknown, status: number): string;
/** "Prefix: detail." — every voice failure reaches the user as one sentence. */
export declare function voiceErrorSentence(prefix: string, e: unknown): string;
/** A recording shorter than this carries no speech: say so instead of sending it. */
export declare const MIN_RECORDING_MS = 350;
/** The browser can route Web Audio to a chosen speaker (`AudioContext.setSinkId`). */
export declare function audioOutputSelectable(): boolean;
export declare function useGatewayVoice(opts: GatewayVoiceOptions): GatewayVoice;
export default useGatewayVoice;
//# sourceMappingURL=use_gateway_voice.d.ts.map