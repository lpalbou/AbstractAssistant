# Installation

For a quick walkthrough, start with `getting-started.md`.

## Install

```bash
pip install "abstractassistant"
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

If you want only the CLI (no tray UI), install and use:

```bash
pip install abstractassistant
assistant run --prompt "Hello"
```

The CLI entrypoint is available as both `assistant` and `abstractassistant`.

## Notes

- Video frame-sampling fallback (for non-video-native models) may require `ffmpeg` on your PATH.
