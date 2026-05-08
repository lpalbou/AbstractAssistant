# Proposed: Gateway Capability Profile Alignment

## Metadata
- Created: 2026-05-08
- Status: Proposed
- Completed: N/A

## Context

AbstractAssistant is a gateway-first tray/CLI thin client. The app should render local UX, capture
input, play audio, and observe Gateway runs; durable execution, providers, generated media, memory,
tools, and workflow selection live in AbstractGateway.

Gateway now exposes native Python deployment profiles:

- `abstractgateway[server]` for lightweight remote/server usage.
- `abstractgateway[apple]` / `abstractgateway[gpu]` for full native local-engine deployments.
- `abstractgateway[all-apple]` / `abstractgateway[all-gpu]` as explicit aggregate spellings.

## Problem

Assistant can easily regress into a local runtime app because it has audio UX and historical local
voice code. That would duplicate Gateway/Core configuration and make installed capabilities differ
between the tray app and the deployed Gateway.

## Proposed Direction

Keep Assistant thin and Gateway-driven:

- use Gateway discovery for workflows, provider/model choices, tool policy, generated image/music
  availability, voice profile/model catalogs, prompt-cache readiness, and memory readiness;
- keep local audio code limited to microphone capture, VAD, playback, and UI metering;
- send STT/TTS requests to Gateway endpoints in gateway mode, so the selected Gateway profile
  decides whether audio is remote OpenAI-compatible, Apple-local, or GPU-local;
- document local hardware setup as `pip install "abstractgateway[apple]"` or
  `pip install "abstractgateway[gpu]"`, not as an Assistant dependency.

## Non-Goals

- Do not make Assistant install Core, Runtime, Vision, Voice, Music, or Memory local engines by
  default.
- Do not store provider API keys or Gateway deployment settings in Assistant-specific config.
- Do not add an Assistant-only model catalog.

## Promotion Criteria

Promote when Assistant needs to expose Gateway 0.2.4+ media/voice/music/memory capability selection
in the tray UI.

## Validation Ideas

- Gateway capability fixture tests for lightweight, Apple, and GPU deployments.
- STT/TTS regression tests proving gateway mode calls Gateway routes, not local model engines.
- Manual smoke with a lightweight Gateway and a native Apple/GPU Gateway to verify the same client
  adapts to advertised capabilities.

## Guidance For Implementing Agents

Preserve the VoiceManager-compatible adapter shape only for local capture/playback ergonomics.
Execution and generated media should remain Gateway-owned in gateway mode.
