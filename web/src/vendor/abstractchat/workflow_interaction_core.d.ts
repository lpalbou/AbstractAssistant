import type { WorkflowInteraction } from "./workflow_interaction.js";
/** Snapshot of the exact decision the user attempted. Kept separate from
 * mutable input state so retry never silently substitutes a newer value. */
export type WorkflowInteractionSubmission = {
    kind: "choice" | "free-text";
    answer: string;
} | {
    kind: "approve" | "deny" | "approve-all" | "skip";
} | {
    kind: "event";
    payload: string;
};
/** Invoke the host callback for a previously captured interaction decision. */
export declare function submitWorkflowInteraction(interaction: WorkflowInteraction, submission: WorkflowInteractionSubmission): void | Promise<unknown>;
//# sourceMappingURL=workflow_interaction_core.d.ts.map