# 1043 — Automation run explanations and live results

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Completed
> Completed: 2026-10-19
> Priority: P1
> Labels: iphone, reliability

## Current code reality

AutomationDetailScreen renders status-only cards, drops occurrence.failure, duplicates the latest row, and requires a manual pull after Run now. The existing Gateway occurrence contract already returns failure.message/reason_code/attempts and run IDs.

## Scope and expected outcome

Decode failure and attempt metadata; provide dated, tappable run cards and a run details sheet with explanation, task, trigger and existing ledger/activity. Refresh only while this screen is visible. Investigate the existing failed remote occurrences read-only using the saved device sign-in. No new automation execution or framework/server changes.

## Validation

Regression tests for actual failure JSON, empty answers and partial metadata; native UI checks for multiple runs, details, timestamps and refresh failures. Preserve evidence without email contents or credentials.

## ADR state

Existing thin-client architecture and ADR0002/0003 delivery boundaries apply; no new durable architecture decision.

## Completion report — 2026-10-19

Delivered LastOccurrence failure/attempt/task decoding, recorded-error explanations, dated
multi-run cards and a details sheet with times, attempts, task/trigger, support ID and expandable
existing activity. The active screen refreshes every5 seconds without starting a new task.
Latest results are not repeated, blank answers get an explicit explanation and active runs
block another Run now. Provider401 remains distinct from phone authentication expiry.

Read-only physical investigation identified two actual AIRelays401 failures after3 attempts;
no email was sent and no framework/server configuration was changed. Correcting that remote
API credential remains an administrator action; the UI change does not claim to repair it.
Package250, contracts14, targeted native4 and physical read-only1 all pass; screenshots inspected.
Public troubleshooting guide and iPhone changelog updated. Evidence: ../evidence/1043/README.md.
No new ADR: existing thin-client and human-gated delivery boundaries apply. Original planned
path moved to completed with the same filename. No unrelated follow-up added.

## Post-completion hardening — 2026-10-19

Full hosted feature checks passed in the80/81 run; the unrelated orb timing assertion is
tracked by1045. Retry runs are now grouped and refreshed by occurrence index even when the
attempt run ID changes. If a row has left the20-run history page, terminal root state still
updates its detail snapshot. The modal uses explicit Refresh details; automatic polling belongs
to the automation’s main page. New identity regression makes package total251.
