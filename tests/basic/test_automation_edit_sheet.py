"""The automation editor (operator QA 2026-10-29: the inline form was unreadable and the tools
could not be set per tool). A sheet with What / When / How / Tools / Delivery; each offered tool
is Off / Ask / Auto (the kit's vocabulary); saving revises the definition's own approvals, and a
run waiting to approve calls whose every tool is now Auto continues without another click."""

from __future__ import annotations

import pytest

from abstractassistant.core.automations import (
    automation_tool_modes,
    tool_approval_line,
    tool_mode_changes,
    waits_cleared_by_modes,
)
from test_automations import AUTOMATIONS_PATH, NEWS, palette, stub  # noqa: F401  (fixtures)
import test_automations

TOOLS = ["fetch_url", "skim_url", "skim_websearch", "web_search"]
# The operator's automation as the iPhone created it: Ask, no per-tool policy.
DEFINITION = {
    "target": {"bundle_ref": "basic-agent@0.0.5", "flow_id": "81795ea9",
               "input_data": {"prompt": "US pharma news", "tools": list(TOOLS), "_runtime": {"allowed_tools": list(TOOLS), "model": "m"}}},
    "policy": {"tool_approval": "ask"},
    "notify": {"channels": ["console"]},
}
INVENTORY = {"items": [{"name": n, "available": True, "toolset": "web"} for n in [*TOOLS, "write_file"]]}


@pytest.mark.basic
def test_modes_read_like_the_runtime_and_the_iphone() -> None:
    modes = automation_tool_modes(DEFINITION, ["write_file"])
    assert modes == {"write_file": "off", **{n: "ask" for n in TOOLS}}
    named = {**DEFINITION, "policy": {"tool_approval": "ask", "tool_policy": {"auto_approve_tools": ["fetch_url"], "require_approval_tools": ["skim_url"]}}}
    assert automation_tool_modes(named)["fetch_url"] == "auto" and automation_tool_modes(named)["skim_url"] == "ask"
    assert automation_tool_modes(named)["web_search"] == "ask", "a tool in neither list asks"
    assert automation_tool_modes({**DEFINITION, "policy": {"tool_approval": "auto"}})["web_search"] == "auto"
    assert tool_approval_line(modes) == "Asks before each of its 4 tools"
    assert tool_approval_line({n: "auto" for n in TOOLS}) == "Runs its 4 tools without asking"
    assert tool_approval_line({"a": "auto", "b": "ask", "c": "off"}) == "Asks before 1 of its 2 tools"


@pytest.mark.basic
def test_mode_changes_store_the_definitions_own_approvals() -> None:
    modes = {"fetch_url": "auto", "skim_url": "ask", "skim_websearch": "auto", "web_search": "off"}
    changes = tool_mode_changes(DEFINITION, modes)
    data = changes["target"]["input_data"]
    assert data["tools"] == ["fetch_url", "skim_url", "skim_websearch"] == data["_runtime"]["allowed_tools"]
    assert data["prompt"] == "US pharma news" and data["_runtime"]["model"] == "m", "every other input is kept"
    assert changes["policy"] == {"tool_policy": {"auto_approve_tools": ["fetch_url", "skim_websearch"], "require_approval_tools": ["skim_url"]}, "tool_approval": "ask"}
    assert tool_mode_changes(DEFINITION, {n: "auto" for n in TOOLS})["policy"]["tool_approval"] == "auto"


@pytest.mark.basic
def test_waits_split_by_the_new_modes() -> None:
    wait = {"run_id": "r1", "wait_key": "tool_approval:r1:act:x", "kind": "tool_approval",
            "details": [{"name": "fetch_url"}, {"name": "fetch_url"}, {"name": "skim_websearch"}]}
    summary = {"attention": {"waits": [wait, {"run_id": "r2", "wait_key": "ask_user:q", "kind": "ask_user"}]}}
    resume, still = waits_cleared_by_modes(summary, {"fetch_url": "auto", "skim_websearch": "auto"})
    assert [w["run_id"] for w in resume] == ["r1"] and still == []
    resume, still = waits_cleared_by_modes(summary, {"fetch_url": "auto", "skim_websearch": "ask"})
    assert resume == [] and still[0][1] == ["skim_websearch"]


def _open_editor(window, stub, *, waits=None):
    window._poll_automations()
    if waits is not None:
        att = stub.summary(NEWS)["attention"]
        att["waits"] = waits
        att["pending_waits"] = len(waits)
        window._poll_automations()
    window._open_automation(NEWS)
    view = window.automation_view
    view.control_buttons["revise"].click()
    view.set_edit_definition({"definition": DEFINITION}, INVENTORY)
    return view


@pytest.mark.basic
def test_the_editor_is_a_sheet_with_sections_and_per_tool_modes(palette, stub) -> None:
    window, _ = palette
    view = _open_editor(window, stub)
    sheet = view.edit_box
    assert sheet.isVisibleTo(view) and sheet.isWindow(), "a sheet, not a form drawn over the conversation"
    assert list(sheet.sections) == ["what", "when", "how", "tools", "delivery"]
    assert view.edit_prompt.toPlainText() == "US pharma news"
    assert view.edit_workflow.currentText() == "basic-agent 0.0.5", "the workflow by its readable name (ADR 0043)"
    assert sorted(view.edit_tool_controls) == TOOLS and "write_file" not in view.edit_tool_controls
    assert all(c.value() == "ask" for c in view.edit_tool_controls.values())
    assert view.edit_tools_state.text() == "Asks before each of its 4 tools"
    control = view.edit_tool_controls["fetch_url"]
    assert [b.toolTip() for b in control._buttons] == ["Off: not offered to the run", "Ask: the run waits for your approval", "Auto: runs without asking"]
    assert all(not b.icon().isNull() and not b.text() for b in control._buttons), "icons, the words in tooltips"
    assert view.edit_save.isVisible() and view.edit_cancel.isVisible()


@pytest.mark.basic
def test_per_tool_modes_save_into_the_definition(palette, stub) -> None:
    window, _ = palette
    view = _open_editor(window, stub)
    for name in ("fetch_url", "skim_websearch"):
        view.edit_tool_controls[name].set_value("auto")
        view._on_tool_mode(name, "auto")
    assert view.edit_tools_state.text() == "Asks before 2 of its 4 tools"
    view.edit_save.click()
    changes = stub.calls("PATCH")[-1]["body"]["changes"]
    assert changes["policy"] == {"tool_policy": {"auto_approve_tools": ["fetch_url", "skim_websearch"], "require_approval_tools": ["skim_url", "web_search"]}, "tool_approval": "ask"}
    assert changes["target"]["input_data"]["tools"] == TOOLS


@pytest.mark.basic
def test_a_waiting_run_whose_tools_are_set_to_auto_continues(palette, stub) -> None:
    """The operator's case: a run waits to approve fetch_url and skim_websearch; setting both to
    Auto and saving continues it (setting them to Auto is the approval) with no click on its card."""
    app = test_automations._APP
    window, _ = palette
    wait = {"run_id": "run-waiting", "wait_key": "tool_approval:run-waiting:act:k", "kind": "tool_approval", "reason": "user",
            "details": [{"name": "fetch_url"}, {"name": "fetch_url"}, {"name": "skim_websearch"}]}
    view = _open_editor(window, stub, waits=[wait])
    for name in TOOLS:
        view.edit_tool_controls[name].set_value("auto")
        view._on_tool_mode(name, "auto")
    view.edit_save.click()
    for _ in range(200):
        app.processEvents()
        if [c for c in stub.calls("POST", "/api/gateway/commands") if c["body"].get("run_id") == "run-waiting"]:
            break
        import time
        time.sleep(0.01)
    sent = [c["body"] for c in stub.calls("POST", "/api/gateway/commands") if c["body"].get("run_id") == "run-waiting"]
    assert sent and sent[0]["type"] == "resume" and sent[0]["payload"]["wait_key"] == wait["wait_key"]
    assert sent[0]["payload"]["payload"] == {"approved": True}


@pytest.mark.basic
def test_a_run_still_waiting_says_which_tools_keep_it_waiting(palette, stub) -> None:
    app = test_automations._APP
    window, _ = palette
    wait = {"run_id": "run-waiting", "wait_key": "tool_approval:run-waiting:act:k", "kind": "tool_approval", "reason": "user",
            "details": [{"name": "fetch_url"}, {"name": "skim_websearch"}]}
    view = _open_editor(window, stub, waits=[wait])
    view.edit_tool_controls["fetch_url"].set_value("auto")
    view._on_tool_mode("fetch_url", "auto")
    view.edit_save.click()
    for _ in range(100):
        app.processEvents()
    assert not [c for c in stub.calls("POST", "/api/gateway/commands") if c["body"].get("run_id") == "run-waiting"]
    assert "1 run still waits: skim_websearch is on Ask." in view.notice_label.text()
