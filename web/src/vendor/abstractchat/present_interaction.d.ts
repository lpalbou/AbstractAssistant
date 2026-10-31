import { type WorkflowInteraction, type WorkflowInteractionRemember } from "./workflow_interaction.js";
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
    /**
     * Offer "Allow all enabled tools" on a tool approval: approves the batch,
     * then the host switches its tool policy to all (`permissions: all`).
     * Omit it and only Allow once / Deny are offered.
     */
    onPermissionsAll?: () => Promise<void>;
    /**
     * Where the "Allow all enabled tools" policy is kept, in the host's words
     * ("for this Gateway account", "in this browser"). Only the host knows; the
     * default sentence asserts no scope (backlog 0032: AbstractCode said
     * "Gateway account" over per-browser storage).
     */
    approveAllScope?: string;
    /**
     * Offer "Allow for this chat": approves this batch, then the host turns on
     * its chat-scoped grant (e.g. a session-level tool policy it applies to
     * every run of this conversation with `setToolApprovalPolicy`). The host
     * owns the scope because a chat spans several runs: the controller's own
     * `allowAllToolsForRun` ends with the run. Omit it and the button is not
     * offered.
     */
    onAllowForSession?: () => Promise<void>;
    /** Why the broad grants cannot be offered for this batch (rendered disabled, reason visible). */
    approveAllDisabledReason?: string;
    /** Host-owned per-tool "remember" checkbox for this batch's tool names. */
    remember?: (toolNames: string[]) => WorkflowInteractionRemember | null | undefined;
    /** "Decide later" / "Keep waiting": the host dismisses the control. Nothing is sent. */
    onDefer?: () => void | Promise<unknown>;
    /** Offer "Continue without answering" on a question: resumes with an empty answer. */
    allowSkip?: boolean;
    /**
     * Turn on the chat's tool policy controls (session tool policy contract v1).
     * The MODE is the controller's (`controller.sessionPolicyStatus()`), never a
     * host prop, so the controls always say what the click will do:
     * - `"gateway"`: "Allow for this chat" writes `{approve:{all:true}}` THEN answers
     *   the shown wait; each toolset of the batch gets "Allow all <toolset> tools for
     *   this chat" (`{approve:{kinds:[toolset]}}`). `toolsetOf(name)` maps a tool to the
     *   `toolset` of its `GET discovery/tools` row; a call carrying `toolset` wins; a
     *   tool with neither gets no kind button. The controller's `clamped` renders
     *   "Not covered: …".
     * - `"local-fallback"`: the host's `onAllowForSession` ("Allow for this chat",
     *   labeled browser-only), else the controller's run-scoped grant ("Allow for this
     *   run", labeled).
     * - `"unavailable"`: no chat grant; the reason is shown; Allow once still works.
     * Re-present on every snapshot change (the mode can change).
     */
    sessionPolicy?: {
        toolsetOf?: (toolName: string) => string | undefined;
        /** The person's explicit Ask tools: sent on every write so a broad approve never overrides them. */
        ask?: readonly string[];
        /** Contract `approve.max_risk_rank` for "Allow for this chat" (default: unset). */
        maxRiskRank?: number;
    };
};
/** The controller methods the controls call. */
export type InteractionController = Pick<WorkflowSessionController, "approve" | "approveWithPolicyChange" | "resume" | "emitEvent"> & Partial<Pick<WorkflowSessionController, "approveAllForSession" | "approveKindForSession" | "denyToolForSession" | "denyKindForSession" | "sessionPolicyStatus" | "answerEvent">>;
/**
 * Converts a runtime wait into a control, or null when the wait is not one a
 * person answers here (e.g. a subworkflow wait: never a question).
 */
export declare function presentInteraction(input: WorkflowWaitInteraction | ReplayInteraction | null, controller: InteractionController, options?: PresentInteractionOptions): WorkflowInteraction | null;
//# sourceMappingURL=present_interaction.d.ts.map