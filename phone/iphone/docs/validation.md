# Developer preview validation

This iteration preserves the committed 0.4.1 baseline (`e2c7025`) and improves the iPhone
app using the Watch voice/responder flows as a direct reference. Version **0.5.0 (7)**.
Changes are owned by `phone/`; Watch source and shared desktop files are untouched.

## What changed

- Voice selection immediately previews the selected voice. Speed choices 1×, 1.15×, 1.3×
  and 1.5× preview the current voice and apply to real playback. The separate Preview step
  and long explanatory text are removed. Speech recognition has a focused model chooser.
- Who answers is opened by the current chat title and chevron. It lists/searches accessible
  entities and Assistant, shows the current selection and offers New entity. Files/settings
  use one More menu, preventing the crowded toolbar from collapsing essential controls.
- Entity creation checks the name through the gateway, explains permanence before Create,
  opens a successfully created entity, and preserves partial/existing outcomes and warnings.
  It uses the ordinary authenticated-user endpoint, without inventing an admin-only gate.
- Automations/Inbox show useful content first. Empty Automations has one full-width padded
  action. Settings puts preferences first and collapses connection details. Chat keeps its
  established floating controls, typing expansion/hide-orb and outside-tap draft behavior.

## Package evidence

**61 tests passed:** 33 phone state/transport/feature tests and 28 inherited gateway tests.
New checks cover account-scoped speed persistence/invalid values, safe entity paths,
authenticated validation/create bodies, manifest parsing, partial warnings, duplicate
creation and readable quota errors. Existing tests cover local silence/cancellation,
permissions, attachments, account generations, workflows and authentication lockout.

```sh
swift test --package-path Packages/AssistantKit --scratch-path build/SwiftTests --jobs 1
python3 scripts/build.py --ui-test <dedicated-iphone-simulator-id>
```

Live gateway HTTP tests intercept URLSession and inspect actual requests. Native UI tests
use demo data; they send no production messages or automations and create no live entities.
The explicit Debug voice fixture supplies measured synthetic activity then silence, and
cannot activate against a live gateway or Release build.

## Native and visual evidence

**25 native tests passed** (13 hosted, 12 UI) on the dedicated iPhone 17 Pro simulator,
iOS 26.5: `build/UITests-1792273161919583000.xcresult`. They include actual AVAudioPlayer
speed/preview replacement and waveform metering, voice selection and speed auto-preview,
entity listing/selection/creation, empty automation CTA geometry, conversation, approvals,
files and the established composer/silence behavior. The final canonical entity-id and visual polish changes then passed **two focused UI
tests**, with no runtime warnings: `build/UITests-1792273463421121000.xcresult`. Entity
manifest tests also verify canonical routing IDs and readable display-name round trips.

Both parent and reviewers inspected the rendered native screens, including:

- [Voice](../design/screenshots/voice-settings.png), [Automatic preview](../design/screenshots/voice-choices.png), [Speed](../design/screenshots/speaking-speed.png), [Speech recognition](../design/screenshots/speech-recognition.png)
- [Empty Automations](../design/screenshots/empty-automations.png), [Automations](../design/screenshots/automations.png), [New automation](../design/screenshots/new-automation.png)
- [Who answers](../design/screenshots/entities.png), [New entity](../design/screenshots/new-entity.png), [Created entity](../design/screenshots/created-entity.png), [Selected entity](../design/screenshots/entity-conversation.png)
- [Assistant](../design/screenshots/assistant.png), [Expanded editor](../design/screenshots/keyboard-composer.png), [Inbox](../design/screenshots/inbox.png)

A preexisting SwiftUI runtime warning remains during automation creation: “Invalid frame
dimension (negative or non-finite).” The exact source is unidentified. The native creation
check passes and its inspected screens fill their container; the warning is recorded as
an unresolved follow-up, rather than claimed fixed by the layout correction.

The earlier [WAV energy trace](../design/validation/wav-playback-energy.csv) remains evidence
for the unchanged audio envelope (interior range 0.5192–0.9999). Silence detection uses raw
audio power rather than semantic recognition. Injected microphone tests do not establish
physical microphone sensitivity.

## Independent review

- **Execution Mode:** implementation plus two independent adversarial reviewers, as requested.
- **Planned / Actual Reviewer Set:** everyday usability, and technical/user behavior.
- **Subagents Used:** `iphone_adversary` and `iphone_behavior_adversary`; read-only, no builds.
- **Fallback Reason / Contract Degradation:** none; user requested exactly two reviewers.
- **Observed Evidence:** Watch and phone source, gateway route contracts, package tests;
  both native bundles and the final rendered voice/entity/automation/composer images.
- **Findings addressed:** explicit discovery/validation retry, search-empty feedback, readable
  entity names, account-scoped speed, stale preview cancellation, permanent creation,
  partial-warning handling, one empty-state CTA and discoverable responder navigation.
- **Critical distinctions:** local voice/speed preferences versus gateway defaults; entity
  own voice; a new chat view versus retained entity memory; permanent birth versus settings.
- **State coverage:** entry/happy/empty/keyboard states have native checks. Loading/error/
  quota/partial outcomes are covered by source or transport checks where noted; they are
  not automatically treated as visually inspected states.
- **Inference / Missing Evidence:** live provider preview and entity creation, physical
  microphone sensitivity, calls/Bluetooth routes, VoiceOver and large Dynamic Type remain
  hands-on. No uninspected state is claimed fully validated.
- **Residual Risk:** low/constant room noise and quiet speech can affect the local energy
  gate. Server permissions/defaults/quotas can refuse entity creation and remain authoritative.

- **Reviewer Verdicts:** everyday UX Approved for developer preview; technical/user behavior
  Conditional Approval pending physical deployment verification. Neither found an unresolved
  blocker in the reviewed implementation. The parent completed deployment verification below.
- **Final Verdict:** suitable for this developer preview with the stated live-provider,
  physical audio, accessibility and known automation-warning limits.

## Physical deployment

On 17 October 2026, preview **0.5.0 (7)** was built for the connected iPhone 17 Pro Max,
its code signature and version verified, installed over the existing app and launched with
`devicectl`. Bundle: `ai.abstractframework.assistant.iphone`. No app uninstall, data reset or
Keychain clearing was performed. Deployment proves installation and launch; live provider
preview and remote entity creation are not claimed tested by that action.

## Resource isolation

Builds use one low-priority job, separate phone DerivedData and a named iPhone simulator.
The Watch has priority. A Darwin truncated-process-column bug was repaired in the resource
monitor; assertions verify that the phone yields to another Xcode build, only the explicitly named idle
Watch test is excepted, and the phone's own process is excluded. The in-flight phone build
was stopped to make that repair; no Watch process or simulator was stopped. No global
Xcode/simulator reset was performed. Only phone build products were refreshed after an
incremental-module cache failed to recognize a new phone-owned package extension.

[Build](../BUILD.md) · [Architecture](architecture.md) · [iPhone overview](../README.md)
