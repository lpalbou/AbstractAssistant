# Proposed: Complications, Smart Stack widget and App Intents

> Created: 2026-10-16 22:30:00 +0200
> Type: feature
> Priority: P2
> Labels: watch, widgetkit, siri

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractassistant (watch client)
- Track: [watch-apple](README.md) (Apple Watch client)

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md) (gateway-native thin client: the gateway owns workflows, runs, tools, policy and speech)
- ADR impact: None. The watch is one more thin client of the same gateway contract.

## Summary
A WidgetKit extension with a rectangular Smart Stack widget ("2 waiting for you", the last
automation result) and a corner complication with the waiting count; App Intents so Siri and
Shortcuts can "Ask my assistant" and "Approve the waiting run".

## Why
The glance value of a watch is the face. The waiting count is the one number the user wants
without opening anything, and Siri lets a question be asked without touching the screen.

## Scope
- `Sources/Widgets` target: timeline provider reading a shared snapshot (App Group) written by the app on each poll and on background refresh; relevance for the Smart Stack when a wait exists.
- `AppIntents`: `AskAssistantIntent(prompt)`, `ApproveWaitingRunIntent` (opens the app on the first wait; it never approves silently), `RunAutomationIntent(name)`.

## Non-goals
No Live Activities (ActivityKit is not available to a watch-only app on this SDK); no complication that approves anything.

## Current code reality
- `WidgetKit` and `AppIntents` are present in the watchOS 26.5 SDK; `ActivityKit` is not (`untracked/watch/research/toolchain-check.md` §D).
- The waiting count comes from `GET /runs?status=waiting` and automation `attention.pending_waits` (abstractgateway/docs/api.md §runs; automations.md §attention).

## Dependencies
Item 0012.

## Expected outcomes
- The face shows the waiting count; tapping opens the first wait. Siri asks a question through the same run path as the Ask screen.

## Acceptance Criteria
- [ ] The rectangular widget shows the waiting count and updates within one background refresh of a change
- [ ] The corner complication shows the count; tapping opens the first wait
- [ ] "Ask my assistant to …" through Siri starts a run and shows the answer in the app

## Testing
- `cd watch/apple && xcodegen generate && xcodebuild -scheme AbstractAssistantWatchWidgets -destination 'platform=watchOS Simulator,name=Apple Watch Series 11 (46mm)' build CODE_SIGNING_ALLOWED=NO`
