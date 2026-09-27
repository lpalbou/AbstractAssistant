"""Gateway session manager for AbstractAssistant (legacy class name retained).

The assistant is a gateway-native thin client: AbstractGateway owns workflows,
durable execution, providers, media routing — and the sessions themselves. The
session list is the gateway's root runs folded by `session_id`
(`gateway_sessions`), a transcript is the gateway's history for the session,
and this module keeps only a rebuildable local cache of both
(`session_cache`: labels, fetched titles, the last list, cached transcripts)
plus a cached `GatewayClient`.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .gateway_sessions import (
    SESSION_LIST_LIMIT,
    SESSION_PROMPT_MAX,
    fold_session_rows,
    prompt_from_input_data,
)
from .session_cache import SessionCache, is_own_session
from .session_digest import SessionDigestCache, digest_from_record
from .session_store import SessionSnapshotUnreadable, SessionStore, SessionSnapshot
from ..gateway import GatewayClient, GatewayClientConfig, get_cached_assistant_capabilities
from ..gateway.history_seed import seed_messages_from_history_bundle
import uuid
import warnings


def _apply_attachment_refs(messages: List[Dict[str, Any]], pending: List[Tuple[str, List[Dict[str, Any]]]]) -> int:
    """Merge a session's turn attachment refs into ``messages`` IN PLACE,
    matching user rows by exact prompt text. Returns how many rows changed."""
    pending = list(pending)
    updated = 0
    for message in messages:
        if not pending:
            break
        if str(message.get("role") or "") != "user":
            continue
        content = str(message.get("content") or "").strip()
        index = next((i for i, (prompt, _) in enumerate(pending) if prompt == content), None)
        if index is None:
            continue
        _prompt, refs = pending.pop(index)
        metadata = dict(message.get("metadata") or {})
        existing = metadata.get("attachments")
        known = {str(item.get("filename") or ""): item for item in (existing or []) if isinstance(item, dict)}
        if known and all(
            str(ref.get("$artifact") or "") in {str(item.get("$artifact") or "") for item in known.values()}
            for ref in refs
        ):
            continue
        merged: List[Dict[str, Any]] = []
        for ref in refs:
            item = dict(ref)
            local = known.get(str(ref.get("filename") or ""))
            # Keep a local path that still resolves: it needs no download.
            if isinstance(local, dict) and local.get("local_path"):
                item.setdefault("local_path", local["local_path"])
            merged.append(item)
        metadata["attachments"] = merged
        metadata["media"] = merged
        message["metadata"] = metadata
        updated += 1
    return updated


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
        self._session_cache = SessionCache(self.data_dir)
        # One gateway list refresh at a time; the last failure is shown on the
        # session list until a refresh succeeds.
        self._session_refresh_lock = threading.Lock()
        self._session_list_error = ""
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
        return self._session_cache.active_session_id

    def get_last_run_id(self) -> Optional[str]:
        """Return the last run id for the active session."""
        try:
            snap = self._ensure_gateway_snapshot()
            return snap.last_run_id
        except Exception:
            return None

    def _gateway_store_for(self, session_id: str) -> SessionStore:
        data_dir = self._session_cache.data_dir_for(session_id)
        return SessionStore(Path(data_dir) / "session.json")

    def _load_gateway_snapshot(self, session_id: str) -> SessionSnapshot:
        """The cached transcript of a session (empty when none is cached yet).

        Nothing is written here: a session opened from the gateway list has no
        cache until the gateway's history arrives. An UNREADABLE cache is moved
        aside (never overwritten with an empty transcript) and recorded, so the
        gateway sync rebuilds it — or the failure is surfaced.
        """
        sid = str(session_id)
        store = self._gateway_store_for(sid)
        try:
            snap = store.read()
        except SessionSnapshotUnreadable as exc:
            aside = self._session_cache.set_aside(store.path)
            where = f"; the file was moved to {aside}" if aside is not None else ""
            # Persisted next to the cache (not only in memory) until the
            # gateway has rebuilt it, so a restart still says so.
            self._session_cache.mark_unreadable(
                sid, f"The local copy of this session could not be read ({exc}){where}."
            )
            snap = None
        if snap is None:
            snap = SessionSnapshot(session_id=sid, actor_id="gateway", messages=[], last_run_id=None)
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

    def backfill_attachments_from_gateway(self) -> int:
        """Restore attachments the local transcript lost, from the runtime.

        The runtime — not this cache — is the durable record of a session: each
        turn of its history bundle carries the artifact refs the client uploaded
        at submit time, and those outlive the user's own copy of the file. Old
        transcripts here were written before the client kept the refs, so they
        show nothing once the local file is gone.

        Merged by exact prompt text, never by position: a runtime `ask_user`
        answer is a user row locally but not a turn, so the two sequences do not
        line up. Existing metadata (a still-valid `local_path`) is preserved.
        Returns the number of messages updated. Safe to call from a worker
        thread; it never replaces messages, so tool cards survive.
        """
        with self._snapshot_lock:
            snapshot = self._gateway_snapshot
            last_run_id = str(getattr(snapshot, "last_run_id", "") or "").strip()
            session_id = str(getattr(snapshot, "session_id", "") or "").strip()
            messages = [dict(m) for m in (getattr(snapshot, "messages", None) or [])]
        if not messages or not last_run_id:
            return 0
        if last_run_id.startswith("session_memory_"):
            # The synthetic upload run runs the `__session_memory__` workflow
            # and yields no turns; there is nothing to read back.
            return 0
        try:
            client = self.gateway_client()
            bundle = client.get_run_history_bundle(
                run_id=last_run_id,
                include_subruns=False,
                include_session=True,
                session_turn_limit=1000,
                ledger_mode="tail",
                ledger_max_items=1,
                # This is an optional enrichment of a transcript that already
                # renders, so it must not hold a thread for the client's full
                # timeout when the gateway is unreachable — the app is meant to
                # work offline.
                timeout_s=8.0,
            )
        except Exception as e:
            warnings.warn(f"#FALLBACK: could not read session attachments: {e}")
            return 0

        session = bundle.get("session") if isinstance(bundle, dict) else None
        turns = session.get("turns") if isinstance(session, dict) else None
        if not isinstance(turns, list):
            return 0
        pending: List[Tuple[str, List[Dict[str, Any]]]] = []
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            refs = [a for a in (turn.get("attachments") or []) if isinstance(a, dict)]
            prompt = str(turn.get("prompt") or "").strip()
            if refs and prompt:
                pending.append((prompt, refs))
        if not pending:
            return 0

        with self._snapshot_lock:
            snap = self._ensure_gateway_snapshot()
            if str(snap.session_id or "").strip() != session_id or str(snap.last_run_id or "").strip() != last_run_id:
                # The user switched sessions (or a turn landed) while the
                # gateway call was in flight: these refs describe a transcript
                # that is not the one on screen any more.
                return 0
            # MERGE into the transcript as it is NOW, not the copy taken before
            # the gateway call: an upload that returned meanwhile
            # (merge_message_metadata) must survive.
            current = [dict(m) for m in (snap.messages or [])]
            updated = _apply_attachment_refs(current, pending)
            if not updated:
                return 0
            self._gateway_snapshot = SessionSnapshot(
                session_id=snap.session_id,
                actor_id=snap.actor_id,
                messages=current,
                last_run_id=snap.last_run_id,
                workspace_root=snap.workspace_root,
            )
            self._save_gateway_snapshot(self._gateway_snapshot)
        return updated

    def merge_message_metadata(self, message_id: str, metadata: Dict[str, Any]) -> bool:
        """Merge keys into one message's metadata.

        Attachments are shown the moment the user sends, but their durable
        gateway artifact ids only exist once the upload returns — this writes
        them onto the message that is already on screen.
        """
        target = str(message_id or "").strip()
        if not target or not isinstance(metadata, dict) or not metadata:
            return False
        try:
            with self._snapshot_lock:
                snap = self._ensure_gateway_snapshot()
                updated = False
                messages: List[Dict[str, Any]] = []
                for message in snap.messages:
                    entry = dict(message or {})
                    if str(entry.get("message_id") or "") == target:
                        merged = dict(entry.get("metadata") or {})
                        merged.update(metadata)
                        entry["metadata"] = merged
                        updated = True
                    messages.append(entry)
                if not updated:
                    return False
                self._gateway_snapshot = SessionSnapshot(
                    session_id=snap.session_id,
                    actor_id=snap.actor_id,
                    messages=messages,
                    last_run_id=snap.last_run_id,
                    workspace_root=snap.workspace_root,
                )
                self._save_gateway_snapshot(self._gateway_snapshot)
                return True
        except Exception as e:
            warnings.warn(f"Error updating message metadata: {e}")
            return False

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

    # ------------------------------------------------------------ sessions

    def list_sessions(self) -> List[Dict[str, str]]:
        """The session list, reduced to id / title / stamps."""
        return [
            {
                "session_id": str(d.get("session_id") or ""),
                "title": str(d.get("display_title") or d.get("title") or ""),
                "created_at": str(d.get("created_at") or ""),
                "updated_at": str(d.get("updated_at") or ""),
            }
            for d in self.session_digests()
        ]

    def session_digests(self) -> List[Dict[str, Any]]:
        """The session list for the switcher, from the cache only (no network).

        Rows are the gateway's sessions as last fetched
        (`refresh_sessions_from_gateway`), minus the ones removed from this
        list; plus the active session while it has no gateway run yet ("new,
        empty"), plus 0.6.1-and-earlier local sessions the migration has not decided yet.
        Title = local label, else the gateway's opening prompt, else the cached
        transcript's; metrics come from the cached transcript when there is one.
        Safe to call from any thread.
        """
        cache = getattr(self, "_session_digest_cache", None)
        if cache is None:
            cache = SessionDigestCache()
            self._session_digest_cache = cache
        store = self._session_cache
        active = self.active_session_id
        out: List[Dict[str, Any]] = []
        seen: set = set()

        def _add(session_id: str, *, created_at: str, updated_at: str, row=None) -> None:
            if session_id in seen or store.is_hidden(session_id):
                return
            seen.add(session_id)
            record = {
                "session_id": session_id,
                "title": store.label(session_id) or "New session",
                "created_at": created_at,
                "updated_at": updated_at,
            }
            folder = store.data_dir_for(session_id)
            try:
                digest = cache.digest(record, folder)
            except Exception:
                digest = digest_from_record(record)
            if row is not None:
                if digest.detailed and digest.messages == 0:
                    # A gateway session is never "empty": its cache just has
                    # not been filled yet.
                    digest = digest_from_record(record)
                prompt = store.prompt(session_id)
                digest = replace(
                    digest,
                    turns=int(row.turns),
                    state=str(row.state or ""),
                    first_prompt=prompt or digest.first_prompt,
                    last_run_id=row.latest_run_id or digest.last_run_id,
                    session_kind=row.session_kind,
                    automation_id=row.automation_id,
                )
            payload = asdict(digest)
            payload["display_title"] = digest.display_title
            payload["on_gateway"] = row is not None
            payload["own"] = is_own_session(session_id)
            out.append(payload)

        show_all = store.show_all
        for row in store.rows():
            # A discussion is this principal's own fork of its own automation
            # (the gateway scopes automations per principal), whatever id the
            # gateway minted for its session.
            if show_all or is_own_session(row.session_id) or row.session_kind == "discussion":
                _add(row.session_id, created_at=row.created_at, updated_at=row.updated_at, row=row)
        for session_id, meta in store.legacy_pending().items():
            _add(session_id, created_at=meta.get("created_at", ""), updated_at=meta.get("updated_at", ""))
        if active not in seen:
            _add(active, created_at="", updated_at=store.last_seen(active))
        return out

    def session_list_state(self) -> Dict[str, Any]:
        """What the session list header says about its source."""
        store = self._session_cache
        return {
            "error": self._session_list_error,
            "fetched_at": store.fetched_at,
            "truncated": store.truncated,
            "limit": SESSION_LIST_LIMIT,
            "refreshing": self._session_refresh_lock.locked(),
            "notice": store.peek_notice(),
        }

    def take_session_notice(self) -> str:
        """The one-time migration notice; cleared once taken."""
        return self._session_cache.take_notice()

    def refresh_sessions_from_gateway(self, *, timeout_s: float = 15.0) -> Dict[str, Any]:
        """Fetch the session list from the gateway into the cache.

        Blocking network: call it off the GUI thread. One request for the list
        (the pinned `/runs` query), then up to `SESSION_PROMPT_MAX` opening
        prompts not fetched before. The first COMPLETE list also runs the
        one-time migration of 0.6.1-and-earlier local sessions. A failure keeps the
        cached rows and is reported by `session_list_state()`.
        """
        if not self._session_refresh_lock.acquire(blocking=False):
            return {"ok": False, "skipped": True}
        try:
            try:
                client = self.gateway_client()
                caps = self.gateway_capabilities(stale_ok=True)
                # A gateway that advertises the session_kind filter lists the
                # regular kinds only; the fold drops the others either way.
                kind_filter = bool(caps is not None and not caps.error and "session_kind" in caps.runs_list_filters())
                payload = client.list_session_runs(
                    limit=SESSION_LIST_LIMIT, timeout_s=timeout_s, session_kind_filter=kind_filter
                )
            except Exception as exc:
                self._session_list_error = f"{type(exc).__name__}: {exc}"
                return {"ok": False, "error": self._session_list_error}
            rows, truncated = fold_session_rows(payload)
            self._session_list_error = ""
            active_before = self.active_session_id
            with self._snapshot_lock:
                removed = self._session_cache.reconcile_legacy(
                    (row.session_id for row in rows), complete=not truncated
                )
                self._session_cache.set_rows(rows, truncated=truncated)
            store = self._session_cache
            untitled = [
                row
                for row in rows
                if row.first_run_id
                and not store.is_hidden(row.session_id)
                and not store.label(row.session_id)
                and store.prompt(row.session_id) is None
            ]
            # The rows the list shows first (this client's own, unless every
            # gateway session is shown), newest first; the cap stays.
            show_all = store.show_all
            untitled.sort(key=lambda row: 0 if (show_all or is_own_session(row.session_id)) else 1)
            wanted = untitled[:SESSION_PROMPT_MAX]
            prompts: Dict[str, str] = {}
            for row in wanted:
                try:
                    data = client.get_run_input_data(run_id=row.first_run_id, timeout_s=5.0)
                except Exception:
                    continue  # not cached: the next refresh asks again
                prompts[row.session_id] = prompt_from_input_data(data)
            store.set_prompts(prompts)
            return {
                "ok": True,
                "rows": len(rows),
                "truncated": truncated,
                "removed": int(removed or 0),
                "active_changed": self.active_session_id != active_before,
            }
        finally:
            self._session_refresh_lock.release()

    def sync_session_from_gateway(self, *, timeout_s: float = 8.0) -> Dict[str, Any]:
        """Replace the active session's cached transcript with the gateway's.

        Reads the history bundle of the session's latest root run with its
        session turns (every turn up to that run) through the same seeding the
        reattach path uses, and REPLACES the cache with it. Skipped — never
        merged — when the user switched sessions or a turn landed while the
        call was in flight. Blocking network: call it off the GUI thread.

        Returns ``{"changed", "error"}``; ``error`` is set only when the cached
        copy was unreadable and the gateway could not rebuild it (a failure the
        user must see — an offline session otherwise just renders its cache).
        """
        with self._snapshot_lock:
            snap = self._ensure_gateway_snapshot()
        sid = str(snap.session_id or "").strip()
        problem = self._session_cache.unreadable_problem(sid)
        row = self._session_cache.row(sid)
        if row is None and problem:
            # The cache that would name the latest run is gone: ask the list.
            listed = self.refresh_sessions_from_gateway()
            if listed.get("error"):
                return {"changed": False, "error": f"{problem} The gateway could not be reached to rebuild it: {listed['error']}"}
            row = self._session_cache.row(sid)
        run_id = (row.latest_run_id if row is not None else "") or str(snap.last_run_id or "").strip()
        if not run_id or run_id.startswith("session_memory_"):
            # No gateway run yet (a new session), or the synthetic upload run.
            error = f"{problem} The gateway has no run for it to rebuild from." if problem else ""
            return {"changed": False, "error": error}
        try:
            client = self.gateway_client()
            bundle = client.get_run_history_bundle(
                run_id=run_id,
                include_subruns=True,
                include_session=True,
                session_turn_limit=max(200, int(row.turns) if row is not None else 0),
                ledger_mode="tail",
                ledger_max_items=2000,
                timeout_s=timeout_s,
            )
            messages = seed_messages_from_history_bundle(
                bundle,
                include_tool_calls_for_run_id=run_id,
                artifact_loader=lambda rid, aid: client.download_run_artifact_content(run_id=rid, artifact_id=aid),
            )
        except Exception as exc:
            error = f"{problem} The gateway could not rebuild it: {type(exc).__name__}: {exc}" if problem else ""
            return {"changed": False, "error": error}
        if not messages:
            error = f"{problem} The gateway returned no turns for it." if problem else ""
            return {"changed": False, "error": error}
        with self._snapshot_lock:
            if self._gateway_snapshot is not snap:
                return {"changed": False, "error": ""}
            changed = self.replace_gateway_messages(messages, last_run_id=run_id)
        self._session_cache.clear_unreadable(sid)
        return {"changed": bool(changed), "error": ""}

    def session_problem(self) -> str:
        """Why the active session's cached copy could not be read ("" if fine)."""
        return self._session_cache.unreadable_problem(str(self.active_session_id))

    def session_notice(self) -> str:
        """A line to show instead of an empty transcript: the active session
        was moved to ``sessions-legacy/`` (removed from the list, or dropped
        by the migration while an older list was on screen)."""
        sid = str(self.active_session_id)
        if self.session_messages() or self._session_cache.row(sid) is not None:
            return ""
        kept = self._session_cache.legacy_copy_for(sid)
        if kept is None:
            return ""
        return f"This session is no longer in the list; its text is kept in {kept}."

    def show_all_sessions(self) -> bool:
        return self._session_cache.show_all

    def set_show_all_sessions(self, value: bool) -> None:
        """Every session on the gateway (True) or this client's own (False)."""
        self._session_cache.set_show_all(bool(value))

    def session_legacy_dir(self) -> Path:
        return self._session_cache.legacy_dir

    def rename_session(self, session_id: str, title: str) -> None:
        """A LOCAL label for the session, shown instead of its opening prompt."""
        sid = str(session_id or "").strip()
        if sid:
            self._session_cache.set_label(sid, title)

    def delete_session(self, session_id: str) -> str:
        """Remove a session from this list and drop its cached transcript.

        The gateway offers no route to delete a session, so its runs stay
        there. Returns the active session id afterwards.
        """
        sid = str(session_id or "").strip()
        if not sid:
            return self.active_session_id
        cache = getattr(self, "_session_digest_cache", None)
        if cache is not None:
            cache.forget(sid)
        was_active = sid == self.active_session_id
        with self._snapshot_lock:
            new_active = self._session_cache.remove_from_list(sid)
            if was_active:
                self._gateway_snapshot = self._load_gateway_snapshot(new_active)
        return new_active

    def create_new_session(self) -> str:
        with self._snapshot_lock:
            sid = self._session_cache.create_session()
            self._gateway_snapshot = self._load_gateway_snapshot(sid)
        return sid

    def switch_session(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id must be non-empty")
        if sid == self.active_session_id:
            return
        with self._snapshot_lock:
            self._session_cache.set_active(sid)
            self._gateway_snapshot = self._load_gateway_snapshot(sid)

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
