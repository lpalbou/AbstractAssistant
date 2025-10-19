# AbstractAssistant Architecture

## Overview

AbstractAssistant is a modern macOS system tray application that provides instant access to Large Language Models through a sleek Qt-based interface. Built with Python, it leverages AbstractCore for universal LLM provider support and AbstractVoice for conversational AI capabilities.

## Core Design Philosophy

### Simple, Focused, Effective
- **Single Purpose**: Quick AI interactions from the macOS menu bar
- **Minimal Resource Usage**: Lightweight system tray application
- **Native Feel**: Qt-based interface that feels at home on macOS
- **Robust Fallbacks**: Graceful degradation when services are unavailable

## Project Structure

```
abstractassistant/
├── pyproject.toml              # Package configuration and dependencies
├── requirements.txt            # Python dependencies
├── config.toml                # Default configuration
├── abstractassistant/         # Main package
│   ├── __init__.py
│   ├── cli.py                 # CLI entry point and argument parsing
│   ├── app.py                 # Main application coordinator
│   ├── config.py              # Configuration management
│   ├── core/                  # Business logic
│   │   ├── llm_manager.py     # LLM provider management via AbstractCore
│   │   └── tts_manager.py     # AbstractVoice integration for TTS
│   ├── ui/                    # User interface components
│   │   ├── qt_bubble.py       # Main Qt chat interface
│   │   ├── toast_window.py    # Notification system
│   │   ├── bubble_window.py   # Alternative webview interface
│   │   └── chat_bubble.py     # Legacy interface
│   ├── utils/                 # Utilities
│   │   ├── icon_generator.py  # Dynamic system tray icon creation
│   │   └── markdown_renderer.py # Markdown processing
│   └── web_server.py          # Web server for alternative interface
├── web/                       # Web interface assets (alternative UI)
│   ├── index.html            # Full web interface
│   ├── bubble.html           # Bubble-specific interface
│   ├── styles.css            # Web styling
│   ├── bubble.css            # Bubble-specific styling
│   ├── app.js               # Web application logic
│   └── bubble.js            # Bubble-specific logic
├── docs/                     # Documentation
│   └── ARCHITECTURE.md       # This file
└── tests/                    # Test files
    └── *.py                  # Various test modules
```

## Core Components

### 1. Application Coordinator (`app.py`)

**AbstractAssistantApp**: Main application class that orchestrates all components
- **System Tray Management**: Creates and manages the macOS menu bar icon
- **UI Coordination**: Handles Qt bubble creation and lifecycle
- **Status Management**: Updates icon animations based on AI processing state
- **Event Handling**: Processes clicks, double-clicks, and keyboard shortcuts
- **Component Integration**: Connects LLM manager, UI, and voice systems

**Key Features**:
- Custom `ClickableIcon` class for direct click handling
- Dynamic icon generation with status animations
- Graceful component initialization and cleanup

### 2. LLM Management (`core/llm_manager.py`)

**LLMManager**: Handles all AI model interactions via AbstractCore
- **Provider Discovery**: Automatically detects available LLM providers
- **Model Management**: Dynamically loads models for each provider
- **Session Handling**: Manages conversation context and history
- **Token Tracking**: Real-time token usage monitoring
- **Error Handling**: Robust fallbacks for network and API issues

**Supported Providers** (via AbstractCore):
- LMStudio (local models)
- OpenAI (GPT-4, GPT-3.5, etc.)
- Anthropic (Claude models)
- Ollama (local models)
- And many more through AbstractCore's extensible architecture

### 3. Voice Integration (`core/tts_manager.py`)

**VoiceManager**: AbstractVoice-compatible TTS interface
- **High-Quality Speech**: VITS model with espeak-ng for best quality
- **Speed Control**: Adjustable speech rate with pitch preservation
- **Model Fallbacks**: Automatic fallback to compatible models
- **Threading**: Non-blocking speech synthesis
- **Error Recovery**: Graceful handling of TTS failures

### 4. Qt User Interface (`ui/qt_bubble.py`)

**QtChatBubble**: Modern chat interface with iPhone Messages styling
- **Cross-Platform Qt**: Supports PyQt5, PySide2, and PyQt6
- **Modern Design**: Dark theme with rounded corners and smooth animations
- **Provider Controls**: Dynamic dropdowns for provider and model selection
- **Session Management**: Built-in save, load, clear, and history functions
- **TTS Integration**: Toggle switch for voice mode
- **Responsive Layout**: Optimized for quick interactions

**Key UI Elements**:
- Clean header with session controls and status indicator
- Provider/model selection dropdowns
- Text input area with send button
- Token counter display
- TTS toggle switch
- History dialog with markdown rendering

### 5. System Tray Integration

**Icon System**: Dynamic, animated system tray icons
- **Status Visualization**: Different colors and animations for AI states
- **High-DPI Support**: Crisp icons on Retina displays
- **Neural Network Theme**: Modern, tech-inspired design
- **Smooth Animations**: Heartbeat effects during processing

**States**:
- **Ready**: Steady green - AI is ready for input
- **Generating**: Pulsing red/purple - AI is processing
- **Error**: Red - Something went wrong

### 6. Configuration Management (`config.py`)

**Config System**: TOML-based configuration with validation
- **Default Values**: Sensible defaults for all settings
- **File-based Config**: Optional `config.toml` for customization
- **CLI Overrides**: Command-line arguments override config file
- **Validation**: Ensures configuration integrity

## Data Flow

### Typical User Interaction

1. **User Clicks Icon**: System tray icon click detected
2. **UI Creation**: Qt bubble window created and positioned
3. **Provider Loading**: Available providers and models loaded via AbstractCore
4. **User Input**: User types message and selects provider/model
5. **LLM Processing**: Message sent to selected provider via AbstractCore
6. **Response Handling**: AI response received and processed
7. **Output**: Response displayed in toast notification or spoken via TTS
8. **Cleanup**: UI hidden, ready for next interaction

### Voice Mode Flow

1. **TTS Toggle**: User enables voice mode
2. **Prompt Adaptation**: LLM system prompt modified for conversational responses
3. **Response Processing**: AI response cleaned for speech synthesis
4. **Speech Generation**: AbstractVoice converts text to speech
5. **Audio Playback**: Response spoken through system audio

## Key Design Decisions

### Qt Over Web Interface
- **Native Performance**: Qt provides better system integration
- **Offline Capability**: No dependency on web server or browser
- **Resource Efficiency**: Lower memory and CPU usage
- **Platform Integration**: Better macOS menu bar integration

### AbstractCore Integration
- **Provider Agnostic**: Single interface for multiple LLM providers
- **Future Proof**: Easy to add new providers as they become available
- **Robust Error Handling**: Built-in fallbacks and error recovery
- **Session Management**: Persistent conversation context

### AbstractVoice for TTS
- **High Quality**: VITS model provides natural-sounding speech
- **Cross-Platform**: Works on macOS, Linux, and Windows
- **Configurable**: Multiple TTS models and speed controls
- **Lightweight**: Optional dependency, graceful fallback if unavailable

## Error Handling Strategy

### Graceful Degradation
- **Missing Dependencies**: Application works without optional components
- **Network Issues**: Offline mode with clear error messages
- **Provider Failures**: Automatic fallback to available providers
- **UI Failures**: Console fallback for critical operations

### User Experience
- **Clear Error Messages**: User-friendly explanations of issues
- **Recovery Suggestions**: Actionable steps to resolve problems
- **Non-Blocking Errors**: Application continues running despite component failures
- **Debug Mode**: Detailed logging for troubleshooting

## Performance Considerations

### Memory Efficiency
- **Lazy Loading**: UI components created only when needed
- **Resource Cleanup**: Proper disposal of Qt widgets and threads
- **Session Management**: Efficient conversation history storage
- **Icon Caching**: Reuse generated icons when possible

### Responsiveness
- **Threading**: LLM operations run in background threads
- **Non-Blocking UI**: Interface remains responsive during processing
- **Efficient Updates**: Minimal redraws and updates
- **Fast Startup**: Quick application initialization

### Scalability
- **Provider Extensibility**: Easy to add new LLM providers
- **Configuration Flexibility**: Adaptable to different use cases
- **Cross-Platform Foundation**: Extensible to Windows and Linux
- **Modular Architecture**: Components can be enhanced independently

## Future Extensibility

### Planned Enhancements
- **Global Keyboard Shortcuts**: System-wide hotkeys for quick access
- **Multiple Conversations**: Tabbed or windowed conversation management
- **Plugin System**: Custom tools and integrations
- **Cloud Sync**: Settings and conversation synchronization
- **Mobile Companion**: iOS/Android app integration

### Platform Expansion
- **Windows Support**: System tray integration for Windows
- **Linux Support**: Notification area integration for Linux distributions
- **Cross-Platform Consistency**: Unified experience across operating systems

## Dependencies

### Core Libraries
- **abstractcore**: Universal LLM interface - the foundation of multi-provider support
- **pystray**: Cross-platform system tray integration
- **PyQt5/PySide2/PyQt6**: Modern GUI framework (auto-detected)
- **Pillow**: Image processing for icon generation

### Optional Libraries
- **abstractvoice**: High-quality Text-to-Speech (graceful fallback if unavailable)
- **coqui-tts**: TTS engine backend
- **openai-whisper**: Speech recognition (future feature)
- **PyAudio**: Audio input/output

### Development Tools
- **pytest**: Testing framework
- **black**: Code formatting
- **isort**: Import sorting
- **mypy**: Type checking

## Security Considerations

### API Key Management
- **Environment Variables**: Secure storage of API keys
- **No Hardcoding**: Keys never stored in code or config files
- **Local Processing**: Sensitive data processed locally when possible

### Network Security
- **HTTPS Only**: All external API calls use secure connections
- **Input Validation**: User input sanitized before processing
- **Error Sanitization**: Sensitive information removed from error messages

## Testing Strategy

### Component Testing
- **Unit Tests**: Individual component functionality
- **Integration Tests**: Component interaction testing
- **UI Tests**: Interface behavior validation
- **Error Condition Tests**: Failure scenario handling

### Manual Testing
- **User Experience**: Real-world usage scenarios
- **Performance Testing**: Resource usage under load
- **Compatibility Testing**: Different macOS versions and Qt variants
- **Provider Testing**: Various LLM providers and models

This architecture provides a solid foundation for a reliable, extensible, and user-friendly AI assistant application that integrates seamlessly with the macOS desktop environment.