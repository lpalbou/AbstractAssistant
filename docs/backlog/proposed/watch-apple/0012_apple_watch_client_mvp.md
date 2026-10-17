# Proposed: Apple Watch client MVP: waiting for you, ask, runs, automations

> Created: 2026-10-16 22:30:00 +0200
> Type: feature
> Priority: P1
> Labels: watch, apple, thin-client

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractassistant (`watch/apple/`)
- Track: [watch-apple](README.md) (Apple Watch client)

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md) (gateway-native thin client: the gateway owns workflows, runs, tools, policy and speech)
- ADR impact: None. The watch is one more thin client of the same gateway contract.

## Summary
Ship AbstractAssistant for Apple Watch 0.1: a standalone watchOS 26 SwiftUI app that shows the
runs waiting for the user (tool approvals and questions) and answers them, sends a dictated
question as a run of the default agent workflow, lists runs and automations with Run now, and
signs in with a pasted account token. Mock and live gateway clients behind one protocol.

## Why
The gateway already persists waits and answers them from any client. The wrist is the one
client you carry when away from the Mac, the terminal and the browser. The design, the
mockups and the animated prototype are in `watch/apple/` (README, docs/design.md,
docs/architecture.md, design/).

## Scope
- `watch/apple/` XcodeGen project, `Sources/App` SwiftUI screens from `docs/design.md` (Home,
  Approval, Approval done, Question, Ask / Listening / Thinking / Answer, Runs, Run detail,
  Automations, Automation result, Settings, Pairing by token).
- `Packages/AbstractGatewayClient`: async URLSession client with bearer auth, models for runs,
  waits, automations, `resume` and `cancel` commands, `runs/start`, polling helpers; tests run
  with `swift test` on macOS.
- Foreground polling (15 s; 2 s on the thinking screen), best-effort background refresh,
  haptics, stop on 401, offline state with age.
- Adopted from the cross-review on 2026-10-16 and built: the orb as the assistant's presence
  (idle / listening / thinking) and app icon; the responder picker (default assistant or one of
  the account's entities, `GET /entities`, `POST /entities/{name}/chat/open` + `turn`); an
  outreach approval card (`send_*` tools: recipient, subject, "View draft" with the body;
  "Send it" instead of "Allow once"; Double Tap off); run counts on Home (running / done / failed).
- `scripts/build.sh`: generate, test, build unsigned for the simulator, install, launch,
  screenshot per screen; device compile check.

## Non-goals
No push, no pairing code, no voice recording, no complications, no iPhone companion (items
0013–0017, 0019). No transcript browsing, no workflow editing, no gateway configuration.

## Current code reality
- The desktop assistant uses about 60 `/api/gateway/*` routes; the watch needs ten
  (`watch/apple/docs/architecture.md`, API mapping). Waits are discovered with
  `GET /runs?status=waiting` and answered with `POST /commands` `type: resume`
  (abstractgateway/docs/automations.md §Waits on a person; api.md §commands).
- A chat turn is `POST /runs/start {flow_id: "@default", interface: "abstractcode.agent.v1", …}`
  then `GET /runs/{id}` (abstractgateway/docs/api.md §runs). `abstractassistant.agent.v1` may
  have no host workflow on a given gateway; the watch falls back to `abstractcode.agent.v1`.
- There is no device pairing flow and one bearer token per account
  (abstractgateway/docs/security.md §tokens); 0.1 pastes the account token.
- No Python code in this repository is touched; `MANIFEST.in` and
  `[tool.setuptools.packages.find]` keep `watch/` out of the sdist and wheel (verify with a
  build).

## Dependencies
- Toolchain proven on 2026-10-16: Xcode 26.6, watchOS 26.5 SDK, XcodeGen 2.45.3, simulator
  "Apple Watch Series 11 (46mm)" (`untracked/watch/research/toolchain-check.md`).
- Gateway 0.15 API as documented; nothing new required for 0.1.

## Expected outcomes
- A developer runs `watch/apple/scripts/build.sh` and gets the app on the simulator with
  screenshots of every screen in mock mode.
- Against a live gateway on the LAN, the app lists waits, allows or denies one, and the
  desktop assistant shows the same wait as answered.
- A dictated question becomes a run and its `output` is shown on the watch.
- Verified live on 2026-10-16 through Tailscale Funnel (`https://forge.tail43a344.ts.net`) as the dedicated `watch` user: the app listed a real `execute_command` approval from a basic-agent run (the wait lives on the agent's child run; the list row carries only `waiting.reason`, the full block is on `GET /runs/{id}`), approved it through the live client, and the ledger recorded the `resume`; the run completed with the command's output (`watch/apple/screenshots/live/`).

## Acceptance Criteria
- [ ] `scripts/build.sh` passes on a clean checkout: package tests, simulator build, install, launch, 12 screenshots
- [ ] Live mode against a gateway: a `tool_approval` wait answered from the watch is recorded as a `resume` on the run's ledger and the run continues
- [ ] Live mode: an `ask_user` wait answered with a choice resumes the run
- [ ] Live mode: `runs/start` from the Ask screen returns an answer shown on the watch and listed in the desktop assistant's session list
- [ ] A 401 stops polling and shows the pairing screen; no retry loop (checked against the gateway's lockout counter)
- [ ] `python -m build` produces an sdist and wheel that contain no `watch/` files
- [ ] Stale approval protection: the same wait opened on the Mac and the watch is applied at most once; the second client shows "already handled" and sends nothing (spec tests T-09, T-10)
- [ ] An answer shows queued → applied (or rejected) distinctly; a request accepted by HTTP is never shown as applied before the run resumed
- [ ] Cellular-only test on the Series 11 with the iPhone off: waits, approve, ask and runs work over the public HTTPS address (spec tests T-02, T-03)
- [ ] Gateway restart during a run: the watch recovers the run state from `GET /runs/{id}` (spec test T-08)

## Testing
- `cd watch/apple && ./scripts/build.sh`
- `cd watch/apple/Packages/AbstractGatewayClient && swift test`
- `xcodebuild -project watch/apple/AbstractAssistantWatch.xcodeproj -scheme AbstractAssistantWatch -destination 'generic/platform=watchOS' -configuration Release build CODE_SIGNING_ALLOWED=NO`
- `python -m build && unzip -l dist/*.whl | grep -c watch/` (expect 0)

## Progress (2026-10-17)
- Runs on a Series 11 (watchOS 27.0.1), installed from the CLI (`watch/apple/scripts/deploy-watch.sh`; pairing procedure in `watch/apple/docs/pairing.md`), provisioned by launch arguments (`--gateway`, `--token`, kept in UserDefaults).
- Verified on the watch: approval of a real `execute_command` wait on a local gateway 0.14 through Tailscale Funnel; against gateway.abstractframework.ai (0.15): sign-in, waits (a 19-day-old `fetch_url` approval with its URL), runs, automations with unseen counts, entities (Pollux, "asleep · born 6 Oct"). Run detail with the ledger, Cancel, Run now and Mark read are built and unit-tested on the real payload shapes but were not tapped on the device.
- Ask from the watch to the Assistant on the public gateway completes (after its provider key was fixed the same night). A root run waiting on its agent (`subworkflow:<child>`) was mistaken for a person's wait and opened an empty approval; fixed, with a test. The entity Pollux still gets `HTTP 401`: it follows the gateway default, but the entity chat host reads provider keys from a config snapshot taken at gateway start (runs read them fresh), so a key change needs a gateway restart until the gateway is fixed.
- Markdown rendering, Read aloud with the orb following the voice (gateway TTS stream, verified on the watch speaker), and a Link screen (page text in the app, Handoff to the iPhone) added the same night.
- Still open in this item: a dedicated watch user on the public gateway (the token in use is an admin token and the Account row says so), the entity-turn path verified end to end on a gateway whose provider answers, Double Tap and risk tiers (0015), audio (0016), push (0014), device pairing (0013).
