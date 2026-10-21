# Independent adversarial review — 2026-10-20

Reviewer: chat_render_adversary (read-only; independent source audit).

Found an immediate animated scrollTo(bottom) triggered only by last-message text before
LazyVStack measurement; no store append/ID/MainActor defect found. Identified missing
artifact/activity/composer geometry triggers and confirmed independent TTS preparation can
outlive answer creation. Existing existence-only checks do not establish visible messages.

Reviewed the replacement and requested: prevent pending corrections during tracking/drag/
deceleration; reconcile following at idle; tolerate fractional geometry jitter; use stable
latest-message selectors rather than assuming lazy rows remain in accessibility; verify
initial restoration, duplicate voice questions, keyboard resizing, reading history and
jump-to-latest. All changes adopted. Idle reconciliation uses authoritative phase geometry.

Final source verdict: no further source-level blocker. Native verification required and
was explicitly still pending at review time. No reviewer edits or builds.
