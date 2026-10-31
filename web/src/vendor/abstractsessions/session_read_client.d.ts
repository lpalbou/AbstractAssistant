import type { SessionReceipt } from "./session_activity.js";
export type SessionReadEvent = {
    sequence: number;
    session_id: string;
    run_id: string;
    status: string;
    at: string;
    event_id: string;
};
export interface SessionReadClient {
    load(receipts: readonly SessionReceipt[], signal: AbortSignal): Promise<SessionReadEvent[]>;
    mark(receipts: readonly SessionReceipt[], signal: AbortSignal): Promise<SessionReadEvent[]>;
}
export declare function sessionReadIdentity(p: SessionReceipt): {
    session_id: string;
    run_id: string;
    status: string;
};
export declare function sessionReadEventReceipt(e: SessionReadEvent): SessionReceipt;
export declare const sessionReceiptKey: (p: SessionReceipt) => string;
/** Caller injects its authenticated, CSRF-aware same-origin transport. */
export declare function createSessionReadClient(fetchGateway: (path: string, init?: RequestInit) => Promise<Response>): SessionReadClient;
//# sourceMappingURL=session_read_client.d.ts.map