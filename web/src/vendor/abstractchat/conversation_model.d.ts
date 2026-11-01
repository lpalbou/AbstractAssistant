import type { ChatMessage } from "./chat_message_card.js";
import type { WorkflowConnection, WorkflowSessionSnapshot } from "./workflow_runtime.js";
/** Explicit actor-authored public text; never derived from tool output or reasoning. */
export type PublicUpdate = {
    id: string;
    text: string;
    runId: string;
    sessionId?: string;
    iteration?: number;
    sourceCallIds: string[];
};
export type AvatarConversationState = "idle" | "working" | "paused" | "listening" | "speaking" | "question" | "approval" | "completed" | "failed" | "connecting" | "disconnected";
export type ConversationAttention = {
    id: string;
    kind: "approval" | "question" | "completion";
    importance?: "essential" | "clarification";
    deadline?: string;
    fallback?: string;
};
export type ConversationCuePreferences = Record<ConversationAttention["kind"], {
    visual: boolean;
    audio: boolean;
    haptic?: boolean;
}>;
export type ConversationCue = ConversationAttention & {
    channels: ConversationCuePreferences[ConversationAttention["kind"]];
};
/** The avatar always signals with both a visual and an audio cue; a host's settings can turn one off. */
export declare const DEFAULT_CONVERSATION_CUES: ConversationCuePreferences;
/** Validate the durable public channel at the presentation boundary, preserving exact text. */
export declare function publicUpdate(value: unknown, runId: string): PublicUpdate | null;
/** Public history contains user input and durable replies, never arbitrary assistant/system rows. */
export declare function conversationMessages(messages: readonly ChatMessage[]): ChatMessage[];
/** Quote only an explicitly selected public update from the current live run. */
export declare function conversationReply(text: string, context: ChatMessage | null, currentRunId: string, allowedSourceRunIds?: readonly string[]): string;
/** Subtitle pages preserve words and punctuation; full text remains in history. */
export declare function conversationPages(text: string, max?: number): string[];
export declare function conversationState(input: {
    status?: AvatarConversationState;
    listening?: boolean;
    speaking?: boolean;
    connection?: WorkflowConnection;
    attention?: ConversationAttention | null;
}): AvatarConversationState;
/** Served interaction remains authoritative; this helper changes presentation only. */
export declare function conversationSnapshot(snapshot: WorkflowSessionSnapshot): {
    status: AvatarConversationState;
    connection: WorkflowConnection;
    attention: ConversationAttention | null;
    replaying: boolean;
};
/** First observation, replay, history and reconnect establish a baseline, never a cue. */
export type ConversationCueCursor = {
    sessionKey: string;
    connected: boolean;
    seen: string[];
};
export declare function conversationCueStep(previous: ConversationCueCursor | null, input: {
    sessionKey: string;
    connected: boolean;
    attended: boolean;
    attention?: ConversationAttention | null;
    preferences: ConversationCuePreferences;
}): {
    cursor: ConversationCueCursor;
    cue: ConversationCue | null;
};
/** Narrate only a newly observed latest public update; never queue missed speech. */
export declare function conversationNarrationStep(previous: ConversationCueCursor | null, input: {
    sessionKey: string;
    connected: boolean;
    attended: boolean;
    enabled: boolean;
    listening?: boolean;
    messages: readonly ChatMessage[];
}): {
    cursor: ConversationCueCursor;
    message: ChatMessage | null;
};
//# sourceMappingURL=conversation_model.d.ts.map