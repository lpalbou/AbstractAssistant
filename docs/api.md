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
assistant run --help
```

### Global options

Defined in `abstractassistant/cli.py`:
- `--gateway-url URL`: optional gateway base URL override
- `--gateway-token TOKEN`: optional gateway auth token override

Run-specific options:
- `--prompt TEXT`: user prompt text

Note: global options appear before the subcommand.

Examples:

```bash
assistant run --prompt "Summarize this repo"
assistant --gateway-url http://127.0.0.1:9090 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN" run --prompt "Summarize this repo"
```

### `assistant run`

Runs a single agentic turn in the terminal.

Required:
- `--prompt TEXT`

Gateway behavior:
- provider/model come from gateway discovery or the cached session selection
- workflow selection comes from the gateway bundle catalog
- if the gateway exposes no `abstractcode.agent.v1` entrypoint, configure workflow bundles on the gateway side, typically via `ABSTRACTGATEWAY_FLOWS_DIR`

Tool approvals:
- prompts when a tool batch requires approval

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

### Environment-driven tray config

Evidence: `abstractassistant/config.py`

The tray UI is gateway-first and resolves connection settings from environment variables.

Gateway settings:
- `ABSTRACTGATEWAY_URL` (default `http://127.0.0.1:8080`)
- `ABSTRACTGATEWAY_AUTH_TOKEN`

Equivalent assistant CLI overrides:
- `--gateway-url`
- `--gateway-token`

Provider/model/workflow inventory is discovered from the gateway. The tray app does not keep a built-in provider/model or workflow default; it only persists the last selected provider/model/workflow in session state.

## Related docs

- [architecture.md](architecture.md) for the durability/tool boundary rationale
- [faq.md](faq.md) for common questions and troubleshooting
