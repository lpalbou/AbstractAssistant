"""
Tray click behavior tests for full-voice listening state.
"""

from abstractassistant.app import AbstractAssistantApp


def _stub_listening_app() -> AbstractAssistantApp:
    app = AbstractAssistantApp.__new__(AbstractAssistantApp)
    app.debug = False
    app.current_status = "listening"
    app._assistant_state = lambda: "listening"  # type: ignore[method-assign]
    app._full_voice_listening_state = lambda: "listening"  # type: ignore[method-assign]
    app._voice_is_active = lambda: False  # type: ignore[method-assign]
    return app


def test_single_click_listening_toggles_pause_not_show() -> None:
    app = _stub_listening_app()
    calls = {"toggle": 0, "show": 0}
    app._toggle_full_voice_listening_pause = lambda: calls.__setitem__("toggle", calls["toggle"] + 1) or True  # type: ignore[method-assign]
    app.show_chat_bubble = lambda *a, **k: calls.__setitem__("show", calls["show"] + 1)  # type: ignore[method-assign]

    app.handle_single_click()

    assert calls["toggle"] == 1
    assert calls["show"] == 0


def test_double_click_listening_stops_full_voice_mode() -> None:
    app = _stub_listening_app()
    calls = {"stop": 0, "ready": 0}
    app._stop_full_voice_mode = lambda: calls.__setitem__("stop", calls["stop"] + 1) or True  # type: ignore[method-assign]
    app.update_icon_status = lambda status: calls.__setitem__("ready", calls["ready"] + (1 if status == "ready" else 0))  # type: ignore[method-assign]

    app.handle_double_click()

    assert calls["stop"] == 1
    assert calls["ready"] == 1
