# 1077: Desktop Settings → Tools: the kit's Off / Ask / Auto, the same control on the group, read-only rows the gateway does not offer

**Status**: in progress, HANDED OFF 2026-10-28 (lead: removed from DESK2's scope, another worker takes it) · the
work so far is on branch `feat/settings-tools-watch` (commit "1077 WIP"), see "State" below.
**Found by**: operator QA 2026-10-28 (screenshot: group "agora · 12" with "All auto / All ask"; each tool "Disabled on
gateway", Off / Auto / Ask): "I am unsure you use the vocabulary we decided; and the group must have the same states
as the tools (Off / Auto / Ask), not only All auto / All ask."
**Ground truth**: abstractuic ui-kit `tool_plan.ts` (`TOOL_MODES` off|ask|auto, `BULK_AUTO_MAX_RANK`, `bulkAutoReaches`,
`normalizeToolCatalog` why = `why_disabled` || `enable_gate`), `tool_mode_editor.tsx` (`TOOL_MODE_LABELS`,
`BULK_AUTO_CAP_SENTENCE`, group head control + "Mixed", "Not offered by the gateway: <why>", "Default: X" chip).

## State (on the branch)

- `ui/settings/common.py`: `SegmentedControl.set_mixed()` (no segment pressed).
- `ui/settings/pages.py`: constants `TOOL_MODE_LABELS`, `TOOL_ROW_MODES` (Off / Ask / Auto over the stored
  disabled/ask/approve), `TOOL_ALLOW_LIST_MODES` (Off / On), `BULK_AUTO_CAP_SENTENCE` (verbatim), `_bulk_cap_text`;
  `_ToolGroup` rewritten: head = state label ("Off"/"Ask"/"Auto"/"Mixed") + `mode` SegmentedControl ("All <toolset>
  tools"), Auto disabled when every shown tool is capped, Auto tooltip carries the cap sentence, `cap_note` (sentence +
  "N tools here stay as it is: names.") shown when the panel is open; rows Off / Ask / Auto with tooltips "Not offered
  to the run" / "Asks before each call" / "Runs without asking" (+ " · gateway default"); a "Default: X" chip on a row
  that differs from the gateway default; a tool the gateway does not offer: shown Off, read-only, tooltip and a
  warning line "Not offered by the gateway: <why>." ("switched off on the gateway" when none is served), never stored;
  group logic `_bulk_auto_reaches` (rank <= 2, unknown rank = 4, not `model_controlled_destination`), group acts on the
  shown offered rows, group state follows the filter; selection_only gets an Off / On group control (no persist).
- `controller.py` `_compute_tool_inventory`: `available` also honours `available: false`; passes `why_disabled`
  (or `enable_gate`) and `model_controlled_destination`.
- NOT done: tests. `tests/basic/test_r10w4_settings.py::test_all_auto_and_all_ask_are_pressed_state_controls_that_apply_at_once`
  and `::test_the_filter_searches_every_category_and_opens_the_ones_with_hits` FAIL (they drive the removed
  `all_auto`/`all_ask` buttons and `_buttons[2]` = Ask in the old order): rewrite them on `group.mode`
  (Off/Ask/Auto buttons 0/1/2). The approval sheet (`ui/approval.py`) still says "Disabled on gateway" (out of this
  item's scope as briefed; decide).

## Next steps

1. Rewrite the two r10w4 tests; add: group control sets every reachable shown row and shows "Mixed"; group Auto leaves
   rank > 2 / model-chosen-destination rows and the footer says the kit's cap sentence; a not-offered row is Off,
   disabled, tooltip = "Not offered by the gateway: <why>." (+ the fallback words); labels pinned to the kit's
   `TOOL_MODE_LABELS` strings; mutation-check each.
2. Screenshots `untracked/release-closing/design/tools/tools-{before,after}-{light,dark}.png` (before ones: shoot.py
   with `TOOLS_DIR=1` on main).
3. Adversarial review, CI, merge.
