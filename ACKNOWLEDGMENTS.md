# Acknowledgments

AbstractAssistant is built on top of a number of open-source projects. We’re grateful to all maintainers and contributors.

This list is not exhaustive. The source of truth for install-time dependencies is `pyproject.toml`.

## AbstractFramework ecosystem

- **AbstractCore** — providers, tool/media schemas, LLM client helpers: https://github.com/lpalbou/abstractcore
- **AbstractRuntime** — durable runs, waits, ledger, artifacts: https://github.com/lpalbou/abstractruntime
- **AbstractAgent** — agent loops (ReAct/CodeAct/MemAct): https://github.com/lpalbou/abstractagent
- **AbstractVoice** — STT/TTS integration used by the tray UI: https://github.com/lpalbou/abstractvoice

## UI and desktop integration

- **pystray** — system tray integration: https://github.com/moses-palmer/pystray
- **PyQt5 / PySide2 / PyQt6** — Qt bindings used by the tray bubble UI
- **Pillow** — image utilities (tray icons)

## Rendering and UX helpers

- **markdown** + **pymdown-extensions** — Markdown rendering
- **Pygments** — syntax highlighting
- **pyperclip** — clipboard integration
- **plyer** — native notifications

## Configuration and packaging

- **tomli** / **tomli-w** — TOML parsing/writing (Python version compatibility)
- **setuptools** / **wheel** — build tooling

## Development tooling

- **pytest**, **black**, **isort**, **mypy**
