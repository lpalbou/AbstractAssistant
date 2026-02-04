from pathlib import Path

import pytest

from abstractassistant.core.session_store import SessionSnapshot, SessionStore


@pytest.mark.basic
def test_session_store_round_trip(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "session.json")
    snap = SessionSnapshot(session_id="sess_1", actor_id="actor_1", messages=[{"role": "user", "content": "hi"}])
    store.save(snap)
    loaded = store.load()
    assert loaded is not None
    assert loaded.session_id == "sess_1"
    assert loaded.actor_id == "actor_1"
    assert loaded.messages and loaded.messages[0]["content"] == "hi"

