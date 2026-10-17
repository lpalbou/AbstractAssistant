# Proposed: Voice on the wrist: record, transcribe on the gateway, speak the answer

> Created: 2026-10-16 22:30:00 +0200
> Type: feature
> Priority: P2
> Labels: watch, voice

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractassistant (watch client), abstractgateway (session-scoped transcription)
- Track: [watch-apple](README.md) (Apple Watch client)

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md) (gateway-native thin client: the gateway owns workflows, runs, tools, policy and speech)
- ADR impact: None. The watch is one more thin client of the same gateway contract.

## Summary
Hold to record on the Ask screen, upload the audio, transcribe it on the gateway (Whisper or
the configured speech engine), send the text as the prompt, and stream the answer's speech back
to the watch speaker or Bluetooth headphones.

## Why
The watch SDK has no on-device speech recognition (`Speech.framework` is absent on watchOS;
`untracked/watch/research/toolchain-check.md` §D). Dictation through the text field works but
is Apple's cloud service; recording and transcribing on the user's own gateway keeps the audio
at home, which is the point of the framework. Speech-to-text and text-to-speech already exist
on the gateway as run-scoped routes.

## Scope
- Watch: `presentAudioRecorderController` (or `AVAudioRecorder`) for a short clip; `POST /attachments/upload`; transcription; `runs/start` with the text; `GET /runs/{id}/voice/tts/stream` played with `AVAudioPlayer`/`AVAudioEngine`.
- Gateway: a session-scoped transcription route (`POST /api/gateway/sessions/{id}/audio/transcribe` or an unscoped `audio/transcribe` under the account token) so the watch does not have to start an empty run to transcribe.

## Non-goals
No hands-free loop on the watch (battery and the suspend model), no wake word, no on-watch models.

## Current code reality
- STT and TTS routes are run-scoped: `POST /runs/{id}/audio/transcribe` (uploaded artifact), `GET /runs/{id}/voice/tts[/stream]` (abstractgateway/docs/api.md §audio). `/v1/audio/*` exists only with `/v1` enabled and a named key, which the watch cannot use for gateway routes.
- Uploads: `POST /attachments/upload`, 25 MB, tied to a session (api.md §attachments).
- The desktop assistant plays the TTS stream chunk by chunk and measured first audio under a second on a settled gateway (`docs/voice.md`).

## Dependencies
Item 0012 (the app), gateway agreement on a session-scoped transcription route.

## Expected outcomes
- A question spoken into the watch is transcribed by the user's gateway and answered aloud, with the audio never leaving the user's infrastructure.

## Acceptance Criteria
- [ ] A 10 s recording uploads and transcribes through the gateway; the transcript is shown before sending
- [ ] The answer is spoken from the TTS stream with first audio under 2 s on a LAN
- [ ] Bluetooth headphones are used when connected; the watch speaker otherwise

## Testing
- `cd watch/apple && ./scripts/build.sh --screen listen`
- `curl -s -H "Authorization: Bearer $TOKEN" -F file=@clip.m4a http://127.0.0.1:8080/api/gateway/attachments/upload`

## Progress (2026-10-17)
- Voice OUT is built: Read aloud on answers, run outputs, automation results and fetched pages streams `POST /runs/{id}/voice/tts/stream` (entities: `/entities/{name}/voice/tts/stream`) and plays the WAV chunks through the watch speaker; the orb follows the audio level. Verified on a Series 11 against gateway.abstractframework.ai (supertonic, first audio about 5 s).
- Voice IN is built: tap the orb to record, tap again or 5 s of silence to send; upload + `/runs/{owner}/audio/transcribe`. Verified in the simulator against the public gateway; on the watch it needs the microphone permission tap.
- Answers reach the person while the app is closed: a background URLSession follows the run's ledger stream and the app posts the answer as a notification (Listen action). Push from the gateway for automations and waits stays with 0014.
