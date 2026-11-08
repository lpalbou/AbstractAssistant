/**
 * `replay_view_v1` -> what the chat renders: the transcript (`ChatMessage[]`), the tool rows,
 * the pending interaction, the status. Pure: no fetch, no state. `WorkflowSessionController`
 * uses it when the gateway serves the replay view; hosts that hold a view themselves can call
 * it directly.
 *
 * Mapping (panel-chat README "Messages from the replay view"):
 * - `messages[]` -> `ChatMessage` (`id`, `runId`, `kind`, `artifactIds`; `ts` = the item's time).
 *   A `final` that `repeats` an earlier answer is shown once (the answer carries the turn's
 *   statistics). The open question's own message is not repeated above its card.
 * - `activities[]` of kind `tool` -> one tool row per call (`ToolActivityGroup`), statuses as
 *   served (`denied` shows as a failed call with its reason); kind `tool_policy` -> the
 *   "Tool policy" line. Other kinds (llm, subworkflow, timer, answer, event_wait) are not
 *   transcript items.
 * - `interaction` -> a `WorkflowWaitInteraction` carrying the view's `command` (answering goes
 *   through `POST commands` with it).
 */
import type { ChatMessage } from "./chat_message_card.js";
import type { WorkflowStatistics, WorkflowToolActivity } from "./workflow_evidence.js";
import type { WorkflowWaitInteraction } from "./workflow_runtime.js";
import { type ReplayView, type ReplayViewActivity, type ReplayViewInteraction } from "./replay_view.js";
/**
 * The served interaction as a raw runtime wait (same control, same target). `command` and
 * `kind` ride along: an `event` interaction is answered with its resume command, never by
 * re-deriving an event route.
 */
export declare function replayInteractionWait(interaction: ReplayViewInteraction): WorkflowWaitInteraction;
/** One tool row per call of a `tool` activity. */
export declare function replayToolActivities(activity: ReplayViewActivity): WorkflowToolActivity[];
/** The transcript row of a tool call (the controller's own shape, shared). */
export declare function toolActivityMessage(tool: WorkflowToolActivity): ChatMessage;
/** The turn's statistics from the view: `usage`, the tool calls, the files they changed, the span of its activities. */
export declare function replayStatistics(view: ReplayView): WorkflowStatistics;
export type ReplayProjection = {
    /** Transcript in the view's order: messages, tool rows and policy lines interleaved. */
    messages: ChatMessage[];
    /** Every tool row (also inside `messages`), by id. */
    tools: WorkflowToolActivity[];
    interaction: WorkflowWaitInteraction | null;
    status: string;
    displayStatus: string;
    /** `${run_id}:${step_id}` of model calls still running (Stop evidence). */
    openLlmCalls: string[];
    /** `${run_id}:${step_id}` of model calls that ended (their live text is replaced). */
    endedLlmCalls: string[];
    /** Runs of the tree and their status. */
    runStatus: Map<string, string>;
    statistics: WorkflowStatistics;
};
/**
 * An open event wait the view lists as a machine `signal` (runtime replay `wait_kind`: an event
 * wait with no prompt and no choices is not person-facing, so `view.interaction` is null), as
 * the raw runtime wait it is: `reason: "event"` on its canonical `evt:` key. The conversation then
 * reads "Waiting for an event" (never "Working") and the host can still deliver that event by hand
 * (`presentInteraction` resolves its route from the key and the run, and no `command` is
 * invented). Only `evt:` keys: other signals carry no event to deliver.
 */
export declare function replaySignalWait(view: ReplayView): WorkflowWaitInteraction | null;
/** Project a whole view. */
export declare function projectReplayView(view: ReplayView): ReplayProjection;
//# sourceMappingURL=replay_view_projection.d.ts.map