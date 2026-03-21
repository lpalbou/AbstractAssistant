# Installation

See also:
- [README.md](README.md) (docs hub)
- [getting-started.md](getting-started.md) (first run)

## Requirements (practical)

- **Python**: 3.10+
- **Tray UI**: macOS is the primary target (menu bar app). Other OSes may work via `pystray`/Qt but are not the focus.
- **Gateway**: an AbstractGateway instance must be available
- **Providers**:
  - local: LMStudio / Ollama must be configured on the gateway
  - cloud: API keys belong on the gateway side

## Install (PyPI)

```bash
pip install "abstractassistant"
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

## macOS app bundle (optional)

AbstractAssistant ships a helper that creates a native app bundle under `/Applications`:

```bash
create-app-bundle
```

Notes:
- requires macOS (`iconutil` is used to build `icon.icns`)
- may require permissions to write to `/Applications`

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

- AbstractAssistant does not bundle `ffmpeg`. If your provider/media pipeline relies on `ffmpeg` for video frame extraction, ensure it is on your PATH.

## Next

- [getting-started.md](getting-started.md)
- [api.md](api.md)
