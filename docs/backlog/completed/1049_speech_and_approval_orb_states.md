# 1049 — Speech-processing and approval orb states

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Completed
> Completed: 2026-10-19
> Priority: P1
> Labels: iphone, voice, observability, animation

## Current code reality

AssistantOrb morphs only between sphere and stop. VoicePresence ignores VoiceController.preparing
and transcribing for geometry. Approval waits leave the Stop control active, although the scoped
conversation wait already opens the complete decision sheet from RunActivityPanel. Orb touch
accessibility hints still assume automatic voice sending regardless of the new review default.

## Scope and expected outcome

Add smooth animated geodesic speech-wait geometry for STT/TTS preparation and an orange woven
raised-hand approval shape. Morph the cords themselves. Guard activation opens the existing
scoped wait decision UI and never auto-approves or stops the run. Speech processing activation
cancels pending speech rather than starting microphone capture. Maintain Stop behavior, confirmed
stop guards, meter isolation, background pause and Reduce Motion. No Framework/Watch changes.

## Validation

Render recognizable endpoints, sampled morph/reversal and moving/frozen frames at phone sizes.
Native tests for TTS/STT preparation/cancel and guard activation opening all three existing
approval choices, including a child wait. Retain screenshots, update docs/changelog, install a
normal development build. No Git commit/push or Store upload until user validation.

## ADR state

Existing thin-client/rendering and delivery boundaries apply. No new cross-task architecture rule.

## Completion report — 2026-10-19

AssistantOrb/OrbArtwork interpolate Stop, geodesic and Guard geometry; OrbWeave projects a
subdivided icosahedron or orange raised-hand cords. VoicePresence maps actual transcription
and TTS preparation/buffering state to geodesic, and the current scoped tool approval to
Guard. Guard opens the existing three-choice sheet without stopping or deciding. Speech
cancellation retains generation/task guards. Touch-down captures its intended action, so a
resolved approval cannot turn release into microphone activation. Reduce Motion/background,
Stop debounce and voice envelope behavior are preserved.

Package260/260 and native22/22 pass, including12 voice tests and5 renderer checks. Final1050
regression3/3 also passes. Native endpoint/morph/production screenshots inspected; evidence:
../evidence/1049/README.md. README, architecture, native changelog and llms-full updated.
Normal development-signed0.6.22(33) signature-verified, installed and launched on the iPhone.

Original planned/1049_speech_and_approval_orb_states.md moved here with its ID and intent
preserved. Existing thin-client/rendering ADR boundaries apply; no new durable rule or
follow-up needed. User device validation remains pending; animation was inspected through
native snapshots/tests rather than continuous video. No Framework/Watch edits, commit/push
or Store upload.
