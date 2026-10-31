import React from "react";
import { type MarkdownImages } from "./markdown.js";
export declare function ChatMessageContent(props: {
    text: string;
    className?: string;
    renderMarkdown?: (markdown: string) => React.ReactElement;
    jsonCollapseAfterDepth?: number;
    /** Passed to `Markdown` (default `"inline"` here; chat cards pass `"link"` for non-user messages). */
    images?: MarkdownImages;
    inlineImage?: (src: string) => boolean;
}): React.ReactElement;
//# sourceMappingURL=message_content.d.ts.map