# Getting started

AbstractAssistant is a tray-accessible agent host built on AbstractFramework (Agent + Runtime + Core).

See also:
- `../README.md`
- `architecture.md`

## Install

```bash
pip install "abstractassistant"
```

### Editable (development)

```bash
pip install -e ".[dev]"
```

## Run

### Tray

```bash
assistant tray
```

Alias:

```bash
abstractassistant tray
```

### Voice modes

```bash
assistant tray --listening-mode wait
```

Valid modes: `none`, `stop`, `wait`, `full`, `ptt`.

### Terminal (one agentic turn)

```bash
assistant run --prompt "Explain this repository structure"
```

Override provider/model:

```bash
assistant run --provider ollama --model qwen3:4b-instruct --prompt "Summarize my last changes"
```

## Tool approvals

AbstractAssistant enforces an explicit tool approval boundary:
- read-only / known-safe tools may auto-run
- writes, shell execution, and unknown tools pause and require approval

Approvals are requested as a **batch** of tool calls.

In the tray bubble, the Tools button lets you:
- choose “All tools” vs a “Custom allowlist”
- set per-tool default approval mode (`Approve` or `Ask`) for the current session

## Attachments (tray UI)

Use the paperclip button to attach local files (images, documents, audio, video). File paths are passed to the underlying provider/media pipeline.

Notes:
- Audio: common containers like `.wav`, `.mp3`, `.m4a`, `.ogg`, `.flac`, `.aac`, `.webm`
- Audio STT: when `abstractvoice` is installed (default), audio attachments are automatically transcribed and the transcript is inlined into the prompt for text-only models (the first run may download model weights).
- Video: common containers like `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, `.wmv`, `.m4v`
- Video frame-sampling fallback (for text-only models) may require `ffmpeg` on your PATH.

## Sessions (tray UI)

Use the “Sessions” badge to switch between sessions. Each row shows a short date, title, and a few quick stats (messages, files, tools).

## Voice (STT/TTS)

In the tray bubble:
- Speaker toggle: enable/disable TTS for assistant responses
- Microphone toggle (“Full Voice Mode”): continuous STT → agent turns → TTS responses
- In Full Voice Mode, the UI becomes voice-only (no typing). Say “stop” to exit.

Listening modes control how STT interacts with speaking/processing and depend on your AbstractVoice backend.

## Configuration

AbstractAssistant can load a `config.toml` (optional).

- Pass an explicit file with: `assistant --config /path/to/config.toml`
- If omitted, it searches `config.toml` in:
  - the current directory
  - the package directory

Common keys:

```toml
[llm]
default_provider = "ollama"
default_model = "qwen3:4b-instruct"
```

## Data directory

By default, assistant state is stored in `~/.abstractassistant/`:
- `session.json`: quick UI snapshot (transcript + last run id)
- `runtime/`: run store + ledger + artifacts (source of truth)

Override with:

```bash
assistant --data-dir /path/to/dir tray
```

## Troubleshooting

- Tray fails to start: reinstall base dependencies: `pip install --upgrade "abstractassistant"`.
- Voice toggles missing/unavailable: reinstall: `pip install --upgrade "abstractassistant"` and restart.
- Mic says “listening” but hears nothing: macOS System Settings → Privacy & Security → Microphone → enable access for AbstractAssistant, then restart the app.
- Provider errors: ensure your local provider is running (LMStudio/Ollama) or set API keys (OpenAI/Anthropic).
- Reset state: use “Clear” in the UI, or delete your data dir (`~/.abstractassistant/` by default).
