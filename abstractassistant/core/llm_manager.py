"""Gateway session manager for AbstractAssistant (legacy class name retained).

The assistant is a gateway-native thin client: AbstractGateway owns workflows,
durable execution, providers, and media routing. This module owns the local
side of a session — the durable transcript snapshot (`session.json` per
session), the session index, and a cached `GatewayClient`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .session_index import SessionIndex
from .session_store import SessionStore, SessionSnapshot
from ..gateway import GatewayClient, GatewayClientConfig, get_cached_assistant_capabilities
import uuid
import warnings


class LLMManager:
    """Local session/transcript state plus the shared gateway client."""

    # Class-level default so instances built without __init__ (tests, tools)
    # still lock correctly; __init__ replaces it with a per-instance lock.
    _snapshot_lock: threading.RLock = threading.RLock()

    def __init__(self, config=None, debug: bool = False, *, data_dir: Optional[Path] = None):
        if config is None:
            from ..config import Config

            config = Config.default()

        self.config = config
        self.debug = bool(debug)
        self._gateway_client: Optional[GatewayClient] = None

        self.data_dir = (Path(data_dir).expanduser() if data_dir is not None else (Path.home() / ".abstractassistant"))
        self._session_index = SessionIndex(self.data_dir)
        # Serializes gateway-snapshot read-copy-write + save. Appends arrive
        # from the GatewayWorker thread, wait-submit threads, and the Qt main
        # thread; without this, concurrent appends are last-writer-wins.
        self._snapshot_lock = threading.RLock()

        self._gateway_store: Optional[SessionStore] = None
        self._gateway_snapshot: Optional[SessionSnapshot] = self._load_gateway_snapshot(self.active_session_id)
        self._prefetch_gateway_capabilities()

    def gateway_client(self) -> Optional[GatewayClient]:
        """Return the cached GatewayClient for the configured gateway."""
        gw = getattr(self.config, "gateway", None)
        url = str(getattr(gw, "url", "") or "").strip()
        if not url:
            raise ValueError("Gateway URL is required")
        token = str(getattr(gw, "auth_token", "") or "").strip()
        auth_mode = str(getattr(gw, "auth_mode", "bearer") or "bearer").strip() or "bearer"
        user_id = str(getattr(gw, "user_id", "") or "").strip()
        session_id = str(getattr(gw, "session_id", "") or "").strip()
        csrf_token = str(getattr(gw, "csrf_token", "") or "").strip()
        session_expires_at = str(getattr(gw, "session_expires_at", "") or "").strip()
        if self._gateway_client is None:
            self._gateway_client = GatewayClient(
                GatewayClientConfig(
                    base_url=url,
                    auth_token=token,
                    auth_mode=auth_mode,
                    user_id=user_id,
                    session_id=session_id,
                    csrf_token=csrf_token,
                    session_expires_at=session_expires_at,
                )
            )
        return self._gateway_client

    def gateway_capabilities(self, *, force: bool = False, stale_ok: bool = False):
        """Return cached assistant-facing Gateway capabilities."""
        gw = self.gateway_client()
        if gw is None:
            return None
        return get_cached_assistant_capabilities(gw, force=bool(force), stale_ok=bool(stale_ok))

    def _prefetch_gateway_capabilities(self) -> None:
        """Warm Gateway discovery off the UI/speech critical path."""

        def _worker() -> None:
            try:
                self.gateway_capabilities(force=True)
            except Exception:
                pass

        try:
            threading.Thread(target=_worker, name="gateway-capabilities-prefetch", daemon=True).start()
        except Exception:
            pass

    @property
    def active_session_id(self) -> str:
        return self._session_index.active_session_id

    def get_last_run_id(self) -> Optional[str]:
        """Return the last run id for the active session."""
        try:
            snap = self._ensure_gateway_snapshot()
            return snap.last_run_id
        except Exception:
            return None

    def _gateway_store_for(self, session_id: str) -> SessionStore:
        data_dir = self._session_index.data_dir_for(session_id)
        return SessionStore(Path(data_dir) / "session.json")

    def _load_gateway_snapshot(self, session_id: str) -> SessionSnapshot:
        store = self._gateway_store_for(session_id)
        snap = store.load()
        if snap is None:
            snap = SessionSnapshot(
                session_id=str(session_id),
                actor_id="gateway",
                messages=[],
                last_run_id=None,
            )
            store.save(snap)
        self._gateway_store = store
        return snap

    def _save_gateway_snapshot(self, snapshot: SessionSnapshot) -> None:
        # Resolve the store from the snapshot's own session id: a cached store
        # could belong to another session after a switch, silently writing one
        # session's transcript into another session's file.
        store = self._gateway_store_for(snapshot.session_id)
        self._gateway_store = store
        store.save(snapshot)

    def _fresh_message_id(self) -> str:
        return uuid.uuid4().hex

    def _message_id_from_dict(
        self,
        message: Dict[str, Any],
        *,
        fallback_index: int = 0,
        session_id: str = "",
    ) -> str:
        if not isinstance(message, dict):
            return self._fresh_message_id()
        direct = str(message.get("message_id") or "").strip()
        if direct:
            return direct
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        meta_id = str((metadata or {}).get("message_id") or "").strip()
        if meta_id:
            return meta_id
        payload = {
            "session_id": str(session_id or "").strip(),
            "role": str(message.get("role") or ""),
            "ts": str(message.get("ts") or message.get("timestamp") or ""),
            "content": str(message.get("content") or ""),
            "index": max(0, int(fallback_index)),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha1(encoded).hexdigest()[:24]

    def _normalize_message_dict(
        self,
        message: Dict[str, Any],
        *,
        fallback_index: int = 0,
        session_id: str = "",
    ) -> Dict[str, Any]:
        normalized = dict(message or {})
        normalized["message_id"] = self._message_id_from_dict(
            normalized,
            fallback_index=fallback_index,
            session_id=session_id,
        )
        return normalized

    def replace_gateway_messages(self, messages: List[Dict[str, Any]], *, last_run_id: Optional[str] = None) -> bool:
        """Replace gateway session messages with a provided history snapshot."""
        try:
            with self._snapshot_lock:
                snap = self._ensure_gateway_snapshot()
                run_id = snap.last_run_id if last_run_id is None else str(last_run_id or "").strip() or None
                existing: List[Dict[str, Any]] = [dict(m) for m in (snap.messages or []) if isinstance(m, dict)]
                cleaned: List[Dict[str, Any]] = []
                for index, m in enumerate(messages):
                    if isinstance(m, dict):
                        cleaned.append(
                            self._normalize_message_dict(
                                m,
                                fallback_index=index,
                                session_id=snap.session_id,
                            )
                        )
                history_changed = cleaned != existing
                self._gateway_snapshot = SessionSnapshot(
                    session_id=snap.session_id,
                    actor_id=snap.actor_id,
                    messages=cleaned,
                    last_run_id=run_id,
                    workspace_root=snap.workspace_root,
                )
                self._save_gateway_snapshot(self._gateway_snapshot)
            return history_changed
        except Exception:
            return False

    def session_workspace_root(self) -> str:
        """The gateway workspace root remembered for the active session ("" if none)."""
        try:
            snap = self._ensure_gateway_snapshot()
            return str(getattr(snap, "workspace_root", "") or "").strip()
        except Exception:
            return ""

    def set_session_workspace_root(self, root: str) -> None:
        """Remember the folder the gateway ran this session in (see SessionSnapshot)."""
        value = str(root or "").strip()
        try:
            with self._snapshot_lock:
                snap = self._ensure_gateway_snapshot()
                if str(getattr(snap, "workspace_root", "") or "") == value:
                    return
                self._gateway_snapshot = SessionSnapshot(
                    session_id=snap.session_id,
                    actor_id=snap.actor_id,
                    messages=list(snap.messages),
                    last_run_id=snap.last_run_id,
                    workspace_root=value,
                )
                self._save_gateway_snapshot(self._gateway_snapshot)
        except Exception as e:
            warnings.warn(f"Error saving session workspace root: {e}")

    def remove_message(self, message_id: str) -> bool:
        """Drop one message from the active transcript (a turn that never started)."""
        target = str(message_id or "").strip()
        if not target:
            return False
        try:
            with self._snapshot_lock:
                snap = self._ensure_gateway_snapshot()
                kept = [m for m in snap.messages if str((m or {}).get("message_id") or "") != target]
                if len(kept) == len(snap.messages):
                    return False
                self._gateway_snapshot = SessionSnapshot(
                    session_id=snap.session_id,
                    actor_id=snap.actor_id,
                    messages=kept,
                    last_run_id=snap.last_run_id,
                    workspace_root=snap.workspace_root,
                )
                self._save_gateway_snapshot(self._gateway_snapshot)
                return True
        except Exception as e:
            warnings.warn(f"Error removing message: {e}")
            return False

    def _ensure_gateway_snapshot(self) -> SessionSnapshot:
        with self._snapshot_lock:
            snap = self._gateway_snapshot
            if snap is None:
                snap = self._load_gateway_snapshot(self.active_session_id)
                self._gateway_snapshot = snap
            return snap

    def list_sessions(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for rec in self._session_index.records():
            title = rec.title
            if str(title).strip().lower() in {"", "new session"}:
                fallback = self._fallback_title_for_session(rec.session_id)
                if fallback:
                    title = fallback
            out.append(
                {
                    "session_id": rec.session_id,
                    "title": str(title),
                    "created_at": rec.created_at,
                    "updated_at": rec.updated_at,
                }
            )
        return out

    def create_new_session(self) -> str:
        rec = self._session_index.create_session()
        with self._snapshot_lock:
            self._gateway_snapshot = self._load_gateway_snapshot(rec.session_id)
        return rec.session_id

    def switch_session(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id must be non-empty")
        if sid == self.active_session_id:
            return
        self._session_index.set_active(sid)
        with self._snapshot_lock:
            self._gateway_snapshot = self._load_gateway_snapshot(sid)

    @staticmethod
    def _extract_first_last_questions(messages: List[Dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
        prompts: List[str] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            if str(m.get("role") or "") != "user":
                continue
            content = str(m.get("content") or "").strip()
            if not content:
                continue
            # Ignore runtime ask_user responses (not "questions").
            if content.startswith("[User response]:"):
                continue
            prompts.append(content)
        if not prompts:
            return None, None
        return prompts[0], prompts[-1]

    def _fallback_title_for_session(self, session_id: str) -> Optional[str]:
        """Local-only fallback title derived from transcript (no network)."""
        sid = str(session_id or "").strip()
        if not sid:
            return None
        try:
            data_dir = self._session_index.data_dir_for(sid)
            snap = SessionStore(Path(data_dir) / "session.json").load()
        except Exception:
            return None
        if snap is None or not isinstance(getattr(snap, "messages", None), list):
            return None
        first, last = self._extract_first_last_questions(list(snap.messages))
        if not first and not last:
            return None

        def _clean(s: Optional[str]) -> str:
            txt = str(s or "").replace("\n", " ").replace("\r", " ").strip()
            return " ".join(txt.split())

        def _trunc(txt: str, n: int) -> str:
            t = _clean(txt)
            if len(t) <= n:
                return t
            return (t[: max(0, n - 1)].rstrip() + "…").strip()

        first_txt = _clean(first)
        last_txt = _clean(last)
        if not first_txt:
            return _trunc(last_txt, 80) if last_txt else None
        return _trunc(first_txt, 80)

    def append_message(
        self,
        *,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        ts: Optional[str] = None,
    ) -> str:
        """Append a message to the current session transcript; returns its message_id."""
        try:
            with self._snapshot_lock:
                snap = self._ensure_gateway_snapshot()
                messages = list(snap.messages)
                message_id = self._fresh_message_id()
                msg: Dict[str, Any] = {
                    "role": str(role),
                    "content": str(content),
                    "ts": str(ts or "").strip() or datetime.now(timezone.utc).isoformat(),
                    "message_id": message_id,
                }
                if metadata:
                    msg["metadata"] = dict(metadata)
                messages.append(msg)
                self._gateway_snapshot = SessionSnapshot(
                    session_id=snap.session_id,
                    actor_id=snap.actor_id,
                    messages=messages,
                    last_run_id=snap.last_run_id,
                    workspace_root=snap.workspace_root,
                )
                self._save_gateway_snapshot(self._gateway_snapshot)
                return message_id
        except Exception as e:
            warnings.warn(f"Error appending message: {e}")
            raise

    def set_last_run_id(self, run_id: str) -> None:
        """Persist last run id for the active session."""
        try:
            with self._snapshot_lock:
                snap = self._ensure_gateway_snapshot()
                self._gateway_snapshot = SessionSnapshot(
                    session_id=snap.session_id,
                    actor_id=snap.actor_id,
                    messages=list(snap.messages),
                    last_run_id=str(run_id or "").strip() or None,
                    workspace_root=snap.workspace_root,
                )
                self._save_gateway_snapshot(self._gateway_snapshot)
        except Exception as e:
            warnings.warn(f"Error setting last run id: {e}")
            raise

    def session_messages(self) -> List[Dict[str, Any]]:
        """Return the durable session messages (for gateway run input)."""
        try:
            snap = self._ensure_gateway_snapshot()
            return [dict(m) for m in (snap.messages or []) if isinstance(m, dict)] if snap else []
        except Exception:
            return []
