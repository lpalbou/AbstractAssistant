# Proposed: Tauri shell spike

## Metadata
- Created: 2026-06-12
- Status: Proposed
- Completed: N/A

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: None

## Context

The assistant may eventually benefit from a more portable host than the current Qt shell. Nearby
projects already provide a web-oriented gateway client and UI patterns, but the desktop assistant
still depends on native tray, hotkey, microphone, playback, and artifact-opening behavior.

## Current code reality

- The current active redesign path is still Python/Qt in `abstractassistantv2/`.
- There is no committed Tauri host in this repo today.
- Gateway-native controller and service logic now make a future host swap more plausible than it
  was in the legacy architecture.

## Problem or opportunity

A future host spike could improve cross-platform packaging and shared UI reuse, but it is not yet
clear that those gains outweigh the native bridge work for tray, hotkey, mic, playback, and auth.

## Proposed direction

Run a bounded Tauri spike only after the gateway-native v2 behavior is stable. The spike should
measure whether a Tauri host can match or exceed the Qt shell on summonability, permissions,
artifact handling, and install quality.

## Why it might matter

If the spike shows strong cross-platform and packaging gains, the assistant could eventually move
to a thinner host around the same gateway-native logic.

## Promotion criteria

- The Qt-first rollout is stable enough that host migration is the main remaining product question.
- A prototype demonstrates tray, hotkey, mic, playback, and artifact flows on macOS at minimum.
- Packaging or cross-platform evidence shows a clear benefit over the Qt shell.

## Validation ideas

- Cold start and summon-latency comparison
- Permissions and installer friction comparison
- Voice and artifact flow comparison
- Hosted auth feasibility review

## Non-goals

- This proposal does not authorize a full host rewrite now.
- This proposal does not weaken Gateway’s ownership of workflows or defaults.

## Guidance for future agents

Treat this as a host experiment, not an excuse to revisit the gateway-native authority boundary.

## Spike criteria (2026-10-26, ADR 0008)

[ADR 0008](../../adr/0008_desktop_host.md) keeps PyQt5 as the desktop host for this cycle and
gates this spike on a change of goal by the operator (one component codebase for web and desktop,
or first-class Windows/Linux distribution). When the gate opens, the spike is ONE week, on
macOS, Windows and Ubuntu 24.04 (X11 and Wayland), wrapping the web assistant's components
(ADR 0007) in a Tauri 2 shell, and it must prove with measurements:

- a tray badge updating at 15 fps with click handling (Linux AppIndicator delivers no clicks and
  writes a file per icon update: this is the expected failure point);
- hotkey to a focused composer in under 150 ms;
- AudioWorklet PCM capture to gateway STT without `MediaRecorder` (unusable on stock Ubuntu;
  `audio/mp4`-only on WKWebView);
- streamed TTS with first audio under 1 s;
- a CHILD-run approval answered from the palette (the wait-identity rule of the desktop);
- the bearer host with gateway CORS for `tauri://localhost` and `http://tauri.localhost`;
- a signed and notarized `.app` with only the `audio-input` entitlement, keeping the TCC grants
  under `ai.abstractframework.assistant.mac`.

A spike that fails any of these ends the question for the cycle. Evidence base: the adversarial
review of 2026-10-26 (session scratch `untracked/apple-web-wave/adversary.md` §3).
