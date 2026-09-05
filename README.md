# AbstractAssistant

AbstractAssistant is a gateway-native desktop assistant for the AbstractFramework ecosystem: a
macOS menu-bar app with a compact palette, a hands-free voice conversation mode, and a small CLI.

The desktop client stays thin. AbstractGateway owns workflow discovery, durable runs, provider
connections, tool execution and policy, workspace policy, and multimodal defaults. The assistant
keeps only local state: your chats, window placement, downloads, and the overrides you choose for
this app.

```text
Tray / Palette / CLI -> AbstractGateway -> AbstractRuntime -> AbstractCore -> Providers
```

## What you get

- A menu-bar palette whose title tells you what the app is doing, with a recent-chat picker and a
  live gateway connection orb.
- Live run activity in the transcript: the current step, elapsed time, recent tool calls with
  their arguments and durations, and pause / resume / stop controls.
- Tool approvals in a modeless sheet that shows the gateway's risk tier for each call and never
  blocks the palette; "always allow on this Mac" and per-chat trust for low-risk tools.
- A voice conversation mode (⌘⇧V): listen, send, speak, listen again — with a live status strip.
  Spoken replies stream from the gateway; dictation is a button away.
- A Settings window with seven sections: Connection, Models & reasoning (including the model's
  reasoning effort), Voice, Workspace (root and allowed folders), Tools & permissions, Window &
  shortcuts, About. Every value says whether it is the gateway default or this app's override.
- Local, persistent overrides for every route the assistant drives (chat, voice, image, video,
  music, sound) that ride each request without touching the gateway's shared defaults.
- Per-answer statistics (tokens, tools, files, duration, model) with clickable detail views.
- Multi-attachment composer with an image gallery, drag and drop, and artifact previews.

## Install

```bash
pip install "abstractassistant[voice]"
```

The `voice` extra adds local microphone capture (dictation and voice conversations). The base
install covers text chat, spoken replies and gateway-backed media; STT and TTS run on the gateway
either way.

Requirements: Python 3.10+, an AbstractGateway you can reach. macOS is the primary tray target;
Linux and Windows may work but are not packaged to the same standard.

## Quick start

Start a local gateway for development:

```bash
export ABSTRACTGATEWAY_FLOWS_DIR="$PWD/abstractgateway/flows/bundles"
export ABSTRACTGATEWAY_AUTH_TOKEN="your-shared-token"
abstractgateway serve --host 127.0.0.1 --port 8080
```

Launch the tray assistant:

```bash
assistant
```

Run a single terminal turn:

```bash
assistant run --prompt "Search the web for the latest OpenAI news and summarize it with sources."
```

Connection overrides:

```bash
assistant --gateway-url http://127.0.0.1:8080 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN"
```

The app uses the published `abstractassistant-orchestrator` workflow from the gateway tenant
catalog; there is no workflow to choose.

## Defaults and durability

The gateway is the source of truth for the published workflow, provider and model defaults, tool
inventory and approval defaults, workspace policy, run history, waits and artifacts.

The desktop client stores under `~/.abstractassistant/`:

- `preferences.json` — this app's overrides and preferences (model routes, reasoning effort,
  workspace grant, voice options, tool modes, hotkey, window size)
- `gateway_connection.json` — gateway URL and sign-in state
- `sessions/` — chat snapshots, last run ids and each chat's granted workspace folder
- downloads and cached audio

## Documentation

Start with [docs/README.md](docs/README.md).

- [docs/INSTALLATION.md](docs/INSTALLATION.md)
- [docs/getting-started.md](docs/getting-started.md)
- [docs/settings.md](docs/settings.md)
- [docs/voice.md](docs/voice.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/api.md](docs/api.md)
- [docs/faq.md](docs/faq.md)
- [docs/troubleshooting.md](docs/troubleshooting.md)
- [docs/adr/README.md](docs/adr/README.md)

## Development

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen python -m pytest tests/basic -q
```

## Project links

- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Acknowledgments: [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)
- License: [LICENSE](LICENSE)
