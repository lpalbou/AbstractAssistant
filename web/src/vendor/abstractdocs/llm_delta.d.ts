/**
 * Live model-reply deltas on the gateway's run ledger stream.
 *
 * The gateway sends two extra SSE event names on `GET /runs/{id}/ledger/stream`
 * when a run streams its replies (`_runtime.stream`). They carry NO `id:`
 * line: they are volatile and never move the ledger cursor.
 *
 *   event: llm.delta      data: {kind, run_id, root_run_id, parent_run_id, node_id, call_id, seq, text, channel, snapshot}
 *   event: llm.delta_end  data: {kind, run_id, root_run_id, parent_run_id, node_id, call_id, seq, reason, detail?}
 *
 * `run_id` is the run that called the model; a stream subscribed to a root
 * run also carries its sub-runs' deltas (`parent_run_id` is null for a root).
 *
 * `call_id` is the `step_id` of the run's `llm_call` ledger step. A
 * `snapshot: true` delta (sent on subscribe/reconnect, or when the gateway
 * coalesced frames for a slow reader) carries the whole text so far for its
 * channel. The durable `llm_call` terminal record (written before the
 * `llm.delta_end`) and the run's assistant message replace the live text.
 * There is one `llm.delta_end` per model-call attempt (a retry gets a fresh
 * `call_id`), including calls that ran without streaming, so an end for a
 * call that sent no delta is normal. `reason: "unavailable"` says why a call
 * was not streamed (`detail`). `<think>` blocks are already split out by the
 * server into the `reasoning` channel. Extra fields (such as a legacy
 * `truncated`) are tolerated and ignored.
 */
export type LlmDeltaChannel = "content" | "reasoning";
export type LlmDelta = {
    kind?: "llm.delta";
    run_id: string;
    root_run_id?: string;
    /** Null (or absent) for a root run's own model call. */
    parent_run_id?: string | null;
    node_id?: string;
    call_id: string;
    seq: number;
    text: string;
    channel: LlmDeltaChannel;
    snapshot: boolean;
};
export type LlmDeltaEndReason = "completed" | "failed" | "cancelled" | "unavailable";
/** Why a call was not streamed (`reason: "unavailable"`); other strings may appear. */
export type LlmStreamUnavailableDetail = "structured_output" | "remote_core" | "provider_cannot_stream" | "sink_error" | "usage_unavailable";
export type LlmDeltaEnd = {
    kind?: "llm.delta_end";
    run_id: string;
    root_run_id?: string;
    parent_run_id?: string | null;
    node_id?: string;
    call_id: string;
    seq: number;
    reason: LlmDeltaEndReason;
    /** Present with `reason: "unavailable"`. */
    detail?: LlmStreamUnavailableDetail | string;
};
export type LlmDeltaEvent = LlmDelta | LlmDeltaEnd;
export declare const LLM_DELTA_EVENT: "llm.delta";
export declare const LLM_DELTA_END_EVENT: "llm.delta_end";
/** True for a validated `llm.delta_end` payload (as opposed to an `llm.delta`). */
export declare function isLlmDeltaEnd(event: LlmDeltaEvent): event is LlmDeltaEnd;
/**
 * Validate one delta payload (the parsed `data:` of an `llm.delta` or
 * `llm.delta_end` frame). Throws an Error naming the problem for a payload
 * that does not match the contract; it never guesses a missing field.
 */
export declare function validateLlmDeltaEvent(value: unknown, eventName?: string): LlmDeltaEvent;
/**
 * For host SSE readers: turn one received frame into a delta event, or
 * `null` when the frame is not a delta (then it is a ledger item, handled as
 * before). `data` may be the raw `data:` string or an already parsed value.
 *
 *   const delta = llmDeltaFromSse(frame.event, frame.data);
 *   if (delta) { onDelta?.(delta); continue; } // never touch the ledger cursor
 *
 * Throws for a malformed delta frame (see `validateLlmDeltaEvent`).
 */
export declare function llmDeltaFromSse(eventName: string, data: unknown): LlmDeltaEvent | null;
/** The widget's "Stream replies" choice. */
export type StreamRepliesMode = "gateway_default" | "on" | "off";
/**
 * The run-input `_runtime` entries for a `StreamRepliesMode`:
 * `"on"` → `{ stream: true }`, `"off"` → `{ stream: false }`,
 * `"gateway_default"` → `{}` (leave `_runtime.stream` unset so the gateway's
 * `agents.streaming_default` setting decides). Merge the result into the
 * `_runtime` object of the start-run input.
 */
export declare function streamRepliesRuntime(mode: StreamRepliesMode): {
    stream?: boolean;
};
/** One line explaining an `llm.delta_end` with `reason: "unavailable"`. */
export declare function describeStreamUnavailable(detail?: string): string;
//# sourceMappingURL=llm_delta.d.ts.map