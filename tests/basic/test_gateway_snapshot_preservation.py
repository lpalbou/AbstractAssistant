"""Gateway snapshot preservation regressions for AbstractAssistant."""

from __future__ import annotations

import warnings

import pytest

from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.core.session_store import SessionSnapshot


@pytest.mark.basic
def test_replace_gateway_messages_does_not_shrink_existing_history() -> None:
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

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager.replace_gateway_messages(
            [{"role": "user", "content": "only latest", "ts": "2026-06-14T10:01:00+00:00"}],
            last_run_id="run-new",
        )

    assert manager._gateway_snapshot.messages == existing_messages
    assert manager._gateway_snapshot.last_run_id == "run-new"
    assert saved[-1].messages == existing_messages
    assert any("shorter than the local session snapshot" in str(item.message) for item in caught)


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

    assert manager._gateway_snapshot.messages == [
        {"role": "user", "content": "first", "ts": "2026-06-14T10:00:00+00:00"},
        {"role": "assistant", "content": "second", "ts": "2026-06-14T10:00:01+00:00"},
    ]
    assert manager._gateway_snapshot.last_run_id == "run-new"
