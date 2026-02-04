"""Agentic manager for AbstractAssistant (legacy name retained for UI compatibility).

This module used to wrap `abstractcore.BasicSession`. It now hosts an agentic backend
powered by:
- AbstractAgent (ReAct/CodeAct/MemAct patterns)
- AbstractRuntime (durable runs + waits)
- AbstractCore (providers + tool schemas/normalization)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    def __init__(self, config=None, debug: bool = False):
        if config is None:
            from ..config import Config

            config = Config.default()

        self.config = config
        self.debug = bool(debug)

        self.current_provider: str = str(getattr(config.llm, "default_provider", "") or "ollama")
        self.current_model: str = str(getattr(config.llm, "default_model", "") or "qwen3:4b-instruct")

        self._tts_mode: bool = False
        self._host = AgentHost(
            AgentHostConfig(
                provider=self.current_provider,
                model=self.current_model,
                agent_kind="react",
                # Keep assistant state under a stable per-user directory.
                data_dir=Path.home() / ".abstractassistant",
            )
        )

        # UI-facing compatibility fields.
        self.token_usage = TokenUsage()
        self.current_session: Optional[_SessionView] = None
        self.llm = self._best_effort_llm_for_ui()
        self._refresh_session_view()

    @property
    def agent_host(self) -> AgentHost:
        return self._host

    def refresh(self) -> None:
        """Refresh the UI-facing session view from the durable snapshot."""
        self._refresh_session_view()

    def _best_effort_llm_for_ui(self) -> Optional[Any]:
        """Return the underlying AbstractCore provider instance when available (best-effort)."""
        try:
            rt = getattr(self._host, "_runtime", None)
            client = getattr(rt, "_abstractcore_llm_client", None)
            getter = getattr(client, "get_provider_instance", None)
            if callable(getter):
                return getter(provider=self.current_provider, model=self.current_model)
        except Exception:
            return None
        return None

    def _refresh_session_view(self) -> None:
        snap = self._host.snapshot
        msgs: List[_SessionMessage] = []
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

        # Best-effort max context from AbstractCore detection (when `llm` is present).
        max_tokens = None
        try:
            max_tokens = getattr(self.llm, "max_tokens", None)
        except Exception:
            max_tokens = None
        if isinstance(max_tokens, int) and max_tokens > 0:
            self.token_usage.max_context = max_tokens

    def create_new_session(self, tts_mode: bool = False):
        self._tts_mode = bool(tts_mode)
        self._host.clear_messages()
        self._refresh_session_view()

    def clear_session(self):
        self.create_new_session(tts_mode=False)

    def update_session_mode(self, tts_mode: bool = False):
        self._tts_mode = bool(tts_mode)

    def save_session(self, filepath: str) -> bool:
        try:
            self._host.export_messages(Path(filepath))
            return True
        except Exception:
            return False

    def load_session(self, filepath: str) -> bool:
        try:
            self._host.import_messages(Path(filepath))
            self._refresh_session_view()
            return True
        except Exception:
            return False

    def set_provider(self, provider: str, model: Optional[str] = None):
        self.current_provider = str(provider or "").strip() or self.current_provider
        if model is not None:
            self.current_model = str(model or "").strip() or self.current_model
        self.llm = self._best_effort_llm_for_ui()

    def set_model(self, model: str):
        self.current_model = str(model or "").strip() or self.current_model
        self.llm = self._best_effort_llm_for_ui()

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
