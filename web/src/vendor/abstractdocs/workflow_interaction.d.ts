import React from "react";
import type { PublicApprovalRequest } from "./public_approval.js";
/**
 * The ONE wording set for questions and approvals (ADR 0001 §5, backlog 0032).
 * A tool approval offers exactly three decisions (operator ruling 2026-11-07:
 * "Deny, Allow (this tool), Allow All (ALL tools). but the scope is ONLY FOR THIS
 * SESSION"): Deny refuses this request; Allow allows the requested tool for the rest
 * of this session; Allow All allows every tool for the rest of this session. None of
 * them changes the app's default tool settings. A dismissal ("Decide later") defers,
 * never denies. Hosts relabel through props only when the job itself differs.
 */
export declare const WORKFLOW_INTERACTION_LABELS: {
    readonly deny: "Deny";
    readonly allow: "Allow";
    readonly allowAll: "Allow All";
    /** Tooltips of the two allow buttons: what each one reaches. */
    readonly allowTitle: (tools: string) => string;
    readonly allowAllTitle: "Allow every tool for the rest of this session";
    /** No session grant here (the host did not ask for one, or the gateway cannot keep it). */
    readonly allowThisRequestNote: "Allow covers this request only.";
    readonly noSessionGrantNote: "This gateway cannot keep a choice for the session, so Allow covers this request only.";
    readonly decideLater: "Decide later";
    readonly submit: "Submit";
    readonly skip: "Continue without answering";
    readonly keepWaiting: "Keep waiting";
    readonly sendEvent: "Send event";
};
/** A value supplied by a user-facing workflow interaction. */
export type WorkflowInteractionChoice = {
    id: string;
    label: string;
    description?: string;
    disabled?: boolean;
};
type WorkflowInteractionBase = {
    /** Stable identifier from the host's workflow state. */
    id: string;
    /** Short label shown above the interaction. */
    title?: string;
    /** Supporting context; never interpreted as transport data by this package. */
    description?: React.ReactNode;
};
export type WorkflowAskUserInteraction = WorkflowInteractionBase & {
    kind: "ask-user";
    prompt: React.ReactNode;
    /** Rendered as buttons; a click answers with the choice id. */
    choices?: WorkflowInteractionChoice[];
    /** Defaults to true. Set false for a choice-only question. */
    allowFreeText?: boolean;
    freeTextPlaceholder?: string;
    submitLabel?: string;
    /** The host persists or forwards the answer. */
    onSubmit: (answer: string) => void | Promise<unknown>;
    /** "Continue without answering": the run resumes with an empty answer.
     * Offered only when the host injects it. */
    onSkip?: () => void | Promise<unknown>;
    skipLabel?: string;
    /** "Keep waiting": close/dismiss without answering. The run stays parked;
     * nothing is sent. Offered only when the host injects it. */
    onDefer?: () => void | Promise<unknown>;
    deferLabel?: string;
};
export type WorkflowToolApprovalInteraction = WorkflowInteractionBase & {
    kind: "tool-approval";
    toolName: string;
    /** Ordinary action/targets and an explicitly batch-bound public explanation. */
    publicRequest?: PublicApprovalRequest;
    /** Human-readable detail, such as a redacted argument summary. */
    detail?: React.ReactNode;
    /** Default "Allow". */
    approveLabel?: string;
    /** Tooltip of Allow (what it reaches). */
    approveTitle?: string;
    /** Default "Deny". */
    denyLabel?: string;
    /** "Allow": the requested tool(s), for the rest of this session when the host keeps a
     * session grant (`presentInteraction` with `sessionPolicy`), else this request only. */
    onApprove: () => void | Promise<unknown>;
    /** "Deny": refuses this request. */
    onDeny: () => void | Promise<unknown>;
    /** "Allow All": every tool, for the rest of this session. Offered only when injected. */
    onApproveAll?: () => void | Promise<unknown>;
    approveAllLabel?: string;
    /** Tooltip of Allow All (what it reaches). */
    approveAllTitle?: string;
    /** "Decide later": dismiss without deciding. A dismissal is never a deny:
     * nothing is sent and the run keeps waiting. Offered only when injected. */
    onDefer?: () => void | Promise<unknown>;
    deferLabel?: string;
    /** One short line under the decisions, only when Allow cannot reach the session
     * (e.g. `WORKFLOW_INTERACTION_LABELS.noSessionGrantNote`). */
    scopeNote?: string;
    /** Tools of this batch the session's stored policy denies: the gateway refuses them even if allowed. */
    deniedNote?: string;
};
export type WorkflowEventWaitInteraction = WorkflowInteractionBase & {
    kind: "event-wait";
    eventName?: string;
    prompt: React.ReactNode;
    payloadLabel?: string;
    payloadPlaceholder?: string;
    initialPayload?: string;
    sendLabel?: string;
    /** The host decides how this payload resumes the waiting workflow. */
    onSend: (payload: string) => void | Promise<unknown>;
};
/**
 * A presentation-only workflow pause. The host owns routing, persistence,
 * and resume protocols; this union only describes the user decision to show.
 */
export type WorkflowInteraction = WorkflowAskUserInteraction | WorkflowToolApprovalInteraction | WorkflowEventWaitInteraction;
export type WorkflowInteractionPanelProps = {
    interaction: WorkflowInteraction;
    disabled?: boolean;
    onError?: (error: unknown) => void;
    /**
     * `"panel"` (default): the full panel under a chat transcript.
     * `"card"`: a compact card for served-state lists (a "Needs you" board, an
     * inbox): same decisions and callbacks, detail folded behind "Review".
     * `"conversation"`: public action/targets/purpose with labeled decision icons;
     * technical arguments and standing policy choices stay in the host's detailed view.
     */
    variant?: "panel" | "card" | "conversation";
    /** Switch the host to its existing technical view; this never submits a decision. */
    onReviewTechnical?: () => void;
};
/** Renders a single workflow wait without taking ownership of its transport. */
export declare function WorkflowInteractionPanel(props: WorkflowInteractionPanelProps): React.ReactElement;
export default WorkflowInteractionPanel;
//# sourceMappingURL=workflow_interaction.d.ts.map