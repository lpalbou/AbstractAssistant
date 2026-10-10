"""Round 11 Assistant Settings (R11-W4): Workspace = "My default workspaces"
(account) + "This chat" (session) on the kit WorkspaceChooser words; Voice
without the "Engines" card; Tools sorted by name and all collapsed; no Save
footer on any page; "Stream replies" a plain switch sent with every run.

Headless (QT_QPA_PLATFORM=offscreen), stub controller + a fake of the
gateway's workspace levels (r11_workspace_fake.py), no network.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QLabel, QPushButton

import test_settings_pages as tsp
from r11_workspace_fake import FakeWorkspaceGateway

from abstractassistant.ui.settings import workspace_chooser as wc
from abstractassistant.ui.settings.workspace_chooser import WORKSPACE_CHOOSER_TEXT as WT

PACKAGE = Path(__file__).resolve().parents[2] / "abstractassistant"


class _Ctl(tsp._Controller):
    def __init__(self, fake: FakeWorkspaceGateway = None, items=None):
        super().__init__()
        self._workspace_fake = fake or FakeWorkspaceGateway()
        self._items = items

    def tool_inventory(self):
        if self._items is None:
            return super().tool_inventory()
        return {"tool_mode": "approval", "items": self._items}


def _dialog(ctl=None):
    return tsp._dialog(ctl or _Ctl())


def _workspace(fake=None):
    ctl = _Ctl(fake)
    dlg, _ = _dialog(ctl)
    dlg.show_section("workspace")
    return dlg, ctl._workspace_fake, dlg.page_workspace


def _texts(widget) -> list:
    return [w.text() for w in widget.findChildren(QLabel) if w.isVisibleTo(widget)]


# --------------------------------------------------------------------------- #
# 1. Workspace — account level ("My default workspaces")


@pytest.mark.basic
def test_account_level_shows_the_gateway_line_and_follows_the_gateway_policy() -> None:
    dlg, fake, page = _workspace()
    acc = page.account
    assert acc.card.title_label.text() == "My default workspaces"
    assert acc.card.help_label.text() == WT["accountHelp"]
    assert acc.gateway_label.text() == "Gateway: Deny everything, allow listed workspaces · /data/project (rw) · /archive (ro)"
    assert acc.follow_switch.text() == "Follow the gateway policy"
    assert acc.follow_switch.isChecked()  # configured:false
    # Following: what applies is shown, read-only (no add row, no remove).
    assert set(acc.mode_controls) == {"/data/project", "/archive"}
    assert not any(c.isEnabled() for c in acc.mode_controls.values())
    assert acc.add_field is None and not acc.remove_buttons
    assert acc.effective_label.text() == "Deny everything, allow listed workspaces · /data/project (rw) · /archive (ro)"
    assert fake.puts == []


@pytest.mark.basic
def test_follow_off_puts_the_effective_rows_then_every_change_is_one_full_put() -> None:
    dlg, fake, page = _workspace()
    acc = page.account
    acc.follow_switch.click()  # off
    assert fake.puts[-1] == ("account", "session-1", {
        "configured": True, "posture": "allowed_only", "default_mode": "rw",
        "folders": [{"path": "/data/project", "mode": "rw"}, {"path": "/archive", "mode": "ro"}],
    })
    assert not acc.follow_switch.isChecked()
    assert acc.status_note.text() == WT["saved"]
    # The modes above the gateway's cap are disabled with the kit tooltip.
    archive = acc.mode_controls["/archive"]
    assert archive.isEnabled()
    assert not archive.option_enabled("rw") and archive.option_enabled("ro") and archive.option_enabled("deny")
    rw = next(b for b in archive._buttons if b.property("value") == "rw")
    assert rw.toolTip() == "The gateway allows this workspace read-only"
    assert acc.mode_controls["/data/project"].option_enabled("rw")
    # The kit's order and words, with "&" escaped for Qt.
    assert [b.text() for b in archive._buttons] == ["Read && write", "Read-only", "Refused"]
    # One row's mode: one PUT with the whole level.
    next(b for b in acc.mode_controls["/data/project"]._buttons if b.property("value") == "ro").click()
    assert fake.puts[-1][2]["folders"] == [{"path": "/data/project", "mode": "ro"}, {"path": "/archive", "mode": "ro"}]
    assert "/data/project (ro)" in acc.effective_label.text()
    # Remove: an icon button with the themed tooltip.
    remove = acc.remove_buttons["/archive"]
    assert remove.objectName() == "iconButton" and remove.text() == "" and remove.toolTip() == "Remove"
    remove.click()
    assert fake.puts[-1][2]["folders"] == [{"path": "/data/project", "mode": "ro"}]
    assert len(fake.puts) == 3


@pytest.mark.basic
def test_add_a_workspace_path_typed_or_chosen_and_the_refusal_is_the_gateway_sentence() -> None:
    fake = FakeWorkspaceGateway()
    fake.account = {"posture": "allowed_only", "default_mode": "rw", "folders": [{"path": "/data/project", "mode": "rw"}]}
    dlg, fake, page = _workspace(fake)
    acc = page.account
    assert acc.add_field.placeholderText() == "Add a workspace path"
    assert acc.choose_button.text() == "Choose…" and acc.add_button.text() == "Add"
    acc.add_field.setText("/data/project/sub")
    acc.add_button.click()
    # A new row starts Read-only under "Deny everything, allow listed workspaces".
    assert fake.puts[-1][2]["folders"][-1] == {"path": "/data/project/sub", "mode": "ro"}
    assert "/data/project/sub" in acc.mode_controls
    assert acc.add_field.text() == ""
    # Choose… opens the directory picker and adds what it returns.
    seen = {}
    page.choose_directory = lambda start: seen.setdefault("start", start) and "/archive/2024"
    acc.choose_button.click()
    assert seen["start"]
    assert fake.puts[-1][2]["folders"][-1] == {"path": "/archive/2024", "mode": "ro"}
    # A path outside the eligible set: the gateway's sentence + "Not saved.".
    before = len(acc.mode_controls)
    acc.add_field.setText("/etc")
    acc.add_field.returnPressed.emit()
    assert acc.status_note.text() == "/etc is outside the workspaces this gateway allows. Not saved."
    assert acc.status_note.property("workspace") == "refusal"
    assert len(acc.mode_controls) == before and "/etc" not in acc.mode_controls
    assert acc.add_field.text() == "/etc"  # the draft is kept to fix it


@pytest.mark.basic
def test_posture_and_everything_else_and_new_rows_refused_under_allow_everything() -> None:
    fake = FakeWorkspaceGateway()
    fake.account = {"posture": "allowed_only", "default_mode": "rw", "folders": []}
    dlg, fake, page = _workspace(fake)
    acc = page.account
    assert acc.posture_control.values() == ["allowed_only", "any_except_denied"]
    assert [b.text() for b in acc.posture_control._buttons] == [WT["postureAllowedOnly"], WT["postureAnyExceptDenied"]]
    assert acc.default_mode_control is None
    assert WT["emptyAllowed"] in _texts(acc.card)
    acc.posture_control._buttons[1].click()
    assert fake.puts[-1][2] == {"configured": True, "posture": "any_except_denied", "default_mode": "rw", "folders": []}
    # The top line stays the gateway's ceiling, verbatim; the effective line moves.
    assert acc.gateway_label.text() == "Gateway: Deny everything, allow listed workspaces · /data/project (rw) · /archive (ro)"
    assert acc.effective_label.text() == "Allow everything, refuse listed workspaces (rw)"
    assert acc.default_mode_control is not None
    next(b for b in acc.default_mode_control._buttons if b.property("value") == "ro").click()
    assert fake.puts[-1][2]["default_mode"] == "ro"
    acc.add_field.setText("/data/project/secret")
    acc.add_button.click()
    assert fake.puts[-1][2]["folders"] == [{"path": "/data/project/secret", "mode": "deny"}]


@pytest.mark.basic
def test_follow_on_sends_configured_false() -> None:
    fake = FakeWorkspaceGateway()
    fake.account = {"posture": "allowed_only", "default_mode": "rw", "folders": [{"path": "/archive", "mode": "ro"}]}
    dlg, fake, page = _workspace(fake)
    page.account.follow_switch.click()
    assert fake.puts[-1] == ("account", "session-1", {"configured": False})
    assert fake.account is None and page.account.follow_switch.isChecked()


@pytest.mark.basic
def test_locked_level_is_shown_not_changeable() -> None:
    fake = FakeWorkspaceGateway()
    fake.can_edit = False
    dlg, fake, page = _workspace(fake)
    assert not page.account.follow_switch.isEnabled()
    assert page.account.load_note.text() == WT["locked"]


# --------------------------------------------------------------------------- #
# 2. Workspace — session level ("This chat")


@pytest.mark.basic
def test_this_chat_uses_my_default_then_its_own_subset_on_the_session_route() -> None:
    fake = FakeWorkspaceGateway(session_id="sess-42")
    fake.account = {"posture": "allowed_only", "default_mode": "rw", "folders": [{"path": "/data/project", "mode": "rw"}]}
    dlg, fake, page = _workspace(fake)
    chat = page.session
    assert chat.card.title_label.text() == "This chat"
    assert chat.card.help_label.text() == WT["sessionHelp"]
    assert chat.follow_switch.text() == "Use my default" and chat.follow_switch.isChecked()
    assert chat.gateway_label.text().startswith("Gateway: ")
    assert WT["privateNote"] in _texts(chat.card)
    # Use my default off: the chat starts from the account default.
    chat.follow_switch.click()
    assert fake.puts[-1] == ("session", "sess-42", {
        "configured": True, "posture": "allowed_only", "default_mode": "rw",
        "folders": [{"path": "/data/project", "mode": "rw"}],
    })
    chat.add_field.setText("/archive")
    chat.add_button.click()
    assert fake.puts[-1][0] == "session" and fake.puts[-1][1] == "sess-42"
    assert fake.sessions["sess-42"]["folders"][-1] == {"path": "/archive", "mode": "ro"}
    assert fake.account["folders"] == [{"path": "/data/project", "mode": "rw"}]  # the account is untouched
    assert chat.effective_label.text() == "Deny everything, allow listed workspaces · /data/project (rw) · /archive (ro)"
    # Use my default on again: {configured: false} on the session route.
    chat.follow_switch.click()
    assert fake.puts[-1] == ("session", "sess-42", {"configured": False})


@pytest.mark.basic
def test_an_account_change_rereads_what_this_chat_follows() -> None:
    dlg, fake, page = _workspace()
    page.account.follow_switch.click()  # own subset = the gateway rows
    next(b for b in page.account.mode_controls["/data/project"]._buttons if b.property("value") == "deny").click()
    assert "/data/project (refused)" in page.session.effective_label.text()


@pytest.mark.basic
def test_no_shared_workspace_and_no_run_workspace_anywhere() -> None:
    dlg, fake, page = _workspace()
    page.account.follow_switch.click()
    words = " ".join(_texts(page)).lower()
    assert "shared" not in words and "folder" not in words
    assert not any(b.text() == "Save" for b in page.findChildren(QPushButton))
    assert not hasattr(page, "workspace_root_edit")
    assert not any("folder" in v.lower() or "shared" in v.lower() for v in WT.values())
    source = (PACKAGE / "ui/settings/workspace_chooser.py").read_text()
    assert "shared_workspace\" not in" in source  # an older answer is refused, never read
    assert not (PACKAGE / "ui/settings/workspace_folders.py").exists()


@pytest.mark.basic
def test_parsers_fail_loudly_on_an_older_gateway() -> None:
    with pytest.raises(wc.WorkspaceAnswerError):
        wc.parse_answer({"policy": {"default_mode": None, "folders": []}, "effective": {}})
    good = FakeWorkspaceGateway().answer("account")
    bad = json.loads(json.dumps(good))
    bad["effective"]["shared_workspace"] = "/srv/gw"
    with pytest.raises(wc.WorkspaceAnswerError):
        wc.parse_answer(bad)
    bad = json.loads(json.dumps(good))
    del bad["effective"]["folders"][0]["cap"]
    with pytest.raises(wc.WorkspaceAnswerError):
        wc.parse_answer(bad)
    assert wc.parse_answer(good)["effective"]["gateway_summary"].startswith("Deny everything")


@pytest.mark.basic
def test_refusal_reads_the_fastapi_wrapped_detail_from_the_real_client() -> None:
    from abstractassistant.gateway.client import GatewayHttpError, _read_error

    body = json.dumps({"detail": {"reason": "workspace_refused", "message": "The gateway allows /archive read-only.", "path": "/archive"}})
    text = _read_error(SimpleNamespace(read=lambda: body.encode()), label="x")
    assert wc.refusal(GatewayHttpError("x", status=400, body_text=text)) == "The gateway allows /archive read-only. Not saved."
    assert wc.refusal(GatewayHttpError("x", status=403, body_text="Only an admin can change it")) == "Only an admin can change it. Not saved."


@pytest.mark.basic
def test_controller_routes_each_level_to_its_gateway_path(monkeypatch) -> None:
    import threading

    from abstractassistant.controller import AssistantController
    from abstractassistant.gateway.client import GatewayClient

    client = GatewayClient.__new__(GatewayClient)
    seen = []
    monkeypatch.setattr(client, "_url", lambda path, query=None: f"{path}?{query}" if query else path)
    monkeypatch.setattr(client, "_request_json", lambda **kw: seen.append((kw["method"], kw["url"], kw.get("body"))) or {})
    client.workspace_account_policy("me")
    client.put_workspace_account_policy({"configured": False}, "me")
    client.session_workspaces("s/1")
    client.put_session_workspaces("s/1", {"configured": False})
    client.workspace_effective("me", session_id="s1")
    assert seen == [
        ("GET", "/api/gateway/workspace/policy/me", None),
        ("PUT", "/api/gateway/workspace/policy/me", {"configured": False}),
        ("GET", "/api/gateway/sessions/s%2F1/workspaces", None),
        ("PUT", "/api/gateway/sessions/s%2F1/workspaces", {"configured": False}),
        ("GET", "/api/gateway/workspace/effective/me?{'session': 's1'}", None),
    ]

    fake = FakeWorkspaceGateway(session_id="chat-7")
    calls = []
    ctl = AssistantController.__new__(AssistantController)
    ctl._cache_lock = threading.RLock()
    ctl._cache_epoch = 0
    ctl._cache_ttl_s = 20.0
    ctl._workspace_policy_cache = None
    ctl._workspace_policy_cache_at = 0.0
    ctl.llm_manager = SimpleNamespace(active_session_id="chat-7")
    ctl.gateway_service = SimpleNamespace(describe_connection_issue=str)
    ctl.gateway = SimpleNamespace(
        workspace_account_policy=lambda account="me": calls.append(("get-account", account)) or fake.answer("account"),
        session_workspaces=lambda sid: calls.append(("get-session", sid)) or fake.answer("session", sid),
        put_workspace_account_policy=lambda body, account="me": calls.append(("put-account", account)) or fake.answer("account"),
        put_session_workspaces=lambda sid, body: calls.append(("put-session", sid)) or fake.answer("session", sid),
    )
    out = ctl.workspace_policy()
    assert out["session"]["session_id"] == "chat-7" and out["account"]["state"]["policy"]["configured"] is False
    ctl.workspace_policy()  # cached
    assert calls == [("get-account", "me"), ("get-session", "chat-7")]
    ctl.put_workspace_policy("session", {"configured": False}, session_id="chat-7")
    ctl.put_workspace_policy("account", {"configured": False})
    assert calls[-2:] == [("put-session", "chat-7"), ("put-account", "me")]
    ctl.workspace_policy()  # a write drops the cache
    assert calls[-2:] == [("get-account", "me"), ("get-session", "chat-7")]
    with pytest.raises(ValueError):
        ctl.put_workspace_policy("session", {"configured": False}, session_id="")


# --------------------------------------------------------------------------- #
# 3. Voice: no "Engines" card


@pytest.mark.basic
def test_voice_tab_has_no_engines_card_and_keeps_the_device_and_reply_options() -> None:
    dlg, ctl = _dialog()
    dlg.show_section("voice")
    page = dlg.page_voice
    titles = [t.text() for t in page.findChildren(QLabel, "cardTitle")]
    assert "Engines" not in titles
    # Round 18: "Listening" holds the account's Spoken language (served by the gateway).
    assert titles == ["Output", "Replies", "Listening", "Voice conversation"]
    assert {b.text() for b in page.findChildren(QPushButton)} == {"Test"}
    for gone in ("tts_summary", "stt_summary", "tts_link", "stt_link", "navigate", "engine_summary"):
        assert not hasattr(page, gone), gone
    rows = [label.text() for label in page.findChildren(QLabel, "rowLabel")]
    assert rows == ["Output device", "Playing on", "Read aloud", "Voice latency", "Spoken language", "Sending", "Reply style", "Barge-in"]


# --------------------------------------------------------------------------- #
# 4. Tools: sorted by name, all collapsed


def _tool(name, toolset, *, default="ask", selected=None, available=True):
    return {
        "name": name, "toolset": toolset, "description": f"{name} does one thing.", "available": available,
        "risk_tier": "observe", "risk_rank": 1, "policy_default": default, "selected_mode": selected or default,
    }


TOOLS = [
    _tool("web_search", "web"),
    _tool("agora_post", "agora", available=False),  # all-disabled: no longer sinks to the end
    _tool("camera_capture_photo", "camera", selected="approve"),  # an override on this Mac
    _tool("read_file", "files", default="approve"),
    _tool("send_whatsapp", "comms.whatsapp"),
    _tool("send_email", "comms"),
    _tool("run_shell", "shell"),
]


@pytest.mark.basic
def test_tool_categories_are_sorted_by_name_and_all_collapsed() -> None:
    dlg, ctl = _dialog(_Ctl(items=TOOLS))
    dlg.show_section("tools")
    page = dlg.page_tools
    layout = page._groups
    order = [layout.itemAt(i).widget().toolset for i in range(layout.count())]
    assert order == sorted(order) == ["agora", "camera", "comms", "comms.whatsapp", "files", "shell", "web"]
    assert not any(g.is_open() for g in page.groups.values())  # the camera override too
    # The filter opens the panels with hits; clearing folds them again.
    page.search_edit.setText("send_")
    assert page.groups["comms"].is_open() and page.groups["comms.whatsapp"].is_open()
    assert not page.groups["web"].isVisibleTo(page)
    page.search_edit.setText("")
    assert not any(g.is_open() for g in page.groups.values())
    # A panel opened by hand stays open across a refresh.
    page.groups["shell"].toggle.click()
    page.refresh()
    assert page.groups["shell"].is_open() and not page.groups["camera"].is_open()


# --------------------------------------------------------------------------- #
# 5. No Save footer on any page


@pytest.mark.basic
def test_no_page_has_a_save_button_and_connection_keeps_connect() -> None:
    dlg, ctl = _dialog()
    for key, page in dlg.pages.items():
        labels = [b.text() for b in page.findChildren(QPushButton)]
        assert "Save" not in labels, key
        assert not any(b.text().startswith("Save") for b in page.actions()), key
    assert [b.text() for b in dlg.page_connection.actions()] == ["Reload status", "Sign out", "Connect"]
    for name in ("pages.py", "dialog.py", "route_editor.py", "common.py"):
        source = (PACKAGE / "ui/settings" / name).read_text()
        assert 'button("Save"' not in source and "save_button_workspace" not in source, name


@pytest.mark.basic
def test_refusals_on_every_settings_page_say_not_saved() -> None:
    sources = "".join((PACKAGE / "ui/settings" / n).read_text() for n in ("pages.py", "route_editor.py"))
    assert "Could not save" not in sources


# --------------------------------------------------------------------------- #
# 6. Stream replies: a plain switch, always sent


@pytest.mark.basic
def test_stream_replies_switch_is_on_by_default_and_the_run_always_carries_it(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.gateway.run_input import build_run_input_data

    dlg, ctl = _dialog()
    switch = dlg.page_models.stream_switch
    assert switch.isChecked() and switch.text() == "Stream replies"
    assert "Gateway default" not in " ".join(_texts(dlg.page_models.stream_switch.parentWidget()))

    controller = AssistantController(config=Config(), data_dir=tmp_path / "data")
    monkeypatch.setattr(controller, "gateway_streaming", lambda **kw: {"deltas": True, "default": False})
    assert controller.preferences.stream_replies == "on"
    assert build_run_input_data(prompt="x", stream=controller.run_scope()["stream"])["_runtime"]["stream"] is True
    controller.update_preferences(stream_replies="off", hotkey_enabled=False)
    monkeypatch.setattr(controller, "gateway_streaming", lambda **kw: {"deltas": True, "default": True})
    assert build_run_input_data(prompt="x", stream=controller.run_scope()["stream"])["_runtime"]["stream"] is False


@pytest.mark.basic
def test_cli_stream_help_names_the_switch() -> None:
    from abstractassistant.cli import create_parser

    run = next(a for a in create_parser()._subparsers._group_actions[0].choices["run"]._actions if "--stream" in a.option_strings)
    assert "Stream replies' switch (on unless switched off in Settings)" in run.help
    assert "gateway default" not in run.help.lower()
    assert "Gateway default" not in inspect.getsource(__import__("abstractassistant.cli", fromlist=["x"]))


@pytest.mark.basic
def test_the_per_turn_stream_pin_reads_the_cached_discovery_without_fetching() -> None:
    """Every turn's `stream` comes from the cached capabilities snapshot: no
    HTTP on the GUI thread and no refresh thread per message."""
    from abstractassistant.controller import AssistantController
    from abstractassistant.preferences import AssistantPreferences

    def no_fetch(**kw):
        raise AssertionError("a turn must not fetch discovery")

    ctl = AssistantController.__new__(AssistantController)
    ctl.preferences = AssistantPreferences()
    caps = SimpleNamespace(error="", raw={"streaming": {"deltas": True, "default": False}})
    ctl.llm_manager = SimpleNamespace(
        gateway_capabilities=no_fetch, peek_gateway_capabilities=lambda: caps, session_workspace_root=lambda: ""
    )
    assert ctl.run_scope()["stream"] is True
    assert ctl.stream_on_but_unsupported() is False
    caps.raw = {"streaming": {"deltas": False, "default": True}}
    assert ctl.run_scope()["stream"] is False
    assert ctl.stream_on_but_unsupported() is True
    ctl.llm_manager.peek_gateway_capabilities = lambda: None  # nothing cached yet
    assert ctl.run_scope()["stream"] is False
    assert ctl.stream_on_but_unsupported() is False
