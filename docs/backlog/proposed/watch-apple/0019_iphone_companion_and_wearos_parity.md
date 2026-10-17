# Proposed: iPhone companion (QR pairing, notification relay) and Wear OS parity study

> Created: 2026-10-16 22:30:00 +0200
> Type: task
> Priority: P3
> Labels: watch, ios, wearos, parity

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractassistant
- Track: [watch-apple](README.md) (Apple Watch client)

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md) (gateway-native thin client: the gateway owns workflows, runs, tools, policy and speech)
- ADR impact: None. The watch is one more thin client of the same gateway contract.

## Summary
Decide whether an iPhone companion app is worth shipping (QR pairing by scanning the console,
a local notification relay while push is not available, a bigger screen for the same thin
client) and study parity on Wear OS under `watch/wearos/`.

## Why
The watch is standalone by design, but a phone app would remove the two hardest parts of the
watch experience (pairing and notifications) at the cost of a second Apple target. Parity with
other platforms is part of the folder layout (`watch/<platform>/`).

## Scope
- A short written decision with evidence: what the companion would own (WatchConnectivity for credentials, QR scan, notification mirroring), what it would duplicate, and the maintenance cost.
- Wear OS: which of the ten API calls and which screens carry over; Kotlin/Compose for Wear OS scaffold estimate.

## Non-goals
No implementation in this item.

## Current code reality
- The Swift client package targets watchOS, iOS and macOS so a companion would reuse it (`watch/apple/docs/architecture.md`).
- No mobile or wearable mention exists elsewhere in this repository; Linux and Windows support is "may work" (`README.md`).

## Dependencies
Items 0012–0014 decide most of the value of a companion.

## Expected outcomes
- A decision recorded in this item (go / no-go for the companion, scope for Wear OS) with the reasons.

## Acceptance Criteria
- [ ] Decision written with evidence and a cost estimate
- [ ] If go: a follow-up planned item for the companion with its own acceptance criteria

## Testing
- `n/a` (decision item; see the follow-up item's tests)
