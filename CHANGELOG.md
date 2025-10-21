# Changelog

All notable changes to AbstractAssistant will be documented in this file.

## [0.2.5] - 2025-10-21

### Added
- **File Attachments**: Click the 📎 button to attach images, PDFs, Office docs, or data files to your messages. The AI can now analyze documents, images, spreadsheets, and more.
- **Clickable Messages**: Click any message bubble in the history panel to copy its content to clipboard. A subtle flash confirms the copy.

### Improved
- **Chat History Layout**: Reduced text size (17px → 14px), increased bubble width (320px → 400px), and tightened spacing throughout for better readability and more efficient use of screen space.
- **Markdown Rendering**: Headers, paragraphs, and lists now use minimal spacing to display more content without scrolling.

### Updated
- **AbstractCore 2.4.5**: Upgraded from 2.4.2 to leverage universal media handling system with support for images, PDFs, Office documents (DOCX, XLSX, PPTX), and data files (CSV, JSON).

### Technical
- Added `ClickableBubble` widget with visual feedback for clipboard operations
- Enhanced `LLMManager` and `LLMWorker` to handle media file attachments
- File chips display with type-specific icons and individual remove buttons
- Improved markdown processor with tighter vertical spacing

## [1.1.0] - 2024-10-16

### 🌐 Major UI Overhaul: Beautiful Web Interface

#### Added
- **Modern Web Interface**: Complete replacement of Qt/Tkinter with beautiful HTML/CSS/JavaScript
- **Glassmorphism Design**: Stunning visual effects with backdrop blur and transparency
- **WebSocket Communication**: Real-time bidirectional communication between web UI and Python backend
- **Responsive Design**: Works perfectly on desktop and mobile browsers
- **Advanced Settings Panel**: Theme selection, temperature control, and token limit configuration
- **Smooth Animations**: Professional transitions and loading states
- **Dark/Light Themes**: Automatic system theme detection with manual override

#### Enhanced
- **Web Server**: Full aiohttp-based server with WebSocket support
- **Real-time Status**: Live updates for connection status and processing state
- **Modern Typography**: Inter font family for professional appearance
- **Gradient Buttons**: Beautiful send button with hover effects
- **Message Bubbles**: Elegant chat interface with markdown rendering

#### Technical Improvements
- Added `aiohttp` and `websockets` dependencies
- Created `WebServer` class with async/await support
- Fallback to simple HTTP server if aiohttp unavailable
- Updated system tray to launch web interface instead of Qt bubble
- Maintained backward compatibility with existing configuration

## [1.0.0] - 2024-10-15

### Added
- **System Tray Integration**: Native macOS menu bar icon with neural network-inspired design
- **Modern Chat Bubble UI**: Glassy, translucent interface with 1/6th screen size
- **Multi-Provider Support**: OpenAI, Anthropic, and Ollama integration via AbstractCore
- **Toast Notifications**: Elegant collapsible notifications with markdown rendering
- **TOML Configuration**: Modern configuration management with validation
- **CLI Interface**: `abstractassistant` command with multiple options
- **Real-time Status**: Token counting and execution status display
- **Copy to Clipboard**: One-click result sharing
- **Keyboard Shortcuts**: Cmd+Enter to send, Escape to close
- **Error Handling**: Graceful fallbacks and user-friendly error messages
- **Debug Mode**: Comprehensive debugging and logging capabilities

### Features
- **Universal LLM Support**: Works with any provider supported by AbstractCore
- **Session Management**: Persistent conversation memory
- **Modern Design**: Dark theme with glassy effects and smooth animations
- **Performance Optimized**: Threaded operations and efficient resource usage
- **Cross-Platform Foundation**: Built for future Windows/Linux support

### Technical
- **Modular Architecture**: Clean separation of concerns
- **Robust Error Handling**: Comprehensive exception management
- **Configuration Validation**: Type-safe configuration with defaults
- **Package Structure**: Proper Python package with CLI entry points
- **Development Mode**: Editable installation support

### CLI Commands
```bash
abstractassistant                    # Launch with default settings
abstractassistant --provider openai # Set provider
abstractassistant --model gpt-4o     # Set model
abstractassistant --debug            # Debug mode
abstractassistant --config custom.toml # Custom config
```

### Configuration
- TOML-based configuration with validation
- Environment variable support for API keys
- Customizable UI themes and behavior
- Provider and model defaults

### Dependencies
- AbstractCore 2.4.0+ for universal LLM support
- CustomTkinter for modern UI components
- pystray for cross-platform system tray
- TOML libraries for configuration management
