# Getting started

AbstractAssistant is a macOS-first tray app and CLI that hosts a **local, durable agent**:
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
assistant tray
```

Running `assistant` with no subcommand also starts the tray UI.

Voice listening mode (tray):

```bash
assistant tray --listening-mode wait
```

Valid modes: `none`, `stop`, `wait`, `full`, `ptt`.

### CLI (single agentic turn)

```bash
assistant run --prompt "What is in this repo and where do I start?"
```

Override provider/model:

```bash
assistant --provider ollama --model qwen3:4b-instruct run --prompt "Summarize my last changes"
```

Select agent kind (CLI only):

```bash
assistant --agent codeact run --prompt "Refactor this function safely"
```

Defaults:
- Tray UI defaults come from `config.toml` (or built-in defaults). By default: provider `lmstudio`, model `qwen/qwen3-next-80b`.
- CLI `run` defaults to provider `ollama`, model `qwen3:4b-instruct`, agent `react`.

Tip: global flags (like `--provider`, `--model`, `--agent`, `--data-dir`) go **before** the subcommand.

## Providers (local vs cloud)

AbstractAssistant delegates provider access to **AbstractCore**.

- Local providers:
  - **Ollama**: ensure the daemon is running, then use `--provider ollama`
  - **LMStudio**: enable the local server, then use `--provider lmstudio`
- Cloud providers:
  - set API keys via environment variables (for example `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)

## Tool approvals (safety boundary)

Tool calls are surfaced as a **durable wait** and require explicit approval by default:
- safe/read-only tools can be auto-approved
- writes, shell execution, and unknown tools require approval

Evidence in code:
- default policy: `abstractassistant/core/tool_policy.py`
- durable wait/resume: `abstractassistant/core/agent_host.py`

CLI:
- prompts interactively when a tool batch requires approval
- `--approve-all-tools` auto-approves all tool calls (dangerous)

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

## Configuration

Tray mode can load an optional `config.toml`:
- pass explicitly: `assistant --config /path/to/config.toml tray`
- auto-discovery: `config.toml` in current directory, then in the package directory

Common keys (evidence: `abstractassistant/config.py`):

```toml
[llm]
default_provider = "lmstudio"
default_model = "qwen/qwen3-next-80b"
max_tokens = 32000
temperature = 0.7
```

Note: `assistant run` currently uses CLI defaults and flags; it does not read `config.toml`.

## Data directory

By default, state is stored in `~/.abstractassistant/`:
- `session.json`: transcript snapshot + last run id (fast UX state)
- `sessions.json`: session registry + active session id
- `runtime/`: AbstractRuntime stores (durability source of truth)

Override with:

```bash
assistant --data-dir /path/to/dir tray
```

## Troubleshooting

- Tray fails to start: reinstall: `pip install --upgrade "abstractassistant"`.
- Provider errors:
  - local: ensure LMStudio/Ollama is running
  - cloud: ensure API keys are set
- Microphone hears nothing (macOS): System Settings → Privacy & Security → Microphone → enable access for AbstractAssistant, then restart.
- Reset state: use “Clear” in the UI, or delete your data dir (`~/.abstractassistant/` by default).

## Next

- [api.md](api.md)
- [architecture.md](architecture.md)
- [faq.md](faq.md)
