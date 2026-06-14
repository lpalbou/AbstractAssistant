# Backlog Overview

AbstractAssistant is in the middle of a gateway-native desktop redesign. The active goal is to
finish the v2 tray and palette shell while keeping Gateway as the authority for workflow launch,
multimodal defaults, and durable execution. The runtime contract is now a single published gateway
workflow, not a hybrid of workflow, private-bundle, and direct-chat paths.

## Current Counts

- Planned: 2
- Proposed: 2
- Completed: 1
- Deprecated: 0
- Recurrent: 0

## Next Recommended Work

1. Finish the production UX hardening pass around the now-canonical gateway workflow shell.
2. Continue the broader v2 rollout and remove remaining legacy assistant code that still suggests
   alternate runtime models.
3. Harden the desktop auth UX around expiry, session renewal, and secure local storage.

## Planned Items

| ID | Item | Status | Notes |
|---|---|---|---|
| [0002](planned/0002_gateway_native_assistant_v2_rollout.md) | Gateway-native assistant v2 rollout | Planned | Broader rollout and legacy de-emphasis after the single-path contract cleanup. |
| [0004](planned/0004_production_ux_and_catalog_default_hardening.md) | Production UX and catalog-default hardening | Planned | Final polish and live macOS validation on the single-workflow shell. |

## Proposed Items

| ID | Item | Status | Promotion criteria |
|---|---|---|---|
| [0001](proposed/0001_gateway_capability_profile_alignment.md) | Gateway capability profile alignment | Proposed | Keep as background design memory while v2 rollout lands. |
| [0003](proposed/0003_tauri_shell_spike.md) | Tauri shell spike | Proposed | Promote only if cross-platform host evidence outweighs Qt-first delivery. |

## Completed Items

| ID | Item | Status | Notes |
|---|---|---|---|
| [0005](completed/0005_single_gateway_workflow_contract_cleanup.md) | Single gateway workflow contract cleanup | Completed | Removed active hybrid runtime behavior and codified the canonical managed workflow boundary. |

## Deprecated Items

No deprecated backlog items currently tracked.

## Operating Notes

- New items use four-digit global IDs.
- Gateway-related authority changes must cite [ADR 0001](../adr/0001_gateway_native_assistant_v2.md).
- When code and backlog disagree, update backlog text in the same pass.
