# 1046 — Edit and resend stopped requests

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Completed
> Completed: 2026-10-19
> Priority: P1
> Labels: iphone, usability

## Current code reality

Stopping returns to ready but the prompt has no edit/retry action; live user messages do not retain their run ID. Reopened cancelled runs do not mark their prompt as stopped.

## Scope and expected outcome

Retain original request text/attachments and associate prompts with confirmed cancellations. Add a scoped editor with Cancel/Send and removable attachments. Resending uses the normal start path without changing recorded history or sending automatically. Cover reload, cancellation races and active-run guards.

## Validation

Run meaningful Foundation regressions and targeted native UI flows; inspect retained screenshots. Install a normal development build on the physical iPhone. No Git commit/push or Store upload until user validation. No Framework changes.

## ADR state

Existing thin-client and delivery ADRs apply; this changes presentation and request construction, not durable architecture policy.

## Completion report — 2026-10-19

Delivered a visible Edit and resend action below confirmed stopped user prompts. The modal
preserves the original request text and removable source attachments, keeps a separate composer
draft untouched, and starts a new turn only after Send. Live and reloaded cancellation states
remain editable, including partial answers. Resends recheck session/context, provenance and
readiness. Completion-before-cancellation and uncertain stops do not become confirmed cancelled
prompts. Updated ConversationMessage, AssistantStore and ChatScreen; Gateway history is preserved.
Foundation255/255 and native6/6 pass. Retained screenshots visually inspected; README,
architecture and native changelog updated. Normal0.6.22(31) installed and launched on the
physical iPhone. Evidence: ../evidence/1046/README.md. No new architecture rule; existing
thin-client boundaries apply. No residual implementation issue found; actual user validation
is pending. These changes remain uncommitted/unpushed; no Store upload.
