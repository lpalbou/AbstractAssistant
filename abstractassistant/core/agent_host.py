"""Agentic backend for AbstractAssistant (Runtime + AbstractAgent).

This module is UI-agnostic. UIs (Qt/tray, CLI) should drive it via:
- `AgentHost.run_turn(...)` (generator of structured events)

Key invariants:
- Durable state lives in AbstractRuntime stores (JSON-safe vars + ledger).
- Tool callables are held only by the host (MappingToolExecutor); runtime persists only specs/requests/results.
"""

from __future__ import annotations

import datetime
import hashlib
import mimetypes
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Sequence

from abstractagent.agents.codeact import CodeActAgent
from abstractagent.agents.memact import MemActAgent
from abstractagent.agents.react import ReactAgent
from abstractagent.tools import ALL_TOOLS
from abstractruntime import (
    RunState,
    RunStatus,
    WaitReason,
    WaitState,
    FileArtifactStore,
    JsonFileRunStore,
    JsonlLedgerStore,
)
from abstractruntime.integrations.abstractcore import MappingToolExecutor, PassthroughToolExecutor, create_local_runtime

from .session_store import SessionSnapshot, SessionStore
from .tool_policy import ToolApprovalPolicy


@dataclass(frozen=True)
class AgentHostConfig:
    provider: str
    model: str
    agent_kind: str = "react"  # react|codeact|memact
    data_dir: Path = Path.home() / ".abstractassistant"

    # Workspace scoping (used by runtime effect handlers before tool execution).
    workspace_root: Optional[str] = None
    workspace_access_mode: str = "workspace_only"
    workspace_ignored_paths: Optional[List[str]] = None
    workspace_allowed_paths: Optional[List[str]] = None

    # Agent behavior
    max_iterations: int = 25
    plan_mode: bool = False
    review_mode: bool = True
    review_max_rounds: int = 3

    # Tool approvals
    tool_policy: ToolApprovalPolicy = field(default_factory=ToolApprovalPolicy)


_BUILTIN_TOOL_NAMES: set[str] = {
    # Agent schema-only tools (handled by adapters/runtime effect handlers).
    "ask_user",
    "open_attachment",
    "recall_memory",
    "inspect_vars",
    "remember",
    "remember_note",
    "compact_memory",
    "delegate_agent",
}


def _new_message(*, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"role": str(role), "content": str(content)}
    if metadata:
        msg["metadata"] = dict(metadata)
    return msg


def _tool_denied_results(tool_calls: Sequence[Dict[str, Any]], *, reason: str) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for i, tc in enumerate(tool_calls or []):
        if not isinstance(tc, dict):
            continue
        call_id = str(tc.get("call_id") or tc.get("id") or f"call_{i}")
        name = str(tc.get("name") or "")
        results.append(
            {
                "call_id": call_id,
                "runtime_call_id": tc.get("runtime_call_id"),
                "name": name,
                "success": False,
                "output": None,
                "error": reason,
            }
        )
    return {"mode": "executed", "results": results}


def _normalize_allowed_tools(allowed_tools: Optional[Sequence[str]]) -> Optional[List[str]]:
    """Normalize a per-run tool allowlist.

    Notes:
    - None means "no allowlist" (all tools allowed).
    - When an allowlist is provided, we always include AbstractAgent built-in schema tools
      so core agent functionality (ASK_USER, memory, delegation, attachments) continues to work.
    """
    if allowed_tools is None:
        return None
    allow: set[str] = {str(t).strip() for t in (allowed_tools or []) if isinstance(t, str) and str(t).strip()}
    allow |= set(_BUILTIN_TOOL_NAMES)
    return sorted(allow)


class AgentHost:
    """A durable, local agent host with explicit tool approval boundaries."""

    def __init__(
        self,
        config: AgentHostConfig,
        *,
        tools: Optional[Sequence[Callable[..., Any]]] = None,
        runtime_builder: Optional[Callable[..., Any]] = None,
        lazy_runtime: bool = True,
    ):
        self._config = config
        base_tools = list(tools) if tools is not None else list(ALL_TOOLS)

        # Optional AbstractCore skim tools (installed via `abstractcore[tools]`).
        # These keep web triage prompt-friendly vs fetching full pages.
        try:
            from abstractcore.tools.common_tools import skim_url, skim_websearch  # type: ignore
        except Exception:
            pass
        else:
            def _tool_name(fn: Callable[..., Any]) -> str:
                td = getattr(fn, "_tool_definition", None)
                name = getattr(td, "name", None) if td is not None else None
                if not name:
                    name = getattr(fn, "__name__", None)
                return str(name or "").strip()

            existing_names = {_tool_name(t) for t in base_tools if callable(t) and _tool_name(t)}
            for extra in (skim_websearch, skim_url):
                name = _tool_name(extra)
                if name and name not in existing_names:
                    base_tools.append(extra)
                    existing_names.add(name)

        self._tools = base_tools
        self._runtime_builder = runtime_builder
        self._lazy_runtime = bool(lazy_runtime)

        self._runtime_dir = Path(config.data_dir) / "runtime"
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        self._run_store = JsonFileRunStore(self._runtime_dir)
        self._ledger_store = JsonlLedgerStore(self._runtime_dir)
        self._artifact_store = FileArtifactStore(self._runtime_dir)

        self._session_store = SessionStore(Path(config.data_dir) / "session.json")
        snap = self._session_store.load()
        if snap is None:
            snap = SessionSnapshot(
                session_id=f"sess_{uuid.uuid4().hex}",
                actor_id=f"actor_{uuid.uuid4().hex}",
                messages=[],
                last_run_id=None,
            )
            self._session_store.save(snap)
        self._snapshot = snap

        self._runtime = None
        self._local_tool_executor = None
        self._agent = None
        self._stt_adapter = None
        self._stt_adapter_lock = threading.Lock()
        if not self._lazy_runtime:
            self._ensure_ready()

    def _default_stt_language(self) -> Optional[str]:
        try:
            from abstractcore.config.manager import get_config_manager  # type: ignore

            lang = getattr(getattr(get_config_manager().config, "audio", None), "stt_language", None)
            if isinstance(lang, str) and lang.strip():
                return lang.strip()
        except Exception:
            return None
        return None

    def _get_stt_adapter(self):
        with self._stt_adapter_lock:
            adapter = self._stt_adapter
            try:
                if adapter is not None and bool(getattr(adapter, "is_available", lambda: False)()):
                    return adapter
            except Exception:
                adapter = None

            try:
                from abstractvoice.adapters.stt_faster_whisper import FasterWhisperAdapter  # type: ignore

                adapter = FasterWhisperAdapter(
                    model_size="base",
                    device="auto",
                    compute_type="int8",
                    allow_downloads=True,
                )
                if bool(getattr(adapter, "is_available", lambda: False)()):
                    self._stt_adapter = adapter
                    return adapter
            except Exception:
                adapter = None

            self._stt_adapter = None
            return None

    def _transcribe_audio_file(self, *, file_path: str, language: Optional[str]) -> str:
        adapter = self._get_stt_adapter()
        if adapter is None:
            raise RuntimeError(
                "Audio transcription is unavailable. Ensure `abstractvoice` and its STT backend are installed "
                "(faster-whisper) and that the model weights can be downloaded/cached."
            )

        transcribe = getattr(adapter, "transcribe", None)
        if not callable(transcribe):
            raise RuntimeError("Audio transcription adapter does not support transcribe().")

        try:
            text = transcribe(str(file_path), language=language)
        except Exception as e:
            raise RuntimeError(f"Audio transcription failed: {e}") from e

        return str(text or "").strip()

    @staticmethod
    def _sha256_file(file_path: str, *, chunk_bytes: int = 1024 * 1024) -> str:
        """Compute SHA-256 for a file without loading it fully into memory."""
        p = str(file_path or "").strip()
        if not p:
            raise ValueError("file_path is required")
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while True:
                chunk = f.read(int(chunk_bytes))
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _ensure_audio_transcript_artifact(
        self,
        *,
        session_id: str,
        audio_sha256: str,
        audio_filename: str,
        audio_path: str,
        language: Optional[str],
    ) -> Dict[str, Any]:
        """Return transcript artifact metadata (creates it if missing)."""
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id is required")
        sha = str(audio_sha256 or "").strip().lower()
        if not sha:
            raise ValueError("audio_sha256 is required")

        rid = self._ensure_session_memory_run_exists(session_id=sid)
        try:
            existing = self._artifact_store.list_by_run(str(rid))
        except Exception:
            existing = []

        for m in existing or []:
            tags = getattr(m, "tags", None)
            if not isinstance(tags, dict):
                continue
            if str(tags.get("kind") or "") != "attachment":
                continue
            if str(tags.get("source") or "") != "ui.attachment.transcript":
                continue
            if str(tags.get("parent_sha256") or "").lower() != sha:
                continue
            aid = str(getattr(m, "artifact_id", "") or "").strip()
            if aid:
                return {
                    "artifact_id": aid,
                    "filename": str(tags.get("filename") or ""),
                    "handle": str(tags.get("path") or tags.get("source_path") or tags.get("filename") or ""),
                    "content_type": str(getattr(m, "content_type", "") or "text/plain"),
                    "size_bytes": int(getattr(m, "size_bytes", 0) or 0),
                }

        transcript = self._transcribe_audio_file(file_path=audio_path, language=language)
        if not transcript:
            raise RuntimeError(f"Audio transcription produced empty text for '{audio_filename}'.")

        stem = Path(audio_filename).stem if audio_filename else "audio"
        transcript_filename = f"{stem}.transcript.txt"
        transcript_handle = transcript_filename

        tags: Dict[str, str] = {
            "kind": "attachment",
            "source": "ui.attachment.transcript",
            "path": transcript_handle,
            "filename": transcript_filename,
            "session_id": sid,
            "parent_sha256": sha,
        }

        payload = f"Transcript of audio attachment '{audio_filename}':\n\n{transcript}\n"
        meta = self._artifact_store.store(
            payload.encode("utf-8"),
            content_type="text/plain",
            run_id=str(rid),
            tags=tags,
        )
        return {
            "artifact_id": str(getattr(meta, "artifact_id", "") or ""),
            "filename": transcript_filename,
            "handle": transcript_handle,
            "content_type": "text/plain",
            "size_bytes": len(payload.encode("utf-8")),
        }

    @staticmethod
    def _max_attachment_bytes() -> int:
        raw = str(os.getenv("ABSTRACTGATEWAY_MAX_ATTACHMENT_BYTES", "") or "").strip()
        if raw:
            try:
                v = int(raw)
                if v > 0:
                    return v
            except Exception:
                pass
        return 25 * 1024 * 1024

    def _ensure_session_memory_run_exists(self, *, session_id: str) -> str:
        from abstractruntime.integrations.abstractcore.session_attachments import session_memory_owner_run_id

        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id is required")

        rid = session_memory_owner_run_id(sid)
        try:
            existing = self._run_store.load(str(rid))
        except Exception:
            existing = None
        if existing is not None:
            return str(rid)

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        run0 = RunState(
            run_id=str(rid),
            workflow_id="__session_memory__",
            status=RunStatus.COMPLETED,
            current_node="done",
            vars={
                "context": {"task": "", "messages": []},
                "scratchpad": {},
                "_runtime": {"memory_spans": []},
                "_temp": {},
                "_limits": {},
            },
            waiting=None,
            output={"messages": []},
            error=None,
            created_at=now_iso,
            updated_at=now_iso,
            actor_id=None,
            session_id=sid,
            parent_run_id=None,
        )
        try:
            self._run_store.save(run0)
        except Exception:
            # Best-effort: artifacts can still be stored, but run-scoped APIs may 404.
            pass
        return str(rid)

    def _register_path_attachment(self, *, session_id: str, file_path: str, source: str) -> Optional[Dict[str, Any]]:
        if not file_path:
            return None
        if self._artifact_store is None:
            return None

        sid = str(session_id or "").strip()
        if not sid:
            return None

        fp_raw = str(file_path or "").strip()
        if not fp_raw:
            return None

        try:
            p = Path(fp_raw).expanduser()
        except Exception:
            return None
        try:
            resolved = p.resolve()
        except Exception:
            resolved = p

        try:
            if not resolved.exists() or not resolved.is_file():
                return None
        except Exception:
            return None

        max_bytes = self._max_attachment_bytes()
        try:
            size = int(resolved.stat().st_size)
        except Exception:
            size = -1
        if size >= 0 and size > max_bytes:
            return None

        try:
            content = resolved.read_bytes()
        except Exception:
            return None
        if len(content) > max_bytes:
            return None

        sha256 = hashlib.sha256(bytes(content)).hexdigest()
        filename = resolved.name or fp_raw.replace("\\", "/").rsplit("/", 1)[-1]

        # Keep attachment handles model-safe: relative to workspace root when inside,
        # otherwise just the filename (avoid leaking absolute local paths).
        handle = filename
        ws_root = getattr(self._config, "workspace_root", None)
        if isinstance(ws_root, str) and ws_root.strip():
            try:
                ws = Path(ws_root).expanduser().resolve()
                handle = resolved.relative_to(ws).as_posix()
            except Exception:
                handle = filename

        guessed, _enc = mimetypes.guess_type(filename)
        content_type = str(guessed or "application/octet-stream")

        rid = self._ensure_session_memory_run_exists(session_id=sid)
        try:
            existing = self._artifact_store.list_by_run(str(rid))
        except Exception:
            existing = []

        for m in existing or []:
            tags = getattr(m, "tags", None)
            if not isinstance(tags, dict):
                continue
            if str(tags.get("kind") or "") != "attachment":
                continue
            if str(tags.get("sha256") or "") != sha256:
                continue
            if str(tags.get("filename") or "") != filename:
                continue
            if str(getattr(m, "artifact_id", "") or ""):
                return {
                    "artifact_id": str(getattr(m, "artifact_id", "") or ""),
                    "handle": str(handle),
                    "filename": str(filename),
                    "sha256": sha256,
                    "content_type": content_type,
                    "size_bytes": len(content),
                }

        tags: Dict[str, str] = {
            "kind": "attachment",
            "source": str(source or "ui.attachment"),
            "path": str(handle),
            "filename": str(filename),
            "session_id": sid,
            "sha256": sha256,
        }
        try:
            meta = self._artifact_store.store(bytes(content), content_type=str(content_type), run_id=str(rid), tags=tags)
        except Exception:
            return None
        return {
            "artifact_id": str(getattr(meta, "artifact_id", "") or ""),
            "handle": str(handle),
            "filename": str(filename),
            "sha256": sha256,
            "content_type": content_type,
            "size_bytes": len(content),
        }

    def _normalize_attachments_for_run(self, attachments: Optional[Sequence[Any]]) -> Optional[List[Any]]:
        items = list(attachments) if isinstance(attachments, (list, tuple)) else []
        if not items:
            return None

        out: List[Any] = []
        for it in items:
            if isinstance(it, dict):
                # Keep artifact refs intact.
                aid = it.get("$artifact")
                if not (isinstance(aid, str) and aid.strip()):
                    aid = it.get("artifact_id")
                if isinstance(aid, str) and aid.strip():
                    out.append(dict(it))
                continue

            if isinstance(it, str) and it.strip():
                meta = self._register_path_attachment(
                    session_id=self._snapshot.session_id,
                    file_path=it.strip(),
                    source="ui.attachment",
                )
                ct = str((meta or {}).get("content_type") or "").strip().lower()
                filename = str((meta or {}).get("filename") or Path(it.strip()).name or "").strip()
                sha = str((meta or {}).get("sha256") or "").strip().lower()
                is_audio = ct.startswith("audio/") or Path(filename).suffix.lower() in {
                    ".wav",
                    ".mp3",
                    ".m4a",
                    ".aac",
                    ".ogg",
                    ".flac",
                    ".opus",
                    ".webm",
                }

                # Audio attachments: pre-transcribe via AbstractVoice so text-only models
                # work even when AbstractCore capability plugins aren't packaged in this env.
                if is_audio and filename:
                    # If the attachment is too large to store as an artifact, compute a stable SHA
                    # directly from disk so we can cache/reuse transcripts across turns.
                    if not sha:
                        try:
                            sha = self._sha256_file(it.strip())
                        except Exception as e:
                            raise RuntimeError(f"Failed to read audio attachment '{filename}': {e}") from e
                    lang = self._default_stt_language()
                    transcript_meta = self._ensure_audio_transcript_artifact(
                        session_id=self._snapshot.session_id,
                        audio_sha256=sha,
                        audio_filename=filename,
                        audio_path=it.strip(),
                        language=lang,
                    )
                    out.append(
                        {
                            "$artifact": str(transcript_meta.get("artifact_id") or ""),
                            "filename": str(transcript_meta.get("filename") or ""),
                            "source_path": str(transcript_meta.get("handle") or ""),
                            "content_type": str(transcript_meta.get("content_type") or "text/plain"),
                        }
                    )
                    continue

                # Default: attach the original file as artifact-backed media when possible.
                if meta and meta.get("artifact_id"):
                    out.append(
                        {
                            "$artifact": str(meta["artifact_id"]),
                            "filename": str(meta.get("filename") or ""),
                            "source_path": str(meta.get("handle") or ""),
                            "content_type": str(meta.get("content_type") or ""),
                            "sha256": str(meta.get("sha256") or ""),
                            "size_bytes": int(meta.get("size_bytes") or 0),
                        }
                    )
                else:
                    out.append(it.strip())
                continue

        return out or None

    @property
    def config(self) -> AgentHostConfig:
        return self._config

    @property
    def tool_policy(self) -> ToolApprovalPolicy:
        return self._config.tool_policy

    @property
    def snapshot(self) -> SessionSnapshot:
        return self._snapshot

    @property
    def tools(self) -> List[Callable[..., Any]]:
        return list(self._tools)

    def _ensure_ready(self, *, provider: Optional[str] = None, model: Optional[str] = None) -> None:
        if self._runtime is not None and self._local_tool_executor is not None and self._agent is not None:
            return

        builder = self._runtime_builder or create_local_runtime
        # Runtime uses passthrough tool executor so TOOL_CALLS always produces a durable wait.
        self._runtime = builder(
            provider=str(provider or self._config.provider),
            model=str(model or self._config.model),
            run_store=self._run_store,
            ledger_store=self._ledger_store,
            artifact_store=self._artifact_store,
            tool_executor=PassthroughToolExecutor(mode="approval_required"),
        )
        self._local_tool_executor = MappingToolExecutor.from_tools(self._tools)
        self._agent = self._create_agent()

    def clear_messages(self) -> None:
        """Clear the persisted transcript for the current session."""
        self._set_agent_session_messages([])

    def export_messages(self, path: Path) -> None:
        """Export the current transcript snapshot to a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"messages": self._agent_session_messages()}
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def import_messages(self, path: Path) -> None:
        """Import a transcript snapshot from a JSON file (best-effort)."""
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        msgs_raw = data.get("messages") if isinstance(data, dict) else None
        msgs: List[Dict[str, Any]] = []
        if isinstance(msgs_raw, list):
            for m in msgs_raw:
                if isinstance(m, dict) and isinstance(m.get("role"), str) and "content" in m:
                    msgs.append(dict(m))
        self._set_agent_session_messages(msgs)

    def _create_agent(self) -> object:
        if self._runtime is None:
            raise RuntimeError("AgentHost runtime is not initialized")
        kind = str(self._config.agent_kind or "react").strip().lower()
        actor_id = self._snapshot.actor_id
        session_id = self._snapshot.session_id
        if kind == "codeact":
            return CodeActAgent(
                runtime=self._runtime,
                tools=list(self._tools),
                max_iterations=int(self._config.max_iterations),
                actor_id=actor_id,
                session_id=session_id,
            )
        if kind == "memact":
            return MemActAgent(
                runtime=self._runtime,
                tools=list(self._tools),
                max_iterations=int(self._config.max_iterations),
                actor_id=actor_id,
                session_id=session_id,
            )
        return ReactAgent(
            runtime=self._runtime,
            tools=list(self._tools),
            max_iterations=int(self._config.max_iterations),
            plan_mode=bool(self._config.plan_mode),
            review_mode=bool(self._config.review_mode),
            review_max_rounds=int(self._config.review_max_rounds),
            actor_id=actor_id,
            session_id=session_id,
        )

    def _persist_snapshot(self) -> None:
        self._session_store.save(self._snapshot)

    def _patch_workspace_scope(self, state: RunState) -> None:
        ws_root = self._config.workspace_root
        if ws_root is None:
            return
        state.vars["workspace_root"] = str(ws_root)
        state.vars["workspace_access_mode"] = str(self._config.workspace_access_mode or "workspace_only")
        if self._config.workspace_ignored_paths:
            state.vars["workspace_ignored_paths"] = list(self._config.workspace_ignored_paths)
        if self._config.workspace_allowed_paths:
            state.vars["workspace_allowed_paths"] = list(self._config.workspace_allowed_paths)

        # Save via the configured run store (durable, JSON-safe).
        self._run_store.save(state)

    def _agent_session_messages(self) -> List[Dict[str, Any]]:
        return [dict(m) for m in (self._snapshot.messages or []) if isinstance(m, dict)]

    def _set_agent_session_messages(self, messages: List[Dict[str, Any]]) -> None:
        self._snapshot = SessionSnapshot(
            session_id=self._snapshot.session_id,
            actor_id=self._snapshot.actor_id,
            messages=[dict(m) for m in messages if isinstance(m, dict)],
            last_run_id=self._snapshot.last_run_id,
        )
        self._persist_snapshot()

    def run_turn(
        self,
        *,
        user_text: str,
        attachments: Optional[Sequence[Any]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt_extra: Optional[str] = None,
        allowed_tools: Optional[Sequence[str]] = None,
        approve_tools: Optional[Callable[[List[Dict[str, Any]]], bool]] = None,
        ask_user: Optional[Callable[[WaitState], str]] = None,
    ) -> Generator[Dict[str, Any], None, str]:
        """Run one user turn as an agentic run.

        Yields structured dict events:
        - {"type":"status", ...}
        - {"type":"tool_request", ...}
        - {"type":"tool_result", ...}
        - {"type":"assistant", ...} (final)

        Returns:
            The final assistant answer string.
        """
        text = str(user_text or "").strip()
        if not text:
            raise ValueError("user_text must be non-empty")

        init_provider = provider.strip() if isinstance(provider, str) and provider.strip() else None
        init_model = model.strip() if isinstance(model, str) and model.strip() else None
        self._ensure_ready(provider=init_provider, model=init_model)

        # Ensure the current user message is in the transcript, because the ReAct adapter
        # sends `messages` (not `task`) for multi-turn sessions.
        messages = self._agent_session_messages()
        messages.append(_new_message(role="user", content=text))
        self._set_agent_session_messages(messages)

        # Keep the agent’s session cache aligned with the persisted snapshot.
        setattr(self._agent, "session_messages", self._agent_session_messages())  # type: ignore[union-attr]

        normalized_attachments = self._normalize_attachments_for_run(attachments)

        # Start the run.
        start = getattr(self._agent, "start")  # type: ignore[union-attr]
        run_id = start(
            text,
            allowed_tools=_normalize_allowed_tools(allowed_tools),
            attachments=list(normalized_attachments) if normalized_attachments else None,
        )
        self._snapshot = SessionSnapshot(
            session_id=self._snapshot.session_id,
            actor_id=self._snapshot.actor_id,
            messages=self._snapshot.messages,
            last_run_id=str(run_id),
        )
        self._persist_snapshot()

        state = self._runtime.get_state(str(run_id))  # type: ignore[union-attr]
        self._patch_workspace_scope(state)
        # Per-turn routing override (MultiLocalAbstractCoreLLMClient honors these).
        runtime_ns = state.vars.get("_runtime")
        if not isinstance(runtime_ns, dict):
            runtime_ns = {}
            state.vars["_runtime"] = runtime_ns

        # Default audio handling: make audio attachments usable with text-only models by
        # enabling the AbstractCore STT fallback (requires an audio capability plugin, e.g. AbstractVoice).
        try:
            runtime_ns.setdefault("audio_policy", "speech_to_text")
        except Exception:
            pass

        # If the user attached audio, nudge the agent away from shell-based Whisper fallbacks.
        has_audio_attachment = False
        try:
            for a in normalized_attachments or []:
                if isinstance(a, dict):
                    ct = str(a.get("content_type") or a.get("mime_type") or "").strip().lower()
                    if ct.startswith("audio/"):
                        has_audio_attachment = True
                        break
                    candidate = a.get("source_path") or a.get("path") or a.get("filename") or a.get("handle")
                    a = candidate if candidate is not None else a
                if isinstance(a, str):
                    ext = Path(a).suffix.lower()
                    if ext in {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".webm"}:
                        has_audio_attachment = True
                        break
        except Exception:
            has_audio_attachment = False
        if isinstance(provider, str) and provider.strip():
            runtime_ns["provider"] = provider.strip()
        if isinstance(model, str) and model.strip():
            runtime_ns["model"] = model.strip()
        if has_audio_attachment:
            audio_hint = (
                "Audio attachments are supported via AbstractCore STT (audio_policy='speech_to_text'). "
                "Do not run external transcription via execute_command; use the built-in audio pipeline."
            )
            if isinstance(system_prompt_extra, str) and system_prompt_extra.strip():
                system_prompt_extra = system_prompt_extra.strip() + "\n" + audio_hint
            else:
                system_prompt_extra = audio_hint
        if isinstance(system_prompt_extra, str) and system_prompt_extra.strip():
            runtime_ns["system_prompt_extra"] = system_prompt_extra.strip()
        self._run_store.save(state)

        yield {"type": "status", "status": "thinking", "run_id": str(run_id)}

        def _default_approve(tool_calls: List[Dict[str, Any]]) -> bool:
            return not self._config.tool_policy.requires_approval(tool_calls)

        approve_cb = approve_tools or _default_approve

        # Drive the run until it completes; handle waits.
        step = getattr(self._agent, "step")  # type: ignore[union-attr]
        while True:
            state = step()
            if state.status == RunStatus.RUNNING:
                continue

            if state.status == RunStatus.WAITING and isinstance(state.waiting, WaitState):
                wait = state.waiting
                # Tool approvals (delegated TOOL_CALLS).
                details = wait.details if isinstance(wait.details, dict) else {}
                tc = details.get("tool_calls")
                tool_calls: List[Dict[str, Any]] = [dict(x) for x in tc if isinstance(x, dict)] if isinstance(tc, list) else []
                if tool_calls:
                    yield {"type": "tool_request", "run_id": str(run_id), "wait_key": wait.wait_key, "tool_calls": tool_calls, "details": dict(details)}
                    approved = False
                    try:
                        approved = bool(approve_cb(tool_calls))
                    except Exception:
                        approved = False

                    yield {"type": "status", "status": "executing_tools" if approved else "tools_denied", "run_id": str(run_id)}

                    if approved:
                        results = self._local_tool_executor.execute(tool_calls=tool_calls)  # type: ignore[union-attr]
                    else:
                        results = _tool_denied_results(tool_calls, reason="Denied by user")

                    yield {"type": "tool_result", "run_id": str(run_id), "wait_key": wait.wait_key, "result": dict(results)}
                    self._runtime.resume(  # type: ignore[union-attr]
                        workflow=getattr(self._agent, "workflow"),  # type: ignore[union-attr]
                        run_id=str(run_id),
                        wait_key=wait.wait_key,
                        payload=results,
                        max_steps=0,
                    )
                    yield {"type": "status", "status": "thinking", "run_id": str(run_id)}
                    continue

                # ASK_USER waits.
                if wait.reason == WaitReason.USER:
                    yield {"type": "ask_user", "run_id": str(run_id), "wait_key": wait.wait_key, "prompt": wait.prompt, "choices": wait.choices}
                    if ask_user is None:
                        raise RuntimeError("Run is waiting for user input but no ask_user callback was provided")
                    response_text = str(ask_user(wait))
                    self._runtime.resume(  # type: ignore[union-attr]
                        workflow=getattr(self._agent, "workflow"),  # type: ignore[union-attr]
                        run_id=str(run_id),
                        wait_key=wait.wait_key,
                        payload={"response": response_text},
                        max_steps=0,
                    )
                    yield {"type": "status", "status": "thinking", "run_id": str(run_id)}
                    continue

                # Unknown wait: surface and stop.
                yield {"type": "waiting", "run_id": str(run_id), "wait": wait}
                raise RuntimeError(f"Run is waiting (reason={wait.reason}) and cannot be auto-resumed")

            # Terminal states.
            if state.status == RunStatus.COMPLETED and isinstance(state.output, dict):
                answer = str(state.output.get("answer") or "")
                # Sync transcript snapshot from the agent cache.
                try:
                    updated_messages = getattr(self._agent, "session_messages", None)  # type: ignore[union-attr]
                    if isinstance(updated_messages, list):
                        self._set_agent_session_messages([dict(m) for m in updated_messages if isinstance(m, dict)])
                except Exception:
                    pass

                yield {"type": "assistant", "run_id": str(run_id), "content": answer, "output": dict(state.output)}
                yield {"type": "status", "status": "ready", "run_id": str(run_id)}
                return answer

            if state.status == RunStatus.FAILED:
                yield {"type": "error", "run_id": str(run_id), "error": str(state.error or "Run failed")}
                raise RuntimeError(str(state.error or "Run failed"))

            if state.status == RunStatus.CANCELLED:
                yield {"type": "error", "run_id": str(run_id), "error": "Run cancelled"}
                raise RuntimeError("Run cancelled")

            raise RuntimeError(f"Unexpected run status: {state.status}")

    def resume_run(
        self,
        *,
        run_id: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        approve_tools: Optional[Callable[[List[Dict[str, Any]]], bool]] = None,
        ask_user: Optional[Callable[[WaitState], str]] = None,
    ) -> Generator[Dict[str, Any], None, str]:
        """Resume an existing run (e.g. after app restart).

        This is primarily intended for runs that are currently WAITING on:
        - tool approvals (TOOL_CALLS)
        - user input (ASK_USER)
        """
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("run_id must be non-empty")

        init_provider = provider.strip() if isinstance(provider, str) and provider.strip() else None
        init_model = model.strip() if isinstance(model, str) and model.strip() else None
        self._ensure_ready(provider=init_provider, model=init_model)

        attach = getattr(self._agent, "attach", None)  # type: ignore[union-attr]
        if not callable(attach):
            raise RuntimeError("Agent does not support attach()")
        attach(rid)

        self._snapshot = SessionSnapshot(
            session_id=self._snapshot.session_id,
            actor_id=self._snapshot.actor_id,
            messages=self._snapshot.messages,
            last_run_id=rid,
        )
        self._persist_snapshot()

        try:
            state = self._runtime.get_state(rid)  # type: ignore[union-attr]
            self._patch_workspace_scope(state)
        except Exception:
            pass

        yield {"type": "status", "status": "thinking", "run_id": rid}

        def _default_approve(tool_calls: List[Dict[str, Any]]) -> bool:
            return not self._config.tool_policy.requires_approval(tool_calls)

        approve_cb = approve_tools or _default_approve
        step = getattr(self._agent, "step")  # type: ignore[union-attr]

        while True:
            state = step()
            if state.status == RunStatus.RUNNING:
                continue

            if state.status == RunStatus.WAITING and isinstance(state.waiting, WaitState):
                wait = state.waiting
                details = wait.details if isinstance(wait.details, dict) else {}
                tc = details.get("tool_calls")
                tool_calls: List[Dict[str, Any]] = [dict(x) for x in tc if isinstance(x, dict)] if isinstance(tc, list) else []
                if tool_calls:
                    yield {"type": "tool_request", "run_id": rid, "wait_key": wait.wait_key, "tool_calls": tool_calls, "details": dict(details)}
                    approved = False
                    try:
                        approved = bool(approve_cb(tool_calls))
                    except Exception:
                        approved = False

                    yield {"type": "status", "status": "executing_tools" if approved else "tools_denied", "run_id": rid}

                    if approved:
                        results = self._local_tool_executor.execute(tool_calls=tool_calls)  # type: ignore[union-attr]
                    else:
                        results = _tool_denied_results(tool_calls, reason="Denied by user")

                    yield {"type": "tool_result", "run_id": rid, "wait_key": wait.wait_key, "result": dict(results)}
                    self._runtime.resume(  # type: ignore[union-attr]
                        workflow=getattr(self._agent, "workflow"),  # type: ignore[union-attr]
                        run_id=rid,
                        wait_key=wait.wait_key,
                        payload=results,
                        max_steps=0,
                    )
                    yield {"type": "status", "status": "thinking", "run_id": rid}
                    continue

                if wait.reason == WaitReason.USER:
                    yield {"type": "ask_user", "run_id": rid, "wait_key": wait.wait_key, "prompt": wait.prompt, "choices": wait.choices}
                    if ask_user is None:
                        raise RuntimeError("Run is waiting for user input but no ask_user callback was provided")
                    response_text = str(ask_user(wait))
                    self._runtime.resume(  # type: ignore[union-attr]
                        workflow=getattr(self._agent, "workflow"),  # type: ignore[union-attr]
                        run_id=rid,
                        wait_key=wait.wait_key,
                        payload={"response": response_text},
                        max_steps=0,
                    )
                    yield {"type": "status", "status": "thinking", "run_id": rid}
                    continue

                yield {"type": "waiting", "run_id": rid, "wait": wait}
                raise RuntimeError(f"Run is waiting (reason={wait.reason}) and cannot be auto-resumed")

            if state.status == RunStatus.COMPLETED and isinstance(state.output, dict):
                answer = str(state.output.get("answer") or "")
                try:
                    updated_messages = getattr(self._agent, "session_messages", None)  # type: ignore[union-attr]
                    if isinstance(updated_messages, list):
                        self._set_agent_session_messages([dict(m) for m in updated_messages if isinstance(m, dict)])
                except Exception:
                    pass

                yield {"type": "assistant", "run_id": rid, "content": answer, "output": dict(state.output)}
                yield {"type": "status", "status": "ready", "run_id": rid}
                return answer

            if state.status == RunStatus.FAILED:
                yield {"type": "error", "run_id": rid, "error": str(state.error or "Run failed")}
                raise RuntimeError(str(state.error or "Run failed"))

            if state.status == RunStatus.CANCELLED:
                yield {"type": "error", "run_id": rid, "error": "Run cancelled"}
                raise RuntimeError("Run cancelled")

            raise RuntimeError(f"Unexpected run status: {state.status}")
