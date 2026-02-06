# AbstractAssistant

One-click, tray-accessible agent host for AbstractFramework.

AbstractAssistant runs **agentic** loops (ReAct/CodeAct/MemAct) on top of:
- **AbstractAgent** (agent patterns)
- **AbstractRuntime** (durable runs, waits, ledgers)
- **AbstractCore** (provider/tool normalization)
- Optional: **AbstractVoice** (STT/TTS)

Docs:
- `docs/getting-started.md`
- `docs/architecture.md`

## Install profiles

- `abstractassistant` (default) == `lite`: tray UI + agent backend (no voice)
- `abstractassistant[all]`: voice (STT/TTS) + broader provider/media extras

```bash
pip install "abstractassistant"
# or
pip install "abstractassistant[all]"
```

## Quick start

Tray (macOS):
```bash
assistant tray
```

Alias:
```bash
abstractassistant tray
```

Terminal (one turn):
```bash
assistant run --prompt "What is in this repo and where do I start?"
```

Provider/model override:
```bash
assistant run --provider ollama --model qwen3:4b-instruct --prompt "Summarize my changes"
```

## Tool approvals (important)

AbstractAssistant enforces a durable tool boundary:
- read-only / known-safe tools can auto-run
- anything else pauses and requires approval (tray dialog or terminal prompt)

This aligns with the framework’s durability + safety model: tools are executed by the host, not persisted as callables inside run state.

## Data & durability

By default, assistant state is stored in `~/.abstractassistant/` (configurable via `--data-dir`):
- `session.json`: fast UI snapshot (transcript + last run id)
- `runtime/`: run store + ledger + artifacts (source of truth)

## Development

```bash
pip install -e ".[dev,lite]"   # base tray (no voice)
# or
pip install -e ".[dev,all]"    # voice (STT/TTS) + provider/media extras
python -m pytest -q
assistant tray --debug
```
- **📱 Unobtrusive**: Lives quietly in your menu bar until needed
- **🔊 Conversational**: Optional voice mode for natural AI interactions

## 📚 Documentation

| Guide | Description |
|-------|------------|
| [📖 Installation Guide](docs/INSTALLATION.md) | Complete setup instructions, prerequisites, and troubleshooting |
| [🎯 Getting Started Guide](docs/getting-started.md) | Step-by-step usage guide with all features explained |
| [🏗️ Architecture Guide](docs/architecture.md) | Technical documentation and development information |

## 📋 Requirements

- **macOS**: 10.14+ (Mojave or later)
- **Python**: 3.10+
- **Qt Framework**: PyQt5, PySide2, or PyQt6 (automatically detected)
- **Core deps**: AbstractAgent + AbstractRuntime (installed with `abstractassistant`)
- **Optional deps**: voice + provider/media extras via `abstractassistant[all]` (installs AbstractVoice + AbstractCore extras)

## 🤝 Contributing

Contributions welcome! Please read the architecture documentation and follow the established patterns:

- **Clean Code**: Follow PEP 8 and use type hints
- **Modular Design**: Keep components focused and reusable
- **Modern UI/UX**: Maintain the sleek, native feel
- **Error Handling**: Always include graceful fallbacks
- **Documentation**: Update docs for any new features

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

AbstractAssistant is built on excellent open-source projects:

### Core Dependencies
- **[AbstractCore](https://github.com/lpalbou/abstractcore)**: Universal LLM interface - enables seamless multi-provider support
- **[AbstractVoice](https://github.com/lpalbou/abstractvoice)**: High-quality text-to-speech engine with natural voice synthesis

### Framework & UI
- **[PyQt5/PySide2/PyQt6](https://www.qt.io/)**: Cross-platform GUI framework for the modern interface
- **[pystray](https://github.com/moses-palmer/pystray)**: Cross-platform system tray integration
- **[Pillow](https://python-pillow.org/)**: Image processing for dynamic icon generation

### Part of the AbstractX Ecosystem
AbstractAssistant integrates seamlessly with other AbstractX projects:
- 🧠 **[AbstractCore](https://github.com/lpalbou/abstractcore)**: Universal LLM provider interface
- 🗣️ **[AbstractVoice](https://github.com/lpalbou/abstractvoice)**: Advanced text-to-speech capabilities

See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) for complete attribution.

---

**Built with ❤️ for macOS users who want AI at their fingertips**
