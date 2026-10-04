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

Yes, in Settings → Workspace: the gateway's posture ("Deny everything, allow listed workspaces" or
"Allow everything, refuse listed workspaces"), the shared workspace (always on, Read & write) and each
listed workspace with Read & write / Read-only / Refused. You may lower what the admin allows, never
raise it; these are your account's workspaces on the gateway, the same in every client. Without a run
workspace, the gateway gives each chat a private workspace and later turns of the same chat reuse it.

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

The one chosen in Settings → Workflow, for the tray app and the CLI alike. The default
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

Click the chat name in the header. The **Sessions** tab lists every session on the gateway —
whichever client started it: the Assistant on any device, AbstractCode, AbstractObserver — with
its topic, last activity and what it holds (turns, state, and once opened here, tool calls,
tokens, running time, and the workspace the gateway reports, which opens in Finder when it
is on this Mac), grouped
by recency and filtered as you type; 100 at a time, with **Load more sessions** at the end. The
pencil renames a session on this device. There is no delete: a session exists as long as the
gateway lists it, and the gateway has no session delete.

## Can the assistant do something on a schedule?

Yes, on a gateway that offers automations. The clock button in the palette header opens
**Schedule this conversation…**: the conversation's workflow and last question, an interval in UTC
("every 8 hours", "every 7 days", or once at a time), whether each run starts fresh
(Independent, the default) or sees the previous runs (Growing), and whether its tools run without
asking (the default) or ask each time. The gateway runs it, also when the Assistant is closed.
Automations are listed in the session switcher's **Automations** tab and under
**Automations…** in the tray menu; opening one shows its runs as a chat with the **Active** switch
(off = paused), run now, stop, edit, archive and Discuss. You are notified only for results the workflow marks as
notable, failures after all retries, and runs waiting for your answer; ordinary results stay
quiet. Details: [automations.md](automations.md).

## Does the Assistant have to stay open for automations to run?

No. The gateway runs them. The Assistant only reads them: every 60 seconds while the palette is
visible and every 5 minutes while it is hidden, so notifications reach the tray. Results that
arrive while the Assistant is closed are waiting in the automation, marked new, when you open it.

## Why can't I approve a tool call when a scheduled run uses it?

With **Run without asking** (the default), creating the automation is the approval, and its
runs do not stop to ask. Choose **Ask me before each tool call** in the automation window to approve each run's tool
calls from the automation; see [automations.md](automations.md#tool-consent).

## Why don't the sessions of my automations appear among my chats?

Each automation's runs are grouped under the automation in the **Automations** tab, not
listed as chats: the switcher lists only sessions the gateway marks as chats or discussions. A
**Discuss** session is an ordinary chat and does appear, with the badge
"about automation <title>"; the automation's files are mounted read-only and the discussion has
its own writable workspace. The file tools refuse to write into the mount; shell commands are not
sandboxed, so approve them accordingly.

## I upgraded and some old chats are gone from the list

The session list comes from the gateway only: a chat that existed only on this Mac (for example
after the gateway was reset) is not a gateway session, so it is not listed. See
[architecture.md](architecture.md#sessions).

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
