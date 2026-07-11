import threading
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


@pytest.mark.basic
def test_session_store_concurrent_saves_never_corrupt(tmp_path: Path) -> None:
    """Concurrent saves used to share one .tmp path, interleaving writes into
    invalid JSON. With unique temp names, the file always holds one complete
    snapshot afterwards."""
    store = SessionStore(tmp_path / "session.json")
    snapshots = [
        SessionSnapshot(
            session_id="sess_1",
            actor_id="actor_1",
            messages=[{"role": "user", "content": f"message {i}" * 200}],
            last_run_id=f"run-{i}",
        )
        for i in range(8)
    ]

    threads = [threading.Thread(target=store.save, args=(snap,)) for snap in snapshots]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    loaded = store.load()
    assert loaded is not None, "session.json was corrupted by concurrent saves"
    assert loaded.last_run_id in {f"run-{i}" for i in range(8)}
    leftovers = [p for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert leftovers == []

