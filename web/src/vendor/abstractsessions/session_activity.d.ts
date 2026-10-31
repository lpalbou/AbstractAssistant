/** Presentation facts only. Receipt revisions distinguish a request from its later answer. */
export type SessionContent = SessionReceipt & {
    runId: string;
    status: string;
};
export type SessionActivity = {
    revision: string;
    updatedAt: string;
    content: SessionContent[];
    needsAttention: boolean;
    working: boolean;
    toolCount?: number;
};
export declare function sessionContentRevision(runId: string, status: string): string;
export declare function sessionNeedsAttention(run: Record<string, unknown>): boolean;
export declare function sessionActivityFromRuns(body: unknown): Record<string, SessionActivity>;
/** Non-secret account identity; never include a token or token fingerprint. */
export declare function sessionReadScope(connection: {
    gateway_url?: string;
    gateway?: {
        principal?: {
            user_id?: string;
            tenant_id?: string;
            runtime_id?: string;
        };
    };
} | null | undefined): string;
export type SessionReceipt = {
    sessionId: string;
    revision: string;
    updatedAt: string;
};
export type ReceiptStorage = Pick<Storage, "getItem" | "setItem" | "removeItem" | "key" | "length">;
export declare class SessionReadStore {
    private storage;
    readonly prefix: string;
    readonly since: number;
    error: string;
    private memory;
    constructor(scope: string, storage: ReceiptStorage | null, now?: number);
    private key;
    observe(p: SessionReceipt): void;
    isUnread(p: SessionReceipt): boolean;
    markRead(p: SessionReceipt): void;
}
/** The loaded message whose footer can acknowledge a run's displayed outcome.
 * Failures/cancellations must render `outcome` before the marker: a prompt alone is insufficient. */
export declare function sessionReadTarget<T extends {
    runId?: string;
    role: string;
    live?: unknown;
    toolActivity?: unknown;
}>(messages: readonly T[], runId: string, status: string): {
    message?: T;
    outcome?: string;
};
//# sourceMappingURL=session_activity.d.ts.map