import { WorkflowSessionController, type WorkflowSessionSnapshot, type WorkflowTransport, type WorkflowToolApprovalPolicy } from "./workflow_runtime.js";
export type UseWorkflowSessionOptions = {
    transport: WorkflowTransport;
    runId?: string | null;
    enabled?: boolean;
    onAuthError?: (error: unknown) => void;
    clientId?: string;
    /** Stable, non-secret principal/session generation. Change it after sign
     * in/out or account switching; never pass a bearer token here. */
    authScopeKey?: string | number | null;
    toolApprovalPolicy?: WorkflowToolApprovalPolicy | null;
    /** See `WorkflowSessionControllerOptions.liveRenderIntervalMs` (default 60 ms). */
    liveRenderIntervalMs?: number;
};
/** React lifecycle wrapper.  The controller remains independently testable. */
export type WorkflowSessionHook = {
    controller: WorkflowSessionController;
    snapshot: WorkflowSessionSnapshot;
};
export declare function useWorkflowSession(options: UseWorkflowSessionOptions): WorkflowSessionHook;
//# sourceMappingURL=use_workflow_session.d.ts.map