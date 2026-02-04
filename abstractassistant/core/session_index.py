"""Durable multi-session index for AbstractAssistant.

AbstractAssistant already persists a single session under the data dir:
- `session.json` (transcript snapshot + ids)
- `runtime/` (AbstractRuntime stores)

This module adds a light registry so the tray UI can manage *multiple* sessions.
New sessions are created under:
  <data_dir>/sessions/<session_id>/
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .session_store import SessionSnapshot, SessionStore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_title(title: str) -> str:
    t = str(title or "").strip()
    if not t:
        return "New session"
    # Keep dropdown readable.
    t = t.replace("\n", " ").replace("\r", " ").strip()
    return t[:80] if len(t) > 80 else t


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    actor_id: str
    title: str
    path: str  # relative to base_dir, "." for legacy/base session
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "actor_id": self.actor_id,
            "title": self.title,
            "path": self.path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "SessionRecord":
        sid = str(raw.get("session_id") or "").strip()
        aid = str(raw.get("actor_id") or "").strip()
        if not sid:
            raise ValueError("session_id is required")
        if not aid:
            raise ValueError("actor_id is required")
        title = _safe_title(str(raw.get("title") or ""))
        path = str(raw.get("path") or "").strip() or "."
        created_at = str(raw.get("created_at") or "").strip() or _utc_now_iso()
        updated_at = str(raw.get("updated_at") or "").strip() or created_at
        return cls(
            session_id=sid,
            actor_id=aid,
            title=title,
            path=path,
            created_at=created_at,
            updated_at=updated_at,
        )


class SessionIndex:
    """Stores the list of durable sessions and the active session."""

    def __init__(self, base_dir: Path):
        self._base_dir = Path(base_dir).expanduser()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._base_dir / "sessions.json"
        self._active_session_id: Optional[str] = None
        self._sessions: List[SessionRecord] = []
        self._load_or_bootstrap()

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def path(self) -> Path:
        return self._path

    @property
    def active_session_id(self) -> str:
        sid = str(self._active_session_id or "").strip()
        if sid:
            return sid
        if self._sessions:
            return self._sessions[0].session_id
        # Should not happen; bootstrap guarantees at least one session.
        return self._ensure_legacy_session().session_id

    def active_record(self) -> SessionRecord:
        return self.get(self.active_session_id)

    def records(self) -> List[SessionRecord]:
        # Sort by recency (updated_at is ISO).
        return sorted(self._sessions, key=lambda r: str(r.updated_at), reverse=True)

    def get(self, session_id: str) -> SessionRecord:
        sid = str(session_id or "").strip()
        for r in self._sessions:
            if r.session_id == sid:
                return r
        raise KeyError(f"Unknown session_id: {sid}")

    def data_dir_for(self, session_id: str) -> Path:
        rec = self.get(session_id)
        rel = Path(rec.path)
        return (self._base_dir / rel).resolve()

    def set_active(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id must be non-empty")
        _ = self.get(sid)  # validate
        self._active_session_id = sid
        self._save()

    def touch(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            return
        now = _utc_now_iso()
        updated: List[SessionRecord] = []
        for r in self._sessions:
            if r.session_id != sid:
                updated.append(r)
                continue
            updated.append(
                SessionRecord(
                    session_id=r.session_id,
                    actor_id=r.actor_id,
                    title=r.title,
                    path=r.path,
                    created_at=r.created_at,
                    updated_at=now,
                )
            )
        self._sessions = updated
        self._save()

    def update_title(self, session_id: str, title: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            return
        now = _utc_now_iso()
        new_title = _safe_title(title)
        updated: List[SessionRecord] = []
        for r in self._sessions:
            if r.session_id != sid:
                updated.append(r)
                continue
            updated.append(
                SessionRecord(
                    session_id=r.session_id,
                    actor_id=r.actor_id,
                    title=new_title,
                    path=r.path,
                    created_at=r.created_at,
                    updated_at=now,
                )
            )
        self._sessions = updated
        self._save()

    def create_session(self) -> SessionRecord:
        """Create a new durable session directory and set it active."""
        session_id = f"sess_{uuid.uuid4().hex}"
        actor_id = f"actor_{uuid.uuid4().hex}"
        now = _utc_now_iso()
        rel_path = Path("sessions") / session_id
        data_dir = self._base_dir / rel_path
        data_dir.mkdir(parents=True, exist_ok=True)

        # Create an empty snapshot so AgentHost loads the intended ids.
        store = SessionStore(data_dir / "session.json")
        store.save(SessionSnapshot(session_id=session_id, actor_id=actor_id, messages=[], last_run_id=None))

        rec = SessionRecord(
            session_id=session_id,
            actor_id=actor_id,
            title="New session",
            path=str(rel_path).replace("\\", "/"),
            created_at=now,
            updated_at=now,
        )
        self._sessions.append(rec)
        self._active_session_id = session_id
        self._save()
        return rec

    def _load_or_bootstrap(self) -> None:
        data = None
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                data = None

        if not isinstance(data, dict):
            self._bootstrap()
            return

        sessions_raw = data.get("sessions")
        sessions: List[SessionRecord] = []
        if isinstance(sessions_raw, list):
            for item in sessions_raw:
                if not isinstance(item, dict):
                    continue
                try:
                    sessions.append(SessionRecord.from_dict(item))
                except Exception:
                    continue

        # Always ensure legacy/base session is present (for back-compat).
        legacy = self._ensure_legacy_session()
        if not any(r.session_id == legacy.session_id for r in sessions):
            sessions.append(legacy)

        # Filter out missing directories (except legacy ".").
        filtered: List[SessionRecord] = []
        for r in sessions:
            if r.path == ".":
                filtered.append(r)
                continue
            if (self._base_dir / Path(r.path)).exists():
                filtered.append(r)
        if not filtered:
            filtered = [legacy]

        active = str(data.get("active_session_id") or "").strip()
        if not active or not any(r.session_id == active for r in filtered):
            active = filtered[0].session_id

        self._sessions = filtered
        self._active_session_id = active
        self._save()

    def _bootstrap(self) -> None:
        legacy = self._ensure_legacy_session()
        self._sessions = [legacy]
        self._active_session_id = legacy.session_id
        self._save()

    def _ensure_legacy_session(self) -> SessionRecord:
        """Ensure base_dir/session.json exists and return its record."""
        store = SessionStore(self._base_dir / "session.json")
        snap = store.load()
        if snap is None:
            snap = SessionSnapshot(
                session_id=f"sess_{uuid.uuid4().hex}",
                actor_id=f"actor_{uuid.uuid4().hex}",
                messages=[],
                last_run_id=None,
            )
            store.save(snap)

        now = _utc_now_iso()
        # Keep title best-effort: if an index exists we will override from it.
        return SessionRecord(
            session_id=str(snap.session_id),
            actor_id=str(snap.actor_id),
            title="New session",
            path=".",
            created_at=now,
            updated_at=now,
        )

    def _save(self) -> None:
        payload = {
            "active_session_id": self.active_session_id,
            "sessions": [r.to_dict() for r in self._sessions],
        }
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self._path)

