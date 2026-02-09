# Installation

See also:
- [README.md](README.md) (docs hub)
- [getting-started.md](getting-started.md) (first run)

## Requirements (practical)

- **Python**: 3.10+
- **Tray UI**: macOS is the primary target (menu bar app). Other OSes may work via `pystray`/Qt but are not the focus.
- **Providers**:
  - local: LMStudio / Ollama must be running
  - cloud: set API keys via environment variables (for example `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)

## Install (PyPI)

```bash
pip install "abstractassistant"
```

Verify:

```bash
assistant --help
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

## Notes

- AbstractAssistant does not bundle `ffmpeg`. If your provider/media pipeline relies on `ffmpeg` for video frame extraction, ensure it is on your PATH.

## Next

- [getting-started.md](getting-started.md)
- [api.md](api.md)
