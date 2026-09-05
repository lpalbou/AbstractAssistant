"""Settings window: sidebar pages, reasoning dial, workspace grant, tools page."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from abstractassistant.gateway_service import CapabilityRouteRow, ChoiceItem
from abstractassistant.preferences import AssistantPreferences
from abstractassistant.ui.settings import SettingsDialog, ToolSettingsDialog


_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class _Controller:
    """A controller with the full new surface (reasoning, workspace, tools)."""

    def __init__(self) -> None:
        self.preferences = AssistantPreferences(hotkey_enabled=False)
        self.saved_tool_prefs: dict = {}
        self.overrides: dict = {}
        self.data_dir = "/tmp/assistant-test"
        self.llm_manager = SimpleNamespace(
            gateway_capabilities=lambda **kw: SimpleNamespace(
                raw={"abstractgateway": {"installed": True, "version": "0.2.29"}, "contracts": {"version": 1}},
                common={},
            ),
            session_workspace_root=lambda: "",
        )
        self.voice_manager = SimpleNamespace(output_device_label=lambda: "MacBook Pro Speakers", output_volume_state=lambda: (62, False))

    # connection
    def current_connection(self):
        return SimpleNamespace(base_url="http://127.0.0.1:8080", auth_mode="bearer", auth_token="t", user_id="admin", remember_session=True, session_id="")

    def connection_status(self):
        return {"ok": True, "principal": {"user_id": "admin", "tenant_id": "default", "roles": ["admin"]}, "auth": {"mode": "users"}, "routing": {"mode": "per-principal"}}

    # routes
    def route_map(self, **kwargs):
        return {
            "output.text": CapabilityRouteRow(key="output.text", label="Text Output", kind="output", modality="text", task="", provider="lmstudio", model="qwen/qwen3.8-27b", configured=True),
        }

    def route_override(self, key):
        return self.overrides.get(key)

    def save_route_override(self, **kwargs):
        self.overrides[kwargs["route_key"]] = {"provider": kwargs["provider"], "model": kwargs["model"]}

    def clear_route_override(self, *, route_key):
        self.overrides.pop(route_key, None)

    def provider_choices(self, **kwargs):
        return [ChoiceItem(id="lmstudio", label="lmstudio")]

    def model_choices(self, **kwargs):
        return [ChoiceItem(id="qwen/qwen3.8-27b", label="qwen/qwen3.8-27b")]

    def voice_choices(self, **kwargs):
        return []

    def parse_options(self, text):
        return {}

    # reasoning / workspace / tools
    def reasoning_levels(self):
        return ["none", "low", "medium", "high"]

    def effective_chat_route(self):
        return {"provider": "lmstudio", "model": "qwen/qwen3.8-27b", "source": "gateway"}

    def model_capabilities(self, model):
        return {"thinking_support": True, "reasoning_levels": ["low", "medium", "xhigh"]}

    def workspace_policy(self):
        return {
            "policy": {"allowed_access_modes": ["workspace_only", "workspace_or_allowed"], "mounts": [], "trust_client_launch_folder": True},
            "self": {"customized": False, "effective": {"mode": "whitelist", "client_workspace_scope_overrides": True, "workspace_allowed_paths": [], "workspace_blocked_paths": []}},
            "error": "",
        }

    def workspace_access_modes(self):
        return ["workspace_only", "workspace_or_allowed"]

    def workspace_root_status(self):
        return {"root": self.preferences.workspace_root, "source": "local" if self.preferences.workspace_root else "gateway"}

    def tool_inventory(self):
        return {
            "tool_mode": "approval",
            "note": "",
            "items": [
                {"name": "read_file", "toolset": "files", "description": "Read a file.", "available": True, "risk_tier": "observe", "approval_default": "auto", "policy_default": "approve", "selected_mode": "approve"},
                {"name": "execute_command", "toolset": "system", "description": "Run a shell command.", "available": True, "risk_tier": "destroy", "mutating": True, "destructive_capable": True, "approval_default": "ask", "policy_default": "ask", "selected_mode": "ask"},
                {"name": "send_email", "toolset": "comms.email", "description": "Send an email.", "available": False, "risk_tier": "outreach", "comms_send": True, "approval_default": "ask", "policy_default": "ask", "selected_mode": "ask"},
            ],
        }

    def save_tool_preferences(self, statuses):
        self.saved_tool_prefs = dict(statuses)

    def current_workflow(self):
        return SimpleNamespace(bundle_id="abstractassistant-orchestrator", bundle_version="0.0.1", registry_scope="tenant_catalog")

    # prefs
    def update_preferences(self, **updates):
        payload = self.preferences.to_dict()
        payload.update(updates)
        self.preferences = AssistantPreferences.from_dict(payload)
        return self.preferences

    def save_preferences(self, prefs):
        self.preferences = prefs


def _dialog(controller=None):
    _app()
    ctl = controller or _Controller()
    return SettingsDialog(controller=ctl, apply_hotkey=lambda: None, parent=None), ctl


@pytest.mark.basic
def test_sidebar_has_seven_sections_and_switches_pages() -> None:
    dlg, _ctl = _dialog()
    assert [dlg.nav.item(i).data(0x0100) for i in range(dlg.nav.count())] == list(SettingsDialog.SECTIONS)
    dlg.show_section("workspace")
    assert dlg.current_section() == "workspace"
    assert dlg.stack.currentWidget() is dlg.page_workspace
    dlg.show_section("models", "output.text")
    assert dlg.current_section() == "models"
    assert dlg.route_list.currentRow() == 0


@pytest.mark.basic
def test_reasoning_dial_reflects_gateway_levels_and_saves_locally() -> None:
    dlg, ctl = _dialog()
    control = dlg.page_models.reasoning_control
    assert control.values() == ["", "none", "low", "medium", "high"]
    assert control.value() == ""  # gateway default until chosen
    dlg.page_models._on_reasoning_changed("high")
    assert ctl.preferences.reasoning_effort == "high"
    note = dlg.page_models.reasoning_note.text()
    assert "qwen/qwen3.8-27b" in note and "low, medium, xhigh" in note
    assert "Currently sending: High" in note


@pytest.mark.basic
def test_reasoning_dial_falls_back_to_the_contract_ladder_without_a_gateway() -> None:
    ctl = _Controller()
    ctl.reasoning_levels = lambda: []  # type: ignore[method-assign]
    dlg, _ = _dialog(ctl)
    assert dlg.page_models.reasoning_control.values() == ["", "none", "minimal", "low", "medium", "high", "xhigh"]


@pytest.mark.basic
def test_workspace_page_refuses_relative_paths_and_auto_switches_mode() -> None:
    dlg, ctl = _dialog()
    page = dlg.page_workspace
    dlg.show_section("workspace")
    assert [page.workspace_mode_combo.itemData(i) for i in range(page.workspace_mode_combo.count())] == ["", "workspace_only", "workspace_or_allowed"]

    assert page._add_path("relative/dir") is False
    assert "absolute" in page.feedback.text().lower()
    assert page._add_path("/srv/data/") is True
    assert page.workspace_mode_combo.currentData() == "workspace_or_allowed"
    assert page._add_path("/srv/data") is False  # duplicate

    page.workspace_root_edit.setText("~/site")
    page._save()
    assert ctl.preferences.workspace_root.endswith("/site") and ctl.preferences.workspace_root.startswith("/")
    assert ctl.preferences.workspace_access_mode == "workspace_or_allowed"
    assert ctl.preferences.workspace_allowed_paths == ["/srv/data"]
    assert "Next run works in your folder" in page.current_note.text()

    page._reset()
    assert ctl.preferences.workspace_root == ""
    assert ctl.preferences.workspace_allowed_paths == []


@pytest.mark.basic
def test_workspace_page_shows_the_gateway_policy_read_only() -> None:
    dlg, _ = _dialog()
    dlg.show_section("workspace")
    text = dlg.page_workspace.policy_lines.text()
    assert "Your posture: whitelist" in text
    assert "Client scope overrides: allowed" in text
    assert "workspace_only, workspace_or_allowed" in text


@pytest.mark.basic
def test_tools_page_shows_gateway_risk_and_saves_only_tool_preferences() -> None:
    dlg, ctl = _dialog()
    dlg.show_section("tools")
    page = dlg.page_tools
    rows = page._rows
    assert set(rows) == {"read_file", "execute_command", "send_email"}
    assert rows["send_email"]["available"] is False
    assert not rows["send_email"]["control"].isEnabled()
    assert rows["execute_command"]["control"].value() == "ask"
    rows["read_file"]["control"].set_value("ask")
    page._save()
    # Only rows that differ from the gateway's default are stored: a tool left
    # on its default keeps following the gateway if that default changes.
    assert ctl.saved_tool_prefs == {"read_file": "ask"}
    page._reset_defaults()
    assert rows["read_file"]["control"].value() == "approve"


@pytest.mark.basic
def test_voice_page_saves_conversation_options() -> None:
    dlg, ctl = _dialog()
    dlg.show_section("voice")
    page = dlg.page_voice
    assert "MacBook Pro Speakers" in page.device_summary.text()
    page.voice_mode_full.setChecked(True)
    page.voice_auto_send.setChecked(False)
    page._save()
    assert ctl.preferences.voice_mode == "full"
    assert ctl.preferences.voice_auto_send is False


@pytest.mark.basic
def test_window_page_and_about_page_render_from_controller_truth() -> None:
    dlg, ctl = _dialog()
    dlg.show_section("window")
    dlg.width_spin.setValue(800)
    dlg.page_window._save_preferences()
    assert ctl.preferences.window_width == 800
    dlg.show_section("about")
    assert "abstractgateway 0.2.29" in dlg.page_about.stack_label.text()
    assert "abstractassistant-orchestrator" in dlg.page_about.workflow_label.text()


@pytest.mark.basic
def test_tool_settings_dialog_shim_opens_the_tools_page() -> None:
    _app()
    dlg = ToolSettingsDialog(controller=_Controller(), parent=None)
    assert dlg.current_section() == "tools"


@pytest.mark.basic
def test_settings_dialog_uses_the_shared_stylesheet_without_gradients() -> None:
    dlg, _ = _dialog()
    sheet = dlg.styleSheet()
    assert "QListWidget#navList" in sheet
    assert "qlineargradient" not in sheet
