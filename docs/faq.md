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
allow … on this Mac" in the approval sheet (offered for observe and act tools), or trust the
enabled tools for the current chat. Chat-wide trust covers the observe and act tiers; outreach
and destructive calls keep asking unless you set that tool to Auto by name.

## Why is a tool marked "Disabled on gateway"?

The gateway has turned it off. The assistant shows it for transparency and never offers it to a run.

## Which workflow does the assistant use?

The published gateway workflow bundle `abstractassistant-orchestrator`. The tray app and the CLI
both run through it; there is no workflow picker in the normal desktop path.

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

## Where are downloads stored?

Under `~/.abstractassistant/downloads/`.

## Which auth model does the desktop app use?

Gateway bearer tokens or hosted gateway sessions, chosen in Settings → Connection. The CLI is
bearer-token oriented.

## Can I use it outside macOS?

macOS is the primary tray target. Linux and Windows may work, especially for the CLI, but they are
not validated to the same standard.

## How do I report a security issue?

Use the process in [../SECURITY.md](../SECURITY.md).
