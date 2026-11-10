import React from "react";
import { type ChatComposerSend, type ChatMention, type ChatMentionCandidate } from "./mentions.js";
/** Rounded multiline is the shared default; `legacy` restores the former flat layout. */
export type ChatComposerVariant = "compact" | "legacy";
export type ChatComposerProps = {
    value: string;
    onChange: (value: string) => void;
    /** Send (Enter or the button). `onSend` wins when given. */
    onSubmit?: () => void;
    /**
     * Send with the picked mentions: `{text, mentions: [{id, name, kind, index, start}]}`. `text` is
     * the message as shown, each chip written as "@" + its name; `mentions` are the chips in text
     * order, `index` 0, 1, … (the gateway's `mention_index`) and `start` where the chip's "@Name"
     * sits in `text`. Wins over `onSubmit`. Uncontrolled chips are cleared once it returns (or its
     * promise resolves); a throw or a rejection keeps them.
     */
    onSend?: (send: ChatComposerSend) => void | Promise<unknown>;
    /**
     * `@` mentions. Typing `@` opens a list of the names this returns for the query typed after
     * it (the HOST decides the source, e.g. `GET /entities`; it is called as the person types, so
     * cache in the host). A pick puts a chip bound to that candidate in the text, in place of the
     * typed `@query`; an `@` that was not picked stays plain text. Absent: no list and no chips.
     */
    mentionCandidates?: (query: string) => Promise<ChatMentionCandidate[]>;
    /**
     * Controlled chips, each with `start` (where its "@Name" sits in `value`); `onMentionsChange`
     * gets them in text order after every edit. A chip whose "@Name" is not at its `start` is not
     * in the message (not drawn, not sent) until the text holds it there again (a draft the host
     * restores after a failed send); the person's next edit drops it. Omit to let the composer keep them.
     */
    mentions?: ChatMention[];
    onMentionsChange?: (mentions: ChatMention[]) => void;
    /**
     * The sentence shown above the field the first time a name is picked in this conversation
     * (e.g. "Castor will read this conversation's history"), while its chip is in the text. The
     * host writes it; null = none.
     */
    mentionNotice?: (candidate: ChatMentionCandidate) => string | null | undefined;
    /** The conversation "the first time" counts in (e.g. the session id); a new key starts over. */
    mentionSessionKey?: string;
    /**
     * The host's sentence when mentions cannot be used here (e.g. an older gateway without the
     * mentions route: "This gateway does not offer mentions yet"). Typing `@` then shows this
     * sentence instead of names (no new chip), and it stays under any chips already picked.
     */
    mentionsUnavailable?: string | null;
    /**
     * A sentence the host shows about the last mentions it sent (e.g. "Castor is in another
     * conversation."); shown above the field, with or without chips, until the host clears it.
     */
    mentionStatus?: string | null;
    /** Omit for the shared rounded multiline composer; `legacy` restores the former layout. */
    variant?: ChatComposerVariant;
    placeholder?: string;
    /** Accessible name for the message field. Falls back to its placeholder. */
    ariaLabel?: string;
    textareaId?: string;
    ariaDescribedBy?: string;
    disabled?: boolean;
    busy?: boolean;
    rows?: number;
    autoFocus?: boolean;
    className?: string;
    textareaClassName?: string;
    sendButtonClassName?: string;
    sendLabel?: string;
    busyLabel?: string;
    /** Host eligibility for attachment-only or other valid payloads. Busy/disabled still win. */
    canSubmit?: boolean;
    /** Preserve multiline-first chats that submit with Ctrl/Cmd+Enter. */
    submitKey?: "enter" | "mod-enter";
    actions?: React.ReactNode;
    /**
     * The primary round button turns into Stop (compact variant): an arrow-to-square
     * morph, same size and place. `active` = Stop right now; `stopping` = the stop
     * was asked and is settling (aria-busy). Absent = the button is only ever Send.
     */
    stop?: {
        active: boolean;
        stopping?: boolean;
        onStop: () => void;
        label?: string;
    };
    /** Controls next to Send, such as a microphone. */
    trailingActions?: React.ReactNode;
    /** Shared attachment control; the host owns its file chooser and upload lifecycle. */
    onAttach?: () => void;
    attachLabel?: string;
    attachDisabled?: boolean;
    attachPending?: boolean;
    /** Rendered inside the composer box above the textarea (e.g. attachment chips). */
    leading?: React.ReactNode;
    /** Absolutely positioned layer over the composer box (e.g. a drop zone). */
    overlay?: React.ReactNode;
    /** Runs first; a `preventDefault()` here (e.g. pasted files) keeps the composer's own paste out. */
    onPaste?: React.ClipboardEventHandler<HTMLTextAreaElement>;
};
export declare const ChatComposer: React.ForwardRefExoticComponent<ChatComposerProps & React.RefAttributes<HTMLTextAreaElement>>;
//# sourceMappingURL=chat_composer.d.ts.map