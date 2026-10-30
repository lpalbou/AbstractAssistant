# 1084-assistant: [BUG] iPhone notification completion and repeated approval gates

> Package: abstractassistant
> Type: bug
> Created: 2026-10-30
> Status: completed
> Completed: 2026-10-30
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

- [x] Notification tap routes and completes exactly once on the main thread, including dismissed/unknown payloads.
- [x] Accepted same-gate decisions cannot reappear or submit twice after stale refresh/activity reads; a new wait remains actionable.
- [x] Failed submissions stay actionable and expose errors; connection changes isolate decision state.
- [x] Native/Swift tests and a guarded app build pass; preserve credentials and other agents' desktop changes.

ADR impact: none expected; callback correctness and local projection of accepted
exact-key decisions, within existing thin-client contracts. No live approvals
will be sent for testing. Device crash source retained privately under /tmp;
commit only sanitized diagnostic facts. No App Store publication implied.

## Completion report

Completed 2026-10-30. Source `8f773fb`; intake `693d128`.
Original path: `planned/1084_iphone_notification_completion_and_approval_reconciliation.md`.
Final path: `completed/1084_iphone_notification_completion_and_approval_reconciliation.md`.

Fixed PhoneNotifier’s notification completion executor using an explicit callback
bridge on MainActor; no generated async completion returns UIKit restoration to
a background queue. Two native iOS 26.5 tests verify routing and exactly-once
main-thread completion for background-delivered, dismissed and unknown taps.

AssistantStore tracks accepted exact-key decisions while their queued commands
are applied. Stale list/activity reads cannot redraw that gate or submit it again;
full owning-run transitions retire pending state so genuinely new or later reused
keys still work. Old probes cannot retire a newer submitted gate. Failed answers
stay actionable, cross-connection state is reset, and the UI distinguishes a sent
decision from gateway execution. No API/Runtime contract or tool trust expansion.
Touched PhoneNotifier.swift, AssistantStore.swift and their native/package tests.

228 Swift logic tests, two native notification tests, and 43 desktop regressions
passed. [Evidence](../evidence/1084/README.md) retains sanitized crash facts,
xcresult summary, source identity and signed binary digest. The existing guarded
Debug build/install/launch succeeded on the connected physical iPhone, preserving
its saved sign-in; app running and no new crash after launch. No App Store upload,
new service, persistence mechanism or live approval test. Dedicated test simulator
removed. Actual physical notification tapping remains an operator retest.

The other agent’s desktop fix `b962b94` was verified read-only. Its app.py source
was modified before the running desktop process started, and the deployment
symlink targets that source. No desktop changes were overwritten/staged and no
desktop restart was performed. The initial timing concern based only on commit
time was corrected using source mtime and process start. Gateway 0991 is already
closed/deployed separately. No new follow-up, recurrent task or ADR impact.
Backlog counts/links reconciled. Agora remained connection-refused; local
receipts retained without claiming hub synchronization.
