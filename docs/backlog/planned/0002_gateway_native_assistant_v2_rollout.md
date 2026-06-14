# Planned: Gateway-native assistant v2 rollout

## Metadata
- Created: 2026-06-12
- Status: Planned
- Completed: N/A

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: None

## Context

The assistant repo now contains a v2 shell that is closer to the gateway contract than the legacy
desktop stack. It still needs follow-up work around auth, packaging, UX hardening, and legacy
de-emphasis before the redesign can be treated as the stable product path.

## Current code reality

- `abstractassistantv2/` contains the new tray shell, controller, preferences, and gateway service.
- The CLI now launches the v2 tray shell by default and assistant execution is routed through one
  managed catalog workflow.
- The legacy `app.py` and `ui/qt_bubble.py` path still exists and still represents a large amount
  of historical complexity.
- The settings flow now supports both bearer-token and hosted gateway-session sign-in.

## Problem

The architectural boundary is now correct enough to build on, but the rollout is not complete until
the remaining user-visible and operational gaps are closed.

## What we want to do

Make the v2 tray shell the stable assistant path and finish the missing product work around hosted
auth, UX hardening, packaging, and legacy de-emphasis.

## Why

Without a tracked rollout item, the repo can easily drift back into mixed ownership and legacy UI
work, even though Gateway is now the correct control plane.

## Requirements

- Keep Gateway as the source of truth for workflow and multimodal defaults.
- Keep the assistant on one published catalog workflow path with no runtime fallbacks.
- Add a desktop-compatible path for hosted gateway auth.
- Validate approvals, tray summonability, hotkey behavior, and workflow-routed media requests.
- Reduce user-visible dependence on the legacy tray path.

## Suggested implementation

- Continue building on `abstractassistantv2/`.
- Keep controller/service logic host-thin.
- Add auth/session support in the gateway client and desktop shell.
- Add smoke and UX validation around the tray/palette flows.

## Scope

- v2 shell rollout
- auth follow-up
- UX hardening
- packaging and validation notes

## Non-goals

- Do not migrate to Tauri in this item.
- Do not reintroduce local provider/model defaults as the normal routing policy.

## Dependencies and related tasks

- [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- [0001](../proposed/0001_gateway_capability_profile_alignment.md)
- [0003](../proposed/0003_tauri_shell_spike.md)

## Expected outcomes

- The tray assistant behaves as a gateway-native thin client by default.
- Remaining legacy modules stop being the preferred extension point.
- Hosted auth and gateway-owned defaults have a clear user path.
- The single-workflow contract remains intact while the rollout finishes.

## Validation

- `python -m pytest tests/basic tests/integration -q`
- Manual tray smoke on macOS: chat, tool use, image request, voice, approval flow, hotkey
- Documentation review for gateway-owned defaults and workflow catalog behavior

## Progress checklist
- [x] Add hosted desktop auth support for gateway user-session deployments
- [x] Collapse the runtime contract to one managed assistant workflow path
- [ ] Validate tray/palette UX on macOS with workflow-routed media requests enabled
- [ ] Review legacy desktop modules and decide what remains for compatibility only
- [ ] Record packaging and platform validation expectations

## Guidance for the implementing agent

Prefer gateway-native behavior even when legacy code offers a local shortcut. If a new feature
needs local provider/model state to work, treat that as a design smell and re-check the gateway
boundary first.
