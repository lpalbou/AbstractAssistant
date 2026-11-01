/** Public permission language describes the requested action, never its private reasoning. */
export type PublicApprovalRequest = {
    question: string;
    actions: {
        kind: "page" | "search" | "read" | "write" | "edit" | "folder" | "unknown";
        label: string;
        target: string;
    }[];
    explanation?: {
        text: string;
        updateId: string;
    };
    reviewRequired: boolean;
};
type Call = {
    name?: unknown;
    arguments?: unknown;
    call_id?: unknown;
    id?: unknown;
};
/** Built only from concrete requested actions and an explicitly bound public message. */
export declare function publicApprovalRequest(calls: readonly Call[], value: unknown, runId: string): PublicApprovalRequest;
export {};
//# sourceMappingURL=public_approval.d.ts.map