/**
 * What a reply formed, shown as badges under its words (AbstractRuntime turn notices,
 * 2026-11-09). The runtime serves the reply WITHOUT its bracket markers
 * ("[kept in diary - …]", "[learned: "…"]") and, beside it, a structured list:
 *
 *   [{kind: "diary"|"question"|"lesson"|"interest"|"realization",
 *     record_id: <graph id of the formed record> | null,
 *     title: <as formed; "" while it is still being written>,
 *     text?: <his words, whole>,
 *     visibility?: "private",        a private diary entry: title "" and no words
 *     staged?: true}]                a visit-lane election that forms at the visit's close
 *                                    (record_id null until then)
 *
 * The kit never reads a marker out of the text: a badge exists only for a served notice.
 * This module is pure (no DOM, no React): `chatNoticesOf` reads a served list, `chatNoticeView`
 * says what one badge shows. `ChatNoticeBadges` (chat_notice_badges.tsx) renders the row.
 */
import type { IconName } from "@abstractframework/ui-kit";
/** The kinds the runtime serves today. Another kind still renders, with its own word. */
export type ChatNoticeKind = "diary" | "question" | "lesson" | "interest" | "realization";
/** One structured turn notice, as served (snake_case kept: the host hands it back to its gateway). */
export type ChatNotice = {
    kind: ChatNoticeKind | (string & {});
    /** The graph id of the formed record; null while it is staged for the visit's close. */
    record_id: string | null;
    /** The title as formed ("" while it is still being written, and for a private entry). */
    title: string;
    /** His words, whole (absent for a private entry and for most diary entries). */
    text?: string;
    /** "private": a private diary entry; it carries no words. */
    visibility?: string;
    /** A visit-lane lesson, interest or realization that forms at the visit's close. */
    staged?: boolean;
};
export declare const CHAT_NOTICE_KINDS: readonly ChatNoticeKind[];
/** The words for the badge's own sentences (exported so hosts and checks use the same ones). */
export declare const CHAT_NOTICE_WORDS: {
    readonly group: "Kept from this reply";
    readonly private: "private diary entry";
    readonly staged: "forming…";
    /** The staged word in a badge's accessible name (no ellipsis glyph for a screen reader to say). */
    readonly stagedSpoken: "forming";
    readonly privateNote: "A private diary entry: its words are not shown in the conversation.";
    readonly stagedNote: "Forming: it is kept when the visit closes.";
    readonly close: "Close";
};
/**
 * The notices of a served list (a reply's `notices` / `reply_notices`): only notice-shaped
 * items (an object with a `kind`), the runtime's own rule (`history_bundle.turn_notices_of`); a
 * list of plain strings (an operator log) is not this list. Fields are copied as served, never
 * derived from text.
 */
export declare function chatNoticesOf(raw: unknown): ChatNotice[];
/** What one badge says. */
export type ChatNoticeView = {
    key: string;
    kind: string;
    /** The kind's word ("diary", "lesson", …). */
    word: string;
    icon: IconName;
    /** After the word: the title; "private diary entry"; else his words (whole; the badge shows
     *  their first words, the panel all of them); "" = the word alone. */
    label: string;
    /** The label is his words (the title is still empty). */
    fromText: boolean;
    private: boolean;
    /** Forms at the visit's close (no record yet). */
    staged: boolean;
    /** The badge's accessible name: words only (his line breaks read as spaces, no glyph). */
    ariaLabel: string;
};
export declare function chatNoticeView(notice: ChatNotice, index?: number): ChatNoticeView;
//# sourceMappingURL=chat_notices.d.ts.map