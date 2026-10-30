# 1084 — iPhone notification crash and approval reconciliation

Code `8f773fb`; intake `693d128`. [Validation](validation.json),
[sanitized device crash](crash-summary.json), [native results](native-tests.json).

The physical iPhone’s 0.16.0 (39) crash at 06:22:17 aborted in UIKit state
restoration from the generated async notification completion on a cooperative
background queue. PhoneNotifier now implements the completion-handler delegate
entry point explicitly, and routes/completes on MainActor, exactly once even
for dismissal or unknown destinations. Native tests dispatch from background
tasks and check callback thread, routing and completion count.

The phone also removed a wait after a queued command acknowledgement but could
restore it from a stale run/list read. Accepted exact-key decisions are now
reconciled against authoritative owning-run state. Pending keys stay hidden
until that occurrence disappears; legitimate later reuse remains supported.
Revision checks reject old probes, new gates remain actionable, failed submissions
remain visible and connection replacement clears decision state. The waiting
screen says Decision sent while the gateway still exposes a submitted gate.
Wire endpoints and Runtime approval ownership are unchanged.

All 228 AssistantKit tests and two native notification tests passed. The existing
guarded build produced the combined iPhone/Watch app, then installed/launched the
Debug app over the connected iPhone with its saved sign-in. No new crash report
appeared after launch. The app keeps marketing/build 0.16.0 (39) for this local
Debug refresh; binary digest identifies the installed code. Nothing was uploaded
to App Store Connect. No real approvals or requests were submitted for testing.
The dedicated simulator was deleted after its xcresult was retained.

Desktop sync was another agent’s work, committed separately as `b962b94`.
Its source predates the running desktop process and the deployment symlink
points to it. This pass verified 43 focused Python regressions, without staging
its files or restarting its process. The earlier Models header update is already
completed/deployed as Gateway 0991 (`549680a7`, closure `871e7d64`).

Limits: the real notification tap and end-to-end Watch-to-desktop conversation
still need operator retesting; no test generated a live approval. Existing Xcode
warnings in model/orb/notifier code outside this change were left untouched;
xcresult reports Passed, two tests, zero failures/runtime warnings.
