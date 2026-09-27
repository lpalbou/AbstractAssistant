"""The Assistant's local session cache — rebuildable, never a source of truth.

A session exists if and only if the gateway lists it (see ``gateway_sessions``);
there is no local-only session, no local removal and no local archive. What
lives here is only what makes the app fast and usable offline, keyed by the
gateway ``session_id``:

- ``<data_dir>/session_cache.json`` — the active session id, the user's local
  labels (renames), the opening prompts already fetched, last-seen stamps, the
  remembered switcher tab, and the last session rows the gateway returned
  (shown, marked as cached, while it cannot be reached);
- ``<data_dir>/sessions/<session_id>/session.json`` — a cached transcript,
  painted instantly and REPLACED by the gateway's history when the session is
  opened.

Deleting all of it loses nothing but labels: the next refresh lists the same
sessions from the gateway and opening one rebuilds its transcript. An
unreadable cache file is discarded and rebuilt, never kept aside.

A new session mints its id here (the gateway accepts any id and learns it with
the first run); until that run exists it is shown only while it is the active
session — it becomes a gateway session with its first turn.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .gateway_sessions import GatewaySession
from .session_store import SessionSnapshot, SessionStore

__all__ = [
    "SessionCache",
    "safe_title",
    "CACHE_FILE",
    "SESSION_ID_PREFIX",
    "SWITCHER_TABS",
    "UNREADABLE_MARKER",
]

CACHE_FILE = "session_cache.json"
# Written next to a cached transcript that could not be read, until the
# gateway has rebuilt it — so the problem is still said after a restart.
UNREADABLE_MARKER = "session.unreadable.json"
# How this client names the sessions it mints (`create_session`). A naming
# convention only: the list shows EVERY gateway session (operator ruling
# 2026-09-27, "all clients must have access to the same pool of sessions"), so
# nothing is ever classified by its id.
SESSION_ID_PREFIX = "sess_"
# The switcher's two tabs; the last one used is remembered here.
SWITCHER_TABS = ("sessions", "automations")
_CACHE_VERSION = 1

_TITLE_MAX = 80  # session-picker title bound (marked when it bites; ADR-0026)
_SAFE_DIR_NAME = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_title(title: str) -> str:
    """One line, bounded, for a label or an opening prompt shown as a title."""
    t = str(title or "").strip()
    if not t:
        return ""
    # ADR-0026 §1: a bare cut reads back as the whole title — mark it instead.
    # The conversation itself is never touched.
    t = " ".join(t.replace("\n", " ").replace("\r", " ").split())
    if len(t) <= _TITLE_MAX:
        return t
    #[WARNING:TRUNCATION] session title bounded for the picker
    return t[: _TITLE_MAX - 1].rstrip() + "…"


class SessionCache:
    """Local cache state for the session list (thread-safe)."""

    def __init__(self, base_dir: Path):
        self._base_dir = Path(base_dir).expanduser()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._base_dir / CACHE_FILE
        self._lock = threading.RLock()
        self._active_session_id = ""
        self._labels: Dict[str, str] = {}
        self._prompts: Dict[str, str] = {}
        self._last_seen: Dict[str, str] = {}
        self._rows: List[GatewaySession] = []
        self._fetched_at = ""
        self._truncated = False
        self._switcher_tab = SWITCHER_TABS[0]
        self._load()

    # ------------------------------------------------------------ properties

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def path(self) -> Path:
        return self._path

    @property
    def active_session_id(self) -> str:
        with self._lock:
            if not self._active_session_id:
                self._mint_locked()
                self._save_locked()
            return self._active_session_id

    # ------------------------------------------------------------- sessions

    def data_dir_for(self, session_id: str) -> Path:
        """The cache folder for a gateway session id (any id is accepted)."""
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id must be non-empty")
        name = sid if _SAFE_DIR_NAME.match(sid) else "sha_" + hashlib.sha256(sid.encode("utf-8")).hexdigest()[:32]
        return self._base_dir / "sessions" / name

    def set_active(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id must be non-empty")
        with self._lock:
            self._active_session_id = sid
            self._last_seen[sid] = _utc_now_iso()
            self._save_locked()

    def create_session(self) -> str:
        """Mint a new session id locally and make it active."""
        with self._lock:
            sid = self._mint_locked()
            self._save_locked()
            return sid

    def _mint_locked(self) -> str:
        sid = f"{SESSION_ID_PREFIX}{uuid.uuid4().hex}"
        SessionStore(self.data_dir_for(sid) / "session.json").save(
            SessionSnapshot(session_id=sid, actor_id="gateway", messages=[], last_run_id=None)
        )
        self._active_session_id = sid
        self._last_seen[sid] = _utc_now_iso()
        return sid

    def label(self, session_id: str) -> str:
        with self._lock:
            return self._labels.get(str(session_id or "").strip(), "")

    def set_label(self, session_id: str, title: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            return
        value = safe_title(title)
        with self._lock:
            if value:
                self._labels[sid] = value
            else:
                self._labels.pop(sid, None)
            self._save_locked()

    def prompt(self, session_id: str) -> Optional[str]:
        """The gateway opening prompt already fetched ("" = the gateway had
        none), or None when it was never fetched."""
        with self._lock:
            return self._prompts.get(str(session_id or "").strip())

    def set_prompts(self, prompts: Dict[str, str]) -> None:
        if not prompts:
            return
        with self._lock:
            for sid, text in prompts.items():
                if str(sid or "").strip():
                    self._prompts[str(sid).strip()] = safe_title(text)
            self._save_locked()

    def last_seen(self, session_id: str) -> str:
        with self._lock:
            return self._last_seen.get(str(session_id or "").strip(), "")

    # ------------------------------------------------------ unreadable marker

    def mark_unreadable(self, session_id: str, problem: str) -> None:
        folder = self.data_dir_for(session_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / UNREADABLE_MARKER).write_text(
            json.dumps({"problem": str(problem), "at": _utc_now_iso()}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def unreadable_problem(self, session_id: str) -> str:
        marker = self.data_dir_for(session_id) / UNREADABLE_MARKER
        if not marker.exists():
            return ""
        try:
            return str(json.loads(marker.read_text(encoding="utf-8")).get("problem") or "") or "The local copy of this session could not be read."
        except Exception:
            return "The local copy of this session could not be read."

    def clear_unreadable(self, session_id: str) -> None:
        try:
            (self.data_dir_for(session_id) / UNREADABLE_MARKER).unlink()
        except FileNotFoundError:
            pass

    # ------------------------------------------------------- switcher tab

    @property
    def switcher_tab(self) -> str:
        with self._lock:
            return self._switcher_tab

    def set_switcher_tab(self, tab: str) -> None:
        if tab not in SWITCHER_TABS:
            raise ValueError(f"unknown switcher tab {tab!r}")
        with self._lock:
            if tab != self._switcher_tab:
                self._switcher_tab = tab
                self._save_locked()

    # --------------------------------------------------------- gateway rows

    def rows(self) -> List[GatewaySession]:
        with self._lock:
            return list(self._rows)

    def row(self, session_id: str) -> Optional[GatewaySession]:
        sid = str(session_id or "").strip()
        with self._lock:
            for row in self._rows:
                if row.session_id == sid:
                    return row
        return None

    @property
    def fetched_at(self) -> str:
        with self._lock:
            return self._fetched_at

    @property
    def truncated(self) -> bool:
        with self._lock:
            return self._truncated

    def set_rows(self, rows: Iterable[GatewaySession], *, truncated: bool) -> None:
        with self._lock:
            self._rows = [r for r in rows if isinstance(r, GatewaySession)]
            self._truncated = bool(truncated)
            self._fetched_at = _utc_now_iso()
            self._save_locked()

    # ------------------------------------------------------------ persistence

    def _load(self) -> None:
        with self._lock:
            data: Any = None
            if self._path.exists():
                try:
                    data = json.loads(self._path.read_text(encoding="utf-8"))
                except Exception:
                    # A broken cache is rebuilt, never trusted.
                    self.discard(self._path)
                    data = None
            if isinstance(data, dict):
                self._active_session_id = str(data.get("active_session_id") or "").strip()
                self._labels = {str(k): str(v) for k, v in dict(data.get("labels") or {}).items() if str(v).strip()}
                self._prompts = {str(k): str(v) for k, v in dict(data.get("prompts") or {}).items()}
                self._last_seen = {str(k): str(v) for k, v in dict(data.get("last_seen") or {}).items()}
                self._rows = [r for r in (GatewaySession.from_dict(x) for x in (data.get("rows") or [])) if r is not None]
                self._fetched_at = str(data.get("fetched_at") or "")
                self._truncated = bool(data.get("truncated"))
                tab = str(data.get("switcher_tab") or "")
                self._switcher_tab = tab if tab in SWITCHER_TABS else SWITCHER_TABS[0]
            if not self._active_session_id:
                self._mint_locked()
            self._save_locked()

    @staticmethod
    def discard(path: Path) -> None:
        """Delete an unreadable cache file: the gateway rebuilds its content."""
        try:
            Path(path).unlink()
        except FileNotFoundError:
            pass

    def _save_locked(self) -> None:
        payload = {
            "version": _CACHE_VERSION,
            "active_session_id": self._active_session_id,
            "labels": dict(self._labels),
            "prompts": dict(self._prompts),
            "last_seen": dict(self._last_seen),
            "rows": [r.to_dict() for r in self._rows],
            "fetched_at": self._fetched_at,
            "truncated": self._truncated,
            "switcher_tab": self._switcher_tab,
        }
        self._base_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(f"{self._path.suffix}.tmp-{uuid.uuid4().hex[:8]}")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self._path)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
