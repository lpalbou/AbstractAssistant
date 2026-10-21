# Backlog Overview

AbstractAssistant is in the middle of a gateway-native desktop redesign. The active goal is to
finish the v2 tray and palette shell while keeping Gateway as the authority for workflow launch,
multimodal defaults, and durable execution. The runtime contract is now a single published gateway
workflow, not a hybrid of workflow, private-bundle, and direct-chat paths.

## Current Counts

- Planned: 9
- Proposed: 17
- Completed: 16

Counts recomputed from disk on 2026-10-20 after adding iPhone session approvals1052 (topic tracks included).
- Deprecated: 0
- Recurrent: 0

## Next Recommended Work

0. Follow-ups from the 0.5.0 UX pass (2026-09-05): stop publishing/promoting the managed workflow
   from the client (ship it as a gateway-side catalog package and only check presence); list chats
   from the gateway session store instead of the local registry (now item 0853); add the per-answer "steps" chip
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
7. Apple Watch client: promote 0012 (MVP) once `watch/apple/scripts/build.sh` is green in CI (0018); file 0013 and
   0014 with the gateway seat, since they are the two items that turn the watch from a polling client into a
   notified one.

## Planned Items

| ID | Item | Status | Notes |
|---|---|---|---|
| [1052](planned/1052_revocable_session_tool_approvals.md) | Revocable session tool approvals | Planned | Orange revoke shield delivered in36, 266 package tests and native revoke pass; minor37 polish blocked by Watch guard. |
| [1051](planned/1051_chat_message_visibility_and_following.md) | Chat visibility and bottom following | Planned | Normal36 delivered; manual bottom and history-reading checks pass. Repeated voice-following refinement still awaits completed native validation. |
| [0009](planned/0009_shared_code_and_markdown_rendering.md) | # Planned: Share code and markdown rendering with abstractuic | Planned | Existing rich Markdown client work; retained in counts. |
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
| [0010](proposed/0010_interrupted_turns_invisible_to_the_model.md) | Interrupted turns are invisible to the model (runtime history replay) | Proposed | Owning package abstractruntime; promote when the history-replay contract is decided. |
| [0011](proposed/0011_token_usage_lost_upstream.md) | Token usage zeroed upstream; router calls never counted | Proposed | Owning packages abstractcore and abstractruntime; promote when either seat takes the patch. |
| [watch-apple](proposed/watch-apple/README.md) | Track: Apple Watch client (0012–0023) | Proposed | Design, mockups and prototype in `watch/apple/`. 0012 (MVP) needs nothing new from the gateway; 0013 (pairing) and 0014 (push) make it a notified client; 0015–0019 follow. Promote 0012 when the scaffold builds in CI (0018). |

## Completed Items

| ID | Item | Status | Notes |
|---|---|---|---|
| [1050](completed/1050_any_runnable_automation_workflow.md) | Any runnable automation workflow | Completed 2026-10-19 | Planned→completed; package260, final native3; typed workflow inputs, mint creation; normal33 installed, uncommitted. |
| [1049](completed/1049_speech_and_approval_orb_states.md) | Speech-processing and approval orb states | Completed 2026-10-19 | Planned→completed; native22; inspected geodesic/hand/morph screenshots; normal33 installed, user validation pending. |
| [1048](completed/1048_voice_message_review_setting.md) | Review spoken messages before sending | Completed 2026-10-19 | Planned→completed; package256, native16; default review, explicit auto-send; normal32 installed, uncommitted. |
| [1046](completed/1046_edit_and_resend_stopped_requests.md) | Edit and resend stopped requests | Completed 2026-10-19 | Planned→completed; package255, native6; inspected screenshots and normal31 installed; user validation pending, uncommitted. |
| [1047](completed/1047_explicit_automation_title.md) | Separate automation title from task | Completed 2026-10-19 | Planned→completed; explicit Gateway title, package255, native6; normal31 installed; uncommitted. |
| [1045](completed/1045_orb_animation_ci_presentation_sampling.md) | Reliable orb CI presentation checks | Completed 2026-10-19 | Full CI81/81; combined126.1 candidate verified; human upload gate waiting. |
| [1043](completed/1043_automation_run_diagnostics.md) | Automation run explanations and live results | Completed 2026-10-19 | Planned→completed; package250, native4 and physical read-only1; evidence and screenshots under1043. |
| [1044](completed/1044_iphone_version_and_updates.md) | Installed version and supported app updates | Completed 2026-10-19 | Planned→completed; package250, native4 and physical read-only1; evidence and screenshots under1043. |
| [0853](completed/0853_sessions_are_gateway_first.md) | Sessions are gateway-first: the local session index is a rebuildable cache | Completed (0.7.0, 2026-09-27) | Operator finding 2026-09-27 (purge + reinstall still listed old sessions): the list, titles and transcripts come from `~/.abstractassistant`, never the gateway, with no reconciliation. List = `/runs?root_only=true` folded by `session_id` as in AbstractCode; titles and transcripts from gateway history; local files a deletable cache; one-time migration. Prerequisite for 0852. |
| [1042](completed/1042_unified_iphone_and_watch_store_delivery.md) | Unified iPhone and Watch Store delivery | Completed 2026-10-19 | Planned→completed; full79 native, combined119.1 archive, human-approved Apple upload succeeded; operator installed through TestFlight. [Evidence](evidence/1042/apple-delivery.json). |
| [1041](completed/1041_iphone_ci_and_gated_apple_delivery.md) | iPhone CI and gated Apple delivery | Completed 2026-10-19 | Created/completed 2026-10-19; planned→completed. Automatic CI plus manual main-only human-approved ASC upload; ADR0002 and distribution guide. Contracts10/10, package246/246, native79/79; real full archive verified. First approved upload failed: no separate iPhone app record; unified product correction tracked in 1042. [Evidence](evidence/1041/README.md). |
| [1040](completed/1040_iphone_restored_image_previews.md) | iPhone restored image previews | Completed 2026-10-18 | Created/completed 2026-10-18; planned→completed. Conversation-owned shared downloads, inline decoding and retry; native 7/7, inspected cold-relaunch screenshots; normal 0.6.21 (29) installed (phone locked for launch). |
| [1039](completed/1039_iphone_stop_orb_morph_and_contrast.md) | iPhone stop orb morph and contrast | Completed 2026-10-18 | Created/completed 2026-10-18; moved planned→completed. Checkpoint 7c5d9ec, bright stop control, two-way interrupted morph; native 5/5 and inspected frames; normal 0.6.20 (28) installed/launched. |
| [1038](completed/1038_iphone_category_tool_controls_and_conversation_archiving.md) | iPhone category controls and actionable conversations | Completed 2026-10-18 | Created/completed 2026-10-18; moved planned→completed. Category Off/Auto/Approve; grouped history, compact stats/status and existing gateway archive/restore. 246 package + two native + one read-only device test passed, screenshots/adversary approved; normal 0.6.19 (27) installed/launched. iPhone only, uncommitted. [Evidence](evidence/1038/README.md). |
| [0852](completed/0852_automations_in_the_assistant.md) | Automations in the Assistant | Completed 2026-09-27, UNRELEASED | Automations v1 mission A (root 0928): gateway-fed Automations section, the automation view (chat pairs, controls, Discuss, wait answers by kind), "Schedule this conversation" with the tool-approval consent, tray notifications from a 60 s / 5 min poll, and a regular list of `chat` + `discussion`. `e3a0445`…`52d75df`; suite 967; walk 27/27 against a hermetic gateway; review 49 GO. Release: root 0941. |
| [0005](completed/0005_single_gateway_workflow_contract_cleanup.md) | Single gateway workflow contract cleanup | Completed | Removed active hybrid runtime behavior and codified the canonical managed workflow boundary. |

## Deprecated Items

No deprecated backlog items currently tracked.

## Operating Notes

- New items use four-digit global IDs.
- Gateway-related authority changes must cite [ADR 0001](../adr/0001_gateway_native_assistant_v2.md).
- When code and backlog disagree, update backlog text in the same pass.
