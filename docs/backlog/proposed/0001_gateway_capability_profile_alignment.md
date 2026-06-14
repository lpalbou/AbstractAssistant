# Proposed: Gateway capability profile alignment

## Metadata
- Created: 2026-05-08
- Status: Proposed
- Completed: N/A

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: None

## Context

Gateway now exposes multimodal capability defaults, direct media catalogs, and workflow-catalog
selection as the shared control-plane contract for desktop clients.

## Current code reality

- The assistant repo has moved substantially toward a gateway-native v2 shell.
- The legacy assistant architecture still exists and can still invite local routing assumptions if
  future work is not careful.
- Hosted desktop auth and cross-platform host questions remain open.

## Problem or opportunity

Even after the v2 redesign began, the assistant can still drift back toward acting like a second
routing control plane instead of a gateway-native shell.

## Proposed direction

Keep the assistant thin and gateway-driven:

- use gateway discovery and workflow-catalog routes for workflow selection;
- use gateway capability-default routes for text, voice, image, video, sound, and music defaults;
- keep local desktop code focused on UX concerns such as tray behavior, hotkeys, mic capture,
  playback, and downloads.

## Why it might matter

This proposal captures the design pressure that justified the v2 redesign and remains useful as
background while rollout work continues.

## Promotion criteria

- Promote only if new code reintroduces local routing policy or if additional rollout work needs a
  broader implementation item.

## Validation ideas

- Fixture coverage for gateway capability-default payloads
- Validation that desktop settings edit gateway routes rather than local defaults
- Workflow-launch tests that prefer workflow-catalog metadata

## Non-goals

- This proposal does not authorize a host rewrite by itself.
- This proposal does not replace the active rollout item.

## Guidance for future agents

Use this proposal as background design memory. For active implementation sequencing, prefer the
planned rollout item.
