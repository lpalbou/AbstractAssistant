import type { ServerRecord, WorkflowRecord, WorkflowWaitInteraction } from "./workflow_runtime.js";
export type WorkflowEventScope = "session" | "workflow" | "run" | "global";
export type WorkflowEventTarget = {
    name: string;
    scope: WorkflowEventScope;
    scopeId: string;
    sessionId?: string;
    workflowId?: string;
    runId?: string;
};
export type WorkflowEventTargetResolution = {
    target: WorkflowEventTarget;
    error?: never;
} | {
    target: null;
    error: string;
};
/**
 * Resolves an event target only from the exact durable wait key plus matching
 * wait-record evidence. Event keys intentionally permit colons in scope IDs
 * and names, so splitting them is unsafe. The result is suitable to hand to
 * an emit-event transport; a failure is deliberately explicit and fail-closed.
 */
export declare function resolveWorkflowEventTarget(raw: WorkflowWaitInteraction | null, records?: WorkflowRecord[], currentRun?: ServerRecord | null): WorkflowEventTargetResolution;
//# sourceMappingURL=event_target.d.ts.map