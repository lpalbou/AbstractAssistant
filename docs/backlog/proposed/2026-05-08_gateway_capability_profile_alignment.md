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

## Detailed Plan

1. Add a Gateway capability service in the Assistant client layer.
   - Fetch and cache `/api/gateway/discovery/capabilities`.
   - Parse provider/model catalogs, workflow entrypoints, generated media, voice profiles/models,
     music readiness, memory readiness, prompt-cache support, tool policy, and workspace policy.
   - Keep stale/offline state explicit so reconnect UX can recover without local fallbacks.

2. Rework voice UX around Gateway catalogs.
   - Keep local microphone capture, VAD, playback, pause/resume, and meter rendering.
   - Route STT and TTS through Gateway endpoints in gateway mode.
   - Populate voice/profile/model choices from Gateway catalog routes.
   - Treat missing Gateway TTS/STT as disabled UI state, not as permission to load local speech
     models.

3. Add generated-media handling.
   - Render generated images/audio/music artifacts from run output and ledger events.
   - Download/play audio artifacts through Gateway artifact routes.
   - Keep generated resources such as cloned voices distinct from one-off audio files.
   - Avoid duplicate final responses when media appears both in ledger events and final run output.

4. Align session and workflow controls.
   - Workflow picker should use Gateway entrypoint metadata and input schemas.
   - Prompt-cache controls should call Gateway session prompt-cache endpoints only when advertised.
   - Tool approval UI should use Gateway tool inventory/default approval policy.
   - Memory status should be informational unless the selected workflow requires KG memory.

5. Test the thin-client boundary.
   - Gateway mode must not import or instantiate local Core/Vision/Voice/Music engines.
   - Add fixture tests for lightweight, Apple, GPU, offline, and partially configured Gateway
     capability payloads.

## Non-Goals

- Do not make Assistant install Core, Runtime, Vision, Voice, Music, or Memory local engines by
  default.
- Do not store provider API keys or Gateway deployment settings in Assistant-specific config.
- Do not add an Assistant-only model catalog.

## Promotion Criteria

Promote when Assistant needs to expose Gateway 0.2.4+ media/voice/music/memory capability selection
in the tray UI.

## Expected Outcomes

- One Assistant binary can connect to lightweight, Apple-native, or GPU-native Gateway deployments.
- Voice and generated media behavior follows the connected Gateway profile, not local Assistant
  dependencies.
- Gateway readiness errors are visible and actionable from the tray UI.

## Validation Ideas

- Gateway capability fixture tests for lightweight, Apple, and GPU deployments.
- STT/TTS regression tests proving gateway mode calls Gateway routes, not local model engines.
- Manual smoke with a lightweight Gateway and a native Apple/GPU Gateway to verify the same client
  adapts to advertised capabilities.

## Guidance For Implementing Agents

Preserve the VoiceManager-compatible adapter shape only for local capture/playback ergonomics.
Execution and generated media should remain Gateway-owned in gateway mode.
