# Getting Started

AbstractAssistant is a tray-first gateway client. It does not host providers or durable workflows
locally. Instead, it connects to AbstractGateway, runs each turn through the published
`abstractassistant-orchestrator` assistant workflow in the gateway catalog, and uses gateway
capability defaults.

See also:

- [INSTALLATION.md](INSTALLATION.md)
- [architecture.md](architecture.md)
- [troubleshooting.md](troubleshooting.md)

## 1. Install

```bash
pip install "abstractassistant"
```

## 2. Start A Gateway

For local development, make sure the gateway loads workflow bundles and exposes an auth token the
assistant can use:

```bash
export ABSTRACTGATEWAY_FLOWS_DIR="$PWD/abstractgateway/flows/bundles"
export ABSTRACTGATEWAY_AUTH_TOKEN="your-shared-token"
abstractgateway serve --host 127.0.0.1 --port 8080
```

If the gateway cannot expose a published assistant workflow, the assistant fails closed instead of
falling back to a different runtime path.

## 3. Launch The Assistant

Tray app:

```bash
assistant
```

Terminal turn:

```bash
assistant run --prompt "Search the web for the latest OpenAI news and summarize it with sources."
```

Optional overrides:

```bash
assistant --gateway-url http://127.0.0.1:8080 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN"
```

## 4. Use The Tray And Palette

The desktop shell is a compact top-right palette with a tray icon.

For hosted gateways with user auth enabled, open **Settings** and use the `Gateway connection`
section to sign in with a gateway user token. For local/shared setups, a bearer token remains fine.

Typical flow:

1. Open the palette from the tray, or use the global summon hotkey when available.
2. Ask a question or attach files.
3. Let the published `abstractassistant-orchestrator` workflow decide whether the turn needs normal
   chat, tools, or media generation.
4. Approve tool batches when the workflow requests them.

You do not choose a workflow in the normal tray path. The gateway publishes the assistant workflow,
and the desktop app uses that workflow directly.

The default summon hotkey is `cmd+shift+space` when global hotkey support is available on your
machine. If your platform or permissions do not allow global hooks, the assistant still works from
the tray icon.

## 5. Configure Defaults In The Right Place

Gateway owns multimodal provider/model defaults. The assistant Settings window edits those gateway
defaults through capability-default routes.

Use Settings for three different kinds of state:

- `Gateway connection`: gateway URL plus either a bearer token or a hosted gateway session
- `Gateway-owned defaults`: text understanding, voice output, STT, image/video/music routes
- `Local preferences`: hotkey enablement, auto-speak, palette size, bottom gap

Local provider/model selections are not the source of truth. Gateway defaults are.

For gateway image/video routes, Settings keeps the provider/model selectors
typed and keeps advanced route parameters in the `options` JSON field. Supported
Gateway/Core vision options include:

- `count`
- `seeds`
- `lora_adapters`
- `guidance_2`
- `flow_shift` on compatible video routes

## 6. Sessions And Requests

The desktop app remembers:

- transcript snapshots
- the last run id

Attachments can be added with the file picker or drag-and-drop.

When the assistant workflow returns media artifacts, the desktop client keeps
the full response payload and opens downloaded artifacts locally.

## 7. Voice

Microphone capture and playback happen locally on the desktop. STT and TTS requests are sent to
gateway routes.

If gateway voice routes are not configured, the assistant disables the affected controls instead of
quietly falling back to a local speech model.

## 8. Local Data

By default, local state is stored under `~/.abstractassistant/`.

That data includes:

- session registry and snapshots
- gateway connection state
- local downloads
- palette/tray preferences

Gateway remains the durability source of truth for run history, waits, and generated artifacts.

## Next

- [api.md](api.md)
- [architecture.md](architecture.md)
- [faq.md](faq.md)
- [troubleshooting.md](troubleshooting.md)
