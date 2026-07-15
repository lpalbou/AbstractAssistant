# Acknowledgments

AbstractAssistant is built on top of a number of open-source projects. We’re grateful to all maintainers and contributors.

This list is not exhaustive. The source of truth for install-time dependencies is `pyproject.toml`.

## AbstractFramework ecosystem

- **AbstractGateway** — workflows, durable execution, providers, and media routing (the assistant is a thin client of it): https://github.com/lpalbou/abstractgateway
- **AbstractRuntime** — durable runs, waits, ledger, artifacts, and the session-memory run-id contract: https://github.com/lpalbou/abstractruntime
- **AbstractCore** — configuration and schema helpers: https://github.com/lpalbou/abstractcore
- **AbstractVoice** — microphone capture and in-process audio playback used by the tray UI: https://github.com/lpalbou/abstractvoice

## UI and desktop integration

- **PyQt5** — Qt bindings for the tray palette UI
- **Pillow** — image utilities (tray icons)
- **pynput** — optional global hotkey support

## Rendering and UX helpers

- **markdown-it-py** — Markdown rendering
- **Pygments** — syntax highlighting

## Packaging

- **setuptools** / **wheel** — build tooling
- **PyInstaller** — macOS app bundle builds

## Development tooling

- **pytest**, **black**, **isort**, **mypy**
