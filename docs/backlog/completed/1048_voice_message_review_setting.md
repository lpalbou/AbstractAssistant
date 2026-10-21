# 1048 — Review spoken messages before sending

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Completed
> Completed: 2026-10-19
> Priority: P1
> Labels: iphone, voice, usability

## Current code reality

ChatScreen.finishVoice always starts a Gateway run after transcription. PhonePreferences has
no voice-send preference; Voice settings configures recognition and playback only. The orb's
countdown always announces Sending. Existing native automatic-send coverage assumes that default.

## Scope and expected outcome

Default spoken messages to review in the ordinary keyboard composer. Preserve an existing
typed draft by appending the transcription, and retain pending attachments. Provide Send voice
messages automatically in Settings → Voice & reading, saved per account on this iPhone. Explicit
opt-in preserves the existing direct-send behavior and separate typed draft. Cancellation,
backgrounding and context checks continue to prevent late transcription from acting. Label
countdown according to the selected mode. No Framework changes or live diagnostic tasks.

## Validation

Verify default, persistence/account isolation, native review/edit/manual-send, explicit auto-send,
existing draft preservation and cancellation flows. Update README, voice architecture and
changelog, inspect native screenshots and install a normal physical iPhone build. No commit/push
or Store deployment until user validates. Existing thin-client and local-preference ADR scope
applies; no new architecture rule required.

## Completion report — 2026-10-19

PhonePreferences.autoSendVoice defaultsfalse on clean installs and upgrades and persists per
account/Gateway on this iPhone. Settings → Voice & reading exposes the toggle and explains
both modes. After transcription, ChatScreen opens the ordinary keyboard composer by default,
appends below an existing typed draft and keeps pending attachments; Send is required before
starting the Assistant run. Explicit automatic mode preserves independent voice sending and
its separate typed draft. Foreground/context/session/cancellation guards and temporary recording
cleanup are retained. Orb accessibility countdown now distinguishes preparing text from sending.

Foundation256/256 and native16/16 pass with no failed or skipped tests. Native checks include
review/edit/manual-send, explicit automatic sending, keyboard/suggestion cancellation and11
voice lifecycle/playback cases. Setting and composer screenshots visually inspected. README,
voice architecture, native changelog and llms-full.txt updated; documentation checks pass.
Normal development-signed0.6.22(32) installed and launched on the physical iPhone. Evidence:
../evidence/1048/README.md. Original planned path moved here with the same ID/filename.
Existing local-preference/thin-client architecture applies; no new ADR or follow-up needed.
User validation remains pending. No Framework modifications, Git commit/push or Store upload.
