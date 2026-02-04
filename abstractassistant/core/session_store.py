"""Session persistence for AbstractAssistant.

This module stores *host UX state* (session id, actor id, and chat transcript snapshot)
separately from AbstractRuntime stores. The runtime remains the source of truth for run
durability; this file is a convenience for fast app startup and UX continuity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str
    actor_id: str
    messages: List[Dict[str, Any]]
    last_run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "actor_id": self.actor_id,
            "messages": list(self.messages),
            "last_run_id": self.last_run_id,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "SessionSnapshot":
        session_id = str(raw.get("session_id") or "").strip()
        actor_id = str(raw.get("actor_id") or "").strip()
        if not session_id:
            raise ValueError("session_id is required")
        if not actor_id:
            raise ValueError("actor_id is required")
        messages_raw = raw.get("messages")
        messages: List[Dict[str, Any]] = []
        if isinstance(messages_raw, list):
            for m in messages_raw:
                if isinstance(m, dict):
                    messages.append(dict(m))
        last_run_id_raw = raw.get("last_run_id")
        last_run_id = str(last_run_id_raw).strip() if last_run_id_raw is not None else None
        if last_run_id == "":
            last_run_id = None
        return cls(session_id=session_id, actor_id=actor_id, messages=messages, last_run_id=last_run_id)


class SessionStore:
    def __init__(self, path: Path):
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Optional[SessionSnapshot]:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        try:
            return SessionSnapshot.from_dict(data)
        except Exception:
            return None

    def save(self, snapshot: SessionSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self._path)

