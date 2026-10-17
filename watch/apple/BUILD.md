# AbstractAssistant for Apple Watch

Standalone watchOS 26+ SwiftUI app (watch-only, no iPhone companion) plus a SwiftPM gateway client.
Runs on the simulator with mock data; the live client talks to AbstractGateway with a bearer token,
on the simulator or on a paired watch (tested on a Series 11, watchOS 27.0.1, against a local
gateway 0.14 through Tailscale Funnel and against gateway.abstractframework.ai, 0.15).

## Build and run (simulator)

Needs Xcode 27.1 (watchOS 26.5 simulator runtime) and xcodegen (2.45.3 tested). Simulator builds
need no signing and no Apple account.

```sh
cd watch/apple
scripts/build.sh               # generate + swift test + simulator build + install + 12 screenshots (~70 s)
scripts/build.sh --no-screens  # generate + swift test + build only
```

What the script runs:

```sh
xcodegen generate --spec project.yml
(cd Packages/AbstractGatewayClient && swift test)          # macOS, no simulator
xcodebuild -project AbstractAssistantWatch.xcodeproj -scheme AbstractAssistantWatch \
  -destination 'platform=watchOS Simulator,name=Apple Watch Series 11 (46mm)' \
  -configuration Debug -derivedDataPath build/DerivedData build CODE_SIGNING_ALLOWED=NO
xcrun simctl boot "Apple Watch Series 11 (46mm)"; xcrun simctl bootstatus "Apple Watch Series 11 (46mm)"
xcrun simctl install "Apple Watch Series 11 (46mm)" build/DerivedData/Build/Products/Debug-watchsimulator/AbstractAssistantWatch.app
xcrun simctl launch "Apple Watch Series 11 (46mm)" ai.abstractframework.assistant.watch --mock --screen approval
xcrun simctl io "Apple Watch Series 11 (46mm)" screenshot screenshots/approval.png
xcrun simctl shutdown "Apple Watch Series 11 (46mm)"
```

Override the simulator with `SIM="Apple Watch ..." scripts/build.sh`. Screenshots land in `screenshots/<screen>.png`.
Only the install step catches a wrong standalone key: `INFOPLIST_KEY_WKWatchOnly: YES` must be the only one (research/toolchain-check.md C).

## Launch arguments

| Argument | Effect |
|---|---|
| `--screen <name>` | initial screen: `home` `approval` `email` (an outreach send) `draft` `done` `askuser` `ask` `ask-entity` `picker` `listening` `thinking` `answer` `runs` `run` `automations` `settings` `pairing` `signin` |
| `--mock` | mock client (screenshots); without it the app is live: a saved sign-in, else the sign-in page |
| `--live --gateway <url> --token <token>` | live client against a gateway; `--gateway`/`--token` are SAVED (UserDefaults `gateway.url`/`gateway.token`), so one launch provisions a watch and every later launch, including Xcode's Run, stays live |
| `--forget-gateway` | forgets the saved credential (the sign-in page shows; the gateway address stays as its default) |
| `--user <id>` | with `--gateway`/`--token`: the account name kept with the token |
| `--test-identify <user or email>` / `--test-secret <token or code>` | test hooks: the sign-in page fills and submits them |
| `--test-pause` | test hook: the Read screen pauses 2 s into the speech and resumes 3 s later (logged) |
| `--test-approve once\|all` | test hook: the next approval screen answers itself after 2 s (Allow once / Allow all in this session) |
| `--test-action allow-first\|deny-first` | simulator test hook: answers the first wait after the first poll |
| `--test-ask "<prompt>"` | live test hook: opens Ask and sends the prompt once |
| `--test-read "<markdown>"` | live test hook: opens Read on that text, spoken through the newest run's session |
| `--test-open <url>` | test hook: opens a URL as a tapped link does (the Link screen) |
| `--test-listen` | test hook: opens Ask and starts listening at once (with the Mac's `say`, a full voice check in the simulator) |
| `--no-notification-prompt` | screenshot runs: never show the one-time notification question |

## Mock vs live

- `MockGatewayClient` (actor) carries the mockups' content: 3 waits (`send_email` to a team address from the Morning digest automation, with subject and body for "View draft"; `execute_command` `rm -rf build/ && make`, Destructive, coding-agent; `ask_user` from deep-research with three choices), 5 runs, 3 automations, 3 entities (castor, mira, nerin) whose chat answers a canned reply after 1.6 s. A started run "streams" a canned answer word by word through the same `GET runs/{id}` polling path the live client uses.
- `LiveGatewayClient` (actor, URLSession async/await, `Authorization: Bearer`) implements `GET /api/health`, `GET /api/gateway/me`, `GET /api/gateway/runs?status=waiting` (waits projected from each row's `waiting` block), `GET /api/gateway/runs?root_only=true&limit=20`, `GET /api/gateway/runs/{id}`, `POST /api/gateway/runs/start` (`@default`, `abstractcode.agent.v1`, `use_session_history: true`), `POST /api/gateway/commands` (`resume` with `{approved}` or `{response}`), `GET /api/gateway/automations`, `POST /api/gateway/automations/{id}/commands` (`automation.run_now`), `GET /api/gateway/automations/{id}/occurrences?limit=`, `POST /api/gateway/automations/{id}/seen` (`{attention_cursor}`), `GET /api/gateway/runs/{id}/ledger?after=` (replayed on Run detail and followed every 2 s while the run is live; the Ask screen shows the last record as the thinking step), `POST /api/gateway/commands` `cancel`, `GET /api/gateway/entities`, `POST /api/gateway/entities/{name}/chat/open` and `.../chat/{id}/turn` (reopened once on 404/409). After a 401 it sends nothing more (the gateway locks out per address) and polling stops.
- `AppModel` (@MainActor) polls waits, runs and automations every 15 s while the app is on screen, including the dimmed wrist-down state; it stops in the background. The three first-poll calls go out together. Waits and runs are published before the automations call (7 s on the public gateway, measured) and an automations failure never marks the gateway offline. Until the first answer the Home dot is amber with "connecting…". Haptics: `.notification` on a new wait, `.success` on allow, `.failure` on a failed answer.
- Double Tap (`.handGestureShortcut(.primaryAction)`) is attached to Allow once only when the wait is not destructive.

Checked against a live gateway (0.14, 2026-10-16, through Tailscale Funnel): an agent run's final text is `output.response` (`output` is `{response, success, meta}`); the runs list row carries only `waiting.reason`, so the client reads `GET /runs/{id}` for each row with `reason == "user"` and projects the wait from its full `waiting` block (`wait_key` prefix `tool_approval:` or `ask_user:`, `details.tool_calls`); the approval lives on the agent's child run. `answer` re-reads the run first and throws `alreadyHandled` when the key changed.

## On a paired watch

`docs/pairing.md` is the watchOS 27 pairing procedure (Device Hub → `+` → Pair Nearby Device makes
the Developer Mode row appear on the watch). Then:

```sh
scripts/deploy-watch.sh --env ../../../untracked/watch/.secrets/public-gateway.env   # signed build, install, launch provisioned (GW_URL, GW_TOKEN)
scripts/deploy-watch.sh --no-build --screen picker --shoot picker                     # relaunch at a screen, screenshot to design/screenshots/device/
scripts/deploy-watch.sh --no-build --forget                                           # clear the pairing on the watch
```

The device build signs automatically (`DEVELOPMENT_TEAM` in `project.yml`, `-allowProvisioningUpdates`);
the CoreDevice id comes from `xcrun devicectl list devices`, kept in `untracked/watch/.secrets/watch-device-id.txt`.
Give the watch its own gateway user: with an admin token the Account row says so, and every approval
from the wrist carries admin rights.

Live run (simulator): `scripts/run-live.sh [screen]` reads `GW_URL` and `GW_WATCH_TOKEN` from `../../../untracked/watch/.secrets/watch.env` (override with `GW_ENV=`), launches with `--live`, waits `WAIT` seconds (default 8) and writes `screenshots/live/<screen>.png`. `EXTRA="--test-action allow-first"` (or `deny-first`) answers the first real wait once, for an end-to-end check.

## Known gaps

- No push: polling only, foreground only. The gateway has no push channel.
- Sign-in: first launch, Sign out, or a 401 from the gateway shows the sign-in page (`Settings/SignInView.swift`). "User or email": a user name asks for its token, checked with `GET /api/gateway/me` (the account must be the one typed); an email address asks the gateway for an emailed 8-digit code (`POST /api/gateway/session/recovery/request`) and redeems it (`/session/recovery/redeem`, `remember: true`), keeping the session and CSRF values from its cookies as the credential (`X-AbstractGateway-Session`, `X-AbstractGateway-CSRF` on writes). The credential is kept in UserDefaults (scaffold, not a sealed store). An email is resolved to its account by the gateway: that resolution is new in abstractgateway (`mail/recovery.py` `account_for`, uncommitted, unreleased, tested), so on a released gateway only the account id works for codes. The gateway also needs "Sign-in by email" on and an email plus a connected mailbox on the account; gateway.abstractframework.ai answers "This account has no email address" today. Verified in the simulator against the public gateway: the token path signs in; the email path shows the gateway's answer. Not verified: a real code end to end (no account there has an email).
- Persona: every Ask run carries `input_data.system` (AbstractAssistant, built on AbstractFramework, answers read aloud on a watch); the gateway's default agent has none of its own ("I'm ChatGPT" before, "I'm AbstractAssistant, your personal AI assistant" after, verified live). The agent keeps its tools.
- Sessions: `GET /runs?root_only=true&session_kind=chat,discussion&include_metrics=true&limit=80` (Show older adds 100) grouped by `session_id` on the watch; titles = first line of the first prompt (`GET /runs/{id}/input_data`), cut to ~32 characters, cached; Today / Yesterday / Earlier; a tap continues the conversation (Ask opens on its last exchange, in that session), a swipe opens its details (last six exchanges, loaded in parallel). A gateway sessions endpoint with written titles and paging is the right long-term source.
- Waits while closed: a background refresh about every 15 minutes (`.backgroundTask(.appRefresh("assistant.waits"))`) posts each new wait once: Allow (needs the watch unlocked) + Deny for ordinary tools, Deny only for sends and destructive calls; a question opens the app. Not yet observed on the watch (needs notification permission and watchOS's refresh budget).
- Speech in pieces: the text is split along its markdown blocks (the first block alone), one TTS stream request per piece, so the next piece synthesizes while the current one plays.
- Approvals from Ask: answering returns to the orb, which follows the run again. "Allow all in this session" trusts the Ask session (the watch answers later approvals of the run; new runs carry `_runtime.tool_policy` with `auto_approve_max_risk_rank: 4` and the outreach tools in `require_approval_tools`). Risk pills come from `GET /api/gateway/discovery/tools` (`risk_tier`: observe, act, outreach, destroy) and gate Double Tap. Verified in the simulator against the public gateway: approval of the first `fetch_url` with Allow all, back on the orb, the second `fetch_url` answered by the watch, answer spoken.
- Wrist down: watchOS suspends the app a few seconds after the screen dims, which stopped the voice mid-sentence (device trace 2026-10-17: scene inactive at 4:37:14, a 14.6 s chunk started at 4:37:15 and never finished, the next chunk never played). `RuntimeKeeper` now holds a `WKExtendedRuntimeSession` (`WKBackgroundModes: self-care`, up to 10 minutes) from the tap that starts a turn until the voice ends; it can only start while the app is active. Not yet verified on the watch (every test launch found the screen off, and the simulator refuses these sessions with an unknown error); a stream that breaks midway now ends with "The voice stopped early" instead of silence. Debug builds log `scene`, `keeper` and `speaker` lines to the console (`devicectl device process launch --console`).
- Pause: tap the speaking orb (Ask answer, Read) to pause, tap again to resume. Verified in the simulator: paused at 2.02 s of the sentence, resumed at 2.02 s, a chunk that arrived during the pause played after it.
- No approve-all / always-allow: not a documented wait answer.
- Outreach cards (`send_*` tools) are recognised by tool name: the gateway's approval gate always asks before a send to anyone but you, but the wait payload carries no tier, so the amber "sends to someone else" pill is client-derived. Double Tap is off for sends and destructive calls.
- Entities: `GET /entities` lists only the entities the signed-in account may visit (the picker shows the entity's state and birth date, "asleep · born 6 Oct"). A chosen entity that the account cannot see falls back to the Assistant with a notice. The entity turn (`chat/open` → `turn`) was exercised against the mock and against the public gateway, where it returned the gateway's own provider error (see below).
- No risk tier: the real wait payload has none; `riskTier` exists only in mock data, so the Destructive pills and the Double Tap gate are demo-only.
- Reading: answers, run outputs, automation results and email drafts render markdown (headings, lists, quotes, code, tables, rules; bold, italic, code and links inline; bare URLs linked). `MarkdownBlock`, `SpeechText` and `WebPageText` live in the package and are tested.
- Read aloud: `POST /api/gateway/runs/{id}/voice/tts/stream` (the gateway's voice; an entity's text uses `POST /api/gateway/entities/{name}/voice/tts/stream`, its own voice). Each streamed chunk is a complete WAV; they play back to back through `AVAudioPlayer` with metering, and the orb's size, glow and ring follow the measured level. Verified on the watch: playback through the built-in speaker, first chunk about 5 s after the request, peak levels 0.76–0.81. Reading starts once per screen, continues with the wrist down and stops on Back.
- Links: every web link opens the Link screen. The watch fetches the page itself and shows its title and readable text with Read aloud, publishes the URL for Handoff (Safari on the iPhone offers it), and keeps "Open in the watch browser". The system web view answered "URL failed to load" for every page tried from the app on watchOS 27.0.1, which is why the page is read in the app.
- No SSE: the ledger is polled (2 s on Run detail, 1 s while an Ask is thinking), not streamed.
- Ask by voice: tap the orb to record (16 kHz mono WAV, metered, `NSMicrophoneUsageDescription`), tap again or stop speaking for 3 s to send (nothing heard in 5 s: it stops); the WAV goes to `POST /api/gateway/attachments/upload` (multipart, `session_id`) and `POST /api/gateway/runs/{session owner}/audio/transcribe`. Verified in the simulator against gateway.abstractframework.ai with the Mac's voice: "Tell me in two sentences why the sky is blue." transcribed word for word (faster-whisper base, about 10 s), answered and spoken. On the watch the first tap asks for the microphone; that path was not driven on the device (it needs a tap on Allow).
- Answers while away: each Assistant Ask hands `GET /runs/{id}/ledger/stream` to a background URLSession (`ai.abstractframework.assistant.answers`); the gateway closes it when the run ends and watchOS wakes the app (`.backgroundTask(.urlSession)`), which posts the answer as a notification (actions: open, Listen). Verified on the watch: the stream closed in the background and the post was attempted; it was refused because notifications were not yet allowed (the app asks once, after the first answer). Not posted for the answer on screen while the app is active.
- Settings: Refresh now, Sign out and the Account row are live; Voice, Haptics and Double Tap rows are static.
- Public gateway, 2026-10-17: an Ask from the watch to the Assistant completes (`--test-ask "<prompt>"` sends one prompt from the Ask screen at launch, for a device check without typing). The entity Pollux still answers with its provider's refusal (`HTTP 401 … Missing or invalid AIRelays bearer token`): Pollux follows the gateway default (`endpoint:airelays`), but the entity chat host resolves that profile through AbstractCore's process-wide config, loaded when the gateway started, while runs read the profile fresh. A gateway restart reloads it.
- A watch lying on a desk sleeps its screen within seconds and watchOS suspends the app: an Ask keeps polling once the wrist is raised, and the answer appears then.

## App Store packaging

A watch-only app reaches the App Store inside an empty iOS container: target `AbstractAssistant`
(`application.watchapp2-container`, bundle `ai.abstractframework.assistant`) embeds
`AbstractAssistantWatch` (`ai.abstractframework.assistant.watch`, `SKIP_INSTALL: YES` so the archive
holds one app, otherwise Xcode sees a "generic archive" with no distribution method). Versions come
from `MARKETING_VERSION` / `CURRENT_PROJECT_VERSION` in `project.yml` (bump the build number for
every upload); `ITSAppUsesNonExemptEncryption: false`; `Resources/PrivacyInfo.xcprivacy` declares
UserDefaults (CA92.1), no tracking, no developer-collected data.

```sh
scripts/testflight.sh --no-upload   # archive only (Release, generic iOS), prints version (build)
```

Releases (TestFlight, App Store) are made by the maintainers through the approved CI release.

## Layout

```
project.yml                          XcodeGen spec (app target AbstractAssistantWatch, depends on the local package)
Packages/AbstractGatewayClient/      Models, GatewayClient + LiveGatewayClient, MockGatewayClient, tests (swift test)
Sources/App/                         SwiftUI: Home, Approvals, Ask, Runs, Automations, Settings, Shared
scripts/build.sh                     simulator build + screenshot pipeline
scripts/run-live.sh                  simulator, live mode against a private env file
scripts/deploy-watch.sh              signed device build, install, launch (provisioned by launch args), screenshot
scripts/testflight.sh                archive the App Store carrier and upload to TestFlight (internal)
Container/Info.plist                 the empty iOS container's Info.plist (generated)
Resources/PrivacyInfo.xcprivacy      privacy manifest
docs/pairing.md                      pairing a physical watch for development on watchOS 27
```
