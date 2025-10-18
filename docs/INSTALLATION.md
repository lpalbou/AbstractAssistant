# Installation Guide

This guide covers different ways to install and set up AbstractAssistant on your macOS system.

## Quick Install (Recommended)

### From PyPI

```bash
# Install the latest stable version
pip install abstractassistant

# Launch immediately
assistant
```

### From Source (Latest Features)

```bash
# Clone the repository
git clone https://github.com/lpalbou/abstractassistant.git
cd abstractassistant

# Install in development mode
pip install -e .

# Launch
assistant
```

## Detailed Installation

### Prerequisites

- **macOS**: 10.14+ (Mojave or later)
- **Python**: 3.9 or higher
- **pip**: Latest version recommended

### Step 1: Python Environment (Recommended)

Create a virtual environment to avoid conflicts:

```bash
# Create virtual environment
python3 -m venv ~/.venvs/abstractassistant

# Activate it
source ~/.venvs/abstractassistant/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### Step 2: Install AbstractAssistant

Choose one of these methods:

#### Option A: PyPI (Stable)
```bash
pip install abstractassistant
```

#### Option B: GitHub (Latest)
```bash
pip install git+https://github.com/lpalbou/abstractassistant.git
```

#### Option C: Local Development
```bash
git clone https://github.com/lpalbou/abstractassistant.git
cd abstractassistant
pip install -e .
```

### Step 3: Verify Installation

```bash
# Check if command is available
assistant --version

# Test launch (should show system tray icon)
assistant --debug
```

## Optional Dependencies

### Voice Features (Recommended)

For Text-to-Speech capabilities:

```bash
# Install VoiceLLM and dependencies
pip install voicellm>=0.1.9

# For best voice quality, install espeak-ng
brew install espeak-ng
```

### Qt Framework

AbstractAssistant automatically detects and uses available Qt frameworks:

```bash
# Option 1: PyQt5 (most common)
pip install PyQt5

# Option 2: PySide2 (alternative)
pip install PySide2

# Option 3: PyQt6 (latest)
pip install PyQt6
```

*Note: At least one Qt framework is required for the GUI.*

## Configuration

### API Keys

Set up your API keys for different providers:

```bash
# OpenAI
export OPENAI_API_KEY="your_openai_key_here"

# Anthropic
export ANTHROPIC_API_KEY="your_anthropic_key_here"

# Add to your shell profile for persistence
echo 'export OPENAI_API_KEY="your_key"' >> ~/.zshrc
```

### Configuration File

Create a custom configuration file:

```bash
# Create config directory
mkdir -p ~/.config/abstractassistant

# Create config file
cat > ~/.config/abstractassistant/config.toml << EOF
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
EOF
```

## Local LLM Setup

### LMStudio (Recommended)

1. Download and install [LMStudio](https://lmstudio.ai/)
2. Download a model (e.g., Qwen3-Next-80B)
3. Start the local server
4. AbstractAssistant will automatically detect it

### Ollama

```bash
# Install Ollama
brew install ollama

# Start Ollama service
ollama serve

# Pull a model
ollama pull qwen2.5:latest
```

## Troubleshooting

### Common Issues

#### "assistant: command not found"
```bash
# Make sure virtual environment is activated
source ~/.venvs/abstractassistant/bin/activate

# Or install globally
pip install --user abstractassistant
```

#### "No Qt library available"
```bash
# Install a Qt framework
pip install PyQt5
```

#### "VoiceLLM not available"
```bash
# Install voice dependencies
pip install voicellm coqui-tts openai-whisper PyAudio

# On macOS, you might need
brew install portaudio
```

#### System Tray Icon Not Appearing
- Check macOS System Preferences > Security & Privacy
- Allow AbstractAssistant in Accessibility settings if prompted
- Try running with `--debug` flag for more information

### Debug Mode

Run with debug mode for detailed logging:

```bash
assistant --debug
```

### Clean Reinstall

If you encounter issues:

```bash
# Uninstall
pip uninstall abstractassistant

# Clear cache
pip cache purge

# Reinstall
pip install abstractassistant
```

## Advanced Setup

### Shell Integration

Add to your shell profile for easy access:

```bash
# Add to ~/.zshrc or ~/.bash_profile
alias ai="assistant"
alias assistant-debug="assistant --debug"

# Function for quick provider switching
function ai-openai() {
    assistant --provider openai --model gpt-4o
}

function ai-claude() {
    assistant --provider anthropic --model claude-3-5-sonnet-20241022
}
```

### Startup Integration

To start AbstractAssistant automatically on login:

1. Open System Preferences > Users & Groups
2. Click your user account
3. Go to Login Items
4. Add AbstractAssistant to the list

Or create a LaunchAgent:

```bash
# Create LaunchAgent directory
mkdir -p ~/Library/LaunchAgents

# Create plist file
cat > ~/Library/LaunchAgents/com.abstractassistant.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.abstractassistant</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/your/venv/bin/assistant</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

# Load the agent
launchctl load ~/Library/LaunchAgents/com.abstractassistant.plist
```

## Updating

### PyPI Installation
```bash
pip install --upgrade abstractassistant
```

### Source Installation
```bash
cd abstractassistant
git pull origin main
pip install -e .
```

## Uninstallation

```bash
# Uninstall the package
pip uninstall abstractassistant

# Remove configuration (optional)
rm -rf ~/.config/abstractassistant

# Remove LaunchAgent (if created)
launchctl unload ~/Library/LaunchAgents/com.abstractassistant.plist
rm ~/Library/LaunchAgents/com.abstractassistant.plist
```

---

For more help, see the [main README](../README.md) or open an issue on [GitHub](https://github.com/lpalbou/abstractassistant/issues).
