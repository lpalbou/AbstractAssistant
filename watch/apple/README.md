# AbstractAssistant for Apple Watch

**Your AI, everywhere. On your wrist.** A thin, secure client for your AbstractGateway.

Status: design proposal and buildable scaffold (2026-10-16). Nothing here is released. The watch
app is a thin client of AbstractGateway, like the desktop assistant: the gateway owns workflows,
runs, tools, policy and speech; the watch owns nothing but a token and a cache.

## Why a watch app

The gateway already makes runs durable and waits first-class: an agent stops at a tool approval or a
question, the run is persisted, and the answer can come from any client. The desktop assistant,
the terminal client and the browser render that wait today. The wrist is the one surface you carry
when you are away from all three. So the watch app is not a chat app. It is the **decision and
continuity surface** of your gateway:

- **Decide.** Approvals and questions reach your wrist with a haptic; you allow, deny or answer in
  one tap, and the run continues on your Mac. Each answer is a ledger record with who and when.
- **Ask.** A short question, dictated, becomes a run of your default agent workflow; the answer
  comes back as text and can be spoken.
- **Know.** Runs and automations at a glance, a complication that says "2 waiting for you".
- **Continue.** Everything is the same session as on the Mac: "Continue on Mac" is not a hand-off,
  it is the same run viewed from another client.

## What it is not

- Not a transcript browser, not a workflow editor, not a place to configure the gateway.
- Not a model host: nothing runs on the watch; speech-to-text and text-to-speech run on the
  gateway, through the run-scoped audio routes.
- Not a replacement for the desktop assistant's hands-free loop.

## Where it lives and why

`abstractassistant/watch/apple/` inside the AbstractAssistant repository.

- One product, one identity, one documentation and backlog system. ADR 0001 (gateway-native thin
  client) applies to the watch verbatim.
- The folder name leaves room for parity: `watch/wearos/` later, and a shared Swift package can
  move to `clients/swift/` the day a native iOS or macOS client appears.
- The Swift sources are excluded from the Python sdist and wheel (`MANIFEST.in`,
  `[tool.setuptools.packages.find]` only includes `abstractassistant*`). The watch app has its own
  version (`MARKETING_VERSION` in `project.yml`) and its own release channel (TestFlight, App
  Store), so the PyPI cadence is untouched.
- A separate repository was considered and set aside: it would fragment identity and docs, add a
  25th repository for one maintainer, and the only thing worth sharing (the Swift gateway client)
  can be extracted later if two apps need it.

## Scope by version

| Version | Ships | Needs from the gateway |
|---|---|---|
| 0.1 (this scaffold) | Waiting for you (tool approvals, outreach sends with the draft, questions), Ask by voice to the default assistant or to one of your entities (picker): tap the orb and speak, the gateway transcribes, the orb speaks the answer, the answer comes back as a notification when the app is not on screen; markdown answers, read aloud, links read in the app, Runs with counts, Automations with Run now, Settings. Foreground polling every 15 s, best-effort background refresh, haptics, Double Tap on safe approvals only. Sign-in with a pasted account token. | Nothing new. Uses `GET /api/gateway/runs?status=waiting` + `GET /runs/{id}`, `POST /api/gateway/commands`, `POST /api/gateway/runs/start`, `GET /api/gateway/entities` + `POST /entities/{name}/chat/open|turn`, `GET /api/gateway/automations`. |
| 0.2 | Push notifications with Allow / Deny actions, pairing by short code with a per-device revocable token, Allow all in this run, risk tier on the approval card, voice in and out through the gateway, Smart Stack widget and corner complication, Siri "Ask my assistant". | Device pairing and per-device tokens; a notification bridge (APNs); risk tier and approve-all in the wait payload; session-scoped transcription. See the backlog track. |
| 0.3 | Optional iPhone companion (pairing by QR, local notification relay), Wear OS parity study. | None beyond 0.2. |

## Reaching the gateway from a cellular watch

The gateway never terminates TLS and listens on loopback by default. A watch on cellular needs an
HTTPS address: Tailscale Funnel, Cloudflare Tunnel, or a reverse proxy in front of a gateway set to
the `internet` network mode, with accounts on. There is no Tailscale client for watchOS, so a
tailnet-only address does not work away from the phone. On a LAN, plain HTTP works for development
only, with an App Transport Security exception for local networking.

With Tailscale (Funnel enabled on the tailnet), the whole setup is:

```sh
abstractgateway network set --mode internet --acknowledge-internet   # or the console's Network page
tailscale funnel 8080            # foreground: the public address exists while this runs
tailscale funnel --bg 8080       # or persistent across logins; `tailscale funnel off` removes it
curl https://<host>.<tailnet>.ts.net/api/health
```

Funnel runs on the gateway machine, so the gateway believes its `X-Forwarded-For`: sign-in
lockouts and the audit log see the real client address, and no loopback-only privilege leaks to
the internet. Give the watch its own account (`POST /api/gateway/admin/users {user_id: "watch",
roles: ["user"]}`, token shown once); never put the admin token on a watch.

## Design and prototype

- `docs/design.md` — screens, flows, interaction rules (haptics, Double Tap, what never happens
  without a tap), states and error handling. The orb (`Sources/App/Shared/Orb.swift`) is the
  assistant's presence: it breathes when idle, becomes a constellation of dots while listening, orbits while
  thinking; `design/anim/orb-states.gif` shows the three states captured from the simulator.
- `docs/architecture.md` — client architecture, API mapping, polling and push, security, the gaps
  that need gateway work.
- `design/screens/` — 16 screen mockups (PNG in a Series 11 46 mm frame, SVG sources) generated by
  `design/make_screens.py`; `design/sheet.png` shows them all.
- `design/prototype.html` — animated prototype of the three key flows (an approval arrives, ask by
  voice, an automation result); `design/flows/*.gif` are the same flows as GIFs.
- `../../docs/backlog/proposed/watch-apple/` — the backlog track.

## Build and run

Requires Xcode 27.1 with the watchOS 26 simulator and XcodeGen; a paired watch for the device build.

```sh
cd watch/apple
./scripts/build.sh                                   # generate, test the Swift package, build, run in the simulator, screenshot
./scripts/deploy-watch.sh --env <file with GW_URL and GW_TOKEN>   # signed build, install on the paired watch, launch provisioned
```

`docs/pairing.md` is the watchOS 27 pairing procedure; the app has run on a Series 11 against a
local gateway through Tailscale Funnel and against gateway.abstractframework.ai.

Launch arguments select the initial screen for screenshots (`--screen approval`) and the data
source (`--mock`, the default in Debug). `scripts/run-live.sh [screen]` launches the installed
simulator app in live mode against the gateway named in a private env file and captures a
screenshot; `EXTRA="--test-action allow-first"` answers the first real wait, for an end-to-end
check without a tap. See `BUILD.md` and `docs/architecture.md`.

## Apple developer account

Simulator builds and the Swift package tests need no account. A device build signs with an Apple
developer team (`DEVELOPMENT_TEAM` in `project.yml`, automatic signing).
