import React from "react";
export type TextLinkPart = {
    text: string;
    href?: string;
};
/** Detect whole URLs before applying decoration. Never interpret text as HTML. */
export declare function splitTextLinks(text: string): TextLinkPart[];
export declare function textLinks(text: string): React.ReactNode[];
export declare function TextLinks({ text }: {
    text: string;
}): React.ReactElement;
/** Keep JSON escape notation in text without treating its backslashes as URL bytes. */
export declare function JsonTextLinks({ text }: {
    text: string;
}): React.ReactElement;
//# sourceMappingURL=text_links.d.ts.map