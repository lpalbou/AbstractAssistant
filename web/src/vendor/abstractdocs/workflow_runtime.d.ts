/**
 * Transport-injected durable workflow session state.
 *
 * This deliberately knows ledger shapes, but not HTTP, gateway URLs, cookies,
 * or React presentation.  Hosts supply those through WorkflowTransport.
 */
import type { ChatMessage } from "./chat_message_card.js";
import { type LlmDelta, type LlmDeltaEnd } from "./llm_delta.js";
import { type ReplayView, type ReplayViewTransport } from "./replay_view.js";
export type ServerRecord = Record<string, unknown>;
export type WorkflowRecord = {
    cursor: number;
    record: ServerRecord;
    runId: string;
};
export type GatewayCommand = {
    command_id: string;
    run_id: string;
    type: string;
    payload: Record<string, unknown>;
    client_id?: string;
};
export type WorkflowTransport = {
    getRun(runId: string, signal?: AbortSignal): Promise<ServerRecord>;
    /** Usually a RunHistoryBundle.  Other observer-shaped history values are tolerated. */
    getHistory(runId: string, signal?: AbortSignal): Promise<unknown>;
    getLedger(runId: string, after: number, signal?: AbortSignal): Promise<unknown>;
    /**
     * Resolve when the source closes; call onStep in strictly received order.
     * `onOpen` is optional for existing transports. Invoke it only after the
     * stream response is genuinely usable, never as an auth/connect intent.
     *
     * `onDelta` is optional (transports written before live replies keep
     * working; the chat then shows each reply when it is complete). A transport
     * that supports live replies dispatches every SSE frame named `llm.delta`
     * or `llm.delta_end` to `onDelta` with its parsed `data:` payload
     * (`llmDeltaFromSse(event, data)` does the name check and validation) and
     * never to `onStep`. Those frames carry no `id:` and must not move the
     * ledger cursor or the `Last-Event-ID` used to reconnect.
     */
    streamLedger(runId: string, after: number, onStep: (item: unknown) => void, signal: AbortSignal, onOpen?: () => void, onDelta?: (event: LlmDelta | LlmDeltaEnd) => void): Promise<void>;
    submitCommand(command: GatewayCommand, signal?: AbortSignal): Promise<unknown>;
    /**
     * Optional (backlog 0031): a run artifact as the chat can show it. The host
     * reads the metadata (`GET runs/{run_id}/artifacts/{artifact_id}`,
     * abstractgateway routes/gateway.py:11260: `content_type`, `size_bytes`)
     * and the bytes (`.../content`, routes/gateway.py:11293) with its own
     * credentials and returns an object URL; `chatMediaFromArtifact` turns the
     * result into a `ChatMedia`. The controller does NOT call it yet: folding
     * `$artifact` refs and generated-media ledger events into `message.media`
     * is still the host's job (see the panel-chat README).
     */
    resolveArtifact?(runId: string, artifactId: string, signal?: AbortSignal): Promise<ResolvedArtifact>;
    /**
     * Optional: the gateway's replay view (`GET runs/{id}/view` + `/view/stream`, AbstractGateway
     * >= 0.17.0; `createReplayViewTransport({ fetch })` builds it over the host's fetch). With it
     * the controller renders the conversation from the view (status, interaction, messages, tool
     * activities) and does not fold ledger records: `getHistory`/`getLedger` are not called, the
     * ledger stream is opened only for live reply text, and there is no timed `GET runs/{id}`.
     * Without it, or when the gateway answers that it has no such route (probed once per
     * transport), the ledger fold is used and the snapshot says so (`source: "ledger_fold"`,
     * `sourceReason`).
     */
    replayView?: ReplayViewTransport;
};
/**
 * Session tool policy (contract v1, 2026-10-27; abstractgateway branch
 * `feat/session-tool-policy`, routes/session_tool_policy.py:92-122:
 * GET / PUT / POST / DELETE `sessions/{session_id}/tool-policy` under the gateway API base).
 * NOT on gateway `main` yet: a host injects a client only when
 * `GET discovery/capabilities` serves `capabilities.session_tool_policy.supported === true`.
 * The same structural types are exported by ui-kit as `SessionToolPolicyClient` (HTTP client).
 */
export type SessionToolPolicyBody = {
    approve?: {
        tools?: string[];
        kinds?: string[];
        all?: boolean;
        max_risk_rank?: number;
    };
    deny?: {
        tools?: string[];
        kinds?: string[];
    };
    ask?: string[];
    client?: string;
    if_revision?: number;
};
/** One requested name the gateway did not store (contract §3: "never silently"). */
export type SessionToolPolicyClamp = {
    selector: string;
    name: string;
    reason: string;
};
/**
 * Where approve and deny apply, in the gateway's words. Served at the TOP level of every
 * tool-policy response (abstractgateway `feat/session-tool-policy` WIP
 * routes/session_tool_policy.py:104, :115, :152; the words are `SCOPE` in
 * session_tool_policy.py:226-230), as an object `{approve, deny}`. Rendered exactly as
 * served, never composed by a client.
 */
export type SessionToolPolicyScope = {
    approve?: string;
    deny?: string;
};
/** The stored, effective policy (contract §3 response `policy`). */
export type SessionToolPolicy = {
    version: number;
    session_id: string;
    revision: number;
    approve: Record<string, string>;
    deny: Record<string, string>;
    ask: string[];
    request?: unknown;
    clamped?: SessionToolPolicyClamp[];
    set_by?: {
        tenant_id?: string;
        user_id?: string;
        client?: string;
    };
    set_at?: string;
    /** The response's top-level `scope`, which the client carries onto the policy it returns
     * (absent when the client or the gateway does not provide it; the UI then says so). */
    scope?: SessionToolPolicyScope;
};
/** Host-injected, already bound to one `session_id`. The controller never fetches a policy route itself. */
export type SessionToolPolicyClient = {
    /** `capabilities.session_tool_policy.supported === true` from `GET discovery/capabilities`. */
    supported: boolean;
    sessionId: string;
    get(): Promise<SessionToolPolicy | null>;
    /** PUT: replace the policy. */
    replace(body: SessionToolPolicyBody): Promise<SessionToolPolicy>;
    /** POST: merge into the policy. */
    merge(body: SessionToolPolicyBody): Promise<SessionToolPolicy>;
    /** DELETE: no session policy. `ifRevision` guards it (`DELETE ?if_revision=`); the answer has
     * no policy, so its `scope` rides next to the revision. */
    reset(ifRevision?: number): Promise<{
        revision?: number;
        scope?: SessionToolPolicyScope;
    }>;
};
/**
 * Where "Allow for this chat" is stored:
 * - `"gateway"`: on the gateway (every run and client of the chat);
 * - `"local-fallback"`: the gateway has no such capability (older gateway, or no client
 *   injected): the client-side grant, labeled as such;
 * - `"unavailable"`: the capability read failed (`sessionPolicyReason`); no chat grant is
 *   made (Allow once still works).
 */
export type SessionPolicyMode = "gateway" | "local-fallback" | "unavailable";
/** The controller's session-policy state, the ONE source the approval controls read. */
export type SessionPolicyStatus = {
    mode: SessionPolicyMode;
    reason?: string;
    clamped: SessionToolPolicyClamp[];
    policy: SessionToolPolicy | null;
};
/** A run artifact resolved by the host for display. */
export type ResolvedArtifact = {
    /** Object URL (or same-origin path) of the bytes. */
    src: string;
    /** The gateway's `content_type`. MUST be the type the object URL's Blob was
     * created with: the raw-link guard (`objectUrlRawLinkSafe`) trusts it. */
    contentType: string;
    name?: string;
    /** The gateway's `size_bytes`. */
    size?: number;
    /** Text kinds (markdown, code, json, text): the text, when the host already read it
     * (e.g. a small artifact). Without it the document opens as a raw-file link. */
    text?: string;
};
/** Raw runtime wait; presentation code may map this to its own UI union. */
export type WorkflowWaitInteraction = {
    runId: string;
    wait: ServerRecord;
    stepId?: string;
    /** From the replay view: the wait's kind as the runtime classifies it. */
    kind?: "tool_approval" | "ask_user" | "event";
    /** From the replay view: the resume that answers it (`POST commands`, answer under `payload`). */
    command?: {
        type: "resume";
        run_id: string;
        payload: {
            wait_key: string;
        };
    };
};
/**
 * Where a snapshot's conversation comes from:
 * - `"replay_view"`: the gateway's replay view (one server-side reconstruction of the run tree);
 * - `"ledger_fold"`: this client's own fold of ledger records (gateways without the view, or a
 *   transport without `replayView`); `sourceReason` says why.
 */
export type WorkflowSessionSource = "replay_view" | "ledger_fold";
export type WorkflowApprovalTarget = {
    runId: string;
    waitKey: string;
    stepId?: string;
};
export type WorkflowToolApprovalPolicy = {
    enabledTools: readonly string[];
    autoApproveTools: readonly string[];
};
export type WorkflowConnection = "idle" | "connecting" | "connected" | "reconnecting" | "disconnected";
export type WorkflowSessionSnapshot = {
    messages: ChatMessage[];
    records: WorkflowRecord[];
    run: ServerRecord | null;
    interaction: WorkflowWaitInteraction | null;
    /** Authoritative root-run lifecycle from GET /runs/{id}; never inferred
     * from an individual completed ledger step. */
    status: string;
    /** Optional human-facing status emitted by `abstract.status` events. */
    displayStatus: string;
    loading: boolean;
    /** Earlier session turns are still being restored. The current answer may
     * already be rendered; hosts must wait before consuming an opening's history. */
    historyLoading?: boolean;
    error: string | null;
    connection: WorkflowConnection;
    /** Browser/controller-local consent only; never persisted or a policy bypass. */
    autoApproveTools?: boolean;
    /**
     * True when `interaction` is a tool approval this controller has already
     * approved (automatically under the standing permission, or an accepted
     * Allow), or will approve in this same update. The raw wait is kept for
     * command routing, but it is running work, not a question: hosts must not
     * render an approval card or "Approval needed" for it (see
     * `workflowPendingInteraction`). Never true for questions, event waits,
     * denials, or batches outside the current permission.
     */
    toolApprovalGranted?: boolean;
    /**
     * Where a Stop stands, from LEDGER EVIDENCE only (never a browser timer):
     * `stopping` from the moment this client asks until the gateway proves the
     * model call ended; `stopped` once the root run is cancelled and no
     * `llm_call` step of the tree is still open (every started step has a
     * terminal record — the runtime writes `cancelled` with `cancelled_by`);
     * `forced` when the gateway's kill switch wrote its `abstract.status`
     * record (`killed_by: "kill_switch"`), whose text is the label.
     * Null when this client never asked to stop and nothing was forced.
     */
    stop?: WorkflowStopState | null;
    /** `"gateway"` when a supported `SessionToolPolicyClient` is injected, else `"local-fallback"`
     * (the client-side grant; hosts must label it, see `presentInteraction`). */
    sessionPolicyMode?: SessionPolicyMode;
    /** Why the mode is `"unavailable"` (e.g. the capability read failed). */
    sessionPolicyReason?: string;
    /** The conversation's stored policy after this controller's last write/read (gateway mode). */
    sessionPolicy?: SessionToolPolicy | null;
    /** What the gateway did not store on the last write (`policy.clamped`). Never dropped. */
    sessionPolicyClamped?: SessionToolPolicyClamp[];
    /** See `WorkflowSessionSource`; unset until a run is loaded. */
    source?: WorkflowSessionSource;
    /** Why the conversation is not rendered from the replay view (`source: "ledger_fold"`). */
    sourceReason?: string;
    /** The replay view as folded from the gateway's stream (`source: "replay_view"`), else null. */
    view?: ReplayView | null;
};
/** One line for a host to show where the conversation comes from (empty before a load). */
export declare function workflowSourceLabel(snapshot: Pick<WorkflowSessionSnapshot, "source" | "sourceReason">): string;
export type WorkflowStopPhase = "stopping" | "stopped" | "forced";
export type WorkflowStopState = {
    phase: WorkflowStopPhase;
    label: string;
    record?: ServerRecord;
};
/** The wait a host should present as a question, or null. A tool approval
 * this client has already granted is presented as running tools instead. */
export declare function workflowPendingInteraction(snapshot: Pick<WorkflowSessionSnapshot, "interaction" | "toolApprovalGranted">): WorkflowWaitInteraction | null;
type Subscriber = () => void;
export type WorkflowSessionControllerOptions = {
    onAuthError?: (error: unknown) => void;
    clientId?: string;
    /**
     * Minimum time between two re-renders of live (streamed) reply text, in
     * milliseconds. Default 60: every frame still updates the reply state, but
     * the transcript (and its Markdown) is re-rendered at most this often; the
     * latest text is always rendered at the end of the interval. 0 renders every
     * frame.
     */
    liveRenderIntervalMs?: number;
    /** Session tool policy client (see `SessionToolPolicyClient`); also `setSessionToolPolicyClient`. */
    sessionToolPolicy?: SessionToolPolicyClient | null;
    /** The host could not read the capability: the mode starts `"unavailable"` with this reason. */
    sessionToolPolicyUnavailableReason?: string;
    /** Called with the stored policy and its `clamped` list after every write/read/reset. */
    onSessionPolicy?: (policy: SessionToolPolicy | null, clamped: SessionToolPolicyClamp[]) => void;
};
export declare class WorkflowSessionController {
    private readonly transport;
    private readonly options;
    private snapshot;
    private subscribers;
    private controller;
    private generation;
    private rootRunId;
    private cursors;
    private seenRecords;
    private seenMessages;
    private watchedRuns;
    private childCatchUpAttempts;
    private runStates;
    /** Authoritative terminal snapshots for historical session roots only. */
    private historicalRuns;
    private historicalRunFailures;
    private commandIds;
    private toolActivities;
    private historicalEvidence;
    private approvedWaits;
    /** Tool-approval occurrences this client has sent `approved: true` for
     * (automatic: at dispatch; manual: after acknowledgement). */
    private grantedToolWaits;
    /** `${runId}:${wait_key}` of waits a ledger `resume` record has answered
     * (any client's). The runtime appends that record BEFORE it saves the run
     * without its wait, so a run snapshot read in between still says
     * "waiting" for a decision already made: durable adoption skips these
     * until a new waiting record (a new occurrence) arrives for the key. */
    private resolvedWaits;
    private approvalEpoch;
    private toolApprovalPolicy;
    private toolApprovalSuspended;
    private toolApprovalStopped;
    private displayStatusAt;
    /** Stop evidence (see `WorkflowSessionSnapshot.stop`). */
    private stopRequested;
    private stopFollowing;
    private openLlmSteps;
    private forcedStop;
    /** Live (streamed) replies still open, keyed by `${runId}:${callId}`. */
    private liveReplies;
    /** Calls whose live reply has ended (delta_end, terminal llm_call record,
     * or the run's assistant message): later deltas for them are ignored. */
    private closedLiveCalls;
    /** Calls that showed a live bubble (pruned with `closedLiveCalls`). */
    private shownLiveCalls;
    private liveDirty;
    private liveRenderTimer;
    private lastLiveRender;
    private readonly liveRenderIntervalMs;
    private sessionToolPolicy;
    private sessionPolicyUnavailableReason;
    private sessionPolicyState;
    private sessionPolicyClamped;
    /** `abstract.tool_policy_decision` provenance by `${runId}:${call_id}` (contract §5). */
    private toolPolicyByCall;
    /** Where the conversation comes from (`WorkflowSessionSnapshot.source`), decided by `load`. */
    private source;
    /** Replay view mode: the view folded from the gateway's stream; null in ledger mode. */
    private viewFold;
    /** `GET runs/{root}` in view mode: lifecycle flags the view does not carry (`paused`). */
    private viewRun;
    private viewDigest;
    private viewAssistantIds;
    private viewTerminalRuns;
    /** The view stream ended (done, or gave up): the live-reply stream stops with it. */
    private viewStreamEnded;
    /** Replay view mode: the conversation's EARLIER turns (one view read each, oldest first),
     * shown before the loaded run's own messages. */
    private viewEarlier;
    /** The conversation's finished earlier turns, kept across `load()` calls of the same session
     * (a new turn reloads the controller): a finished turn's view cannot change, so each is read
     * once, and the transcript does not collapse to the new prompt while the list is re-read. */
    private viewTurnCache;
    constructor(transport: WorkflowTransport, options?: WorkflowSessionControllerOptions);
    /** `"gateway"` only for an injected client whose capability is `supported === true`. */
    sessionPolicyMode(): SessionPolicyMode;
    /** Mode, reason, `clamped` and stored policy: what `presentInteraction` reads (never a host prop). */
    sessionPolicyStatus(): SessionPolicyStatus;
    /**
     * Inject (or remove) the session policy client, e.g. once discovery has answered or the
     * session changed. `null` with a `reason` means the capability read FAILED (mode
     * `"unavailable"`); `null` alone means the gateway does not offer it (`"local-fallback"`).
     */
    setSessionToolPolicyClient(client: SessionToolPolicyClient | null, options?: {
        reason?: string;
    }): void;
    private gatewayPolicy;
    private adoptSessionPolicy;
    /** Read the conversation's stored policy (gateway mode). */
    loadSessionPolicy(): Promise<SessionToolPolicy | null>;
    /**
     * The grant is read from the run tree's ROOT session (contract §4.2): the client must be
     * bound to the root run's `session_id`, never a child's. Fails loudly otherwise.
     */
    private requireRootSession;
    /** The revision a guarded write uses: the adopted policy's, else read first (the policy's, or the
     * client's latest answer revision, which also covers "no policy yet"). */
    private currentRevision;
    /** A failed policy write, labeled: a conflict asks to re-read (and re-reads); the client's own
     * refusal (e.g. ui-kit's `SessionToolPolicyRevisionError`) says the policy was not changed. */
    private policyWriteError;
    /** The shown approval must still be the current one before any policy is written. */
    private requireTarget;
    /**
     * Write the policy FIRST, then answer the shown wait (contract §4: the policy never
     * answers existing waits). `ask` (the person's explicit Ask tools) travels on every
     * write, so a broad approve never overrides them.
     */
    private writeThenAnswer;
    /**
     * "Allow for this chat". Gateway mode: merge `{approve:{all:true}}` into the
     * conversation's policy, then answer the shown wait `{approved:true}`; later
     * calls of every run of the conversation run without a wait. Local fallback
     * (no supported client): the existing client-side grant
     * (`allowAllToolsForRun`: this controller, until the run ends). Returns the
     * stored policy, or null in the fallback.
     */
    approveAllForSession(target: WorkflowApprovalTarget, options?: {
        maxRiskRank?: number;
        ask?: readonly string[];
    }): Promise<SessionToolPolicy | null>;
    /** "Allow all <toolset> tools for this chat": merge `{approve:{kinds:[kind]}}`, then answer `{approved:true}`. Gateway mode only. */
    approveKindForSession(target: WorkflowApprovalTarget, kind: string, options?: {
        ask?: readonly string[];
    }): Promise<SessionToolPolicy>;
    /** Deny a toolset for the chat, then answer `{approved:false}`. Gateway mode only; no panel control (hosts expose it). */
    denyKindForSession(target: WorkflowApprovalTarget, kind: string, options?: {
        ask?: readonly string[];
    }): Promise<SessionToolPolicy>;
    /** Deny one tool for the chat, then answer `{approved:false}`. Gateway mode only; no panel control (hosts expose it). */
    denyToolForSession(target: WorkflowApprovalTarget, tool: string, options?: {
        ask?: readonly string[];
    }): Promise<SessionToolPolicy>;
    /** Reset: gateway mode deletes the conversation's policy; the fallback revokes the local grant. */
    /** Narrowing an approve (undo) is a reset (DELETE), never a merge: a merge only adds. */
    resetSessionPolicy(): Promise<void>;
    private withSessionPolicy;
    private withSource;
    subscribe(listener: Subscriber): () => void;
    getSnapshot(): WorkflowSessionSnapshot;
    reset(): void;
    dispose(): void;
    load(runId: string): Promise<void>;
    sendCommand(type: string, payload?: Record<string, unknown>): Promise<unknown>;
    /** Answer the current question. With `target`, refuses when the question shown is no longer the current one. */
    resume(response: string, target?: WorkflowApprovalTarget): Promise<unknown>;
    /**
     * Answer an event wait served by the replay view with its own resume command (the view's
     * `answer_payload` for an event is the payload itself). With `target`, refuses when the wait
     * shown is no longer the current one.
     */
    answerEvent(payload: unknown, target?: WorkflowApprovalTarget): Promise<unknown>;
    approve(approved: boolean, target?: WorkflowApprovalTarget): Promise<unknown>;
    approveWithPolicyChange(target: WorkflowApprovalTarget, onApproved: () => void): Promise<void>;
    allowAllToolsForRun(target: WorkflowApprovalTarget): Promise<void>;
    revokeToolApproval(): void;
    /** Host-owned persistent permissions, intersected with current availability.
     * This is configuration, not a blanket grant and cannot enable a tool. */
    setToolApprovalPolicy(policy: WorkflowToolApprovalPolicy | null): void;
    private occurrenceKey;
    /**
     * The interaction to show once `candidate` is observed. A wait a person can
     * answer (tool approval, question, event) replaces what is shown: the latest
     * evidence wins, as before. A delegation wait (`subworkflow:<child>`: the
     * root parked on its agent loop) never displaces a person-facing wait — the
     * root's wait says "the child is working", the child's says what must be
     * decided. Every client rebuilds the same gate from the same durable state
     * whichever order it reads it in (2026-09-29: a fresh client showed
     * "Running a tool" for a turn parked on the child's write_file approval).
     * Same run and key without a step id (a run snapshot) keeps the occurrence
     * the ledger record established.
     */
    private interactionWith;
    /**
     * A run's durable wait (`GET /runs/{id}.waiting`) is the gate a client that
     * never received the ledger record must still show: the bundle's tail
     * window can drop it, a stream can reconnect past it. Ledger records keep
     * their precedence (`foldRecord`); this fills what durable state proves and
     * never re-opens a wait the ledger already resolved.
     */
    private adoptDurableWait;
    /** Whether the automatic approver answers `interaction` in `snapshot`
     * (ignoring its own once-per-occurrence dedupe). Single source for both
     * the approver and the presentation flag, so they cannot disagree. */
    private coveredByStandingPermission;
    /** Presentation of a controller snapshot: a granted tool approval shows
     * its calls as running, never as "need approval". Raw statuses stay in
     * `toolActivities`, so a failed automatic approval reverts exactly. */
    private present;
    private toolCallsMatch;
    private isToolApproval;
    private autoApproveCurrentWait;
    emitEvent(payload: Record<string, unknown>): Promise<unknown>;
    cancel(): Promise<unknown>;
    private requireInteraction;
    private interactionRunId;
    private live;
    private set;
    /**
     * Render from the gateway's replay view when the transport offers it and the gateway serves
     * it. Returns false (and labels the snapshot `ledger_fold` with the reason) otherwise: no
     * transport, a gateway that advertises no view, or one that answered it has no such route
     * (remembered per transport). Any other failure is a load failure, never a silent fallback.
     */
    private loadView;
    /** Read the views of the conversation's turns before `runId` and keep their messages. */
    private loadEarlierTurns;
    /** Project the folded view into the snapshot (the ONE place view mode writes conversation state). */
    private adoptView;
    /** Follow the view stream (`Last-Event-ID` = the last applied frame) until `done`. */
    private followView;
    /**
     * Live reply text (`llm.delta`) is not part of the view: it rides the root's ledger stream
     * (which also carries the sub-runs' deltas). Its records are ignored here: the view has them.
     */
    private followLiveReplies;
    /** Conditional re-read of the view (304 while unchanged). */
    private refreshView;
    /** `GET runs/{root}` for what the view does not carry (`paused`); never a lifecycle authority over the view. */
    private refreshViewRun;
    private catchUpAndWatch;
    private catchUp;
    /** Follow one run's stream until it ends or this controller stops
     * following it; either way no live reply that stream delivered survives. */
    private watch;
    private followStream;
    private ingestHistory;
    private ingestSessionTurn;
    /** Fetch only returned prior session roots, with bounded fan-out. */
    private hydrateHistoricalSessionRuns;
    private ingestItem;
    private foldRecord;
    /** Ledger evidence for the Stop states: open model calls and forced stops. */
    private foldStopEvidence;
    private recomputeStop;
    /** Ledger catch-up while a cancelled tree still has an open model call. Ends
     * on evidence (stopped/forced) or when this controller is reset; the state
     * itself only ever changes through `foldStopEvidence`. */
    private followStop;
    private addMessage;
    private toolMessage;
    private upsertTool;
    /** Session history is a fallback; durable answer_user and terminal output
     * are authoritative. Suppress only an exact duplicate for the same run. */
    private addRunAssistantMessage;
    /**
     * Fold one `llm.delta` / `llm.delta_end` event delivered by the stream of
     * `streamRunId`. A snapshot replaces the channel's text (unless it is older
     * than what is shown); a live delta is appended only when its `seq` is
     * higher than the last one of its channel, so duplicates and out-of-order
     * frames are dropped. A call whose durable record or reply is already here
     * never gets a bubble again. A malformed event is reported as an error.
     */
    private ingestDelta;
    private runEnded;
    /** Render changed live replies now, or at the end of the current interval. */
    private scheduleLiveRender;
    private renderLiveReplies;
    private liveMessage;
    /** End a live reply: remove its bubble, or replace it with a short note
     * when the stream ended because the call failed or was cancelled. */
    private closeLiveReply;
    private restartNote;
    /** A call ran without streaming: one note per run and cause, never a bubble. */
    private noteStreamUnavailable;
    private closeLiveRepliesOfRun;
    /** Close the live replies a stream delivered (the controller stopped following it). */
    private closeLiveRepliesVia;
    /**
     * A run reached a terminal state: close its live replies (for the root, every
     * live reply of the turn, sub-agents included) whether or not their
     * `llm.delta_end` arrived, then forget its closed-call keys. Later frames for
     * it are refused by the terminal-run check in `ingestDelta`.
     */
    private endLiveRepliesOfRun;
    /** Forget (without closing) the live replies a stream delivered; its
     * reconnect snapshots bring the current text back. */
    private dropLiveRepliesVia;
    private fail;
    private newCommandId;
    private updateRunState;
    private upsertFinal;
    private refreshRunState;
    /**
     * SSE is the source for ledger records, not an exhaustive lifecycle feed.
     * In particular a parked event wait can remain connected while another
     * actor pauses it or cancels its root. Poll only the root metadata at a
     * modest cadence; AbortController + generation prevent stale completions
     * from an old run or auth scope changing the current snapshot.
     */
    private pollRootLifecycle;
    private waitForRetry;
}
export {};
//# sourceMappingURL=workflow_runtime.d.ts.map