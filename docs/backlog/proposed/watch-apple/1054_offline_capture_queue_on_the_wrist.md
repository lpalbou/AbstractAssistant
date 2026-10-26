# Proposed: Offline note queue on the wrist: record now, send when the network returns

> Created: 2026-10-26
> Type: feature
> Priority: P2
> Labels: watch, voice, offline, notes, reliability

## Metadata
- Created: 2026-10-26 (rewritten the same day after an adversarial review)
- Status: Proposed
- Completed: N/A
- Owning packages: abstractassistant (watch client); abstractnote's `note-capture` flow is the target (no gateway change)
- Track: [watch-apple](README.md)
- Origin: the operator's ask of 2026-10-26, from the Watch deck's "connection truth" point; [0020](0020_meeting_capture_on_the_wrist.md) (meetings) reuses this queue's store, one meeting being one item holding chunks

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md), [ADR 0004](../../../adr/0004_notes_inside_the_assistant_abstractnote_stays_a_service.md)
- ADR impact: None

## Summary
A note recorded on the watch is kept on the watch until the gateway has received it, and sent on
its own when a usable connection returns, with the truth on screen at every step: saved on the
watch, sending, received, organizing, organized. Leaving the screen, locking the watch or losing
the phone never loses the recording. Questions are not queued: a question asked offline keeps its
recording with Retry and Discard on the orb, and is sent when the person retries.

## Why
The watch records only while connected: `transcribeAndSend` (`watch/apple/Sources/App/Ask/AskView.swift`)
posts the WAV at once and a failed upload discards it; `Listener` overwrites `tmp/ask.wav` on the
next recording. "No phone nearby" is not "offline" (the watch reaches the gateway over Wi-Fi or
cellular), and "offline" must not mean "lost". A note product on the wrist is only as good as its
worst connection. A question is different: a run started hours later, with the answer arriving
when the person has moved on, surprises more than it helps, so it waits for a deliberate retry.

## Scope
- **Slice 0, independent of Notes:** a failed question upload keeps its WAV and shows Retry and
  Discard on the orb; a new recording no longer overwrites a kept one. Ships alone.
- **The note queue:** items (client uuid, recording time, bytes on disk, state, last error) in a
  store that survives restarts, bounded by size and count; the oldest is evicted only after it
  was received. States and their words: *Saved on the watch* → *Sending* → *Received* →
  *Organizing* → *Organized* (the last two from `GET /api/gateway/note/status` and the note's
  processing state). A failure keeps the item with its reason and a retry; nothing silent.
- **Sending:** one item at a time, from the app in front and from the existing background
  refresh (`AnswerNotifier.checkWaits`, which already has the credential), on the default
  `URLSession`: a 60-second recording is about 1.9 MB and fits a refresh. No background upload
  session in the first version.
- **Exactly once:** `note-capture` takes `idempotency_key` (the item's uuid) and derives the note
  id from it (`abstractnote/docs/api.md`, `data-model.md`), so a retried start creates no second
  note; the upload is content-addressed. `occurred_at` carries the recording time, so a note made
  in a tunnel is filed when it was spoken, not when it was sent.
- **A queue row on the Notes surface** listing what has not been received yet.

## Progress — 2026-10-26
Slice 0 shipped on main (commit 25b849e): a question whose upload or transcription fails keeps its
recording in its own file (`KeptQuestion`, out of backups), "Not sent." with Retry and Discard under
the orb, offered again after leaving the page or relaunching; Retry sends the same recording and
success deletes it; `--test-fail-send` and `KeptQuestionUITests` (the relaunch assertion fails when
the keep is broken). The note queue itself waits for the Notes surface.

## Non-goals
No transcription on the watch. No queued questions or decisions (0012's stale-approval rule
stands). No recording longer than one note (meetings are 0020). No upload through the phone.

## Current code reality
- `AskView.transcribeAndSend` discards the WAV on failure; `Listener` records to one temporary file.
- `AnswerNotifier.session` is a background session used for download tasks (the answer stream);
  a background upload would need `uploadTask(fromFile:)` and a wake to chain the run start, which
  is why the first version uses the refresh instead.
- Attachments upload through `POST /api/gateway/attachments/upload` (25 MB cap, content-addressed
  artifact id); the gateway's `runs/start` has no idempotency key of its own, `note-capture` has.
- No Notes surface exists yet in this repository (ADR 0004).

## Dependencies
- The Notes surface of ADR 0004 for everything but slice 0.

## Expected outcomes
- A note recorded in a tunnel is on the gateway before the person looks again, with no action
  from them, filed at the time it was spoken, and the watch shows when it arrived.
- Killing the app or restarting the watch between recording and sending loses nothing.

## Acceptance Criteria
- [ ] Slice 0: a failed question upload offers Retry and Discard; a new recording does not
      overwrite the kept one
- [ ] Airplane mode on: record a note; *Saved on the watch*; airplane mode off: *Received* with
      no tap, from the foreground and from a background refresh
- [ ] Force-quit between record and send: the item is still queued after relaunch
- [ ] A network loss mid-send, then a retry: exactly one note on the gateway, with the recording
      time as `occurred_at`
- [ ] The queue refuses a new recording only when full, and says so

## Testing
- `cd watch/apple && scripts/test-watch.sh light CaptureQueueUITests` (new, the mock's connection
  toggled by a launch hook)
- A physical-watch run of the airplane-mode case, recorded in this item
