# Developer preview validation

Checked on 17 October 2026.

Validation uses the demo and deterministic HTTP fixtures. No personal gateway credentials,
outgoing email or production automation were used. The phone owns all files under `phone/`;
the Watch project and the shared desktop client are outside this change.

## Automated evidence

From `phone/iphone/`:

```sh
swift test --package-path Packages/AssistantKit --scratch-path build/SwiftTests --jobs 1
python3 scripts/build.py --ui-test <your-own-iphone-simulator-id>
```

- **37 package tests passed:** 28 inherited gateway wire/authentication/format tests and
  nine phone state/transport tests. These cover safe gateway addresses, account-scoped
  session preferences, workflow choice, history restoration, stale account responses,
  expired credentials, stale approvals and avoiding alternate-agent retries.
- **Three signed native tests passed** on an isolated iPhone 17 Pro simulator running
  iOS 26.5: conversation/navigation, approval inspection/denial, and Keychain credential
  add/read/update/removal. Ad-hoc signing exercises the actual Keychain service.
- Xcode 27.1, Swift 6 language mode, strict concurrency, one build job, isolated DerivedData.
  Build results and XCTest attachments remain locally in ignored `build/`.

The three-test result is `build/UITests-1792243760503616000.xcresult`. Final UI polish
(block Markdown, busy composer and approval labels) followed that XCTest run. All final
app sources passed a native Swift 6 strict-concurrency typecheck and were compiled/linked
with one low-priority `swiftc` process against the previously built phone frameworks.
The separate ad-hoc-signed `build/IsolatedPreview/AbstractAssistantPhone.app` was installed
and inspected in the dedicated iPhone simulator. This avoided the shared Xcode build
service while the Watch's Xcode process was still open. The updated XCTest assertions
for settled navigation/composer visibility have not been rerun against this final polish;
the final screenshots supply manual evidence instead.

Subsequently, the final source also completed a native physical-device Xcode build
with automatic development signing. The signature was verified, the app was installed
on the connected iPhone 17 Pro Max (iOS 27.0.1), launched normally, and its running process
confirmed. This used one low-priority job and separate `build/DeviceDerivedData`; an idle
Watch simulator-test process was allowed, with monitoring to stop the phone build on new
Watch compilation. Installation and launch succeeded without modifying the Watch app.
This confirms device deployment, not live-gateway, microphone or playback behavior.

The UI test captures [Assistant](../design/screenshots/assistant.png),
[Inbox](../design/screenshots/inbox.png), [Automations](../design/screenshots/automations.png)
and [Approval](../design/screenshots/approval.png). The completed
[Conversation](../design/screenshots/conversation.png) is captured from the final signed
isolated preview; the [welcome screen](../design/screenshots/welcome.png) from the signed
Xcode build. The approval screenshot precedes the final argument-label polish.

## Independent review

- **Execution Mode:** implementation plus one independent adversarial reviewer, as requested.
- **Planned / Actual Reviewer Set:** one reviewer covering correctness, architecture fit,
  security and user experience.
- **Subagents Used:** `iphone_adversary`; read-only, no competing builds or Watch changes.
- **Fallback Reason / Contract Degradation:** none; the user requested one reviewer.
- **Observed Evidence:** source, transport/state tests, signed Keychain test, native UI
  interactions and simulator screenshots.
- **Findings addressed:** account workflow selection, stale account responses, restoring
  history before sending, authentication lockout, no insecure credential fallback, demo
  isolation, recording/transcription races, actionable errors, complete approval arguments
  and navigation/composer visibility.
- **Reviewer Verdicts:** conditional approval for the developer preview; simulator evidence
  is available, physical audio remains unverified. The final conversation capture closes
  the reviewer's navigation and composer findings.
- **Inference Or Unverified Claims / Missing Evidence:** live gateway integration, physical
  microphone/playback, VoiceOver, large Dynamic Type and private-network permission behavior.
- **Residual Risk:** provider-specific responses or device permission/audio routes may need
  adjustment during first device use. This preview has no push or background polling.
- **Final Verdict:** conditional approval for a developer preview; device and live-gateway
  validation remain necessary before daily use or distribution.

## Resource isolation

Builds use a dedicated iPhone simulator and never target the ambiguous `booted` destination.
The build helper skips an active Xcode build and stops only its own process if another
build starts. Watch compiler processes are also checked. GUI coordination still needs
care: this is a development courtesy, not a global Xcode scheduler.

[Build instructions](../BUILD.md) · [Architecture](architecture.md) · [iPhone overview](../README.md)
