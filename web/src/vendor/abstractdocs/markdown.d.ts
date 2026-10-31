import React from "react";
/**
 * Default rule for `images="link"`: an image loads only from the page's own
 * origin. The source is resolved like the browser resolves it — against
 * `document.baseURI` — so a RELATIVE path (the kit's own "api/gateway/…"
 * workspace content route, which resolves under an app mounted at
 * /apps/<id>/), a root-relative path and an absolute URL with the page's
 * origin all load. Protocol-relative (`//host/…`, `/\host`), another origin,
 * and every non-http(s) scheme (`javascript:`, `data:`, `blob:`, …) become
 * links. Without a document (server rendering), a source that resolves to
 * no other origin — i.e. a relative one — counts as same-origin.
 */
export declare function sameOriginImage(src: string): boolean;
export type MarkdownImages = "inline" | "link";
export type MarkdownProps = {
    text: string;
    className?: string;
    highlight?: string;
    highlights?: string[];
    highlightClassName?: string;
    highlightId?: string;
    /**
     * `"inline"` (default for `Markdown`) loads every image. `"link"` loads
     * only images `inlineImage(src)` accepts (default `sameOriginImage`) and
     * shows every other one as a link "image: <alt>", so text written by a
     * model cannot make the browser fetch a remote URL. Chat messages use
     * `"link"` for assistant and system messages.
     */
    images?: MarkdownImages;
    inlineImage?: (src: string) => boolean;
};
export declare function Markdown(props: MarkdownProps): React.ReactElement;
//# sourceMappingURL=markdown.d.ts.map