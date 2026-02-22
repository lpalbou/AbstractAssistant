# FAQ

See also:
- [README.md](README.md) (docs hub)
- [getting-started.md](getting-started.md) (first run)
- [api.md](api.md) (CLI + programmatic API)
- [architecture.md](architecture.md) (durability + tool boundary)

## What is AbstractAssistant?

A macOS-first tray app and CLI that runs **gateway-first** by default (thin client).
Local mode is still available for development. It uses:
- **AbstractAgent** for agent loops
- **AbstractRuntime** for durable runs and resumable waits
- **AbstractCore** for provider/tool/media schemas

Evidence: `abstractassistant/core/agent_host.py`, `abstractassistant/app.py`, `abstractassistant/cli.py`

## Is it part of AbstractFramework?

Yes. AbstractAssistant is a component in the AbstractFramework ecosystem:
- https://github.com/lpalbou/AbstractFramework
- https://github.com/lpalbou/abstractcore
- https://github.com/lpalbou/abstractruntime

## Does it run locally / offline?

The host runs locally. Whether it works offline depends on the provider:
- local providers (Ollama / LMStudio): can be offline (no cloud call)
- cloud providers (OpenAI / Anthropic): require network and API keys

## Where is my data stored?

By default: `~/.abstractassistant/` (override with `--data-dir`).

Evidence: `abstractassistant/core/agent_host.py`, `abstractassistant/core/session_index.py`

## Why do I keep seeing tool approval prompts?

Because AbstractAssistant enforces an explicit tool boundary:
- read-only tools may auto-run
- writes, shell execution, and unknown tools require approval

Evidence: `abstractassistant/core/tool_policy.py`

CLI:
- prompts in the terminal
- `--approve-all-tools` disables the boundary (dangerous)

Tray UI:
- use “Tools” to set a per-session allowlist and default approval mode

## Can I disable tools entirely?

Yes:
- tray UI: switch to a custom tool allowlist and select none (or only safe tools)
- programmatic: pass `allowed_tools=[]` to `AgentHost.run_turn(...)`

## Why was a file write blocked in gateway mode?

Gateway workspace policies limit where tools can write. If you see a tool result
error mentioning the workspace/root path, ensure your target path is inside the
gateway workspace, or configure:

- `ABSTRACTGATEWAY_WORKSPACE_DIR`
- `ABSTRACTGATEWAY_WORKSPACE_MOUNTS`

The tray UI will surface a hint in the tool result bubble when this happens.

## Where do artifact downloads go?

Artifact downloads are cached under:

- `~/.abstractassistant/artifacts/` by default
- or `<data-dir>/artifacts/` when you launch with `--data-dir`

## How does voice work in gateway mode?

When `gateway.use_gateway=true`, TTS and STT are routed through the gateway
audio endpoints (`/voice/tts`, `/audio/transcribe`). The client still needs a
local recorder and player; if those are unavailable, the UI will emit a
`#FALLBACK` warning and disable the affected control.

## How do I select a gateway workflow?

Use the **Workflow** dropdown in the tray UI. Selection is saved per session
and sent with each run via `bundle_id` + `flow_id`.

## Why does the status show OFFLINE?

The gateway is unreachable or restarting. The UI will retry with backoff and
you can use **Reconnect gateway** from the menu to force a refresh.

## How do attachments work?

In the tray UI, attached files are registered as runtime artifacts when possible and passed to the
provider/media pipeline. The default attachment size limit is 25 MiB (override via
`ABSTRACTGATEWAY_MAX_ATTACHMENT_BYTES`).

Evidence: `abstractassistant/core/agent_host.py`

## Why is voice not working?

Common causes:
- microphone permission not granted on macOS
- STT backend unavailable or model weights not downloaded yet

Start with:
- macOS System Settings → Privacy & Security → Microphone → enable AbstractAssistant

## Which agent loops are supported?

The backend supports `react`, `codeact`, and `memact` (AbstractAgent).
- CLI can select via `--agent`
- tray UI currently drives `react`

Evidence: `abstractassistant/core/agent_host.py`, `abstractassistant/cli.py`, `abstractassistant/core/llm_manager.py`

## How do I report a security issue?

Please follow [../SECURITY.md](../SECURITY.md).
