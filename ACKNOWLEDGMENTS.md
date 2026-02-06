# Acknowledgments

AbstractAssistant is built on top of a number of open-source projects. We’re grateful to all maintainers and contributors.

This list is not exhaustive. The source of truth for install-time dependencies is `pyproject.toml`.

## Core libraries

Agent/runtime foundations:
- **AbstractAgent** — agent loop + tool calling interface
- **AbstractRuntime** — durable runs/session storage + tool execution boundary
- **AbstractCore** — provider-agnostic LLM interface (`create_llm`) and provider/model utilities

UI and desktop integration:
- **PyQt5** — native UI framework
- **pystray** — menu bar / system tray integration
- **Pillow** — tray icon rendering and image utilities

Rendering and UX helpers:
- **markdown**, **pymdown-extensions** — Markdown rendering
- **Pygments** — syntax highlighting
- **pyperclip** — clipboard integration
- **plyer** — native notifications

Configuration:
- **tomli** / **tomli-w** — TOML parsing/writing (compatibility across Python versions)

## Optional extras

- **AbstractVoice** — voice/audio capabilities (installed via `abstractassistant[all]` when enabled)

## Development tooling

- **pytest**, **black**, **isort**, **mypy**
