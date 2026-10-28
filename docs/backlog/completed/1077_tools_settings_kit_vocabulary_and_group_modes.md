# 1077: Desktop Settings → Tools: the kit's Off / Ask / Auto, the same control on the group, read-only rows the gateway does not offer

**Status**: completed 2026-10-28 on branch `feat/tools-vocabulary` (DESK2's WIP commit 0accdbc cherry-picked onto
origin/main, then finished by DESK1) · ships with the next AbstractAssistant release (CHANGELOG `[Unreleased]`).
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

## Finished (DESK1, 2026-10-28)

- Wording decision: a tool the gateway does not offer reads the kit's words exactly, "Not offered by the gateway:
  <why>" or "Not offered by the gateway." when none is served (the WIP's fallback "switched off on the gateway" is
  not in the kit: one wording set, AbstractUIC ADR 0001). The approval sheet's chip says "Not offered by the gateway"
  (was "Disabled on gateway").
- `ToolsPage.refresh` hides and unparents the old panels before `deleteLater` (they painted under the rebuilt ones:
  two control rows over each other in every grab, before and after).
- Docs: settings.md (Tools table), faq.md, troubleshooting.md, getting-started.md, api.md use Off / Ask / Auto and
  "Not offered by the gateway".

## Evidence

- Tests (`tests/basic/test_r10w4_settings.py`), each mutation-checked RED:
  `test_the_tool_vocabulary_is_the_kits` (labels and the cap sentence pinned to the kit's strings; segment order
  Off / Ask / Auto on rows and groups; old order → red), `test_the_group_control_has_the_rows_states_and_shows_mixed`
  (group Off / Ask set every offered row, Mixed after a hand change; no "Mixed" → red),
  `test_group_auto_honours_the_kits_cap_and_says_which_tools_stay` (rank 4 and rank 3 rows stay, the cap line names
  them, Auto unavailable where it reaches nothing; no cap → red),
  `test_a_tool_the_gateway_does_not_offer_is_read_only_with_the_why` (served why / kit fallback, read-only, never
  stored, the group skips it; editable row → red); rewritten: the filter test and the refused-save test on the new
  control; `tests/basic/test_tool_approval_sheet.py` (the chip's words; old words → red).
- Screenshots: `untracked/release-closing/design/tools/tools-{before,after}-{light,dark}.png` (the agora panel open;
  `tools-full-*` are the inner list only, the dark one without its window background).
