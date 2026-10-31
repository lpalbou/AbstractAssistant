/**
 * Pure helpers behind WorkflowChat's drag-and-drop and paste-to-attach.
 *
 * Nothing here touches React or the document: every function takes the
 * browser object it inspects (a DataTransfer's `types`/`items`/`files`, a
 * clipboard) as a plain argument so the rules are testable in Node.
 */
/** A DataTransfer `types` value (array in modern engines, DOMStringList in old ones). */
export type DragTypes = ArrayLike<string> | null | undefined;
type ItemLike = {
    kind?: string;
    type?: string;
    getAsFile?: () => File | null;
    webkitGetAsEntry?: () => {
        isDirectory?: boolean;
        name?: string;
    } | null;
};
/** The DataTransfer surface the helpers read. */
export type TransferLike = {
    types?: DragTypes;
    items?: ArrayLike<ItemLike> | null;
    files?: ArrayLike<File> | null;
};
/** True only for OS file drags. Text selections and links carry no "Files" type. */
export declare function dragCarriesFiles(types: DragTypes): boolean;
/**
 * How many files a drag carries, when the engine says so before the drop.
 * Chromium and Firefox expose `items` (kind "file") during dragenter/dragover;
 * Safari may expose nothing. `null` means unknown — never guess a number.
 */
export declare function draggedFileCount(transfer: TransferLike | null | undefined): number | null;
/** The drop zone's headline, pluralised with the count when it is known. */
export declare function dropZoneLabel(count: number | null): string;
export type DroppedFiles = {
    files: File[];
    folders: string[];
};
/**
 * Split a drop into uploadable files and folders. A folder arrives as a
 * "file" item whose entry is a directory; uploading it would send an empty or
 * failing body, so it is reported instead (never silently skipped).
 */
export declare function droppedFiles(transfer: TransferLike | null | undefined): DroppedFiles;
/** The message shown when a drop contained folders. */
export declare function folderRefusal(folders: string[]): string;
/**
 * A readable name for a pasted file. Browsers name every clipboard screenshot
 * "image.png"; three of those in one message are indistinguishable, so a
 * generic (or empty) name becomes "Pasted image 2026-09-23 at 14.05.09.png".
 * A real file name (a file copied in Finder) is kept.
 */
export declare function pastedFileName(name: string, type: string, now: Date): string;
/**
 * Files to attach from a paste, or [] to let the paste behave as text.
 *
 * Rich documents (Word, Excel, Pages) put text/plain AND text/html on the
 * clipboard next to a rendered picture of the selection: that paste is text.
 * A screenshot (Files only), an image copied from a page (text/html + Files)
 * or a file copied in Finder (text/plain name + Files) is an attachment.
 */
export declare function pastedFiles(clipboard: TransferLike | null | undefined, now?: Date): File[];
/**
 * Tracks whether a file drag is over the window.
 *
 * dragenter/dragleave fire for EVERY element the pointer crosses (enter on
 * the new element, then leave on the old), so a boolean flickers off on each
 * child boundary. A depth counter only reaches zero when the drag has really
 * left. Engines drop a dragleave now and then (fast exits, Escape), so
 * `stale` also retires a drag that has gone quiet: while a drag is over the
 * page the engine repeats dragover every few hundred milliseconds even when
 * the pointer rests.
 */
export declare class DragPresence {
    readonly staleMs: number;
    depth: number;
    lastSeen: number;
    constructor(staleMs?: number);
    enter(now: number): void;
    over(now: number): void;
    /** Returns true while the drag is still somewhere over the window. */
    leave(now: number): boolean;
    reset(): void;
    active(now: number): boolean;
}
export {};
//# sourceMappingURL=file_drop.d.ts.map