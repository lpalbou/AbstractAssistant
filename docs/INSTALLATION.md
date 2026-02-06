# Installation

For a quick walkthrough, start with `getting-started.md`.

## Install profiles

- `abstractassistant` (default) == `lite`: tray UI + agent backend (no voice)
- `abstractassistant[all]`: voice (STT/TTS) + broader provider/media extras

```bash
pip install "abstractassistant"
# or
pip install "abstractassistant[all]"
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

If you want only the CLI (no tray UI), you can install without extras and use:

```bash
pip install abstractassistant
assistant run --prompt "Hello"
```

The CLI entrypoint is available as both `assistant` and `abstractassistant`.
