# Build the iPhone app

Requirements: Xcode 27.1 (Swift 6.2 or later), an iOS 26+ SDK/runtime, and XcodeGen.
The package tests run on macOS 14+ without a simulator or signing account.

From `abstractassistant/phone/iphone/`:

```sh
swift test --package-path Packages/AssistantKit --scratch-path build/SwiftTests --jobs 1
python3 scripts/build.py
```

The build script generates `AbstractAssistantPhone.xcodeproj`, builds with one job at lower
CPU priority and keeps DerivedData in `build/DerivedData`. It does not boot, reset, shut down
or change any simulator. If another command-line Xcode build starts, the script stops only
its own build and exits with status 75 so the other development takes priority.
The simulator app is signed locally with an ad-hoc identity so Keychain works; this needs
no developer account and does not sign a physical-device build.

Xcode’s GUI build service is shared: also check for other active builds before starting,
particularly while the Watch client is being developed. Do not launch both apps’ build
scripts together. A simulator is not required to compile the app.

## Open in Xcode

```sh
xcodegen generate --spec project.yml
open AbstractAssistantPhone.xcodeproj
```

Select **AbstractAssistantPhone**, an iPhone simulator, then Run. For a physical iPhone,
select your developer team for this target. The phone’s bundle ID is
`ai.abstractframework.assistant.iphone`, distinct from the Watch app and its App Store
carrier. No signing team is pinned in the project.

For a connected physical iPhone, the guarded command-line build accepts your device and
development team IDs without saving either in the project:

```sh
python3 scripts/build.py --device <iphone-id> --team <development-team-id>
xcrun devicectl device install app --device <iphone-id> \
  build/DeviceDerivedData/Build/Products/Debug-iphoneos/AbstractAssistantPhone.app
xcrun devicectl device process launch --device <iphone-id> ai.abstractframework.assistant.iphone
```

This uses Xcode's automatic development provisioning and may register the app identifier
and device with your existing developer account. It does not upload or distribute the app.

The project is generated; change `project.yml`, not the generated project. The checked-in
app icon can be regenerated with `swift scripts/make-icon.swift`.

## Demo

Choose **Take a look around** on the welcome screen, or launch a Debug build with:

```sh
xcrun simctl launch <your-own-iphone-simulator-id> ai.abstractframework.assistant.iphone --demo
```

Use an explicit iPhone simulator ID. Do not use `booted`: another developer’s Watch
simulator may also be running.

Debug screenshot states: `--demo --screen conversation`, `--demo --screen inbox`,
`--demo --screen automations`. Release builds ignore launch arguments; the visible demo
entry is still available without credentials.

## UI tests

The separate **AbstractAssistantPhoneUITests** scheme drives the demo and runs the hosted
Keychain test. When resources are available, use the guarded script against your own
iPhone simulator with isolated DerivedData and one job:

```sh
python3 scripts/build.py --ui-test <your-own-iphone-simulator-id>
```

Use `--only-testing Target/Class/testMethod` to rerun an affected native test. Test runs
keep results and screenshots but disable the lengthy automatic simulator diagnostic pass.
The optional `--allow-idle-watch-test <pid>` permits only a specifically identified idle
Watch UI-test process; the helper still yields to Watch activity or compilation and memory
pressure. Omit it for normal builds.

App Store distribution, signing and upload are not configured by this preview.
