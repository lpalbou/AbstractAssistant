"""Switching sessions shows ONLY the new session's transcript.

Operator report (2026-09-25): after picking another session in the switcher,
the old and the new conversation were drawn over each other. ``refresh_history``
removed the old ``MessageCard``s with ``takeAt`` + ``deleteLater`` only, so until
the event loop got round to the deferred deletion they were still visible
children of ``history_host`` — painted under the new cards on the translucent,
frameless window. A second cause: the attachment backfill started for session A
could finish after the switch and write A's messages into B's snapshot.

The old test (test_session_switcher.py) stubs ``refresh_history``; this one
builds a real palette offscreen.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication  # noqa: E402

A_TEXTS = ["alpha question one", "alpha answer one"]
B_TEXTS = ["beta question one", "beta answer one", "beta question two", "beta answer two"]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def palette_and_sessions(qapp, tmp_path, monkeypatch):
    import abstractassistant.app as app_module
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.theme import BASE_METRICS, DEFAULT_THEME, activate, activate_metrics

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    app_module._MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE = False

    controller = AssistantController(config=Config(), data_dir=tmp_path / "data")
    controller.preferences = controller._copy_preferences(hotkey_enabled=False)
    # No gateway in tests: the backfill has nothing to restore.
    monkeypatch.setattr(controller, "backfill_session_attachments", lambda: 0)

    manager = controller.llm_manager
    session_a = manager.active_session_id
    for i, text in enumerate(A_TEXTS):
        manager.append_message(role="user" if i % 2 == 0 else "assistant", content=text)
    session_b = controller.create_session()
    controller.switch_session(session_b)
    for i, text in enumerate(B_TEXTS):
        manager.append_message(role="user" if i % 2 == 0 else "assistant", content=text)
    controller.switch_session(session_a)

    window = app_module.AssistantPalette(controller=controller)
    window.resize(650, 700)
    window.show()
    qapp.processEvents()
    try:
        yield window, session_a, session_b
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()
        activate(DEFAULT_THEME)
        activate_metrics(BASE_METRICS.font_body)


def _cards_under_host(window):
    from abstractassistant.app import MessageCard

    # children(), not findChildren(MessageCard): the typed lookup skips a card
    # already scheduled for deletion, which is exactly the one still painting.
    return [w for w in window.history_host.children() if isinstance(w, MessageCard)]


@pytest.mark.basic
def test_switch_leaves_no_visible_card_of_the_old_session(palette_and_sessions, qapp, monkeypatch) -> None:
    from PyQt5.QtWidgets import QWidget

    from abstractassistant.app import MessageCard

    window, session_a, session_b = palette_and_sessions
    window.refresh_history()
    qapp.processEvents()
    assert sorted(c._content for c in _cards_under_host(window) if c.isVisible()) == sorted(A_TEXTS)

    # When each old card is handed to deleteLater(), it must already be
    # invisible and out of history_host: from then until the event loop gets
    # round to the deletion it would otherwise keep painting.
    retired = []

    def _record(card):
        retired.append((card._content, card.isVisible(), card.parent() is window.history_host))
        QWidget.deleteLater(card)

    monkeypatch.setattr(MessageCard, "deleteLater", _record)
    window._switch_to_session(session_b)
    assert sorted(r[0] for r in retired) == sorted(A_TEXTS)
    still_painting = [content for content, visible, under_host in retired if visible or under_host]
    assert not still_painting, f"old-session cards retired while still painted: {still_painting}"
    qapp.processEvents()

    visible = [c for c in _cards_under_host(window) if c.isVisible()]
    contents = [c._content for c in visible]
    assert not set(contents) & set(A_TEXTS), f"old-session cards still painted: {contents}"
    assert sorted(contents) == sorted(B_TEXTS)
    # Every card in the transcript layout is one of the new session's messages.
    in_layout = [
        window.history_layout.itemAt(i).widget()
        for i in range(window.history_layout.count())
        if window.history_layout.itemAt(i).widget() is not None
        and hasattr(window.history_layout.itemAt(i).widget(), "_content")
    ]
    assert len(in_layout) == len(B_TEXTS)
    assert window.history_scroll.updatesEnabled()


@pytest.mark.basic
def test_a_late_backfill_for_the_old_session_does_not_redraw_the_new_one(palette_and_sessions, qapp, monkeypatch) -> None:
    window, session_a, session_b = palette_and_sessions
    window._attachment_backfill_session = session_a
    window._switch_to_session(session_b)
    qapp.processEvents()
    # Pretend the backfill started for A finished now.
    window._attachment_backfill_session = session_a
    calls = []
    monkeypatch.setattr(window, "refresh_history", lambda *a, **k: calls.append(1))
    window._on_session_attachments_restored(1)
    assert calls == []
    window._attachment_backfill_session = session_b
    window._on_session_attachments_restored(1)
    assert calls == [1]


@pytest.mark.basic
def test_backfill_never_writes_into_a_session_switched_to_meanwhile(tmp_path) -> None:
    from abstractassistant.config import Config
    from abstractassistant.core.llm_manager import LLMManager

    manager = LLMManager(config=Config(), data_dir=tmp_path / "data")
    session_a = manager.active_session_id
    manager.append_message(role="user", content="alpha prompt")
    manager.set_last_run_id("run-a")
    session_b = manager.create_new_session()

    class _Gateway:
        def get_run_history_bundle(self, **_kw):
            # The user switches while this call is in flight.
            manager.switch_session(session_b)
            return {"session": {"turns": [{"prompt": "alpha prompt", "attachments": [{"$artifact": "x", "filename": "f.png"}]}]}}

    manager.switch_session(session_a)
    manager.gateway_client = lambda: _Gateway()  # type: ignore[method-assign]
    assert manager.backfill_attachments_from_gateway() == 0
    assert manager.active_session_id == session_b
    assert [m.get("content") for m in manager.session_messages()] == []
