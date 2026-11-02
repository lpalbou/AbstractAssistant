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
/** The plain label a person sees for a public message in the Avatar view's history. */
export declare function conversationLabel(m: ChatMessage): "You" | "Update" | "Question" | "Answer";
/** Quote only an explicitly selected public update from the current live run. */
export declare function conversationReply(text: string, context: ChatMessage | null, currentRunId: string, allowedSourceRunIds?: readonly string[]): string;
/** One rolling caption: a public message of the current turn, ready for the shared message renderer. */
export type ConversationCaption = {
    /** Stable across renders and appends (run + public id), so a caption never re-enters. */
    key: string;
    kind: "update" | "question" | "outcome" | "answer";
    message: ChatMessage;
};
/**
 * The rolling captions: what the assistant has said publicly in the CURRENT turn (after the
 * person's latest message; accepted mid-run guidance does not start a new turn), oldest first,
 * the newest last. Pure and time-free: the same messages always give the same captions, so
 * nothing cycles; a new public message is appended and earlier captions keep their keys. The
 * final answer is one caption, never split. At most `limit` captions (older ones have scrolled
 * out of the caption area; the full history stays in the conversation).
 */
export declare function conversationCaptions(messages: readonly ChatMessage[], limit?: number): ConversationCaption[];
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