/** One chip in the composer. */
export type ComposerAttachmentState = "queued" | "uploading" | "attached" | "refused" | "failed";
export type ComposerAttachment = {
    id: string;
    name: string;
    size?: number;
    state: ComposerAttachmentState;
    /** Host-supplied preview (blob:/data:/http(s)/same-origin); never fetched by the chip itself beyond an <img>. */
    thumbnailUrl?: string;
    /** Why the file is not attached (refused/failed), in words. */
    error?: string;
};
/** Uploads in flight at once: parallel enough to be quick, few enough to read. */
export declare const UPLOAD_CONCURRENCY = 3;
/**
 * The refusal for a file over the gateway's limit, or null when it may be
 * uploaded (no limit published = the gateway decides). The message always
 * carries both numbers; when rounding would print the same figure twice it
 * falls back to exact byte counts.
 */
export declare function uploadRefusal(file: {
    name: string;
    size: number;
}, maxBytes: number | undefined): string | null;
/** The gateway's reason for a failed upload, as the chip shows it (client call-name prefixes dropped). */
export declare function uploadFailure(message: string): string;
/** Runs `worker` over `items` with at most `limit` in flight, in order. */
export declare function runBounded<T>(items: readonly T[], limit: number, worker: (item: T) => Promise<void>): Promise<void>;
/** The screen-reader summary after a batch settles ("2 files attached"). */
export declare function uploadAnnouncement(attached: number, notAttached: number): string;
/**
 * Why a new turn cannot start yet, or null. A chip the user can still see
 * must never be left behind silently by a send: uploads in flight are
 * awaited, and a refused/failed file must be retried or removed first.
 * `WorkflowChat` applies this to `attachmentItems` before calling `onSend`.
 */
export declare function unattachedSendBlock(items: readonly Pick<ComposerAttachment, "name" | "state">[]): string | null;
export type UseAttachmentUploadsOptions<T> = {
    /** The host's upload (e.g. `POST attachments/upload`); resolves to the reference the next run carries. */
    upload: (file: File) => Promise<T>;
    /** The gateway's published limit (`maxAttachmentBytes`); unset = the gateway decides. */
    maxBytes?: number;
    /** Uploads in flight at once (default 3). */
    concurrency?: number;
    /** Optional preview for a chip (e.g. an object URL for images). The host owns
     * the URL: revoke it when the chip is removed or the queue is cleared. */
    thumbnail?: (file: File) => string | undefined;
};
export type AttachmentUploads<T> = {
    /** Chips for `WorkflowChat.attachmentItems`. */
    items: ComposerAttachment[];
    /** The references of attached files, in order: what the next run carries. */
    attached: T[];
    /** Queue files (refused ones never reach the network). Returns their chip ids. */
    add: (files: File[]) => string[];
    remove: (id: string) => void;
    retry: (id: string) => void;
    /** Drop every chip (after a send, or when the session changes); late uploads are ignored. */
    clear: () => void;
    /** `unattachedSendBlock(items)`. */
    sendBlock: string | null;
    /** Screen-reader summary of the last settled batch. */
    announcement: string;
};
/** The composer upload queue as a hook: chips, bounded uploads, retry, remove. */
export declare function useAttachmentUploads<T>(options: UseAttachmentUploadsOptions<T>): AttachmentUploads<T>;
//# sourceMappingURL=attachment_uploads.d.ts.map