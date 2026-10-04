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

- A menu-bar palette whose title tells you what the app is doing, with a session switcher fed by
  the gateway (your sessions from every device, optionally every client's) and a live gateway
  connection orb.
- Automations: schedule a conversation to run on the gateway at a fixed UTC interval or when an
  email arrives (with the result emailed to you if you want), read its runs
  as a chat, switch it off or on (**Active**), run it now, edit or archive it, answer the runs that wait for you, discuss a
  result, and get a tray notification only when a result is notable, a run fails or a run waits for
  you. See [docs/automations.md](docs/automations.md).
- Live run activity in the transcript: the current step, elapsed time, recent tool calls with
  their arguments and durations, and pause / resume / stop controls.
- Live replies: with **Stream replies** on (or left to a gateway that streams by default), the
  answer appears while the model writes it, with its reasoning folded away under **Thinking**;
  the finished answer replaces the live text.
- Tool approvals in a modeless sheet that shows the gateway's risk tier for each call and never
  blocks the palette; "always allow on this Mac" and per-chat trust for low-risk tools.
- A voice conversation mode (⌘⇧V): listen, send, speak, listen again — with a live status strip.
  Spoken replies stream from the gateway; dictation is a button away.
- A Settings window with seven sections: Connection, Models & reasoning (workflow, reasoning
  effort, reply streaming), Voice, Workspace (workspace folders and run folder), Tools & permissions,
  Appearance & window, About. Every value says whether it is the gateway default or this app's
  override. About is also on the menu-bar icon (**About AbstractAssistant…**).
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

Requirements: Python 3.10+, an AbstractGateway you can reach. AbstractCore is installed as a
dependency (its minimum version is set in `pyproject.toml`). macOS is the primary tray target;
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

`--gateway-url` on its own is enough when you have already signed in to that gateway: the app
reuses the sign-in saved in `~/.abstractassistant/gateway_connection.json`.

If the gateway runs the AbstractGateway console, the simplest way to start the assistant is
**Open** on its card there: the console launches the app already signed in as you, and the app
remembers that sign-in for later launches. The console can sign in only an Assistant it launches,
so quit a running Assistant before you click **Open**.

Each turn runs the gateway's default workflow for the assistant (`abstractassistant.agent.v1`).
When the gateway sets none, the app runs its built-in orchestrator, the
`abstractassistant-orchestrator` workflow it publishes to your tenant catalog. You can pick
another assistant workflow in Settings → Models → Workflow; the list holds only the assistant
workflows the gateway says you can run (what your admin made available, plus your own:
`GET /api/gateway/bundles?executable_for=abstractassistant.agent.v1`).

## Defaults and durability

The gateway is the source of truth for the published workflow, provider and model defaults, tool
inventory and approval defaults, workspace policy, run history, waits and artifacts.

The desktop client stores under `~/.abstractassistant/`:

- `preferences.json` — this app's overrides and preferences (model routes, reasoning effort,
  reply streaming, workspace grant, voice options, tool modes, hotkey, window size)
- `gateway_connection.json` — gateway URL and sign-in state
- `session_cache.json`, `sessions/` — a rebuildable cache of the gateway's sessions (local labels,
  cached transcripts, each session's granted workspace folder); the sessions themselves live on
  the gateway
- `automations_notified.json` — which automation notifications were already shown; automations
  themselves live on the gateway
- downloads and cached audio

## Documentation

Start with [docs/README.md](docs/README.md).

- [docs/INSTALLATION.md](docs/INSTALLATION.md)
- [docs/getting-started.md](docs/getting-started.md)
- [docs/settings.md](docs/settings.md)
- [docs/voice.md](docs/voice.md)
- [docs/automations.md](docs/automations.md)
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
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Acknowledgments: [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)
- License: [LICENSE](LICENSE)
