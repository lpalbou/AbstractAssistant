# 1047 — Separate automation title from task

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Completed
> Completed: 2026-10-19
> Priority: P1
> Labels: iphone, usability

## Current code reality

The Gateway accepts title separately; NewAutomation derives it from the task first line and the creation form exposes only the task.

## Scope and expected outcome

Add a Title field above task, transmit an explicitly entered title with existing fallback for clients leaving it blank. Include title in creation retry identity so edits cannot resend stale requests. Preserve task, workflow, schedule and permissions.

## Validation

Run meaningful Foundation regressions and targeted native UI flows; inspect retained screenshots. Install a normal development build on the physical iPhone. No Git commit/push or Store upload until user validation. No Framework changes.

## ADR state

Existing thin-client and delivery ADRs apply; this changes presentation and request construction, not durable architecture policy.

## Completion report — 2026-10-19

The New automation form now requires Title plus separate task instructions. Titles are limited
to120 characters and stored in the Gateway's existing title field; the complete task remains
in target.input_data.prompt. NewAutomation retains the task-derived name for older callers
that omit a title. Title edits invalidate an existing pending creation receipt so retry cannot
reuse a stale name. Updated NewAutomationScreen, request model, native creation fixtures and
contract tests. Foundation255/255 and native6/6 pass, including independent title/task values,
custom and inherited tool grants and growing history budgets. Screenshots visually inspected.
Public README, architecture and changelog updated. Normal0.6.22(31) installed and launched
on the physical iPhone. Evidence: ../evidence/1047/README.md. Existing Gateway contract used;
no Framework changes or new ADR needed. No new residual implementation risk; user validation
pending. No Git commit/push or Store deployment.
