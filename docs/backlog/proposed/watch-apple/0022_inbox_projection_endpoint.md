# Proposed: Inbox projection: one feed of waits, notable results, failures and entity questions

> Created: 2026-10-16 23:10:00 +0200
> Type: improvement
> Priority: P2
> Labels: watch, gateway, attention

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractgateway (route), abstractassistant (desktop and watch)
- Track: [watch-apple](README.md) (Apple Watch client)
- Origin: cross-review of the product spec `AbstractAssistant_Apple_Watch_Product_Spec_2026-10-16.md` (another agent's notes), adopted on 2026-10-16

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: None unless a new gateway contract is added; then file the contract with the gateway seat.

## Summary
A gateway route that merges, for the caller, the runs waiting on a person, the automation
occurrences needing attention, failed runs since the last cursor, and entity questions, as
watch-sized cards with a cursor. Clients stop assembling the inbox from four lists.

## Why
Today the watch polls `runs?status=waiting`, then one detail per waiting run, then
`automations` and its attention feeds. A single projection cuts the round trips to one per poll,
which matters on cellular and for the push bridge (item 0014) that needs the same feed.

## Scope
- `GET /api/gateway/me/inbox?cursor=…` returning `{items: [{kind: wait|result|failure|question, run_id, wait_key?, title, subtitle, at, payload}], next_cursor}` built from existing stores (active-run index, automation attention, entity tasks).
- `POST /api/gateway/me/inbox/seen` with a cursor.

## Non-goals
No new storage; the projection reads what exists.

## Current code reality
- Waits on a person are found with `GET /runs?status=waiting` and the full wait block on `GET /runs/{id}` (verified live 2026-10-16: list rows carry only `waiting.reason`).
- Automation attention: `GET /automations` `attention.pending_waits`, `.../attention`, `.../seen` (abstractgateway/docs/automations.md).

## Dependencies
Agreement with the gateway seat.

## Expected outcomes
- One request per poll on the watch; the push bridge and the desktop assistant read the same feed.

## Acceptance Criteria
- [ ] The inbox route returns the same waits as `runs?status=waiting` plus detail, in one call
- [ ] Failures and automation results appear once, with a cursor that advances on `seen`
- [ ] The watch home tile and the desktop notifications read from the route

## Testing
- `cd abstractgateway && python -m pytest tests -k inbox -q`
