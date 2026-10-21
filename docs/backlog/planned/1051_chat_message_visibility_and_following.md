# 1051 — Chat message visibility and bottom following

> Package: abstractassistant
> Type: bug
> Created: 2026-10-20
> Status: Planned
> Completed: N/A
> Priority: P1
> Labels: iphone, conversation, voice, observability

## Current code reality

ChatScreen appends through an observable MainActor store and uses LazyVStack. Its sole
scroll trigger observes the last message text and immediately animates scrollTo(bottom).
That misses same-text identity changes, artifact/activity height changes and keyboard/inset
resizing, and can run before lazy rows are measured. User reports new voice question and
answer becoming visible only after scrolling; geodesic speech-wait orb remained visible.
Independent adversarial review agrees this is a layout/viewport hypothesis; verify before
claiming an exact device reproduction. Speech state must also be checked independently.

## Scope and expected outcome

Make submitted questions, incoming answers and terminal status visible without requiring a
manual pan. Follow laid-out content while at latest messages; respect explicit reading of
older messages and offer a clear return to latest. Sending a new turn resumes following.
Preserve lazy history, media, keyboard/composer and cancellation behavior. Establish that
speech-wait geometry returns to playback/idle and cannot conceal an already completed answer.
No Watch/Gateway/Framework changes, Git commit/push or Store upload.

## Validation and ADR state

Use an adversarial subagent and native regressions asserting visible viewport geometry,
without swiping after send. Cover restored history, spoken/typed submission, streaming,
read-aloud preparation/completion and deliberate history reading. Inspect native screenshots,
update docs/changelog and install the normal developer build for user validation. Existing
thin-client/UI ownership applies; no new cross-task ADR expected.

## Delivery update — 2026-10-20

On the user’s reinstall request, normal developer build0.6.22(34) compiled successfully,
passed strict signature verification, and was installed and launched on the physical iPhone.
No demo/test launch arguments were supplied. Evidence:../evidence/1051/development-install.json.
One initial build yielded to the concurrent Watch CPU guard; the next build succeeded when
the guard allowed it. Independent adversarial source review is in../evidence/1051/adversarial-review.md.
Native visibility regressions remain pending; this item stays Planned rather than claiming
runtime verification. No Git commit/push or Store upload.

## User validation refinement — 2026-10-20

Build34 user screenshot showed Latest messages persisting at the bottom. The indicator was
conditioned on stale following intent rather than actual proximity; a final idle geometry
change could arrive after the drag/phase callbacks. Geometry now restores following whenever
it observes bottom proximity, even after the gesture ends. The indicator also requires actual
distance from the bottom, so stale intent alone cannot display it. Added a native manual
scroll-up/scroll-back regression, without tapping the indicator. Both selected native-test
attempts and both development-build attempts yielded to the existing Watch priority guard
(PID55417; helper exit75). No tests completed and no new binary was installed. Documentation
index consistency and git diff whitespace checks pass. Build35 delivery remains pending;
the phone still has build34. Evidence:../evidence/1051/latest-messages-refinement.json.

## Redeployment — 2026-10-20

On the user’s redeploy request, build35 compiled and passed strict signature verification,
then installed and launched successfully on the physical iPhone without fixture arguments.
An initial linker failure due to disk exhaustion was resolved by clearing obsolete generated
iPhone build caches. Native regression tests remain pending; no Git commit/push or Store upload.
Evidence:../evidence/1051/development-install-35.json.

## Native validation refinement — 2026-10-20

Native checks reproduced the persistent indicator: the prior offset formula double-counted
safe-area insets. Bottom distance now uses contentSize.height minus visibleRect.maxY. Manual
scroll-back and history-reading/new-submission regressions passed. The standalone manual
fixture now adds enough content to scroll beyond the near-bottom tolerance.

The repeated spoken-turn regression exposed a separate remaining race: both questions were
visible; the second reply footer was not yet hittable during speech preparation and became
visible by speech completion. A cooperative yield can resume before layout; the pending
refinement coalesces through a 32 ms display interval instead. Its native retest was interrupted
by the Watch priority guard. Keep this item Planned pending completed voice validation.
Evidence:../evidence/1051/native-validation-2026-10-20.json.
