import React from "react";
/**
 * A gateway request with the host's credentials. `path` is RELATIVE,
 * "api/gateway/…" (ui-kit `gatewayApiPath`): a same-origin host passes it to
 * `fetch` as is (it resolves under the app's base path) with
 * `credentials: "same-origin"`; a direct-URL host joins it to its gateway
 * base URL (ui-kit `joinBaseUrl`) and adds its bearer header. Returns the raw
 * Response; non-2xx answers are turned into errors here.
 */
export type GatewayFetch = (path: string, init?: RequestInit) => Promise<Response>;
/** `GET /runs/{id}/workspace`. */
export type RunWorkspace = {
    run_id?: string;
    workspace_root: string;
    kind?: string;
    session_id?: string | null;
    exists: boolean;
    host?: {
        hostname?: string;
        caller_is_this_machine?: boolean;
    };
    /** `POST /runs/{id}/workspace/open` works (admin, same machine, folder exists). */
    open_supported?: boolean;
};
export type WorkspaceEntry = {
    name: string;
    path: string;
    type: "file" | "dir";
    size_bytes?: number;
    mtime?: string | number;
};
/** `GET /runs/{id}/workspace/files`. `hidden` counts what the deny rules kept out. */
export type WorkspaceListing = {
    path: string;
    entries: WorkspaceEntry[];
    truncated: boolean;
    hidden?: {
        outside_links?: number;
        blocked?: number;
        other?: number;
    };
};
export declare function workspaceInfoUrl(runId: string): string;
export declare function workspaceFilesUrl(runId: string, path: string): string;
export declare function workspaceContentUrl(runId: string, path: string): string;
/** `What failed (HTTP 404): <the gateway's detail>` — the gateway's own reason, never a generic failure. */
export declare function gatewayResponseError(response: Response, what: string): Promise<Error>;
/**
 * Validate a `/workspace/files` answer. A malformed or older response is an
 * error, never an empty folder.
 */
export declare function parseWorkspaceListing(data: unknown, directory: string): WorkspaceListing;
/** `GET /runs/{id}/workspace`. */
export declare function loadRunWorkspace(fetchGateway: GatewayFetch, runId: string, signal?: AbortSignal): Promise<RunWorkspace>;
/** `GET /runs/{id}/workspace/files?path=` (one folder, validated). */
export declare function listWorkspaceFolder(fetchGateway: GatewayFetch, runId: string, path: string, signal?: AbortSignal): Promise<WorkspaceListing>;
/** `GET /runs/{id}/workspace/content?path=`: one file's bytes, with the host's credentials. */
export declare function readWorkspaceFile(fetchGateway: GatewayFetch, runId: string, path: string, signal?: AbortSignal): Promise<Blob>;
/**
 * Where the run's folder is and, when it exists, one folder of it: what the
 * browser shows (the stateful `WorkspaceBrowser` loads exactly this).
 */
export declare function loadWorkspaceView(fetchGateway: GatewayFetch, runId: string, path: string, signal?: AbortSignal): Promise<{
    where: RunWorkspace;
    listing: WorkspaceListing | null;
}>;
/** Breadcrumb of a workspace-relative folder: [{label, path}], root first. */
export declare function workspaceCrumbs(path: string): Array<{
    label: string;
    path: string;
}>;
/** The parent of a workspace-relative folder ("" for the top folder). */
export declare function workspaceParent(path: string): string;
export declare function formatBytes(n: number | undefined): string;
/** Folders first, then files, each by name. */
export declare function sortWorkspaceEntries(entries: WorkspaceEntry[]): WorkspaceEntry[];
/** "2 entries hidden by the gateway's workspace rules; the list is truncated" — or "" when neither. */
export declare function workspaceHiddenNote(listing: Pick<WorkspaceListing, "hidden" | "truncated">): string;
/**
 * How a fetched file opens in a new tab. A blob URL runs with THIS app's
 * origin, so a workspace file written by a model must never execute there:
 * an HTML, SVG, XML or script file (and any other text) opens as plain text
 * (its source); a type a tab cannot show safely is downloaded instead.
 */
export declare function tabOpenPlan(contentType: string): {
    mode: "open";
    type: string;
} | {
    mode: "download";
};
/**
 * Hand fetched bytes to the user: "open" shows them in a new tab when
 * `tabOpenPlan` allows it (active content as its source text), otherwise, and
 * for "download", saves them under `name`.
 */
export declare function deliverBlob(blob: Blob, name: string, mode: "open" | "download"): void;
/**
 * Open (or download) a file the gateway links in its data — a run's ledger
 * JSON, an artifact's content URL — through the host's credentials. The
 * server's gateway-rooted URL is mapped to the relative path the app's proxy
 * or base URL serves (ui-kit `gatewayResourcePath`; anything else throws),
 * fetched with `fetchGateway`, and shown with the same safe rule as workspace
 * files (`tabOpenPlan`).
 */
export declare function openGatewayResource(fetchGateway: GatewayFetch, serverUrl: string, options: {
    name: string;
    mode?: "open" | "download";
    signal?: AbortSignal;
}): Promise<void>;
/** The last segment of a path ("/srv/ws/run-1" → "run-1"); the whole path when it has none. */
export declare function workspaceShortName(root: string): string;
/** "Open folder" acts on the gateway machine: offered only to a browser on that machine, where the gateway can open folders. */
export declare function workspaceCanOpenFolder(where: RunWorkspace | null | undefined): boolean;
export type WorkspaceBrowserProps = {
    /** The host's gateway request (credentials included). */
    fetchGateway: GatewayFetch;
    /** A run whose workspace is the folder to browse (an automation's id is its controller run). */
    runId: string;
    /** "Automation files", "Discussion files", … */
    title: string;
    /** One line under the title (e.g. "Mounted read-only for the discussion"). */
    note?: string;
    onClose?: () => void;
    /**
     * Select a file instead of previewing it here (a host with its own
     * preview). Without it, a click opens the shared `FileViewer` in place.
     */
    onSelectFile?: (entry: WorkspaceEntry) => void;
    selectedPath?: string;
    /** Changes whenever the host knows files changed (e.g. a run finished): the folder is re-listed. */
    refreshKey?: string | number;
    className?: string;
    /** Extra actions in the preview header for a file (e.g. AbstractCode's "Attach"). */
    fileActions?: (entry: WorkspaceEntry) => React.ReactNode;
    /**
     * Open the folder on the gateway machine (`POST /runs/{id}/workspace/open`
     * with the host's CSRF rules). Offered only when `workspaceCanOpenFolder`.
     */
    onOpenFolder?: () => Promise<void>;
    /** Copy text (default: `navigator.clipboard.writeText`). Returns success. */
    copyText?: (text: string) => Promise<boolean>;
    /** "Now" for relative dates (default Date.now() per render). */
    nowMs?: number;
};
/** Stateful browser: loads where the folder is and one level at a time; previews a file in place. */
export declare function WorkspaceBrowser(props: WorkspaceBrowserProps): React.ReactElement;
export type WorkspaceBrowserViewProps = {
    title: string;
    note?: string;
    where: RunWorkspace | null;
    path: string;
    listing: WorkspaceListing | null;
    error: string;
    /** A one-line outcome ("Path copied."). */
    notice?: string;
    loading: boolean;
    fileBusy: string;
    selectedPath?: string;
    className?: string;
    /** "Now" for the rows' relative dates (deterministic in checks). */
    nowMs?: number;
    onNavigate(path: string): void;
    onRefresh(): void;
    /** The row's download icon. `mode` is always "download" (0.3.0: no "Open" button). */
    onFile?(entry: WorkspaceEntry, mode: "download"): void;
    /** A click on the file name (the preview). */
    onSelectFile?(entry: WorkspaceEntry): void;
    onClose?: () => void;
    onCopyPath?: () => void;
    onOpenFolder?: () => void;
    openingFolder?: boolean;
    /** Shown instead of the list (a file preview); its close returns to the list. */
    preview?: React.ReactNode;
};
/** The hook-free view (checks render it in any state). */
export declare function WorkspaceBrowserView(p: WorkspaceBrowserViewProps): React.ReactElement;
//# sourceMappingURL=workspace_browser.d.ts.map