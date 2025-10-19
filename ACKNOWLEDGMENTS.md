# Acknowledgments

AbstractAssistant would not be possible without the incredible work of the open-source community and the following libraries and projects:

## Core Foundation

### [AbstractCore](https://www.abstractcore.ai/)
**The heart of AbstractAssistant's multi-provider LLM support**

AbstractCore provides the universal interface that makes it possible to seamlessly switch between different AI providers. Without AbstractCore, this project would require implementing separate integrations for each LLM provider.

- **What it provides**: Universal LLM interface, provider discovery, model management, session handling
- **Why it's essential**: Enables support for 6+ LLM providers and 100+ models through a single, consistent API
- **License**: MIT License
- **Repository**: [AbstractCore on GitHub](https://github.com/lpalbou/abstractcore)

*Special thanks to the AbstractCore team for creating such a robust and extensible foundation for AI applications.*

## Voice and Audio

### [AbstractVoice](https://github.com/lpalbou/abstractvoice)
**High-quality Text-to-Speech integration**

AbstractVoice provides the conversational AI capabilities that make AbstractAssistant truly interactive. The VITS model integration delivers natural-sounding speech synthesis.

- **What it provides**: TTS engine, voice activity detection, speech-to-text capabilities
- **Features used**: Text-to-speech with speed control, model fallbacks, threading support
- **License**: MIT License

### [Coqui TTS](https://github.com/coqui-ai/TTS)
**Advanced Text-to-Speech engine**

The underlying TTS engine that powers AbstractVoice's high-quality speech synthesis.

- **What it provides**: Neural text-to-speech models, voice cloning, multilingual support
- **License**: MPL 2.0 License

### [OpenAI Whisper](https://github.com/openai/whisper)
**Robust automatic speech recognition**

Used by AbstractVoice for potential future speech-to-text features.

- **What it provides**: Multilingual speech recognition, robust audio processing
- **License**: MIT License

### [PyAudio](https://people.csail.mit.edu/hubert/pyaudio/)
**Cross-platform audio I/O**

Enables audio input/output for voice features.

- **What it provides**: Audio stream handling, cross-platform audio support
- **License**: MIT License

## User Interface

### [Qt Framework](https://www.qt.io/) (PyQt5/PySide2/PyQt6)
**Modern, native GUI framework**

Qt provides the foundation for AbstractAssistant's sleek, native-feeling interface. The automatic detection of PyQt5, PySide2, or PyQt6 ensures compatibility across different environments.

- **What it provides**: Native GUI widgets, cross-platform compatibility, modern styling
- **Features used**: Custom widgets, layouts, styling, threading, event handling
- **License**: 
  - PyQt5/PyQt6: GPL v3 / Commercial License
  - PySide2/PySide6: LGPL v3 / Commercial License

### [pystray](https://github.com/moses-palmer/pystray)
**Cross-platform system tray support**

Enables AbstractAssistant to live in the macOS menu bar with native integration.

- **What it provides**: System tray icon management, context menus, click handling
- **License**: LGPL v3 License

## Image Processing

### [Pillow (PIL Fork)](https://python-pillow.org/)
**Powerful image processing library**

Used for dynamic system tray icon generation with animations and status indicators.

- **What it provides**: Image creation, manipulation, format support
- **Features used**: Dynamic icon generation, image compositing, color manipulation
- **License**: HPND License

## Utilities and Support

### [pyperclip](https://github.com/asweigart/pyperclip)
**Cross-platform clipboard operations**

Enables copy-to-clipboard functionality for AI responses.

- **What it provides**: Clipboard read/write operations
- **License**: BSD 3-Clause License

### [plyer](https://github.com/kivy/plyer)
**Cross-platform native features**

Provides access to platform-specific notification systems.

- **What it provides**: Native notifications, platform abstraction
- **License**: MIT License

### [markdown](https://python-markdown.github.io/)
**Markdown processing**

Enables rich text rendering in the history dialog and notifications.

- **What it provides**: Markdown to HTML conversion, extensions support
- **License**: BSD 3-Clause License

### [Pygments](https://pygments.org/)
**Syntax highlighting**

Provides code syntax highlighting in markdown-rendered content.

- **What it provides**: Code syntax highlighting, multiple language support
- **License**: BSD 2-Clause License

## Configuration and Data

### [tomli](https://github.com/hukkin/tomli) / [tomli-w](https://github.com/hukkin/tomli-w)
**TOML configuration file support**

Enables clean, human-readable configuration files.

- **What it provides**: TOML parsing and writing
- **License**: MIT License

## Development Tools

### [setuptools](https://setuptools.pypa.io/)
**Python packaging**

Modern Python packaging and distribution.

- **License**: MIT License

## Special Recognition

### The Python Community
The entire Python ecosystem that makes rapid development of sophisticated applications possible.

### macOS Integration
Apple's excellent developer documentation and APIs that enable seamless system integration.

### Open Source Contributors
All the maintainers, contributors, and users of the above projects who make open-source software development possible.

---

## License Compatibility

AbstractAssistant is released under the MIT License, which is compatible with all the dependencies listed above. Users should be aware of the specific licensing terms of each dependency, particularly:

- **Qt-based components** (PyQt5/PyQt6) are available under GPL v3 or commercial license
- **PySide2/PySide6** are available under LGPL v3 or commercial license
- All other dependencies use permissive licenses (MIT, BSD, etc.)

For commercial use, consider the licensing implications of Qt-based components.

---

**Thank you to all the developers and maintainers who make projects like AbstractAssistant possible!** 🙏
