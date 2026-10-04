"""R10.4 Assistant Settings (R10-W4): Chat model MTP depth, Voice engines
read-only, Tools collapsible categories, Global shortcut Accessibility.

Headless (QT_QPA_PLATFORM=offscreen), stub controller, no gateway; the macOS
permission calls are injected — no real prompt, no System Settings.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QLineEdit, QPushButton

from abstractassistant import hotkey as hotkey_module
from abstractassistant.gateway.run_input import build_run_input_data

import test_settings_pages as tsp


LIVE_VOICE_DEFAULTS = {
    "tts": {"route": "output.voice", "configured": True, "provider": "supertonic", "model": "supertonic-3", "voice": "M3"},
    "stt": {"route": "input.voice", "configured": True, "provider": "faster-whisper", "model": "large-v3"},
    "source": "capability_defaults",
}

MTP_CAPABLE = {"execution": {"speculation": {
    "supported": True, "ready": True, "reason": None,
    "supported_depths": [1, 2, 3, 4], "effective_default": {"mode": "native_mtp", "num_draft_tokens": 2},
    "requires_reload": False,
}}}
NOT_MTP = {"execution": {"speculation": {
    "supported": False, "ready": None, "reason": "native_mtp_backend_unavailable", "supported_depths": [],
}}}


class _Ctl(tsp._Controller):
    voice_answer = LIVE_VOICE_DEFAULTS
    voice_calls = 0
    save_fails = False

    def voice_defaults(self):
        type(self).voice_calls += 1
        return self.voice_answer

    def tool_inventory(self):
        def tool(name, toolset, tier="observe", default="approve", selected=None, available=True, rank=1):
            return {
                "name": name, "toolset": toolset, "description": f"{name} does one thing. More text.",
                "available": available, "risk_tier": tier, "risk_rank": rank,
                "approval_default": "auto" if default == "approve" else "ask",
                "policy_default": default, "selected_mode": selected or default,
            }

        return {
            "tool_mode": "approval",
            "items": [
                tool("read_file", "files"),
                tool("list_files", "files"),
                tool("write_file", "files", tier="act", default="ask", rank=2),
                tool("delete_file", "files", tier="destroy", default="ask", rank=4),
                tool("web_search", "web"),
                tool("fetch_url", "web"),
                # An override on this Mac (gateway default ask, chosen auto):
                # the camera panel opens by default.
                tool("camera_capture_photo", "camera", tier="act", default="ask", selected="approve", rank=2),
                tool("send_email", "comms", tier="outreach", default="ask", rank=3),
                tool("list_emails", "comms"),
            ],
        }

    def save_tool_preferences(self, statuses):
        if self.save_fails:
            raise RuntimeError("the preferences file is read-only")
        super().save_tool_preferences(statuses)


def _dialog(ctl=None):
    return tsp._dialog(ctl or _Ctl())


# --------------------------------------------------------------------------- #
# 1. Chat model: MTP depth (the kit's SpeculationSelect wording)


def _mtp_editor(payload):
    dlg, ctl = _dialog()
    dlg.show_section("models", "output.text")
    editor = dlg.page_models.route_editor
    editor._apply_speculation_payload(editor._speculation_epoch, payload)
    return dlg, ctl, editor


@pytest.mark.basic
def test_mtp_capable_model_offers_the_shared_depth_choices_and_rides_the_run() -> None:
    dlg, ctl, editor = _mtp_editor(MTP_CAPABLE)
    combo = editor.speculation_combo
    assert editor.speculation_label.text() == "MTP depth"
    assert editor.speculation_label.isVisibleTo(editor) and combo.isVisibleTo(editor)
    assert combo.isEnabled()
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Gateway default (depth 2)", "Off", "Depth 1", "Depth 2", "Depth 3", "Depth 4",
    ]
    combo.setCurrentIndex(combo.findText("Depth 3"))
    assert ctl.preferences.speculation == {"mode": "native_mtp", "num_draft_tokens": 3, "require_acceleration": True}
    assert editor.route_feedback.text() == "Saved on this device."
    # Persisted, then sent: the run carries the gateway's field.
    run = build_run_input_data(prompt="hi", speculation=ctl.preferences.run_scope()["speculation"])
    assert run["_runtime"]["speculation"] == {"mode": "native_mtp", "num_draft_tokens": 3, "require_acceleration": True}
    combo.setCurrentIndex(0)
    assert ctl.preferences.speculation is None
    assert "speculation" not in ctl.preferences.run_scope()


@pytest.mark.basic
def test_non_mtp_model_shows_the_list_disabled_with_the_gateway_sentence() -> None:
    dlg, ctl, editor = _mtp_editor(NOT_MTP)
    combo = editor.speculation_combo
    assert not combo.isEnabled()
    assert [combo.itemData(i) for i in range(combo.count())] == [None, False]
    assert editor.speculation_note.text() == "native_mtp_backend_unavailable"
    # A pinned value stays changeable so it can go back to Gateway default.
    ctl.update_preferences(speculation={"mode": "native_mtp", "num_draft_tokens": 4})
    editor._apply_speculation_payload(editor._speculation_epoch, NOT_MTP)
    assert combo.isEnabled()
    assert combo.currentText() == "Depth 4 (saved; not available)"


@pytest.mark.basic
def test_mtp_notes_are_the_kit_sentences() -> None:
    from abstractassistant.speculation import speculation_options

    def note(caps):
        return speculation_options({"execution": {"speculation": caps}})[1]

    assert note({"supported": True, "ready": False, "supported_depths": [2]}) == "MTP is supported but not ready on this instance."
    assert note({"supported": True, "supported_depths": [2]}) == "MTP support verified; loaded-instance readiness is unknown."
    assert note({"supported": True, "requires_reload": True, "supported_depths": [2]}) == "Model reload required before MTP can run."
    assert note({"supported": False}) == "MTP is not supported on this model/backend."
    assert speculation_options({})[1] == "MTP capability unknown; no depth is assumed."
    # No `supported` boolean = not described (kit speculationCapability → null).
    assert speculation_options({"execution": {"speculation": {"supported_depths": [2]}}})[0] == [(None, "Gateway default"), (False, "Off")]


# --------------------------------------------------------------------------- #
# 2. Voice tab: engines read-only, "Change under Models"


@pytest.mark.basic
def test_voice_tab_shows_the_gateway_engines_read_only_from_voice_defaults() -> None:
    dlg, ctl = _dialog()
    dlg.show_section("voice")
    page = dlg.page_voice
    assert page.tts_summary.text() == "Gateway default · supertonic / supertonic-3"
    assert page.stt_summary.text() == "Gateway default · faster-whisper / large-v3"
    assert "openai" not in page.tts_summary.text() + page.stt_summary.text()
    # No engine controls on this page: the only lists are the output device,
    # voice latency and barge-in; no provider / model / voice picker.
    combos = page.findChildren(QComboBox)
    assert set(combos) == {page.output_device_combo, page.voice_quality_combo, page.voice_mode_combo}
    labels = {b.text() for b in page.findChildren(QPushButton)}
    assert labels == {"Change under Models", "Test"}
    assert page.tts_link.objectName() == "linkButton" and page.stt_link.objectName() == "linkButton"
    assert page.tts_link.toolTip() and page.stt_link.toolTip()
    # Kept: output device + Test, Playing on, Read aloud, Voice latency, dictation options.
    assert page.device_summary.text().startswith("MacBook Pro Speakers")
    assert page.auto_speak.text() == "Speak replies automatically"
    assert page.voice_auto_send.text() == "Send what you say automatically"
    assert page.voice_spoken_replies.text() == "Ask for short, spoken-style replies"
    assert page.voice_mode_combo.itemText(0) == "Pause the mic while speaking"


@pytest.mark.basic
def test_change_under_models_lands_on_the_models_voice_route() -> None:
    dlg, ctl = _dialog()
    ctl_routes = dict(tsp._Controller.route_map(ctl))
    from abstractassistant.gateway_service import CapabilityRouteRow

    ctl_routes["output.voice"] = CapabilityRouteRow(key="output.voice", label="Voice output", kind="output", modality="voice", task="", provider="supertonic", model="supertonic-3", configured=True)
    ctl.route_map = lambda **kw: ctl_routes  # type: ignore[method-assign]
    dlg.refresh()
    dlg.show_section("voice")
    dlg.page_voice.tts_link.click()
    assert dlg.current_section() == "models"
    assert dlg.route_editor._active_row().key == "output.voice"
    dlg.show_section("voice")
    dlg.page_voice.stt_link.click()
    assert dlg.current_section() == "models"
    assert dlg.route_editor._active_row().key == "input.voice"


@pytest.mark.basic
def test_voice_engine_summary_states() -> None:
    from abstractassistant.ui.settings.pages import VoicePage

    s = VoicePage.engine_summary
    assert s(LIVE_VOICE_DEFAULTS, "tts", None)[0] == "Gateway default · supertonic / supertonic-3"
    override = {"provider": "kokoro", "model": "kokoro-82m", "options": {"voice": "af_heart"}}
    assert s(LIVE_VOICE_DEFAULTS, "tts", override)[0] == "kokoro / kokoro-82m · voice af_heart — this app"
    unset = {"stt": {"route": "input.voice", "configured": False, "provider": None, "model": None, "note": "No gateway default is set for speech to text."}}
    text, tip = s(unset, "stt", None)
    assert text == "Gateway default · not set" and tip.startswith("No gateway default")
    text, tip = s({"error": "connection refused"}, "stt", None)
    assert text == "Gateway default · unknown" and "connection refused" in tip
    assert s(None, "tts", None)[0] == "Gateway default · unknown"


@pytest.mark.basic
def test_controller_voice_defaults_reads_the_gateway_route(monkeypatch) -> None:
    from abstractassistant.controller import AssistantController
    from abstractassistant.gateway.client import GatewayClient

    client = GatewayClient.__new__(GatewayClient)
    seen = {}
    monkeypatch.setattr(client, "_url", lambda path, query=None: seen.update(path=path) or "u")
    monkeypatch.setattr(client, "_request_json", lambda **kw: seen.update(method=kw["method"]) or LIVE_VOICE_DEFAULTS)
    assert client.voice_defaults() == LIVE_VOICE_DEFAULTS
    assert seen == {"path": "/api/gateway/voice/defaults", "method": "GET"}

    import threading

    ctl = AssistantController.__new__(AssistantController)
    ctl._cache_lock = threading.RLock()
    ctl._cache_epoch = 0
    ctl._cache_ttl_s = 20.0
    calls = []
    ctl.gateway = SimpleNamespace(voice_defaults=lambda: calls.append(1) or LIVE_VOICE_DEFAULTS)
    assert ctl.voice_defaults()["tts"]["provider"] == "supertonic"
    assert ctl.voice_defaults()["stt"]["model"] == "large-v3"
    assert calls == [1]  # cached like the other Settings reads

    def boom():
        raise RuntimeError("connection refused")

    ctl2 = AssistantController.__new__(AssistantController)
    ctl2._cache_lock = threading.RLock()
    ctl2._cache_epoch = 0
    ctl2._cache_ttl_s = 20.0
    ctl2.gateway = SimpleNamespace(voice_defaults=boom)
    assert ctl2.voice_defaults() == {"error": "connection refused"}


# --------------------------------------------------------------------------- #
# 3. Tools: collapsible category panels


def _tools():
    dlg, ctl = _dialog()
    dlg.show_section("tools")
    return dlg, ctl, dlg.page_tools


@pytest.mark.basic
def test_tool_categories_are_the_gateway_toolsets_collapsed_except_overrides() -> None:
    dlg, ctl, page = _tools()
    assert set(page.groups) == {"files", "web", "camera", "comms"}
    files = page.groups["files"]
    assert files.toggle.text() == "files"
    assert files.count_chip.text() == "4"
    # Collapsed by default …
    for name in ("files", "web", "comms"):
        assert not page.groups[name].is_open(), name
    # … except the one carrying an override on this Mac.
    assert page.groups["camera"].is_open()
    # Opening by hand is kept across a refresh.
    files.toggle.click()
    assert files.is_open()
    page.refresh()
    assert page.groups["files"].is_open()
    assert page.groups["files"].toggle.toolTip() == "Hide the files tools"
    assert page.groups["web"].toggle.toolTip() == "Show the web tools"


@pytest.mark.basic
def test_all_auto_and_all_ask_are_pressed_state_controls_that_apply_at_once() -> None:
    dlg, ctl, page = _tools()
    web = page.groups["web"]
    # Pressed state = the rows' truth: every web tool is on Auto.
    assert web.all_auto.isCheckable() and web.all_auto.isChecked() and not web.all_ask.isChecked()
    files = page.groups["files"]
    assert not files.all_auto.isChecked() and not files.all_ask.isChecked()  # mixed
    # All ask on web: applied and saved at once (no Save button).
    web.all_ask.click()
    assert all(page._rows[n]["control"].value() == "ask" for n in ("web_search", "fetch_url"))
    assert ctl.saved_tool_prefs == {"web_search": "ask", "fetch_url": "ask", "camera_capture_photo": "approve"}
    assert web.all_ask.isChecked() and not web.all_auto.isChecked()
    # Clicking the pressed one again keeps it pressed (it is a state, not a verb).
    web.all_ask.click()
    assert web.all_ask.isChecked()
    # All auto on files: destructive delete_file stays on Ask; the state shows
    # "All auto" pressed (every tool it may reach is on Auto).
    files.all_auto.click()
    assert page._rows["write_file"]["control"].value() == "approve"
    assert page._rows["delete_file"]["control"].value() == "ask"
    assert files.all_auto.isChecked()
    assert "delete_file" in page.feedback.text()
    # One row changed by hand flips the panel back to "mixed".
    page._rows["read_file"]["control"]._buttons[2].click()  # Ask
    assert ctl.saved_tool_prefs["read_file"] == "ask"
    assert not files.all_auto.isChecked() and not files.all_ask.isChecked()
    assert page.actions() and [b.text() for b in page.actions()] == ["Use gateway defaults"]


@pytest.mark.basic
def test_a_refused_tool_save_says_not_saved_and_puts_the_row_back() -> None:
    ctl = _Ctl()
    ctl.save_fails = True
    dlg, _ = _dialog(ctl)
    dlg.show_section("tools")
    page = dlg.page_tools
    page._rows["web_search"]["control"]._buttons[2].click()
    assert page._rows["web_search"]["control"].value() == "approve"
    assert page.feedback.text() == "Not saved. the preferences file is read-only"


@pytest.mark.basic
def test_the_filter_searches_every_category_and_opens_the_ones_with_hits() -> None:
    dlg, ctl, page = _tools()
    page.search_edit.setText("email")
    assert page.groups["comms"].is_open() and page.groups["comms"].isVisibleTo(page)
    assert page.groups["comms"].count_chip.text() == "2 of 2"
    for name in ("files", "web", "camera"):
        assert not page.groups[name].isVisibleTo(page), name
    page.search_edit.setText("file")
    assert page.groups["files"].is_open()
    assert page.groups["files"].count_chip.text() == "4 of 4"
    # A filtered "All auto" only touches what is shown.
    page.search_edit.setText("read_file")
    page.groups["files"].all_auto.click()
    assert page._rows["write_file"]["control"].value() == "ask"
    # Cleared: every panel back, collapsed except the overrides.
    page.search_edit.setText("")
    assert all(g.isVisibleTo(page) for g in page.groups.values())
    assert not page.groups["comms"].is_open() and page.groups["camera"].is_open()
    assert page.groups["files"].count_chip.text() == "4"


@pytest.mark.basic
def test_categories_come_only_from_the_toolset_field() -> None:
    """No hand-made category list and nothing read from a tool's name."""
    import inspect

    from abstractassistant.ui.settings import pages

    source = inspect.getsource(pages.ToolsPage.refresh)
    assert 'item.get("toolset")' in source
    ctl = _Ctl()
    ctl.tool_inventory = lambda: {"items": [{"name": "email_send", "toolset": "web", "available": True, "policy_default": "ask"}]}  # type: ignore[method-assign]
    dlg, _ = _dialog(ctl)
    dlg.show_section("tools")
    assert set(dlg.page_tools.groups) == {"web"}


# --------------------------------------------------------------------------- #
# 4. Global shortcut: macOS Accessibility


class _AxOracle:
    def __init__(self, granted):
        self.granted = granted
        self.requests = 0
        self.opens = 0

    def install(self, monkeypatch):
        monkeypatch.setattr(hotkey_module, "accessibility_state", lambda: self.granted)
        monkeypatch.setattr(hotkey_module, "request_accessibility", self._request)
        monkeypatch.setattr(hotkey_module, "open_accessibility_settings", self._open)
        return self

    def _request(self):
        self.requests += 1
        return self.granted

    def _open(self):
        self.opens += 1
        return True


def _window(monkeypatch, granted, *, hotkey_enabled=True):
    oracle = _AxOracle(granted).install(monkeypatch)
    ctl = _Ctl()
    ctl.preferences = ctl.update_preferences(hotkey_enabled=hotkey_enabled)
    applied = []
    tsp._app()
    from abstractassistant.ui.settings import SettingsDialog

    dlg = SettingsDialog(controller=ctl, apply_hotkey=lambda: applied.append(1), parent=None)
    dlg.show_section("window")
    return dlg, ctl, dlg.page_window, oracle, applied


@pytest.mark.basic
def test_accessibility_state_is_shown_and_configure_asks_macos(monkeypatch) -> None:
    dlg, ctl, page, oracle, applied = _window(monkeypatch, False)
    assert page.accessibility_state.text() == "Not granted"
    assert page.accessibility_state.property("tone") == "warning"
    assert page.accessibility_configure.text() == "Configure"
    assert page.accessibility_configure.toolTip()
    help_label = page._accessibility_row.help_label
    assert help_label.text() == "Works anywhere once macOS grants Accessibility access; otherwise use the menu bar icon."
    dlg.show()
    tsp._app().processEvents()
    page.accessibility_configure.click()
    assert oracle.requests == 1 and oracle.opens == 1
    assert "updates when you come back" in page.feedback.text()
    # The user grants it in System Settings; nothing changes until the
    # Settings window is activated again.
    oracle.granted = True
    tsp._app().processEvents()
    assert page.accessibility_state.text() == "Not granted"
    from PyQt5.QtCore import QEvent
    from PyQt5.QtWidgets import QApplication

    QApplication.sendEvent(page, QEvent(QEvent.ActivationChange))  # back from System Settings
    assert page.accessibility_state.text() == "Granted"
    assert page.accessibility_state.property("tone") == "ok"
    assert applied, "the shortcut is armed once the permission arrives"
    assert page.feedback.text() == "Accessibility granted — the global shortcut is on."
    dlg.close()


@pytest.mark.basic
def test_accessibility_rechecks_when_the_page_is_shown_again(monkeypatch) -> None:
    dlg, ctl, page, oracle, applied = _window(monkeypatch, False, hotkey_enabled=False)
    assert page.accessibility_state.text() == "Not granted"
    oracle.granted = True
    dlg.show_section("about")
    dlg.show_section("window")  # the page refreshes when it is shown
    assert page.accessibility_state.text() == "Granted"
    assert page.feedback.text() == "Accessibility granted."
    assert not applied  # the shortcut is off: nothing to arm


@pytest.mark.basic
def test_accessibility_row_is_hidden_where_no_permission_exists(monkeypatch) -> None:
    dlg, ctl, page, oracle, applied = _window(monkeypatch, None)
    assert not page._accessibility_row.isVisibleTo(page)


@pytest.mark.basic
def test_request_and_open_use_the_macos_calls(monkeypatch) -> None:
    calls = {}
    fake = SimpleNamespace(
        kAXTrustedCheckOptionPrompt="AXTrustedCheckOptionPrompt",
        AXIsProcessTrustedWithOptions=lambda opts: calls.setdefault("opts", opts) and False,
        AXIsProcessTrusted=lambda: False,
    )
    monkeypatch.setitem(sys.modules, "HIServices", fake)
    monkeypatch.setattr(hotkey_module.sys, "platform", "darwin")
    assert hotkey_module.request_accessibility() is False
    assert calls["opts"] == {"AXTrustedCheckOptionPrompt": True}
    assert hotkey_module.accessibility_state() is False
    import subprocess

    launched = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv: launched.append(argv))
    assert hotkey_module.open_accessibility_settings() is True
    assert launched == [["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"]]
    monkeypatch.setattr(hotkey_module.sys, "platform", "linux")
    assert hotkey_module.accessibility_state() is None
    assert hotkey_module.request_accessibility() is None


@pytest.mark.basic
def test_shortcut_and_window_size_apply_on_change_without_save(monkeypatch) -> None:
    dlg, ctl, page, oracle, applied = _window(monkeypatch, True)
    assert page.actions() == []
    page.hotkey_edit.setText("ctrl+alt+space")
    page.hotkey_edit.editingFinished.emit()
    assert ctl.preferences.hotkey_sequence == "ctrl+alt+space"
    assert applied
    assert page.feedback.text() == "Saved on this device: ctrl+alt+space."
    page.width_spin.setValue(720)
    assert ctl.preferences.window_width == 720
    page.bottom_offset_spin.setValue(0)
    assert ctl.preferences.bottom_offset == 0
    # A refresh never writes.
    before = ctl.preferences.to_dict()
    page.refresh()
    assert ctl.preferences.to_dict() == before
    assert isinstance(page.hotkey_edit, QLineEdit)


@pytest.mark.basic
def test_reasoning_note_is_elided_with_an_ellipsis_at_its_laid_out_width() -> None:
    """Pre-existing (e73ee81), found by the adversary: the note was elided
    against the label's pre-layout width and clipped with no "…"."""
    from PyQt5.QtGui import QFontMetrics

    for width in (820, 1000):
        dlg, ctl = _dialog()
        dlg.show()
        tsp._app().processEvents()
        dlg.setMinimumSize(0, 0)
        dlg.setMaximumSize(16777215, 16777215)
        dlg.setFixedSize(width, 760)
        dlg.show_section("models", "output.text")
        tsp._app().processEvents()
        note = dlg.route_editor.reasoning_note
        full = note.toolTip()
        assert full.startswith("Applies to ")
        shown = note.text()
        fits = QFontMetrics(note.font()).horizontalAdvance(shown) <= note.contentsRect().width()
        assert fits, (width, shown)
        assert shown == full or shown.endswith("…"), (width, shown)
        dlg.close()
