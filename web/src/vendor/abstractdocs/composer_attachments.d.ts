import React from "react";
import type { ComposerAttachment } from "./attachment_uploads.js";
export type ComposerAttachmentChipsProps = {
    items: ComposerAttachment[];
    onRemove?: (id: string) => void;
    /** Offered on a failed chip only. */
    onRetry?: (id: string) => void;
    disabled?: boolean;
};
/**
 * The composer's attachment chips (backlog 0030/0031): one chip per file with
 * its state in words ("Waiting", "Uploading", attached with its size, or the
 * refusal/failure reason), Retry on a failed chip and Remove on every chip
 * when the host offers them. Every chip is focusable and names its state for
 * screen readers.
 */
export declare function ComposerAttachmentChips(props: ComposerAttachmentChipsProps): React.ReactElement | null;
export default ComposerAttachmentChips;
//# sourceMappingURL=composer_attachments.d.ts.map