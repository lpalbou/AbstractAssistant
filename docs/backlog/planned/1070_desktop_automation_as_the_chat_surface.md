# 1070: Desktop: an automation opens as the chat (composer continues it as a session), a chip header, the footer's stat card

**Status**: planned · **Created**: 2026-10-28 · branch `feat/automation-chat-surface`
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

## Plan

1. The automation renders in the chat's surface: the history card's transcript area, the chat's `MessageCard`s
   (speaker wired to the palette's voice), the palette's own composer kept under it.
2. Typing there calls `POST /automations/{id}/discuss` with the latest finished run (or the run chosen with
   "Discuss here"), switches to the new session, and shows "Continued as a session from “<title>” (run N)." with a
   link back; the composer shows "Continuing as a session…" meanwhile.
3. A compact header: title (elided), one status chip, one schedule chip, one next-run chip, the Active switch,
   icon buttons; a ⋯ menu for workflow, workspaces, context and "Copy automation id".
4. The footer's chips open one structured card (title + headline, sections, footnote), as the kit's.
5. Tests that go red when each fix is removed; before/after screenshots.
