# Proposed: Frozen macOS bundle parity and packaging trim

## Metadata
- Created: 2026-06-21
- Status: Proposed
- Completed: N/A

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: None

## Context

The repo already has a working macOS bundle path through `build-macos-app`, and the v2 tray shell
is the canonical desktop experience. Recent validation showed that contributor workflow can still
drift if source-run tray testing is treated as equivalent to the installed `/Applications` bundle.

## Current code reality

- `abstractassistant/build_macos_app.py` wraps the PyInstaller build and installs the resulting
  `AbstractAssistant.app` into `/Applications`.
- `packaging/macos/AbstractAssistant.spec` previously force-collected all `abstractcore`
  submodules, which widened the PyInstaller graph far beyond the gateway-native tray surface.
- The spec has now been narrowed, but the build still analyzes some optional desktop-adjacent
  packages and emits residual warnings from unused native dependencies such as `numba`/`libomp`.
- The release workflow does not publish or validate the macOS `.app`.

## Problem or opportunity

The bundle build is functional again, but there is still room to improve parity guarantees between
source and frozen-app validation, reduce packaging breadth further, and make bundle health easier to
check before release.

## Proposed direction

Keep this as a follow-up track for targeted packaging trim and stronger frozen-bundle validation
evidence.

## Why it might matter

If the bundle remains materially broader than the runtime surface, future UI work can still pay
avoidable packaging cost and may accumulate warnings that obscure real macOS app regressions.

## Promotion criteria

- Bundle build time, size, or warnings become a recurring friction point.
- A frozen-app-only regression appears that source-run tray testing would not catch.
- Release automation or contributor workflow needs explicit macOS bundle checks.

## Validation ideas

- Compare PyInstaller analysis breadth before and after any further spec trimming.
- Validate `/Applications/AbstractAssistant.app` after user-visible tray/palette changes.
- Track whether unused optional packages can be excluded without breaking voice, tray, or settings
  behavior.

## Non-goals

- This proposal does not authorize a host migration.
- This proposal does not change the gateway-native runtime contract.

## Guidance for future agents

Treat bundle-parity work as packaging hygiene, not as a reason to re-open local-runtime routing.
Any trim should preserve the v2 tray shell, gateway connection UX, and bundle rebuild path first.
