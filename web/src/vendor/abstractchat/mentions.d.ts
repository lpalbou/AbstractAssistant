/**
 * `@` mentions in the composer ("@entity from any chat window", operator 2026-11-08).
 *
 * A mention is STRUCTURED: the person types `@`, picks a name from a list the HOST feeds
 * (`mentionCandidates`), and the pick becomes a chip bound to that candidate. The kit never
 * reads `@` out of the text on send (no-heuristics ruling): an `@` that was not picked stays
 * plain text. The only text rule here is the input-time trigger (an `@` the person is typing
 * at the caret opens the list), the same rule as any completion popup.
 *
 * DOM-free; checked by `scripts/check_mentions.mjs`.
 */
import type { ChatAvatarLook } from "./chat_author.js";
export type ChatMentionKind = "entity" | "agent";
/** One name the host offers (e.g. from `GET /entities`). */
export type ChatMentionCandidate = {
    id: string;
    name: string;
    kind: ChatMentionKind;
    avatar?: ChatAvatarLook | null;
    /** A short second line in the list (e.g. "your research partner"). */
    hint?: string;
};
/** A chip in the composer: the candidate it was picked from. */
export type ChatMention = ChatMentionCandidate;
/** A mention as sent: `index` is its position among the message's mentions (0, 1, …),
 * the gateway's `mention_index`. */
export type ChatMentionSent = {
    id: string;
    name: string;
    kind: ChatMentionKind;
    index: number;
};
/** What a send carries: the text exactly as typed, and the picked mentions in order. */
export type ChatComposerSend = {
    text: string;
    mentions: ChatMentionSent[];
};
/** The `@` being typed at the caret: where it starts and what follows it. */
export type MentionTrigger = {
    start: number;
    query: string;
};
/** The longest query the list follows; past it the `@` is just text. */
export declare const MENTION_QUERY_MAX = 48;
/**
 * The `@` the person is typing at `caret`, or null. It opens the list when it starts the
 * text or follows a space, and nothing but non-space characters sit between it and the
 * caret ("me@host" and "@ " do not open it).
 */
export declare function mentionTriggerAt(text: string, caret: number): MentionTrigger | null;
/** The text once a pick replaces the typed `@query`, and where the caret goes. */
export declare function applyMentionPick(text: string, trigger: MentionTrigger, caret: number): {
    text: string;
    caret: number;
};
export declare function mentionKey(m: Pick<ChatMentionCandidate, "kind" | "id">): string;
/** The chips once `candidate` is picked: appended, once (a second pick of the same name is a no-op). */
export declare function addMention(list: readonly ChatMention[], candidate: ChatMentionCandidate): ChatMention[];
export declare function removeMention(list: readonly ChatMention[], key: string): ChatMention[];
/** A send: the text as typed and the chips in the order they appear (picked), numbered. */
export declare function mentionSendPayload(text: string, mentions: readonly ChatMention[]): ChatComposerSend;
/** The highlighted option after an arrow key: wraps at both ends; -1 when the list is empty. */
export declare function moveMentionActive(active: number, count: number, delta: number): number;
/** Candidates the list can show: an id, a name and a known kind; the rest are dropped. */
export declare function usableCandidates(value: unknown): ChatMentionCandidate[];
//# sourceMappingURL=mentions.d.ts.map