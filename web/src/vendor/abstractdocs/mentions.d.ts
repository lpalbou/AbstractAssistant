/**
 * `@` mentions in the composer ("@entity from any chat window", operator 2026-11-08; inline in
 * the text, operator 2026-11-10).
 *
 * A mention is STRUCTURED: the person types `@`, picks a name from a list the HOST feeds
 * (`mentionCandidates`), and the pick puts a chip bound to that candidate INTO the text, where the
 * `@query` was. The chip's text is its display form, `@` + the name ("@Castor"); the chip itself
 * is the candidate plus `start`, where that text sits. The kit never reads `@` out of the text
 * (no-heuristics ruling): an `@name` that was not picked (typed, or pasted from elsewhere) stays
 * plain text. The only text rule here is the input-time trigger (an `@` the person is typing at
 * the caret opens the list), the same rule as any completion popup.
 *
 * The serialization a send carries (`mentionSendPayload`):
 *   text      the message as shown, each chip written as "@" + its name, e.g.
 *             "Hi @Castor how are you doing ?"
 *   mentions  the chips in TEXT order: {id, name, kind, index, start}, where
 *             index = 0, 1, 2… (the chip's place among the message's mentions, the gateway's
 *                     `mention_index`), and
 *             start = the UTF-16 offset of its "@Name" in `text`, so
 *                     text.slice(start, start + name.length + 1) === "@" + name.
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
/**
 * A chip in the composer: the candidate it was picked from, and `start`, the UTF-16 offset of its
 * "@Name" in the composer's text. A chip whose "@Name" is not at `start` (no `start`, or the text
 * changed under it) is not in the message: it is not drawn and not sent.
 */
export type ChatMention = ChatMentionCandidate & {
    start?: number;
};
/** A mention as sent: `index` is its place among the message's mentions in text order (0, 1, …),
 * the gateway's `mention_index`; `start` is where its "@Name" sits in the sent text (the composer
 * always sets it). */
export type ChatMentionSent = {
    id: string;
    name: string;
    kind: ChatMentionKind;
    index: number;
    start?: number;
};
/** What a send carries: the text as shown (each chip as "@Name"), and its mentions in text order. */
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
/** The text once a pick REMOVES the typed `@query`, and where the caret goes (the chips-above
 * composer up to panel-chat 0.9.11; the composer now uses `mentionPickEdit`). */
export declare function applyMentionPick(text: string, trigger: MentionTrigger, caret: number): {
    text: string;
    caret: number;
};
export declare function mentionKey(m: Pick<ChatMentionCandidate, "kind" | "id">): string;
/** The chips once `candidate` is picked: appended, once (a second pick of the same name is a no-op). */
export declare function addMention(list: readonly ChatMention[], candidate: ChatMentionCandidate): ChatMention[];
export declare function removeMention(list: readonly ChatMention[], key: string): ChatMention[];
/** A send: the text as shown and the chips that are in it, in text order, numbered (`index`) and
 * placed (`start`). A chip not in the text (`mentionsInText`) is not sent. */
export declare function mentionSendPayload(text: string, mentions: readonly ChatMention[]): ChatComposerSend;
/** A chip's text in the message: "@" and its name, the display form ("@Castor"). */
export declare function mentionText(m: Pick<ChatMentionCandidate, "name">): string;
/** Where a chip's "@Name" ends in the text (`start` + its length). */
export declare function mentionEnd(m: ChatMention): number;
/**
 * The chips that are in `text`: each one's "@Name" sits at its `start`. In text order, each name
 * once; of two that overlap, the earlier one.
 */
export declare function mentionsInText<M extends ChatMention>(text: string, mentions: readonly M[]): M[];
/** The span an edit changed: `[start, prevEnd)` of the old text became `[start, nextEnd)` of the new. */
export type MentionEditSpan = {
    start: number;
    prevEnd: number;
    nextEnd: number;
};
/**
 * What changed between `prev` and `next`. `caret` (where the caret is in `next` right after the
 * edit) anchors the end of the change when the text after it is unchanged: typing "@" just before
 * a chip "@Castor" is then an insertion before the chip, never one inside it.
 */
export declare function mentionEditSpan(prev: string, next: string, caret?: number | null): MentionEditSpan;
/**
 * The chips once the person edited `prev` into `next`: a chip before the change stays, one after
 * it moves with the text, and one the change touched is gone (deleted, typed over, or cut into:
 * its remaining letters are plain text). Only chips that were in `prev` are carried.
 */
export declare function mentionsAfterEdit<M extends ChatMention>(prev: string, next: string, mentions: readonly M[], caret?: number | null): M[];
/**
 * `mentions` plus `added` (chips with `start` relative to `at`, e.g. pasted), placed in `text` at
 * `at`. A name already in the text is not added twice (the pasted one stays plain text).
 */
export declare function mentionsWithInserted<M extends ChatMention>(text: string, mentions: readonly M[], at: number, added: readonly M[]): M[];
/** A pick: the chip's "@Name" replaces the typed `@query` (`from`..`to`), with one space after it
 * unless a space follows; `caret` goes after that space. */
export type MentionPickEdit = {
    from: number;
    to: number;
    insert: string;
    text: string;
    caret: number;
};
export declare function mentionPickEdit(text: string, trigger: MentionTrigger, caret: number, candidate: Pick<ChatMentionCandidate, "name">): MentionPickEdit;
/** The chip that ends at `caret` ("before": what Backspace deletes) or starts there ("after":
 * what Delete deletes), or null. */
export declare function mentionAtCaret<M extends ChatMention>(text: string, mentions: readonly M[], caret: number, side: "before" | "after"): M | null;
/**
 * The selection kept off the inside of chips. A caret inside a chip goes to the edge it moved
 * across (`from`, the caret one step before) or else the nearer one; a range that cuts a chip
 * grows to cover it whole.
 */
export declare function mentionSelection(text: string, mentions: readonly ChatMention[], start: number, end: number, from?: number | null): {
    start: number;
    end: number;
};
/** The clipboard type that carries chips between copies and pastes of the composer. */
export declare const MENTION_CLIPBOARD_TYPE = "application/x-abstractframework-mentions+json";
/** What a copy of `text[from, to)` puts on the clipboard under `MENTION_CLIPBOARD_TYPE`: the
 * chips wholly inside it, `start` relative to `from`; null when it holds none. */
export declare function mentionClipboard(text: string, mentions: readonly ChatMention[], from: number, to: number): string | null;
/**
 * The chips a paste brings: only those a copy of this composer put on the clipboard
 * (`mentionClipboard`), and only when the pasted plain text is exactly what that copy held
 * (`start` relative to the paste). Anything else is plain text: an "@name" is never read out of it.
 */
export declare function mentionsFromClipboard(data: string | null | undefined, plain: string): ChatMention[] | null;
/**
 * A send whose mentions stopped partway (an entity could not answer, a call failed): the chips
 * NOT answered (the failed one and those after it) are what the composer keeps for a resend.
 * A host's `onSend` / `onSteer` names them as `unsentMentions` on what it settles with: the
 * value it resolves, or the error it rejects with (`mentionsStoppedError`).
 */
export type ChatMentionsUnsent = {
    unsentMentions: ChatMentionSent[];
};
/** The chips a settled send names to keep (`unsentMentions` on its value or its error);
 * null when it names none (an array, empty included, is a choice). */
export declare function unsentMentionsOf(settled: unknown): ChatMentionSent[] | null;
/** The error a host rejects a send with when its mentions stopped partway: the sentence to show
 * and the chips to keep (`unsentMentions`). */
export declare function mentionsStoppedError(sentence: string, unsent: readonly ChatMentionSent[]): Error & ChatMentionsUnsent;
/**
 * The chips once a send settled. `sent`: the chips the composer held when it sent. Those are
 * removed, except the ones `keep` names (a send that stopped partway keeps its unsent chips for
 * the resend). Chips picked WHILE the send was in flight are not the send's and stay, in order.
 */
export declare function mentionsAfterSend(now: readonly ChatMention[], sent: readonly Pick<ChatMentionCandidate, "kind" | "id">[], keep?: readonly Pick<ChatMentionCandidate, "kind" | "id">[]): ChatMention[];
/**
 * What a send stopped partway leaves for the resend: its words, the person's own turn they were
 * sent with (`repeat_of`; null when none), and the mentions not answered, with their first `index`.
 */
export type MentionResend = {
    text: string;
    repeatOf: string | null;
    unsent: ChatMentionSent[];
};
/**
 * The mentions to ask when a send RESENDS `pending`, or null when it is a new message.
 * A resend = the same words (trimmed) with at least one chip: it asks ONLY those chips, each
 * entity once, with the same `repeat_of` and never a new turn of the person (the host's rule).
 * A chip that was unsent keeps its first index; a chip added since is numbered after them.
 */
export declare function mentionResend(pending: MentionResend | null | undefined, text: string, mentions: readonly ChatMentionSent[]): ChatMentionSent[] | null;
/** A message's mentions, each name once: the first occurrence keeps its place and index. */
export declare function uniqueMentions<M extends Pick<ChatMentionCandidate, "kind" | "id">>(mentions: readonly M[]): M[];
/** The highlighted option after an arrow key: wraps at both ends; -1 when the list is empty. */
export declare function moveMentionActive(active: number, count: number, delta: number): number;
/** Candidates the list can show: an id, a name and a known kind; the rest are dropped. */
export declare function usableCandidates(value: unknown): ChatMentionCandidate[];
//# sourceMappingURL=mentions.d.ts.map