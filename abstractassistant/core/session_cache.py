"""The Assistant's local session cache — rebuildable, never a source of truth.

Which sessions exist, their turns and their transcripts belong to the gateway
(see ``gateway_sessions``). What lives here is only what makes the app fast and
usable offline, keyed by the gateway ``session_id``:

- ``<data_dir>/session_cache.json`` — the active session id, the user's local
  labels (renames), the opening prompts already fetched, last-seen stamps,
  sessions the user removed from this list, and the last session rows the
  gateway returned (shown, marked as cached, while it cannot be reached);
- ``<data_dir>/sessions/<session_id>/session.json`` — a cached transcript,
  painted instantly and REPLACED by the gateway's history when the session is
  opened.

Deleting all of it loses nothing but labels and removals: the next refresh
lists the same sessions from the gateway and opening one rebuilds its
transcript.

A new session still mints its id here (the gateway accepts any id and learns it
with the first run); until that run exists it is listed only while it is the
active session.

Migration from the local-first index of 0.6.1 and earlier
(``sessions.json`` + ``session.json`` in the data dir) happens in two steps:
at construction the old files are converted to this layout and the old index is
moved to ``sessions-legacy/``; on the first COMPLETE listing from the gateway,
every old session the gateway does not know is dropped from the list and its
folder moved to ``sessions-legacy/`` — never deleted — with one notice.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
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
    "LEGACY_INDEX_FILE",
    "LEGACY_DIR",
    "SESSION_ID_PREFIX",
    "SWITCHER_TABS",
    "UNREADABLE_MARKER",
]

CACHE_FILE = "session_cache.json"
LEGACY_INDEX_FILE = "sessions.json"
LEGACY_DIR = "sessions-legacy"
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


def _placeholder(title: str) -> bool:
    return str(title or "").strip().lower() in {"", "new session", "new chat"}


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
        self._hidden: List[str] = []
        self._rows: List[GatewaySession] = []
        self._fetched_at = ""
        self._truncated = False
        self._notice = ""
        self._switcher_tab = SWITCHER_TABS[0]
        # Sessions converted from the 0.6.1-and-earlier local index that the gateway has
        # not yet confirmed: {session_id: {"created_at", "updated_at"}}.
        self._legacy_pending: Dict[str, Dict[str, str]] = {}
        self._load()

    # ------------------------------------------------------------ properties

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def path(self) -> Path:
        return self._path

    @property
    def legacy_dir(self) -> Path:
        return self._base_dir / LEGACY_DIR

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

    def is_hidden(self, session_id: str) -> bool:
        with self._lock:
            return str(session_id or "").strip() in self._hidden

    def remove_from_list(self, session_id: str) -> str:
        """Hide a session from this list; its local text is KEPT.

        The gateway has no route to delete a session, so its runs stay there;
        hiding is a local preference, like a label. The cached folder moves to
        ``sessions-legacy/`` rather than being deleted: for a session that
        exists only on this machine (never run, or an old local session the
        migration has not decided yet) it is the only copy. Returns the active
        session id afterwards (a new session when the removed one was active).
        """
        sid = str(session_id or "").strip()
        if not sid:
            return self.active_session_id
        with self._lock:
            if sid not in self._hidden:
                self._hidden.append(sid)
            self._labels.pop(sid, None)
            self._legacy_pending.pop(sid, None)
            folder = self.data_dir_for(sid)
            if folder.exists():
                target = self.legacy_dir / folder.name
                if target.exists():
                    target = self.legacy_dir / f"{folder.name}-removed-{uuid.uuid4().hex[:6]}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(folder), str(target))
            if self._active_session_id == sid:
                candidates = [r.session_id for r in self._rows if r.session_id not in self._hidden]
                if candidates:
                    self._active_session_id = candidates[0]
                else:
                    self._mint_locked()
            self._save_locked()
            return self._active_session_id

    def legacy_copy_for(self, session_id: str) -> Optional[Path]:
        """The kept transcript of a session moved to ``sessions-legacy/``, if any."""
        sid = str(session_id or "").strip()
        if not sid:
            return None
        candidate = self.legacy_dir / self.data_dir_for(sid).name / "session.json"
        return candidate if candidate.exists() else None

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

    # ------------------------------------------------------------ migration

    def legacy_pending(self) -> Dict[str, Dict[str, str]]:
        with self._lock:
            return {sid: dict(meta) for sid, meta in self._legacy_pending.items()}

    def reconcile_legacy(self, gateway_ids: Iterable[str], *, complete: bool) -> Optional[int]:
        """Drop 0.6.1-and-earlier local sessions the gateway does not know.

        Runs once, on the first COMPLETE listing (a truncated page cannot prove
        a session absent; the decision is then deferred). Returns how many
        sessions were removed from the list, or None when deferred / nothing
        was pending. Removed folders move to ``sessions-legacy/`` — the text is
        kept. The ACTIVE session is never moved while in use: when it is
        local-only its transcript is copied there and it stays listed only
        while active, like any session without a gateway run.
        """
        with self._lock:
            if not self._legacy_pending:
                return None
            if not complete:
                return None
            known = {str(s) for s in gateway_ids}
            removed = 0
            for sid in list(self._legacy_pending):
                if sid in known:
                    continue
                removed += 1
                self._labels.pop(sid, None)
                folder = self.data_dir_for(sid)
                target = self.legacy_dir / folder.name
                if not folder.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                if sid == self._active_session_id:
                    if not target.exists():
                        shutil.copytree(folder, target)
                elif not target.exists():
                    shutil.move(str(folder), str(target))
            self._legacy_pending = {}
            if removed:
                plural = removed != 1
                self._notice = (
                    f"{removed} local-only session{'s' if plural else ''} from an earlier version "
                    f"{'were' if plural else 'was'} removed from the list; their text is kept in {self.legacy_dir}"
                )
            self._save_locked()
            return removed

    def take_notice(self) -> str:
        """The one-time migration notice (cleared once read)."""
        with self._lock:
            notice = self._notice
            if notice:
                self._notice = ""
                self._save_locked()
            return notice

    def peek_notice(self) -> str:
        with self._lock:
            return self._notice

    # ------------------------------------------------------------ persistence

    def _load(self) -> None:
        with self._lock:
            data: Any = None
            if self._path.exists():
                try:
                    data = json.loads(self._path.read_text(encoding="utf-8"))
                except Exception:
                    # A broken cache is rebuilt, never trusted — keep it aside.
                    self._set_aside(self._path)
                    data = None
            if isinstance(data, dict):
                self._active_session_id = str(data.get("active_session_id") or "").strip()
                self._labels = {str(k): str(v) for k, v in dict(data.get("labels") or {}).items() if str(v).strip()}
                self._prompts = {str(k): str(v) for k, v in dict(data.get("prompts") or {}).items()}
                self._last_seen = {str(k): str(v) for k, v in dict(data.get("last_seen") or {}).items()}
                self._hidden = [str(s) for s in (data.get("hidden") or []) if str(s).strip()]
                self._rows = [r for r in (GatewaySession.from_dict(x) for x in (data.get("rows") or [])) if r is not None]
                self._fetched_at = str(data.get("fetched_at") or "")
                self._truncated = bool(data.get("truncated"))
                self._notice = str(data.get("notice") or "")
                tab = str(data.get("switcher_tab") or "")
                self._switcher_tab = tab if tab in SWITCHER_TABS else SWITCHER_TABS[0]
                pending = data.get("legacy_pending")
                if isinstance(pending, dict):
                    self._legacy_pending = {
                        str(k): {kk: str(vv) for kk, vv in dict(v or {}).items()} for k, v in pending.items()
                    }
            legacy_index = self._base_dir / LEGACY_INDEX_FILE
            if legacy_index.exists():
                # Also resumes a conversion interrupted by a crash: every step
                # below is idempotent.
                self._convert_legacy_index(legacy_index)
                return
            if not self._active_session_id:
                self._mint_locked()
            self._save_locked()

    def _convert_legacy_index(self, legacy_index: Path) -> None:
        """Step one of the migration: the 0.6.1-and-earlier files become this cache.

        Local only, and crash-safe: every old session with text on disk is
        first RECORDED — its rename as a label, the session as PENDING until
        the gateway confirms it — and ``session_cache.json`` is written
        (atomic rename) before any file moves. Only then is the legacy base
        session's transcript moved into ``sessions/<id>/`` and the old index
        set aside into ``sessions-legacy/``. A crash at any point leaves either
        the old index in place (the next start resumes here) or a cache that
        already references everything.
        """
        try:
            data = json.loads(legacy_index.read_text(encoding="utf-8"))
        except Exception:
            data = None
        records = data.get("sessions") if isinstance(data, dict) else None
        records = [item for item in (records if isinstance(records, list) else []) if isinstance(item, dict)]
        base_snapshot = self._base_dir / "session.json"
        confirmed = {row.session_id for row in self._rows}

        def _source(item: Dict[str, Any]) -> Path:
            rel = str(item.get("path") or "").strip() or "."
            return base_snapshot if rel == "." else self._base_dir / Path(rel)

        # 1. Record everything, then persist — before anything moves.
        for item in records:
            sid = str(item.get("session_id") or "").strip()
            if not sid or sid in self._hidden:
                continue
            target = self.data_dir_for(sid)
            if not (_source(item).exists() or (target / "session.json").exists()):
                continue
            title = str(item.get("title") or "")
            if not _placeholder(title) and sid not in self._labels:
                self._labels[sid] = safe_title(title)
            if sid not in confirmed and sid not in self._legacy_pending:
                self._legacy_pending[sid] = {
                    "created_at": str(item.get("created_at") or ""),
                    "updated_at": str(item.get("updated_at") or ""),
                }
        if not self._active_session_id:
            active = str(data.get("active_session_id") or "").strip() if isinstance(data, dict) else ""
            if active and (active in self._legacy_pending or active in confirmed):
                self._active_session_id = active
            elif self._legacy_pending:
                newest = sorted(self._legacy_pending.items(), key=lambda kv: kv[1].get("updated_at", ""), reverse=True)
                self._active_session_id = newest[0][0]
            else:
                self._mint_locked()
        self._save_locked()

        # 2. Move transcripts into the cache layout (skipped when already done).
        for item in records:
            sid = str(item.get("session_id") or "").strip()
            if not sid or sid in self._hidden:
                continue
            source = _source(item)
            target = self.data_dir_for(sid)
            if not source.exists():
                continue
            if source == base_snapshot:
                if not (target / "session.json").exists():
                    target.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(base_snapshot), str(target / "session.json"))
            elif source.resolve() != target.resolve() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))

        # 3. The old index is kept, not deleted; so is a base snapshot no
        # record referenced (a legacy session the user had deleted).
        self._set_aside(legacy_index, keep_name=True)
        if base_snapshot.exists():
            self._set_aside(base_snapshot, keep_name=True)
        self._save_locked()

    def set_aside(self, path: Path) -> Optional[Path]:
        """Move an unreadable cache file into ``sessions-legacy/`` (kept, never
        overwritten). Returns where it went, or None if it could not move."""
        with self._lock:
            return self._set_aside(Path(path))

    def _set_aside(self, path: Path, *, keep_name: bool = False) -> Optional[Path]:
        try:
            self.legacy_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            name = path.name if keep_name else f"{path.parent.name}-{path.name}.unreadable-{stamp}"
            target = self.legacy_dir / name
            if target.exists():
                target = self.legacy_dir / f"{name}.{uuid.uuid4().hex[:6]}"
            shutil.move(str(path), str(target))
            return target
        except Exception:
            return None

    def _save_locked(self) -> None:
        payload = {
            "version": _CACHE_VERSION,
            "active_session_id": self._active_session_id,
            "labels": dict(self._labels),
            "prompts": dict(self._prompts),
            "last_seen": dict(self._last_seen),
            "hidden": list(self._hidden),
            "rows": [r.to_dict() for r in self._rows],
            "fetched_at": self._fetched_at,
            "truncated": self._truncated,
            "switcher_tab": self._switcher_tab,
        }
        if self._notice:
            payload["notice"] = self._notice
        if self._legacy_pending:
            payload["legacy_pending"] = {k: dict(v) for k, v in self._legacy_pending.items()}
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
