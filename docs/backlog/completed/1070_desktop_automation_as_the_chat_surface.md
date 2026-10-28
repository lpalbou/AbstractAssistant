# 1070: Desktop: an automation opens as the chat (composer continues it as a session), a chip header, the footer's stat card

**Status**: completed 2026-10-28 · branch `feat/automation-chat-surface`, PR lpalbou/AbstractAssistant#18 · ships with
the next AbstractAssistant release (sequenced by the lead; CHANGELOG under `[Unreleased]`)
**Found by**: operator, 2026-10-28, on the desktop automation view: "still not the right abstraction. It should be
our conventional chat and I should even be allowed to write. When I do, it automatically creates a session based on
the accumulated context so far and continues the discussion in a session. Moreover the design is very poor: so much
text in the upper tab, unreadable, not enough use of buttons. Review completely the design and aesthetics."
**Related**: 1068 (the "New result" mark, kept), 1069 (runs as replay-view exchanges), ADR 0043 (readable labels),
ADR 0039 (word states), AbstractUIC panel-chat `stat_detail.tsx` (the footer's structured stat card; the kit's
"Message footer" spec in `abstractuic/docs/adoption-guide.md`).

## Problem

- The automation view was a separate surface: a dense header (title, one " · "-joined line with trigger, status,
  next run, context mode and run count; "Workflow: basic-agent@0.0.5:81795ea9"; a "Workspaces: …" line; text
  buttons), runs whose user bubble started with the runtime's "[Trigger schedule@1 · occurrence 1 · fired …]"
  envelope and whose caption named a run-now's command id; no composer (it was hidden); a per-run "Discuss this
  run" button opening a second input.
- Automation result cards had no speaker.
- The message footer's chips showed plain grey multi-line tooltips.

## Plan (done)

1. The automation renders in the chat's surface: the history card's transcript area, the chat's `MessageCard`s
   (speaker wired to the palette's voice), the palette's own composer kept under it.
2. Typing there calls `POST /automations/{id}/discuss` with the latest finished run (or the run chosen with
   "Discuss here"), switches to the new session, and shows "Continued as a session from “<title>” (run N)." with a
   link back; the composer shows "Continuing as a session…" meanwhile.
3. A compact header: title (elided), one status chip, one schedule chip, one next-run chip, the Active switch,
   icon buttons; a ⋯ menu for workflow, workspaces, context and "Copy automation id".
4. The footer's chips open one structured card (title + headline, sections, footnote), as the kit's.
5. Tests that go red when each fix is removed; before/after screenshots.

## Evidence

- **Tests** (tests/basic, offscreen Qt), each mutation-checked RED with its fix removed:
  - `test_the_header_is_chips_and_icons_not_a_joined_sentence` (a " · "-joined meta label put back → red);
  - `test_a_run_reads_as_a_system_line_never_the_bracketed_envelope` (the raw `user_turn` in the bubble → red;
    also checks the run-now command id never reaches a label or tooltip);
  - `test_typing_in_the_automation_continues_its_latest_run_as_a_session` (composer not routed → red; the first
    run instead of the latest → red);
  - `test_continuing_says_so_in_words_and_a_refusal_keeps_the_text` (no word state → red);
  - `test_an_automation_result_card_has_the_chats_speaker` (no `on_toggle_voice` → red);
  - `test_a_chip_opens_the_structured_card_on_hover_and_focus` (a plain tooltip put back → red);
  - plus `test_discuss_here_picks_the_run_the_composer_continues_from`,
    `test_leaving_the_automation_while_its_session_is_created_loses_nothing`,
    `test_choosing_a_chat_leaves_the_automation_and_its_draft_stays_the_chats`,
    `test_a_chosen_run_that_can_no_longer_be_discussed_is_let_go_visibly`, `test_runs_loading_reads_as_loading_not_as_no_run`,
    `test_the_automation_links_the_session_it_was_continued_as`, `tests/basic/test_automation_chat_surface.py`
    (the Qt-free words: envelope and email/event input-frame split, system line, chips, overflow lines, continued
    sessions, the Tokens card, a non-button chip reachable by keyboard).
- **Suite**: `tests/basic` 1419 passed, 10 skipped (offscreen, Python 3.12); CI on PR #18.
- **Screenshots** (offscreen grabs, fixture: 1 automation + 3 runs, one failed): 
  `untracked/release-closing/design/automation/automation-{before,after}-{light,dark}.png`,
  `footer-tooltip-after-light.png` (framework root).

## Gateway gaps (not papered over; for the gateway seat)

1. **Occurrence rows carry no metrics.** `GET /automations/{id}/occurrences` rows have no usage / model calls /
   duration, so an automation's result card has no stat chips (the chat's cards get them from the run ledger).
   Proposal: serve the run's folded statistics on the row, or render the answer from the replay view (1069).
2. **A run-now's served `trigger.summary` names its command id** ("manual: run now (5b0e1c27-…)",
   `routes/automations.py` `_trigger_summary`), against ADR 0043. The desktop no longer shows the served summary
   (the system line is composed from `trigger.source_id`, `index` and `fired_at`).
3. **No per-automation list of its discussions.** "Continued as a session on <date>" is read from the session list
   the palette already holds (`/runs` rows' `session_kind=discussion` + `automation_id`, the pages loaded so far): a
   discussion older than those pages is not linked. Proposal: the automation summary/detail lists its discussion
   sessions (`session_id`, `created_at`, `occurrence_index`), or `/runs` accepts an `automation_id` filter.
4. **Discuss takes text only** (`DiscussBody` = `request_id`, `occurrence_index`, `prompt`): files cannot be
   attached to the message that opens the session; the composer's attach button is disabled with that reason.

## Kit follow-ups

- The per-run action is "Discuss here" in a ⋯ menu (operator's brief); the kit's label is "Discuss this run (your
  own copy; the automation's files stay read-only)" (`ui-kit` 12f736a). The help text is the kit's, word for word.

## Adversarial review (fresh reviewer, read-only, 2026-10-28) and what was fixed

1. An email / feed / webhook run's untrusted-input frame (boundary token, uids) stayed in the task bubble → the
   frame is cut from the task and counted on the system line ("2 new emails").
2. Choosing a chat or + New chat with an automation open left the composer routed to discuss → both leave the
   automation first.
3. A chat draft (or a send queued while a stopped run closes) could be sent as a discussion → the chat's draft is
   kept aside while an automation is open and restored on leaving; a queued send fires only in the chat it was
   typed in.
4. Leaving the view while the session was being created lost the text / the session → a refusal puts the text back
   (with a banner), a success still opens the session, unless a reply is live in the chat on screen (then a banner
   says where the session is; the live run's session is never swapped).
5. The next-run chip's clock was the automation zone's wall time beside local times → the served instant in the
   person's zone (the served wall time stays in the tooltip); clocks formatted like the cards ("05:40 PM").
6.–8. Stop icon / readiness / placeholder leaking between the modes; the pending word state lost on "Discuss
   here" or a reopen → the composer state follows the mode and the in-flight request everywhere.
9. "No finished run…" / "Workflow: not reported" while still loading → "Loading runs…", "Workflow: loading…",
   "Workflow: could not be read" on a failed read.
10. A chosen run that stopped being discussable fell back silently → the selection is let go visibly.
11. Non-button chips were not reachable by keyboard → every chip takes Tab focus (the kit's `tabIndex 0`).
12. "Continued as a session on …" missed the session just created → the sessions this app created are listed
    until the gateway's list names them. Nits: a raw exception in user text replaced by a sentence; a disabled icon
    control's tooltip starts with its name.
