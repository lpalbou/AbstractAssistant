"""Settings window: sidebar pages, reasoning dial, workspace grant, tools page."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
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
def test_reasoning_belongs_to_the_chat_model_not_the_page() -> None:
    """Reasoning is a property of the model that reasons — it sits in the chat
    route's own form, beside its provider and model, and is not offered for a
    voice, image, video, music or sound-effect model."""
    dlg, ctl = _dialog()
    editor = dlg.page_models.route_editor
    assert not hasattr(dlg.page_models, "reasoning_control"), "no page-level dial"

    dlg.show_section("models", "output.text")
    assert editor.reasoning_combo.isVisibleTo(editor)
    assert editor.reasoning_label.isVisibleTo(editor)
    combo = editor.reasoning_combo
    values = [combo.itemData(i) for i in range(combo.count())]
    assert values == ["", "none", "low", "medium", "high"]
    assert combo.currentData() == ""  # gateway default until chosen
    editor._on_reasoning_changed("high")
    assert ctl.preferences.reasoning_effort == "high"
    note = editor.reasoning_note.text()
    assert "qwen/qwen3.8-27b" in note and "low, medium, xhigh" in note
    assert "Currently sending: High" in note

    # Every other route hides it: none of those models reasons.
    for key in ("output.voice", "input.voice", "output.image", "output.video", "output.music"):
        rows = [r for r in editor.rows() if r.key == key]
        if not rows:
            continue
        dlg.show_section("models", key)
        assert not editor.reasoning_combo.isVisibleTo(editor), key
        assert not editor.reasoning_label.isVisibleTo(editor), key


@pytest.mark.basic
def test_reasoning_dial_falls_back_to_the_contract_ladder_without_a_gateway() -> None:
    ctl = _Controller()
    ctl.reasoning_levels = lambda: []  # type: ignore[method-assign]
    dlg, _ = _dialog(ctl)
    editor = dlg.page_models.route_editor
    combo = editor.reasoning_combo
    assert [combo.itemData(i) for i in range(combo.count())] == [
        "", "none", "minimal", "low", "medium", "high", "xhigh"
    ]


@pytest.mark.basic
def test_mtp_selector_preserves_off_and_rejects_stale_discovery(tmp_path) -> None:
    dlg, ctl = _dialog()
    dlg.show_section("models", "output.text")
    editor = dlg.page_models.route_editor
    combo = editor.speculation_combo
    assert [combo.itemData(i) for i in range(combo.count())] == [None, False]
    assert "unknown" in editor.speculation_note.text()
    payload = {"execution": {"speculation": {
        "supported": True, "ready": False, "reason": "head_not_loaded",
        "supported_depths": [2, 3, 4, 5], "default": {"mode": "native_mtp", "num_draft_tokens": 2},
        "requires_reload": True,
    }}}
    editor._apply_speculation_payload(editor._speculation_epoch, payload)
    assert combo.count() == 6
    assert "depth 2" in combo.itemText(0)
    combo.setCurrentIndex(1)
    assert ctl.preferences.speculation is False
    editor._apply_speculation_payload(editor._speculation_epoch - 1, {})
    assert combo.count() == 6
    assert combo.currentData() is False
    combo.setCurrentIndex(3)
    assert ctl.preferences.speculation == {"mode": "native_mtp", "num_draft_tokens": 3, "require_acceleration": True}
    editor._apply_speculation_payload(editor._speculation_epoch, {})
    assert combo.currentText() == "Depth 3 (saved; unavailable)"
    combo.setCurrentIndex(0)
    assert ctl.preferences.speculation is None
    editor._apply_speculation_payload(editor._speculation_epoch, payload)
    dlg.show()
    _app().processEvents()
    assert editor.grab().save(str(tmp_path / "assistant-mtp-selector.png"))
    dlg.close()


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
    # Barge-in is a list, like every other choice on the page (2026-09-18).
    page.voice_mode_combo.setCurrentIndex(page.voice_mode_combo.findData("full"))
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


@pytest.mark.basic
def test_no_settings_page_is_clipped_at_any_size() -> None:
    """Apply and half the reasoning levels used to sit off the right edge at
    the dialog's own default size, with the horizontal scrollbar disabled —
    unreachable, with nothing to say so."""
    dlg, _ = _dialog()
    for width, height in ((820, 520), (840, 600), (1180, 760)):
        dlg.resize(width, height)
        dlg.show()
        _app().processEvents()
        for name in ("connection", "models", "voice", "workspace", "tools", "window", "about"):
            dlg.show_section(name)
            _app().processEvents()
            page = dlg.stack.currentWidget()
            viewport = page.scroll.viewport().width()
            needed = page.scroll.widget().minimumSizeHint().width()
            assert needed <= viewport, (
                f"{name} at {width}x{height}: needs {needed}px, has {viewport}px"
            )
    dlg.close()


@pytest.mark.basic
def test_the_models_page_has_no_actions_to_host() -> None:
    """Reload / Reset to gateway / Apply were three buttons for one question.

    Since 2026-09-18 a choice applies when it is made, "Gateway default" is the
    first item of the provider list (so it IS the reset), and an empty list
    retries itself when opened — leaving the footer nothing to hold. This
    replaced the earlier contract that those three lived in the footer.
    """
    dlg, _ = _dialog()
    page = dlg.page_models
    assert page.actions() == []
    assert not page.footer_frame.isVisibleTo(page)


@pytest.mark.basic
def test_the_window_sizes_itself_to_its_own_pages_and_stays_that_size() -> None:
    """The dialog is not resizable, so the size it picks IS the contract.

    It picked one 38px too narrow for the Models page: a page parked in the
    stack reports a stale width hint (the route list re-measures itself on
    resize), so the fit measured pages that had never been laid out. The
    route set here is production-sized — with one route the page is far too
    narrow for the bug to appear at all.
    """

    class _WideController(_Controller):
        def provider_choices(self, **kwargs):
            return [ChoiceItem(id="endpoint:airelay", label="endpoint:airelay"), ChoiceItem(id="mlx-gen", label="mlx-gen")]

        def model_choices(self, **kwargs):
            # Real model ids are long; they set the combo's width, and with a
            # short stub id the page is far too narrow for the bug to appear.
            return [
                ChoiceItem(
                    id="AbstractFramework/wan2.2-i2v-a14b-diffusers-8bit",
                    label="AbstractFramework/wan2.2-i2v-a14b-diffusers-8bit",
                )
            ]

        def route_map(self, **kwargs):
            rows = {}
            for key, label, provider, model in (
                ("input.text", "Main Chat Model", "endpoint:airelay", "gpt-5.6-terra"),
                ("input.image", "Image Understanding", "endpoint:airelay", "gpt-5.6-terra"),
                ("input.voice", "Speech To Text", "faster-whisper", "large-v3"),
                ("output.text", "Text Output", "endpoint:airelay", "gpt-5.6-terra"),
                ("output.image.text_to_image", "Image Generation", "mlx-gen", "AbstractFramework/flux.2-klein-9b-8bit"),
                ("output.voice", "Voice output (TTS)", "supertonic", "supertonic-3"),
                ("output.sound", "Sound Generation", "stable-audio-3", "stabilityai/stable-audio-3-small-sfx"),
            ):
                kind, _, rest = key.partition(".")
                modality, _, task = rest.partition(".")
                rows[key] = CapabilityRouteRow(
                    key=key, label=label, kind=kind, modality=modality, task=task,
                    provider=provider, model=model, configured=True,
                )
            return rows

    dlg, _ = _dialog(_WideController())
    dlg.show()
    _app().processEvents()

    assert dlg.minimumSize() == dlg.maximumSize(), "the settings window must not be resizable"
    # Shorter than the first cut, which was taller than any page needed.
    assert dlg.height() <= 576, f"settings window is {dlg.height()}px tall"
    assert dlg.height() >= 460, "too short to show a page without scrolling everything"

    for name in ("connection", "models", "voice", "workspace", "tools", "window", "about"):
        dlg.show_section(name)
        _app().processEvents()
        page = dlg.stack.currentWidget()
        needed = page.scroll.widget().minimumSizeHint().width()
        viewport = page.scroll.viewport().width()
        # There is no horizontal scrollbar, so anything past the viewport is
        # simply unreachable.
        assert needed <= viewport, f"{name} needs {needed}px, the window gives {viewport}px"
    dlg.close()


@pytest.mark.basic
def test_the_fit_measures_pages_that_have_never_been_laid_out() -> None:
    """A page parked in the stack sits at a placeholder size, and a child that
    measures itself on resize (the route list does exactly this) reports a
    stale width until the page is actually laid out. Measuring in that state
    made the window 38px too narrow for the Models page, with no horizontal
    scrollbar to reach the rest.
    """
    from PyQt5.QtCore import QSize
    from PyQt5.QtWidgets import QScrollArea, QVBoxLayout, QWidget

    class _GrowsOnLayout(QWidget):
        """Reports a small width hint until it is given real geometry.

        This is the route list's behaviour in miniature: it re-measures its
        own width from its longest row in ``resizeEvent``, so its hint is
        meaningless until the page it lives on has actually been laid out.
        """

        def __init__(self) -> None:
            super().__init__()
            self._min = 120

        def minimumSizeHint(self):  # noqa: N802 (Qt API)
            return QSize(self._min, 200)

        def resizeEvent(self, event):  # noqa: N802 (Qt API)
            super().resizeEvent(event)
            if self.width() > 200 and self._min != 760:
                self._min = 760
                self.updateGeometry()

    class _LatePage(QWidget):
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            box = QVBoxLayout(self)
            box.setContentsMargins(0, 0, 0, 0)
            self.scroll = QScrollArea(self)
            self.scroll.setWidgetResizable(True)
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.scroll.setWidget(_GrowsOnLayout())
            box.addWidget(self.scroll)

    dlg, _ = _dialog()
    late = _LatePage(dlg)
    dlg.pages["late"] = late
    dlg.stack.addWidget(late)

    dlg.show()
    _app().processEvents()
    dlg.stack.setCurrentWidget(late)
    _app().processEvents()

    needed = late.scroll.widget().minimumSizeHint().width()
    viewport = late.scroll.viewport().width()
    assert needed <= viewport, f"page needs {needed}px, the window gives {viewport}px"
    dlg.close()


@pytest.mark.basic
def test_a_theme_that_could_not_be_saved_is_never_reported_as_saved() -> None:
    """`apply_theme` returns whether the choice was WRITTEN, and the page threw
    that away — so a theme could apply on screen, fail to persist, and still
    say "saved on this device". The next launch came back on the old theme
    with nothing having warned. This is how a preferences file kept
    `abstract-glass` while the operator picked theme after theme.
    """
    class _Failing(_Controller):
        def apply_theme(self, theme_id, **kwargs):
            self.attempted = theme_id
            return False  # applied on screen, not written to disk

    class _Working(_Controller):
        def apply_theme(self, theme_id, **kwargs):
            self.attempted = theme_id
            return True

    for controller, should_warn in ((_Failing(), True), (_Working(), False)):
        dlg, _ = _dialog(controller)
        dlg.show_section("window")
        _app().processEvents()
        page = dlg.page_window
        index = page.theme_combo.findData("gruvbox")
        assert index >= 0
        page.theme_combo.setCurrentIndex(index)
        _app().processEvents()

        assert controller.attempted == "gruvbox"
        said = page.feedback.text()
        if should_warn:
            assert "could not be saved" in said, f"silent failure: {said!r}"
        else:
            assert "saved" in said.lower() and "could not" not in said, said
        dlg.close()


@pytest.mark.basic
def test_the_spin_controls_have_visible_arrows() -> None:
    """A spin box's arrows are SUBCONTROLS: no widget to setIcon on, and QSS
    cannot take a QIcon. Without an explicit image Qt falls back to its native
    arrow — a dark glyph on a dark field, which is invisible. QDoubleSpinBox
    is not a QSpinBox and has to be named separately; it was the one control
    left with the bare native arrows.
    """
    import os
    import re

    from abstractassistant.ui.styles import dialog_stylesheet

    _app()
    css = dialog_stylesheet()
    for control in ("QSpinBox", "QDoubleSpinBox"):
        for part in ("up-arrow", "down-arrow"):
            match = re.search(
                rf"{control}::{part}[^{{]*\{{([^}}]*)\}}", css
            )
            assert match, f"{control}::{part} has no rule at all"
            body = match.group(1)
            url = re.search(r"image:\s*url\(([^)]+)\)", body)
            assert url, f"{control}::{part} has no image; Qt will draw its invisible native arrow"
            assert os.path.exists(url.group(1)), f"{control}::{part} points at a missing file"
        assert re.search(rf"{control}::up-button", css), f"{control} up-button is unstyled"
