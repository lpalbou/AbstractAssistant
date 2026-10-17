# Proposed: On-demand location context attached to a question

> Created: 2026-10-16 23:10:00 +0200
> Type: feature
> Priority: P3
> Labels: watch, location, privacy

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
An explicit "attach my location" toggle on the Ask screen: with permission, the question
carries the current coordinates, timestamp and accuracy as run input, and the Answer screen says
that location was shared. Nothing is tracked in the background.

## Why
Questions like "what is around here" or "have I been here before" need the position. The
cross-review spec asks for on-demand sharing only, with the indicator visible.

## Scope
- `CoreLocation` one-shot request; input pin `location: {lat, lon, accuracy_m, at}`; visible indicator; a setting to forget the last location.

## Non-goals
No background location, no geofences, no visit history on the watch.

## Current code reality
- The default agent workflow accepts run input pins; adding a `location` pin needs the workflow to read it (abstractgateway/docs/shipped-workflows.md).

## Dependencies
Item 0012.

## Expected outcomes
- A question can carry the current location once, with the user's consent shown on screen.

## Acceptance Criteria
- [ ] Location is sent only when the toggle is on for that question
- [ ] The Answer screen shows that location was shared
- [ ] Denied permission leaves the question working without location

## Testing
- `cd watch/apple && ./scripts/build.sh --screen ask`
