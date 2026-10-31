import { type ConversationCue, type ConversationCuePreferences } from "./conversation_model.js";
type Mode = "chat" | "avatar";
/** Host/user-scoped local preferences; callers must include their owner identity in scope. */
export declare function useAvatarConversationPreferences(scope: string): {
    mode: Mode;
    setMode: (mode: Mode) => void;
    preferences: ConversationCuePreferences;
    setPreferences: (preferences: ConversationCuePreferences) => void;
    error: string | null;
};
/** Optional local earcon. Call only for a fresh onCue and after audio was enabled by a user. */
export declare function playConversationCue(cue: ConversationCue): Promise<void>;
export {};
//# sourceMappingURL=conversation_preferences.d.ts.map