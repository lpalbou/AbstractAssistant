/**
 * The message footer SPEC (operator QA 2026-10-28, AbstractUIC 0.8.4; backlog 0064).
 *
 * One spec for every chat surface of the framework. The web apps render it through
 * `ChatMessageCard` (never a local twin); the AbstractAssistant desktop mirrors it in its
 * own Qt bubble (it differs today: "Yesterday 10:52 PM" without the separator, a zero-padded
 * day "Oct 01", no year form, the raw text for a malformed stamp; its owner aligns it).
 * Exception until backlog 0063: the Docs assistant has no read-aloud path, so its answers
 * carry no speaker. A message's meta line holds, in this order:
 *
 *  1. STAMP: `formatMessageStamp(ts, now)`, in the reader's locale and time zone:
 *       - today              -> the time only               "12:46 AM"
 *       - yesterday          -> "Yesterday · " + time        "Yesterday · 10:52 PM"
 *       - earlier this year  -> short month, day · time      "Oct 21 · 10:52 PM"
 *       - another year       -> month, day, year · time      "Oct 21, 2025 · 10:52 PM"
 *     (a future day, e.g. clock skew, uses the dated form). "Today"/"yesterday" are the
 *     reader's calendar days, not 24 h windows; an open card re-renders at local midnight
 *     (`useLocalDay`). The full date and time is the stamp's hover text (`messageStampTitle`).
 *     A missing or malformed timestamp shows no stamp, never "Invalid Date". A bare date
 *     ("2026-10-27") is that local day, stamped without a time ("Yesterday", "Oct 27").
 *  2. SPEAKER: on EVERY assistant message whenever the host has a read-aloud path (the
 *     card's `onSpeakToggle`), always visible (never hover-only), on every assistant
 *     message kind (answers, questions, warnings, a reply from history, a reply that
 *     carries media). Its states are `speakButtonView` (speaker / spinner while the
 *     first audio is generated / Pause / Resume). While the reply is still streaming,
 *     or when the message has no text to read, the speaker stays in place DISABLED with
 *     its reason as the hover text ("Read aloud when the reply is finished", "No text to
 *     read aloud"; `aria-disabled`, still focusable), so the row never jumps and the reader
 *     sees the feature exists.
 *     User and system messages carry no speaker; a tool-activity row and a one-line
 *     system hint are not messages and carry no meta line.
 *  3. COPY: on every card unless the host passes `showCopy={false}`; always visible.
 *
 * Under the body, the STAT CHIPS of a workflow turn (`message.statistics`): tokens, tools,
 * files changed, duration. Every chip opens the structured `StatDetailPanel` on hover or
 * keyboard focus (title, headline, sections, footnote; `statDetail()`), never a native
 * multi-line `title` tooltip. A value the ledger did not report reads "not reported",
 * never 0. Labels are readable words (ADR 0043): file names, counts, durations; no ids.
 *
 * Checked by `panel-chat/scripts/check_message_footer.mjs` (red when the date is dropped
 * for a message not from today, when the speaker disappears from an assistant message of
 * a TTS host, or when a stat chip falls back to a plain `title`).
 */
/**
 * The message stamp: the time today, "Yesterday · <time>", "<Mon D> · <time>" earlier this
 * year, "<Mon D, YYYY> · <time>" another year. "" for a missing or malformed timestamp.
 * `locales` defaults to the reader's (undefined = the runtime's default locale).
 */
export declare function formatMessageStamp(ts: string | number | Date | null | undefined, now?: Date, locales?: string | string[]): string;
/** The stamp's hover text: the full date and time ("Tuesday, October 21, 2026 at 10:52 PM"). "" when malformed. */
export declare function messageStampTitle(ts: string | number | Date | null | undefined, locales?: string | string[]): string;
/** The stamp's machine-readable form for `<time dateTime>` (ISO 8601). "" when malformed. */
export declare function messageStampIso(ts: string | number | Date | null | undefined): string;
/** The reader's calendar day, as a key: a card re-derives its stamp when the day changes. */
export declare function localDayKey(now?: Date): string;
/** Internal (not re-exported from the package): the shared midnight timer, exported for its check. */
export declare function subscribeLocalDay(listener: () => void): () => void;
/** The reader's calendar day (`localDayKey`); the component re-renders when it changes (local midnight).
 *  Plain useState/useEffect (no useSyncExternalStore), so host test harnesses that stub React's basic hooks keep working. */
export declare function useLocalDay(): string;
//# sourceMappingURL=message_footer.d.ts.map