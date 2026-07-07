"""Gateway snapshot replacement regressions for AbstractAssistant."""

from __future__ import annotations

import pytest

from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.core.session_store import SessionSnapshot


@pytest.mark.basic
def test_replace_gateway_messages_allows_gateway_replay_to_shrink_local_history() -> None:
    manager = LLMManager.__new__(LLMManager)
    manager.use_gateway = True
    manager._gateway_store = None
    manager._refresh_session_view = lambda: None

    existing_messages = [
        {"role": "user", "content": "first", "ts": "2026-06-14T10:00:00+00:00"},
        {"role": "assistant", "content": "second", "ts": "2026-06-14T10:00:01+00:00"},
    ]
    manager._gateway_snapshot = SessionSnapshot(
        session_id="session-1",
        actor_id="gateway",
        messages=list(existing_messages),
        last_run_id="run-old",
    )

    saved: list[SessionSnapshot] = []
    manager._save_gateway_snapshot = lambda snapshot: saved.append(snapshot)

    manager.replace_gateway_messages(
        [{"role": "user", "content": "only latest", "ts": "2026-06-14T10:01:00+00:00"}],
        last_run_id="run-new",
    )

    assert [msg["content"] for msg in manager._gateway_snapshot.messages] == ["only latest"]
    assert manager._gateway_snapshot.last_run_id == "run-new"
    assert [msg["content"] for msg in saved[-1].messages] == ["only latest"]


@pytest.mark.basic
def test_replace_gateway_messages_accepts_longer_history_snapshots() -> None:
    manager = LLMManager.__new__(LLMManager)
    manager.use_gateway = True
    manager._gateway_store = None
    manager._refresh_session_view = lambda: None
    manager._gateway_snapshot = SessionSnapshot(
        session_id="session-1",
        actor_id="gateway",
        messages=[{"role": "user", "content": "first", "ts": "2026-06-14T10:00:00+00:00"}],
        last_run_id="run-old",
    )
    manager._save_gateway_snapshot = lambda snapshot: None

    manager.replace_gateway_messages(
        [
            {"role": "user", "content": "first", "ts": "2026-06-14T10:00:00+00:00"},
            {"role": "assistant", "content": "second", "ts": "2026-06-14T10:00:01+00:00"},
        ],
        last_run_id="run-new",
    )

    assert [msg["role"] for msg in manager._gateway_snapshot.messages] == ["user", "assistant"]
    assert [msg["content"] for msg in manager._gateway_snapshot.messages] == ["first", "second"]
    assert all(str(msg.get("message_id") or "").strip() for msg in manager._gateway_snapshot.messages)
    assert manager._gateway_snapshot.last_run_id == "run-new"


@pytest.mark.basic
def test_append_gateway_message_assigns_message_id() -> None:
    manager = LLMManager.__new__(LLMManager)
    manager.use_gateway = True
    manager._gateway_store = None
    manager._refresh_session_view = lambda: None
    manager._gateway_snapshot = SessionSnapshot(
        session_id="session-1",
        actor_id="gateway",
        messages=[],
        last_run_id=None,
    )
    manager._save_gateway_snapshot = lambda snapshot: None

    manager.append_message(role="assistant", content="hello")

    stored = manager._gateway_snapshot.messages[-1]
    assert stored["role"] == "assistant"
    assert stored["content"] == "hello"
    assert str(stored.get("message_id") or "").strip()
