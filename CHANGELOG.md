# Changelog

All notable changes to AbstractAssistant will be documented in this file.


## [0.3.0] - 2025-10-22

### Fixed
- **CRITICAL: Session Persistence**: Completely eliminated unwanted session clearing that was destroying chat history
  - Sessions now persist when switching providers or models
  - TTS mode switching preserves chat history
  - Error handling preserves sessions instead of creating new ones
  - System tray actions require user confirmation and cannot bypass session control
  - Only explicit "Clear" button action in UI destroys sessions
  - Separated LLM initialization from session management
  - Added `update_session_mode()` method for history-preserving mode switches
  - Fixed automatic session loading that bypassed user control
  - Bulletproof session control: NO internal process can clear sessions
- **UI Layout**: Fixed window resizing when adding/removing file attachments
  - Window now dynamically resizes to accommodate file attachment widget
  - Base size: 630x196, expands to 630x224 when files are attached (compact)
  - Voice mode properly adjusts: 630x120 base, 630x148 with attachments
  - Maintains proper positioning relative to system tray after resize
- **Session Clearing**: Clear session now also clears attached files
  - When user clicks "Clear" button, both messages and attached files are cleared
  - Updated confirmation dialog to mention attached files will be removed
  - Ensures complete session reset including file attachments
- **File Chip Styling**: Made file attachment chips more compact and space-efficient
  - Reduced font size from 10px to 8px for better space utilization
  - Decreased border radius from 10px to 6px for tighter appearance
  - Minimized padding and margins throughout (50% reduction)
  - Smaller remove buttons (16x16 → 12x12) for cleaner look
  - Window expansion reduced from +40px to +28px (30% space savings)
- **UI Cleanup**: Removed unwanted voice control panel extension
  - Eliminated the play/pause control panel that sometimes appeared at bottom
  - Cleaner interface without unnecessary UI extensions
  - Voice controls still available through existing TTS toggle button

## [0.2.8] - 2025-10-21

### Added
- **macOS App Bundle**: Native macOS application bundle (`.app`) with Dock integration and system tray support
- **Automated App Creation**: `create-app-bundle` command to generate macOS app bundle post-installation
- **Streamlined Installation**: `install.py` script for one-command macOS setup with app bundle creation
- **Neural Network Icon**: Beautiful AI-inspired icon automatically generated and converted to `.icns` format

### Improved
- **Cross-Environment Compatibility**: Robust Python environment detection supporting pyenv, anaconda, homebrew, and system Python
- **Portable Launch Script**: Smart Python discovery that works across different users and system configurations
- **Error Handling**: User-friendly dialog boxes for installation and launch issues
- **Documentation**: Updated installation guides for macOS App Bundle workflow

### Fixed
- **Python Environment Detection**: Resolved issues with finding correct Python installation in GUI launch context
- **Development vs Production**: Launch script now correctly uses installed package instead of development version
- **PATH Resolution**: Fixed Python executable discovery when launched from Dock vs terminal

### Technical
- Added `MacOSAppBundleGenerator` class for programmatic app bundle creation
- Enhanced `setup_macos_app.py` with comprehensive Python environment detection
- Updated `pyproject.toml` to include app bundle creation tools as console scripts
- Improved launch script with fallback mechanisms for different Python installations
- Added proper `Info.plist` configuration for macOS app bundle standards

### Installation
```bash
# Simple one-command installation for macOS users
python install.py

# Or manual installation
pip install abstractassistant
create-app-bundle
```

### Usage
- Launch from **Applications folder** or **Dock**
- Look for neural network icon in **menu bar** (system tray)
- All existing CLI options remain available

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
