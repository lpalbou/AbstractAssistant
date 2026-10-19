# Building AbstractAssistant for Apple Watch

A standalone watchOS 26+ SwiftUI app (watch-only, no iPhone companion) and a Swift package,
`AbstractGatewayClient`, that talks to AbstractGateway. It runs in the simulator with built-in
sample data, or live against a gateway in the simulator or on a paired watch. For what the app
does, see [README.md](README.md); for how it is built inside, [docs/architecture.md](docs/architecture.md).

## Requirements

- Xcode 27.1 with the watchOS 26.5 simulator runtime, and XcodeGen (2.45 tested).
- Simulator builds and the package tests need no signing and no Apple account. A build for a
  physical watch signs with an Apple developer team (`DEVELOPMENT_TEAM` in `project.yml`).

## Build and run in the simulator

```sh
cd watch/apple
scripts/build.sh               # generate the project, test the package, build, install, screenshot every screen
scripts/build.sh --no-screens  # generate, test and build only
```

`scripts/build.sh` runs, in order:

```sh
xcodegen generate --spec project.yml
(cd Packages/AbstractGatewayClient && swift test)
xcodebuild -project AbstractAssistantWatch.xcodeproj -scheme AbstractAssistantWatch \
  -destination 'platform=watchOS Simulator,id=<Apple Watch Series 11 (46mm)>' \
  -configuration Debug -derivedDataPath build/DerivedData build CODE_SIGNING_ALLOWED=NO
xcrun simctl install <simulator> build/DerivedData/Build/Products/Debug-watchsimulator/AbstractAssistantWatch.app
xcrun simctl launch <simulator> ai.abstractframework.assistant.watch --mock --screen <name>
xcrun simctl io <simulator> screenshot screenshots/<name>.png
```

Choose another simulator with `SIM="Apple Watch ..." scripts/build.sh`. The Xcode project is
generated from `project.yml` and is not committed.

## Tests

- **Package tests**: `swift test --package-path Packages/AbstractGatewayClient` (models decoded
  from the gateway's real shapes, sign-in, markdown and speech text, automation edits).
- **UI tests**: the `AbstractAssistantWatchUITests` scheme drives the app in the simulator where a
  real tap matters (for example, editing an automation's task starts from its current text).
  Screenshots of each step are written to the folder named by `TEST_RUNNER_SHOTS_DIR`.

```sh
TEST_RUNNER_SHOTS_DIR=/tmp/shots xcodebuild test -project AbstractAssistantWatch.xcodeproj \
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
| `--screen <name>` | opens a screen at launch: `home` `signin` `approval` `approval-ask` `email` `draft` `askuser` `waits` `ask` `ask-entity` `picker` `listening` `thinking` `answer` `sessions` `session` `automations` `automation` `automation-new` `automation-edit` `occurrence` `settings` `orbstyle` `about` `read` `link` `tools` `tools:<group>` `session-search` `session-search-media` |
| `--gateway <url> --token <token> [--user <id>]` | signs in with that gateway and token and keeps the sign-in, so one launch provisions a simulator or a watch |
| `--forget-gateway` | forgets the saved sign-in (the sign-in screen shows) |
| `--orb-design <letter>` | chooses the orb style (R Lotus, S Crystal, U Eclipse, V Synapse, W Drop, G Face, I Imprint, J Hologram, K Eye, L Lens, M Dome, N Valet, O Retro, P Deco, Q Rover, H Ocean); `--ask-orb` asks the first-launch question again |
| `--no-notification-prompt` | never shows the one-time notification question (screenshot runs) |

Debug builds also accept test hooks that answer, ask or navigate without a tap: `--test-identify`
/ `--test-secret` (sign-in), `--test-approve once|all`, `--test-action allow-first|deny-first`,
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
listing (`ai.abstractframework.assistant`) receives the real iPhone app with the independent
Watch app (`ai.abstractframework.assistant.watch`) embedded. Both use one version/build and pass
checks before the required human `app-store` approval. The standalone Watch workflow validates
developer builds and has no upload job.

See [Apple testing and distribution](../../phone/iphone/docs/distribution.md) for the release
entrypoint, signing setup, TestFlight and manual same-build App Store promotion. Local Watch
projects and developer installs retain their standalone configuration. The legacy
`scripts/testflight.sh --no-upload` can inspect a watch-only archive; use the combined workflow
for Store delivery.

## Layout

```
project.yml                     XcodeGen spec: the watch app, the UI tests, the App Store container
Packages/AbstractGatewayClient/ models, LiveGatewayClient, MockGatewayClient, sign-in, markdown; tests
Sources/App/                    SwiftUI: Home, Ask, Approvals, Runs (sessions), Automations, Settings, Shared
UITests/                        UI tests (own scheme)
Resources/                      Info.plist, assets, privacy manifest, the framework identity file (About)
Container/Info.plist            the empty iOS container's Info.plist
scripts/                        build.sh, run-live.sh, deploy-watch.sh, testflight.sh
design/                         mockups, prototype, orb animations, icon
docs/                           design, architecture, pairing
```
