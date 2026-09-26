# FAQ

See also:

- [getting-started.md](getting-started.md)
- [settings.md](settings.md)
- [voice.md](voice.md)
- [troubleshooting.md](troubleshooting.md)

## What is AbstractAssistant?

A desktop assistant for AbstractGateway: a menu-bar app with a compact palette and a matching
CLI. It is thin by design. The gateway owns workflows, defaults, tools and durable execution; the
app owns the interface and local preferences.

## Does it run locally?

The desktop shell runs locally. Whether requests work offline depends on the gateway and its
providers: a gateway backed by local providers can stay local; a gateway backed by cloud providers
needs network access.

## Where do provider and model defaults live?

On the gateway. Settings → Models & reasoning shows the gateway default for each route and lets
you pin a different provider and model **for this app only**. The pin is stored in
`preferences.json` and sent with each request; the gateway's shared default is never changed.

## What does "reasoning effort" do?

It sets the thinking level (none to extra high) sent with every run, using the gateway's own
contract. The page shows which model it applies to and which levels that model reports; a level
the model cannot honor is mapped to the nearest supported one by AbstractCore. "Gateway default"
sends nothing.

## Can I choose which folders the assistant may touch?

Yes, in Settings → Workspace: a workspace root, an access mode and extra allowed folders. The
gateway's own policy is shown read-only and always wins: a grant outside it makes the run start
fail with the gateway's reason. Without a root, the gateway assigns a folder to the first run of a
chat and later turns of the same chat reuse it.

## Why do I keep seeing approval requests?

Tool execution is gateway-driven and explicit. Tools you never configured follow the gateway's
approval default, which is "ask" for anything that sends messages, writes remotely or is
destructive. Pre-approve a tool for this Mac in Settings → Tools & permissions, tick "Always
allow … on this Mac" in the approval sheet (offered for observe and act tools), or use the
chevron next to Allow once to trust the enabled tools for the current chat. Chat-wide trust
reaches as far as the batch it was granted on: from a read-only batch it still asks before
anything that reaches outside or destroys, and the menu item names the wider scope when you grant
it on such a batch.

## Why is a tool marked "Disabled on gateway"?

The gateway has turned it off. The assistant shows it for transparency and never offers it to a run.

## Which workflow does the assistant use?

The one chosen in Settings → Models → Workflow, for the tray app and the CLI alike. The default
choice, **Gateway default**, runs the workflow the gateway operator set for
`abstractassistant.agent.v1`, or the app's built-in `abstractassistant-orchestrator` when the
gateway sets none. You can instead pick any workflow in the catalog that declares the assistant
interface; it always runs its latest version. The app never switches workflow on its own: if the
choice cannot run, sending is blocked and the palette says why. See
[settings.md](settings.md#models--reasoning).

## How does voice work?

Microphone audio is captured locally and played locally; STT and TTS run on the gateway. Replies
stream progressively when the gateway advertises streaming TTS. A hands-free conversation mode
(⌘⇧V) listens, sends, speaks and listens again. See [voice.md](voice.md).

## Why can't I interrupt the assistant by talking?

With the default barge-in setting the microphone is paused while the assistant speaks, so it
never transcribes itself through your speakers. Use Esc, the stop button, or switch Barge-in to
"Keep the mic open" when you use headphones.

## What does the activity card show?

The current step of the run (thinking cycle, tool call, waiting for you), the elapsed time, and the
most recent steps with their outcome and duration. It reads the run ledger the gateway streams;
nothing is estimated. Reattached runs show no total time because the start was not observed.

## How do I find an old chat, and can I delete one?

Click the chat name in the header. The switcher lists every chat with its topic, last activity and
what it holds (turns, tool calls, tokens, running time, workspace folder), grouped by recency and
filtered as you type. The pencil renames a chat; the bin deletes it and its transcript after an
in-row confirmation. Deleting removes that chat's folder under `~/.abstractassistant/sessions/`;
the gateway keeps its own durable session data.

## Where are downloads stored?

Under `~/.abstractassistant/downloads/`.

## Which auth model does the desktop app use?

Gateway bearer tokens or hosted gateway sessions, chosen in Settings → Connection, or a session
handed over by the gateway console when you click **Open** on the assistant's card. The CLI uses
the same saved sign-in, or `--gateway-token`.

## I clicked Open in the gateway console but the Assistant did not sign in

The console signs in only an Assistant it launches. If the Assistant was already running, quit it
from the menu-bar icon and click **Open** again. See [api.md](api.md#global-flags) for the
hand-over rules.

## Do replies stream?

When the gateway offers live replies, yes, according to Settings → Models → **Stream replies**:
Gateway default follows the gateway's own default, On streams, Off waits for the finished answer.
See [settings.md](settings.md#live-replies).

## Can I use it outside macOS?

macOS is the primary tray target. Linux and Windows may work, especially for the CLI, but they are
not validated to the same standard.

## How do I report a security issue?

Use the process in [../SECURITY.md](../SECURITY.md).
