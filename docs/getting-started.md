# Getting Started

AbstractAssistant is a tray-first gateway client. It does not host providers or workflows
locally: it connects to AbstractGateway, runs each turn through the published
`abstractassistant-orchestrator` workflow, and follows gateway defaults unless you override them
for this app.

See also:

- [INSTALLATION.md](INSTALLATION.md)
- [settings.md](settings.md)
- [voice.md](voice.md)
- [troubleshooting.md](troubleshooting.md)

## 1. Install

```bash
pip install "abstractassistant[voice]"
```

The `voice` extra adds local microphone capture (dictation and voice conversations). The base
install covers text chat, spoken replies and gateway-backed media.

## 2. Start a gateway

For local development, load the workflow bundles and set a shared token:

```bash
export ABSTRACTGATEWAY_FLOWS_DIR="$PWD/abstractgateway/flows/bundles"
export ABSTRACTGATEWAY_AUTH_TOKEN="your-shared-token"
abstractgateway serve --host 127.0.0.1 --port 8080
```

If the gateway cannot expose the published assistant workflow, the assistant says so instead of
falling back to another runtime path.

## 3. Launch

Tray app:

```bash
assistant
```

One terminal turn:

```bash
assistant run --prompt "Search the web for the latest OpenAI news and summarize it with sources."
```

Connection overrides:

```bash
assistant --gateway-url http://127.0.0.1:8080 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN"
```

## 4. The palette

Summon it from the menu-bar icon or with the global shortcut (default `cmd+shift+space`).

- **Header**: the title shows what the app is doing (Running, Reconnecting, Listening, Speaking,
  Not sent); the chat control names the current chat and opens the chat switcher; the buttons
  start a new chat (⌘N), open Tools & permissions, toggle spoken replies, and open Settings (⌘,);
  the orb at the right shows whether the gateway is reachable.
- **Chat switcher**: click the chat name in the header. Chats are grouped by recency (today,
  yesterday, previous 7 and 30 days, older) and each row shows what that chat holds: its topic,
  its latest question, when it was last active, and its turns, tool calls, tokens, running time
  and workspace folder. A chat whose tools failed or whose last question was never answered is
  flagged. Type to filter by topic, folder or tool name; ↑↓ move, Return opens, Esc closes. The
  pencil renames a chat and the bin deletes it (with its transcript) after an in-row
  confirmation; ⌘⌫ asks the same for the selected row.
- **Transcript**: your messages and the assistant's replies. Each reply ends with a statistics
  line (tokens, tools, files, duration, model); the tools and files segments open detail views.
  While a run works, an activity card at the bottom shows the current step, the elapsed time and
  the latest steps; it can pause, resume or stop the run and open the full run log.
- **Composer**: attach files (button or drag and drop), dictate with the microphone, start a voice
  conversation (⌘⇧V), type, and send with Return (Shift+Return adds a line). During a run the
  send button becomes Stop (⌘.) and typed text steers the run.

## 5. Approvals and questions

When the workflow needs a tool you have not pre-approved, an approval sheet opens beside the
palette. It lists each call with the gateway's risk tier and the command, path or query it will
use. `Allow once` (Return) runs this batch, `Deny` (⌘D) refuses it, Esc decides later and the
question returns when you reopen the palette. Tick "Always allow … on this Mac" to stop being
asked for that tool. The palette stays usable while the sheet is open.

Questions from the assistant open a dialog with the rendered question and a multi-line answer
box; you can also keep the run waiting or continue without answering.

## 6. Configure

Open Settings (⌘,). Gateway defaults apply everywhere unless you override them for this app; each
page says where a value comes from. Common first steps:

- **Connection**: gateway URL and sign-in (bearer token or gateway session).
- **Models & reasoning**: pin a chat model for this app, set the reasoning effort.
- **Voice**: engines for speech, auto-speak, conversation options.
- **Workspace**: the folder the assistant may work in and extra allowed folders.
- **Tools & permissions**: per-tool Off / Auto / Ask on top of the gateway's defaults.

The full reference is [settings.md](settings.md).

## 7. Voice

Click a reply's speaker button to hear it, use the microphone button to dictate, or press ⌘⇧V for
a hands-free conversation. Details and failure handling are in [voice.md](voice.md).

## 8. Files and workspace

Runs read and write files inside a workspace on the gateway host. Choose a folder in Settings →
Workspace to work in your own files; otherwise the gateway assigns a folder to the first run of a
chat and later turns of that chat reuse it. The chat picker's tooltip shows the current folder.

## 9. Local data

`~/.abstractassistant/` holds the chat registry and snapshots, the gateway connection state, local
preferences and downloaded artifacts. The gateway remains the source of truth for run history,
waits and generated artifacts.

## Next

- [settings.md](settings.md)
- [voice.md](voice.md)
- [architecture.md](architecture.md)
- [troubleshooting.md](troubleshooting.md)
