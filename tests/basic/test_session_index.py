from pathlib import Path

import pytest

from abstractassistant.core.session_index import SessionIndex
from abstractassistant.core.session_store import SessionStore


@pytest.mark.basic
def test_session_index_bootstraps_legacy_session(tmp_path: Path) -> None:
    idx = SessionIndex(tmp_path)
    assert (tmp_path / "sessions.json").exists()
    assert (tmp_path / "session.json").exists()

    legacy_snap = SessionStore(tmp_path / "session.json").load()
    assert legacy_snap is not None
    assert idx.active_session_id == legacy_snap.session_id


@pytest.mark.basic
def test_session_index_create_and_switch_persists(tmp_path: Path) -> None:
    idx = SessionIndex(tmp_path)
    legacy_id = idx.active_session_id

    rec = idx.create_session()
    assert rec.session_id != legacy_id
    assert idx.active_session_id == rec.session_id
    assert rec.path.startswith("sessions/")
    assert (tmp_path / "sessions" / rec.session_id / "session.json").exists()

    new_snap = SessionStore(tmp_path / "sessions" / rec.session_id / "session.json").load()
    assert new_snap is not None
    assert new_snap.session_id == rec.session_id
    assert new_snap.actor_id == rec.actor_id

    idx.set_active(legacy_id)
    assert idx.active_session_id == legacy_id

    idx2 = SessionIndex(tmp_path)
    assert idx2.active_session_id == legacy_id

    idx2.update_title(rec.session_id, "My Session Title")
    idx3 = SessionIndex(tmp_path)
    assert idx3.get(rec.session_id).title == "My Session Title"

