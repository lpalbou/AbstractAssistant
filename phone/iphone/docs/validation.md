# Developer preview validation

Checked on 17 October 2026 for iPhone preview **0.2.0**.

The original preview is saved in commit `48260ba`. This iteration changes only the phone
subtree; the Watch project and shared desktop client remain outside its scope. The user
confirmed that their live gateway conversation works after the Gateway provider fix.
The new feature checks below use demo data and deterministic HTTP fixtures, without
production automation, outgoing messages or personal gateway credentials.

## Automated evidence

From `phone/iphone/`:

```sh
swift test --package-path Packages/AssistantKit --scratch-path build/SwiftTests --jobs 1
python3 scripts/build.py --ui-test <your-own-iphone-simulator-id>
```

- **45 package tests passed:** 28 inherited gateway wire/authentication/reading/model tests
  and 17 phone state, transport and feature tests. These cover workflow preference writes,
  account-scoped voice preferences, attachment upload/provenance and run input context,
  bounded artifact sizes and safe paths, history without automatic reading, stale account
  responses, authentication lockout, stale approvals and idempotent automation creation.
- **Eight native tests passed** on the dedicated iPhone 17 Pro simulator, iOS 26.5:
  three hosted tests for Keychain credentials and attachment lifecycle/local previews;
  five UI tests for conversation/navigation, approvals, voice/workflow settings,
  creating an automation and browsing returned files.
- A subsequent focused conversation test also passed with an explicit assertion for the
  returned-files link. The initial stronger read-aloud assertion exposed a test interaction
  mistake: iOS exposes both a labelled row and the trailing control as switches. Tapping
  the actual trailing switch passes the enabled-value assertion.
- The final focused settings/automation rerun passed **2/2**, including the switch value
  and the corrected full-width automation detail. The final speech path also uses the
  already-tested `SpeechText.plain` helper, as Watch does, before requesting TTS.
- Xcode 27.1, Swift 6 language mode, strict concurrency, one low-priority build job and
  isolated DerivedData. Test results and attachments remain in ignored `build/`.

The final **0.2.0 (2)** app completed a development-signed physical-device build; its
signature was verified, then it was installed and launched successfully on the connected
iPhone 17 Pro Max running iOS 27.0.1. This updated the existing app without uninstalling
it or removing its Keychain sign-in. Installation is evidence of deployment, rather than
physical audio or camera validation.

Evidence bundles:

- Full native suite: `build/UITests-1792254607224570000.xcresult` (8 passed).
- Conversation/files-link assertion: `build/UITests-1792254745161166000.xcresult`
  (conversation passed; settings test exposed the row-tap mistake above).
- Final settings/automation rerun: `build/UITests-1792254901589327000.xcresult`
  (2 passed).

The creation test still logs one SwiftUI runtime warning, “Invalid frame dimension
(negative or non-finite).” Its source is not identified. The screen fills its container,
creation/navigation complete, and screenshots show no remaining collapsed layout; this
warning remains a follow-up for native-device use. No explicit variable-size frame in
the creation screen supplies a negative or infinite value.

## Visual evidence

Settled native XCTest screenshots are checked in:

- [Assistant](../design/screenshots/assistant.png),
  [Conversation with persistent orb and returned files](../design/screenshots/conversation.png)
- [Voice settings, read aloud enabled](../design/screenshots/voice-settings.png),
  [Workflow selection](../design/screenshots/workflow-settings.png)
- [New automation](../design/screenshots/new-automation.png),
  [Created automation](../design/screenshots/created-automation.png)
- [Conversation files](../design/screenshots/conversation-files.png),
  [Inbox](../design/screenshots/inbox.png),
  [Automations](../design/screenshots/automations.png),
  [Approval](../design/screenshots/approval.png)

## Independent review

- **Execution Mode:** implementation plus one independent adversarial reviewer, as requested.
- **Planned / Actual Reviewer Set:** one reviewer covering correctness, architecture fit,
  security and user experience.
- **Subagents Used:** `iphone_adversary`; read-only, no competing builds or Watch changes.
- **Fallback Reason / Contract Degradation:** none; the user requested one reviewer.
- **Observed Evidence:** source, deterministic transport/state tests, signed native tests,
  UI interactions and screenshots.
- **Findings addressed:** account guards across async voice/workflow/media operations;
  preserving unsent drafts; preserving staged uploads across tab returns; bounded reads,
  streaming-download cancellation and safe local filenames; picker progress and origin;
  discoverable returned files; foreground-only automatic reading; truthful workflow scope;
  stable automation request IDs; full-width automation detail and plain-text TTS.
- **Reviewer Verdicts:** conditional approval for the developer preview, with no unresolved
  blocker in the reviewed changes. Focused native checks subsequently passed.
- **Inference Or Unverified Claims / Missing Evidence:** actual physical microphone level
  response, playback routes, camera photo/video capture, cloud-provider imports, live
  attachment/automation provider behavior, VoiceOver and large Dynamic Type.
- **Residual Risk:** permission/audio routes and provider-specific behavior need real-device
  exercise; the creation warning above remains unresolved. No push or background polling.
- **Final Verdict:** suitable for a developer preview with the stated validation limits.

## Resource isolation

Builds use a dedicated iPhone simulator and never target the ambiguous `booted` destination.
The helper skips another active Xcode build and stops only its own process if a new build
starts. An explicit PID exception can permit a known idle Watch test process while still
yielding to Watch compilation, activity or memory pressure. No Watch process is stopped.
XCTest diagnostic collection is disabled to avoid a long simulator-wide diagnostic pass;
ordinary results and screenshots remain available.

[Build instructions](../BUILD.md) · [Architecture](architecture.md) · [iPhone overview](../README.md)
