# 1148: iPhone: a Notes tab, the fourth icon at the bottom, to capture a note like the Watch does

**Status**: planned. Filed 2026-11-07 from the operator's ask ("a note capability on the iPhone, likely a 4th icon at
the bottom"). Not implemented.
**Governing ADR**: [ADR 0004](../../adr/0004_notes_inside_the_assistant_abstractnote_stays_a_service.md) (Notes live
inside the Assistant's apps; AbstractNote stays a service). ADR impact: none; this is the first iPhone slice of it.

## Plain description

The Watch already has Notes: write or dictate a thought, tap Save, see "Saved to Notes". The iPhone has no way to
do that. Add a fourth tab, **Notes**, after Automations, that does the same thing with the same gateway call and the
same notebook, so a note saved from the phone and one saved from the wrist end up in one place.

## What is true today (main `abstractassistant`, 2026-11-07)

- **The bottom bar has three tabs**, defined in one place, `phone/iphone/Sources/App/AbstractAssistantPhoneApp.swift:39-43`:
  `Tab("Assistant", systemImage: "sparkle", value: 0)` (ChatScreen), `Tab("Inbox", systemImage: "tray", value: 1)`
  (InboxScreen, badge), `Tab("Automations", systemImage: "clock.arrow.circlepath", value: 2)` (AutomationsScreen, badge).
  Notifications open a tab by its number (`PhoneNotifier.shared.open = { tab = $0 }`, same file :65), so the new tab
  takes value 3 and the three existing numbers do not move.
- **The Watch's capture flow** (`watch/apple/Sources/App/Notes/NotesView.swift`, added in `21d7d4f`, shipped from v0.18.1):
  `WatchNotes.save` builds one `NoteCaptureRequest` per note (kept as `pending`, so a retry reuses the same
  `idempotency_key` and never saves twice, :49-56), starts it with `client.startNoteCapture` (:65), polls `client.run(id:)`
  for up to 60 s and maps the run with `NoteCaptureOutcome` (:70-90): saved / failed with the gateway's sentence /
  waiting for approval / still saving. 404 says "AbstractNote isn't set up on this gateway", 503 "Notes are
  temporarily unavailable" (:93-97). Dictation goes through `client.transcribe` (:28-48). A draft survives leaving
  the page, never a change of gateway or account (`bind(to:)`, :19-22).
- **The endpoint** is the shared client's `startNoteCapture`: `POST api/gateway/runs/start` with
  `{bundle_id: "abstractnote", flow_id: "note-capture", session_id, input_data: {text, session_id, idempotency_key,
  occurred_at, process_inline: false, source: {client}}}`
  (`watch/apple/Packages/AbstractGatewayClient/Sources/AbstractGatewayClient/NoteCapture.swift:4-43`,
  `GatewayClient.swift:575-577`). The iPhone already links that package
  (`phone/iphone/project.yml:30-33`), so the request, the outcome mapping and the call are available as they are.
  One gap: `NoteCaptureRequest` hardcodes `source.client = "watch"` (`NoteCapture.swift:22`).
- **The notebook** is the signed-in account's: the gateway binds the note tools to the caller's plane notebook and
  stamps the account on each capture (`abstractgateway/src/abstractgateway/abstractnote_seam.py:83-102`). Signed in
  as the same account as the Watch means the same notebook; there is no notebook choice to make in the app.
- **No offline queue on the Watch yet.** Its pending note lives in memory only; a failed save keeps the text with
  "Check again" and "Discard draft". The durable queue is [1054](../proposed/watch-apple/1054_offline_capture_queue_on_the_wrist.md)
  (proposed).
- **Not capability-gated on the Watch.** The Home row "Notes" is always shown (`watch/apple/Sources/App/Home/HomeView.swift:45-47`);
  ADR 0004 asks for the `GET /api/gateway/note/status` probe.
- Live evidence that the path works: the operator's notebook holds the Watch captures of 2026-11-06 20:15, 21:20 and
  21:45 UTC (`runtime/abstractnote/note.sqlite3`, `client = watch`, per-capture sessions `note-watch-<uuid>`).

## Plan

1. **Tab.** `Tab("Notes", systemImage: "note.text", value: 3) { NotesScreen() }` after Automations, shown only when
   `GET /api/gateway/note/status` answered 200 at sign-in or launch (ADR 0004: a 404 hides the tab, asked again next
   launch, nothing remembered for a day). Same symbol as the Watch's Home row.
2. **Reuse, do not copy.** Move the Watch's `WatchNotes` save/poll/outcome logic into the shared
   `AbstractGatewayClient` package (or `AssistantKit` if it needs app state) so both apps use one implementation
   (backlog 1053's rule: converge a file when a fix touches both). Add a `client` field to `NoteCaptureRequest`
   (`"watch"` default kept, `"iphone"` from the phone) so the notebook shows where each note came from.
3. **Screen.** A multi-line text field ("Write a note…"), a Dictate button through the iPhone's existing voice path
   (`VoiceController`, `client.transcribe`), Save note, then the same receipts as the Watch: Saving… → Saved to Notes
   (with "New note") / the gateway's failure sentence with Check again and Discard draft / Waiting for approval.
   The draft survives switching tabs, never a change of gateway or account.
4. **Offline.** Match the Watch: keep the unsent note (same idempotency key) with Check again; no background queue in
   this item. When 1054's queue lands, the phone uses the same store and states.
5. **Same account and notebook as the Watch:** no notebook picker; the tab's footer says "Saves to your AbstractNote
   notebook." like the Watch.

Out: recall/search of notes on the phone, attachments and photos, location, editing saved notes, a background queue.

## Acceptance

- The bar shows four tabs, Assistant / Inbox / Automations / Notes; Notes only on a gateway whose
  `GET /api/gateway/note/status` is 200; notification taps still open Inbox (1) and Automations (2).
- A note typed on the iPhone is saved in the signed-in account's notebook with `source.client = "iphone"`, visible in
  the Note web app; a note from the Watch on the same account lands in the same notebook.
- Saving twice after a lost answer creates one note (same idempotency key; the gateway answers `duplicate`).
- 404 / 503 / failure / approval states show the Watch's sentences; a test per state against the mock client.
- Watch Notes keeps working on the shared code (its package tests and `NotesUITests` green).
- UI test of the Notes tab in the iPhone suite; one screenshot of the Notes tab on a phone screen about 400 points
  wide (the app's dark theme), nothing cut off or overlapping, attached under `docs/backlog/evidence/1148/`, checked
  before any device install.
- Adversarial review (Fable, with the screenshots) before merge; installed on the operator's iPhone from main.
