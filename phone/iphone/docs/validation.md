# Developer preview validation

Checked on 17 October 2026. Current layout follow-up: **0.3.1 (4)**.

## 0.3.1 compact composer follow-up

The empty, unfocused text panel now uses half its previous width. The +, field and orb
align to the actual orb center, with its caption below. The repeated idle instruction
line is removed; active capture/countdown cancellation controls remain available.
Keyboard focus still expands the field, and staged attachments or a nonempty draft keep
the regular composer width.

Three focused native UI tests passed in
`build/UITests-1792265056209102000.xcresult`, with no runtime warnings: conversation/navigation,
keyboard expansion/restoration and hold/release/cancel/automatic voice send. The tightened
keyboard test checks the empty field's compact width, all three control centers within
3 points, absence of the idle footer, and the expanded keyboard layout. Updated Assistant,
Conversation, Keyboard, Compact and Countdown screenshots below come from this run.
The same independent adversarial reviewer inspected these screenshots and the result:
**Approved** for this small layout follow-up, with no new blocker. The existing physical
audio/accessibility limitations remain as recorded below.

The final 0.3.1 (4) device build was signature-verified, installed and launched on the
connected iPhone over the previous app, preserving its sign-in and data.

## 0.3.0 voice/composer baseline

The baseline results below cover preview **0.3.0 (3)**; the 0.3.1 follow-up changes layout,
copy and version metadata, leaving the voice/network policy and package code intact.

This iteration changes only the phone subtree. Watch and desktop sources are outside its
scope. Checks use deterministic HTTP fixtures and demo data, without production automation,
outgoing messages or personal gateway credentials. The user previously confirmed that
chat works against their gateway after the Gateway provider fix.

## Automated evidence

From `phone/iphone/`:

```sh
swift test --package-path Packages/AssistantKit --scratch-path build/SwiftTests --jobs 1
python3 scripts/build.py --ui-test <your-own-iphone-simulator-id>
```

**51 package tests passed:** 28 inherited gateway wire/authentication/reading/model tests
and 23 phone state/transport/feature tests. New tests cover the local capture policy:
holding never sends, release starts a fresh three-second grace, touching during grace
cancels, a late permission grant cannot revive capture, one handoff is claimed at most
once, and reaching the recording limit still requires an actual release. Envelope tests
check quiet/loud energy, decay and finite bounds. Existing tests cover workflow/voice
preferences, attachment provenance, safe paths/sizes, stale account responses, history,
authentication lockout and stable automation request IDs.

**15 native tests passed** on the dedicated iPhone 17 Pro simulator, iOS 26.5:

- Eight hosted tests: Keychain, attachment lifecycle/local previews and five voice tests.
  Voice tests inject a recorder and monotonic clock but use the real LiveGatewayClient
  with an intercepted URLSession. They verify **zero gateway requests** before grace and
  after cancellation, exactly one upload plus one STT request after an uncanceled grace,
  no microphone startup after permission was released, and no send during an interruption
  or a held recording limit.
- Seven UI tests: conversation/navigation, approvals, voice/workflow settings, automation
  creation, returned files, keyboard expansion/restoration and hold/release/cancel/autosend.
  The voice interaction uses an explicitly enabled Debug demo fixture. Its second touch
  begins during grace and lifts after the old deadline, proving cancellation happens on
  touch-down. A separate voice turn sends automatically while its typed draft survives.
  Keyboard assertions verify the orb hides, input expands, attachments remain available,
  and Done/Send are both tappable with nonoverlapping frames.

The actual **AVAudioPlayer WAV playback** test then passed a stricter focused rerun. It
checks variation inside playback rather than comparing startup silence with a constant
playing indicator. The recorded interior envelope ranged from **0.5185 to 0.9997** (span
0.4812). The [110-sample trace](../design/validation/wav-playback-energy.csv) contains
measured levels in sample order, sampled nominally every 30 ms. Pause and Stop also drive
the meter back to zero. This is actual playback metering; microphone-controller tests use
injected dB values and do not substitute for physical microphone validation.

Evidence bundles in ignored `build/`:

- `UITests-1792264429532309000.xcresult`: full suite, **15 passed**.
- `UITests-1792264573330615000.xcresult`: strengthened WAV meter test, **1 passed**, with
  its raw energy attachment and no runtime warnings.
- `UITests-1792264356643500000.xcresult`: focused voice/settings tests, **7 passed**.

The native tests caught and fixed an integration regression: storing a SwiftUI view method
at onAppear retained an outdated scenePhase and canceled otherwise valid voice handoffs.
The current implementation observes the ready phase from the current body. Visual review
also caught a floating keyboard Done button overlapping Send; Done now has a separate
composer row. The final full suite verifies both fixes. Final animation polish preserves
angular phase across voice-state changes, reduces idle rendering, respects Reduce Motion,
initializes the countdown ring immediately and dims disabled text Send. The physical-device
build compiles this final source with Swift 6 strict concurrency.

The final development-signed **0.3.0 (3)** app was signature-verified and installed over
the existing application on the connected iPhone 17 Pro Max running iOS 27.0.1. The app
was not uninstalled and its Keychain sign-in was retained. Installation confirms device
deployment, rather than physical audio, microphone or camera validation.

One existing SwiftUI warning remains during automation creation: “Invalid frame dimension
(negative or non-finite).” The creation/navigation test passes and its screen fills the
container. The warning's source remains unidentified. Conversation and keyboard warning
instances seen before relocating Done no longer occur in the final full suite.

## Visual evidence

Settled native XCTest screenshots are checked in:

- [Compact composer](../design/screenshots/compact-composer.png)
- [Expanded keyboard composer with separate Done and Send](../design/screenshots/keyboard-composer.png)
- [Voice countdown and preserved typed draft](../design/screenshots/voice-countdown.png)
- [Assistant](../design/screenshots/assistant.png),
  [Conversation](../design/screenshots/conversation.png),
  [Voice settings](../design/screenshots/voice-settings.png),
  [Workflow](../design/screenshots/workflow-settings.png)
- [New automation](../design/screenshots/new-automation.png),
  [Created automation](../design/screenshots/created-automation.png),
  [Conversation files](../design/screenshots/conversation-files.png),
  [Inbox](../design/screenshots/inbox.png),
  [Automations](../design/screenshots/automations.png),
  [Approval](../design/screenshots/approval.png)

The current composer captures come from the 0.3.1 focused run. Other feature captures
remain from the 0.3.0 baseline; their functional layouts are unchanged.

## Independent review

- **Execution Mode:** implementation plus one independent adversarial reviewer, as requested.
- **Planned / Actual Reviewer Set:** one reviewer covering correctness, architecture fit,
  security/privacy, operations and user experience.
- **Subagents Used:** `iphone_adversary`, read-only; no competing builds or Watch changes.
- **Fallback Reason / Contract Degradation:** none; one reviewer was explicitly requested.
- **Observed Evidence:** source, local state-policy tests, real transport spy tests, native
  audio playback tests, native UI interaction results, waveform trace and screenshots.
- **Findings addressed:** holding owns capture; a real release starts grace; touch-down
  cancels synchronously; stale permission/scene callbacks cannot send; draft/attachments
  survive canceled voice; interruption/navigation/keyboard cancel pending capture; clear
  automatic-send wording; stronger signal response; Done/Send overlap and phase jumps.
- **Reviewer Verdicts:** conditional approval for the developer preview, no unresolved
  blocker in the reviewed voice/composer changes. Final screenshots and 15/15 plus the
  stricter WAV results were independently inspected.
- **Inference Or Unverified Claims / Missing Evidence:** physical microphone sensitivity,
  actual hardware speaker/headphone/Bluetooth routes and calls, VoiceOver, large Dynamic
  Type, camera/cloud imports and live gateway provider variability.
- **Residual Risk:** physical audio/permission routes need hands-on device exercise. The
  preexisting automation warning remains a follow-up. No push or background polling.
- **Final Verdict:** suitable for a developer preview with these validation limits.

## Resource isolation

Builds use a dedicated iPhone simulator, separate DerivedData and one low-priority job.
They never target `booted`. The helper yields to other builds and stops only its own
process. A specific known-idle Watch test PID was temporarily allowed; Watch compilation,
activity or memory pressure would stop the phone build. The Watch process subsequently
finished independently. No Watch process, simulator or source was modified. XCTest retains
results and screenshots while disabling lengthy simulator-wide diagnostic collection.

[Build instructions](../BUILD.md) · [Architecture](architecture.md) · [iPhone overview](../README.md)
