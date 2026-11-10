import React from "react";
import { type MarkdownImages } from "./markdown.js";
import { type ChatMessageMention } from "./mentions.js";
export declare function ChatMessageContent(props: {
    text: string;
    className?: string;
    renderMarkdown?: (markdown: string) => React.ReactElement;
    jsonCollapseAfterDepth?: number;
    /** Passed to `Markdown` (default `"inline"` here; chat cards pass `"link"` for non-user messages). */
    images?: MarkdownImages;
    inlineImage?: (src: string) => boolean;
    /**
     * The message's mentions ({id, name, kind, index, start}): each one whose "@Name" sits at its
     * `start` in `text` is drawn as the composer's chip, in place. One without a valid `start`
     * keeps its plain words (logged once as `#SEAM`). Drawn by the kit's Markdown only (not with
     * `renderMarkdown`, not in a JSON message).
     */
    mentions?: readonly ChatMessageMention[];
    /** The host's card for a mention chip, shown after a 150 ms rest on it (`ChatMentionChip`). */
    renderMentionCard?: (mention: ChatMessageMention) => React.ReactNode | null;
}): React.ReactElement;
//# sourceMappingURL=message_content.d.ts.map