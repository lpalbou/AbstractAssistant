# Usage Guide

This guide covers how to use AbstractAssistant effectively for your daily AI interactions.

## Getting Started

### First Launch

1. **Start the Application**:
   ```bash
   assistant
   ```

2. **Find the Icon**: Look for the AbstractAssistant icon in your macOS menu bar (top-right)

3. **Click to Open**: Click the icon to open the chat bubble

4. **Start Chatting**: Type your message and press Shift+Enter or click the send button

## Main Interface

### Chat Bubble

The main interface is a sleek, dark-themed chat bubble that appears when you click the system tray icon.

#### Header Controls
- **✕ (Close)**: Closes the chat bubble (top-left)
- **Clear**: Starts a new conversation
- **Load**: Loads a saved conversation
- **Save**: Saves the current conversation
- **History**: Opens the conversation history viewer
- **🔊 (TTS Toggle)**: Enables/disables voice responses
- **READY**: Shows current AI status (Ready/Generating)

#### Main Area
- **Text Input**: Large text area for typing your messages
- **Send Button (→)**: Blue circular button to send messages
- **Provider Dropdown**: Select AI provider (LMStudio, OpenAI, etc.)
- **Model Dropdown**: Choose specific model for the selected provider
- **Token Counter**: Shows current/total tokens (e.g., "143 / 262k")

### System Tray Icon

The icon in your menu bar provides visual feedback:

- **Green (Steady)**: Ready for input
- **Red/Purple (Pulsing)**: AI is generating a response
- **Red (Steady)**: Error occurred

## Core Features

### Provider and Model Selection

AbstractAssistant supports multiple AI providers through AbstractCore:

#### LMStudio (Local Models)
- **Setup**: Install LMStudio, download models, start local server
- **Benefits**: Privacy, no API costs, works offline
- **Models**: Qwen3-Next-80B, Llama models, and more

#### OpenAI
- **Setup**: Set `OPENAI_API_KEY` environment variable
- **Models**: GPT-4o, GPT-4, GPT-3.5-turbo, and more
- **Benefits**: High quality, fast responses

#### Anthropic
- **Setup**: Set `ANTHROPIC_API_KEY` environment variable
- **Models**: Claude 3.5 Sonnet, Claude 3 Opus, and more
- **Benefits**: Excellent reasoning, long context

#### Ollama
- **Setup**: Install Ollama, pull models
- **Models**: Qwen2.5, Llama 3, Mistral, and more
- **Benefits**: Local, open-source models

### Voice Mode

Enable Text-to-Speech for conversational AI:

1. **Click the TTS Toggle** (🔊 icon)
2. **Voice Responses**: AI responses will be spoken aloud
3. **Optimized Prompts**: AI uses shorter, conversational responses
4. **High Quality**: Uses VoiceLLM with VITS model for natural speech

#### Voice Controls
- **Toggle On/Off**: Click the speaker icon
- **Stop Speaking**: Click the system tray icon while speaking
- **Speed Control**: Configurable in settings (future feature)

### Session Management

Keep track of your conversations:

#### Save Conversations
1. Click **Save** button
2. Choose filename and location
3. Conversation saved as JSON file

#### Load Conversations
1. Click **Load** button
2. Select saved conversation file
3. Context restored for continued conversation

#### View History
1. Click **History** button
2. Browse all messages in iPhone Messages-style interface
3. User messages (blue) and AI responses (black) with timestamps
4. Markdown rendering for AI responses

#### Clear Session
- Click **Clear** to start fresh conversation
- Previous context is lost

## Keyboard Shortcuts

### In Chat Bubble
- **Shift+Enter**: Send message
- **Escape**: Close chat bubble
- **Tab**: Navigate between controls

### System-wide
- **Click Tray Icon**: Open/close chat bubble
- **Double-click Tray Icon**: Force open (even during TTS)

## Advanced Usage

### Configuration

Create `~/.config/abstractassistant/config.toml`:

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

### Command Line Options

```bash
# Use specific provider and model
assistant --provider openai --model gpt-4o

# Enable debug mode
assistant --debug

# Use custom config file
assistant --config /path/to/config.toml

# Show help
assistant --help
```

### Environment Variables

Set up API keys:

```bash
# Add to ~/.zshrc or ~/.bash_profile
export OPENAI_API_KEY="your_openai_key"
export ANTHROPIC_API_KEY="your_anthropic_key"

# For session persistence
export ABSTRACTASSISTANT_SESSION_DIR="~/Documents/AI_Sessions"
```

## Tips and Best Practices

### Effective Prompting

#### For General Use
- Be specific and clear in your requests
- Provide context when needed
- Use follow-up questions to refine responses

#### For Voice Mode
- Ask shorter questions
- Expect conversational responses
- Use it for quick information or brainstorming

#### For Coding
- Specify the programming language
- Provide relevant context or error messages
- Ask for explanations along with code

### Provider Selection

#### Choose LMStudio When:
- Privacy is important
- You want to avoid API costs
- Working with sensitive data
- Need offline capability

#### Choose OpenAI When:
- Need highest quality responses
- Working on complex reasoning tasks
- Speed is important
- Using latest models

#### Choose Anthropic When:
- Need excellent reasoning capabilities
- Working with long documents
- Want helpful, harmless responses
- Need nuanced understanding

### Session Management

#### Save Important Conversations
- Research sessions with valuable information
- Complex problem-solving discussions
- Creative writing or brainstorming sessions

#### Use Clear for:
- Switching topics completely
- Starting fresh after errors
- Privacy (clearing sensitive discussions)

#### Load Previous Sessions When:
- Continuing complex projects
- Referencing previous discussions
- Building on earlier work

## Troubleshooting

### Common Issues

#### Chat Bubble Not Appearing
- Check if icon is in menu bar
- Try clicking the icon again
- Run with `--debug` to see error messages

#### No Response from AI
- Check internet connection (for cloud providers)
- Verify API keys are set correctly
- Try switching to a different provider
- Check token limits

#### Voice Not Working
- Ensure VoiceLLM is installed: `pip install voicellm`
- Install espeak-ng for best quality: `brew install espeak-ng`
- Check system audio settings
- Try toggling TTS off and on

#### Provider Not Available
- For LMStudio: Ensure local server is running
- For Ollama: Check if service is started (`ollama serve`)
- For cloud providers: Verify API keys and internet connection

### Debug Mode

Run with debug mode for detailed information:

```bash
assistant --debug
```

This shows:
- Configuration loading
- Provider discovery
- Model loading
- Request/response details
- Error messages with stack traces

### Getting Help

1. **Check the logs**: Debug mode provides detailed information
2. **Review configuration**: Ensure settings are correct
3. **Test providers**: Try different providers to isolate issues
4. **GitHub Issues**: Report bugs or request features

## Integration Ideas

### Workflow Integration

#### Writing Assistant
- Use for brainstorming ideas
- Get help with grammar and style
- Generate outlines and structures

#### Coding Helper
- Debug error messages
- Get code explanations
- Generate boilerplate code
- Review and optimize code

#### Research Tool
- Quick fact checking
- Summarize complex topics
- Generate research questions
- Explore different perspectives

#### Creative Partner
- Brainstorm creative ideas
- Get feedback on projects
- Generate variations and alternatives
- Overcome creative blocks

### Shell Integration

Add to your shell profile:

```bash
# Quick aliases
alias ai="assistant"
alias ai-debug="assistant --debug"

# Provider-specific shortcuts
alias ai-gpt4="assistant --provider openai --model gpt-4o"
alias ai-claude="assistant --provider anthropic --model claude-3-5-sonnet-20241022"
alias ai-local="assistant --provider lmstudio"
```

---

For more advanced configuration and development information, see the [Architecture Guide](ARCHITECTURE.md).
