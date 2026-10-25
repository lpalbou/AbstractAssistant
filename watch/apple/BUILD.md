# Building AbstractAssistant for Apple Watch

A watchOS 26+ SwiftUI app, the companion of the AbstractAssistant iPhone app and independent of
it (it signs in and runs without the iPhone), and a Swift package, `AbstractGatewayClient`, that
talks to AbstractGateway. One XcodeGen spec builds both apps:
[`../../phone/iphone/project.yml`](../../phone/iphone/BUILD.md) (`AbstractAssistant.xcodeproj`),
with the watch targets `AbstractAssistantWatch` (`ai.abstractframework.assistant.watchkitapp`),
`AbstractAssistantComplication` (`….watchkitapp.orbclock`), `AbstractAssistantWatchNotifications`
(`….watchkitapp.notifications`) and `AbstractAssistantWatchUITests`. The watch's gateway client is
compiled there as a static framework, `WatchGatewayClient` (module `AbstractGatewayClient`): the
iPhone's own client package exports a module of the same name. It runs in the simulator with built-in
sample data, or live against a gateway in the simulator or on a paired watch. For what the app
does, see [README.md](README.md); for how it is built inside, [docs/architecture.md](docs/architecture.md).

## Requirements

- Xcode 27.1 with the watchOS 26.5 simulator runtime, and XcodeGen (2.45 tested).
- Simulator builds and the package tests need no signing and no Apple account. A build for a
  physical watch signs with an Apple developer team (`DEVELOPMENT_TEAM` in
  `../../phone/iphone/project.yml`).

## Build and run in the simulator

```sh
cd watch/apple
scripts/build.sh               # generate the project, test the package, build, install, screenshot every screen
scripts/build.sh --no-screens  # generate, test and build only
```

`scripts/build.sh` runs, in order:

```sh
xcodegen generate --spec ../../phone/iphone/project.yml
(cd Packages/AbstractGatewayClient && swift test)
(cd ../../phone/iphone/Packages/AssistantPush && swift test)
xcodebuild -project ../../phone/iphone/AbstractAssistant.xcodeproj -scheme AbstractAssistantWatch \
  -destination 'platform=watchOS Simulator,id=<Apple Watch Series 11 (46mm)>' \
  -configuration Debug -derivedDataPath build/DerivedData build CODE_SIGNING_ALLOWED=NO
xcrun simctl install <simulator> build/DerivedData/Build/Products/Debug-watchsimulator/AbstractAssistantWatch.app
xcrun simctl launch <simulator> ai.abstractframework.assistant.watchkitapp --mock --screen <name>
xcrun simctl io <simulator> screenshot screenshots/<name>.png
```

Choose another simulator with `SIM="Apple Watch ..." scripts/build.sh`. The Xcode project is
generated from `../../phone/iphone/project.yml` and is not committed.

## Tests

`scripts/test-watch.sh light` runs the package tests and the tests of the shared pages (the orb
page, navigation, an automation, tools; about 5 minutes): after each change, adding the classes of
the area changed (`scripts/test-watch.sh light ShareUITests`). `scripts/test-watch.sh full` runs
every test but the live ones on three simulator clones in parallel (about 10 minutes): once, before
a commit or a deploy. `WATCH_SIM` picks the simulator. The script grants the simulator's
microphone to `ai.abstractframework.assistant.watchkitapp` first: the voice tests listen, and a
permission question would stop them.

- **Package tests**: `swift test --package-path Packages/AbstractGatewayClient` (models decoded
  from the gateway's real shapes, sign-in, markdown and speech text, automation edits).
- **UI tests**: the `AbstractAssistantWatchUITests` scheme drives the app in the simulator where a
  real tap matters (for example, editing an automation's task starts from its current text).
  Screenshots of each step are written to the folder named by `TEST_RUNNER_SHOTS_DIR`.

```sh
TEST_RUNNER_SHOTS_DIR=/tmp/shots xcodebuild test -project ../../phone/iphone/AbstractAssistant.xcodeproj \
  -scheme AbstractAssistantWatchUITests -destination 'platform=watchOS Simulator,id=<simulator>' \
  -derivedDataPath build/DerivedData CODE_SIGNING_ALLOWED=NO
```

The same tests run on a paired watch (`-destination 'platform=watchOS,id=<watch UDID>'
-allowProvisioningUpdates`), which matters for taps near the top bar. With `TEST_RUNNER_GW_URL`
and `TEST_RUNNER_GW_TOKEN`, a test reads the workflow list from a real gateway (it creates
nothing). The app's own scheme, CI and the release archive do not build the UI tests.

## Launch arguments

| Argument | Effect |
|---|---|
| `--mock` | sample data instead of a gateway (screenshots, previews) |
| `--screen <name>` | opens a screen at launch: `home` `signin` `approval` `approval-ask` `email` `draft` `askuser` `waits` `ask` `ask-entity` `picker` `listening` `thinking` `answer` `sessions` `session` `automations` `automation` `automation-info` `automation-new` `automation-edit` `face` (debug: the Assistant complication on each slot) `settings` `connection` `orbstyle` `about` `read` `link` `tools` `tools:<group>` `session-search` `session-search-media` |
| `--gateway <url> --token <token> [--user <id>]` | signs in with that gateway and token and keeps the sign-in, so one launch provisions a simulator or a watch |
| `--forget-gateway` | forgets the saved sign-in (the sign-in screen shows) |
| `--orb-design <letter>` | chooses the orb style (R Lotus, S Crystal, U Eclipse, V Synapse, W Drop, X Wave, G Face, I Imprint, J Hologram, K Eye, L Lens, M Dome, N Valet, O Retro, P Deco, Q Rover, H Ocean); `--ask-orb` asks the first-launch question again |
| `--no-notification-prompt` | never shows the one-time notification question (screenshot runs) |

Debug builds also accept test hooks that answer, ask or navigate without a tap: `--test-identify`
/ `--test-secret` (sign-in), `--reset-signins` (forgets the sign-in, the known gateways and the kept
sign-ins), `--test-known <url,url>` (gateways signed into, oldest first), `--test-kept <user,user>`, `--test-last-user <name>` (the user signed in last, what the field starts with)
(sign-ins kept on the default gateway), `--test-approve once|all`, `--test-action allow-first|deny-first`,
`--test-ask "<prompt>"`, `--test-read "<markdown>"`, `--test-open <url>`, `--test-listen`,
`--test-pause`, `--test-rewind` (with `--rewind-1`), `--open-automation <n>`, `--run-now`,
`--run-first`, `--scroll-bottom`, `--scroll-end-now`, `--home-bottom`, `--render-icon`,
`--render-orb-work` (the orb at work, frame by frame, into Documents), `--render-orb-scenes` (the scene styles, robots included, at rest, speaking, listening, thinking and working, into Documents), `--reset-tools` (tool and
workflow choices back to the gateway's), `--reset-seen` (every answer counts as new),
`--fresh-conversation` and `--test-session <id>` (open a conversation), `--slow-automations`
(sample automations answer 6 s late, as on a public gateway). Release builds ignore them.

## Live in the simulator

`scripts/run-live.sh [screen]` launches the installed simulator app against the gateway named in a
private env file (`GW_URL`, `GW_WATCH_TOKEN`; set its path with `GW_ENV=`), waits `WAIT` seconds and
writes `screenshots/live/<screen>.png`.

## On a paired watch

[docs/pairing.md](docs/pairing.md) pairs a physical watch for development. Then:

```sh
scripts/deploy-watch.sh --env <file with GW_URL and GW_TOKEN>   # signed build, install, launch signed in
scripts/deploy-watch.sh --no-build --screen picker --shoot picker  # install the last build, open a screen, screenshot
scripts/deploy-watch.sh --no-build --forget                       # clear the sign-in on the watch
```

The device id comes from `xcrun devicectl list devices` (`WATCH_DEVICE`). Give the watch its own
gateway account; an admin token on a watch carries admin rights to every approval.

## App Store packaging

Store delivery uses **Actions → Apple app (iPhone + Watch)**. The existing AbstractAssistant
listing (`ai.abstractframework.assistant`) receives the iPhone app with the independent
Watch app (`ai.abstractframework.assistant.watchkitapp`) embedded, from one project. Both use one version/build and pass
checks before the required human `app-store` approval. The standalone Watch workflow validates
developer builds and has no upload job.

See [Apple testing and distribution](../../phone/iphone/docs/distribution.md) for the release
entrypoint, signing setup, TestFlight and manual same-build App Store promotion.
`scripts/testflight.sh --no-upload` archives the signed iPhone app with the watch app inside, for
inspection; use the combined workflow for Store delivery.

## Layout

```
../../phone/iphone/project.yml  the one XcodeGen spec (iPhone app, watch app, complication, extensions, UI tests)
../../phone/iphone/Packages/AssistantPush/  sealed sign-in, push registration and rendering, iPhone handoff; tests
../../phone/iphone/NotificationService/     the notification service extension (one source, iPhone and watch)
Packages/AbstractGatewayClient/ models, LiveGatewayClient, MockGatewayClient, sign-in, markdown; tests
Sources/App/                    SwiftUI: Home, Ask, Approvals, Runs (sessions), Automations, Settings, Shared
UITests/                        UI tests (own scheme)
Resources/                      Info.plist, entitlements, assets, privacy manifest, the framework identity file (About)
Localization/en.lproj/          the push strings (push.<kind>.title/body), shared with the extension
scripts/                        build.sh, run-live.sh, deploy-watch.sh, testflight.sh
design/                         mockups, prototype, orb animations, icon
docs/                           design, architecture, pairing
```
