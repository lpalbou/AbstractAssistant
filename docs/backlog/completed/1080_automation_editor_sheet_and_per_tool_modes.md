# 1080 — The automation editor: a sheet with sections, per-tool Off / Ask / Auto, waiting runs continue

**Status**: completed (2026-10-29, unreleased) · **Priority**: P0 · **Created**: 2026-10-29
**Cross-package**: AbstractUIC (the tool vocabulary `TOOL_MODE_LABELS` Off / Ask / Auto, `automation_controls.json`
words); AbstractRuntime (`policy.tool_policy` named approvals, revisable); 1079 (the iPhone's tool approval).

## Why (operator QA, 2026-10-29)
- The operator's verdict on the Edit form: "absolutely horrible, unreadable, completely redesign the layout and
  flow". It was drawn inline over the conversation.
  - The title sat under the workflow box, and "24h / Growing / Max tokens" was cut by "Tools: 4 selected".
  - "Email result" was half hidden and the buttons were clipped.
  - The workflow read `basic-agent@0.0.5:81795ea9`, against ADR 0043.
- The operator needs to edit, at any time, which tools an automation may use and, per tool, Off, Ask or Auto. The
  automation-level "asks before tools" state must show at a glance. A run waiting on a tool just set to Auto must
  continue without a click.
- The look: less text, more icons.

## What shipped
- `ui/automations.py`, `AutomationEditSheet`: a window-modal sheet. It holds the five sections, each with its icon
  (What, When, How, Tools, Delivery), in a scroll area, with **Cancel** / **Save** below them. The view's `edit_*`
  fields live in it.
  - New field: the Task (`target.input_data.prompt`).
  - The workflow combo names a target the catalog does not list by its readable name (`workflow_label`:
    "basic-agent 0.0.5").
- Tools section:
  - The state line (`tool_approval_line`: "Asks before 2 of its 4 tools", "Runs its 4 tools without asking"),
    with a hand or bolt icon.
  - One row per offered tool, with `tool_mode_control`: the shared `SegmentedControl`, now with `set_icons`. Its
    segments are icons, with the kit's words in their tooltips.
  - **Add or remove tools…**: Settings' grouped tool page in `modes_only` mode (`ToolsPage(modes_only=True)`,
    Off / Ask / Auto per tool, nothing stored on this Mac, "Use these tools").
- `core/automations.py` (pure):
  - `automation_tool_modes` reads the definition as the runtime and the iPhone do.
  - `tool_mode_changes` produces the revision: the tools offered, `policy.tool_policy`, and `policy.tool_approval`
    ("ask" only when a tool asks).
  - `waits_cleared_by_modes` sorts the waits into those to resume and those still blocked.
- `app.py` `_resume_waits_set_to_auto`, after a confirmed save:
  - Each tool-approval wait whose every call is now Auto is answered "approved" through the existing wait answer;
    setting them to Auto is the approval.
  - A run still waiting is named in words: "1 run still waits: skim_websearch is on Ask."
- `settings/dialog.py` `segmented_qss()` holds the segmented control's look, shared with the sheet.
- `docs/automations.md` covers the editor.

## Evidence
- `tests/basic/test_automation_edit_sheet.py` (7):
  - modes are read like the runtime;
  - the revision is shape-exact, and every other input is kept;
  - waits are split by mode;
  - the sheet has its sections, its icons and tooltips, the readable workflow, and Save/Cancel;
  - the per-tool save carries `policy.tool_policy`;
  - the operator's case: a run waiting on fetch_url and skim_websearch resumes with `{approved: true}` after both
    are set to Auto, with no click;
  - a run still blocked is named.
  - Mutation-checked: red without the resume, red without the modes save.
- The existing edit tests (title and interval, tool selection, workflow picker, workspaces, calendar) pass
  unchanged.
- Screenshots (framework root `untracked/release-closing/design/automation-edit/`): `edit-before-desktop.png`, and
  `edit-after-panel.png`, `edit-after-panel-bottom.png` and `edit-after-narrow.png` (420 px).

## Follow-ups
- The create sheet (`ScheduleSheet`) still uses the allow-list picker and one Auto/Ask choice. Moving it to the same
  per-tool modes, and one editor for create and edit, is next.
- The iPhone has its own editor, a different component; it is not touched here.
