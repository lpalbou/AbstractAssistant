# 📖 Installation Guide

Complete setup instructions for AbstractAssistant on macOS, including prerequisites, voice features, and troubleshooting.

**📚 Other Documentation**: [🏠 README](../README.md) | [🎯 Getting Started](getting-started.md) | [🏗️ Architecture](architecture.md)

---

## 🚀 Quick Installation

### Method 1: macOS App Bundle (Recommended for macOS)

```bash
# Enhanced installation with Dock integration
python3 install.py
```

This automatically:
- Installs AbstractAssistant from PyPI
- Creates a macOS app bundle in `/Applications`
- Makes AbstractAssistant available in your Dock

**🎯 Launch Options**:
- **Dock**: Click the AbstractAssistant icon
- **Spotlight**: Search for "AbstractAssistant"
- **Finder**: Open `/Applications/AbstractAssistant.app`

### Method 2: PyPI (Standard)

```bash
# Install the latest stable version
pip install abstractassistant

# Launch immediately
assistant

# Optional: Create macOS app bundle after installation
create-app-bundle
```

**📦 PyPI Package**: [https://pypi.org/project/abstractassistant/](https://pypi.org/project/abstractassistant/)

### Method 3: From Source

```bash
# Clone the repository
git clone https://github.com/lpalbou/abstractassistant.git
cd abstractassistant

# Install in development mode
pip install -e .

# Launch
assistant
```

**📋 GitHub Repository**: [https://github.com/lpalbou/abstractassistant](https://github.com/lpalbou/abstractassistant)

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

### Step 4: macOS App Bundle (Optional but Recommended)

For the best macOS experience, create a native app bundle:

```bash
# Create macOS app bundle after installation
create-app-bundle
```

This will:
- Create `/Applications/AbstractAssistant.app`
- Generate a beautiful neural network-inspired icon
- Make AbstractAssistant launchable from Dock, Spotlight, or Finder
- Provide a native macOS application experience

**🎯 Benefits**:
- **Dock Integration**: Click to launch from Dock
- **Spotlight Search**: Find and launch via Spotlight (⌘+Space)
- **Native Feel**: Behaves like any other macOS application
- **Easy Discovery**: Users can find it in Applications folder

## 🎙️ Voice Features Setup

AbstractAssistant includes **high-quality text-to-speech** powered by [AbstractVoice](https://github.com/lpalbou/abstractvoice).

### Automatic Installation

Voice features are automatically installed with AbstractAssistant:

```bash
# AbstractVoice is included as a required dependency
pip install abstractassistant  # Includes AbstractVoice
```

### Voice Quality Enhancement (Optional)

For the best voice quality, install additional audio libraries:

```bash
# Enhanced audio processing (macOS)
brew install espeak-ng portaudio

# Alternative: Install via pip
pip install PyAudio sounddevice
```

### Voice Features Include:
- **🗣️ Natural Speech**: High-quality voice synthesis
- **⚡ Fast Processing**: Optimized for real-time responses
- **🎛️ Simple Controls**: One-click enable/disable in the UI
- **🔧 No Configuration**: Works out of the box

**📋 AbstractVoice Repository**: [https://github.com/lpalbou/abstractvoice](https://github.com/lpalbou/abstractvoice)

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

## 🤖 Models & Providers Setup

AbstractAssistant supports multiple AI providers via [AbstractCore](https://github.com/lpalbou/abstractcore). Choose your preferred setup:

### Option 1: Local Models (Recommended for Privacy)

#### LMStudio (Easiest)
1. **Download**: [LMStudio](https://lmstudio.ai/)
2. **Install a Model**: Download models like Qwen, Llama, or Mistral
3. **Start Server**: Click "Start Server" in LMStudio
4. **Use in Assistant**: Select "LMStudio" provider in AbstractAssistant

#### Ollama (Command Line)
```bash
# Install Ollama
brew install ollama

# Start Ollama service
ollama serve

# Download a model
ollama pull qwen2.5:latest
ollama pull llama3.2:latest
```

### Option 2: Cloud API Providers

#### API Keys Setup
Set up API keys for cloud providers:

```bash
# OpenAI (GPT-4, GPT-3.5)
export OPENAI_API_KEY="your_openai_key_here"

# Anthropic (Claude)
export ANTHROPIC_API_KEY="your_anthropic_key_here"

# Make permanent
echo 'export OPENAI_API_KEY="your_key"' >> ~/.zshrc
echo 'export ANTHROPIC_API_KEY="your_key"' >> ~/.zshrc
```

### Provider Comparison

| Provider | Cost | Privacy | Setup Difficulty | Performance |
|----------|------|---------|------------------|-------------|
| **LMStudio** | Free | 🔒 Full | ⭐ Easy | ⭐⭐⭐ Good |
| **Ollama** | Free | 🔒 Full | ⭐⭐ Medium | ⭐⭐⭐ Good |
| **OpenAI** | Paid | ⚠️ API | ⭐ Easy | ⭐⭐⭐⭐ Excellent |
| **Anthropic** | Paid | ⚠️ API | ⭐ Easy | ⭐⭐⭐⭐ Excellent |
| **MLX** | Free | 🔒 Full | ⭐⭐⭐ Advanced | ⭐⭐⭐⭐ Excellent* |
| **HuggingFace** | Free | 🔒 Full | ⭐⭐⭐ Advanced | ⭐⭐⭐ Good |

*MLX: Optimized for Apple Silicon (M1/M2/M3/M4)

**📋 AbstractCore Repository**: [https://github.com/lpalbou/abstractcore](https://github.com/lpalbou/abstractcore)

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


## Troubleshooting

### Common Issues

#### "assistant: command not found"
```bash
# Make sure virtual environment is activated
source ~/.venvs/abstractassistant/bin/activate

# Or install globally
pip install --user abstractassistant
```

#### macOS App Bundle Issues
```bash
# If create-app-bundle fails, try:
pip install --upgrade abstractassistant
create-app-bundle

# If you don't have permissions to write to /Applications:
sudo create-app-bundle

# Manual app bundle creation:
python3 -c "from abstractassistant.setup_macos_app import create_macos_app_bundle; create_macos_app_bundle()"
```

#### App Bundle Not Appearing in Dock
- The app bundle runs in the background (system tray only)
- Look for the AbstractAssistant icon in your menu bar
- The Dock icon only appears briefly during launch
- This is normal behavior for system tray applications

#### "No Qt library available"
```bash
# Install a Qt framework
pip install PyQt5
```

#### Voice Features Not Working
```bash
# AbstractVoice should be automatically installed
# If voice features aren't working, try:

# Reinstall with voice dependencies
pip install --upgrade abstractassistant abstractvoice

# Install additional audio libraries (macOS)
brew install portaudio espeak-ng

# Alternative audio libraries
pip install PyAudio sounddevice
```

**🔗 AbstractVoice Issues**: See [AbstractVoice repository](https://github.com/lpalbou/abstractvoice) for voice-specific troubleshooting.

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

#### Option 1: macOS App Bundle (Recommended)
1. Open System Preferences > Users & Groups
2. Click your user account
3. Go to Login Items
4. Add `/Applications/AbstractAssistant.app` to the list

#### Option 2: Terminal Command
1. Open System Preferences > Users & Groups
2. Click your user account
3. Go to Login Items
4. Add the `assistant` command to the list

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

# Remove macOS app bundle (if created)
rm -rf /Applications/AbstractAssistant.app

# Remove configuration (optional)
rm -rf ~/.config/abstractassistant

# Remove LaunchAgent (if created)
launchctl unload ~/Library/LaunchAgents/com.abstractassistant.plist
rm ~/Library/LaunchAgents/com.abstractassistant.plist
```

---

## 🎯 Next Steps

**Installation Complete!** Here's what to do next:

1. **📖 Learn the Interface**: Read the [🎯 Getting Started Guide](getting-started.md)
2. **🏠 Back to README**: Return to the [🏠 Main README](../README.md)
3. **🏗️ Technical Details**: Check the [🏗️ Architecture Guide](architecture.md)

## 🆘 Need Help?

- **🐛 Issues**: [GitHub Issues](https://github.com/lpalbou/abstractassistant/issues)
- **📋 Main Repository**: [AbstractAssistant on GitHub](https://github.com/lpalbou/abstractassistant)
- **🔗 Related Projects**: [AbstractCore](https://github.com/lpalbou/abstractcore) | [AbstractVoice](https://github.com/lpalbou/abstractvoice)
