import React from "react";
import type { SessionReadClient } from "./session_read_client.js";
import { type SessionReceipt } from "./session_activity.js";
/** With a client: Gateway-owned receipts. Without one: explicitly browser-local compatibility mode. */
export declare function useSessionReads(scope: string, observed?: readonly SessionReceipt[], client?: SessionReadClient): {
    markRead: (p: SessionReceipt) => void;
    refresh: () => Promise<void>;
    isUnread: (p: SessionReceipt) => boolean;
    error: string;
    loading: boolean;
};
/** Mount after loaded content; selection and background loads cannot acknowledge it. */
export declare function SessionReadMarker(p: {
    receipt: SessionReceipt;
    enabled: boolean;
    ownerKey?: string;
    relatedReceipts?: readonly SessionReceipt[];
    onRead: (p: SessionReceipt) => void;
}): React.ReactElement;
//# sourceMappingURL=session_reads.d.ts.map