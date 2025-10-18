# AbstractAssistant 🤖

A sleek macOS system tray application providing instant access to Large Language Models with a modern Qt-based interface. Built with Python and powered by [AbstractCore](https://www.abstractcore.ai/).

## ✨ Features

- **🎯 System Tray Integration**: Quick access from macOS menu bar - always at your fingertips
- **💬 Modern Qt Interface**: Clean, iPhone Messages-style chat bubble with dark theme
- **🔊 Voice Support**: Text-to-Speech integration with VoiceLLM for conversational AI
- **🔄 Multi-Provider Support**: Seamlessly switch between LMStudio, OpenAI, Anthropic, Ollama, and more via AbstractCore
- **📊 Real-time Status**: Live token counting, provider/model selection, and animated status indicators
- **💾 Session Management**: Save, load, and view conversation history with markdown rendering
- **⚙️ Smart Controls**: Provider/model dropdowns, TTS toggle, and session buttons
- **🎨 Professional Design**: Rounded corners, smooth animations, and native macOS feel

## 🚀 Quick Start

### Installation

```bash
# Install from PyPI (recommended)
pip install abstractassistant

# Or install from source
git clone https://github.com/lpalbou/abstractassistant.git
cd abstractassistant
pip install -e .
```

### Launch

```bash
# Simple launch (no parameters needed!)
assistant

# With custom provider and model
assistant --provider lmstudio --model qwen/qwen3-next-80b

# With debug mode
assistant --debug

# With custom config
assistant --config my-config.toml

# Show help
assistant --help
```

### First Run

1. **Launch**: Run `assistant` in your terminal
2. **Look for the Icon**: Check your macOS menu bar (top-right) for the AbstractAssistant icon
3. **Click to Chat**: Click the icon to open the modern Qt chat bubble
4. **Start Conversing**: Type your message and press Shift+Enter or click the send button

## 🎮 Usage

### Chat Interface

The main interface is a sleek Qt-based chat bubble that appears when you click the system tray icon:

- **Provider Selection**: Choose from LMStudio, OpenAI, Anthropic, Ollama, and more
- **Model Selection**: Pick your preferred model (automatically populated based on provider)
- **Text Input**: Type your message in the input area
- **Send**: Press Shift+Enter or click the blue send button (→)
- **Voice Mode**: Toggle the TTS switch for spoken responses
- **Session Controls**: Clear, Load, Save, and view History

### Session Management

- **Clear**: Start a fresh conversation
- **Save**: Save current conversation to file
- **Load**: Load a previous conversation
- **History**: View all messages in iPhone Messages-style dialog

### Voice Features

- **TTS Toggle**: Click the speaker icon to enable/disable Text-to-Speech
- **Voice Mode**: When enabled, AI responses are spoken aloud using VoiceLLM
- **Smart Prompting**: In voice mode, the AI uses shorter, conversational responses

### System Tray

- **Single Click**: Open/close the chat bubble
- **Animated Icon**: Visual feedback showing AI status (ready/generating)
- **Always Available**: Minimal resource usage when idle

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

AbstractAssistant follows a clean, modular design:

- **System Tray**: Native macOS integration with `pystray`
- **Qt Interface**: Modern chat bubble using PyQt5/PySide2/PyQt6
- **LLM Manager**: Universal provider support via AbstractCore
- **Voice Integration**: Text-to-Speech with VoiceLLM
- **Session Management**: Persistent conversation history
- **Icon Generator**: Dynamic, animated system tray icons

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed technical documentation.

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
│   │   ├── toast_window.py   # Notification system
│   │   └── bubble_window.py  # Alternative webview interface
│   └── utils/            # Utilities
│       ├── icon_generator.py # Dynamic icon creation
│       └── markdown_renderer.py # Markdown processing
├── web/                  # Web interface assets (alternative UI)
│   ├── index.html        # Full web interface
│   ├── bubble.html       # Bubble-specific interface
│   ├── styles.css        # Web styling
│   └── app.js           # Web application logic
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

## 📋 Requirements

- **macOS**: 10.14+ (Mojave or later)
- **Python**: 3.9+
- **Qt**: PyQt5, PySide2, or PyQt6 (automatically detected)
- **Dependencies**: Automatically installed via pip

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

This project is built on top of excellent open-source libraries:

- **[AbstractCore](https://www.abstractcore.ai/)**: Universal LLM interface library - the foundation that makes multi-provider support seamless
- **[VoiceLLM](https://github.com/lpalbou/voicellm)**: High-quality Text-to-Speech integration
- **[PyQt5/PySide2/PyQt6](https://www.qt.io/)**: Cross-platform GUI framework for the modern interface
- **[pystray](https://github.com/moses-palmer/pystray)**: Cross-platform system tray support
- **[Pillow](https://python-pillow.org/)**: Image processing for dynamic icon generation

See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) for complete attribution.

---

**Built with ❤️ for macOS users who want AI at their fingertips**