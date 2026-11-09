import type { AfGatewayFetch } from "@abstractframework/ui-kit";
import React from "react";
import { type ComposerAttachment } from "./attachment_uploads.js";
import type { ChatMessage, ChatMessageCardProps } from "./chat_message_card.js";
import { type WorkflowInteraction } from "./workflow_interaction.js";
import type { StreamRepliesMode } from "./llm_delta.js";
import { type AvatarConversationOptions } from "./avatar_conversation.js";
import { type ChatMentionCandidate, type ChatMentionSent } from "./mentions.js";
/** What the host's steer door answered (`POST commands {type:"inject_guidance"}`
 * answers `{accepted, duplicate, seq}`; ui-kit `SteerSubmitResult` fits). */
export type ChatSteerResult = {
    accepted: boolean;
    seq?: number;
    duplicate?: boolean;
};
/** "guide": steer the live run (inject_guidance). "queue": hold the message for the next turn. */
export type ChatSteerMode = "guide" | "queue";
export type ChatSteer = {
    /**
     * Called instead of `onSend` while `busy`. The host posts it (ui-kit
     * `submitSteer` posts `inject_guidance` through the app-origin proxy) or
     * queues it for the next turn. The chat never fetches.
     */
    onSteer: (text: string, mode: ChatSteerMode, ctx?: {
        mentions: ChatMentionSent[];
    }) => Promise<ChatSteerResult>;
    /** Default `["guide"]`. With both, the busy composer offers a mode switch. */
    modes?: ChatSteerMode[];
    /** The run is parked on a wait: guidance delivers at its next wake (steers do not wake runs). */
    parked?: boolean;
};
export type ChatToolbar = {
    onNewSession?: () => void | Promise<unknown>;
    onClear?: () => void | Promise<unknown>;
    /** Download the transcript as Markdown (`chatToMarkdown`). */
    exportTranscript?: {
        filename: string;
        heading?: string;
    } | false;
    /** Copy the transcript as Markdown. */
    copyTranscript?: boolean;
};
export type WorkflowChatProps = {
    /** Optional second presentation; the existing controlled composer and actions stay mounted. */
    avatarConversation?: AvatarConversationOptions;
    /** Fully controlled transcript. The host owns message persistence and identity. */
    messages: ChatMessage[];
    /** Authenticated app-origin artifact reads, never model-provided URLs. */
    artifactFetch?: AfGatewayFetch;
    attachmentScope?: string;
    attachmentRun?: {
        runId: string;
        output: unknown;
    };
    /** Fully controlled composer value. It is intentionally retained on failed sends. */
    draft: string;
    onDraftChange: (draft: string) => void;
    /**
     * Submit a chat message. Async failures are surfaced locally and keep the
     * draft. `signal` is aborted when the user presses Stop during this send
     * (or the chat unmounts): a request/response host ties its fetch to it.
     * `mentions`: the names picked with `@` (`mentionCandidates`), in order,
     * `index` = the gateway's `mention_index`; empty without a pick (and while
     * `mentionsUnavailable`). The chips of this send clear once it resolves and
     * stay when it fails, like the draft; chips picked while it is in flight
     * always stay. A send whose mentions stopped partway names the chips to keep
     * as `unsentMentions` on what it resolves or rejects with
     * (`mentionsStoppedError`): only those stay, for the resend.
     */
    onSend: (draft: string, ctx: {
        signal: AbortSignal;
        mentions: ChatMentionSent[];
    }) => void | Promise<unknown>;
    /**
     * `@` mentions in the composer: the names to offer for the query typed after
     * `@` (the host decides the source, e.g. `GET /entities`). Absent: no list,
     * no chips. See `ChatComposer`.
     */
    mentionCandidates?: (query: string) => Promise<ChatMentionCandidate[]>;
    /** The sentence under a chip on the first pick of its name in this conversation. */
    mentionNotice?: (candidate: ChatMentionCandidate) => string | null | undefined;
    /** The conversation "the first pick" counts in (e.g. the session id). */
    mentionSessionKey?: string;
    /** The host's sentence when mentions cannot be used (e.g. "This gateway does not offer
     * mentions yet"): `@` shows it instead of names. See `ChatComposer`. */
    mentionsUnavailable?: string | null;
    /** A sentence about the last mentions sent (e.g. "Castor is in another conversation."). */
    mentionStatus?: string | null;
    busy?: boolean;
    /**
     * The assistant is working on a reply (the host's run state, e.g. `workflowProgress(...).tone
     * === "working"`): three rising dots (`WorkingDots`) sit at the transcript's tail, where the
     * reply will appear. Not shown while an interaction waits on the person, nor in the Avatar view.
     */
    working?: boolean;
    /** Accessible name of the working dots. Default "Working". */
    workingLabel?: string;
    /** Keep the composer active while busy, for hosts that queue/steer messages. */
    sendWhileBusy?: boolean;
    sendLabel?: string;
    /** Optional host-specific explanation while the composer is busy. */
    busyLabel?: string;
    /**
     * Cancels current host work. Only rendered while busy. Stop first aborts
     * the in-flight send's signal (the one `onSend` received), then calls this
     * with that signal; when no send is in flight here (a ledger host whose run
     * outlives `onSend`) the signal is a fresh one, aborted at the same moment.
     */
    onCancel?: (signal: AbortSignal) => void | Promise<unknown>;
    /**
     * Ledger-derived Stop state (`WorkflowSessionSnapshot.stop`). While busy the
     * Stop button reads "Stopping…" for `stopping`. Once the host is no longer
     * busy the composer is back to idle (Send, the host's trailing actions,
     * nothing else): the outcome ("Stopped", or the gateway's forced-stop text)
     * belongs to the host's run status (`workflowProgress`), never the composer.
     */
    stopState?: {
        phase: "stopping" | "stopped" | "forced";
        label: string;
    } | null;
    /** Read-only/observer mode. It disables all actions without hiding context. */
    disabled?: boolean;
    blockedNotice?: React.ReactNode;
    emptyState?: React.ReactNode;
    header?: React.ReactNode;
    footer?: React.ReactNode;
    composerExtras?: React.ReactNode;
    /** Host controls beside Send (e.g. voice); left-side controls stay in composerExtras. */
    composerTrailingActions?: React.ReactNode;
    /** Rounded multiline by default; `legacy` opts into the former layout. */
    composerVariant?: import("./chat_composer.js").ChatComposerVariant;
    /** Optional host-owned attachment picker/action. */
    onAttach?: () => void | Promise<unknown>;
    /**
     * Receives files dropped on the chat (transcript or composer) or pasted into
     * the message field. Setting it turns on the drop zone and paste-to-attach;
     * size policy, upload and chips stay with the host. Folders are refused
     * here with a visible message and never reach the host.
     */
    onFiles?: (files: File[]) => void | Promise<unknown>;
    /** Host-rendered attachment chips, shown inside the composer above the
     * message field. Escape hatch: prefer `attachmentItems`. */
    attachments?: React.ReactNode;
    /**
     * Typed attachment chips (`useAttachmentUploads().items`). While one is
     * queued/uploading/refused/failed, Send refuses with the reason in words
     * (a visible chip is never left behind silently by a send).
     */
    attachmentItems?: ComposerAttachment[];
    /** Required with `attachmentItems`: a refused/failed chip blocks Send until it is removed. */
    onRemoveAttachment?: (id: string) => void;
    onRetryAttachment?: (id: string) => void;
    /** Steer/queue while busy: the send button becomes "Steer"/"Queue". */
    steer?: ChatSteer;
    /** Standard transcript actions in the header row; each only when injected. */
    toolbar?: ChatToolbar;
    /** A pending workflow wait rendered after the transcript. */
    interaction?: WorkflowInteraction | null;
    /** Optional host sanitizer/renderer for every transcript message. */
    renderMarkdown?: (markdown: string) => React.ReactElement;
    placeholder?: string;
    className?: string;
    messageProps?: Omit<ChatMessageCardProps, "message">;
    /**
     * The host's "Stream replies" choice. The widget does not start runs: the
     * host maps it into the start-run input with `streamRepliesRuntime(mode)`
     * — `"on"` → `_runtime.stream: true`, `"off"` → `_runtime.stream: false`,
     * `"gateway_default"` (or omitted) → `_runtime.stream` left unset so the
     * gateway's `agents.streaming_default` decides. Live replies arrive through
     * the transport's `onDelta`; messages carrying `live` render as a streaming
     * bubble whatever this value is. Exposed on the root as `data-stream-replies`.
     */
    streamReplies?: StreamRepliesMode;
};
/**
 * Controlled chat presentation for workflow hosts. Optional artifactFetch supplies
 * authenticated attachment reads; run execution, persistence and approvals stay
 * with the embedding host and controller.
 */
export declare function WorkflowChat(props: WorkflowChatProps): React.ReactElement;
export default WorkflowChat;
//# sourceMappingURL=workflow_chat.d.ts.map