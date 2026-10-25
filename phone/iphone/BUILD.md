# Build AbstractAssistant (iPhone and Apple Watch)

AbstractAssistant is one product: the iPhone app (`ai.abstractframework.assistant`) carries the
Apple Watch app (`ai.abstractframework.assistant.watchkitapp`) as its companion. One XcodeGen
spec, `project.yml` in this folder, builds both apps, the watch face complication and the two
notification service extensions; the watch sources stay in [`../../watch/apple`](../../watch/apple/BUILD.md).

Requirements: Xcode 27.1 (Swift 6.2 or later), iOS 26+ and watchOS 26+ SDKs/runtimes, and XcodeGen.
The package tests run on macOS 14+ without a simulator or signing account.

From `abstractassistant/phone/iphone/`:

```sh
swift test --package-path Packages/AssistantKit --scratch-path build/SwiftTests --jobs 1
swift test --package-path Packages/AssistantPush --scratch-path build/PushTests --jobs 1
python3 scripts/build.py
```

| Target | Bundle ID | What it is |
|---|---|---|
| AbstractAssistantPhone | `ai.abstractframework.assistant` | the iPhone app, the container (shown as AbstractAssistant) |
| AbstractAssistantPhoneNotifications | `ai.abstractframework.assistant.notifications` | iPhone notification service extension (push) |
| AbstractAssistantWatch | `ai.abstractframework.assistant.watchkitapp` | the watch app, an independent companion |
| AbstractAssistantComplication | `ai.abstractframework.assistant.watchkitapp.orbclock` | the watch face complication |
| AbstractAssistantWatchNotifications | `ai.abstractframework.assistant.watchkitapp.notifications` | watch notification service extension (push) |

All five share the app group `group.ai.abstractframework.assistant` and one version
(`MARKETING_VERSION` / `CURRENT_PROJECT_VERSION` in `project.yml`). The two apps carry the
`aps-environment` and Time Sensitive Notifications entitlements.

The build script generates `AbstractAssistant.xcodeproj`, builds with one job at lower
CPU priority and keeps DerivedData in `build/DerivedData`. It does not boot, reset, shut down
or change any simulator. If another command-line Xcode build starts, the script stops only
its own build and exits with status 75 so the other development takes priority.
The simulator app is signed locally with an ad-hoc identity so the app group (where the
sealed sign-in lives) works; this needs no developer account and does not sign a
physical-device build. The iPhone build compiles the watch app too (it is embedded).

Xcode’s GUI build service is shared: also check for other active builds before starting,
particularly while the Watch client is being developed. Do not launch both apps’ build
scripts together. A simulator is not required to compile the app.

## Open in Xcode

```sh
xcodegen generate --spec project.yml
open AbstractAssistant.xcodeproj
```

Select **AbstractAssistantPhone**, an iPhone simulator, then Run; **AbstractAssistantWatch**
runs the watch app on its own. The project signs automatically with team `K3R4D6HP2A`
(`DEVELOPMENT_TEAM` in `project.yml`); pass another team on the command line. The developer
build and the Store build share the bundle ID `ai.abstractframework.assistant` (the
earlier developer-only `ai.abstractframework.assistant.iphone` is retired: sign in again once).

For a connected physical iPhone, the guarded command-line build accepts your device and
development team IDs without saving either in the project:

```sh
python3 scripts/build.py --device <iphone-id> --team <development-team-id>
xcrun devicectl device install app --device <iphone-id> \
  build/DeviceDerivedData/Build/Products/Debug-iphoneos/AbstractAssistantPhone.app
xcrun devicectl device process launch --device <iphone-id> ai.abstractframework.assistant
```

This uses Xcode's automatic development provisioning and may register the five app
identifiers (with Push Notifications, Time Sensitive Notifications and the app group) and the
device with your developer account. It does not upload or distribute the app. iOS offers to
install the embedded watch app on the paired watch; `../../watch/apple/scripts/deploy-watch.sh`
installs and launches it on the watch directly.

The project is generated; change `project.yml`, not the generated project. The checked-in
app icon can be regenerated with `swift scripts/make-icon.swift`.

## Demo

Choose **Take a look around** on the welcome screen, or launch a Debug build with:

```sh
xcrun simctl launch <your-own-iphone-simulator-id> ai.abstractframework.assistant --demo
```

Use an explicit iPhone simulator ID. Do not use `booted`: another developer’s Watch
simulator may also be running.

Debug screenshot states: `--demo --screen conversation`, `--demo --screen inbox`,
`--demo --screen automations`, `--demo --screen settings`. Release builds ignore launch arguments; the visible demo
entry is still available without credentials.

## UI tests

The separate **AbstractAssistantPhoneUITests** scheme drives the demo and runs the hosted
tests (the sealed sign-in store among them). When resources are available, use the guarded script against your own
iPhone simulator with isolated DerivedData and one job:

```sh
python3 scripts/build.py --ui-test <your-own-iphone-simulator-id>
```

Use `--only-testing Target/Class/testMethod` to rerun an affected native test. Test runs
keep results and screenshots but disable the lengthy automatic simulator diagnostic pass.
The optional `--allow-idle-watch-test <pid>` permits only a specifically identified idle
Watch UI-test process (physical Watch or simulator); the helper still yields to Watch activity or compilation and memory
pressure. Omit it for normal builds.

## CI and App Store Connect

The [iPhone workflow](../../.github/workflows/iphone.yml) runs credential-free checks and builds
the same project. The apps now carry explicit entitlements (push, time-sensitive, app group),
so its unsigned-candidate step refuses by design until an archive-signing configuration exists. Manual upload requests on main require the full native suite
and approval of the protected **app-store** environment before signing/upload. See
[Testing and distribution](docs/distribution.md) for first-time setup, TestFlight delivery and
manual promotion of the same build to the public App Store.

## Opt-in live media verification

Use a development-signed iPhone with an existing gateway sign-in. The hosted test reads
its sealed sign-in in place; it never exports it. This starts real, potentially billed
provider generations on that account and uploads the reviewed orchestrator bundle if absent.

```sh
python3 scripts/build.py --live-media-test <iphone-id> --team <development-team-id> \
  --only-testing AbstractAssistantPhoneTests/LiveGatewayMediaTests/testDiscoverSavedGateway
python3 scripts/build.py --live-media-test <iphone-id> --team <development-team-id> \
  --only-testing AbstractAssistantPhoneTests/LiveGatewayMediaTests/testGenerateVoice
python3 scripts/build.py --live-media-test <iphone-id> --team <development-team-id> \
  --only-testing AbstractAssistantPhoneTests/LiveGatewayMediaTests/testGenerateImageAndEdit
```

Image verification generates an image, then edits it using the stored primary-image
reference. Voice verification is independent. Both download the authenticated artifacts,
decode them on the iPhone and check that references survive reloading. Reports contain
run/artifact IDs and byte counts under the app's `Documents/media-verification/`; no keys
or endpoint secrets are stored. The tests resume their own saved runs after interruption;
remove that test report before deliberately creating a new verification session.

Normal tests skip these network actions. After live testing, use the normal device build
and install commands above to replace the test host with the ordinary app.

Read-only live file verification (no generations or messages) uses the saved conversation:

```sh
python3 scripts/build.py --live-media-test <iphone-id> --team <development-team-id> \
  --only-testing AbstractAssistantPhoneTests/LiveGatewayMediaTests/testBrowseSavedConversationWorkspace
```

This regression expects the reported discussion-summary.md in that conversation. It browses
root/child workspaces, downloads/decodes the document, checks cleanup and records only
relative names, counts, run IDs and filtered provenance; document contents are not exported.

Store delivery generates a combined iPhone + Watch archive using the existing AbstractAssistant
listing (`ai.abstractframework.assistant`). Local developer identity/data are retained. See
[distribution](docs/distribution.md) for the shared release entrypoint and Store sandbox details.
