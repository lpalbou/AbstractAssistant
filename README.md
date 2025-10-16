# AbstractAssistant 🤖

A sleek macOS system tray application providing instant access to LLMs with a modern, glassy UI. Built with Python and powered by [AbstractCore](https://www.abstractcore.ai/).

![AbstractAssistant Demo](assets/demo.gif)

## ✨ Features

- **🎯 System Tray Integration**: Quick access from macOS menu bar - always at your fingertips
- **🌐 Beautiful Web Interface**: Modern, responsive web UI with glassmorphism design and smooth animations
- **🎨 Stunning Visual Design**: Dark/light themes, gradient backgrounds, and professional typography
- **🔄 Multi-Provider Support**: Seamlessly switch between OpenAI, Anthropic, Ollama, and more via AbstractCore
- **📊 Real-time Status**: Live token counting, provider/model selection, and execution status
- **💬 Modern Chat Experience**: Elegant message bubbles with markdown rendering and syntax highlighting
- **⚙️ Advanced Settings**: Temperature control, token limits, and theme customization
- **⚡ WebSocket Communication**: Real-time bidirectional communication between web UI and Python backend
- **📱 Responsive Design**: Works perfectly on desktop and mobile browsers

## 🚀 Quick Start

### Installation

```bash
# Clone or download the project
cd abstractassistant

# Create virtual environment (recommended)
python3.12 -m venv .venv
source .venv/bin/activate

# Install the package
pip install -e .
```

### Launch Commands

```bash
# Simple launch (no parameters needed!)
assistant

# With custom provider
assistant --provider anthropic --model claude-3-5-sonnet-20241022

# With debug mode
assistant --debug

# With custom config
assistant --config my-config.toml

# Show help
assistant --help
```

### First Run

1. **Launch**: Run `assistant` in your terminal (with virtual environment activated)
2. **Look for the Icon**: Check your macOS menu bar (top-right) for the AbstractAssistant icon
3. **Open Web Interface**: Click the icon to launch the beautiful web interface in your browser
4. **Enjoy the Modern UI**: Experience the glassmorphism design with smooth animations
5. **Start Chatting**: Type your message in the elegant input area and click send

> **Note**: If you get a conflict with macOS's built-in Assistant, the command is installed in your virtual environment. Make sure to activate it with `source .venv/bin/activate` first.

### API Keys Setup

Set your API keys as environment variables:

```bash
# For OpenAI
export OPENAI_API_KEY="your_openai_key_here"

# For Anthropic
export ANTHROPIC_API_KEY="your_anthropic_key_here"

# For local models (Ollama), no API key needed
```

## 🎮 Usage

### Web Interface

1. **Open Interface**: Click the system tray icon to launch the web UI
2. **Beautiful Design**: Enjoy the modern glassmorphism interface with smooth animations
3. **Select Provider**: Choose from OpenAI, Anthropic, or Ollama using the elegant dropdowns
4. **Pick Model**: Select your preferred model (e.g., GPT-4o, Claude 3.5 Sonnet, Qwen3)
5. **Type Message**: Enter your question in the responsive input area
6. **Send**: Click the gradient send button or press Cmd+Enter
7. **Real-time Response**: Watch AI responses appear with beautiful animations and markdown formatting
8. **Settings**: Click the settings icon to customize theme, temperature, and other preferences

### System Tray Menu

- **Open Web Interface**: Launch the beautiful web UI (default action)
- **Providers**: Quick provider switching (OpenAI, Anthropic, Ollama)
- **Quit**: Exit the application

### Keyboard Shortcuts

- **Cmd+Enter**: Send message in web interface
- **Cmd+C**: Copy response content (in expanded toast)
- **Escape**: Close chat bubble

## ⚙️ Configuration

Edit `config.toml` to customize:

```toml
[ui]
theme = "dark"  # dark, light, system
bubble_size_ratio = 0.167  # 1/6th of screen
auto_hide_delay = 8  # toast auto-hide seconds
always_on_top = true

[llm]
default_provider = "openai"
default_model = "gpt-4o-mini"
max_tokens = 32000
temperature = 0.7

[system_tray]
icon_size = 64
show_notifications = true

[shortcuts]
show_bubble = "cmd+shift+a"
```

## 🏗️ Architecture

AbstractAssistant follows a modular, robust design:

- **System Tray**: Native macOS integration with pystray
- **Chat UI**: Modern interface with CustomTkinter
- **LLM Manager**: Universal provider support via AbstractCore
- **Toast System**: Elegant notifications with markdown rendering
- **Icon Generator**: Dynamic, AI-inspired system tray icons

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed technical documentation.

## 🔧 Development

### Running Tests

```bash
python test_app.py
```

### Project Structure

```
abstractassistant/
├── pyproject.toml       # Package configuration
├── main.py              # Legacy entry point
├── abstractassistant/   # Main package
│   ├── cli.py          # CLI entry point
│   ├── config.py       # Configuration management
│   ├── app.py          # Main application
│   ├── web_server.py   # Web server with WebSocket support
│   ├── core/           # Business logic
│   └── utils/          # Utilities
├── web/                # Modern web interface
│   ├── index.html      # Main HTML with glassmorphism design
│   ├── styles.css      # Beautiful CSS with animations
│   └── app.js          # WebSocket client and UI logic
├── config.toml         # Configuration
└── requirements.txt    # Dependencies
```

## 🌟 Why AbstractAssistant?

- **🎯 Focused**: Designed specifically for quick AI interactions
- **🎨 Beautiful**: Modern web interface with glassmorphism design and smooth animations
- **⚡ Fast**: Instant access without opening heavy applications
- **🔄 Flexible**: Support for multiple AI providers in one interface
- **🛡️ Robust**: Built with error handling and graceful fallbacks
- **📱 Unobtrusive**: Lives quietly in your menu bar until needed
- **🌐 Modern**: Web-based UI that's responsive and works across devices

## 📋 Requirements

- **macOS**: 10.14+ (Mojave or later)
- **Python**: 3.9+
- **Dependencies**: Automatically installed via requirements.txt

## 🤝 Contributing

Contributions welcome! Please read the architecture documentation and follow the established patterns:

- **Robust General-Purpose Logic**: Design for real-world scenarios
- **Modular Design**: Keep components focused and reusable
- **Modern UI/UX**: Maintain the sleek, native feel
- **Error Handling**: Always include graceful fallbacks

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- **AbstractCore**: Universal LLM interface library
- **CustomTkinter**: Modern Tkinter styling
- **pystray**: Cross-platform system tray support

---

**Built with ❤️ for macOS users who want AI at their fingertips**
