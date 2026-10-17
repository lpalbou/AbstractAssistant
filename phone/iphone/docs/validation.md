# Developer preview validation

Checked on 17 October 2026 for iPhone preview **0.4.1 (6)**.

This correction restores separate floating attachment and keyboard buttons on the left and
the orb on the right. The keyboard button expands the editor and hides the orb. An outside
tap dismisses editing and restores the controls without losing the draft. There is no
shared dock, visible voice Cancel, countdown or Done button; only a small Listening label
appears above the active orb. The measured three-second silence and orb-tap cancellation
policy is unchanged. Changes stay inside `phone/`; Watch and desktop sources are outside
this change. Checks use demo data and deterministic HTTP fixtures without production
automations, outgoing messages or personal gateway credentials.

## Automated evidence

From `phone/iphone/`:

```sh
swift test --package-path Packages/AssistantKit --scratch-path build/SwiftTests --jobs 1
python3 scripts/build.py --ui-test <your-own-iphone-simulator-id>
```

**Six focused native UI tests passed on final 0.4.1 source**, on the dedicated iPhone 17
Pro simulator, iOS 26.5. Bundle: `build/UITests-1792268164015961000.xcresult`.

- Separate aligned + / keyboard / orb controls; no idle text field in accessibility.
- Keyboard activation expands input, hides the orb and preserves drafts. Caret taps retain
  editing; outside taps minimize it, restore controls and preserve the draft. Done is absent.
- Attachment menu and Send keep their first-tap action while dismissing editing.
- Keyboard and suggestion activation cancel pending local voice before hiding the orb.
- Orb tap starts listening; only Listening is shown. Touch-down cancels before commit even
  if the finger lifts after the old deadline. A later turn sends automatically after three
  measured quiet seconds, preserving the typed draft. Editing reopens after run completion.
- Conversation, response, file access and tab navigation remain available.

The initial run caught a minimized UIKit input remaining in accessibility; the editor is
now removed when minimized. The reviewer caught a voice-to-suggestion race, closed by
synchronous cancellation. Another test tapped the disabled keyboard button after partial
output but before the run completed; it now waits for the actual enabled/hittable state.

The unchanged voice/transport layer was validated in preview 0.4.0:

**55 package tests passed:** 28 gateway wire/authentication/reading/model tests and 27 phone
state/transport/feature tests. Silence-policy tests verify confirmed activity followed by
three quiet seconds, speech resuming at expiry, cancellation, initial quiet/brief impulses,
late permission grants, raw-power hysteresis, non-finite values, missed samples and isolated
speech samples across gaps. Existing tests cover workflow/voice preferences, attachment
provenance, safe paths/sizes, stale account responses, history, auth lockout and automation
request IDs.

**20 native tests passed** on the dedicated iPhone 17 Pro simulator, iOS 26.5:

- Twelve hosted tests: Keychain, attachment lifecycle/local previews and nine voice tests.
  Voice tests inject continuous raw microphone dB sequences and a monotonic clock while
  using the real LiveGatewayClient with an intercepted URLSession. They verify zero
  requests before the quiet window ends or after cancellation, exactly one upload plus one
  STT request on commit, resumed speech resetting silence, no-speech/noisy-limit discard,
  canceled/inactive permission completion, interruption and a duration-limit boundary.
- Eight UI tests: conversation/navigation and typed Send, approvals, voice/workflow settings,
  automations, returned files, keyboard/caret/outside-tap behavior, one-tap attachment-menu
  access while editing and tap/silence/cancel/automatic voice send. The previous preview
  kept the orb visible while typing; that behavior is superseded
  by the 0.4.1 correction. A tap on the text retains editing; an outside tap dismisses
  the keyboard and minimizes the preserved draft. Done is absent. A pending voice turn is
  canceled on touch-down even when the finger lifts after its previous deadline. The next
  turn automatically sends after fixture speech followed by silence, retaining the draft.

Native result bundle: `build/UITests-1792266261626476000.xcresult` (**20 passed**).
The Debug UI voice fixture is explicitly enabled and supplies local synthetic speech then
silence. It cannot be enabled against a live gateway or in a Release build.

The 0.4.0 native AVAudioPlayer test reads actual WAV power and checks variation inside playback,
then Pause/Stop decay. Its measured interior envelope ranges from **0.5192 to 0.9999**, span
0.4807. The [110-sample trace](../design/validation/wav-playback-energy.csv) records measured
levels in sample order at nominal 30-ms intervals. Microphone tests use injected raw power,
so they do not establish physical microphone sensitivity. SpeechActivity is an audio-energy
gate; room noise and very quiet speech can affect detection.

An additional focused interruption test checks that calling finish after interruption
returns nil and makes zero requests. It also removes an unused test-local warning without
changing application behavior: `build/UITests-1792266463273317000.xcresult` (**1 passed**).
Native code uses Swift 6 strict concurrency, one low-priority build job and separate
DerivedData.

One preexisting SwiftUI warning remains during automation creation: “Invalid frame dimension
(negative or non-finite).” Its source is unidentified; the creation/navigation test passes
and its screen fills its container. It is outside the voice/composer changes.

## Visual evidence

Native XCTest screenshots (composer images updated with the correction):

- [Separate floating controls](../design/screenshots/compact-composer.png)
- [Expanded editor with hidden orb and no Done](../design/screenshots/keyboard-composer.png)
- [Preserved minimized draft](../design/screenshots/minimized-draft.png)
- [Discreet Listening state](../design/screenshots/voice-listening.png)
- [Assistant](../design/screenshots/assistant.png), [Conversation](../design/screenshots/conversation.png)
- [Voice settings](../design/screenshots/voice-settings.png), [Workflow](../design/screenshots/workflow-settings.png)
- [New automation](../design/screenshots/new-automation.png), [Created automation](../design/screenshots/created-automation.png)
- [Files](../design/screenshots/conversation-files.png), [Inbox](../design/screenshots/inbox.png),
  [Automations](../design/screenshots/automations.png), [Approval](../design/screenshots/approval.png)

## Independent review

- **Execution Mode:** implementation plus one independent adversarial reviewer, as requested.
- **Planned / Actual Reviewer Set:** one reviewer covering correctness, architecture fit,
  security/privacy, operations and user experience.
- **Subagents Used:** `iphone_adversary`, read-only; no competing builds or Watch edits.
- **Fallback Reason / Contract Degradation:** none; one reviewer was requested.
- **Observed Evidence:** final source and six focused UI tests, earlier 55 package tests
  and 20 native tests, intercepted transport,
  real WAV metering, power trace and native screenshots. The prior always-visible-orb
  dock verdict is superseded. The reviewer inspected corrected floating, editor and
  Listening screenshots and identified the voice-to-suggestion cancellation race.
- **Findings addressed:** editing hides the orb; idle uses a keyboard icon; no shared
  panel or visible voice Cancel/countdown remains; typing cancels voice synchronously;
  minimized fields leave accessibility. Missing/invalid samples do not imply silence; speech resumes before
  expiry checks; disconnected impulses cannot confirm speech; the hard capture limit wins;
  capture requires current app-active state after permission; outside taps exclude text
  selection and preserve button actions.
- **Reviewer Verdicts:** approved for this developer-preview correction, no unresolved
  blocker. The reviewer independently confirmed all six final tests and the three final
  floating/editor/Listening screenshots.
- **Inference Or Unverified Claims / Missing Evidence:** physical microphone tuning, real
  speaker/headphone/Bluetooth routes and calls, VoiceOver/large Dynamic Type, camera/cloud
  imports and live provider behavior. The raw-energy gate is not semantic speech recognition.
- **Residual Risk:** room noise, quiet speech and device permission/audio routes need hands-on
  exercise. The automation warning remains a follow-up. No push or background polling.
- **Final Verdict:** suitable for a developer preview with the stated validation limits.

## Resource isolation

Builds use a dedicated iPhone simulator, separate DerivedData and one low-priority job,
never `booted`. The helper yields to other builds and stops only its own process. A specific
known-idle Watch test PID was permitted with monitoring for Watch compilation/activity or
memory pressure. No Watch process, simulator or source was modified. XCTest retains results
and screenshots while disabling lengthy simulator-wide diagnostic collection.

## Physical deployment

Preview **0.4.1 (6)** was built for the connected iPhone 17 Pro Max, signature-verified,
installed over the existing app and launched successfully with `devicectl` on 17 October
2026. Bundle ID: `ai.abstractframework.assistant.iphone`. The installation preserved app
data and Keychain; no uninstall or reset was performed. Installation and launch establish
deployment, while the physical microphone and audio-route checks above remain hands-on.

[Build instructions](../BUILD.md) · [Architecture](architecture.md) · [iPhone overview](../README.md)
