# 1210 — Preserve a new attachment after an entity mention refusal

> Package: AbstractAssistant
> Type: bug
> Created: 2026-11-13
> Priority: P0
> Labels: mentions, attachments, release

## Summary

Adding a file while resending a refused entity mention must send that file with a fresh turn,
keeping only the unanswered recipients. A text-only retry remains idempotent against its original
turn. Framework release recovery 1209 owns the package release and main integration.

## Current code reality

The 0.19.0 candidate selected resend by words/chips alone in the palette and worker. It cleared
the queued attachments, then returned before upload. Independent release review identified the
path. The existing text-retry test even supplied a file while asserting that no upload happened.

The working-tree fix checks attachments at both boundaries. The palette creates a fresh user
turn; the worker independently refuses retry mode and reaches upload. A partially answered send
keeps only its unanswered chips, so an entity that already answered is not asked again.

## Acceptance criteria

- [x] Worker and real offscreen palette regressions both fail before the change.
- [x] New files reach upload/start; pure-text retry still starts no extra user turn.
- [x] Existing unsent-turn preservation and mention suites pass (31 tests).
- [x] Stop docs accurately distinguish local suppression from durable Gateway history.
- [x] Real scratch-Gateway proof covers positive sends, refusal/retry, Stop and attachment handling.
- [ ] Full CI/release gates, independent final review, remote-main integration and publication.

## Receipts

- Initial regression: two failures, `af-recovery-mention-attachment-red` under the system temp dir.
- Focused suite: 31 passed, `af-recovery-mention-attachment-green-r2`.
- Independent source review approved the fix conditionally on the real-Gateway and release gates.
- 2026-11-14: actual TCP Gateway + Assistant worker proof passed ordered replies, no entity-only
  agent invocation, reload authors/one person row, idempotent mention POST, 409 continuation,
  503 retry on the same turn, a new durable attachment turn, Stop suppression and unknown 404.
  Deterministic provider leaves; zero external network attempts. Evidence lives in the framework's
  `untracked/release-recovery-2026-11-13/assistant-real-http-proof.{py,log}`.
