# API & CLI reference

See also:
- [README.md](README.md) (docs hub)
- [getting-started.md](getting-started.md) (user guide)
- [architecture.md](architecture.md) (durability + tool boundary)

## CLI

Entry points (evidence: `pyproject.toml`):
- `assistant`
- `abstractassistant`

Help:

```bash
assistant --help
assistant tray --help
assistant run --help
```

### Global options

Defined in `abstractassistant/cli.py`:
- `--config PATH` (tray only): config file path (TOML)
- `--provider ID`: provider id (examples: `ollama`, `lmstudio`, `openai`, `anthropic`)
- `--model NAME`: model id/name for the provider
- `--agent react|codeact|memact` (CLI only): agent kind
- `--data-dir DIR`: where sessions/runtime are stored (default `~/.abstractassistant/`)
- `--workspace-root DIR` (CLI only): workspace root for tool/attachment scoping
- `--debug`: verbose logs

Note: these options must appear **before** the subcommand (for example `assistant --provider ollama run --prompt ...`).

Examples:

```bash
assistant --provider ollama --model qwen3:4b-instruct run --prompt "Summarize this repo"
assistant --debug tray --listening-mode wait
assistant --config ./config.toml tray
```

### `assistant tray`

Runs the menu bar / system tray app.

Options:
- `--listening-mode none|stop|wait|full|ptt`

### `assistant run`

Runs a single agentic turn in the terminal.

Required:
- `--prompt TEXT`

Tool approvals:
- prompts when a tool batch requires approval (see `abstractassistant/core/tool_policy.py`)
- `--approve-all-tools` disables approvals (dangerous)

## Programmatic API (Python)

Most users will use the CLI/tray UI. If you embed AbstractAssistant as a host component,
the stable surface is the backend:

### `AgentHost` (durable agent backend)

Defined in `abstractassistant/core/agent_host.py`.

Create a host:

```python
from pathlib import Path
from abstractassistant.core.agent_host import AgentHost, AgentHostConfig

host = AgentHost(
    AgentHostConfig(
        provider="ollama",
        model="qwen3:4b-instruct",
        agent_kind="react",
        data_dir=Path.home() / ".abstractassistant",
    )
)
```

Run a turn (generator of structured events):

```python
final = ""
for ev in host.run_turn(user_text="Hello"):
    if ev.get("type") == "assistant":
        final = ev.get("content", "")
```

Events (evidence: `AgentHost.run_turn` docstring):
- `status` (`thinking`, `executing_tools`, `tools_denied`, `ready`, …)
- `tool_request` / `tool_result`
- `ask_user`
- `assistant` (final answer)
- `error`

Tool approvals:
- pass `approve_tools(tool_calls)->bool`
- by default, the host auto-approves only the safe/read-only tool set in `ToolApprovalPolicy`

Allowlist tool schemas sent to the model:
- `run_turn(..., allowed_tools=[...])`
- when provided, only those tools (plus built-ins like `ask_user`) are exposed to the model

Resume after restart:
- `AgentHost.resume_run(run_id=...)` resumes WAITING runs (tool approvals / user input)

### Attachments

`AgentHost.run_turn(..., attachments=[...])` accepts:
- strings (local file paths)
- dicts that reference runtime artifacts (advanced / UI-internal)

Default size limit:
- 25 MiB (evidence: `AgentHost._max_attachment_bytes()`)
- override with `ABSTRACTGATEWAY_MAX_ATTACHMENT_BYTES`

Audio handling:
- audio files are transcribed via AbstractVoice when available and the transcript is attached as text

### `SessionStore` / `SessionIndex` (tray UX state)

Evidence:
- `abstractassistant/core/session_store.py`
- `abstractassistant/core/session_index.py`

Files under the data dir:
- `session.json`: transcript snapshot + ids (+ last run id)
- `sessions.json`: registry of sessions + active session id

### `Config` (`config.toml`)

Evidence: `abstractassistant/config.py`

The tray UI can load a TOML config file into `Config` and uses it for defaults
(theme, default provider/model, token limits, shortcut, etc.).

System tray tuning:
- `system_tray.animation_fps` (int): tray icon animation FPS (10-30, default 30)

Gateway settings (thin-client scaffolding):
- `gateway.url` (string): base URL for AbstractGateway (e.g. `http://127.0.0.1:8080`)
- `gateway.auth_token` (string): bearer token for the gateway (optional)
- `gateway.use_gateway` (bool): opt-in flag for gateway-first mode (default false)
- `gateway.bundle_id` (string): default bundle id (default `basic-agent`)
- `gateway.flow_id` (string): optional flow id override (default empty; discovered)

## Related docs

- [architecture.md](architecture.md) for the durability/tool boundary rationale
- [faq.md](faq.md) for common questions and troubleshooting
