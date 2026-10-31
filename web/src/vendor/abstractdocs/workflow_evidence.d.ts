import type { WorkflowRecord } from "./workflow_runtime.js";
import { type ToolSandbox } from "./sandbox_line.js";
import type { WorkflowToolPolicyProvenance } from "./tool_policy.js";
export type WorkflowToolActivity = {
    id: string;
    runId: string;
    name: string;
    arguments?: unknown;
    output?: unknown;
    status: "running" | "waiting" | "completed" | "failed";
    success?: boolean;
    error?: string;
    startedAt?: string;
    endedAt?: string;
    /** The command sandbox this call ran under (process-spawning tools), from its result. */
    sandbox?: ToolSandbox;
    /** The model's call id (`call_id`), when the record carries one. */
    callId?: string;
    /** Set when the conversation's tool policy decided this call (`abstract.tool_policy_decision`). */
    policy?: WorkflowToolPolicyProvenance;
    /** The call waited for the person's decision, so `startedAt`..`endedAt` includes that wait.
     * Replay view: `activities[].wait.kind == "tool_approval"` with an `outcome` (AbstractRuntime
     * `replay/view.py:1050-1051`). Ledger fold: the call's row was `waiting` on an approval
     * (`result.wait.details.mode == "approval_required"`, the rule of `replay/view.py:213-219`). */
    approvalWait?: boolean;
};
export type WorkflowStatistics = {
    inputTokens?: number;
    outputTokens?: number;
    totalTokens?: number;
    llmCalls: number;
    toolCalls: number;
    changedFiles: string[];
    durationMs?: number;
    /** Milliseconds inside model calls (`result.gen_time`). The rest of
     *  `durationMs` is orchestration, tools and model load. */
    genTimeMs?: number;
    /** Model calls that reported `gen_time`. */
    timedCalls?: number;
    /** Prompt-phase milliseconds: prompt tokens ÷ the provider's prompt rate.
     *  That quotient IS the provider's measured prompt time (mlx-vlm divides
     *  the whole prompt, restored tokens included, by the time to the first
     *  token), so the duration is honest even when a cache restore is in play. */
    prefillMs?: number;
    /** Token-generation (decode) seconds, same derivation. */
    decodeMs?: number;
    /** Prompt-processing speed, tokens/second, averaged over reporting calls.
     *  PROVIDER RATE: it counts every prompt token, restored ones included, so
     *  on a cache hit it overstates what was computed (defect 2026-09-22: a turn
     *  that computed 1,803 new tokens in 3.25 s read "1,813 tok/s" because 4,096
     *  restored tokens were in the numerator). Prefer `prefillNewTokensPerSecond`. */
    promptTokensPerSecond?: number;
    /** Prompt tokens actually computed in the timed prefill (fed, not restored),
     *  summed over calls that reported BOTH a prompt rate and a cache split. */
    prefillNewTokens?: number;
    /** Prefill speed over `prefillNewTokens` only: Σ fed ÷ Σ prompt time across
     *  those same calls. The honest rate whenever tokens were restored. */
    prefillNewTokensPerSecond?: number;
    /** Generation speed, tokens/second, averaged over reporting calls. */
    generationTokensPerSecond?: number;
    /** Model calls that reported a `performance` block. */
    measuredSpeedCalls?: number;
    /** Prompt tokens served from cache instead of recomputed. */
    cachedTokens?: number;
    /** Prompt tokens actually fed to the model. */
    fedTokens?: number;
    /** Model calls that reported a `prompt_cache` block. */
    measuredCacheCalls?: number;
    /** Distinct `prompt_cache.outcome` values seen (hit_restore, rebuilt, …). */
    cacheOutcomes?: string[];
    /** Calls that finished with an error. Counted from terminal rows only. */
    toolsFailed?: number;
    /** Calls still parked on a decision (approval gating) — NOT failures. */
    toolsWaiting?: number;
    /** Calls in flight. */
    toolsRunning?: number;
    /** Per-tool tally, so the chip can say WHICH tools ran and which failed.
     *  `ms` is the wall time of the batches in which this tool ran ALONE (a
     *  batch runs its calls together, so a batch shared with another tool
     *  cannot be split honestly — it is counted in `sharedBatches` instead).
     *  `errors` tallies the failure class (`error_class`) when the tool's
     *  result carried one. */
    toolBreakdown?: Record<string, {
        calls: number;
        failed: number;
        ms?: number;
        sharedBatches?: number;
        errors?: Record<string, number>;
    }>;
    /** One row per completed model call, in start order. */
    modelCalls?: WorkflowModelCall[];
    /** Distinct model ids / providers that served the turn's calls. */
    models?: string[];
    providers?: string[];
    /** Reasoning/thinking tokens, when the usage block carries them. */
    reasoningTokens?: number;
    /** Distinct prompt-cache backends (`prompt_cache.backend`). */
    cacheBackends?: string[];
    /** Σ measured time-to-first-token (`abstract.progress` `ttft_s`). */
    ttftMs?: number;
    /** Calls whose TTFT was measured (the rest fall back to the rate quotient). */
    ttftCalls?: number;
    /** Prompt phase per call — the measured TTFT when present, else
     *  prompt tokens ÷ provider prompt rate — summed. */
    promptPhaseMs?: number;
    promptPhaseCalls?: number;
    /** Tokens actually computed (fed) in those prompt phases, and the rate
     *  over them: Σ fed ÷ Σ prompt phase, over calls that reported both. */
    promptPhaseNewTokens?: number;
    promptPhaseTokensPerSecond?: number;
    /** Generation phase per call — `gen_time` − TTFT when both were measured,
     *  else output ÷ provider generation rate — summed, with Σ output ÷ Σ
     *  phase as the rate. */
    generationPhaseMs?: number;
    generationPhaseTokens?: number;
    generationPhaseTokensPerSecond?: number;
    /** Speculative decoding (MTP / draft model), summed over reporting calls. */
    speculation?: WorkflowSpeculation;
    /** Σ wall time of the turn's finished tool batches (calls issued together
     *  share one timing). */
    toolTimeMs?: number;
    toolBatches?: number;
    /** True when at least one timed batch waited on an approval: its time
     *  includes the human, not only the tool. */
    toolTimeIncludesApproval?: boolean;
    /** The slowest finished batch. */
    slowestToolBatch?: {
        ms: number;
        calls: number;
        tools: string[];
    };
};
/** Speculative decoding for the turn (mlx-vlm `metadata.speculation`). */
export type WorkflowSpeculation = {
    /** Calls that reported a speculation block, and how many used it. */
    calls: number;
    used: number;
    modes?: string[];
    draftKinds?: string[];
    acceptedTokens?: number;
    draftedTokens?: number;
    /** Σ accepted ÷ Σ drafted. */
    acceptanceRate?: number;
    rounds?: number;
    /** Distinct `num_draft_tokens` (tokens proposed per round). */
    draftLengths?: number[];
};
/** One model call, folded from its completed `llm_call` record plus the
 *  `abstract.progress` events that share its step. */
export type WorkflowModelCall = {
    runId: string;
    stepId?: string;
    startedAt?: string;
    model?: string;
    provider?: string;
    inputTokens?: number;
    outputTokens?: number;
    totalTokens?: number;
    reasoningTokens?: number;
    cachedTokens?: number;
    fedTokens?: number;
    cacheOutcome?: string;
    cacheBackend?: string;
    genTimeMs?: number;
    /** Measured time to first token. */
    ttftMs?: number;
    /** Prompt phase: `ttftMs` when measured ("ttft"), else prompt tokens ÷
     *  provider prompt rate ("rate"). */
    promptMs?: number;
    promptSource?: "ttft" | "rate";
    /** Fed tokens ÷ prompt phase. */
    promptNewTokensPerSecond?: number;
    /** Provider rates, as reported. */
    promptTokensPerSecond?: number;
    generationTokensPerSecond?: number;
    generationMs?: number;
    speculation?: {
        mode?: string;
        used?: boolean;
        draftKind?: string;
        acceptedTokens?: number;
        draftedTokens?: number;
        acceptanceRate?: number;
        rounds?: number;
        draftLength?: number;
    };
};
export declare function foldWorkflowTools(state: Map<string, WorkflowToolActivity>, entry: WorkflowRecord): WorkflowToolActivity[];
export declare function workflowEvidence(records: WorkflowRecord[]): {
    tools: WorkflowToolActivity[];
    statistics: WorkflowStatistics;
};
export declare function historyRecords(history: unknown): WorkflowRecord[];
//# sourceMappingURL=workflow_evidence.d.ts.map