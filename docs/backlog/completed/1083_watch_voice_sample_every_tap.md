# 1083 — Watch: every voice you choose plays its sample, or says why it cannot

**Status**: completed (2026-10-29, unreleased; in a PR, not done until merged and verified on the operator's watch)
· **Priority**: P1 · **Created**: 2026-10-29

## Why (operator, 2026-10-29)
In Settings → Voice ("Your voices": hal9000-qwen2, hal9000-qwen, pascale-qwen…), selecting a voice did not always
start its sample; sometimes nothing played, and nothing said why.

## Findings
- **Every tap does call `pickVoice`** (a `Button`), so the sample is asked on every tap, not only on a selection
  change. The list's re-render does not cancel it: the `Speaker` is a `@StateObject`.
- **The gateway is not the cause.** The Mac gateway on 8080 (the operator's voices) was measured with the watch's
  request: `POST runs/session_memory_…/voice/tts/stream`, "Hello, I'm AbstractAssistant.", qwen3-tts clones, two
  rounds per voice. Every sample came back 200 with 5 audio chunks, about 2.6–3.4 s of audio and `done`. Audio
  arrived 0.6–2.4 s after the request (the slowest was hal9000-qwen2's first one, cold), with no empty answer and
  no error.
- **Watch side, three paths to silence:**
  1. `Speaker.read` called `stop()`, which deactivated the audio session (`setActive(false)`) before the next
     sample re-activated it. A deactivation still under way left the new reading silent, or failed into a
     `.failed` state that nothing displayed.
  2. A stream that ended with no audio and no error finished as `.finished`, which played nothing and said
     nothing.
  3. The voice list never showed `.failed(reason)`.

## What shipped
- `Speaker.read` stops the previous reading with `stop(keepSession: true)`: the session stays active from one
  reading to the next. It is released when a reading ends or the page closes.
- `SpeechSample.failure` (AbstractGatewayClient): no sound and no error counts as a failure, "The gateway sent no
  sound for this voice." `SpeechSample.line` gives the row's one line.
- `VoiceSettingsView`: the tapped row says "Playing the sample", or "The sample did not play: <reason>" (amber,
  one line). The voice rows and the speed rows alike.
- Mock `--failing-sample`: the mock voice M2 fails like a gateway with its engine missing.
- Tests:
  - package `SpeechSampleTests` (4);
  - UI `VoiceSettingsUITests.testEveryTapPlaysItsSampleAndAFailureSaysWhy`: M1 plays, F1 replaces it, F1 again
    plays, M2 says why;
  - the two existing voice tests stay green.
- Mutation-checked: without the failure line the UI test fails.
