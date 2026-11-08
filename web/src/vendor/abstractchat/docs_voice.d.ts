import { type VoiceClientPreferences, type VoiceDefaults } from "@abstractframework/ui-kit";
import { type GatewayFetch } from "./workspace_browser.js";
import type { ChatMessage, SpeakState } from "./chat_message_card.js";
/** Why the browser withholds the microphone (plain http from another machine), or null. */
export declare function microphoneUnavailableReason(): string | null;
export declare function docsVoiceAvailable(defaults: VoiceDefaults | null, preferences?: VoiceClientPreferences): boolean;
export declare function docsSpeech(fetchGateway: GatewayFetch, message: Pick<ChatMessage, "runId" | "content">, preferences: VoiceClientPreferences, signal?: AbortSignal): Promise<ArrayBuffer>;
/**
 * The voice options the Docs assistant runs with: the person's devices, volume and voice, but it
 * never reads by itself, so it keeps no player open for Read aloud (the host's own hook does; a
 * page keeps one such player).
 */
export declare function docsVoiceOptions(preferences: VoiceClientPreferences): {
    unlock_on_gesture: boolean;
    muted?: boolean | undefined;
    output_device_id?: string | undefined;
    volume?: number | undefined;
    input_device_id?: string | undefined;
    input_gain?: number | undefined;
    capture_mode?: import("@abstractframework/ui-kit").VoiceCaptureMode | undefined;
    tts_voice?: (Record<string, unknown> | string | null) | undefined;
};
export declare function useDocsVoice(props: {
    fetchGateway: GatewayFetch;
    connected: boolean;
    visible: boolean;
    scope: string;
    preferences?: VoiceClientPreferences;
    onError: (message: string) => void;
}): {
    onSpeakToggle: ((message: ChatMessage) => void) | undefined;
    getSpeakState: (message: ChatMessage) => SpeakState;
    stop: () => void;
    voice: import("@abstractframework/ui-kit").GatewayVoice;
    dictationAvailable: boolean;
    captureMode: import("@abstractframework/ui-kit").VoiceCaptureMode;
    routeText: string;
    microphoneReason: string | null;
};
//# sourceMappingURL=docs_voice.d.ts.map