"""
Gateway worker for AbstractAssistant.

Runs gateway ledger replay + streaming in a background QThread.
"""

from __future__ import annotations

import threading
import time
import warnings
from typing import Any, Dict, List, Optional

try:
    from PyQt5.QtCore import QThread, pyqtSignal
except Exception:  # pragma: no cover - Qt binding fallback
    try:
        from PySide2.QtCore import QThread, Signal as pyqtSignal
    except Exception:
        from PyQt6.QtCore import QThread, pyqtSignal

from ..gateway import GatewayEventAdapter, build_run_input_data, select_agent_template
from ..gateway.events import extract_wait_from_record
from ..gateway.history_seed import seed_messages_from_history_bundle
from ..gateway.run_controller import GatewayRunController


class GatewayWorker(QThread):
    """Worker thread that drives a gateway-first run (ledger replay + SSE)."""

    event_emitted = pyqtSignal(object)  # dict payloads
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        *,
        llm_manager,
        user_text: str,
        provider: str,
        model: str,
        attachments: Optional[List[str]] = None,
        system_prompt_extra: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        tool_policy: Optional[Dict[str, Any]] = None,
        bundle_id: str,
        flow_id: str,
        attach_run_id: Optional[str] = None,
        debug: bool = False,
    ) -> None:
        super().__init__()
        self._llm_manager = llm_manager
        self._gateway = None
        self._adapter = GatewayEventAdapter()
        self._user_text = str(user_text or "")
        self._provider = str(provider or "")
        self._model = str(model or "")
        self._attachments = list(attachments or [])
        self._system_prompt_extra = str(system_prompt_extra) if system_prompt_extra else ""
        self._allowed_tools = list(allowed_tools) if allowed_tools is not None else None
        self._tool_policy = dict(tool_policy) if isinstance(tool_policy, dict) else None
        self._bundle_id = str(bundle_id or "").strip()
        self._flow_id = str(flow_id or "").strip()
        self._debug = bool(debug)
        self._attach_run_id = str(attach_run_id or "").strip()

        self._tool_approval_event = threading.Event()
        self._tool_approval_decision: Optional[bool] = None
        self._ask_user_event = threading.Event()
        self._ask_user_response: Optional[str] = None
        self._offline = False
        self._root_run_id = ""
        self._follow_run_id = ""

    def provide_tool_approval(self, approved: bool) -> None:
        self._tool_approval_decision = bool(approved)
        self._tool_approval_event.set()

    def provide_user_response(self, response: str) -> None:
        self._ask_user_response = str(response or "")
        self._ask_user_event.set()

    def _upload_attachments(self, *, session_id: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for path in self._attachments:
            if not path:
                continue
            res = self._gateway.attachments_upload(session_id=session_id, file_path=path)
            attachment = res.get("attachment") if isinstance(res, dict) else None
            if not isinstance(attachment, dict) or not str(attachment.get("$artifact") or "").strip():
                raise RuntimeError(f"Attachment upload failed for {path}")
            out.append(dict(attachment))
        return out

    def _resolve_entrypoint(self) -> Dict[str, str]:
        res = self._gateway.list_bundles()
        return select_agent_template(bundles_response=res, bundle_id=self._bundle_id, flow_id=self._flow_id)

    def _seed_history_from_gateway(self, *, run_id: str) -> None:
        if self._gateway is None or self._llm_manager is None:
            return
        bundle = None
        try:
            bundle = self._gateway.get_run_history_bundle(
                run_id=run_id,
                include_subruns=True,
                include_session=True,
                session_turn_limit=200,
                ledger_mode="tail",
                ledger_max_items=2000,
            )
            messages = seed_messages_from_history_bundle(
                bundle,
                include_tool_calls_for_run_id=run_id,
            )
            try:
                tool_ids = [
                    str(m.get("metadata", {}).get("call_id") or "")
                    for m in messages
                    if isinstance(m, dict) and str(m.get("role") or "") == "tool"
                ]
                self._adapter.seed_tool_call_ids([cid for cid in tool_ids if cid.strip()])
            except Exception:
                pass
            if messages:
                self._llm_manager.replace_gateway_messages(messages, last_run_id=run_id)
                self.event_emitted.emit({"type": "history_seeded"})
            else:
                warnings.warn("#FALLBACK: history bundle produced no messages; keeping local snapshot")
        except Exception as e:
            warnings.warn(f"#FALLBACK: failed to seed history bundle: {e}")
        try:
            if isinstance(bundle, dict):
                self._maybe_emit_pending_wait(run_id=run_id, bundle=bundle)
        except Exception:
            pass

    def _normalize_wait_dict(self, wait: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(wait or {})
        reason = out.get("reason")
        if hasattr(reason, "value"):
            try:
                out["reason"] = str(reason.value or "").strip()
            except Exception:
                out["reason"] = str(reason or "").strip()
        elif reason is not None:
            out["reason"] = str(reason).strip()
        return out

    def _find_latest_wait_from_ledgers(self, bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ledgers = bundle.get("ledgers") if isinstance(bundle, dict) else None
        if not isinstance(ledgers, dict):
            return None
        best: Optional[Dict[str, Any]] = None
        best_ts = ""
        for rid, ledger in ledgers.items():
            items = ledger.get("items") if isinstance(ledger, dict) else None
            if not isinstance(items, list) or not items:
                continue
            for it in reversed(items):
                rec = it.get("record") if isinstance(it, dict) else None
                if not isinstance(rec, dict):
                    continue
                wait = extract_wait_from_record(rec)
                if not isinstance(wait, dict):
                    continue
                ts = str(rec.get("ended_at") or rec.get("started_at") or "")
                if ts >= best_ts:
                    best_ts = ts
                    best = {"run_id": str(rid or "").strip(), "wait": self._normalize_wait_dict(wait)}
                break
        return best

    def _find_wait_from_run_summaries(self, *, bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self._gateway is None:
            return None
        ledgers = bundle.get("ledgers") if isinstance(bundle, dict) else None
        if not isinstance(ledgers, dict):
            return None
        for rid in ledgers.keys():
            run_id = str(rid or "").strip()
            if not run_id:
                continue
            try:
                info = self._gateway.get_run(run_id=run_id)
            except Exception:
                continue
            if not isinstance(info, dict):
                continue
            status = str(info.get("status") or "").strip().lower()
            if status != "waiting":
                continue
            waiting = info.get("waiting")
            if isinstance(waiting, dict):
                return {"run_id": run_id, "wait": self._normalize_wait_dict(waiting)}
        return None

    def _make_synthetic_wait_record(self, wait: Dict[str, Any]) -> Dict[str, Any]:
        """Build a synthetic ledger record with the wait at ``result.wait``
        (the canonical location used by ``StepRecord.finish_waiting``)."""
        return {"result": {"wait": self._normalize_wait_dict(wait)}}

    def _maybe_emit_pending_wait(self, *, run_id: str, bundle: Dict[str, Any]) -> None:
        if not isinstance(bundle, dict):
            return
        run_info = bundle.get("run") if isinstance(bundle.get("run"), dict) else None
        status = str(run_info.get("status") or "").strip().lower() if isinstance(run_info, dict) else ""
        if status != "waiting":
            return
        waiting = run_info.get("waiting") if isinstance(run_info, dict) else None
        if isinstance(waiting, dict):
            rec = self._make_synthetic_wait_record(waiting)
            self._handle_events(run_id=run_id, rec=rec)
            return
        fallback = self._find_latest_wait_from_ledgers(bundle)
        if isinstance(fallback, dict) and isinstance(fallback.get("wait"), dict):
            rec = self._make_synthetic_wait_record(fallback["wait"])
            self._handle_events(run_id=str(fallback.get("run_id") or run_id), rec=rec)
            return
        fallback2 = self._find_wait_from_run_summaries(bundle=bundle)
        if isinstance(fallback2, dict) and isinstance(fallback2.get("wait"), dict):
            self._handle_events(run_id=str(fallback2.get("run_id") or run_id), rec={"wait": fallback2["wait"]})

    def _build_run_activity_summary(self, *, run_id: str, fallback_prompt: str = "") -> str:
        if self._gateway is None:
            return ""
        status = ""
        wait_reason = ""
        try:
            info = self._gateway.get_run(run_id=run_id)
            if isinstance(info, dict):
                status = str(info.get("status") or "").strip().lower()
                waiting = info.get("waiting")
                if isinstance(waiting, dict):
                    wait_reason = str(waiting.get("reason") or "").strip().lower()
        except Exception as e:
            warnings.warn(f"#FALLBACK: failed to load run status for activity: {e}")

        prompt = ""
        try:
            data = self._gateway.get_run_input_data(run_id=run_id)
            input_data = data.get("input_data") if isinstance(data, dict) else None
            if isinstance(input_data, dict):
                prompt = str(input_data.get("prompt") or "")
                if not prompt:
                    ctx = input_data.get("context")
                    if isinstance(ctx, dict):
                        prompt = str(ctx.get("task") or "")
        except Exception as e:
            warnings.warn(f"#FALLBACK: failed to load run input for activity: {e}")

        if not prompt:
            prompt = str(fallback_prompt or "").strip()

        label = "Running"
        if status == "waiting":
            if wait_reason == "tool_approval":
                label = "Waiting for approval"
            elif wait_reason == "ask_user":
                label = "Waiting for input"
            elif wait_reason:
                label = f"Waiting ({wait_reason})"
            else:
                label = "Waiting"
        elif status:
            if status in {"running", "executing"}:
                label = "Running"
            elif status in {"completed", "failed", "cancelled"}:
                label = status.capitalize()
            else:
                label = status.upper()

        suffix = str(run_id or "").strip()
        if suffix:
            short = suffix[-6:] if len(suffix) > 6 else suffix
            label = f"{label} ({short})"

        if prompt:
            return f"{label}: {prompt}"
        return label

    def _emit_run_activity(self, *, run_id: str, fallback_prompt: str = "") -> None:
        summary = self._build_run_activity_summary(run_id=run_id, fallback_prompt=fallback_prompt)
        if summary:
            self.event_emitted.emit({"type": "run_activity", "summary": summary, "run_id": run_id})

    def _submit_resume(self, *, run_id: str, wait_key: str, payload: Dict[str, Any]) -> None:
        self._gateway.submit_command(
            command={
                "command_id": f"resume_{int(time.time() * 1000)}",
                "run_id": str(run_id),
                "type": "resume",
                "payload": {"wait_key": wait_key, "payload": payload},
                "client_id": "abstractassistant",
            }
        )

    def _handle_events(self, *, run_id: str, rec: Dict[str, Any]) -> None:
        self._update_follow_run_id_from_record(run_id=run_id, rec=rec)
        events = self._adapter.handle_record(rec)
        for ev in events:
            if isinstance(ev, dict) and run_id:
                ev.setdefault("run_id", run_id)
            typ = ev.get("type") if isinstance(ev, dict) else None
            if typ == "assistant":
                if not self._is_foreground_run(run_id):
                    continue
                try:
                    content = str(ev.get("content") or "")
                    if self._should_append_assistant(content):
                        self._llm_manager.append_message(role="assistant", content=content)
                except Exception:
                    pass
                self.event_emitted.emit(ev)
                continue

            if typ == "tool_request":
                wait_key = str(ev.get("wait_key") or "").strip()
                self.event_emitted.emit(ev)
                if not wait_key:
                    continue
                self._tool_approval_decision = None
                self._tool_approval_event.clear()
                self._tool_approval_event.wait()
                approved = bool(self._tool_approval_decision)
                payload = {"approved": approved}
                if not approved:
                    payload["reason"] = "Denied by user"
                self._submit_resume(run_id=run_id, wait_key=wait_key, payload=payload)
                continue

            if typ == "ask_user":
                wait_key = str(ev.get("wait_key") or "").strip()
                self.event_emitted.emit(ev)
                if not wait_key:
                    continue
                self._ask_user_response = None
                self._ask_user_event.clear()
                self._ask_user_event.wait()
                response = str(self._ask_user_response or "")
                self._submit_resume(run_id=run_id, wait_key=wait_key, payload={"response": response})
                continue

            if typ == "tool":
                msg = ev.get("message") if isinstance(ev, dict) else None
                if isinstance(msg, dict):
                    try:
                        self._llm_manager.append_message(
                            role="tool",
                            content=str(msg.get("content") or ""),
                            metadata=msg.get("metadata") if isinstance(msg.get("metadata"), dict) else None,
                        )
                    except Exception:
                        pass
                self.event_emitted.emit(ev)
                continue

            self.event_emitted.emit(ev)

    def _should_append_assistant(self, content: str) -> bool:
        text = str(content or "").strip()
        if not text:
            return False
        try:
            if not self._llm_manager:
                return True
            messages = self._llm_manager.session_messages()
            if not isinstance(messages, list):
                return True
            for msg in reversed(messages):
                if not isinstance(msg, dict):
                    continue
                if str(msg.get("role") or "") != "assistant":
                    continue
                last_text = str(msg.get("content") or "").strip()
                if not last_text:
                    continue
                return last_text != text
        except Exception:
            return True
        return True

    def _is_foreground_run(self, run_id: str) -> bool:
        """Return True when events should surface to the UI."""
        rid = str(run_id or "").strip()
        if not rid:
            return True
        root = str(self._root_run_id or "").strip()
        if not root or rid == root:
            return True
        follow = str(self._follow_run_id or "").strip()
        return bool(follow and rid == follow)

    def _update_follow_run_id_from_record(self, *, run_id: str, rec: Dict[str, Any]) -> None:
        """Track the foreground subworkflow run when the root waits."""
        root = str(self._root_run_id or "").strip()
        if not root or str(run_id or "").strip() != root:
            return
        wait = extract_wait_from_record(rec)
        if not isinstance(wait, dict):
            return
        reason = str(wait.get("reason") or "").strip().lower()
        if reason != "subworkflow":
            return
        details = wait.get("details")
        sub = ""
        if isinstance(details, dict):
            sub = str(details.get("sub_run_id") or details.get("subRunId") or "").strip()
        if not sub:
            wait_key = str(wait.get("wait_key") or "").strip()
            if wait_key.startswith("subworkflow:"):
                sub = str(wait_key.split(":", 1)[1] or "").strip()
        if sub:
            self._follow_run_id = sub

    def _mark_offline(self, reason: str) -> None:
        if self._offline:
            return
        self._offline = True
        self.event_emitted.emit({"type": "status", "status": "offline", "reason": str(reason or "")})

    def _mark_online(self) -> None:
        if not self._offline:
            return
        self._offline = False
        self.event_emitted.emit({"type": "status", "status": "thinking"})

    def run(self) -> None:
        try:
            if self._gateway is None:
                self._gateway = self._llm_manager.gateway_client() if self._llm_manager is not None else None
            if self._gateway is None:
                raise RuntimeError("Gateway client is not configured")

            session_id = str(self._llm_manager.active_session_id if self._llm_manager else "")
            if not session_id:
                raise RuntimeError("Session id is required for gateway runs")

            controller = GatewayRunController(gateway=self._gateway, debug=self._debug)

            run_id = self._attach_run_id
            if run_id:
                if self._llm_manager:
                    self._llm_manager.set_last_run_id(run_id)
                self._root_run_id = str(run_id or "")
                self._follow_run_id = ""
                status = controller.get_run_status(run_id=run_id)
                if status in {"completed", "failed", "cancelled"}:
                    self.event_emitted.emit({"type": "status", "status": "completed"})
                    return
                self._seed_history_from_gateway(run_id=run_id)
                self._emit_run_activity(run_id=run_id)
            else:
                try:
                    self._llm_manager.append_message(role="user", content=self._user_text)
                except Exception:
                    pass

                attachments = self._upload_attachments(session_id=session_id) if self._attachments else []
                input_data = build_run_input_data(
                    prompt=self._user_text,
                    provider=self._provider,
                    model=self._model,
                    system=self._system_prompt_extra,
                    messages=self._llm_manager.session_messages() if self._llm_manager else [],
                    attachments=attachments,
                    allowed_tools=self._allowed_tools,
                    tool_policy=self._tool_policy,
                )

                entry = self._resolve_entrypoint()
                run_id = self._gateway.start_run(
                    flow_id=entry["flow_id"],
                    input_data=input_data,
                    bundle_id=entry["bundle_id"],
                    session_id=session_id,
                )
                if self._llm_manager:
                    self._llm_manager.set_last_run_id(run_id)
                self._root_run_id = str(run_id or "")
                self._follow_run_id = ""
                self._emit_run_activity(run_id=run_id, fallback_prompt=self._user_text)

            self.event_emitted.emit({"type": "status", "status": "thinking"})
            self._offline = False

            controller.follow_run(
                root_run_id=run_id,
                on_record=lambda rid, rec: self._handle_events(run_id=rid, rec=rec),
                should_stop=self.isInterruptionRequested,
                on_offline=self._mark_offline,
                on_online=self._mark_online,
            )

            self.event_emitted.emit({"type": "status", "status": "completed"})
        except Exception as e:
            if self._debug:
                import traceback

                traceback.print_exc()
            self.error_occurred.emit(str(e))
