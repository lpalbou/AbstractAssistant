import type { ChatMessage } from "./chat_message_card.js";
import type { WorkflowConnection, WorkflowSessionSnapshot } from "./workflow_runtime.js";
import type { WorkflowToolActivity } from "./workflow_evidence.js";
/** Explicit actor-authored public text; never derived from tool output or reasoning. */
export type PublicUpdate = {
    id: string;
    text: string;
    runId: string;
    sessionId?: string;
    iteration?: number;
    sourceCallIds: string[];
    /** Typed by the actor: "finding" for a fact or piece of evidence it established, "progress" for what it is doing. */
    kind: "progress" | "finding";
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
/** Validate the durable public channel at the presentation boundary, preserving exact text.
 * `kind` is the actor's own type (event `kind`, replay `update_kind`); anything but "finding" is progress. */
export declare function publicUpdate(value: unknown, runId: string): PublicUpdate | null;
/** Public history contains user input and durable replies, never arbitrary assistant/system rows. */
export declare function conversationMessages(messages: readonly ChatMessage[]): ChatMessage[];
/** Quote only an explicitly selected public update from the current live run. */
export declare function conversationReply(text: string, context: ChatMessage | null, currentRunId: string, allowedSourceRunIds?: readonly string[]): string;
/** What the Avatar view shows for the current turn (after the person's latest message; accepted mid-run guidance does not start a turn). */
export type ConversationLive = {
    /** The latest public update, question or question outcome, replaced as new ones arrive; null once an answer came after it. */
    line: ChatMessage | null;
    /** The turn's answer messages (its text, files), each shown once as a message. */
    answers: ChatMessage[];
    /** Identity of the person's latest message (guidance included): a new one ends a reply to an earlier line. */
    personKey: string;
};
/**
 * The live line and the answer messages. Pure and time-free: the same messages always give the same
 * result. With `pinnedRequest`, questions are left out: the open question is shown once, pinned
 * above the line with its answer controls.
 */
export declare function conversationLive(messages: readonly ChatMessage[], options?: {
    pinnedRequest?: boolean;
}): ConversationLive;
/** A finding the actor reported, with the results it cited that this conversation holds. */
export type ConversationFinding = {
    key: string;
    message: ChatMessage;
    /** The cited tool calls (`source_call_ids`) found among the messages, in citation order. */
    sources: WorkflowToolActivity[];
};
/**
 * Every finding of the conversation, across its runs, the newest last. Only updates the actor
 * typed `kind: "finding"` are findings; nothing is inferred from their text.
 */
export declare function conversationFindings(messages: readonly ChatMessage[]): ConversationFinding[];
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