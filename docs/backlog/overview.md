# Backlog Overview

AbstractAssistant is in the middle of a gateway-native desktop redesign. The active goal is to
finish the v2 tray and palette shell while keeping Gateway as the authority for workflow launch,
multimodal defaults, and durable execution. The runtime contract is now a single published gateway
workflow, not a hybrid of workflow, private-bundle, and direct-chat paths.

## Current Counts

- Planned: 12
- Proposed: 22
- Completed: 18

Counts recomputed from disk on 2026-10-26 after adding 1053 (shared Swift client kit) and 1054 (offline capture queue), from the fusion decision of ADR 0004 (topic tracks included). Planned +1 the same day for 1056 (Apple lessons for the desktop). Planned +1 for 1055 (sign and notarize the macOS app, ADR 0006). Planned +1 for 1057 (the Assistant on the web, ADR 0007). Proposed +1 for 1059 (alert levels; recounted from disk 2026-10-26: planned 12, proposed 21, completed 16). Completed +2 on 2026-10-27 for 1060 (desktop voice library) and 1061 (iPhone and watch voice library), both under the framework release wave 1055 (recounted from disk: planned 12, proposed 21, completed 18). Proposed +1 on 2026-10-27 for 1062 (iPhone and watch chat trust through the gateway's session tool policy).
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
| [1057](planned/1057_web_assistant.md) | The Assistant on the web | Planned | Scaffold in `web/` (Vite + React + TypeScript on the abstractuic app-server; host interface for the browser now and a Tauri shell later; session fold, run input, turn reducer ported from the desktop with parity tests; 58 tests, build green; read-only live proofs). Next: operator decision on ADR 0007, live send/approval proof, gateway catalog row (G1), npm publish. |
| [1055](planned/1055_macos_signing_and_notarization.md) | Sign and notarize the macOS app | Planned | Signing, notarization and disk image wired off by default (`build-macos-app --sign/--notarize/--dmg`, bundle id `ai.abstractframework.assistant.mac`, ADR 0006 Proposed); operator: ADR decisions, Developer ID certificate and notary key (docs/macos-signing.md); then a first notarized build and CI. |
| [1056](planned/1056_apple_lessons_for_the_desktop_assistant.md) | What the iPhone and watch taught us, brought to the desktop assistant | Planned | 21 changes ranked for the Qt desktop on all three platforms, each marked portable or per-platform: "needs you" you can click, edit and resend, voice review, an Inbox, past answers reopening their activity (overview item 0), an archive action, CI on all three desktops, the orb and tokens on the Qt palette (ADR 0008). Apple-only features are out of scope. Rows 1-2 shipped 2026-10-26, uncommitted: a send that fails keeps its words and files, and a failed transcription keeps its recording with Retry/Discard. |
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
| [1062](proposed/1062_iphone_and_watch_chat_trust_through_the_session_tool_policy.md) | iPhone and watch: "Approve all" through the gateway's session tool policy | Proposed | The desktop moved in `feat/session-tool-policy`; `AssistantStore.approveAll` / `applyConversationTrust` still answer each wait after it arrived (the gate flashes). Promote when the gateway and runtime `feat/session-tool-policy` are released. |
| [1059](proposed/1059_alert_levels_honoured_and_chosen_per_alert.md) | Alert levels: the apps honour the gateway's (results and "Notify me" arrive silent today), and an alert can choose its own | Proposed | Promote step 1 (apps render the gateway's `active` instead of `passive`) when the operator asks; step 2 (a level per alert) needs the gateway and flow seats. |
| [1058](proposed/1058_assistant_in_the_shell.md) | The assistant in the shell: `assistant "find me file X"` | Proposed | `assistant run --prompt` exists; the bare-prompt form, a conversation loop, session choice and `--file` are the gap (operator ask 2026-10-26). Promote once the operator confirms the shape. |
| [1053](proposed/1053_shared_swift_client_kit_for_apple_clients.md) | Shared Swift between the two Apple apps: one gateway client module, an honest credential file | Proposed | Steps 1-2 shipped 2026-10-26 (protected file, one module name; 24f47c9); step 3 converges files only when a fix touches both; ADR 0004, ADR 0005. |
| [1054](proposed/watch-apple/1054_offline_capture_queue_on_the_wrist.md) | Offline note queue on the wrist | Proposed | Slice 0 shipped 2026-10-26 (25b849e); the note queue waits for the Notes surface of ADR 0004. |
| [0001](proposed/0001_gateway_capability_profile_alignment.md) | Gateway capability profile alignment | Proposed | Keep as background design memory while v2 rollout lands. |
| [0003](proposed/0003_tauri_shell_spike.md) | Tauri shell spike | Proposed | Promote only if cross-platform host evidence outweighs Qt-first delivery. |
| [0007](proposed/0007_frozen_macos_bundle_parity_and_packaging_trim.md) | Frozen macOS bundle parity and packaging trim | Proposed | Promote if bundle breadth, warnings, or frozen-app-only regressions keep recurring. |
| [0010](proposed/0010_interrupted_turns_invisible_to_the_model.md) | Interrupted turns are invisible to the model (runtime history replay) | Proposed | Owning package abstractruntime; promote when the history-replay contract is decided. |
| [0011](proposed/0011_token_usage_lost_upstream.md) | Token usage zeroed upstream; router calls never counted | Proposed | Owning packages abstractcore and abstractruntime; promote when either seat takes the patch. |
| [watch-apple](proposed/watch-apple/README.md) | Track: Apple Watch client (0012–0023) | Proposed | Design, mockups and prototype in `watch/apple/`. 0012 (MVP) needs nothing new from the gateway; 0013 (pairing) and 0014 (push) make it a notified client; 0015–0019 follow. Promote 0012 when the scaffold builds in CI (0018). |

## Completed Items

| ID | Item | Status | Notes |
|---|---|---|---|
| [1061](completed/1061_iphone_and_watch_voice_library.md) | iPhone and Apple Watch: the gateway's voice library in Voice settings | Completed 2026-10-27 | Created/completed on branch `feat/voice-library-ios` (not pushed); grouped voices with their language, language filter, Create a voice (description, recording), rename/delete own voices; watch lists and filters. Packages 174 + 205, both apps build, native UI tests and mutation checks; root [1055](../../../docs/backlog/planned/1055_release_wave_2026_10_27_voice_library_replay_memory.md). |
| [1060](completed/1060_desktop_voice_library.md) | Desktop: the gateway's voice library (create a voice, grouped voices) | Completed 2026-10-27 | Created/completed on branch `feat/voice-library` (not pushed); 6333af4 after adversarial review, 13 tests red before each fix; root [1055](../../../docs/backlog/planned/1055_release_wave_2026_10_27_voice_library_replay_memory.md). |
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
