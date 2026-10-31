import { type VoiceClientPreferences, type VoiceDefaults } from "@abstractframework/ui-kit";
import { type GatewayFetch } from "./workspace_browser.js";
import type { ChatMessage, SpeakState } from "./chat_message_card.js";
export declare function docsVoiceAvailable(defaults: VoiceDefaults | null, preferences?: VoiceClientPreferences): boolean;
export declare function docsSpeech(fetchGateway: GatewayFetch, message: Pick<ChatMessage, "runId" | "content">, preferences: VoiceClientPreferences, signal?: AbortSignal): Promise<ArrayBuffer>;
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
};
//# sourceMappingURL=docs_voice.d.ts.map