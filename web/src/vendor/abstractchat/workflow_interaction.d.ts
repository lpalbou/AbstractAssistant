import React from "react";
import type { PublicApprovalRequest } from "./public_approval.js";
/**
 * The ONE wording set for questions and approvals (ADR 0001 §5, backlog 0032).
 * The native AbstractAssistant (Qt approval sheet, iPhone inbox) is the
 * reference for the decision model: deny / allow once / allow for this chat /
 * allow all enabled tools, and a dismissal that defers, never denies. Hosts
 * relabel through props only when the job itself differs.
 */
export declare const WORKFLOW_INTERACTION_LABELS: {
    readonly deny: "Deny";
    readonly allowOnce: "Allow once";
    readonly allowForChat: "Allow for this chat";
    readonly allowAll: "Allow all enabled tools";
    /** Approve one toolset (a `GET discovery/tools` row's `toolset`) for the conversation. */
    readonly allowKindForChat: (toolset: string) => string;
    /** The labeled line when the gateway cannot store conversation policies (no silent hedge). */
    /** The local, run-scoped grant (no gateway chat policy): says what it does. */
    readonly allowForRun: "Allow for this run";
    readonly localChatPolicyNote: "Allowed for this chat in this browser only — the gateway cannot store chat policies.";
    readonly localRunPolicyNote: "Allowed until this run ends, in this browser only — the gateway cannot store chat policies.";
    /** Deny for the chat (session policy, gateway mode); offered under "More". */
    readonly denyToolForChat: (tool: string) => string;
    readonly denyKindForChat: (toolset: string) => string;
    /** What a deny reaches, stated before the click and in its confirmation (contract §4.3). */
    readonly denyForChatNote: "Always deny applies to every run of this chat, automations and runs that read other people's text included, until the policy is reset; a request shown before it is refused even if approved later.";
    /** No `scope` was served: said so, never composed. */
    readonly noScopeNote: "The gateway did not say where this grant applies.";
    /** The capability read failed: no chat grant is offered. */
    readonly unavailablePolicyNote: (reason: string) => string;
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
/**
 * A host-owned "remember this decision" checkbox (per tool). The host supplies
 * the label because only it knows where the choice is stored ("Always allow
 * write_file in this browser"); the kit never asserts a scope on its own.
 */
export type WorkflowInteractionRemember = {
    label: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
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
    /** Default "Allow once". */
    approveLabel?: string;
    /** Default "Deny". */
    denyLabel?: string;
    /** "Allow once": this batch only. */
    onApprove: () => void | Promise<unknown>;
    onDeny: () => void | Promise<unknown>;
    /** "Allow for this chat": approves this batch and auto-approves the enabled
     * tools for the rest of this conversation. Offered only when injected. */
    onApproveForSession?: () => void | Promise<unknown>;
    approveForSessionLabel?: string;
    /** Scope sentence for the session grant: in the "What the broader choices allow"
     * disclosure and the broad buttons' tooltips when `broadScopeSummary` is given, else
     * rendered open under the decisions. */
    approveForSessionDescription?: string;
    /** One always-visible line under the decisions saying what the broad grants reach (and
     * what keeps asking); with it, the full scope sentences move into one disclosure. */
    broadScopeSummary?: string;
    /** "Allow all enabled tools": the broader standing policy. Host must
     * describe its exact scope (`approveAllDescription`): open, or in the disclosure when
     * `broadScopeSummary` is given. */
    onApproveAll?: () => void | Promise<unknown>;
    approveAllLabel?: string;
    approveAllDescription?: string;
    /** "Decide later": dismiss without deciding. A dismissal is never a deny:
     * nothing is sent and the run keeps waiting. Offered only when injected. */
    onDefer?: () => void | Promise<unknown>;
    deferLabel?: string;
    /** Per-tool "remember" checkbox, owned and worded by the host. */
    remember?: WorkflowInteractionRemember;
    /** Why the broad grants (for this chat / all enabled tools) cannot be
     * offered for this batch. They render disabled with this reason visible. */
    disabledReason?: string;
    /** "Allow all <toolset> tools for this chat", one per toolset in the batch (session policy, gateway mode). */
    approveKinds?: {
        kind: string;
        label?: string;
        onApprove: () => void | Promise<unknown>;
    }[];
    /** A labeled scope line under the decisions, e.g. `WORKFLOW_INTERACTION_LABELS.localChatPolicyNote`. */
    scopeNote?: string;
    /** What the conversation's policy does not cover ("Not covered: send_email (not authorized)"). */
    notCovered?: string;
    /** "Always deny … in this chat" decisions (session policy), under "More" with `denyForChatNote`. */
    denyOptions?: {
        key: string;
        label: string;
        onDeny: () => void | Promise<unknown>;
    }[];
    /** Tools of this batch the chat's policy denies: the gateway refuses them even if allowed once. */
    deniedNote?: string;
    /** One line about the chat's stored policy (counts + where it applies, as served). */
    policySummary?: string;
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