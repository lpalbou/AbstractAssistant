"""The optional native portrait follows real activity and owns no hidden clocks."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from abstractassistant.preferences import AssistantPreferences
from abstractassistant.ui.avatar import ActivityAvatar, AvatarPresentation, audio_level, presentation


_APP = None


def _app():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class Renderer:
    instances = []

    def __init__(self, *, width, height):
        self.width, self.height = width, height
        self.calls = []
        self.closed = False
        self.instances.append(self)

    def render(self, **values):
        assert not self.closed
        self.calls.append(values)
        return bytes([80, 150, 220, 255]) * self.width * self.height

    def set_palette(self, **values):
        self.palette = values

    def close(self):
        self.closed = True


@pytest.mark.basic
def test_avatar_preference_is_opt_in_and_never_enters_run_scope():
    prefs = AssistantPreferences.from_dict({})
    assert prefs.avatar_enabled is False
    assert prefs.avatar_animated is True
    prefs = AssistantPreferences.from_dict({"avatar_enabled": True, "avatar_style": "watch-membrane",
                                             "avatar_animated": False, "auto_speak": True})
    restored = AssistantPreferences.from_dict(prefs.to_dict())
    assert (restored.avatar_enabled, restored.avatar_style, restored.avatar_animated) == (
        True, "watch-membrane", False)
    assert restored.auto_speak
    assert not any(key.startswith("avatar") for key in restored.run_scope())
    assert not AssistantPreferences.from_dict({"avatar_enabled": "false"}).avatar_enabled
    assert AssistantPreferences.from_dict({"avatar_style": "../../outside"}).avatar_style == "halo"


@pytest.mark.basic
@pytest.mark.parametrize("state", ["ready", "thinking", "working", "listening", "speaking", "waiting", "error"])
def test_activity_mapping_covers_every_renderer_state(state):
    values = {} if state == "ready" else {state: True}
    assert presentation(**values).state == state
    assert presentation(speaking=True, thinking=True).state == "speaking"
    assert presentation(waiting=True, thinking=True).state == "waiting"
    assert presentation(error=True, speaking=True).state == "error"
    assert audio_level([0.2, float("nan"), 2]) == 1


@pytest.mark.basic
def test_disabled_hidden_and_reduced_motion_own_no_animation_clock():
    _app()
    Renderer.instances.clear()
    current = [AvatarPresentation("speaking", 0.5)]
    widget = ActivityAvatar(lambda: current[0], renderer_factory=Renderer)
    widget.configure(enabled=False, style="halo", animated=True)
    _app().processEvents()
    assert Renderer.instances == []
    widget.configure(enabled=True, style="halo", animated=True)
    _app().processEvents()
    renderer = Renderer.instances[-1]
    assert widget._timer.isActive()
    assert renderer.calls[-1]["state"] == "speaking"
    widget.hide()
    assert renderer.closed
    assert not widget._timer.isActive()
    widget.show()
    _app().processEvents()
    assert len(Renderer.instances) == 2
    widget.configure(enabled=True, style="halo", animated=False)
    assert not widget._timer.isActive()
    assert Renderer.instances[-1].calls[-1]["time"] == 0
    current[0] = AvatarPresentation("waiting")
    widget.refresh()
    assert Renderer.instances[-1].calls[-1]["state"] == "waiting"
    assert not widget._timer.isActive()
    widget.configure(enabled=False, style="halo", animated=False)
    assert Renderer.instances[-1].closed
    widget.deleteLater()


@pytest.mark.basic
def test_native_failure_is_visible_and_never_replaced_by_another_renderer():
    _app()
    calls = []

    def broken(**_):
        calls.append(1)
        raise RuntimeError("native library missing")

    widget = ActivityAvatar(lambda: AvatarPresentation(), renderer_factory=broken)
    widget.configure(enabled=True, style="halo", animated=True)
    _app().processEvents()
    widget.refresh()
    assert len(calls) == 1
    assert "native library missing" in widget.error
    assert "Avatar unavailable" in widget._image.text()
    assert not widget._timer.isActive()
    widget.hide()
    widget.deleteLater()


@pytest.mark.basic
def test_meter_bursts_cannot_exceed_frame_budget_and_motion_off_is_static(monkeypatch):
    _app()
    import abstractassistant.ui.avatar as module

    clock = [10.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    current = [AvatarPresentation("speaking", 0.5)]
    widget = ActivityAvatar(lambda: current[0], renderer_factory=Renderer)
    widget.configure(enabled=True, style="halo", animated=True)
    renderer = widget._renderer
    before = len(renderer.calls)
    for i in range(30):
        clock[0] += 0.001
        current[0] = AvatarPresentation("speaking", i / 30)
        widget.refresh()
    assert len(renderer.calls) == before
    clock[0] += 0.1
    widget.refresh()
    assert len(renderer.calls) == before + 1
    widget.configure(enabled=True, style="halo", animated=False)
    before = len(renderer.calls)
    for i in range(30):
        current[0] = AvatarPresentation("speaking", i / 30)
        widget.refresh()
    assert len(renderer.calls) == before
    widget.hide()
    widget.deleteLater()


@pytest.mark.basic
def test_settings_persists_style_motion_and_preserves_other_preferences(monkeypatch):
    _app()
    from abstractassistant.ui.settings.pages import WindowPage
    import abstractassistant.ui.avatar as module

    monkeypatch.setattr(module, "available_styles", lambda: ([
        {"id": "halo", "name": "Halo", "description": "Light"},
        {"id": "watch-ocean", "name": "Ocean", "description": "Water"},
    ], ""))
    controller = SimpleNamespace(preferences=AssistantPreferences(auto_speak=True))

    def update(**values):
        data = controller.preferences.to_dict()
        data.update(values)
        controller.preferences = AssistantPreferences.from_dict(data)

    controller.update_preferences = update
    page = WindowPage(controller, lambda: None)
    page.avatar_enabled.click()
    page.avatar_style.setCurrentIndex(1)
    page.avatar_animated.click()
    assert controller.preferences.avatar_enabled is True
    assert controller.preferences.avatar_style == "watch-ocean"
    assert controller.preferences.avatar_animated is False
    assert controller.preferences.auto_speak is True
    page.deleteLater()


@pytest.mark.basic
def test_palette_reads_actual_tool_wait_voice_and_error_state():
    _app()
    from abstractassistant.app import AssistantPalette

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._controller = SimpleNamespace(voice_manager=SimpleNamespace(is_speaking=lambda: False,
                                                                       is_holding=lambda: False))
    palette._run_busy = True
    assert palette._avatar_presentation().state == "thinking"
    palette._thinking_status_tone = "tool"
    assert palette._avatar_presentation().state == "working"
    palette._pending_user_waits = {"w": {}}
    assert palette._avatar_presentation().state == "waiting"
    palette._listening = True
    assert palette._avatar_presentation().state == "listening"
    palette._controller.voice_manager.is_speaking = lambda: True
    assert palette._avatar_presentation().state == "speaking"
    palette._status_tone = "error"
    assert palette._avatar_presentation().state == "error"


@pytest.mark.basic
def test_real_native_frames_reach_qt_when_explicitly_requested():
    library = os.environ.get("ABSTRACTAVATAR_TEST_LIBRARY")
    if not library:
        pytest.skip("Set ABSTRACTAVATAR_TEST_LIBRARY to verify the built native renderer")
    from abstractavatar import Renderer, catalog

    _app()
    assert len(catalog(library_path=library)) >= 44
    current = [AvatarPresentation()]
    widget = ActivityAvatar(lambda: current[0],
                            renderer_factory=lambda **kw: Renderer(library_path=library, **kw))
    widget.configure(enabled=True, style="hover", animated=False)
    seen = []
    for state in ("ready", "thinking", "working", "listening", "speaking", "waiting", "error"):
        current[0] = AvatarPresentation(state, 0.7)
        widget.refresh()
        assert not widget.error
        pixmap = widget._image.pixmap()
        assert pixmap is not None and not pixmap.isNull()
        image = pixmap.toImage()
        seen.append(image.cacheKey())
    assert len(set(seen)) == 7
    widget.hide()
    assert widget._renderer is None
    widget.deleteLater()


@pytest.mark.basic
def test_real_palette_integrates_optional_avatar_without_changing_tray_controls(tmp_path, monkeypatch):
    if not os.environ.get("ABSTRACTAVATAR_TEST_LIBRARY"):
        pytest.skip("Set ABSTRACTAVATAR_TEST_LIBRARY to exercise the native palette integration")
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.app import AssistantPalette

    _app()
    for name in ("_start_bootstrap", "_request_connection_status_refresh", "_schedule_session_refresh",
                 "_poll_automations", "_apply_hotkey"):
        monkeypatch.setattr(AssistantPalette, name, lambda *_args, **_kwargs: None)
    controller = AssistantController(config=Config(), data_dir=tmp_path / "assistant")
    controller.update_preferences(avatar_enabled=True, avatar_style="watch-ocean",
                                  avatar_animated=False, hotkey_enabled=False, window_height=560)
    window = AssistantPalette(controller=controller)
    window.show()
    _app().processEvents()
    window._reflow_shell()
    widget = window.activity_avatar
    assert widget.isVisible()
    assert not widget.error
    assert widget._image.pixmap() is not None
    assert window.header_card.geometry().bottom() < window.history_card.geometry().top()
    assert window._tray_feedback_state() == "idle"
    window._run_busy = True
    window._set_status("Thinking…", tone="busy")
    assert widget._image.accessibleName().endswith("Thinking")
    window._thinking_status_tone = "tool"
    window._refresh_avatar()
    assert widget._image.accessibleName().endswith("Working")
    capture = os.environ.get("ABSTRACTAVATAR_CAPTURE_DIR")
    if capture:
        from pathlib import Path

        destination = Path(capture)
        destination.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(destination / "assistant-desktop.png"))
    window.hide()
    assert widget._renderer is None and not widget._timer.isActive()
    window.deleteLater()
