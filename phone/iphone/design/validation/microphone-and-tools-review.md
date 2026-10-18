# Microphone and session tools — 0.6.2 (10)

## Changes

Listening has its own adaptive display envelope, using recent microphone power rather
than the absolute-amplitude playback scale. A stable noise window can update the visual
baseline independently of raw VAD. Listening level also moves the ribbon phase; active
voice frames request up to 60 Hz with 35 ms level interpolation. Playback keeps its existing
geometry and soft-knee scale. The raw silence detector, three observed quiet seconds,
local cancellation and upload boundary remain unchanged.

Tools are grouped by the gateway's declared toolset. Categories start collapsed and search
reveals matching category/name/description rows. Each available tool has Off, Auto and
Approve; risk labels and disabled reasons come from the inventory. Disabled rows stay Off.
Defaults/drafts remain scoped to account, responder and session, and require Save.
Entity discovery metadata enriches display categories only, preserving the entity's own
availability and defaults. Undeclared categories remain Other.

## Validation

88 package tests pass: 60 phone state/feature tests and 28 client/model tests. They cover
quiet microphone levels, stationary noise using the real raw detector, per-syllable
changes, metadata decoding, category search and entity permission preservation.

19 native tests pass (16 hosted and three UI) with zero runtime warnings on the final
source: `build/UITests-1792292035320140000.xcresult`. The UI checks cover Settings entry,
category disclosure/search, host-disabled tools, filtered Save, per-conversation persistence,
draft preservation across inheritance toggles, and new-conversation defaults. Hosted checks
exercise microphone meter wiring and unchanged send timing, alongside actual WAV playback.
The earlier voice cancel/send and Stop-square UI checks also passed in the first targeted run.

The initial targeted run caught Save disappearing during active search. The production
search toolbar keeps both actions reachable. Its Close action is explicitly identified as
Close tools for accessibility, distinct from the native search-dismiss action. Runs yielded
whenever another Xcode build started, preserving Watch priority.

Two adversarial reviewers inspected the source. The independent UX reviewer also inspected
actual collapsed, expanded and disabled/search renders. The microphone reviewer implemented
an isolated change; the parent reviewed its source and tests. The final [category overview](../screenshots/tool-categories.png),
[expanded tools](../screenshots/tool-category-expanded.png),
[filtered Save](../screenshots/tool-search-save.png) and
[disabled tool](../screenshots/tool-gateway-disabled.png) were inspected directly.
The controller fixture produced display levels 0.0000 (room), 0.9528 (quiet speech) and
0.0000073 (pause): [trace](quiet-microphone-fixture.csv),
[room render](../screenshots/microphone-room.png),
[speech render](../screenshots/microphone-quiet-speech.png).

## Physical boundary

Recorder fixtures test actual VoiceController meter wiring using injected -70 dBFS room
and -48 dBFS speech, and attach rendered orbs from those measured fixture levels. These
are not physical microphone measurements. Sensitivity still needs hands-on iPhone feedback.
A perfectly sustained tone may soften after the stationary window; this affects display
only and cannot change recording/send decisions.


## UX review record

- **Execution mode:** source review, native interaction tests and actual renders.
- **Planned reviewer set / actual reviewer set:** two user-requested adversarial agents;
  one UX reviewer and one technical reviewer, with parent review of delegated changes.
- **Subagents used:** iphone_adversary and iphone_behavior_adversary.
- **Fallback reason / contract degradation:** none; no explicit three-persona skill invocation.
- **Observed evidence:** linked screens, controller traces, 88 package tests and 19 final native tests.
- **Inference or unverified claims:** physical microphone sensitivity and manual VoiceOver use.
- **Blocking UX issues:** none remaining in the inspected scope.
- **Terminology and meaning risks:** modes explain Off, Auto and Approve at the point of choice.
- **Critical distinctions:** gateway inheritance, explicit session choices and gateway-disabled tools.
- **State coverage:** entry, edits, search, no matches, disabled permission state, saving and
  re-entry inspected; transport error and keyboard-only navigation not visually exercised.
- **High-value improvements:** quiet-input normalization, category search and reachable Save.
- **Persona verdicts:** independent UX reviewer found no blocker, conditional only on the
  final native pass; technical review verified visual adaptation stays independent of VAD.
- **Workflow recommendations:** More options → Tools; disable inheritance, choose modes and Save.
- **Accessibility and visual notes:** labelled disclosure and mode controls, explicit Close tools,
  adaptive row layout, preserved Reduce Motion behavior. Portrait renders inspected.
- **Validation status:** final automated gate passed; physical microphone feel needs user feedback.
- **Final verdict:** approved for the inspected native workflow and visual scope.


## Device delivery

The signed 0.6.2 (10) app passes strict code-signature verification. CoreDevice refused
installation with POSIX error 28, No space left on device. A subsequent installed-app
query confirmed 0.6.1 (9) remains installed. The new binary is ready in
`build/DeviceDerivedData/Build/Products/Debug-iphoneos/AbstractAssistantPhone.app`;
installation requires available iPhone storage. No existing app or user data was removed.
