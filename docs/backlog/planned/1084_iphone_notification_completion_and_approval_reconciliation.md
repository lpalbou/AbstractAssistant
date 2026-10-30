# 1084-assistant: [BUG] iPhone notification completion and repeated approval gates

> Package: abstractassistant
> Type: bug
> Created: 2026-10-30
> Status: planned
> Priority: P1
> Labels: iphone, approvals, notifications, seat-framework
> Work-item id: abstractassistant-1084
> Owner: framework
> Thread: unavailable (Agora connection refused; direct operator request)
> Hub refs: none

## Report and current code reality

Operator sent a Watch message: tray badge appears but its transcript is blank;
iPhone notification tap crashes, relaunch restores the gate, and Approve needed
three taps. Another agent has uncommitted desktop session-sync changes in
`abstractassistant/app.py` and related Python tests: inspect only, do not stage
or overwrite. Desktop/Watch successive-gate work already exists in `f5789f6`.

Read-only CoreDevice crash retrieval found iPhone 0.16.0 build 39's 2026-10-30
06:22:17 crash: SIGABRT on a cooperative background queue, UIKit state restoration
assertion under the generated PhoneNotifier notification-tap completion closure.
The async delegate updates its tab on MainActor but the generated completion can
return on a background executor. Replace that bridge with explicit completion
on MainActor and test a background-delivered tap.

`AssistantStore.answer` receives the queued resume acknowledgement, removes its
wait and immediately reads the run again. It has no decided-wait set/revision
update for ordinary Approve; refresh/activity reads can therefore reinsert the
same old gate before the queued command runs. Port the Watch's connection-scoped
decision reconciliation to the phone; preserve next-gate visibility and never
approve a different wait automatically. Keep server/wire ownership unchanged.

## Acceptance criteria

- [ ] Notification tap routes and completes exactly once on the main thread, including dismissed/unknown payloads.
- [ ] Accepted same-gate decisions cannot reappear or submit twice after stale refresh/activity reads; a new wait remains actionable.
- [ ] Failed submissions stay actionable and expose errors; connection changes isolate decision state.
- [ ] Native/Swift tests and a guarded app build pass; preserve credentials and other agents' desktop changes.

ADR impact: none expected; callback correctness and local projection of accepted
exact-key decisions, within existing thin-client contracts. No live approvals
will be sent for testing. Device crash source retained privately under /tmp;
commit only sanitized diagnostic facts. No App Store publication implied.
