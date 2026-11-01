import React from "react";
export type ChatComposerProps = {
    value: string;
    onChange: (value: string) => void;
    onSubmit: () => void;
    /** Compact rounded multiline box; the existing layout is the default. */
    variant?: "default" | "compact";
    placeholder?: string;
    /** Accessible name for the message field. Falls back to its placeholder. */
    ariaLabel?: string;
    disabled?: boolean;
    busy?: boolean;
    rows?: number;
    autoFocus?: boolean;
    className?: string;
    textareaClassName?: string;
    sendButtonClassName?: string;
    sendLabel?: string;
    busyLabel?: string;
    actions?: React.ReactNode;
    /** Rendered inside the composer box above the textarea (e.g. attachment chips). */
    leading?: React.ReactNode;
    /** Absolutely positioned layer over the composer box (e.g. a drop zone). */
    overlay?: React.ReactNode;
    onPaste?: React.ClipboardEventHandler<HTMLTextAreaElement>;
};
export declare const ChatComposer: React.ForwardRefExoticComponent<ChatComposerProps & React.RefAttributes<HTMLTextAreaElement>>;
//# sourceMappingURL=chat_composer.d.ts.map