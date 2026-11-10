import { type WorkflowInteraction } from "./workflow_interaction.js";
import type { ServerRecord, WorkflowRecord, WorkflowSessionController, WorkflowWaitInteraction } from "./workflow_runtime.js";
import type { ReplayViewInteraction } from "./replay_view.js";
import { replayInteractionWait } from "./replay_view_projection.js";
/**
 * The served, tree-resolved pending interaction of the replay view
 * (`replay_view_v1.interaction`: the newest person-facing open wait in the
 * run tree, with a ready `command`). `WorkflowSessionController` reads it from
 * `GET runs/{id}/view` and its stream when the host transport provides
 * `replayView` (see `replay_view.ts`); `presentInteraction` accepts it as well
 * as a raw wait. Shape as written by `ReplayView._interaction_of`
 * (abstractruntime 0.15.0 `replay/view.py`): `details` has `tool_calls`
 * stripped (they are top-level).
 */
export type ReplayInteraction = ReplayViewInteraction;
/** True for a `replay_view_v1.interaction` (it has `run_id` + `wait_key`, a raw wait has `runId` + `wait`). */
export declare function isReplayInteraction(value: unknown): value is ReplayInteraction;
/** The raw runtime wait a replay interaction stands for (same control, same target). */
export { replayInteractionWait };
export type PresentInteractionOptions = {
    /** The session's records: an event wait is routed from them (`resolveWorkflowEventTarget`). */
    records?: WorkflowRecord[];
    /** The run the wait belongs to, when the host has it. */
    currentRun?: ServerRecord | null;
    /** "Decide later" / "Keep waiting": the host dismisses the control. Nothing is sent. */
    onDefer?: () => void | Promise<unknown>;
    /** Offer "Continue without answering" on a question: resumes with an empty answer. */
    allowSkip?: boolean;
    /**
     * A tool approval offers exactly Deny, Allow and Allow All (operator ruling 2026-11-07).
     * `sessionPolicy: true` makes Allow and Allow All last for the rest of this session, on the
     * gateway's session tool policy (contract v1). The MODE is the controller's
     * (`controller.sessionPolicyStatus()`), never a host prop, so the card always does what it says:
     * - `"gateway"`: Allow writes `{approve:{tools:[<this request's tools>]}}`, Allow All writes
     *   `{approve:{all:true}}`, each THEN answers the shown wait. Nothing else is written: never
     *   the app's default tool settings.
     * - `"local-fallback"` / `"unavailable"`: no session grant exists; Allow answers this request
     *   only, one line says so, and Allow All is not offered.
     * Without it (a host with no conversation session, e.g. an automation's discussion: the
     * session grant never reaches automation runs), Allow answers this request only, said in one
     * line. Re-present on every snapshot change (the mode can change).
     */
    sessionPolicy?: boolean;
};
/** The controller methods the controls call. */
export type InteractionController = Pick<WorkflowSessionController, "approve" | "resume" | "emitEvent"> & Partial<Pick<WorkflowSessionController, "approveToolsForSession" | "approveAllForSession" | "sessionPolicyStatus" | "answerEvent">>;
/**
 * Converts a runtime wait into a control, or null when the wait is not one a
 * person answers here (e.g. a subworkflow wait: never a question).
 */
export declare function presentInteraction(input: WorkflowWaitInteraction | ReplayInteraction | null, controller: InteractionController, options?: PresentInteractionOptions): WorkflowInteraction | null;
//# sourceMappingURL=present_interaction.d.ts.map