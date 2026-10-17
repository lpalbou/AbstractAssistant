# Proposed: Meeting capture on the wrist: chunked resumable upload, finalize, meeting workflow

> Created: 2026-10-16 23:10:00 +0200
> Type: feature
> Priority: P2
> Labels: watch, voice, gateway, meetings

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractgateway (meetings contract), abstractassistant (watch client), abstractflow (meeting workflow)
- Track: [watch-apple](README.md) (Apple Watch client)
- Origin: cross-review of the product spec `AbstractAssistant_Apple_Watch_Product_Spec_2026-10-16.md` (another agent's notes), adopted on 2026-10-16

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: None unless a new gateway contract is added; then file the contract with the gateway seat.

## Summary
One-tap meeting recording with the watch microphone: audio is buffered locally in a bounded,
recoverable queue, uploaded in ordered chunks with acknowledgements, finalized with a durable
intent, transcribed on the gateway (diarization where available, gaps marked explicitly), and
handed to a workflow that produces a source-linked summary, decisions and candidate actions,
proposed for review before anything is assigned or sent.

## Why
The cross-review spec names this the flagship experience: capture an experience on one device,
situate it in earlier context, and turn it into reviewed work. Today the gateway has a one-off
transcription route per run, no chunked ingestion and no finalize marker, so the client cannot
build it honestly on existing contracts.

## Scope
- Gateway: `POST /meetings` (id, upload policy), `PUT /meetings/{id}/chunks/{seq}` (idempotent, checksum, ack), `POST /meetings/{id}/finalize`, `GET /meetings/{id}` (recording / received / transcribing / ready / error, gaps), artifacts linked to the session.
- Watch: `AVAudioEngine` capture under the supported background audio session, local queue with sequence numbers, opportunistic upload, visible recording and upload states, "upload pending" never shown as "meeting complete".
- Workflow: a shipped `meeting-digest` flow (transcript → summary, decisions, candidate commitments, people, links to prior memory) whose outputs are proposals; sends and assignments wait for approval.

## Non-goals
No always-on recording, no cross-meeting speaker identification, no AirPods-as-microphone for other participants, no automatic calendar writes.

## Current code reality
- STT exists only as `POST /runs/{id}/audio/transcribe` on an uploaded artifact and `/v1/audio/transcriptions` (abstractgateway/docs/api.md §audio); uploads are capped at 25 MB per attachment (api.md §attachments).
- No meeting or chunk route exists; no `meeting-finalized` trigger source (automations.md §trigger sources).
- The watch SDK supports background audio sessions and `AVAudioRecorder`; long sessions must be measured on the Series 11 (spec C-05).

## Dependencies
Items 0013 (device tokens), 0014 (push for "ready"), a gateway contract agreed with the gateway seat.

## Expected outcomes
- A 30-minute meeting recorded on the wrist arrives complete on the gateway after a network loss, with no duplicated or lost chunk, and produces a reviewed digest with time-coded sources.

## Acceptance Criteria
- [ ] Chunks survive a network loss and an app restart; the gateway reports exactly one copy of each sequence
- [ ] Finalize is refused while acknowledged chunks are missing unless gaps are declared; the transcript marks gaps
- [ ] The digest's claims link to time ranges in the audio artifact
- [ ] Proposed actions are stored as proposals; sending or assigning waits for approval

## Testing
- `cd abstractgateway && python -m pytest tests -k meetings -q`
- `cd watch/apple && ./scripts/build.sh --screen record`
