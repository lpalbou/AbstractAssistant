# Getting Started

AbstractAssistant is a tray-first gateway client. It does not host providers or workflows
locally: it connects to AbstractGateway, runs each turn through the gateway's default workflow for
the assistant (`abstractassistant.agent.v1`) or the built-in `abstractassistant-orchestrator`
workflow it publishes to your tenant catalog, and follows gateway defaults unless you override
them for this app.

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

If no assistant workflow is available on the gateway, the assistant says so and blocks sending
instead of picking another workflow on its own.

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

`--gateway-url` alone reuses the sign-in you saved for that gateway in Settings → Connection.

If the gateway runs the AbstractGateway console, the simplest way to start the assistant is
**Open** on its card there: the console launches the app already signed in as you, and the app
remembers that sign-in for later launches. The console can sign in only an Assistant it launches,
so quit a running Assistant before you click **Open**.

## 4. The palette

Summon it from the menu-bar icon or with the global shortcut (default `cmd+shift+space`).

- **Header**: the title shows what the app is doing (Running, Reconnecting, Listening, Speaking,
  Not sent); the chat control names the current chat and opens the chat switcher; the buttons
  start a new chat (⌘N), open Tools & permissions, schedule this conversation (clock, on a
  gateway that offers automations), toggle spoken replies, and open Settings (⌘,); the orb at
  the right shows whether the gateway is reachable.
- **Chat switcher**: click the chat name in the header. Its **Sessions** tab lists every session
  on the gateway, whichever client started it (the Assistant on any device, AbstractCode,
  AbstractObserver), 100 at a time; its **Automations** tab lists the gateway's automations with
  their controls. Chats are grouped by recency (today,
  yesterday, previous 7 and 30 days, older) and each row shows what that chat holds: its topic,
  its latest question, when it was last active, its turns and state, and once opened on this Mac
  its tool calls, tokens, running time and workspace folder. A chat whose tools failed or whose
  last question was never answered is flagged. Type to filter by topic, folder or tool name; ↑↓
  move, Return opens, Esc closes. The pencil renames a chat on this device; there is no delete
  (the gateway has none). How sessions work: [architecture.md](architecture.md#sessions).
- **Automations**: on a gateway that offers them, the switcher also lists your automations above
  the chats, and the clock button schedules the current conversation to run on a fixed UTC
  interval. See [automations.md](automations.md).
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
- **Models & reasoning**: choose the workflow, pin a chat model for this app, set the reasoning
  effort, and choose whether replies stream (**Stream replies**).
- **Appearance**: theme, text size and spacing, the summon shortcut, window size.
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

A picture a run saves in its workspace and names in its answer (`![Memory over time](memory_curve.png)`)
appears inside the reply at the reply's width; click it to open the file full size. On the
gateway's own machine the file is read in place; from another machine the app fetches a copy
through the gateway into `~/.abstractassistant/downloads/`. A picture it cannot reach is shown as
its caption and file name. In the **files** detail view, **Open file** opens each created or
modified file the same way.

## 9. Local data

`~/.abstractassistant/` holds the chat registry and snapshots, the gateway connection state, local
preferences and downloaded artifacts. The gateway remains the source of truth for run history,
waits and generated artifacts.

## Next

- [settings.md](settings.md)
- [voice.md](voice.md)
- [architecture.md](architecture.md)
- [troubleshooting.md](troubleshooting.md)
