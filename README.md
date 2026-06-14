# AbstractAssistant

AbstractAssistant is a gateway-native desktop assistant for the AbstractFramework ecosystem.

It ships as a macOS-first tray app with a compact top-right palette and a small CLI. The desktop
client stays thin: AbstractGateway owns workflow discovery, durable runs, multimodal capability
defaults, provider connections, and media routing. The assistant keeps only local UX state such as
sessions, window placement, downloads, and optional hotkey preferences.

High-level flow:

```text
Tray / Palette / CLI -> AbstractGateway -> AbstractRuntime -> AbstractCore -> Providers
```

## What You Get

- A tray-first desktop assistant with a compact top-right query palette.
- One published gateway assistant workflow, `abstractassistant-orchestrator`, as the runtime path
  for tray and CLI turns.
- Gateway-backed multimodal defaults for text, voice, image, video, sound, and music routes.
- Local microphone capture and local playback while STT/TTS execution stays on the gateway.
- Workflow-routed image, video, sound, and music generation through gateway defaults.
- Durable tool approvals through gateway waits instead of local side channels.
- Gateway-backed capability-default editing, including advanced route options where the selected
  route supports them.

## Install

```bash
pip install "abstractassistant"
```

Practical requirements:

- Python 3.10+
- An AbstractGateway instance the assistant can reach
- macOS is the primary tray target; Linux and Windows may work but are not yet packaged to the same standard

## Quick Start

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

Optional connection overrides:

```bash
assistant --gateway-url http://127.0.0.1:8080 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN"
```

The tray app does not ask you to choose a workflow. It uses the published
`abstractassistant-orchestrator` workflow from the gateway tenant catalog.

## Defaults And Durability

Gateway is the source of truth for:

- the published `abstractassistant-orchestrator` workflow and its catalog entrypoint
- provider/model defaults for multimodal routes
- media routing and execution
- durable run history, waits, and artifacts

The desktop client stores only local state under `~/.abstractassistant/`, including:

- `sessions.json`: session registry and active session
- session transcript snapshots and last run ids
- `gateway_connection.json`: gateway URL plus bearer-token or session auth state
- local downloads and tray/palette preferences

The desktop assistant stays intentionally thinner than Flow. Settings exposes
gateway capability-default routes plus a bounded advanced `options` JSON
surface. That JSON is passed through unchanged for route features such as
`count`, `seeds`, `lora_adapters`, `guidance_2`, and `flow_shift` when the
selected route supports them.

## Documentation

Start with [docs/README.md](docs/README.md).

Core guides:

- [docs/INSTALLATION.md](docs/INSTALLATION.md)
- [docs/getting-started.md](docs/getting-started.md)
- [docs/api.md](docs/api.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/faq.md](docs/faq.md)
- [docs/troubleshooting.md](docs/troubleshooting.md)

Architecture records:

- [docs/adr/README.md](docs/adr/README.md)

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/basic tests/integration -q
```

## Project Links

- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- License: [LICENSE](LICENSE)
