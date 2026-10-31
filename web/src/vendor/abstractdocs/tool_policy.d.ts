/** Why a tool call ran without asking, or was refused without asking. */
export type WorkflowToolPolicyProvenance = {
    decision: "auto_approved" | "denied";
    /** `"session_policy"` (contract v1). */
    source?: string;
    /** The selector that covered the call (`"tool"`, `"kind:web"`, `"all"`). */
    matched?: string;
    revision?: number;
    /** Who set the policy (`set_by.user_id`, else `set_by.client`). */
    setBy?: string;
    setAt?: string;
};
type Rec = Record<string, unknown>;
/** The decision carried by an `abstract.tool_policy_decision` payload, or null when it is not one. */
export declare function toolPolicyDecision(payload: Rec | null): {
    provenance: WorkflowToolPolicyProvenance;
    calls: {
        callId: string;
        name: string;
        matched?: string;
    }[];
} | null;
/** "Allowed by this chat's policy (set by admin at Oct 27, 2026, 10:00)" / "Denied by this chat's policy".
 * One noun for the scope across the kit (ADR 0001 §5): "chat". */
export declare function toolPolicyDecisionText(provenance: WorkflowToolPolicyProvenance): string;
/** "Not covered: send_email (not authorized); nope (unknown kind)" from a write's `clamped` list ("" when empty). */
export declare function sessionPolicyClampedText(clamped: readonly {
    selector?: string;
    name?: string;
    reason?: string;
}[] | null | undefined): string;
export {};
//# sourceMappingURL=tool_policy.d.ts.map