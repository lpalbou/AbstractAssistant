# AbstractAssistant Architecture

## Overview

AbstractAssistant is a modern macOS system tray application that provides instant access to Large Language Models (LLMs) through a sleek, glassy UI. Built with Python, it leverages AbstractCore for universal LLM provider support.

## Project Structure

```
abstractassistant/
├── main.py                 # Application entry point
├── launch.sh              # Launch script
├── config.yaml            # Configuration file
├── requirements.txt       # Python dependencies
├── test_app.py            # Component tests
├── README.md              # User documentation
├── ARCHITECTURE.md        # This file
├── assets/                # Icons and resources
└── src/                   # Source code
    ├── __init__.py
    ├── app.py             # Main application class
    ├── core/              # Business logic
    │   ├── __init__.py
    │   └── llm_manager.py # LLM provider management
    ├── ui/                # User interface components
    │   ├── __init__.py
    │   ├── chat_bubble.py # Chat interface
    │   └── toast_manager.py # Notification system
    └── utils/             # Utilities
        ├── __init__.py
        └── icon_generator.py # Icon creation
```

## Core Components

### 1. Application Layer (`src/app.py`)

**AbstractAssistantApp**: Main application coordinator
- Manages system tray integration
- Coordinates UI components
- Handles application lifecycle
- Manages inter-component communication

### 2. Core Business Logic (`src/core/`)

**LLMManager**: Handles all LLM-related operations
- Provider management (OpenAI, Anthropic, Ollama, etc.)
- Model selection and configuration
- Token counting and usage tracking
- Session management with conversation memory
- AbstractCore integration with fallback mock

### 3. User Interface (`src/ui/`)

**ChatBubble**: Modern chat interface
- Glassy, modern design using CustomTkinter
- 1/6th screen size positioning
- Provider/model selection dropdowns
- Real-time token counting
- Status indicators
- Keyboard shortcuts (Cmd+Enter to send)

**ToastManager**: Elegant notification system
- Collapsible toast notifications
- Markdown content rendering
- Copy-to-clipboard functionality
- Auto-hide with configurable delays
- Error and success state handling

### 4. Utilities (`src/utils/`)

**IconGenerator**: Creates modern system tray icons
- Neural network-inspired design
- High-DPI support (64px base)
- Status indicator icons
- Gradient and glow effects

## Design Principles

### 1. Robust General-Purpose Logic
- Components designed for real-world scenarios, not just test cases
- Graceful error handling and fallbacks
- Mock implementations for development/testing

### 2. Modular Architecture
- Clear separation of concerns
- Loose coupling between components
- Easy to extend and maintain

### 3. Modern UI/UX
- Native macOS integration
- Glassy, translucent design
- Responsive and intuitive interactions
- Accessibility considerations

### 4. Cross-Platform Foundation
- Built with cross-platform libraries
- Extensible to Windows/Linux
- Platform-specific optimizations where needed

## Data Flow

1. **User Interaction**: Click system tray icon
2. **UI Display**: ChatBubble appears with current settings
3. **Message Input**: User types message, selects provider/model
4. **Processing**: LLMManager handles request via AbstractCore
5. **Response**: ToastManager displays result with markdown formatting
6. **Cleanup**: UI components hide, ready for next interaction

## Key Features

### System Tray Integration
- Native macOS menu bar icon
- Context menu with provider selection
- Always accessible, minimal resource usage

### Universal LLM Support
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Ollama (Local models)
- Extensible to other providers via AbstractCore

### Modern UI
- CustomTkinter for native look and feel
- Dark/light theme support
- Glassy, translucent effects
- Responsive design

### Smart Features
- Real-time token counting
- Session memory
- Status tracking (ready/generating/executing)
- Copy-to-clipboard functionality
- Markdown rendering

## Configuration

The application uses `config.yaml` for user preferences:
- UI theme and sizing
- Default LLM provider/model
- Keyboard shortcuts
- Notification settings

API keys are managed via environment variables for security.

## Error Handling

### Graceful Degradation
- Mock LLM implementation when AbstractCore unavailable
- Fallback UI states for network issues
- User-friendly error messages

### Robust Recovery
- Automatic retry mechanisms
- Session state preservation
- Resource cleanup on errors

## Future Extensibility

### Planned Enhancements
- Global keyboard shortcuts
- Plugin system for custom tools
- Voice input/output
- Multi-conversation management
- Cloud sync for settings

### Platform Expansion
- Windows system tray support
- Linux notification area integration
- Mobile companion app

## Dependencies

### Core Libraries
- **pystray**: Cross-platform system tray
- **customtkinter**: Modern Tkinter styling
- **abstractcore**: Universal LLM interface
- **Pillow**: Image processing for icons

### UI/UX Libraries
- **pyperclip**: Clipboard operations
- **markdown**: Content rendering
- **plyer**: Platform notifications

## Performance Considerations

### Memory Efficiency
- Lazy loading of UI components
- Proper cleanup of resources
- Minimal background processing

### Responsiveness
- Threaded LLM operations
- Non-blocking UI updates
- Efficient icon rendering

### Scalability
- Session-based token tracking
- Configurable resource limits
- Modular component loading
