# AbstractAssistant for Apple Watch

**Your AI, everywhere. On your wrist.** A voice-first Apple Watch app for your AbstractGateway.

Version 0.3.0 · watchOS 26 or later · independent (no iPhone app needed) · pre-release through
TestFlight. See [CHANGELOG.md](CHANGELOG.md) for what changed.

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
(beside Back while it listens, works or speaks) or a 1.5 s hold on the orb stops what it is doing,
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
how many times it has run, how often it runs and when next; a switch turns one off and on, and its
archive button archives it (Archived brings it back). Its page shows its instructions in full, Run
now (with live progress, and you can leave: a notification brings the result), the latest result in
full, Edit (its title, task and instructions, apart), and the earlier runs; once read, a page opens
at once. Every screen shows a spinner until
its information is in, and an error only once reading it has failed several times.

**Get answers while away.** An answer that arrives after you left the app comes as a notification.
New approvals and questions are checked in the background about every 15 minutes; an ordinary tool
approval can be allowed or denied from the notification itself.

**Make it yours.** Settings has Connection (the gateway and account you use), Tools (the defaults
for new conversations), Voice (the speaking voice, its speed and the transcription model), Read
aloud, Orb style (thirty-three styles in six families: Orbs, Forms, Cosmos, Nature, Faces and Machines, each previewed live through listening, thinking, working and speaking) and About.

## Sign in

The first screen asks for your **user or email**, on `gateway.abstractframework.ai` by default (tap
the server line to change it):

- a user name asks for its account token;
- a registered email receives an 8-digit one-time code from the gateway, which signs you in for
  30 days.

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

- **TestFlight.** Testers invited to the TestFlight build install it from the TestFlight app; the
  watch app installs on the paired watch.
- **From source.** Build and run in the simulator or on your own watch with Xcode: see
  [BUILD.md](BUILD.md) and [docs/pairing.md](docs/pairing.md).

## Current limits

- No push notifications: the app polls the gateway every 15 seconds while it is on screen, and
  watchOS decides when background checks run.
- Your sign-in is kept in the app's storage on the watch, not in a sealed store.
- Tools allowed with Accept all are approved by the watch while it follows the run; away from the
  orb page, they ask.
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
