# Planned: Production UX and Catalog-Default Hardening

## Metadata
- Created: 2026-06-12
- Status: Planned
- Completed: N/A

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: Extends the rollout with production UX and default-runtime hardening.

## Context

The v2 shell now has a single managed gateway workflow path, cleaner connection/settings
separation, and a materially better tray surface. It still needs one more hardening pass before it
can be called production-ready on macOS and later on other desktop hosts.

## Current code reality

- `abstractassistantv2/app.py` now submits all turns through the published assistant workflow and
  no longer exposes runtime mode selection in the primary user path.
- `abstractassistantv2/controller.py` and `abstractassistantv2/gateway.py` now reconcile and run a
  managed `abstractassistant-orchestrator` workflow from the gateway tenant catalog.
- The primary palette and settings dialog are visually improved, but expert review still flags
  workflow provenance clarity, blocked-state guidance, and scope copy around gateway-owned defaults.
- Live macOS polish and visual validation are still incomplete.

## Problem

The assistant is now usable again, but the remaining gaps are concentrated in trust, provenance,
and product polish rather than raw integration. Those gaps are exactly what will determine whether
users treat the app as production-grade or as an internal prototype.

## What we want to do

Finish the production hardening pass for the tray shell and its default runtime path.

## Why

Without an explicit follow-up item, the repo can stop at “working again” while leaving the most
important release blockers in the UX and workflow-default story.

## Requirements

- Make the single workflow path understandable on first launch.
- Surface workflow/default provenance clearly enough that users can tell what is governing replies.
- Improve blocked and empty states so the tray surface does not invite actions that are guaranteed
  to fail.
- Keep the tray surface compact and trustworthy while the workflow handles tool and media routing.
- Validate the polished tray shell on a real macOS desktop, including readability, focus behavior,
  hotkey flow, voice toggles, and workflow-routed media actions.

## Suggested implementation

- Add explicit provenance copy and clearer blocked-state guidance on the palette.
- Keep the managed assistant workflow as the only runtime path.
- Capture real desktop screenshots and smoke evidence after the next UX pass.

## Scope

- palette UX hardening
- workflow/default provenance
- catalog default publication
- macOS smoke validation

## Non-goals

- Do not migrate hosts again in this item.
- Do not bring back local provider/model routing as the default policy.

## Dependencies and related tasks

- [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- [0002](0002_gateway_native_assistant_v2_rollout.md)
- [0001](../proposed/0001_gateway_capability_profile_alignment.md)

## Expected outcomes

- The tray assistant is understandable and trustworthy on first launch.
- The canonical assistant workflow is the stable runtime for real deployments.
- Users are not exposed to hidden execution-path differences.

## Validation

- `python -m pytest tests/basic tests/integration -q`
- Live macOS tray smoke with the real gateway:
  - chat
  - multimodal attachment input
  - image/video/music requests through the assistant workflow
  - settings save/reset
  - blocked gateway state
  - summon hotkey
- Screenshot review for the tray shell and settings dialog

## Progress checklist
- [x] Replace private/direct hybrid execution with one managed assistant workflow path
- [x] Rework the settings information architecture into separate connection/gateway/device surfaces
- [ ] Make workflow/default provenance obvious on the main tray surface
- [x] Publish and promote a dedicated assistant workflow into the gateway catalog
- [ ] Complete live macOS UX validation and capture final screenshots

## Guidance for the implementing agent

Treat “looks professional” and “is trustworthy” as the same requirement. If the user cannot tell
what path is answering, what scope a settings change affects, or why the tray is blocked, the work
is not done.
