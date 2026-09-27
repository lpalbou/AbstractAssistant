# Backlog Overview

AbstractAssistant is in the middle of a gateway-native desktop redesign. The active goal is to
finish the v2 tray and palette shell while keeping Gateway as the authority for workflow launch,
multimodal defaults, and durable execution. The runtime contract is now a single published gateway
workflow, not a hybrid of workflow, private-bundle, and direct-chat paths.

## Current Counts

- Planned: 8
- Proposed: 5
- Completed: 1
- Deprecated: 0
- Recurrent: 0

## Next Recommended Work

0. Follow-ups from the 0.5.0 UX pass (2026-09-05): stop publishing/promoting the managed workflow
   from the client (ship it as a gateway-side catalog package and only check presence); list chats
   from the gateway session store instead of the local registry; add the per-answer "steps" chip
   that re-opens the live activity model after a run; add tray icon states for waiting and voice.

1. Finish the remaining v2 runtime-replayer compliance gaps after the strict terminal replay pass:
   cross-client wait race tests, static direct-execution guards, voice/media boundary tests, and
   ledger-only tool details.
2. Finish the production UX hardening pass around the now-canonical gateway workflow shell.
3. Keep frozen macOS bundle validation and source-vs-bundle parity visible for tray and palette
   changes.
4. Define durable session topic/summary metadata so recent-session navigation can stay compact and
   trustworthy without re-deriving titles ad hoc.
5. Continue the broader v2 rollout and remove remaining legacy assistant code that still suggests
   alternate runtime models.
6. Harden the desktop auth UX around expiry, session renewal, and secure local storage.

## Planned Items

| ID | Item | Status | Notes |
|---|---|---|---|
| [0852](planned/0852_automations_in_the_assistant.md) | Automations in the Assistant | Planned | Automations v1 mission A (root 0928): gateway-fed Automations section grouped by `automation_id`, tray "Automations…", "Schedule this conversation…", `changed_since` polling into tray notifications, occurrences as a chat, Discuss as a normal session, answering occurrence waits; regular list = `chat` + `discussion` by `session_kind`. Needs gateway API + abstractuic fixtures. Contracts pass 2026-09-27: see the item's section and root `untracked/design/automations-CONTRACTS.md`. |
| [0851](planned/0851_settings_reads_the_gateway_on_the_gui_thread.md) | Settings reads the gateway on the GUI thread | Planned | Opening Settings blocks the event loop on synchronous 30 s HTTP — measured 61 s against a black-hole host, ~210 s worst case. The 2026-09-18 wave cut the Models page from 7 round trips to 2; threading and a short settings timeout remain. |
| [0850](planned/0850_transcript_refresh_cost_and_answer_link_follow_ups.md) | Transcript refresh cost and clickable-link follow-ups | Planned | Rebuild-everything on each run event now carries per-card filesystem work; spoken paths; fenced-path edge. Follows the 2026-09-17 links/tool-identity wave. |
| [0002](planned/0002_gateway_native_assistant_v2_rollout.md) | Gateway-native assistant v2 rollout | Planned | Broader rollout and legacy de-emphasis after the single-path contract cleanup. |
| [0004](planned/0004_production_ux_and_catalog_default_hardening.md) | Production UX and catalog-default hardening | Planned | Final polish and live macOS validation on the single-workflow shell. |
| [0006](planned/0006_durable_session_topics_and_summaries.md) | Durable session topics and summaries | Planned | Define canonical topic/summary metadata for recent-session navigation in the gateway-native shell. |
| [0008](planned/0008_v2_runtime_replayer_adr_compliance_hardening.md) | V2 runtime replayer ADR compliance hardening | In progress | Strict terminal replay, non-blocking wait projection, runtime-authoritative cache replacement, no durable empty-output fallback, and provider/model-free run input landed; static guards, cross-client race tests, and voice/media boundary tests remain. |

## Proposed Items

| ID | Item | Status | Promotion criteria |
|---|---|---|---|
| [0001](proposed/0001_gateway_capability_profile_alignment.md) | Gateway capability profile alignment | Proposed | Keep as background design memory while v2 rollout lands. |
| [0003](proposed/0003_tauri_shell_spike.md) | Tauri shell spike | Proposed | Promote only if cross-platform host evidence outweighs Qt-first delivery. |
| [0007](proposed/0007_frozen_macos_bundle_parity_and_packaging_trim.md) | Frozen macOS bundle parity and packaging trim | Proposed | Promote if bundle breadth, warnings, or frozen-app-only regressions keep recurring. |

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
