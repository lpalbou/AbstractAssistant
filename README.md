# AbstractAssistant

AbstractAssistant is a macOS-first tray app and CLI.

The tray app is gateway-first: it connects to AbstractGateway, discovers available providers/models there, and keeps only local UI/session state.

It is part of the **AbstractFramework** ecosystem:
- https://github.com/lpalbou/AbstractFramework
- key components used directly here:
  - AbstractCore: https://github.com/lpalbou/abstractcore
  - AbstractRuntime: https://github.com/lpalbou/abstractruntime

## What it does

- **Tray UI**: menu bar/system tray bubble with sessions, attachments, tool approvals, and voice.
- **Media settings**: Gateway-backed Voice, TTS, STT, and Image selectors for generated speech, transcription, and image generation.
- **CLI**: run a single agentic turn in the terminal.
- **Durable tool boundary**: tool calls are surfaced as a resumable wait and executed only through the gateway after approval.

High-level flow:

```
Tray UI / CLI -> AbstractGateway -> AbstractRuntime -> AbstractCore -> Provider(s)
```

## Install

```bash
pip install "abstractassistant"
```

Requirements (summary):
- Python 3.10+
- Tray UI is macOS-first (menu bar/system tray); CLI/backend may work elsewhere but macOS is the primary target.
- For tray mode, an AbstractGateway instance must be available.

## Quick start

Tray UI:

```bash
assistant
```

CLI (one turn):

```bash
assistant run --prompt "What is in this repo and where do I start?"
```

Gateway startup (local dev):

```bash
export ABSTRACTGATEWAY_FLOWS_DIR="$PWD/abstractgateway/flows/bundles"
export ABSTRACTGATEWAY_AUTH_TOKEN="your-shared-token"
abstractgateway serve --host 127.0.0.1 --port 8080
assistant
```

Optional assistant-side overrides:

```bash
assistant --gateway-url http://127.0.0.1:8080 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN"
```

The Media settings dialog is populated from Gateway catalog routes:
`/api/gateway/voice/voices`, `/api/gateway/audio/speech/models`,
`/api/gateway/audio/transcriptions/models`, `/api/gateway/vision/provider_models`,
and `/api/gateway/vision/models`. If it only shows `default`, verify that the
running Gateway is the current package version and not an older server process.

## Data & durability

Default data directory: `~/.abstractassistant/`.

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
```

## Contributing / Security / License

- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security reporting: [SECURITY.md](SECURITY.md)
- License: [LICENSE](LICENSE)
- Acknowledgments: [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)
