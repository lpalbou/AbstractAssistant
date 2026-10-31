import React from "react";
import { type SessionReceipt } from "./session_activity.js";
/** Browser-local, account-scoped receipts shared by clients on this origin. No Gateway writes. */
export declare function useSessionReads(scope: string, observed?: readonly SessionReceipt[]): {
    isUnread: (p: SessionReceipt) => boolean;
    markRead: (p: SessionReceipt) => void;
    error: string;
};
/** Mount after loaded content, normally in ChatMessageCard.renderFooter.
 * A selected row or background subscription cannot acknowledge content. */
export declare function SessionReadMarker(p: {
    receipt: SessionReceipt;
    enabled: boolean;
    ownerKey?: string;
    onRead: (p: SessionReceipt) => void;
}): React.ReactElement;
//# sourceMappingURL=session_reads.d.ts.map