"""Agentic manager for AbstractAssistant (legacy name retained for UI compatibility).

This module used to wrap `abstractcore.BasicSession`. It now hosts an agentic backend
powered by:
- AbstractAgent (ReAct/CodeAct/MemAct patterns)
- AbstractRuntime (durable runs + waits)
- AbstractCore (providers + tool schemas/normalization)
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import warnings

from .session_index import SessionIndex
from .session_store import SessionStore, SessionSnapshot
from .gateway_selection_store import GatewaySelectionStore
from ..gateway import GatewayClient, GatewayClientConfig

if TYPE_CHECKING:
    from .agent_host import AgentHost, AgentHostConfig


@dataclass
class TokenUsage:
    """Best-effort token usage information for UI display."""

    current_session: int = 0
    max_context: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class _SessionMessage:
    """Simple message object with `.role`/`.content` attributes (UI expects this shape)."""

    def __init__(self, role: str, content: str):
        self.role = str(role or "")
        self.content = str(content or "")


class _SessionView:
    """Minimal session view exposed to the Qt UI."""

    def __init__(self, messages: List[_SessionMessage]):
        self.messages = list(messages)

    def get_token_estimate(self) -> int:
        # Heuristic: ~4 chars per token for English-ish text.
        total_chars = sum(len(m.content or "") for m in self.messages)
        return max(0, int(total_chars // 4))


class LLMManager:
    """Back-compat façade: drive an agentic backend and expose a session-like view."""

    def __init__(self, config=None, debug: bool = False, *, data_dir: Optional[Path] = None):
        if config is None:
            from ..config import Config

            config = Config.default()

        self.config = config
        self.debug = bool(debug)
        self.use_gateway = bool(getattr(getattr(config, "gateway", None), "use_gateway", False))
        self._gateway_client: Optional[GatewayClient] = None

        self.data_dir = (Path(data_dir).expanduser() if data_dir is not None else (Path.home() / ".abstractassistant"))
        self._session_index = SessionIndex(self.data_dir)
        self._title_seeds: Dict[str, str] = {}
        self._title_lock = threading.Lock()

        self.current_provider: str = str(getattr(config.llm, "default_provider", "") or "ollama")
        self.current_model: str = str(getattr(config.llm, "default_model", "") or "qwen3:4b-instruct")

        self._tts_mode: bool = False
        self._host: Optional["AgentHost"] = None
        self._gateway_snapshot: Optional[SessionSnapshot] = None
        self._gateway_store: Optional[SessionStore] = None
        if self.use_gateway:
            self._gateway_snapshot = self._load_gateway_snapshot(self.active_session_id)
        else:
            self._host = self._build_host_for_active_session()

        # UI-facing compatibility fields.
        self.token_usage = TokenUsage()
        self.current_session: Optional[_SessionView] = None
        self.llm = None if self.use_gateway else self._best_effort_llm_for_ui()
        self._refresh_session_view()

    @property
    def agent_host(self) -> Optional["AgentHost"]:
        return self._host

    def gateway_client(self) -> Optional[GatewayClient]:
        """Return a cached GatewayClient when gateway mode is enabled."""
        if not self.use_gateway:
            return None
        gw = getattr(self.config, "gateway", None)
        url = str(getattr(gw, "url", "") or "").strip()
        if not url:
            raise ValueError("Gateway URL is required in gateway mode")
        token = str(getattr(gw, "auth_token", "") or "").strip()
        if self._gateway_client is None:
            self._gateway_client = GatewayClient(GatewayClientConfig(base_url=url, auth_token=token))
        return self._gateway_client

    @property
    def active_session_id(self) -> str:
        return self._session_index.active_session_id

    def get_last_run_id(self) -> Optional[str]:
        """Return the last run id for the active session (gateway-first)."""
        try:
            if self.use_gateway:
                snap = self._ensure_gateway_snapshot()
                return snap.last_run_id
            if self._host is None:
                return None
            return getattr(self._host, "last_run_id", None)
        except Exception:
            return None

    def _gateway_store_for(self, session_id: str) -> SessionStore:
        data_dir = self._session_index.data_dir_for(session_id)
        return SessionStore(Path(data_dir) / "session.json")

    def gateway_selection_store(self, *, session_id: Optional[str] = None) -> GatewaySelectionStore:
        """Return a per-session store for gateway bundle/flow selection."""
        sid = str(session_id or self.active_session_id).strip()
        if not sid:
            raise ValueError("session_id is required")
        data_dir = self._session_index.data_dir_for(sid)
        return GatewaySelectionStore(Path(data_dir) / "gateway.json")

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
        store = self._gateway_store or self._gateway_store_for(snapshot.session_id)
        self._gateway_store = store
        store.save(snapshot)

    def replace_gateway_messages(self, messages: List[Dict[str, Any]], *, last_run_id: Optional[str] = None) -> None:
        """Replace gateway session messages with a provided history snapshot."""
        if not self.use_gateway:
            return
        try:
            snap = self._ensure_gateway_snapshot()
            run_id = snap.last_run_id if last_run_id is None else str(last_run_id or "").strip() or None
            cleaned: List[Dict[str, Any]] = []
            for m in messages:
                if isinstance(m, dict):
                    cleaned.append(dict(m))
            self._gateway_snapshot = SessionSnapshot(
                session_id=snap.session_id,
                actor_id=snap.actor_id,
                messages=cleaned,
                last_run_id=run_id,
            )
            self._save_gateway_snapshot(self._gateway_snapshot)
            self._refresh_session_view()
        except Exception:
            return

    def _ensure_gateway_snapshot(self) -> SessionSnapshot:
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
        if self.use_gateway:
            self._host = None
            self._gateway_snapshot = self._load_gateway_snapshot(rec.session_id)
        else:
            self._host = self._build_host_for_session(rec.session_id)
        self.llm = None if self.use_gateway else self._best_effort_llm_for_ui()
        self._refresh_session_view()
        return rec.session_id

    def switch_session(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id must be non-empty")
        if sid == self.active_session_id:
            return
        self._session_index.set_active(sid)
        if self.use_gateway:
            self._host = None
            self._gateway_snapshot = self._load_gateway_snapshot(sid)
        else:
            self._host = self._build_host_for_session(sid)
        self.llm = None if self.use_gateway else self._best_effort_llm_for_ui()
        self._refresh_session_view()

    def refresh(self) -> None:
        """Refresh the UI-facing session view from the durable snapshot."""
        try:
            self._session_index.touch(self.active_session_id)
        except Exception:
            pass
        self._refresh_session_view()

    def update_active_session_title_async(self, *, provider: str, model: str, on_done: Optional[Any] = None) -> None:
        """Best-effort: generate and persist a 1-line title for the active session.

        Uses the active provider/model. Runs in a background thread.
        """
        if self.use_gateway:
            warnings.warn("#FALLBACK: session title generation disabled in gateway mode")
            return
        try:
            messages = getattr(self._host.snapshot, "messages", None)
        except Exception:
            messages = None
        if not isinstance(messages, list) or not messages:
            return

        first_q, last_q = self._extract_first_last_questions(messages)
        if not first_q or not last_q:
            return

        seed = f"{first_q}\n---\n{last_q}"
        sid = self.active_session_id
        with self._title_lock:
            if self._title_seeds.get(sid) == seed:
                return
            self._title_seeds[sid] = seed

        def _run() -> None:
            title = self._generate_session_title(provider=provider, model=model, first=first_q, last=last_q)
            if not title:
                return
            try:
                self._session_index.update_title(sid, title)
            except Exception:
                return
            if callable(on_done):
                try:
                    on_done(sid, title)
                except Exception:
                    return

        threading.Thread(target=_run, daemon=True).start()

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
        if not last_txt or first_txt == last_txt:
            return _trunc(first_txt, 80)
        return f"{_trunc(first_txt, 34)} → {_trunc(last_txt, 34)}"

    @staticmethod
    def _generate_session_title(*, provider: str, model: str, first: str, last: str) -> Optional[str]:
        """Return a single-line title or None (best-effort)."""
        try:
            from abstractcore import create_llm
        except Exception:
            return None

        try:
            llm = create_llm(str(provider), model=str(model))
            prompt = (
                "Generate a single-line title for this chat session.\n"
                "- Max 60 characters.\n"
                "- No quotes.\n"
                "- Be specific.\n\n"
                f"First question: {first}\n"
                f"Most recent question: {last}\n"
            )
            resp = llm.generate(prompt, max_output_tokens=64, temperature=0.2)
            text = getattr(resp, "content", None)
            if text is None:
                text = str(resp)
            title = str(text or "").strip().splitlines()[0].strip()
            title = title.strip(" \"'“”")
            if len(title) > 80:
                title = title[:80].rstrip()
            return title or None
        except Exception:
            return None

    def _build_host_for_active_session(self) -> "AgentHost":
        return self._build_host_for_session(self.active_session_id)

    def _build_host_for_session(self, session_id: str) -> "AgentHost":
        from .agent_host import AgentHost, AgentHostConfig
        data_dir = self._session_index.data_dir_for(session_id)
        return AgentHost(
            AgentHostConfig(
                provider=self.current_provider,
                model=self.current_model,
                agent_kind="react",
                data_dir=data_dir,
            )
        )

    def _best_effort_llm_for_ui(self) -> Optional[Any]:
        """Return the underlying AbstractCore provider instance when available (best-effort)."""
        try:
            if self._host is None:
                return None
            rt = getattr(self._host, "_runtime", None)
            client = getattr(rt, "_abstractcore_llm_client", None)
            getter = getattr(client, "get_provider_instance", None)
            if callable(getter):
                return getter(provider=self.current_provider, model=self.current_model)
        except Exception:
            return None
        return None

    def _refresh_session_view(self) -> None:
        snap = self._ensure_gateway_snapshot() if self.use_gateway else (self._host.snapshot if self._host else None)
        msgs: List[_SessionMessage] = []
        if snap is not None:
            for m in snap.messages:
                if not isinstance(m, dict):
                    continue
                role = str(m.get("role") or "")
                content = str(m.get("content") or "")
                if role == "system":
                    continue
                msgs.append(_SessionMessage(role=role, content=content))
        self.current_session = _SessionView(msgs)
        if self.current_session:
            self.token_usage.current_session = self.current_session.get_token_estimate()

        if not self.use_gateway:
            # Best-effort max context from AbstractCore detection (when `llm` is present).
            max_tokens = None
            try:
                max_tokens = getattr(self.llm, "max_tokens", None)
            except Exception:
                max_tokens = None
            if isinstance(max_tokens, int) and max_tokens > 0:
                self.token_usage.max_context = max_tokens

    def append_message(self, *, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Append a message to the current session transcript."""
        try:
            if self.use_gateway:
                snap = self._ensure_gateway_snapshot()
                messages = list(snap.messages)
                msg: Dict[str, Any] = {"role": str(role), "content": str(content)}
                if metadata:
                    msg["metadata"] = dict(metadata)
                messages.append(msg)
                self._gateway_snapshot = SessionSnapshot(
                    session_id=snap.session_id,
                    actor_id=snap.actor_id,
                    messages=messages,
                    last_run_id=snap.last_run_id,
                )
                self._save_gateway_snapshot(self._gateway_snapshot)
                self._refresh_session_view()
                return
            if self._host is None:
                return
            self._host.append_message(role=role, content=content, metadata=metadata)
            self._refresh_session_view()
        except Exception:
            return

    def set_last_run_id(self, run_id: str) -> None:
        """Persist last run id for the active session."""
        try:
            if self.use_gateway:
                snap = self._ensure_gateway_snapshot()
                self._gateway_snapshot = SessionSnapshot(
                    session_id=snap.session_id,
                    actor_id=snap.actor_id,
                    messages=list(snap.messages),
                    last_run_id=str(run_id or "").strip() or None,
                )
                self._save_gateway_snapshot(self._gateway_snapshot)
                return
            if self._host is None:
                return
            self._host.set_last_run_id(run_id)
        except Exception:
            return

    def session_messages(self) -> List[Dict[str, Any]]:
        """Return the durable session messages (for gateway run input)."""
        try:
            if self.use_gateway:
                snap = self._ensure_gateway_snapshot()
            else:
                snap = self._host.snapshot if self._host else None
            return [dict(m) for m in (snap.messages or []) if isinstance(m, dict)] if snap else []
        except Exception:
            return []

    def reset_active_session(self, tts_mode: bool = False) -> None:
        self._tts_mode = bool(tts_mode)
        if self.use_gateway:
            snap = self._ensure_gateway_snapshot()
            self._gateway_snapshot = SessionSnapshot(
                session_id=snap.session_id,
                actor_id=snap.actor_id,
                messages=[],
                last_run_id=None,
            )
            self._save_gateway_snapshot(self._gateway_snapshot)
            self._refresh_session_view()
            return
        if self._host is None:
            return
        self._host.clear_messages()
        self._refresh_session_view()

    def clear_session(self):
        self.reset_active_session(tts_mode=False)

    def update_session_mode(self, tts_mode: bool = False):
        self._tts_mode = bool(tts_mode)

    def save_session(self, filepath: str) -> bool:
        try:
            if self.use_gateway:
                snap = self._ensure_gateway_snapshot()
                payload = {"messages": list(snap.messages)}
                Path(filepath).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return True
            if self._host is None:
                return False
            self._host.export_messages(Path(filepath))
            return True
        except Exception:
            return False

    def load_session(self, filepath: str) -> bool:
        try:
            if self.use_gateway:
                data = json.loads(Path(filepath).read_text(encoding="utf-8"))
                msgs_raw = data.get("messages") if isinstance(data, dict) else None
                messages: List[Dict[str, Any]] = []
                if isinstance(msgs_raw, list):
                    for m in msgs_raw:
                        if isinstance(m, dict):
                            messages.append(dict(m))
                snap = self._ensure_gateway_snapshot()
                self._gateway_snapshot = SessionSnapshot(
                    session_id=snap.session_id,
                    actor_id=snap.actor_id,
                    messages=messages,
                    last_run_id=None,
                )
                self._save_gateway_snapshot(self._gateway_snapshot)
                self._refresh_session_view()
                return True
            if self._host is None:
                return False
            self._host.import_messages(Path(filepath))
            self._refresh_session_view()
            return True
        except Exception:
            return False

    def set_provider(self, provider: str, model: Optional[str] = None):
        self.current_provider = str(provider or "").strip() or self.current_provider
        if model is not None:
            self.current_model = str(model or "").strip() or self.current_model
        self.llm = None if self.use_gateway else self._best_effort_llm_for_ui()

    def set_model(self, model: str):
        self.current_model = str(model or "").strip() or self.current_model
        self.llm = None if self.use_gateway else self._best_effort_llm_for_ui()

    def generate_response(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        media: Optional[List[str]] = None,
    ) -> str:
        """Run one agentic turn and return the final answer text.

        Note: tool approval is currently auto-managed:
        - safe/known read-only tools are auto-approved
        - dangerous/unknown tools are denied unless explicitly enabled in the UI layer
        """
        if self.use_gateway:
            raise RuntimeError("#FALLBACK: generate_response is not available in gateway mode")
        provider_eff = str(provider or "").strip() or self.current_provider
        model_eff = str(model or "").strip() or self.current_model

        system_extra = None
        if self._tts_mode:
            system_extra = (
                "You are in voice mode.\n"
                "- Keep responses concise and conversational.\n"
                "- Avoid markdown and heavy formatting.\n"
            )

        final = ""
        for ev in self._host.run_turn(
            user_text=str(message),
            attachments=list(media) if media else None,
            provider=provider_eff,
            model=model_eff,
            system_prompt_extra=system_extra,
        ):
            if isinstance(ev, dict) and ev.get("type") == "assistant":
                final = str(ev.get("content") or "")

        # Refresh session view for history/token display.
        self._refresh_session_view()
        return final

    def get_token_usage(self) -> TokenUsage:
        self._refresh_session_view()
        return self.token_usage
