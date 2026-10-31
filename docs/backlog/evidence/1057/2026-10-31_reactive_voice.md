# Measured voice feedback — 2026-10-31

The orb previously subscribed only to the microphone channel. During reply playback
it received zero loudness. A prior adapter also failed to supply scalar amplitude
when optional spectral bands were absent. The current adapter uses the measured
scalar envelope in that case; explicit zero bands still mean silence. Legacy
Vortex Listening also ignored amplitude; its shared generator now contracts with it.

AbstractUIC's `useGatewayVoice` exposes an additive stable
`subscribe_playback_level` subscription. It observes the existing reply gain node,
after volume/mute, with a separate AnalyserNode branch. It does not change playback
routing, start another audio context, capture a microphone, or rerun synthesis.
Samples are RMS ×4, clamped and quantized, at 20Hz. Sampling stops on pause, stop,
completion, unmount or the final unsubscribe. Consumers alone re-render; the voice
hook owner does not receive per-sample state updates. Microphone metering explicitly
resumes its own context. `useVoiceLevel(voice, "playback")` and the meter's `channel`
prop select output while preserving the default microphone API.

The web app selects the microphone channel for Listening and playback for Speaking.
It uses a hashed snapshot of these canonical shared modules until its ui-kit pin
is updated; no independent app audio implementation is introduced. Voice activity
uses scalar RMS; full Watch spectral analysis is not claimed.

Checks:

- Native generator: ten tests, including all 44 designs × Listening/Speaking at
  quiet/loud levels; matching Wasm artifact rebuilt from recorded source.
- Shared Canvas: all 44 designs × both voice poses produce different pixels for
  quiet/loud input at the same time, without requiring measured frequency bands.
- Shared voice lifecycle tests: separate channels, stable callbacks, subscriber
  cancellation, pause/resume without resynthesis, stop and owner render isolation.
  Existing streaming cancellation/EOF/error tests remain green.
- Chromium real Web Audio with generated quiet/loud PCM and a virtual microphone:
  instrumented actual Wasm frames receive microphone levels 0–1 and reply levels
  0–0.65. Reply volume zero produces zero; restoring it restores real amplitude.
  Physical output is disabled by `--mute-audio`, and no physical mic is opened.
- 62 web unit tests; 16 light/dark responsive combinations; existing speech ownership,
  approvals, Docs, catalog, preference and reduced-motion browser checks pass.

Local logs and screenshots: `untracked/voice-feedback-*` and `untracked/voice-feedback/`.
Physical user-device audio and native Watch playback were not tested here.
