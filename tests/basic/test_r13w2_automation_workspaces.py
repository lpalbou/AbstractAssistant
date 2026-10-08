"""Round 13 (DESIGN R13.2): the Assistant's schedule sheet and an
automation's Edit box get a visible "Workspaces" section — the ONE
WorkspaceChooser at the run level, the same rows and words as Settings →
Workspace and the web apps (kit table) — whose value rides the definition as
``target.input_data.workspace`` (absent = "Use my default"). Each change is
the gateway's dry run (a refusal = its sentence + "Not saved.", the value
stays); the form's own action stores it. The automation view shows one line,
"Workspaces: <the gateway's summary>". No "Advanced" anywhere.

Headless (QT_QPA_PLATFORM=offscreen), the fake of the gateway's workspace
levels (r11_workspace_fake.py), no network.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLabel

from r11_workspace_fake import FakeWorkspaceGateway

from abstractassistant.ui import automation_workspaces as aw
from abstractassistant.ui.settings.workspace_chooser import WORKSPACE_CHOOSER_TEXT as WT, parse_effective

PACKAGE = Path(__file__).resolve().parents[2] / "abstractassistant"
TARGET = {"bundle_ref": "basic-agent@0.0.5", "flow_id": "main", "input_data": {"prompt": "Sort the photos"}}
GATEWAY_LINE = "Gateway: Deny everything, allow listed workspaces · /data/project (rw) · /archive (ro)"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _dry(fake: FakeWorkspaceGateway):
    return lambda value: parse_effective(fake.dry_run(value))


def _sheet(fake: FakeWorkspaceGateway):
    from abstractassistant.ui.automations import ScheduleSheet

    sheet = ScheduleSheet(target=TARGET, target_label="Agent", prompt="Sort the photos", preview=lambda trigger, done: done(True, {"time_zone": "Europe/Paris", "first_run_sentence": "Runs (test preview)."}))
    sheet.set_trigger_sources([{"id": "schedule", "version": 1, "available": True}])
    sheet.workspaces.set_dry_run(_dry(fake))
    sheet.workspaces.load(None)
    return sheet


def _labels(widget) -> list:
    return [w.text() for w in widget.findChildren(QLabel) if w.isVisibleTo(widget) and w.text()]


# --------------------------------------------------------------------------- the sheet


@pytest.mark.basic
def test_the_sheet_shows_workspaces_visibly_after_tools_and_before_the_mailbox(app) -> None:
    fake = FakeWorkspaceGateway()
    sheet = _sheet(fake)
    sheet.show()
    level = sheet.workspaces.level
    assert sheet.workspaces.card.isVisibleTo(sheet)
    assert level.card.title_label.text() == "Workspaces" == WT["title"]
    assert level.card.help_label.text() == WT["runHelp"]
    assert level.gateway_label.text() == GATEWAY_LINE
    assert level.follow_switch.text() == "Use my default" and level.follow_switch.isChecked()
    assert level.effective_label.text() == "Deny everything, allow listed workspaces · /data/project (rw) · /archive (ro)"
    layout = sheet.form_body.layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert order.index(sheet.tool_picker) < order.index(sheet.workspaces.card) < order.index(sheet.notify_email)
    # No disclosure, no "Advanced", anywhere in the sheet.
    assert not any("Advanced" in t for t in _labels(sheet))
    assert "Advanced" not in (PACKAGE / "ui" / "automations.py").read_text(encoding="utf-8")
    sheet.close()


@pytest.mark.basic
def test_use_my_default_sends_no_workspace_and_a_chosen_subset_rides_the_create_body(app) -> None:
    fake = FakeWorkspaceGateway()
    sheet = _sheet(fake)
    body, errors = sheet.build_body()
    assert errors == [] and "workspace" not in body["target"]["input_data"]
    level = sheet.workspaces.level
    level.follow_switch.click()  # off: start from what applies now
    assert sheet.workspaces.value == {"posture": "allowed_only", "default_mode": "rw", "folders": [{"path": "/data/project", "mode": "rw"}, {"path": "/archive", "mode": "ro"}]}
    level.mode_controls["/data/project"].set_value("ro")
    level.mode_controls["/data/project"].changed.emit("ro")
    assert sheet.workspaces.value["folders"][0] == {"path": "/data/project", "mode": "ro"}
    level.status = None
    body, errors = sheet.build_body()
    assert body["target"]["input_data"]["workspace"] == sheet.workspaces.value
    assert body["target"]["input_data"]["prompt"] == "Sort the photos"
    assert fake.puts == []  # nothing is PUT: the dry run only
    assert fake.dry_runs[-1] == sheet.workspaces.value
    # Nothing is stored yet: no "Saved" status on a draft.
    assert WT["saved"] not in _labels(sheet.workspaces.card)
    # Back to "Use my default": the payload goes.
    level = sheet.workspaces.level
    level.follow_switch.click()
    assert sheet.workspaces.value is None
    body, _ = sheet.build_body()
    assert "workspace" not in body["target"]["input_data"]


@pytest.mark.basic
def test_a_refused_path_shows_the_gateways_sentence_and_the_value_stays(app) -> None:
    fake = FakeWorkspaceGateway()
    sheet = _sheet(fake)
    sheet.workspaces.level.follow_switch.click()
    before = dict(sheet.workspaces.value)
    assert sheet.workspaces.level.add_path("/etc") is False
    status = sheet.workspaces.level.status_note
    assert status.isVisibleTo(sheet.workspaces.card) or status.text()
    assert status.text() == "/etc is outside the workspaces this gateway allows. Not saved."
    assert sheet.workspaces.value == before
    body, _ = sheet.build_body()
    assert body["target"]["input_data"]["workspace"] == before


@pytest.mark.basic
def test_modes_above_the_cap_are_disabled_with_the_gateways_tooltip(app) -> None:
    fake = FakeWorkspaceGateway()
    sheet = _sheet(fake)
    sheet.workspaces.level.follow_switch.click()
    archive = sheet.workspaces.level.mode_controls["/archive"]
    assert not archive.option_enabled("rw")
    rw = [b for b in archive._buttons if b.property("value") == "rw"][0]
    assert rw.toolTip() == WT["capReadOnly"]


# --------------------------------------------------------------------------- the Edit box


def _view(app):
    from abstractassistant.ui.automations import AutomationView

    view = AutomationView(render_turn=lambda *a, **k: QLabel(""), bubble_width=lambda: 400)
    summary = {"automation_id": "a1", "title": "Sort photos", "status": "active", "revision": 3, "trigger": {"source_id": "schedule", "source_version": 1, "config": {"every": "24h"}}, "context": {"mode": "independent"}, "attention": {"items": [], "waits": []}, "occurrence_count": 0, "controls": {}}
    view.set_summary(summary)
    return view


@pytest.mark.basic
def test_edit_box_round_trip_stores_the_new_workspaces_in_one_revision(app) -> None:
    fake = FakeWorkspaceGateway()
    view = _view(app)
    stored = {"posture": "allowed_only", "default_mode": "rw", "folders": [{"path": "/data/project", "mode": "rw"}]}
    definition = {"revision": 3, "target": {**TARGET, "input_data": {"prompt": "x", "workspace": stored, "workspace_allowed_paths": ["/data/project"], "workspace_access_mode": "workspace_or_allowed"}}, "notify": {"channels": ["console"]}}
    view.set_edit_definition({"definition": definition}, {})
    assert view.edit_workspace_base == stored
    view.edit_workspaces.set_dry_run(_dry(fake))
    view.edit_workspaces.load(view.edit_workspace_base)
    level = view.edit_workspaces.level
    assert not level.follow_switch.isChecked()
    assert list(level.mode_controls) == ["/data/project"]
    # Unchanged workspaces: Save sends no target.
    emitted = []
    view.revise_requested.connect(emitted.append)
    view.edit_title.setText("Sort photos daily")
    view._save_edit()
    assert "target" not in emitted[-1]
    # Change: add /archive (read-only); Save = one revision with the payload, derived keys dropped.
    view.edit_box.show()
    assert level.add_path("/archive") is True
    view._save_edit()
    target = emitted[-1]["target"]
    assert target["bundle_ref"] == "basic-agent@0.0.5" and target["flow_id"] == "main"
    assert target["input_data"]["workspace"] == {"posture": "allowed_only", "default_mode": "rw", "folders": [{"path": "/data/project", "mode": "rw"}, {"path": "/archive", "mode": "ro"}]}
    assert "workspace_allowed_paths" not in target["input_data"] and "workspace_access_mode" not in target["input_data"]
    # "Use my default" on an existing automation removes the payload.
    view.set_edit_definition({"definition": definition}, {})
    view.edit_workspaces.load(view.edit_workspace_base)
    view.edit_workspaces.level.follow_switch.click()
    view._save_edit()
    assert "workspace" not in emitted[-1]["target"]["input_data"]


@pytest.mark.basic
def test_the_view_shows_one_workspaces_line(app) -> None:
    view = _view(app)
    view.set_workspaces_summary("Deny everything, allow listed workspaces · /data/project (rw)")
    assert view.workspaces_label.text() == "Workspaces: Deny everything, allow listed workspaces · /data/project (rw)"
    view.set_workspaces_summary("")
    assert view.workspaces_label.text() == ""


# --------------------------------------------------------------------------- helpers + wiring


@pytest.mark.basic
def test_helpers_and_the_app_wiring() -> None:
    assert aw.TITLE == WT["title"]
    assert aw.workspaces_line("S") == "Workspaces: S"
    stored = {"posture": "allowed_only", "default_mode": "rw", "folders": [{"path": "/p", "mode": "rw"}]}
    assert aw.automation_workspace({"target": {"input_data": {"workspace": stored}}}) == stored
    assert aw.automation_workspace({"target": {"input_data": {}}}) is None
    # The gateway's "follow my default at each run" marker reads as Use my default.
    assert aw.automation_workspace({"target": {"input_data": {"workspace": {"configured": False}}}}) is None
    assert aw.with_workspace({"a": 1, "workspace_allowed_paths": ["/p"]}, None) == {"a": 1}
    state = aw.run_state(None, {"posture": "allowed_only", "default_mode": "rw", "folders": [], "summary": "s", "gateway_summary": "g"})
    assert state["policy"]["configured"] is False
    app_src = (PACKAGE / "app.py").read_text(encoding="utf-8")
    assert "self._load_run_workspaces(sheet.workspaces, None)" in app_src
    assert "self._load_run_workspaces(self.automation_view.edit_workspaces, self.automation_view.edit_workspace_base)" in app_src
    assert "view.set_workspaces_summary(" in app_src
    ctl_src = (PACKAGE / "controller.py").read_text(encoding="utf-8")
    assert "parse_effective(self.gateway.workspace_dry_run(workspace, \"me\"))" in ctl_src


@pytest.mark.basic
def test_the_client_dry_run_is_one_post_with_the_payload(monkeypatch) -> None:
    from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig

    calls = []
    client = GatewayClient(GatewayClientConfig(base_url="http://gw.test", auth_token="t", timeout_s=1.0))
    monkeypatch.setattr(client, "_request_json", lambda **kw: calls.append(kw) or {"ok": True})
    client.workspace_dry_run({"posture": "allowed_only", "default_mode": "rw", "folders": []})
    client.workspace_dry_run(None)
    assert calls[0]["method"] == "POST" and calls[0]["url"].endswith("/api/gateway/workspace/effective/me")
    assert calls[0]["body"] == {"workspace": {"posture": "allowed_only", "default_mode": "rw", "folders": []}}
    assert calls[1]["body"] == {"workspace": None}
