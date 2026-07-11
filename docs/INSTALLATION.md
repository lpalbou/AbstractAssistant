# Installation

See also:
- [README.md](README.md) (docs hub)
- [getting-started.md](getting-started.md) (first run)

## Requirements (practical)

- **Python**: 3.10+
- **Tray UI**: macOS is the primary target. Other OSes may work through the Qt shell, but are not yet packaged to the same standard.
- **Gateway**: an AbstractGateway instance must be available
- **Published workflow**: the gateway must expose the `abstractassistant-orchestrator` workflow in
  the tenant catalog
- **Providers**:
  - local: LMStudio / Ollama must be configured on the gateway
  - cloud: API keys belong on the gateway side

## Install (PyPI)

```bash
pip install "abstractassistant"
```

For local microphone capture (voice conversations and dictation), install the `voice` extra
(the base install covers text chat and gateway-backed media, but not the local audio-input stack):

```bash
pip install "abstractassistant[voice]"
```

Verify:

```bash
assistant --help
```

Gateway startup for local development:

```bash
export ABSTRACTGATEWAY_FLOWS_DIR="$PWD/abstractgateway/flows/bundles"
export ABSTRACTGATEWAY_AUTH_TOKEN="your-shared-token"
abstractgateway serve --host 127.0.0.1 --port 8080
```

## macOS app build (optional)

For a real Finder-launchable `.app`, build the bundled macOS artifact with PyInstaller:

```bash
pip install -e ".[macos-app]"
build-macos-app
```

This builds a self-contained `AbstractAssistant.app` and installs it into `/Applications`.

If you are changing the macOS UI from source and want to verify the packaged app, rerun
`build-macos-app` after your change, quit any older `AbstractAssistant` menu-bar process, and then
relaunch `/Applications/AbstractAssistant.app`. Source-run tray behavior and the installed bundle
are not the same validation target.

If you want the bundle without installing it into `/Applications`, use:

```bash
build-macos-app --skip-install
```

That produces `dist/macos/AbstractAssistant.app`.

The bundle is currently **unsigned and un-notarized**. Building it yourself is fine (locally built
apps carry no quarantine attribute), but a copy you send to someone else will be blocked by
Gatekeeper ("cannot verify developer" / "damaged") until it is signed and notarized. The app is
also menu-bar only (`LSUIElement`), so it deliberately shows no Dock icon — look for the tray icon
in the top-right menu bar, not the Dock.

## Headless / terminal only

You can use the CLI without running the tray UI:

```bash
pip install abstractassistant
assistant run --prompt "Hello"
```

The CLI entrypoint is available as both `assistant` and `abstractassistant`.

Optional assistant-side overrides:
- `--gateway-url`
- `--gateway-token`

## Notes

- Gateway owns workflow discovery and multimodal capability defaults. The assistant does not need
  provider API keys or local model configuration files.
- AbstractAssistant does not bundle `ffmpeg`. If your provider/media pipeline relies on `ffmpeg` for video frame extraction, ensure it is on your PATH.

## Next

- [getting-started.md](getting-started.md)
- [api.md](api.md)
