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
    preferences?: ConversationCuePreferences;
    onPreferencesChange?: (preferences: ConversationCuePreferences) => void;
    /** Foreground fresh-revision cues only. The host owns sounds/haptics. */
    onCue?: (cue: ConversationCue) => void;
    /** Explicit opt-in; the host owns its existing speech stack and handles errors. */
    narrate?: boolean;
    onNarrate?: (message: ChatMessage) => void;
    /** Called before voice, reply, reading history, or session reset. */
    onInterruptSpeech?: () => void;
    onReplyContext?: (message: ChatMessage | null) => void;
    /** Hosts use this to suppress their existing automatic final speech while the person reads or replies. */
    onAttendedChange?: (attended: boolean) => void;
    voiceControl?: React.ReactNode;
    /** Playback actions do not trigger the microphone interruption hook. */
    playbackControl?: React.ReactNode;
};
export type AvatarConversationProps = AvatarConversationOptions & {
    messages: ChatMessage[];
    /** Existing authoritative question or approval controls, supplied by the host. */
    interaction?: React.ReactNode;
    /** Draft editing or other host-owned attention freezes rolling captions. */
    attended?: boolean;
    /** Shared final/attachment rendering, with private reasoning removed before presentation. */
    messageProps?: Omit<ChatMessageCardProps, "message">;
};
/** Optional public presentation. No model, microphone, network or permission side effects. */
export declare function AvatarConversation(props: AvatarConversationProps): React.ReactElement;
//# sourceMappingURL=avatar_conversation.d.ts.map