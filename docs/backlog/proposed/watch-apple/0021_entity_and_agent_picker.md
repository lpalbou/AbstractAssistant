# Proposed: Entity and agent picker: talk to a named entity or a chosen workflow from the wrist

> Created: 2026-10-16 23:10:00 +0200
> Type: feature
> Priority: P2
> Labels: watch, entity, workflows

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractassistant (watch client)
- Track: [watch-apple](README.md) (Apple Watch client)
- Origin: cross-review of the product spec `AbstractAssistant_Apple_Watch_Product_Spec_2026-10-16.md` (another agent's notes), adopted on 2026-10-16

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: None unless a new gateway contract is added; then file the contract with the gateway seat.

## Summary
Status note (2026-10-16): the picker and the entity conversation path are built in the 0012
scaffold (`ResponderPickerView`, `AppModel.entityTurn`). This item keeps the remaining scope: the
entity's card line and open questions, visits through the durable `visit` routes, and the
per-device memory of the last choice across reinstalls.

Let the Ask screen choose who answers: the gateway's default assistant workflow (today's
behaviour), another published workflow that declares the agent interface, or a summoned entity
(`GET /api/gateway/entities`, a visit). The choice is per conversation and is shown on the
Answer screen with the run it produced.

## Why
The cross-review spec's first journey is "talk to an entity away from the phone". The gateway
already lists entities and their cards; the watch only needs a picker and the visit route.

## Scope
- Picker screen: default workflow, entities with their card line (phase, drives), recent workflows.
- Visit an entity through its documented routes; show the entity's open questions and tasks read-only.
- Remember the last choice per device.

## Non-goals
No entity creation, no admin task creation (`POST /entities/{name}/tasks` is admin-scoped), no entity settings.

## Current code reality
- `GET /api/gateway/entities`, `/entities/{name}`, `/entities/{name}/card`, `/entities/{name}/tasks` exist (abstractgateway/docs/api.md §entities); the watch user is a plain `user` role, so task creation is out of scope.
- `GET /api/gateway/bundles` lists `default_agent_workflows` per interface (verified live 2026-10-16).

## Dependencies
Item 0012.

## Expected outcomes
- A question can be addressed to a named entity from the wrist; the answer names the entity and the run.

## Acceptance Criteria
- [ ] The picker lists the default workflow and every entity the user may visit
- [ ] A visit started from the watch appears in the entity's history on the Mac
- [ ] The last choice is restored at the next launch

## Testing
- `cd watch/apple && ./scripts/build.sh --screen picker`
- `curl -s -H "Authorization: Bearer $TOKEN" https://<gateway>/api/gateway/entities`
