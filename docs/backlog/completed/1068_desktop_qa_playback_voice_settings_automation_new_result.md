# 1068: Desktop QA 2026-10-28: playback states, voice settings, an automation's new result

**Status**: completed in 0.16.4 (branch `fix/desktop-qa-2`; released by `release.yml` workflow_dispatch from main).
**Cross-package**: AbstractVoice (`abstractvoice/tts/tts_engine.py` `NonBlockingAudioPlayer.stop_stream()` leaves
`_audio_started` set, see (h)); follow-up 1069 (an automation run as a full replay-view exchange); root 1063 /
AbstractRuntime 0858 (typed runs).
**Scope**: the desktop app only.

## (h) Reply playback: the spinner kept spinning while the reply was spoken

**Cause.** The message card leaves its loading spinner for play/pause when the voice manager reports the start of
speech, and the voice manager reported it only from the audio player's own start hook. AbstractVoice's
`NonBlockingAudioPlayer` fires that hook once per playback, guarded by `_audio_started`; `stop_stream()` (every
stop: another reply's speaker, a new reply, a stop) does not reset the flag and the next `play_audio()` opens a new
stream without resetting it either. After the first interrupted reply, no later reply reported a start: the card
spun for the whole reply.

**Fix.** The voice manager announces the start itself (once per playback) as soon as the first audio is handed to
the player, on the stream lane and on the single-shot lane; the player's hook stays as a second, idempotent source.
Speaker and copy are shown at all times (they were revealed on hover only); the speaker shows the spinner, not
clickable, only while the audio loads, then pause / play.

**Tests.** `test_speech_start_is_announced_when_audio_reaches_the_player` (a player whose hook never fires; fails
on 0.16.3), `test_message_card_speaker_and_copy_are_always_visible`,
`test_message_card_spinner_only_while_loading_then_play_pause`.

**For AbstractVoice.** Reset `_audio_started` in `stop_stream()` / `clear_queue()` (and when `play_audio()` opens a
new stream), so every playback reports its start.

## (i) Voice settings

- **Every Qwen3-TTS model was listed twice.** The speech-model catalog lists each model in `items` (id = the model)
  and again in `provider_models` (id = `"<provider>/<model>"`); the desktop deduplicated by id. A `provider_models`
  row is now keyed by its `model` (also what the override stores). Live check against a scratch AbstractGateway 0.17.0
  + AbstractVoice 0.19.2: 5 Qwen3-TTS models listed once (were 10). Test: `tests/basic/test_voice_model_choices_dedupe.py`.
- **The route's state line looked like a warning and named the voice by its id** ("· voice 41576236…"). The line is
  neutral (`tone="neutral"`, never the theme accent, amber in some themes) and names the voice as the voice list does
  ("· voice hal9000-qwen2"); before the list is read, a stored voice reads "a saved voice"; a saved voice no longer
  listed reads "<name> (saved, not listed now)". Test: `test_the_route_state_names_the_voice_and_is_not_a_warning`.

## (g) "1 new result" -> Open showed nothing marked

The automation view already shows each run as one exchange (the task turn, the answer card). Opening it now reads
the unseen results (`attention.items`, before viewing acknowledges them), marks those runs "New result", and opens
on the first of them instead of the bottom of the list; closing the view clears the marks. A run's file list names
files, never artifact ids. Tests: `tests/basic/test_automation_new_result_marked.py`.

The rest of the ask (each run as a full conversation exchange: its tool activity, media and approvals, as a chat
turn renders them) needs each occurrence's replay view: follow-up 1069.
