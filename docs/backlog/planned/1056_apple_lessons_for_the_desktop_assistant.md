# 1056 — What the iPhone and watch taught us, brought to the desktop assistant

> Package: abstractassistant
> Type: task
> Created: 2026-10-26
> Status: Planned
> Completed: N/A
> Priority: P1
> Labels: desktop, qt, usability, voice, approvals, reliability, cross-platform

## Current code reality

In October 2026 the iPhone and watch apps (1038–1054) got behaviour the Qt desktop app
(PyQt5, `pyproject.toml:47`; macOS, Linux and Windows) does not have. Every claim below was
checked in the code on both sides. The gap analysis, with file:line evidence for each claim,
is `untracked/apple-web-wave/w2-apple-to-desktop.md`.

- **A send that fails is half lost.** If the gateway cannot be reached while attachments upload,
  the exception escapes the `start_run` guard (`ui/gateway_worker.py:1151`, guard `:1194-1219`)
  and reaches `_on_worker_error` (`app.py:9537`). That handler says "The run failed", leaves the
  optimistic user turn in place, and never refills the composer (only `run_start_failed`,
  `app.py:9194-9238`, does). A failed hold-to-talk transcription drops the recording, which only
  ever existed as a local array (`core/gateway_voice_manager.py:549-571`, `app.py:10496`).
- **Voice always sends.** Hold-to-talk calls `_submit()` as soon as the words come back
  (`app.py:10486-10494`). `voice_auto_send` (default True, `preferences.py:334`) only affects the
  hands-free conversation (`app.py:10589`).
- **"Needs you" is a sentence, not a door.** The wait banner has no action
  (`app.py:7986-8004`). A deferred approval only comes back when the window is reopened
  (`app.py:8072-8090`). The cross-conversation banner's Open goes to the first waiting
  conversation only (`app.py:6849-6870`). Clicking a notification does nothing: there is no
  `messageClicked` handler (`app.py:11554-11580`).
- **No edit and resend.** A stopped run ends as "Run stopped." (`app.py:9617-9622`). A user
  message offers Copy only.
- **Past answers cannot reopen their activity.** The footer shows tokens, tools, files and
  duration, but no cycles (`app.py:2032-2115`). The activity dialog is fed only by the live run's
  model (`app.py:7799-7811`, `:8538`). This is item 0 of the overview ("steps chip").
- **No archive.** The session row says the gateway has no way to remove a session
  (`ui/session_switcher.py:410-411`). It has one: `POST /sessions/{id}/archive|unarchive` (gateway
  `routes/session_archive.py:106,119`). The iPhone already uses it.
- **The tray has no voice-capture states.** `_tray_feedback_state` returns speaking, waiting,
  busy, complete or idle (`app.py:11431-11446`). There is no listening state, and no
  transcribing or preparing-speech state.
- **Automations run only Assistant workflows, with no input form.** The picker is filtered to
  `executable_for=abstractassistant.agent.v1` (`ui/automations.py:195-202`). A workflow that
  needs inputs is refused with "configure … from that workflow's input form"
  (`core/automations.py:1231-1244`), and the desktop has no such form.

## Scope and expected outcome

The order is user value over effort. Every row is Qt-level work that runs on all three
desktops unless its portability cell says otherwise. Sizes: S ≤ 1 day, M 2–4 days, L more.

| # | Change | Size | Portability | Touches | Depends on |
|---|---|---|---|---|---|
| 1 | A send that does not start always gets its words back: an attachment upload failure is reported as "Not sent — <reason>" (not "The run failed"), the optimistic turn is removed, and the text and attachments return to the composer | S | portable | `GatewayWorker.run`/`_upload_attachments`, `AssistantPalette._on_worker_error`, `_on_worker_event` (`run_start_failed` branch) | nothing new |
| 2 | Keep the recording of a failed hold-to-talk transcription: "Not sent." with Retry (same audio) and Discard; nothing resends by itself (watch 1054 slice 0) | S | portable | `GatewayVoiceManager.end_hold`, `AssistantPalette._on_hold_transcription_failed`, composer status row | nothing new |
| 3 | "Needs you" becomes clickable: a **Review** action on the wait banner reopens the approval sheet or the question; clicking a notification opens that conversation's wait | S | banner portable; notification click needs a per-platform branch (notifications: `QSystemTrayIcon.messageClicked` behaves differently on macOS, Windows and Linux daemons) | `_refresh_wait_notice`, `_open_approval_sheet`, `_open_ask_dialog`, `_notify`, `_open_attention` | nothing new |
| 4 | Edit and resend a confirmed stopped request: the original text and attachments open in the composer (or a small editor) and are sent only on Send; history is unchanged (iPhone 1046) | M | portable | `MessageCard` user actions, `_on_worker_finished`, `_pending_submission`, history seed of cancelled turns | check that the history bundle projects cancelled turns (see 0010) |
| 5 | Voice review before sending: a "Send what you say automatically" setting also governs hold-to-talk; when it is off, the words land in the composer after any typed draft and Return sends them (iPhone 1048). The default is the operator's call | S | portable | `_on_hold_transcription`, `VoicePage.voice_auto_send` (`ui/settings/pages.py:789-791`), `preferences.py` | operator decision on the default |
| 6 | An Inbox panel: every question and approval across conversations, with Approve / Deny / Approve all / answer inline (the run is re-read before answering), then recent activity; the attention banner's Open lands there | M | portable | new `ui/inbox.py`; `AttentionModel.waits`, `GatewayClient.list_runs(status="waiting")`, `submit_wait_response`, `ToolApprovalSheet` reuse | nothing new (`GET /runs?status=waiting` already used by the iPhone) |
| 7 | A past answer reopens its activity: a cycles chip in the footer replays the run's ledger through `GatewayEventAdapter` into a `RunActivityModel` and opens `RunActivityDialog` (closes item 0 "steps chip") | M | portable | `_assistant_footer_metrics`, `MessageCard`, `RunActivityDialog`, `ui/activity.py`, `gateway/tool_usage.py` | `history_bundle` / `ledger` routes already exist |
| 8 | Archive and restore a conversation from the switcher (not while it runs), plus an Archived list with Restore (iPhone 1038) | M | portable | `ui/session_switcher.py` (`SessionRow`), `core/gateway_sessions.py`, new `GatewayClient.archive_session/unarchive_session/list_archived_runs` | gateway routes exist |
| 9 | Tray voice states: listening (microphone level) and preparing (transcribing, or synthesizing before the first audio); approval keeps its still amber badge | S | per-platform branch: tray (frame cost, `app.py:217-221`) | `_tray_feedback_state`, `_tray_feedback_icon`, `_refresh_tray_feedback` tooltips | nothing new |
| 10 | CI on all three desktops: run `tests/basic` offscreen on macOS and Windows as well as Ubuntu, keep the offscreen screenshots of the windows a change touches as CI artifacts, and give each UI item an evidence folder under `docs/backlog/evidence/<id>/` as the Apple track does | M | portable (CI only) | `.github/workflows/ci.yml`, tests that already `grab()` | none |
| 11 | Automations accept any runnable workflow and get a typed input form (booleans, choices, JSON), pinned to the exact version (iPhone 1050) | M | portable | `AutomationWorkflowCombo`, `ScheduleSheet`, `prepare_workflow_input`, `controller.workflow_menu` | operator decision: `gateway_service.py:572-574` records the 2026-10-01 rule that the gateway, not the client, decides the list |
| 12 | Share a conversation as Markdown (copy, or save to a file, with its attachments next to it) | S | portable | new export helper beside `core/session_digest.py`; header menu | nothing new |
| 13 | Version and updates: Settings → About shows the install channel (editable checkout, pip/pipx, app bundle) and offers an explicit update check | S | portable | `AboutPage` (`ui/settings/pages.py:2276`), `_version.py` | where to read the latest version from (PyPI, or a gateway field that does not exist yet) |
| 14 | Tool categories get Off next to All auto / All ask, and "Mixed" when the tools differ (iPhone 1038) | S | portable | `_ToolGroup` in `ToolsPage` (`ui/settings/pages.py:1345-1392`) | nothing new |
| 15 | Accessible names on the icon-only controls (send/stop, copy, read aloud, attach, microphone), and a reduced-motion switch that freezes the busy and speaking animations | M | names portable; reading the system's reduced-motion setting needs a per-platform branch (macOS, Windows and GNOME each have their own) | `MessageCard`, the composer, `_refresh_tray_feedback`, `voice_strip.py`, `activity.py` | nothing new |
| 16 | Sign in with an emailed code, and keep several gateway sign-ins for one-click switching | M | portable | `ConnectionPage` (`ui/settings/pages.py:147-209`), `GatewayClient`, `preferences.py` | gateway `session/recovery/*` exists |
| 17 | Email and web source counts on an answer (messages read and sent, searches, pages fetched) | M | portable | `_assistant_footer_metrics`, `core/file_activity.py` | nothing new |
| 18 | A conversation files browser (workspace plus attachments) | M | portable | new dialog; `get_run_workspace`, `download_run_workspace_file`, `list_run_artifacts` | nothing new |
| 19 | Who answers: the Assistant or an entity | L | portable | header, `controller`, `GatewayClient` | entity session contract |
| 20 | Read-aloud speed (1×, 1.15×, 1.3×, 1.5×) | M | per-platform branch: audio (pitch-preserving time stretch before `NonBlockingAudioPlayer`) | `GatewayVoiceManager.speak` (`speed` is ignored, `:1105`) | nothing new |

Copied directly from the Apple apps: the words (statuses, "Not sent.", "Approval needed", "A
question for you", "Edit and resend", the Off/Auto/Approve labels), the order of the states,
the rule that a run is re-read before a wait is answered, and the order of the Inbox. The raised
hand of `OrbWeave.swift` and the geodesic of `Design.swift` can be redrawn with `QPainterPath`
for a tray badge. The layout, navigation and gestures are designed again for a menu-bar palette.

## Non-goals

- **Nothing that exists only on Apple platforms.** Apple push and its notification extensions,
  the Keychain and Data Protection, WatchConnectivity sign-in handover, haptics, complications and
  the Smart Stack, StoreKit/TestFlight channels and the App Store delivery pipeline are out of
  scope. The desktop must stay portable across macOS, Linux and Windows; work that would only
  exist on macOS ranks last or is left out.
- The watch's 34 orb styles and avatars. They are a product choice for the wrist.
- No gateway, runtime or framework change in this item. Rows that need one name the dependency
  and wait for it.
- No change to the desktop's own strengths: streaming replies, steering, pause/resume, model
  overrides, calendar schedules, workspaces, the hands-free voice conversation, themes, and the
  global hotkey.

## Validation

For each row: offscreen tests that fail when the change is reverted (mutation-checked, as the
2026-09 desktop waves did), screenshots of the windows it touches, kept under
`docs/backlog/evidence/1056/`, and a rebuilt macOS app checked against the source. Rows 1–3 also
need one Linux and one Windows smoke run once row 10 exists.

## ADR state

[ADR 0001](../../adr/0001_gateway_native_assistant_v2.md) applies: the gateway stays the
authority, and the desktop stays a reader of runs, waits and sessions. No new ADR is needed. A
host change (for example a rewrite) would be a separate ADR, and this list is the behaviour that
host would have to keep.
