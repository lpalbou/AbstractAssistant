# Getting started

AbstractAssistant is a macOS-first tray app and CLI.

The tray app is a **gateway-first thin client**:
- agent loop: `abstractagent` (ReAct / CodeAct / MemAct)
- durability: `abstractruntime` (runs + waits + ledger + artifacts)
- providers/tools/media: `abstractcore`

See also:
- [README.md](README.md) (docs hub)
- [architecture.md](architecture.md) (durability + tool boundary, diagrams)
- [api.md](api.md) (CLI + programmatic API)

## Install

```bash
pip install "abstractassistant"
```

AbstractVoice is installed by default so voice features work out of the box.

## Run

### Tray UI (macOS)

```bash
assistant
```

Running `assistant` starts the tray UI.

Optional connection overrides:

```bash
assistant --gateway-url http://127.0.0.1:8080 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN"
```

### CLI (single agentic turn)

```bash
assistant run --prompt "What is in this repo and where do I start?"
```

Defaults:
- Tray UI defaults to gateway mode at `http://127.0.0.1:8080`.
- Provider and model lists in the tray UI are discovered from the gateway.
- The tray remembers the last selected provider/model in session state.
- Workflow selection comes from the gateway bundle catalog.

### Gateway mode

AbstractAssistant talks to AbstractGateway by default at `http://127.0.0.1:8080`.

Use the same bearer token for both processes, and make sure the gateway loads workflow bundles:

```bash
export ABSTRACTGATEWAY_FLOWS_DIR="$PWD/abstractgateway/flows/bundles"
export ABSTRACTGATEWAY_AUTH_TOKEN="your-shared-token"
abstractgateway serve --host 127.0.0.1 --port 8080
assistant
```

Optional gateway URL override:

```bash
export ABSTRACTGATEWAY_URL="http://127.0.0.1:9090"
assistant
```

If `ABSTRACTGATEWAY_URL` is unset, AbstractAssistant defaults to `http://127.0.0.1:8080`.
If `ABSTRACTGATEWAY_AUTH_TOKEN` is unset, startup fails with a clear error telling you to export it or pass `--gateway-token`.

If you launch `abstractgateway` from the monorepo root without setting `ABSTRACTGATEWAY_FLOWS_DIR`, its default `./flows` may be empty. In that case provider/model discovery can work while workflow discovery still fails because the gateway has no loaded agent bundles.

## Providers (local vs cloud)

In gateway mode, provider and model discovery come from the gateway. Configure LM Studio, Ollama, OpenAI, Anthropic, and any other providers on the gateway side; the tray app only needs to reach the gateway itself.

## Tool approvals (safety boundary)

Tool calls are surfaced as a **durable wait** and require explicit approval by default:
- safe/read-only tools can be auto-approved
- writes, shell execution, and unknown tools require approval

Evidence in code:
- default policy: `abstractassistant/core/tool_policy.py`
- durable wait/resume: `abstractassistant/core/agent_host.py`

CLI:
- prompts interactively when a tool batch requires approval

Tray UI:
- “Tools” lets you choose **All tools** vs a **Custom allowlist**
- per-tool default approval mode for the current session

## Attachments (tray UI)

Use the paperclip button to attach local files.

What happens (evidence: `abstractassistant/core/agent_host.py`):
- attachments are stored as **runtime artifacts** when possible
- file “handles” are kept model-safe (relative to `workspace_root` when configured, otherwise filename)
- default max attachment size is **25 MiB** (override via `ABSTRACTGATEWAY_MAX_ATTACHMENT_BYTES`)

Audio notes:
- common containers like `.wav`, `.mp3`, `.m4a`, `.ogg`, `.flac`, `.aac`, `.webm`
- audio attachments are **pre-transcribed** via AbstractVoice when available, and the transcript is attached as text

Video notes:
- common containers like `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, `.wmv`, `.m4v`
- AbstractAssistant does not bundle `ffmpeg`. If your provider/media pipeline relies on `ffmpeg` for frame extraction, ensure it is on your PATH.

## Sessions (tray UI)

The tray UI supports multiple sessions and persists them under your data directory:
- index: `sessions.json`
- legacy/base session: `session.json`
- additional sessions: `sessions/<session_id>/...`

Evidence: `abstractassistant/core/session_index.py`, `abstractassistant/core/session_store.py`

## Environment

Tray mode is environment-driven:
- `ABSTRACTGATEWAY_URL` for the gateway base URL
- `ABSTRACTGATEWAY_AUTH_TOKEN` for gateway auth

Optional assistant CLI overrides:
- `--gateway-url`
- `--gateway-token`

Provider settings stay on the gateway side:
- provider-specific credentials and base URLs belong to the gateway process, not the tray app

There is no versioned `config.toml` in the repo for tray startup anymore.

## Data directory

By default, state is stored in `~/.abstractassistant/`:
- `session.json`: transcript snapshot + last run id (fast UX state)
- `sessions.json`: session registry + active session id
- `runtime/`: AbstractRuntime stores (durability source of truth)

## Troubleshooting

- Tray fails to start: reinstall: `pip install --upgrade "abstractassistant"`.
- Gateway discovery shows only one provider or a single configured model:
  - ensure `assistant` and `abstractgateway` were launched with the same `ABSTRACTGATEWAY_AUTH_TOKEN`
  - if you previously sent the wrong token, wait for the gateway auth lockout to expire, then relaunch the assistant
- Gateway reports no agent entrypoints:
  - ensure the gateway loads bundles via `ABSTRACTGATEWAY_FLOWS_DIR`
  - for this monorepo checkout, `export ABSTRACTGATEWAY_FLOWS_DIR="$PWD/abstractgateway/flows/bundles"` is the expected local-dev setting
- Provider errors:
  - verify gateway-side provider configuration and credentials
  - verify the gateway itself can reach the provider
- Microphone hears nothing (macOS): System Settings → Privacy & Security → Microphone → enable access for AbstractAssistant, then restart.
- Reset state: use “Clear” in the UI, or delete your data dir (`~/.abstractassistant/` by default).

## Next

- [api.md](api.md)
- [architecture.md](architecture.md)
- [faq.md](faq.md)
