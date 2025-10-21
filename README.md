# AbstractAssistant 🤖

Philosophy : *your AI assistant, always here and available in one click*

A sleek macOS system tray application providing instant access to Large Language Models with a modern Qt-based interface. Built with Python and powered by [AbstractCore](https://github.com/lpalbou/abstractcore) and [AbstractVoice](https://github.com/lpalbou/abstractvoice).

## 📦 Installation & Links

- **📋 GitHub Repository**: [https://github.com/lpalbou/abstractassistant](https://github.com/lpalbou/abstractassistant)
- **🐍 PyPI Package**: [https://pypi.org/project/abstractassistant/](https://pypi.org/project/abstractassistant/)
- **📚 Documentation**: See [docs/](docs/) folder for detailed guides

## ✨ Features

- **🎯 System Tray Integration**: Quick access from macOS menu bar - always at your fingertips
- **💬 Modern Qt Interface**: Clean, iPhone Messages-style chat bubble with dark theme
- **🔊 Voice Support**: Text-to-Speech integration with [AbstractVoice](https://github.com/lpalbou/abstractvoice) for conversational AI
- **🔄 Multi-Provider Support**: Seamlessly switch between LMStudio, Ollama, OpenAI, Anthropic, MLX, HuggingFace via [AbstractCore](https://github.com/lpalbou/abstractcore)
- **📊 Real-time Status**: Live token counting, provider/model selection, and animated status indicators
- **💾 Session Management**: Save, load, and view conversation history with markdown rendering
- **⚙️ Smart Controls**: Provider/model dropdowns, TTS toggle, and session buttons
- **🎨 Professional Design**: Rounded corners, smooth animations, and native macOS feel

## 🚀 Quick Start

### 1. Installation

#### 🍎 macOS Users (Recommended)
```bash
# Install AbstractAssistant
pip install abstractassistant

# Create native macOS app bundle
create-app-bundle
```

This will:
- Install AbstractAssistant from PyPI with all dependencies
- Create a native macOS app bundle in `/Applications`
- Add AbstractAssistant to your Dock with a beautiful neural network icon
- Enable launch from Spotlight, Finder, and Dock

#### 🔧 Standard Installation
```bash
# Install from PyPI (terminal access only)
pip install abstractassistant
```

For detailed installation instructions including prerequisites and voice setup, see **[📖 Installation Guide](docs/installation.md)**.

### 2. First Launch

#### 🍎 macOS App Bundle Users
- **Dock**: Click the AbstractAssistant icon in your Dock
- **Spotlight**: Search for "AbstractAssistant" and press Enter
- **Finder**: Open `/Applications/AbstractAssistant.app`

#### 🔧 Terminal Users
```bash
# Launch the assistant
assistant

# Create macOS app bundle after installation
create-app-bundle
```

### 3. Start Using
1. **Find the Icon**: Look for AbstractAssistant in your macOS menu bar (top-right)
2. **Click to Open**: Click the icon to open the chat bubble
3. **Start Chatting**: Type your message and send!

For a complete walkthrough of all features, see **[🎯 Getting Started Guide](docs/getting-started.md)**.

### 📋 Prerequisites
- **macOS**: 10.14+ (Mojave or later)
- **Python**: 3.9+
- **Models**: Local (LMStudio/Ollama) or API keys (OpenAI/Anthropic)

See **[⚙️ Installation Guide](docs/installation.md)** for detailed setup instructions.

## 🎮 Usage Overview

AbstractAssistant provides a clean, intuitive interface for AI conversations:

### 🖱️ Main Interface
- **Chat Bubble**: Modern iPhone Messages-style interface
- **Provider/Model Selection**: Easy switching between AI providers
- **Voice Support**: Optional text-to-speech for responses
- **Session Management**: Save, load, and view conversation history

### 🎙️ Voice Features
- **Text-to-Speech**: Powered by [AbstractVoice](https://github.com/lpalbou/abstractvoice)
- **High-Quality Speech**: Natural-sounding voice synthesis
- **Simple Controls**: One-click enable/disable

### 🔧 System Integration
- **System Tray**: Always accessible from macOS menu bar
- **Native Feel**: Designed for macOS with smooth animations
- **Lightweight**: Minimal resource usage when idle

**👉 For detailed usage instructions, see [🎯 Getting Started Guide](docs/getting-started.md)**

## ⚙️ Configuration

Create a `config.toml` file to customize settings:

```toml
[ui]
theme = "dark"
always_on_top = true

[llm]
default_provider = "lmstudio"
default_model = "qwen/qwen3-next-80b"
max_tokens = 128000
temperature = 0.7

[system_tray]
icon_size = 64
```

### API Keys Setup

Set your API keys as environment variables:

```bash
# For OpenAI
export OPENAI_API_KEY="your_openai_key_here"

# For Anthropic
export ANTHROPIC_API_KEY="your_anthropic_key_here"

# For local models (LMStudio, Ollama), no API key needed
```

## 🏗️ Architecture

AbstractAssistant is built on a modern, modular architecture:

- **[AbstractCore](https://github.com/lpalbou/abstractcore)**: Universal LLM provider interface
- **[AbstractVoice](https://github.com/lpalbou/abstractvoice)**: High-quality text-to-speech engine
- **Qt Interface**: Cross-platform GUI (PyQt5/PySide2/PyQt6 support)
- **System Integration**: Native macOS system tray with `pystray`
- **Session Management**: Persistent conversation history and settings

**👉 For technical details, see [🏗️ Architecture Guide](docs/architecture.md)**

## 🔧 Development

### Running from Source

```bash
# Clone the repository
git clone https://github.com/lpalbou/abstractassistant.git
cd abstractassistant

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e .

# Run with debug mode
assistant --debug
```

### Project Structure

```
abstractassistant/
├── pyproject.toml          # Package configuration
├── requirements.txt        # Dependencies
├── config.toml            # Default configuration
├── abstractassistant/     # Main package
│   ├── cli.py            # CLI entry point
│   ├── app.py            # Main application
│   ├── config.py         # Configuration management
│   ├── core/             # Business logic
│   │   ├── llm_manager.py    # LLM provider management
│   │   └── tts_manager.py    # Voice/TTS integration
│   ├── ui/               # User interface
│   │   ├── qt_bubble.py      # Main Qt chat interface
│   │   └── toast_window.py   # Notification system
│   └── utils/            # Utilities
│       ├── icon_generator.py # Dynamic icon creation
│       └── markdown_renderer.py # Markdown processing
└── docs/                 # Documentation
    ├── ARCHITECTURE.md   # Technical documentation
    ├── INSTALLATION.md   # Installation guide
    └── USAGE.md         # Usage guide
```

## 🌟 Why AbstractAssistant?

- **🎯 Focused**: Designed specifically for quick AI interactions
- **🎨 Beautiful**: Modern Qt interface with native macOS feel
- **⚡ Fast**: Instant access without opening heavy applications
- **🔄 Flexible**: Support for multiple AI providers in one interface
- **🛡️ Robust**: Built with error handling and graceful fallbacks
- **📱 Unobtrusive**: Lives quietly in your menu bar until needed
- **🔊 Conversational**: Optional voice mode for natural AI interactions

## 📚 Documentation

| Guide | Description |
|-------|------------|
| [📖 Installation Guide](docs/installation.md) | Complete setup instructions, prerequisites, and troubleshooting |
| [🎯 Getting Started Guide](docs/getting-started.md) | Step-by-step usage guide with all features explained |
| [🏗️ Architecture Guide](docs/architecture.md) | Technical documentation and development information |

## 📋 Requirements

- **macOS**: 10.14+ (Mojave or later)
- **Python**: 3.9+
- **Qt Framework**: PyQt5, PySide2, or PyQt6 (automatically detected)
- **Dependencies**: [AbstractCore](https://github.com/lpalbou/abstractcore) and [AbstractVoice](https://github.com/lpalbou/abstractvoice) (automatically installed)

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