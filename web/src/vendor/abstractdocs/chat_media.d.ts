import type { ChatMedia } from "./chat_message_card.js";
import type { ResolvedArtifact } from "./workflow_runtime.js";
/**
 * A browser-local URL (object or data URL): it carries the APP's origin and
 * none of the gateway's headers. Decided by the URL parser, as the browser
 * decides it: it strips leading C0 controls and spaces, so "\u0000blob:…" is
 * a blob URL (review of PR #4). An unparseable value counts as local (fail closed).
 */
export declare function isLocalObjectUrl(url: string | undefined): boolean;
/**
 * Whether a `blob:`/`data:` URL of this file may be opened as its "Raw file"
 * (review N1, security). An object URL carries the APP origin and none of the
 * gateway's `Content-Security-Policy: sandbox` / nosniff headers
 * (abstractgateway routes/gateway.py:11328-11340), so agent-written HTML, SVG
 * or XML opened from it would run on the app's origin. Only an ALLOWLIST of
 * inert types qualifies (pdf, JSON, plain text, Markdown, CSV/TSV, common
 * source-code text types, raster images, concrete audio/video subtypes; no
 * wildcard), never a file whose
 * NAME is an active document; anything unlisted (e.g. `text/xsl`) or no type = no.
 * The guard trusts the declared type: `contentType` MUST be the type the object
 * URL's Blob was created with (`new Blob([bytes], { type: contentType })`).
 * Hosts pass the gateway's (sandboxed) content URL as `href` for the rest.
 */
export declare function objectUrlRawLinkSafe(contentType: string | undefined, name: string | undefined): boolean;
/** The raw-file link a document may show: the host's `href`, else its `src`; a
 * browser-local URL only for an inert type (see `objectUrlRawLinkSafe`). */
export declare function fileRawLink(item: {
    href?: string;
    src?: string;
    contentType?: string;
    name?: string;
}): string | undefined;
/**
 * How a resolved artifact shows in a message: image / audio / video inline,
 * everything else as a `"file"` in the shared viewer. The kind comes from the
 * gateway's `content_type` (and the name), never from model text. SVG and
 * HTML are files (shown as source), never rendered.
 */
export declare function chatMediaFromArtifact(artifact: ResolvedArtifact, extra?: {
    id?: string;
    label?: string;
    href?: string;
    transcript?: string;
    text?: string;
}): ChatMedia;
/**
 * Resolve a message's `artifactIds` (e.g. `replay_view_v1.messages[].artifact_ids`)
 * through the transport's `resolveArtifact`. Rejects when any artifact cannot
 * be resolved: a missing artifact is an error to show, not a silent gap.
 */
export declare function chatMediaForArtifacts(runId: string, artifactIds: readonly string[], resolve: (runId: string, artifactId: string, signal?: AbortSignal) => Promise<ResolvedArtifact>, signal?: AbortSignal): Promise<ChatMedia[]>;
//# sourceMappingURL=chat_media.d.ts.map