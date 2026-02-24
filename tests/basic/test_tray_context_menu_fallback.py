"""
Tests for macOS tray context-menu fallback behavior.
"""

import time

import abstractassistant.app as app_module
from abstractassistant.app import AbstractAssistantApp


def _stub_app(state: str = "ready") -> AbstractAssistantApp:
    app = AbstractAssistantApp.__new__(AbstractAssistantApp)
    app.debug = False
    app._tray_last_activation_ts = 0.0
    app._qt_context_menu = None
    app._assistant_state = lambda: state  # type: ignore[method-assign]
    app._shown = False

    def _show_chat_bubble(*_args, **_kwargs):
        app._shown = True

    app.show_chat_bubble = _show_chat_bubble  # type: ignore[method-assign]
    return app


def test_context_menu_show_opens_ready_when_activation_missing(monkeypatch) -> None:
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    app = _stub_app("ready")
    app._qt_on_context_menu_show()
    assert app._shown is True


def test_context_menu_show_does_not_duplicate_recent_activation(monkeypatch) -> None:
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    app = _stub_app("ready")
    app._tray_last_activation_ts = time.monotonic()
    app._qt_on_context_menu_show()
    assert app._shown is False


def test_context_menu_show_respects_non_ready_states(monkeypatch) -> None:
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    for state in ("running", "speaking", "listening"):
        app = _stub_app(state)
        app._qt_on_context_menu_show()
        assert app._shown is False
