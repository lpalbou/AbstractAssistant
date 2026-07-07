# Planned: V2 Runtime Replayer ADR Compliance Hardening

## Metadata
- Created: 2026-06-28
- Status: Planned
- Completed: N/A

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: May revise existing ADR. ADR 0001 remains accepted policy, but this item must
  verify that ADR/docs explicitly cover cross-client runtime ownership before closure.

## Context

AbstractAssistant v2 is intended to be a thin desktop shell: replay Gateway/runtime execution,
send user commands, upload files, capture microphone input, play audio, and open downloaded
artifacts. It must not become a second runtime, provider router, media executor, sandbox client,
or source of truth for run history.

The hard invariant is cross-client, not AbstractAssistant-specific: AbstractAssistant,
AbstractObserver, AbstractCode, and any future viewer/controller must derive visible run content,
pending waits, tool approvals, ask-user prompts, artifacts, and terminal state from the same
Gateway/Runtime surfaces. A wait is not owned by the client that first displayed it. Until the
runtime records that the wait was answered, any authenticated capable client must be able to
discover it and answer it through Gateway commands.

Recent adversarial review found that the supported v2 tray and CLI path mostly follows the
gateway-catalog workflow contract, but the codebase is not yet clean enough to answer "fully
compliant" without caveats.

## Current code reality

- ADR 0001 requires every tray and CLI turn to run through the tenant-catalog
  `abstractassistant-orchestrator` workflow, with gateway capability-default routes as the source
  of truth.
- `GatewayWorker` rejects incomplete or non-`tenant_catalog` workflow metadata before launching a
  run.
- v2 tray submission builds a `GatewayWorker`, uploads attachments through Gateway, starts
  `/api/gateway/runs/start`, follows the Gateway ledger, and resumes waits through
  `/api/gateway/commands`.
- CLI execution uses the same v2 controller and catalog workflow path.
- Replay is still too forgiving: history seeding failures in `GatewayWorker._seed_history_from_gateway`
  warn and keep the local snapshot instead of surfacing an explicit blocked/degraded state.
- Completed-run attach can return before seeding/replaying history when the attached run is already
  terminal.
- `GatewayRunController.stream_run` can observe a terminal status after SSE idle and return without
  a final ledger replay.
- `GatewayWorker._handle_events` emits `tool_request` and `ask_user` waits, then blocks the ledger
  follow loop on local `threading.Event` objects until this assistant instance answers.
- New runs still pass `LLMManager.session_messages()` into workflow input, so local cached
  transcript state can become runtime context instead of the runtime resolving canonical history
  from `session_id` or a Gateway-issued history envelope.
- `LLMManager.replace_gateway_messages` preserves a larger local snapshot when Gateway replay is
  shorter, which makes local cache win over runtime replay.
- Empty-output fallback text can be appended as assistant history even though it is a local
  diagnostic, not necessarily runtime-authored content.
- Tool details prefer Gateway ledger data, but can fall back to persisted scratchpad-derived calls
  when ledger lookup fails.
- `build_run_input_data` and the v2 controller still materialize provider/model defaults from the
  desktop side into workflow input.
- `GatewayClient` still exposes direct sandbox/media methods, and legacy assistant/bubble code still
  contains local `AgentWorker`/`LLMWorker` execution paths. These are not on the supported v2 entry
  path, but they remain drift-prone and poorly quarantined.
- Tests cover some catalog metadata happy paths, but do not adequately prove fail-closed replay,
  absence of direct/sandbox/media calls from v2/CLI, or command-only wait resumption.

## Problem

The implementation is close to the desired architecture, but it still has soft fallbacks and
residual surfaces that make the assistant look like more than a runtime replayer and command/file
sender. That creates three concrete risks:

- missed or stale user-visible output when replay surfaces fail;
- divergent content between AbstractAssistant, AbstractObserver, AbstractCode, or another viewer;
- pending tool or ask-user waits that are effectively held hostage by one local UI thread;
- accidental future use of direct sandbox/media/local-runtime methods from v2;
- provider/model routing authority drifting back into the desktop shell.

## Adversarial design findings

### Replay pass

Current compliance: No.

The v2 path follows Gateway ledgers, but it does not fail closed or replay terminal state strongly
enough. A replayer must not silently keep local snapshots when Gateway history or ledger surfaces
are unavailable, and it must not let local transcript/session cache become canonical runtime input.

Minimal design:

- Make `GatewayRunController` a strict replay controller: replay before stream, stream while live,
  replay once more before treating a run as terminal, and replay subruns before popping them.
- Make completed-run attach seed/replay history before emitting completed status.
- Convert history-bundle failures and empty required replay results into explicit user-visible
  degraded/blocked events, not warning-only fallbacks.
- Keep placeholder text such as "workflow completed with no written reply" only as a UI diagnosis
  tied to a real terminal ledger/history state.
- Treat local message snapshots as disposable read-through cache. Runtime/Gateway replay wins even
  when it is shorter than local history; if that looks wrong, surface a replay degradation instead
  of silently preserving divergent local state.

### Cross-client wait and content parity pass

Current compliance: No.

The current wait handling is still client-owned in practice: `GatewayWorker` emits the runtime wait
to the UI, then blocks on local events for approval or input before continuing ledger processing.
That prevents the assistant from being a passive observer while another client answers the same
runtime wait.

Minimal design:

- Treat pending `tool_approval` and `ask_user` waits as Gateway/Runtime objects identified by
  `run_id`, `wait_key`, and the runtime wait payload.
- Display wait UIs as projections of runtime state; local buttons submit Gateway commands and then
  observe resolution through replay/streaming.
- Do not block the ledger-follow loop while waiting for local approval/input.
- If AbstractObserver, AbstractCode, or another client answers a wait, AbstractAssistant must
  observe the runtime continuation, close or disable stale local controls, and converge to the same
  final history.
- Handle duplicate or racing wait answers idempotently through the Gateway/Runtime command path and
  surface resolved/conflict outcomes clearly in clients.
- Keep locally synthesized diagnostics as non-durable UI status unless Gateway/Runtime history
  represents the same diagnostic as canonical content.

### Execution-boundary pass

Current compliance: No for the whole codebase; mostly yes for the supported v2 entry path.

Direct/sandbox/media/local-runtime methods are not currently active in the v2 happy path, but the
importable surfaces are too easy to reuse accidentally.

Minimal design:

- Introduce or enforce a narrow v2 Gateway facade used by `abstractassistantv2/*`,
  `abstractassistant/cli.py`, and `GatewayWorker`. The facade should expose only workflow
  catalog/reconcile/start, ledger/history, commands, attachments, artifacts, capability-default
  settings, and Gateway-owned STT/TTS endpoints.
- Quarantine direct sandbox/media helpers behind legacy-only modules or explicit non-v2 names, and
  add tests/static checks that v2 and CLI code cannot call them.
- Mark legacy `AbstractAssistantApp`/`QtChatBubble` local-executor paths as unsupported
  compatibility code, or move them behind an explicit legacy entrypoint that is not imported by the
  v2 product path.
- Preserve per-device tool gating only as local approval preference. Actual tool execution must
  remain Gateway/runtime-owned.
- Clarify whether "allow all enabled tools in this chat" is per-device or runtime/session-wide. If
  it is cross-client, it belongs in Gateway/Runtime policy. If it is local, label it as a device
  preference and keep it out of durable runtime truth.

### Defaults and media/voice pass

Current compliance: Conditional no.

Settings correctly edit Gateway capability defaults, but assistant workflow starts still carry
provider/model fields supplied by the desktop. Voice also has env-var fallback selection for
provider/model/voice after capability lookup failures.

Minimal design:

- Stop passing text provider/model into assistant workflow run input as desktop-owned routing
  choices. The workflow/runtime should resolve defaults inside the Gateway/Core boundary.
- If Gateway needs an explicit default snapshot for reproducibility, expose a Gateway-issued run
  defaults envelope or revision and pass that opaque Gateway-owned value, not local provider/model
  routing fields.
- Keep Settings as a Gateway capability-default editor only.
- For voice, use Gateway capability defaults and explicit route settings. If capability surfaces
  fail, disable or block the voice control with a visible error instead of selecting provider/model
  from environment fallbacks.
- Media generation must remain workflow-routed for assistant turns. Direct media endpoints may
  exist as Gateway API client helpers, but v2 assistant turns must not call them.

## What we want to do

Close the remaining compliance gaps so the v2 assistant can be accurately described as a Gateway
runtime replayer plus command/file sender.

## Why

ADR 0001 is a product and debugging contract, not just an implementation preference. When the
assistant silently falls back, injects routing defaults, or exposes easy alternate execution
surfaces, users and maintainers lose the ability to reason about what actually happened in the
runtime.

## Requirements

- Preserve the single tenant-catalog workflow execution path for tray and CLI turns.
- Treat local transcript/session state as a read-through cache only; Gateway/Runtime history,
  ledger, waits, artifacts, and commands are the durable source of truth.
- Treat Gateway history and ledger surfaces as required replay surfaces.
- Do a final ledger replay before declaring a run terminal in the assistant UI or CLI.
- Seed/replay completed attached runs before reporting completion.
- Surface replay/history failures as explicit user-visible blocked or degraded states.
- Pending waits must remain discoverable from Gateway/Runtime while unresolved and must be
  answerable from any capable client, not only from the client thread that first observed them.
- Wait UI must not block the ledger-follow loop while waiting for local approval/input.
- Local wait approval/input controls must submit Gateway commands directly and then observe
  Runtime resolution through replay/streaming.
- Duplicate or racing wait answers from multiple clients must be handled idempotently by the
  Gateway/Runtime command path and surfaced clearly by clients.
- Locally synthesized diagnostics must not be persisted or presented as canonical assistant
  content unless the same diagnostic is represented by Gateway/Runtime history.
- Do not use scratchpad-derived tool calls as authoritative runtime history; label any fallback as
  degraded historical display only, or remove it from the v2 tool-details path.
- Remove provider/model from assistant-run input unless the value is an opaque Gateway-issued run
  defaults envelope.
- Keep Settings writes directed to Gateway capability-default routes.
- Ensure v2 and CLI code cannot call direct sandbox, direct media methods, local `AgentHost`,
  local `AgentWorker`, local `LLMWorker`, or prompt-cache preparation paths.
- Keep voice local only for capture/playback/control; STT/TTS routing must come from Gateway
  capability/default surfaces.

## Suggested implementation

- Refactor `GatewayRunController` so terminal completion runs one final bounded `replay_ledger`
  pass and reports whether replay was complete.
- Refactor `GatewayWorker.run` so attach-to-terminal-run always seeds/replays before emitting
  terminal status.
- Refactor `GatewayWorker._handle_events` so wait events are non-blocking: emit pending wait state
  to the UI, return immediately, and continue following/replaying the ledger.
- Move local wait submissions into a controller/service method such as `submit_wait_response` that
  calls Gateway `/commands` with `run_id`, `wait_key`, and payload. UI dialogs/buttons should never
  own runtime continuation.
- Add runtime-driven pending-wait state in the UI keyed by `run_id + wait_key`; reattach should
  seed pending waits from Gateway/Runtime state, and ledger replay should clear stale local controls
  when another client resolves the wait.
- Replace warning-only history seeding fallbacks with structured events consumed by v2 UI and CLI.
- Change `build_run_input_data` and callers so assistant workflow input contains prompt, context,
  attachments, tool gating policy, and optional Gateway-owned default revision/envelope, but not
  desktop-selected provider/model routing fields.
- Stop treating local `LLMManager.session_messages()` as authoritative run context. Prefer
  `session_id` plus Gateway/Runtime canonical history, or an opaque Gateway-issued history
  snapshot/revision when reproducibility requires a fixed context.
- Add a narrow v2 Gateway facade or protocol and update v2/CLI/worker code to depend on that
  facade instead of the full `GatewayClient` surface where practical.
- Move or clearly label direct sandbox/media helpers and legacy local executor paths so they are
  impossible to mistake for supported v2 architecture.
- Update tests to encode ADR 0001 as executable constraints, not only happy-path assertions.

## Scope

- v2 tray execution path
- CLI execution path
- Gateway replay/history/ledger usage
- v2 tool-details source of truth
- assistant workflow run input
- voice/media/default boundary checks
- ADR compliance tests and docs/backlog alignment

## Non-goals

- Do not rewrite Gateway, Runtime, Core, or the assistant workflow engine.
- Do not remove Gateway API methods that are needed by other packages unless ownership review says
  they are obsolete.
- Do not reintroduce private workflow discovery, sandbox chat fallback, or client-side direct media
  execution.
- Do not make the assistant responsible for resolving provider/model compatibility.
- Do not treat local transcript caches as durable runtime truth.
- Do not solve missing cross-client wait/history surfaces by inventing assistant-local
  synchronization or hidden local queues.

## Dependencies and related tasks

- [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- [Architecture: Published Workflow](../../architecture.md#published-workflow)
- [0002](0002_gateway_native_assistant_v2_rollout.md)
- [0004](0004_production_ux_and_catalog_default_hardening.md)
- [0005](../completed/0005_single_gateway_workflow_contract_cleanup.md)

## Expected outcomes

- v2 tray and CLI turns are provably catalog-workflow-only.
- Assistant history and tool details are replayed from Gateway ledger/history surfaces, with visible
  degraded states when those surfaces fail.
- AbstractAssistant, AbstractObserver, AbstractCode, and a minimal observer/controller can replay
  the same run and converge on the same canonical messages, waits, tool calls, artifacts, and
  terminal state.
- A pending tool or ask-user wait can be discovered and answered by any capable client, and every
  attached viewer observes the same runtime resolution through replay/streaming.
- Provider/model/media/voice routing is visibly Gateway-owned.
- Legacy/direct execution surfaces are quarantined enough that future v2 work cannot accidentally
  depend on them.
- The repository test suite can answer "yes" to ADR 0001 compliance for v2 without relying on
  manual reasoning.

## Validation

- Unit tests for `GatewayRunController`:
  - replay happens before streaming;
  - subworkflow runs are followed and replayed;
  - SSE idle followed by terminal status triggers a final ledger replay;
  - no terminal status is emitted when required replay fails.
- Unit tests for `GatewayWorker`:
  - missing `bundle_id`, `flow_id`, `bundle_version`, or non-`tenant_catalog` scope fails closed;
  - completed attach seeds/replays history before emitting completed;
  - history bundle failure emits explicit blocked/degraded UI event;
  - wait events do not block ledger following while local UI input is pending.
- Cross-client wait tests:
  - client A starts a run and observes a tool approval wait; client B fetches the same waiting run
    and approves it; client A continues without local approval, and both clients converge to the
    same final history;
  - client A observes an ask-user wait; client B answers it through `/api/gateway/commands`; client
    A observes the continuation through ledger replay/streaming;
  - a fresh client attaches to an already-waiting run, displays the pending wait from Runtime state,
    answers it, and all clients converge;
  - two clients answer the same wait; Runtime executes at most once and the losing client receives a
    resolved/conflict result, not a second execution.
- Cross-viewer parity tests:
  - AbstractAssistant and a minimal observer client replay the same completed run and produce
    identical canonical message/content/artifact references;
  - if a run completes without written content, the diagnostic displayed by clients is derived from
    Gateway/Runtime state and is not stored as assistant-authored content.
- v2/CLI boundary tests:
  - tray and CLI start runs only with tenant-catalog workflow metadata;
  - tool waits resume only through `submit_command(type="resume")`;
  - v2/CLI do not call `sandbox_generate`, direct media methods, local `AgentHost`, `AgentWorker`,
    `LLMWorker`, or prompt-cache preparation.
- Run-input tests:
  - assistant workflow input omits desktop-owned provider/model routing fields;
  - assistant workflow input does not send local cached chat history as authoritative context;
  - Settings still save/clear Gateway capability-default routes.
- Voice/media tests:
  - missing Gateway voice capability disables or blocks voice controls visibly;
  - assistant media prompts run through workflow start/ledger/artifact replay, not direct media
    client methods.
- Static import/use guard:
  - a small test or script fails if `abstractassistantv2/*`, `abstractassistant/cli.py`, or
    `abstractassistant/ui/gateway_worker.py` reference prohibited execution surfaces.
- Full validation:
  - `python -m pytest tests/basic tests/integration -q`
  - live Gateway smoke: chat, tool approval, ask-user wait, file attachment, media prompt, voice
    playback, terminal reattach, simulated ledger/history failure, and two-client wait resolution.

## Progress checklist
- [x] Make replay terminal-state handling strict and final-replay based.
- [x] Make completed-run attach replay before reporting completion.
- [ ] Replace warning-only replay/history fallbacks with explicit blocked/degraded events.
- [x] Make tool approval and ask-user waits non-blocking runtime projections that any capable
      client can answer.
- [x] Make local transcript/session cache disposable and never authoritative over Gateway/Runtime
      replay or context assembly.
- [x] Move empty-output fallback content to runtime-derived diagnostics, not durable assistant
      messages.
- [x] Remove desktop-owned provider/model routing fields from assistant workflow run input.
- [ ] Quarantine direct/sandbox/media/local-runtime surfaces from v2 and CLI.
- [ ] Harden voice/media boundaries against local routing fallback.
- [ ] Add ADR compliance tests and static guards.
- [ ] Update docs if implementation discovers an ADR boundary that must be clarified.

## Implementation report: 2026-06-29 replay hardening pass

### Implemented

- Added terminal ledger drain behavior in `GatewayRunController`: after SSE idle/status polling
  reports a terminal state, the controller now performs a bounded final ledger replay until the
  cursor is quiet before returning terminal.
- Preserved subworkflow discovery during terminal replay, so a child run discovered in the final
  drain is followed before the parent is popped.
- Made completed-run attach replay terminal ledger/history before emitting terminal status.
- Preserved real terminal status for attached and followed runs: `failed` and `cancelled` are no
  longer collapsed into `completed`.
- Made worker wait handling non-blocking: tool approvals and ask-user waits are displayed as
  runtime projections keyed by `run_id` and `wait_key`; local UI responses submit Gateway
  `resume` commands while ledger following continues.
- Stopped persisting the generic "workflow completed with no written reply" text as
  assistant-authored content in both `GatewayWorker` materialization and v2
  `_on_worker_finished`.
- Added `replay_degraded` UI events for history replay exceptions so replay failure becomes
  visible state instead of silent local-cache preservation.
- Made `LLMManager.replace_gateway_messages` treat Gateway replay as authoritative even when the
  replayed message set is shorter than the local cache.
- Removed desktop-owned provider/model routing fields and default local chat-history context from
  assistant workflow input. The start-run payload now carries prompt, attachments/artifacts, tool
  policy, and workflow metadata while Gateway/Core remain responsible for model routing and
  canonical history.
- Preserved bare runtime output artifacts (`{"$artifact": "..."}`) as final assistant events so
  the worker can materialize answer JSON from Gateway artifacts.
- Preferred explicit final-output artifacts over older remembered artifact candidates during
  answer recovery.

### Validation

- `python -m pytest tests/basic/test_gateway_run_controller.py tests/basic/test_gateway_events.py tests/basic/test_gateway_adapter.py tests/basic/test_gateway_worker.py tests/basic/test_gateway_run_input.py tests/basic/test_gateway_snapshot_preservation.py tests/basic/test_cli_gateway_mode.py tests/basic/test_assistant_v2.py -q`
  - Result: `110 passed`.
- `python -m pytest tests/basic -q`
  - Result: `221 passed`.
- `python -m pytest tests/integration -q`
  - Result: `5 passed`.
- `python -m pytest tests/basic tests/integration -q`
  - Result: `226 passed`.
- Real incident replay probe against Gateway root run `7489e42c-caf6-417b-80aa-77f12b9810a3`
  recovered one final assistant event, `1495` chars, with the Voltman answer prefix from the
  original failed UI session.
- `python -m abstractassistant.build_macos_app --skip-install`
  - Result: succeeded; rebuilt `dist/macos/AbstractAssistant.app`.

### Remaining work

- Replace remaining warning-only empty-history cases with a clearer replay state model. The current
  pass emits `replay_degraded` on history replay exceptions, but empty history bundles still leave
  local cache unchanged with `#REPLAY` diagnostics.
- Add stable final-event identity/deduplication by runtime record identity rather than content
  comparison.
- Add deeper cross-client wait tests that exercise two independent clients resolving the same
  runtime wait through Gateway commands.
- Add static guards for direct sandbox/media/local-runtime surfaces in v2 and CLI.
- Finish voice/media routing boundary tests.
- Decide whether scratchpad tool-call display fallback should be removed from v2 or labeled as
  degraded legacy display only.

## Guidance for the implementing agent

Start by writing failing tests for the current drift. Do not fix this by adding more fallback
branches. The clean design is stricter, not cleverer: Gateway owns execution and durable truth;
the assistant replays, displays, uploads files, and sends commands. The pass condition is
cross-client convergence, not a single assistant session appearing correct once.
