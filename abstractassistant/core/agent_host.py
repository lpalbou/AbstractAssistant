"""Agentic backend for AbstractAssistant (Runtime + AbstractAgent).

This module is UI-agnostic. UIs (Qt/tray, CLI) should drive it via:
- `AgentHost.run_turn(...)` (generator of structured events)

Key invariants:
- Durable state lives in AbstractRuntime stores (JSON-safe vars + ledger).
- Tool callables are held only by the host (MappingToolExecutor); runtime persists only specs/requests/results.
"""

from __future__ import annotations

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
        self._tools = list(tools) if tools is not None else list(ALL_TOOLS)
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
        if not self._lazy_runtime:
            self._ensure_ready()

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

        # Start the run.
        start = getattr(self._agent, "start")  # type: ignore[union-attr]
        run_id = start(
            text,
            allowed_tools=_normalize_allowed_tools(allowed_tools),
            attachments=list(attachments) if attachments else None,
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
        if isinstance(provider, str) and provider.strip():
            runtime_ns["provider"] = provider.strip()
        if isinstance(model, str) and model.strip():
            runtime_ns["model"] = model.strip()
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
