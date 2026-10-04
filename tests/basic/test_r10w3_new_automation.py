"""R10.4: automations are created from the Assistant (Sessions | Automations switcher).

Headless Qt (offscreen; the palette fixture disables the traffic-light bridge and the
global hotkey) against the HTTP stub gateway of test_automations.py: the switcher shows the
Automations tab, "New automation" opens the sheet with the kit's AfScheduleDialog content
(workflow "Gateway default" FIRST and selected, Task, Title, When, Stop after / Stop at,
Context, Tools + consent, Mailbox), and "Create automation" POSTs the body asserted here.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from test_automations import AUTOMATIONS_PATH, palette, stub  # noqa: F401 (fixtures; tests/basic is on sys.path)

from abstractassistant.ui.automations import AutomationWorkflowCombo, ScheduleSheet


MENU: List[Dict[str, Any]] = [
    {"choice": "@default", "label": "Gateway default → AbstractAssistant Orchestrator @0.0.9", "detail": "Set on the gateway."},
    {"choice": {"bundle_id": "abstractassistant-orchestrator", "flow_id": "c53b1579", "registry_scope": "private"},
     "label": "Built-in orchestrator @0.0.9", "detail": "always its latest version."},
    {"choice": {"bundle_id": "research", "flow_id": "main", "registry_scope": "private"},
     "label": "Research workflow @1.0.0 — research", "detail": "always its latest version."},
]


def _with_gateway_default(window, monkeypatch, *, available: bool = True) -> None:
    controller = window._controller
    monkeypatch.setattr(controller, "workflow_menu", lambda: list(MENU), raising=False)
    monkeypatch.setattr(controller, "tool_inventory", lambda: {"items": []}, raising=False)
    monkeypatch.setattr(
        controller, "gateway_default_workflow",
        lambda: SimpleNamespace(available=available, bundle_id="abstractassistant-orchestrator", bundle_version="0.0.9", flow_id="c53b1579"),
        raising=False,
    )


@pytest.mark.basic
def test_switcher_automations_tab_new_automation_creates_with_the_gateway_default(palette, stub, monkeypatch) -> None:  # noqa: F811
    window, _controller = palette
    _with_gateway_default(window, monkeypatch)
    window._poll_automations()
    assert window._automations.available is True

    window._open_session_switcher()
    switcher = window._session_switcher
    assert switcher.tab_bar.isVisibleTo(switcher), "Sessions | Automations tabs"
    assert [switcher.tab_buttons[t].text().split(" · ")[0] for t in ("sessions", "automations")] == ["Sessions", "Automations"]
    switcher.tab_buttons["automations"].click()
    assert switcher.tab == "automations"
    assert switcher.new_automation_button.isVisibleTo(switcher)

    switcher.new_automation_button.click()
    sheet = window._schedule_sheet
    assert isinstance(sheet, ScheduleSheet) and sheet.standalone is True
    assert sheet.windowTitle() == "New automation"
    picker = sheet.workflow_picker
    labels = [picker.itemText(i) for i in range(picker.count())]
    assert labels[0] == "Gateway default", labels
    assert picker.currentIndex() == 0, "Gateway default is selected by default"
    assert labels[1:] == ["Built-in orchestrator @0.0.9", "Research workflow @1.0.0 — research"]
    assert sheet.submit_button.text() == "Create automation"

    sheet.prompt_edit.setPlainText("Check the price of ACME shares")
    sheet.count_edit.setText("3")
    sheet.until_edit.setText("2030-01-01 08:00")
    sheet.growing.setChecked(True)
    assert sheet.preview_label.text().startswith("Runs every 8 hours (UTC)")
    sheet.submit_button.click()

    body = stub.calls("POST", AUTOMATIONS_PATH)[-1]["body"]
    assert body["target"] == {
        "flow_id": "@default",
        "interface": "abstractassistant.agent.v1",
        "input_data": {"prompt": "Check the price of ACME shares"},
    }
    assert body["title"] == "Check the price of ACME shares"
    assert body["trigger"] == {
        "source_id": "schedule",
        "source_version": 1,
        "config": {"every": "8h", "count": 3, "until": "2030-01-01T08:00:00Z"},
    }
    assert body["context"] == {"mode": "growing"}
    assert body["policy"] == {"tool_approval": "auto"}
    assert "notify" not in body
    # Back on the Automations tab with the new row selected.
    switcher = window._session_switcher
    assert switcher.tab == "automations"
    assert switcher.selected_automation_id in [r.automation_id for r in switcher.automation_tab_rows]


@pytest.mark.basic
def test_without_a_gateway_default_new_automation_starts_on_the_conversation_workflow(palette, stub, monkeypatch) -> None:  # noqa: F811
    window, _controller = palette
    _with_gateway_default(window, monkeypatch, available=False)
    window._poll_automations()
    window._open_new_automation_sheet()
    sheet = window._schedule_sheet
    picker = sheet.workflow_picker
    assert picker.itemText(0) == "Gateway default"
    assert picker.currentData() == {"bundle_ref": "abstractassistant.agent@0.0.3", "flow_id": "main"}
    sheet.prompt_edit.setPlainText("Task")
    sheet.submit_button.click()
    assert stub.calls("POST", AUTOMATIONS_PATH)[-1]["body"]["target"]["bundle_ref"] == "abstractassistant.agent@0.0.3"


@pytest.mark.basic
def test_stop_fields_are_validated_and_only_for_a_repeating_schedule(palette, stub, monkeypatch) -> None:  # noqa: F811
    window, _controller = palette
    _with_gateway_default(window, monkeypatch)
    window._poll_automations()
    window._open_new_automation_sheet()
    sheet = window._schedule_sheet
    sheet.prompt_edit.setPlainText("Task")
    sheet.count_edit.setText("zero")
    body, errors = sheet.build_body()
    assert body is None and "Stop after this many runs must be a whole number of at least 1." in errors
    sheet.count_edit.setText("")
    sheet.until_edit.setText("tomorrow")
    body, errors = sheet.build_body()
    assert body is None and "Stop at must be a date and time (UTC)." in errors
    sheet.preset_combo.setCurrentIndex(sheet.preset_combo.findData("once"))
    assert not sheet.stop_host.isVisibleTo(sheet)
    sheet.at_edit.setText("2030-01-01 08:00")
    body, errors = sheet.build_body()
    assert not errors and body["trigger"]["config"] == {"start_at": "2030-01-01T08:00:00Z"}


def test_the_workflow_picker_lists_gateway_default_first_and_keeps_a_pinned_target() -> None:
    from test_automations import _qt

    _qt()
    combo = AutomationWorkflowCombo()
    # An automation pinned to research@1.0.0: selected (matches the catalog row), not retargeted.
    combo.set_workflows(MENU, {"bundle_ref": "research@1.0.0", "flow_id": "main"})
    assert combo.itemText(0) == "Gateway default"
    assert combo.currentText() == "Research workflow @1.0.0 — research"
    assert combo.retargeted() is False
    combo.setCurrentIndex(0)
    assert combo.retargeted() is True and combo.currentData() == {"flow_id": "@default", "interface": "abstractassistant.agent.v1"}
    # A target the catalog no longer lists stays as its own row.
    combo.set_workflows(MENU, {"bundle_ref": "gone@2", "flow_id": "x"})
    assert combo.currentText() == "gone@2:x" and combo.retargeted() is False
    # The gateway default target selects the first row.
    combo.set_workflows(MENU, {"flow_id": "@default", "interface": "abstractassistant.agent.v1"})
    assert combo.currentIndex() == 0 and combo.retargeted() is False
    assert [combo.itemText(i) for i in range(combo.count())].count("Gateway default") == 1
