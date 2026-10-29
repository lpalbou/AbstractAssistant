# 1082 — The attention badge opens at the item that needs the person; the approval card's text is readable

**Status**: completed (2026-10-29, unreleased; in a PR, not done until merged and verified on the operator's desktop)
· **Priority**: P1 · **Created**: 2026-10-29
**Cross-package**: the same rule for the kit's `AutomationPanel` (Code web, Observer): AbstractUIC, separate PR.

## Why (operator, 2026-10-29)
"If I click an attention icon, I should get directly to where you need my attention." The badge opened the
automation at the TOP of its conversation; the approval card was at the bottom, out of view. The approval card's tool
lines also used the dimmed meta style (`autoTurnMeta`: faint, 10 px), which read poorly on the dark card.

## What shipped
- `ui/automations.py` `AutomationView.attention_widget(run_id)` and `scroll_to_attention(run_id)` pick the target:
  - the waiting card of the run the badge counted;
  - else the first unresolved wait (the oldest waiting run);
  - else the first unseen result.

  The target's top is scrolled into view and the target is outlined for 2.6 s (`attentionFocus`, an accent
  border). The outline follows a rebuild of the runs. `focus` itself is QWidget's own read-only property and cannot
  be used for this.
- `app.py` `_open_attention` opens with `where="attention"` and the wait's run. `_open_automation(…, where=,
  focus_run=)` falls back to the first new result, then the latest run.
- The approval card's tool-call lines, the group line and the "no calls listed" line use `autoTurnText` (the
  standard text colour). The options stay muted inside the line.
- Test: `test_the_badge_opens_at_the_item_that_needs_the_person` checks the waiting card is chosen, outlined, its
  top in view, and the tool lines use the standard text style. Mutation-checked: without the attention path it
  fails.
