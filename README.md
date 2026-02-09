# AbstractAssistant

AbstractAssistant is a macOS-first tray app and CLI that hosts a **local, durable agent**.

It is part of the **AbstractFramework** ecosystem:
- https://github.com/lpalbou/AbstractFramework
- key components used directly here:
  - AbstractCore: https://github.com/lpalbou/abstractcore
  - AbstractRuntime: https://github.com/lpalbou/abstractruntime

## What it does

- **Tray UI**: menu bar/system tray bubble with sessions, attachments, tool approvals, and optional voice.
- **CLI**: run a single agentic turn in the terminal.
- **Durable tool boundary**: tool calls are surfaced as a resumable wait and executed only by the host after approval.

High-level flow (evidence: `abstractassistant/core/agent_host.py`):

```
Tray UI / CLI -> AgentHost -> AbstractAgent -> AbstractRuntime -> AbstractCore -> Provider(s)
```

## Install

```bash
pip install "abstractassistant"
```

Requirements (summary):
- Python 3.10+
- Tray UI is macOS-first (menu bar/system tray); CLI/backend may work elsewhere but macOS is the primary target.
- A provider must be available (for example LMStudio/Ollama running locally, or cloud API keys set via env vars).

## Quick start

Tray UI:

```bash
assistant tray
```

CLI (one turn):

```bash
assistant run --prompt "What is in this repo and where do I start?"
```

Provider/model override:

```bash
assistant --provider ollama --model qwen3:4b-instruct run --prompt "Summarize my changes"
```

## Data & durability

Default data directory: `~/.abstractassistant/` (override with `--data-dir`).

Contents (evidence: `abstractassistant/core/session_index.py`):
- `session.json`: transcript snapshot + last run id (fast UX state)
- `sessions.json`: session registry + active session id
- `runtime/`: AbstractRuntime stores (run state, ledger, artifacts)

## Documentation

Start here: [docs/README.md](docs/README.md)

Core guides:
- [docs/INSTALLATION.md](docs/INSTALLATION.md)
- [docs/getting-started.md](docs/getting-started.md)
- [docs/api.md](docs/api.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/faq.md](docs/faq.md)

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q
assistant --debug tray
```

## Contributing / Security / License

- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security reporting: [SECURITY.md](SECURITY.md)
- License: [LICENSE](LICENSE)
- Acknowledgments: [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)
