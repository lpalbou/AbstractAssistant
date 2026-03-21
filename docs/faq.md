# FAQ

See also:
- [README.md](README.md) (docs hub)
- [getting-started.md](getting-started.md) (first run)
- [api.md](api.md) (CLI + programmatic API)
- [architecture.md](architecture.md) (durability + tool boundary)

## What is AbstractAssistant?

A macOS-first tray app and CLI that runs **gateway-first** (thin client). It uses:
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

The UI runs locally. Whether responses work offline depends on the provider behind the gateway:
- local providers (Ollama / LMStudio): can be offline (no cloud call)
- cloud providers (OpenAI / Anthropic): require network and API keys

## Where is my data stored?

By default: `~/.abstractassistant/`.

Evidence: `abstractassistant/core/agent_host.py`, `abstractassistant/core/session_index.py`

## Why do I keep seeing tool approval prompts?

Because AbstractAssistant enforces an explicit tool boundary:
- read-only tools may auto-run
- writes, shell execution, and unknown tools require approval

Evidence: `abstractassistant/core/tool_policy.py`

CLI:
- prompts in the terminal

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

- `~/.abstractassistant/artifacts/`

## How does voice work in gateway mode?

When `gateway.use_gateway=true`, TTS and STT are routed through the gateway
audio endpoints (`/voice/tts`, `/audio/transcribe`). The client still needs a
local recorder and player; if those are unavailable, the UI will emit a
`#FALLBACK` warning and disable the affected control.

## Why do I only see one provider or no LM Studio models?

In gateway mode, provider and model lists come from the gateway discovery endpoints, not from the local tray app.

If the assistant cannot authenticate to the gateway, discovery fails and provider/model discovery is rejected. Use the same shared token in both processes:

```bash
export ABSTRACTGATEWAY_AUTH_TOKEN="your-shared-token"
abstractgateway serve --host 127.0.0.1 --port 8080
assistant
```

If you sent the wrong token repeatedly, the gateway will temporarily return `429 Too Many Requests (auth lockout)`. Wait for the lockout window to expire, then relaunch the assistant with the correct token.

AbstractAssistant tray startup is environment-driven. Use:
- `ABSTRACTGATEWAY_URL` when the gateway is not on `http://127.0.0.1:8080`
- `ABSTRACTGATEWAY_AUTH_TOKEN` for the shared bearer token

Equivalent optional CLI flags:
- `--gateway-url`
- `--gateway-token`

There is no versioned tray `config.toml` for secrets.

## Why do I see `Gateway exposes no abstractcode.agent.v1 entrypoints`?

Because workflow discovery comes from the gateway too.

If the gateway starts without any loaded `.flow` bundles, provider/model discovery can still work while workflow discovery fails. For local development in this monorepo, launch the gateway with:

```bash
export ABSTRACTGATEWAY_FLOWS_DIR="$PWD/abstractgateway/flows/bundles"
abstractgateway serve --host 127.0.0.1 --port 8080
```

`abstractassistant` does not choose or load bundles itself. The gateway must expose at least one `abstractcode.agent.v1` entrypoint.

## Where should provider settings like LM Studio live?

On the gateway side.

AbstractAssistant only needs:
- the gateway URL
- the shared gateway auth token

Provider-specific settings such as LM Studio base URL, Ollama host, or cloud API keys belong to the gateway / AbstractCore environment, not the tray app.

## Does the tray app keep a local provider/model default?

No.

The tray app uses gateway discovery to populate the provider/model lists and only caches the last selected provider/model in session state so it can restore your last choice.

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

The gateway-backed workflows can use whatever agent loop the selected workflow defines.

Evidence: `abstractassistant/core/agent_host.py`, `abstractassistant/cli.py`, `abstractassistant/core/llm_manager.py`

## How do I report a security issue?

Please follow [../SECURITY.md](../SECURITY.md).
