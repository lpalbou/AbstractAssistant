import { type MessageArtifact } from "./message_artifacts.js";
import type { PublicUpdate } from "./conversation_model.js";
import React from "react";
import { type IconName } from "@abstractframework/ui-kit";
import type { MarkdownImages } from "./markdown.js";
import type { WorkflowStatistics, WorkflowToolActivity } from "./workflow_evidence.js";
import { type ChatStat } from "./chat_stats.js";
import { type ChatAuthor } from "./chat_author.js";
import type { ChatNotice } from "./chat_notices.js";
import type { ChatMessageMention } from "./mentions.js";
export type ChatMessageLevel = "info" | "warn" | "error";
export type ChatMessage = {
    id?: string;
    role: string;
    content: string;
    ts?: string;
    title?: string;
    level?: ChatMessageLevel;
    /**
     * e.g. report_bug, report_feature. A `replay_view_v1.messages[]` item's
     * kind (prompt, answer, question, event, ...) maps here unchanged; see the
     * README's "Messages from the replay view" mapping.
     */
    kind?: string;
    /** Original public channel attribution, retained through replay. */
    source?: string;
    /**
     * Who wrote this turn (the gateway's turn `author`: `{kind, name, entity_id, identity_ref,
     * avatar: {style, color}}`). On an assistant-side message the header shows the author's
     * mark (an entity's orb, the agent's mark), its name and a kind tag. Null or absent (an
     * older gateway): the header is today's, `title || "Agent"` and no mark. User messages
     * ignore it.
     */
    author?: ChatAuthor | null;
    publicUpdate?: PublicUpdate;
    toolActivity?: WorkflowToolActivity;
    statistics?: WorkflowStatistics;
    runId?: string;
    /**
     * Present while this assistant reply is still being streamed by the model
     * (see `WorkflowSessionController`). The card shows a streaming indicator,
     * and the model's reasoning in a collapsed "Thinking" block.
     */
    live?: ChatLiveReply;
    /**
     * The model's reasoning for a FINISHED reply, shown collapsed under
     * "Thinking" like a live reply's (hosts that do not stream, e.g. a one-shot
     * generation, still have reasoning to show).
     */
    reasoning?: string;
    /** Generated media shown inline under the message text (images, audio, video). */
    media?: ChatMedia[];
    /** Per-message stat chips (e.g. "1.2s · 24 tok"); a card's `stats` prop wins. */
    stats?: ChatStat[];
    /** Per-message attachment chips (e.g. the files a question carried); a
     * card's `attachments` prop wins. */
    attachments?: ChatAttachment[];
    /**
     * Artifact ids this message carries (`replay_view_v1.messages[].artifact_ids`,
     * or `$artifact` refs a host folded). WorkflowChat presents them as named
     * file chips with its artifactFetch transport; hosts may also supply media.
     */
    artifactIds?: string[];
    /** Unlisted replay refs require explicit output recovery, never raw-ID chips. */
    artifactReferencesUnresolved?: boolean;
    artifactRefs?: MessageArtifact[];
    /**
     * What the reply formed (AbstractRuntime turn notices: a diary entry, a lesson, an interest,
     * a question, a realization), served BESIDE the reply text, never parsed out of it: one badge
     * each under the text (`ChatNoticeBadges`). The replay projection carries a view answer's
     * `notices` here; a host sets it from its own lane (`notices` / `reply_notices`).
     */
    notices?: ChatNotice[];
    /**
     * The mentions the message carries, as its send did ({id, name, kind, index, start}; `avatar`:
     * the chip's look when the host knows it). Each is drawn in the words as the composer's chip,
     * placed by its `start` (the text is never read for "@"); copy and read-aloud keep "@Name".
     */
    mentions?: ChatMessageMention[];
};
/**
 * One generated media item. `src` is supplied by the HOST (typically a
 * `blob:` URL of a gateway artifact it fetched with the session), never
 * parsed out of model text; `href` is the raw file link shown beside it.
 * Music rides on `audio`.
 */
export type ChatMedia = {
    id?: string;
    /**
     * `"file"`: a document (pdf, markdown, code, json, text, or a video/audio/
     * image file named as such) shown in the shared `AfFileViewer`, inline
     * behind an "Open" toggle or in the host's opener (`onOpenMedia`).
     */
    kind: "image" | "audio" | "video" | "file";
    /** Object URL / same-origin path of the bytes. A text file may give `text` instead. */
    src: string;
    /** Accessible name / link text, e.g. "Generated image". */
    label?: string;
    /** Link to the raw file (opens in a new tab). */
    href?: string;
    /** Audio: the speech-to-text transcript, shown as a collapsible caption. */
    transcript?: string;
    /** File: its name (with `contentType`, decides how it is shown). */
    name?: string;
    contentType?: string;
    size?: number;
    /** File, text kinds (markdown/code/json/text): the text the host read. */
    text?: string;
};
/** Streaming state of a live assistant reply. `content` holds the visible text only. */
export type ChatLiveReply = {
    callId: string;
    /** Reasoning text, shown collapsed and never mixed into `content`. */
    reasoning: string;
    /** Who is writing, when it is not the conversation's own agent (e.g. "sub-agent · researcher"). */
    caption?: string;
    /** The indicator's text while the reply is pending. Default "streaming";
     *  a one-shot host says what it waits for (e.g. "generating image"). */
    label?: string;
};
export type ChatAttachment = {
    id?: string;
    label: string;
    target?: string;
    title?: string;
    disabled?: boolean;
    onClick?: () => void;
};
export type { ChatStat } from "./chat_stats.js";
export type ChatMessageCardProps = {
    message: ChatMessage;
    className?: string;
    renderMarkdown?: (markdown: string) => React.ReactElement;
    attachments?: ChatAttachment[];
    stats?: ChatStat[];
    onSpeakToggle?: (message: ChatMessage) => void;
    getSpeakState?: (message: ChatMessage) => SpeakState;
    showCopy?: boolean;
    jsonCollapseAfterDepth?: number;
    /**
     * Image loading in the message's Markdown. Default: `"link"` for every
     * message except the user's own (model- and workflow-written text cannot
     * make the browser fetch a remote URL; only images `inlineImage` accepts,
     * by default same-origin ones, load), `"inline"` for user messages.
     * Ignored when `renderMarkdown` is set (the host renderer decides).
     */
    images?: MarkdownImages;
    inlineImage?: (src: string) => boolean;
    /**
     * Per-message slot rendered under the card (after attachments and stats),
     * e.g. a per-turn detail badge. Return null for nothing.
     */
    renderFooter?: (message: ChatMessage) => React.ReactNode;
    /**
     * Per-message presentation. `"hint"` renders the message as one discreet
     * line (no avatar, header or copy): a system note such as "Rejoined the
     * open visit". `"caption"` renders the message's content only (Markdown, media, files and
     * attachments; no header, speaker, copy, reasoning, stats, notice badges or footer) for subtitle-like
     * surfaces such as the Avatar view's live line and findings. `undefined` keeps the full card.
     */
    variant?: (message: ChatMessage) => "hint" | "caption" | undefined;
    /** Host opener for `media` items of kind `"file"` (e.g. a side drawer).
     * Without it the file opens inline in the shared viewer. */
    onOpenMedia?: (item: ChatMedia) => void;
    /**
     * Host opener for a notice badge (`message.notices`), e.g. the record's detail panel by its
     * `record_id`. Return `false` when nothing was opened: the badge opens its own panel (title and
     * words). Without it every badge opens its own panel.
     */
    onNoticeOpen?: (notice: ChatNotice, message: ChatMessage) => void | boolean;
    /**
     * The card for a mention chip in a message's words (`message.mentions`), e.g. the entity's
     * card from your roster: shown in a small popover below the chip after a 150 ms rest on it
     * (pointer or keyboard focus), gone on leave, blur or Escape. Called only then, with the
     * mention ({id, name, kind, index, start, avatar?}); null shows nothing. Absent: no card.
     */
    renderMentionCard?: (mention: ChatMessageMention) => React.ReactNode | null;
};
/** The read-aloud state a host reports for a message (`useGatewayVoice().tts_playback.status`). */
export type SpeakState = "idle" | "loading" | "playing" | "paused";
/**
 * What the message's speaker button shows for a read-aloud state: the spinner ONLY while the
 * first audio is being generated ("loading"); once audio plays, Pause; paused, Play; else the
 * speaker. A host that keeps "loading" while audio plays is wrong: `useGatewayVoice` turns
 * "playing" as the first segment starts (check_voice_stream.mjs).
 */
export declare function speakButtonView(state: SpeakState): {
    icon: IconName;
    title: string;
    spinning: boolean;
};
/**
 * One chat message. Its meta line (stamp, speaker, copy) and stat chips follow the message
 * footer spec in `message_footer.ts` (the one spec every web app and the desktop follow):
 *  - stamp: `formatMessageStamp` (time today; "Yesterday · 10:52 PM"; "Oct 21 · 10:52 PM");
 *  - speaker: on every assistant message when `onSpeakToggle` is given, always visible;
 *    disabled with its reason while streaming or without text, never dropped;
 *  - copy: always visible unless `showCopy === false`;
 *  - stat chips: each opens the structured `StatDetailPanel`, never a multi-line `title`.
 */
export declare function ChatMessageCard(props: ChatMessageCardProps): React.ReactElement;
export default ChatMessageCard;
//# sourceMappingURL=chat_message_card.d.ts.map