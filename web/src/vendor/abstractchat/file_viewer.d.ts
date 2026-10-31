import React from "react";
import { type AfFileViewerKind, type AfFileViewerProps } from "@abstractframework/ui-kit";
import { type MarkdownImages } from "./markdown.js";
/** A gateway request with the host's credentials (see `workspace_browser.tsx`). */
type GatewayFetch = (path: string, init?: RequestInit) => Promise<Response>;
/** Bytes read for a text preview; larger files show their first part. */
export declare const PREVIEW_TEXT_LIMIT: number;
export declare const PREVIEW_LIMIT_LABEL = "1 MiB";
/** Images / audio / PDFs larger than this are offered as a download only. */
export declare const PREVIEW_BLOB_LIMIT: number;
export type BoundedText = {
    text: string;
    received: number;
    total?: number;
    partial: boolean;
};
/** The size a content response reports: the total of `Content-Range` (a 206), else `Content-Length` of a full 200. */
export declare function responseTotal(response: Response): number | undefined;
/** Read at most `limit` bytes of a response body as text, then stop reading (never the whole of a large file). */
export declare function readBoundedText(response: Response, limit: number, knownSize?: number): Promise<BoundedText>;
export declare function partialPreviewNote(total: number | undefined): string;
/**
 * Markdown previews never load images from elsewhere: an image renders only
 * when its URL is this run's workspace content route (a relative path is
 * resolved against the Markdown file's folder); any other image becomes a
 * plain link. Fenced code is left untouched.
 */
export declare function safeMarkdownImages(text: string, runId: string, markdownPath: string): string;
export type FilePreviewEntry = {
    name: string;
    path: string;
    size_bytes?: number;
};
export type FilePreviewState = {
    status: "idle";
} | {
    status: "loading";
    kind: AfFileViewerKind;
} | {
    status: "error";
    kind: AfFileViewerKind;
    message: string;
} | {
    status: "ready";
    kind: AfFileViewerKind;
    contentType: string;
    text?: string;
    url?: string;
    partial: boolean;
    total?: number;
};
/**
 * Load one workspace file for the viewer. Text kinds: a bounded Range read.
 * Image / audio / video / PDF: the bytes as an object URL (revoked when the entry changes).
 * Binary: nothing is read. `refreshKey` re-reads (the run wrote again).
 */
export declare function useWorkspaceFilePreview(fetchGateway: GatewayFetch, runId: string, entry: FilePreviewEntry | null, refreshKey?: string | number): FilePreviewState;
export type FileViewerProps = Omit<AfFileViewerProps, "renderMarkdown" | "nowMs"> & {
    nowMs?: number;
    /** Image loading in a Markdown file (see `Markdown`): `"link"` keeps remote
     * images as links (only `inlineImage`-accepted sources load). Default: inline. */
    markdownImages?: MarkdownImages;
    inlineImage?: (src: string) => boolean;
    /** A host Markdown renderer (e.g. its sanitizer); wins over the built-in one. */
    renderMarkdown?: (markdown: string) => React.ReactNode;
};
/** `AfFileViewer` with panel-chat's Markdown renderer (the one every client uses). */
export declare function FileViewer(props: FileViewerProps): React.ReactElement;
/** Props of `FileViewer` for a loaded `FilePreviewState`. */
export declare function filePreviewViewerProps(state: FilePreviewState): Pick<AfFileViewerProps, "status" | "error" | "text" | "url" | "kind" | "contentType" | "partialNote">;
export {};
//# sourceMappingURL=file_viewer.d.ts.map