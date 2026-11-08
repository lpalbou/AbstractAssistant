import type { WorkflowSessionSnapshot } from "./workflow_runtime.js";
export type WorkflowProgress = {
    label: string;
    detail: string;
    tone: "working" | "waiting" | "success" | "error" | "neutral";
    startedAt?: string;
    toolCalls: number;
    totalTokens?: number;
};
/** Presentation from evidence, never a replacement for authoritative run state. */
export declare function workflowProgress(snapshot: Pick<WorkflowSessionSnapshot, "status" | "loading" | "connection" | "error" | "interaction" | "records" | "run" | "displayStatus"> & Partial<Pick<WorkflowSessionSnapshot, "toolApprovalGranted" | "view" | "stop">>): WorkflowProgress;
//# sourceMappingURL=workflow_progress.d.ts.map