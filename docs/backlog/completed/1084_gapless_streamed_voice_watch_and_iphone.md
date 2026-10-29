# 1084 — Watch and iPhone: a streamed reply plays with no silence between its segments

**Status**: completed (2026-10-29, unreleased; in a PR, not done until merged and verified on the operator's watch)
· **Priority**: P1 · **Created**: 2026-10-29

## Why (operator, 2026-10-29)
On the watch, a long spoken reply was cut for 2–4 s between segments. The gateway was measured sending its
segments with no gap, so the remaining suspect was the client's player.

## Findings
- **Watch `Speaker`** started the next segment from `audioPlayerDidFinishPlaying`, through a MainActor hop, and
  only then created and prepared its `AVAudioPlayer`. Every segment boundary waited for that chain, and a busy
  main thread (UI, network decoding) stretched it.
- **iPhone `VoiceController.read`** played one segment, polled until it ended, then took the next one from the
  stream. Same chain, plus the poll interval.
- `AVAudioEngine` + `AVAudioPlayerNode` was tried first and dropped: `AVAudioUnitTimePitch` (the reading speed)
  is unavailable on watchOS.
- `AVAudioPlayer.isPlaying` is already true for a player booked in the future with `play(atTime:)`, and
  `currentTime` moves in coarse steps. A probe built on either reported 0 ms against a 300 ms mutation (watch),
  or 80–270 ms of silence in the middle of a segment (iPhone). The probe below measures where each player
  really started instead.

## What shipped
- `SpeechTimeline` (AbstractGatewayClient), a pure booking model:
  - each received segment starts at `max(bookedEnd, now)`: right where the previous one ends, or at once when
    the voice already ran dry (a late segment; its `gap` is the lateness);
  - the first start waits for 1.5 s of speech, unless the stream already ended.
- Watch `Speaker` rewritten on it. Each segment's `AVAudioPlayer` is booked on the device clock all players
  share (`play(atTime:)`) the moment it arrives. `audioPlayerDidFinishPlaying` is bookkeeping only. Pause,
  resume, rewind and the position follow the booked players. The audio session stays active between
  readings (from 1083).
- iPhone `VoiceController.read` does the same: book on arrival; pause holds the sounding segment and unbooks
  the rest; resume books them back to back.
- `maxGapMilliseconds` (both apps) is the largest silence asked of the device clock. In DEBUG builds, a
  10 ms probe also measures what was heard: each sounding player's real start is estimated as
  `deviceCurrentTime − currentTime / rate` (earliest estimate kept), and the silence is the next segment's
  real start minus this one's real end. UI tests read it from a hidden `debug.gaps` label.
- Mock `--long-voice` on the iPhone (demo world): 2.4 s, 2 s, then four 8 s segments arriving 1.5 s apart. The
  watch world already had it: 1.3 s, 8 s, then four 8 s segments.

## Evidence (simulators, 2026-10-29)
- Watch UI `GaplessVoiceUITests.testALongStreamedReplyPlaysWithoutGaps`: largest silence 10 ms, 41.3 s
  spoken, no stall.
- iPhone UI `PhoneGaplessVoiceUITests.testALongStreamedReplyPlaysWithoutGaps`: largest silence 4–8 ms, the
  reading lasted 36.4–36.6 s (36.4 s of speech).
- Package `SpeechTimelineTests` (4): back to back with no gap; the 1.5 s first start; a late segment starts at
  once with its lateness as the gap; the segment playing at a given clock time. The whole package suite is
  green (184).
- Mutation-checked:
  - each player started 300 ms later per segment, at the `play(atTime:)` call only, so the booking arithmetic
    does not see it: the watch UI test fails with 308 ms of silence, the iPhone one with 309 ms;
  - a 200 ms gap added in `SpeechTimeline`: all 4 package tests fail.

- Regressions:
  - iPhone unit tests: 50 run, 0 failures. The buffering test caught a voice that ran dry no longer showing
    "preparing"; the sampler now shows it again when every booked part has been heard and the gateway is
    still sending.
  - Watch voice UI tests green: VoiceGoesOn, StopVoice ×2, VoiceSettings ×3, Media ×2. `StopVoiceUITests
    .testHoldingTheOrbTogglesReadingAndListening` failed once while the iPhone tests ran beside it, then
    passed 3/3 alone.

## Not done here
- Verified on the operator's watch: pending a deploy and the operator's ear.
- VoiceButtonUITests `testHoldOnAFinishedVoicePlaysItFromTheStart` and `testNearMissesNeverStartListening`
  also fail on main (b6c0704), so they are not this change.
