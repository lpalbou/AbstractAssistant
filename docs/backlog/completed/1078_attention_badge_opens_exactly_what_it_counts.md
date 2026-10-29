# 1078 — The attention badge opens exactly what it counts (and replaces the text banner)

**Status**: completed (2026-10-29, unreleased) · **Priority**: P0 · **Created**: 2026-10-29
**Cross-package**: AbstractUIC 0067 (lpalbou/AbstractUIC#28: the badge's glyph and words in
`automation_controls.json`, vendored here byte-identically; the AbstractCode TUI vendors the same file).

## Why (operator QA, 2026-10-29)
A banner read "A conversation is waiting for you · 1 new result from your automations · Open".
- Open landed on an old session (the daily news briefing of 27 Oct) with nothing pending.
- The banner never cleared.
- Open again went to the blank initial page.
- The standing rule applies too: less text, more icons. This should be a badge on the sessions control.

## Root cause (read from the operator's own event stream and automation list, 2026-10-29)
- **What was counted.** Two automations ("You report your daily news…" and "what are today's news in the US…")
  each had a run waiting for a tool approval (`fetch_url`). Both waits were raised in the automation's session,
  `automation:<automation id>`. A third automation had one unseen result (seq 20). The stream and the gateway's
  automation list agreed on all three. One wait was the session on screen, so the banner said "A conversation"
  (one).
- **Why Open went to an old session.** The wait branch called `_switch_to_session(wait.session_id)` with
  `automation:<id>`. That loads the automation's backing session as a chat: its old transcript, with no approval
  sheet, because the waiting run is an automation occurrence. The approval is answered in the automation's view,
  which was never opened.
- **Why it never cleared.** Nothing pending was answered. The new result belonged to another automation and was
  never opened, so it was never acknowledged.
- **Why the second Open went blank.** The banner kept its "wait" link and pointed at the next automation's
  backing session.

## What shipped
- `core/attention.py`:
  - `automation_of_session()` reads the automation id from an `automation:<id>` session.
  - `AttentionModel.result_automations()` lists exactly what `new_results` counts, newest first, and
    `new_results_outside(id)` counts the results of every automation but one.
  - The banner text is replaced by `attention_tooltip` and `attention_label`, whose words come from the kit's
    `automation_controls.json` → `attention`.
- `app.py`:
  - The QLabel banner is replaced by `attention_badge`, a button beside the session control. It shows the kit's
    inbox glyph (`icons.attention`, drawn verbatim by `icons.py`) and the count, with the kit's tooltip lines and
    an accessible name.
  - `_attention_targets()` lists the waits not on screen first, then the automations with unseen results.
  - A click opens the first target. A wait in an automation's session opens `_open_automation(id)`. A chat wait
    is checked first, then opens its chat. A result opens its automation, and `mark_seen` runs after the load.
  - A wait or result of the automation in view is not counted while the view is open.
  - With no event stream, the automation list's `unseen_count` drives the result targets.
  - The badge refreshes when a view opens or closes and when the list changes.
- `assets/automation_controls.json`: the kit's file (0067), byte-identical.
- `docs/automations.md`: the badge.

## Evidence
- `tests/basic/test_me_events_attention.py`:
  - `test_the_badge_opens_exactly_what_it_counts_and_opening_clears_it` reproduces the operator's case: a wait in
    `automation:<JOURNAL>` plus a result of TRIAGE. The badge reads 2. The first click opens JOURNAL's view, with
    no chat switch, and the badge drops to 1. The second click opens TRIAGE and POSTs `seen`, and after the
    gateway's echo the result count is 0. Mutation-checked, red with each of these removed: the automation
    routing, the in-view exclusion, the refresh on open, the stream-derived result targets.
  - The palette test now asserts the badge's count, icon, tooltip and accessible name.
  - `test_badge_words_are_the_kits` and `test_result_automations_are_what_new_results_counts`.
- `tests/basic/test_automations.py::test_open_goes_to_the_new_result_and_marks_it` still passes through the
  no-stream path.
