# Architecture

AbstractAssistant is a local “agent host” application: it exposes a tray UI and a CLI, but the core execution model is **agentic** and **durable**.

At a high level:

```
UI (Qt/tray) or CLI
  -> AgentHost (UI-agnostic backend)
      -> AbstractAgent (ReAct / CodeAct / MemAct)
          -> AbstractRuntime (durable runs + waits + ledger)
              -> AbstractCore integrations (LLM providers + tool schemas)
              -> Tool execution (host-held, approval gated)
```

## Goals

- One-click access (tray) to a capable agent.
- Durable execution (runs survive restarts; waits are explicit).
- Safe tool execution: tools are never persisted as callables in run state; the host executes them only after approval.
- Optional voice (STT/TTS) without forcing heavy deps on all installs.

## Core modules

### Agent host (backend)

`abstractassistant/core/agent_host.py` is the main backend. It:
- creates a local runtime with file-backed stores (runs + ledger + artifacts)
- constructs an agent (`ReactAgent`, `CodeActAgent`, or `MemActAgent`)
- drives the agent tick loop until terminal state
- handles waits:
  - TOOL_CALLS waits: emits a `tool_request` event, executes approved tools via a host-held executor, then resumes the run
  - ASK_USER waits: emits an `ask_user` event and resumes with user input

Events are plain dicts intended to be consumed by any UI:
- `status` (`thinking`, `executing_tools`, `ready`, …)
- `tool_request` / `tool_result`
- `ask_user`
- `assistant` (final answer)
- `error`

### Session snapshot (fast UI state)

`abstractassistant/core/session_store.py` persists a small `session.json` snapshot:
- `session_id` / `actor_id`
- transcript messages
- `last_run_id`

This is a UX optimization only: the runtime stores remain the durability source of truth.

### Tool approval policy

`abstractassistant/core/tool_policy.py` defines the default “safe auto-approve” vs “requires approval” sets. UIs can:
- auto-approve safe/read-only batches,
- prompt for approval on destructive/unknown batches,
- optionally maintain a session-scoped allowlist.

## Durability model

By default, state is stored under `~/.abstractassistant/` (override via `--data-dir`):

```
~/.abstractassistant/
  session.json
  runtime/
    *.json   (run store)
    *.jsonl  (ledger)
    ...      (artifacts)
```

Durability is provided by AbstractRuntime:
- every run has a durable state machine (`RUNNING` → `WAITING` → `COMPLETED`/`FAILED`)
- waits are explicit (`TOOL_CALLS`, `ASK_USER`, …) and resumable
- a ledger records effect execution for replay/observability

## Tool execution boundary

AbstractAssistant follows the framework’s “durable tool execution” rule:

- The runtime is configured with a `PassthroughToolExecutor(mode="approval_required")`.
  - Result: a TOOL_CALLS effect produces a durable wait that contains only JSON tool-call specs.
- The host holds the real callables via `MappingToolExecutor.from_tools(...)`.
- After approval, the host executes the tool batch and resumes the run with tool results:
  - `Runtime.resume(workflow=..., run_id=..., wait_key=..., payload=tool_results)`

This ensures:
- no Python callables end up persisted in `RunState.vars`
- pending tool work can be resumed after restarts
- the UI can always show “what is about to happen” before it happens

## UI integration (Qt/tray)

The tray UI uses a worker thread to keep Qt responsive:
- `abstractassistant/ui/qt_bubble.py` uses `AgentWorker` (a `QThread`) to drive `AgentHost.run_turn(...)`
- tool approvals are handled on the main thread via a modal approval dialog
- ASK_USER waits are handled via a simple input prompt

## Voice integration (optional)

Voice features are installed via `abstractassistant[full]`:
- `abstractassistant/core/tts_manager.py` wraps `abstractvoice.VoiceManager`
- the tray UI can run:
  - TTS for assistant outputs
  - Full Voice Mode: STT transcriptions routed into the same agentic send pipeline

Voice is optional by design: `assistant --help` and headless CLI usage must not import audio/GUI stacks.

## Entry points

- CLI: `abstractassistant/cli.py`
  - `assistant tray`
  - `assistant run --prompt ...` (interactive tool approvals in terminal)
- Tray app: `abstractassistant/app.py` (pystray + Qt)

## Install profiles

Defined in `pyproject.toml`:
- `abstractassistant` (default) == `lite`: tray UI dependencies (Qt + tray + markdown UX)
- `abstractassistant[full]`: voice (AbstractVoice) + broader AbstractCore provider/media extras
