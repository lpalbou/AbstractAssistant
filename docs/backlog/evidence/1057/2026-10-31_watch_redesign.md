# 1057 — Watch-inspired web Assistant, 2026-10-31

The operator requested a full web redesign following the Apple Watch Assistant,
using AbstractUIC, and asked why a structured-output streaming notice appeared
as a separate reply.

## Decision and current evidence

Decision question: how to bring the Watch's voice interaction to the browser
while retaining one implementation of authentication, runs, approvals and audio?

Inspected the Watch's `AskView.swift` and `OrbStylePicker.swift`, the web app's
`Workspace.tsx`, and the installed AbstractUIC 0.9.6 / panel-chat 0.6.4 components.
`ActivityAvatar` and its shared Rust/Wasm geometry, microphone controls, voice
hook, workflow controller and panel system already exist. No new dependency,
model, service or shared-package release is needed.

| Alternative | Ownership and migration | User result | Operational cost / reversibility |
|---|---|---|---|
| Restyle existing cards | No boundary change; smallest patch | Retains a chat dashboard rather than the Watch interaction | Low cost, easy rollback, insufficient for the request |
| Port Watch UI and audio into a bespoke web implementation | App owns a second rendering/audio/controller stack | Maximum layout freedom | Duplicates permissions, capture and cancellation; expensive to maintain |
| Compose the existing AbstractUIC controls with a Watch-inspired layout | App owns presentation and Gateway transport; kit owns interaction mechanics | Orb-led voice, readable conversation, shared settings and approvals | Selected: no new runtime services; reversible app changes |

Execution mode: primary-agent architecture and UX review; no delegation requested.
Verdict: Recommend the shared composition. A missing required shared control or a
failed lifecycle test would change that recommendation.

## Streaming notice

`panel-chat/src/workflow_runtime.ts` adds an informational `stream-unavailable:*`
message when `llm.delta_end` reports `reason: unavailable`. For
`detail: structured_output` it describes a call that returns a complete structured
result rather than streamed text. This is a call diagnostic, not an Assistant
answer or necessarily a statement about every call in the workflow.

The app partitions only these identified informational messages into Details.
It preserves every other message, including failures, missing history and warnings.
Usage/timing use the kit's original stat controls when Details is open. Streaming
transport and run inputs remain unchanged.

## Implementation and ownership

- Voice stage: shared procedural avatar, Watch palette, real microphone level,
  gaze tracking, seven activity states, tap/hold recording, playback pause/resume,
  Stop and keyboard access. State follows Gateway evidence and the audio hook;
  there are no invented progress percentages or additional inference requests.
- Avatar picker: shared catalog, immediate selection, preview states, red error
  crosses for the robot, animation preference and system reduced motion.
- Conversation: grouped/searchable sidebar, narrower readable cards, optional
  technical details, persistent composer, shared attachments and approvals.
- Ownership: choosing a conversation or New remounts the conversation owner and
  stops recording/playback. A late send result cannot reopen a departed owner.
  Every send stops previous speech immediately, including a failed send. Only a
  completed reply to a run started by this mounted owner may auto-read, using the
  existing `VoiceClientPreferences.read_aloud` preference. Opening history is silent.
- Fixed a second presentation defect: replay-view answers are identified by their
  run identity, preventing a false “ended without a written reply” below a visible
  answer. Avatar waiting state uses the actual interaction, not stale list state.
- Preferences store only appearance/animation locally. Entity identity and future
  shared voice/appearance settings remain Gateway concerns; no identity schema is
  introduced here. Authentication, CSRF, Gateway tool policy and Markdown image
  restrictions remain supplied by the existing components.

## Validation

- 62 unit tests pass; TypeScript/Vite build and relative-URL check pass.
- Built-app layout checks pass at 420, 760, 1024 and 1280 px, both themes, using
  both replay-view and legacy ledger transports. Checks cover overflow, touch
  targets, history recovery labels, conversation selection and Voice settings.
- Built-app interaction checks use Chromium's virtual microphone and silent WAVs:
  dictation reaches the draft without sending; a new reply auto-reads once;
  pause/resume reuse audio; failed sends retain drafts and stop old audio; New
  stops speech; avatar selection persists and all state controls are reachable;
  Escape closes settings and restores focus; reduced motion stops animation;
  the phone composer remains visible and conversation search works.
  The phone approval card is visible, Decide later sends no command, and Review
  restores the same pending request without granting authority.
- Browser checks report zero JavaScript errors. Both scripts run in web CI.
- Directly inspected desktop, phone, conversation and avatar-preview screenshots.
  Entry, empty, history, voice happy path, failed send, responsive and keyboard
  recovery and pending-approval states were exercised. No real approval or
  inference was issued here.

UX verdict: approved for this conversation/voice redesign. Physical microphone,
real Gateway speech synthesis and full Watch feature parity (hands-free turn,
Inbox, Automations, richer media) remain the separately tracked rollout work.

Review mode and reviewers: primary agent, using first-time, regular and technical
user perspectives; no subagents. No delegation contract applied to this request.
First-time walkthrough: the orb offers talk and the pencil offers typing, with
review before sending. Regular-user walkthrough: search, history, pause/resume,
New and failure recovery work without hidden audio. Technical walkthrough:
Details retains diagnostics and usage, and deferring an approval sends nothing.
All three perspectives approve this scope. Physical audio remains unverified.

Local activation: installed the verified private archive's built frontend under
the running Gateway app, with a rollback copy and atomic shell replacement.
The server files are identical, so no server or Gateway restart was needed.
The signed-in handover, mounted assets and existing conversation history were
checked again against the actual `/apps/assistant-web/` deployment.
