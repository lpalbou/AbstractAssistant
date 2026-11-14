# 1218 — Correlate a manual automation command with its exact run

> Package: AbstractAssistant, AbstractGateway
> Created: 2026-11-14
> Status: Proposed
> Source: independent review of recovery item 1217

## Problem and code reality

Run now reads a fresh run-index baseline before submitting the command. A scheduled run can
still start between those requests; its newer index does not prove it belongs to that command.
The Gateway command has an identity, but the app's result DTO does not expose an exact
command-to-run receipt. Do not claim exact correlation from the index heuristic.

## Proposed outcome

Expose and consume a durable manual-command/run relationship, including delayed starts and
reconnect. Keep errors and the no-start timeout explicit. Specify behavior on older gateways.

Also assess the pre-existing followed-run history retention: prune completed old live entries
without losing an answer, and preserve chronology when the server's limited history drops an
older followed row. Do not let an appended old row become the apparent latest result.

## Validation

Exercise a scheduled/manual race, reconnect before the manual run starts, missing/late command
receipts, a full history window, and arrival of a full answer after an excerpt.

This is outside the accepted recovery scope; original worktrees remain preserved.
