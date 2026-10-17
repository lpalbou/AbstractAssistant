# AbstractAssistant for Apple Watch

**Your AI, everywhere. On your wrist.** A voice-first Apple Watch app for your AbstractGateway.

Version 0.2.0 · watchOS 26 or later · watch-only (no iPhone app needed) · pre-release through
TestFlight. See [CHANGELOG.md](CHANGELOG.md) for what changed.

The watch app is a thin client of AbstractGateway, like the desktop assistant: the gateway owns
workflows, runs, tools, policy and speech, and the watch keeps only your sign-in and what it shows.
Everything you do on the watch is the same session you see on your Mac, in the terminal or in the
browser.

## What you can do

**Talk to your assistant.** The orb is the assistant. Tap it and speak; tap again, or stop speaking
for 3 seconds, to send. The gateway transcribes what you said, the answer appears under the orb in
markdown, and the orb speaks it, swirling with its own voice. Tap the orb to pause and resume the
voice. A small keyboard icon lets you type, dictate or scribble instead.

**Choose who answers.** "Assistant ⌄" at the top of the orb screen switches between:

- **Assistant** — a one-shot agent: you ask, it works with its tools, it answers.
- **Entities** — someone you keep talking with over time, who remembers. Each entity has its own
  colour and shape (planet, kitty, face, wave), set on the gateway.

**Decide what needs you.** When an agent wants to use a tool or asks a question, it appears on your
wrist with a haptic:

- an approval says what the assistant wants to do ("Run a command", "Send an email") and exactly
  what (the command, the page, the recipient and subject, the full email);
- three icons answer it: deny, allow once, and, from a conversation, allow all tools for the rest
  of that conversation (sends to other people always ask);
- a question shows its choices, or takes your own answer.

**Pick up a conversation.** Sessions lists your conversations (Today, Yesterday, Earlier) with the
number of exchanges and tools. Tap one to continue it on the orb; open its details to read its
recent exchanges.

**Follow your automations.** New automation (top of the list) creates one: the task, the
workflow that runs it, when it runs (every few minutes to every week, or daily at a time), whether
each run builds on the earlier ones, and whether it asks before using tools. Each automation shows how often it runs and when it runs next
("🕐 12h ➜ 6h"). Its page has:

- Run now, on the schedule line; while it runs, you see what the agent is doing ("Searching the
  web…", "Reading 4 web pages…"), you can stop it, and you can leave: a notification brings the
  result;
- the latest result in full, readable aloud by the orb;
- Edit: the task, how often it runs, whether each run builds on the earlier ones, active or paused;
- the earlier runs, five at first, any of them opened in full.

**Get answers while away.** An answer that arrives after you left the app comes as a notification.
New approvals and questions are checked in the background about every 15 minutes; an ordinary tool
approval can be allowed or denied from the notification itself.

**Read aloud.** Any answer or automation result can be read by the orb. Tap the orb to pause or
resume; the rewind icon beside Back goes back 10 seconds.

**Make it yours.** Settings → Orb style offers six orbs (Halo, Vortex, Nebula, Rings, Liquid,
Galaxy), asked once at first launch. Settings → Read aloud turns the spoken answers on or off; Settings → About shows the version
and build of the app.

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
- Risk levels come from the gateway's tool catalog; the approval itself does not carry one yet.
- Editing long text is done in the watch's own text editor.

## Documentation

- [docs/design.md](docs/design.md) — screens, flows and interaction rules.
- [docs/architecture.md](docs/architecture.md) — components, the gateway calls behind each screen,
  background behaviour and security.
- [BUILD.md](BUILD.md) — build, test, run in the simulator and on a watch, App Store packaging.
- [docs/pairing.md](docs/pairing.md) — pairing a physical watch for development.
- [CHANGELOG.md](CHANGELOG.md) — release history of the watch app.
- [../../docs/backlog/proposed/watch-apple/](../../docs/backlog/proposed/watch-apple/) — planned work.

The watch app is part of [AbstractAssistant](../../README.md) and of
[AbstractFramework](https://abstractframework.ai). MIT License.
