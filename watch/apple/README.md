# AbstractAssistant for Apple Watch

**Your AI, everywhere. On your wrist.** A voice-first Apple Watch app for your AbstractGateway.

Version 0.16.0 · watchOS 26 or later · the companion of the [AbstractAssistant iPhone
app](../../phone/iphone/README.md), and independent (it also works with no iPhone nearby) ·
pre-release through TestFlight. See [CHANGELOG.md](CHANGELOG.md) for what changed.

**One product, two independent devices.** AbstractAssistant is one app for iPhone and Apple
Watch: the watch app ships inside the iPhone app. Each signs in on its own, possibly to another
gateway or account, and the watch works without the iPhone app.

The watch app is a thin client of AbstractGateway, like the desktop assistant: the gateway owns
workflows, runs, tools, policy, speech and search, and the watch keeps only your sign-in, your
choices for it and what it shows. Everything you do on the watch is the same session you see on
your Mac, in the terminal or in the browser.

## What you can do

**Talk to your assistant.** The orb is the assistant. Tap it and speak; tap again, or stop speaking
for 3 seconds, to send. The keyboard icon lets you type, dictate or scribble instead. While the
assistant works, the space below the orb shows its steps live (thinking, each tool with what it is
about, an image being made) and the orb pulses with each tool call, a satellite circling it for
each tool running. The answer appears in markdown and the orb speaks it, following its voice; the
voice button beside Back plays, pauses and rewinds. A tap on the orb pauses or resumes it; Stop
(beside Back while it listens, works or speaks) or a one-second hold on the orb stops what it is doing,
and at rest the same hold reads the last answer aloud. Once a conversation has a message, swipe
to the left from the orb for its numbers and files (each one shareable).

**Swipe as in a browser.** A swipe to the right (your finger moving right, as with watchOS's Back)
goes back to the page before, down to Home; a swipe to the left goes forward again to a page you
came back from, and does nothing when there is none.

**Choose who answers and with what.** "Assistant ⌄" below the orb switches between the
**Assistant** (it works with its tools and answers) and your **entities** (someone you keep talking
with, who remembers; each has its own colour and shape). The tools icon opens this conversation's
tools (Off, Auto or Ask for each, by group, with its risk) and its **Workflow**: choose
"AbstractAssistant Orchestrator" and the assistant also makes images and recordings, shown under
its answer (tap an image for full screen; the Digital Crown zooms).

**Decide what needs you.** When an agent wants to use a tool or asks a question, it appears on your
wrist with a haptic: what it wants to do and exactly what (the command, the page, the recipient and
the email). Deny, allow once, or, from a conversation, allow its tools for the rest of it; while it
works, the amber shield on the orb takes that back at once. Sends to other people always ask.

**Find and tidy your conversations.** Sessions lists your conversations (Today, Yesterday,
Earlier), outlines the ones with an answer you have not opened, searches every question, answer and
artifact (an image by what it was made from, a file by its name), and archives one with the
archive button at its right (Archived brings it back). Each says how long ago it last changed. Tap a conversation to continue it on the orb.

**Follow your automations.** New automation creates one: the task, the workflow, the tools it may
use, when it runs and whether each run builds on the earlier ones. In the list, each shows its name,
how many times it has run, how often it runs and when next, and the runs you have not seen in an
orange badge; New and Search sit on one line, as in Sessions, and its archive button archives it
(Archived brings it back). It opens on the same orb page as a
conversation: its runs are the messages (what its trigger sent, then the answer), the orb follows a
run in progress and speaks its answer, and talking there opens a conversation about it (its own runs
never read it). Its details sit behind (i), where a conversation has its tools: when it runs, Run,
and Edit (its title and task apart; Active and how often; whether it builds on its earlier runs and
how much of them it reads, in tokens); once read, a page opens at once. Every screen shows a spinner until
its information is in, and an error only once reading it has failed several times.

**Get answers while away.** An answer that arrives after you left the app comes as a notification.
New approvals and questions, and new results from your automations, are read from your gateway's
event stream in the background about every 15 minutes and when the app opens: what needs you comes
as a time-sensitive notification, results as quiet news. With a push forwarder on your gateway they
arrive at once, through Apple push, and the app never shows twice what a push showed. (With an older
gateway, or when the stream cannot be read, the watch reads the waits and automations instead, and an
ordinary tool approval can be allowed or denied from the notification itself.) An automation that finishes a run
posts a notification ("Morning digest finished"; a tap opens it), shown as a banner when the app
is open; Settings → Notifications turns this off.

**See it on your watch face.** The **Assistant** complication puts your avatar on a face: the orb
style you chose, as the app draws it (the app's own orb until the app has opened once), in one of
three states: at rest; speaking, with a dot, when there is news (results or messages you have not
seen); listening, with an amber badge giving the number of approvals and questions waiting for
you. A tap opens the app. It fits the circular, corner and inline slots of a face, and the rectangular one (and the
Smart Stack) adds what needs you first, your next automation ("Morning digest · 2h") and the
results you have not seen. Add it from the face's Edit screen, under Assistant. It shows what the
app last read: the app updates it as it reads, and the background check about every 15 minutes
while it is closed; a new orb style reaches it the next time the app is open. A face that draws
its complications in one tint shows the orb's light in that tint (its picture as a mask, so your
style keeps its shape and texture there); faces such as Infograph and Modular Duo keep its colours.

**Make it yours.** Settings has Connection (the gateway and account you use), Tools (the defaults
for new conversations), Voice (the speaking voice, its speed and the transcription model; the voices in
groups, Your voices, Engine voices and Shared voices, each with its language and a "Voices that speak"
filter; voices are created on the iPhone or the desktop), Read
aloud, Orb style (thirty-four styles in six families: Orbs, Forms, Cosmos, Nature, Faces and Machines, each previewed live through listening, thinking, working and speaking) and About.

## Sign in

The first screen shows the **gateway** (`gateway.abstractframework.ai` by default, then the last one
you signed into; tap it to pick another gateway you have used or type a new address), then asks for
your **user or email**:

- a user name asks for its account token;
- a registered email receives an 8-digit one-time code from the gateway, which signs you in for
  30 days.

Sign out (Settings, or Settings → Connection) asks whether to **keep your sign-in**: a kept sign-in
shows on the sign-in page as "Sign in as <user>" for its gateway only, and one tap signs you in
again. The gateway chooser lists every gateway you signed into or kept an account on (with how
many accounts) and AbstractFramework's own. "Sign out and forget" removes the account, and so does
the gateway refusing it. Once signed out, the watch stays signed out until you sign in on it.

Give the watch its own gateway account with the `user` role; do not put an admin token on a watch.

## Reaching your gateway from the watch

The watch needs an HTTPS address for your gateway. A gateway on your Mac can be published with
Tailscale Funnel, Cloudflare Tunnel or a reverse proxy, with accounts on and the gateway's network
mode set to `internet`. There is no Tailscale client for watchOS, so a tailnet-only address does not
work away from the phone. With Tailscale Funnel:

```sh
abstractgateway network set --mode internet --acknowledge-internet   # or the console's Network page
tailscale funnel --bg 8080                                           # `tailscale funnel off` removes it
curl https://<host>.<tailnet>.ts.net/api/health
```

## Install

- **TestFlight.** Testers invited to the TestFlight build install AbstractAssistant on the
  iPhone from the TestFlight app; the watch app installs on the paired watch with it.
- **From source.** Build and run in the simulator or on your own watch with Xcode: see
  [BUILD.md](BUILD.md) and [docs/pairing.md](docs/pairing.md).

## Current limits

- While the app is on screen it polls the gateway every 15 seconds. While it is closed,
  approvals, questions, published alerts and automation results arrive through Apple push once
  your gateway has a push forwarder (the app registers itself at sign-in; nothing to set up);
  until then watchOS decides when background checks run, about every 15 minutes.
- An automation's result or failure, and a flow's "Notify me", arrive quietly in Notification
  Center (no sound); approvals and questions alert.
- When an iPhone is signed in to the same account, the gateway pushes the iPhone and Apple forwards
  the alert to your wrist (iPhone locked, watch worn). Away from that iPhone, the watch shows it
  when the app next opens or checks.
- Known issue: on a development build, a push can arrive with its generic words ("Approval
  needed", "Open the Assistant to answer") when the notification extension did not replace them;
  the item itself is in the app. A Debug build's `--dump-notify` readout shows why
  ([BUILD.md](BUILD.md#the-notifier-readout)).
- Your sign-in is kept in the watch's Keychain (shared with its notification extension and the
  complication). The accounts you keep at Sign out ("Keep my sign-in") are a second Keychain item, filed by gateway.
- Tools allowed with Approve all are approved by the watch when it sees their approvals (on the orb
  page, or in its regular check while the app is open); with the app closed, they ask. Approve all
  covers the run's own conversation, or its automation, by that one's own tools.
- "New" answers are tracked on this watch: an answer read on another device still shows as new here.
- Search and the live steps read your gateway's data: search needs a gateway that serves it, and
  the live steps read the run's records (about as much data as reading an answer aloud).

## Documentation

- [docs/README.md](docs/README.md) — the index of these pages.
- [docs/design.md](docs/design.md) — screens, flows and interaction rules.
- [docs/architecture.md](docs/architecture.md) — components, the gateway calls behind each screen,
  background behaviour and security.
- [BUILD.md](BUILD.md) — build, test, run in the simulator and on a watch, App Store packaging.
- [docs/pairing.md](docs/pairing.md) — pairing a physical watch for development.
- [CHANGELOG.md](CHANGELOG.md) — release history of the watch app.
- [../../docs/backlog/proposed/watch-apple/](../../docs/backlog/proposed/watch-apple/) — planned work.

The watch app is part of [AbstractAssistant](../../README.md) and of
[AbstractFramework](https://abstractframework.ai). MIT License.

Store delivery packages this independent Watch app with the iPhone app in the existing
AbstractAssistant listing. Use **Actions → Apple app (iPhone + Watch)**; see
[testing and distribution](../../phone/iphone/docs/distribution.md).
