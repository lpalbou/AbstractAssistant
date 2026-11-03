import React from "react";
import { type ChatMessage, type ChatMessageCardProps } from "./chat_message_card.js";
import type { WorkflowConnection } from "./workflow_runtime.js";
import { type AvatarConversationState, type ConversationAttention, type ConversationCue, type ConversationCuePreferences } from "./conversation_model.js";
export type AvatarConversationOptions = {
    /** Stable conversation identity, not the identity of each individual turn. */
    sessionKey: string;
    /** Host renders its own avatar, animation and accessible name. */
    avatar: React.ReactNode;
    status?: AvatarConversationState;
    listening?: boolean;
    speaking?: boolean;
    connection?: WorkflowConnection;
    /** Snapshot/history reconstruction is a silent baseline, even if the stream is connected. */
    replaying?: boolean;
    attention?: ConversationAttention | null;
    /** Cue channels per attention kind; both on by default. Hosts edit them in their settings, never inside this view. */
    preferences?: ConversationCuePreferences;
    onPreferencesChange?: (preferences: ConversationCuePreferences) => void;
    /** Foreground fresh-revision cues only. The host owns sounds/haptics. */
    onCue?: (cue: ConversationCue) => void;
    /** Explicit opt-in; the host owns its existing speech stack and handles errors. */
    narrate?: boolean;
    onNarrate?: (message: ChatMessage) => void;
    /** Called before voice, reply, reading a held line or the findings, or session reset. */
    onInterruptSpeech?: () => void;
    onReplyContext?: (message: ChatMessage | null) => void;
    /** Hosts use this to suppress their existing automatic final speech while the person reads or replies. */
    onAttendedChange?: (attended: boolean) => void;
    voiceControl?: React.ReactNode;
    /** Playback actions do not trigger the microphone interruption hook. */
    playbackControl?: React.ReactNode;
    /** Open the host's detailed conversation; does not answer a pending request. */
    onTechnicalView?: () => void;
};
export type AvatarConversationProps = AvatarConversationOptions & {
    messages: ChatMessage[];
    /** Existing authoritative question or approval controls, supplied by the host. */
    interaction?: React.ReactNode;
    /** Exact currently rendered request; an empty ID means the host deferred it. */
    interactionId?: string;
    /** Draft editing or other host-owned attention: silences narration and non-essential cues. The live line keeps updating. */
    attended?: boolean;
    /** Shared message rendering (live line, answer, findings), with private reasoning removed before presentation. */
    messageProps?: Omit<ChatMessageCardProps, "message">;
};
/**
 * Optional public presentation: the avatar, its status, ONE live line (the latest public update,
 * replaced as new ones arrive), any open question or approval pinned above it, the turn's answer
 * shown once as a message, and the findings the actor reported so far beside the avatar (a sheet
 * the person opens on a narrow screen). No model, microphone, network or permission side effects.
 */
export declare function AvatarConversation(props: AvatarConversationProps): React.ReactElement;
//# sourceMappingURL=avatar_conversation.d.ts.map