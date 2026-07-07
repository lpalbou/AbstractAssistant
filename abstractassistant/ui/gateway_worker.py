"""
Gateway worker for AbstractAssistant.

Runs gateway ledger replay + streaming in a background QThread.
"""

from __future__ import annotations

import json
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

from ..gateway import (
    GatewayEventAdapter,
    build_run_input_data,
)
from ..gateway.events import extract_wait_from_record
from ..gateway.history_seed import seed_messages_from_history_bundle
from ..gateway.run_controller import GatewayRunController
from ..gateway.tool_usage import extract_tool_call_details_from_record


def _parse_iso_ms(raw: Any) -> Optional[int]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    return int(dt.timestamp() * 1000)


def _parse_usage_summary(value: Any) -> Optional[Dict[str, int]]:
    if not isinstance(value, dict):
        return None

    def _num(*keys: str) -> Optional[int]:
        for key in keys:
            try:
                raw = value.get(key)
            except Exception:
                raw = None
            if raw in {None, ""}:
                continue
            try:
                return max(0, int(raw))
            except Exception:
                continue
        return None

    input_tokens = _num("input_tokens", "prompt_tokens", "prompt", "input", "in")
    output_tokens = _num("output_tokens", "completion_tokens", "completion", "output", "out")
    total_tokens = _num("total_tokens", "total")
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
    parsed = {
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }
    if parsed["input_tokens"] == 0 and parsed["output_tokens"] == 0 and parsed["total_tokens"] == 0:
        return None
    return parsed


def _compact_tool_call_for_ui(
    call: Dict[str, Any],
    *,
    max_text_chars: int = 500,
    max_items: int = 24,
) -> Dict[str, Any]:
    def _compact(value: Any) -> Any:
        if isinstance(value, str):
            text = value
            if len(text) <= max_text_chars:
                return text
            return f"{text[: max(0, max_text_chars - 3)]}..."
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            items = list(value.items())
            for key, item in items[:max_items]:
                out[str(key)] = _compact(item)
            if len(items) > max_items:
                out["_omitted_keys"] = len(items) - max_items
            return out
        if isinstance(value, list):
            out = [_compact(item) for item in value[:max_items]]
            if len(value) > max_items:
                out.append(f"... {len(value) - max_items} more")
            return out
        return value

    compacted = {
        "name": str(call.get("name") or "").strip(),
        "arguments": _compact(call.get("arguments")),
    }
    call_id = str(call.get("call_id") or call.get("id") or "").strip()
    if call_id:
        compacted["call_id"] = call_id
    try:
        if compacted != call:
            compacted["_ui_compacted"] = True
    except Exception:
        compacted["_ui_compacted"] = True
    return compacted


class GatewayWorker(QThread):
    """Worker thread that drives a gateway-first run (ledger replay + SSE)."""

    event_emitted = pyqtSignal(object)  # dict payloads
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        *,
        llm_manager,
        user_text: str,
        attachments: Optional[List[str]] = None,
        system_prompt_extra: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        tool_policy: Optional[Dict[str, Any]] = None,
        append_user_message: bool = True,
        bundle_id: str,
        flow_id: str,
        bundle_version: str = "",
        registry_scope: str = "",
        attach_run_id: Optional[str] = None,
        primary_image_artifact: Optional[Dict[str, Any]] = None,
        debug: bool = False,
    ) -> None:
        super().__init__()
        self._llm_manager = llm_manager
        self._gateway = None
        self._adapter = GatewayEventAdapter()
        self._user_text = str(user_text or "")
        self._attachments = list(attachments or [])
        self._system_prompt_extra = str(system_prompt_extra) if system_prompt_extra else ""
        self._allowed_tools = list(allowed_tools) if allowed_tools is not None else None
        self._tool_policy = dict(tool_policy) if isinstance(tool_policy, dict) else None
        self._append_user_message = bool(append_user_message)
        self._bundle_id = str(bundle_id or "").strip()
        self._flow_id = str(flow_id or "").strip()
        self._bundle_version = str(bundle_version or "").strip()
        self._registry_scope = str(registry_scope or "").strip()
        self._debug = bool(debug)
        self._attach_run_id = str(attach_run_id or "").strip()
        self._primary_image_artifact = (
            dict(primary_image_artifact)
            if isinstance(primary_image_artifact, dict) and str(primary_image_artifact.get("$artifact") or "").strip()
            else None
        )

        self._tool_approval_event = threading.Event()
        self._tool_approval_decision: Optional[bool] = None
        self._ask_user_event = threading.Event()
        self._ask_user_response: Optional[str] = None
        self._pending_tool_approval_wait: Optional[Dict[str, str]] = None
        self._pending_ask_user_wait: Optional[Dict[str, str]] = None
        self._offline = False
        self._root_run_id = ""
        self._follow_run_id = ""
        self._stats_by_run: Dict[str, Dict[str, Any]] = {}
        self._run_activity_by_run: Dict[str, str] = {}
        self._output_artifact_candidates: List[tuple[str, str]] = []
        self._seen_output_artifacts: set[tuple[str, str]] = set()

    def provide_tool_approval(self, approved: bool) -> None:
        self._tool_approval_decision = bool(approved)
        self._tool_approval_event.set()
        wait = dict(self._pending_tool_approval_wait or {})
        wait_key = str(wait.get("wait_key") or "").strip()
        run_id = str(wait.get("run_id") or "").strip()
        if not run_id or not wait_key:
            return
        self._pending_tool_approval_wait = None
        payload: Dict[str, Any] = {"approved": bool(approved)}
        if not approved:
            payload["reason"] = "Denied by user"
        self.submit_wait_response(run_id=run_id, wait_key=wait_key, payload=payload)

    def provide_user_response(self, response: str) -> None:
        self._ask_user_response = str(response or "")
        self._ask_user_event.set()
        wait = dict(self._pending_ask_user_wait or {})
        wait_key = str(wait.get("wait_key") or "").strip()
        run_id = str(wait.get("run_id") or "").strip()
        if not run_id or not wait_key:
            return
        self._pending_ask_user_wait = None
        self.submit_wait_response(
            run_id=run_id,
            wait_key=wait_key,
            payload={"response": str(response or "")},
        )

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

    def _pick_primary_image_artifact(self, attachments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            content_type = str(attachment.get("content_type") or "").strip().lower()
            modality = str(attachment.get("modality") or "").strip().lower()
            if content_type.startswith("image/") or modality == "image":
                return dict(attachment)
        if isinstance(self._primary_image_artifact, dict):
            return dict(self._primary_image_artifact)
        return None

    def _resolve_entrypoint(self) -> Dict[str, str]:
        if not self._bundle_id or not self._flow_id or not self._bundle_version:
            raise RuntimeError("Published assistant workflow selection is incomplete.")
        scope = str(self._registry_scope or "").strip() or "tenant_catalog"
        if scope != "tenant_catalog":
            raise RuntimeError(f"Unsupported workflow registry_scope for AbstractAssistant: {scope}")
        return {
            "bundle_id": self._bundle_id,
            "flow_id": self._flow_id,
            "bundle_version": self._bundle_version,
            "registry_scope": scope,
        }

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
                artifact_loader=lambda rid, aid: self._gateway.download_run_artifact_content(
                    run_id=rid,
                    artifact_id=aid,
                ),
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
                had_assistant_before = self._session_has_assistant_for_run(run_id)
                changed = bool(self._llm_manager.replace_gateway_messages(messages, last_run_id=run_id))
                if not self._session_has_assistant_for_run(run_id):
                    recovered = self._latest_assistant_seed_for_run(messages, run_id=run_id)
                    if isinstance(recovered, dict) and self._should_append_assistant(
                        str(recovered.get("content") or ""),
                        meta=recovered.get("metadata") if isinstance(recovered.get("metadata"), dict) else None,
                    ):
                        self._llm_manager.append_message(
                            role="assistant",
                            content=str(recovered.get("content") or ""),
                            metadata=recovered.get("metadata") if isinstance(recovered.get("metadata"), dict) else None,
                            ts=str(recovered.get("ts") or ""),
                        )
                        changed = True
                elif not had_assistant_before:
                    changed = True
                self.event_emitted.emit({"type": "history_seeded", "changed": changed})
            else:
                warnings.warn("#REPLAY: history bundle produced no messages; local cache unchanged")
        except Exception as e:
            warnings.warn(f"#REPLAY_DEGRADED: failed to seed history bundle: {e}")
            self.event_emitted.emit(
                {
                    "type": "replay_degraded",
                    "run_id": run_id,
                    "message": f"Gateway history replay failed: {e}",
                }
            )
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
            self._handle_events(
                run_id=str(fallback2.get("run_id") or run_id),
                rec=self._make_synthetic_wait_record(fallback2["wait"]),
            )

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
            self._run_activity_by_run[str(run_id or "").strip()] = summary
            self.event_emitted.emit({"type": "run_activity", "summary": summary, "run_id": run_id})

    @staticmethod
    def _artifact_id_from_value(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        return str(value.get("$artifact") or value.get("artifact_id") or "").strip()

    def _remember_output_artifact(self, *, run_id: str, artifact_id: str) -> None:
        rid = str(run_id or "").strip()
        aid = str(artifact_id or "").strip()
        if not rid or not aid:
            return
        key = (rid, aid)
        if key in self._seen_output_artifacts:
            return
        self._seen_output_artifacts.add(key)
        self._output_artifact_candidates.append(key)

    def _record_output_artifact_candidates(self, *, run_id: str, rec: Dict[str, Any]) -> None:
        if not isinstance(rec, dict):
            return

        def _remember(value: Any, *, candidate_run_id: str) -> None:
            artifact_id = self._artifact_id_from_value(value)
            if artifact_id:
                self._remember_output_artifact(run_id=candidate_run_id, artifact_id=artifact_id)

        result = rec.get("result")
        if isinstance(result, dict):
            output = result.get("output")
            if output is not None:
                _remember(output, candidate_run_id=run_id)
                if isinstance(output, dict):
                    for key in (
                        "artifact",
                        "artifact_ref",
                        "image_artifact",
                        "video_artifact",
                        "audio_artifact",
                        "music_artifact",
                    ):
                        _remember(output.get(key), candidate_run_id=run_id)

        effect = rec.get("effect")
        payload = effect.get("payload") if isinstance(effect, dict) else None
        resume_payload = payload.get("payload") if isinstance(payload, dict) else None
        if isinstance(resume_payload, dict):
            candidate_run_id = str(resume_payload.get("sub_run_id") or run_id).strip() or run_id
            _remember(resume_payload.get("output"), candidate_run_id=candidate_run_id)

    @staticmethod
    def _text_from_output_payload(payload: Any) -> str:
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            for key in ("answer", "response", "message", "text", "content"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            messages = payload.get("messages")
            if isinstance(messages, list):
                for message in reversed(messages):
                    if not isinstance(message, dict):
                        continue
                    if str(message.get("role") or "").strip() != "assistant":
                        continue
                    text = str(message.get("content") or "").strip()
                    if text:
                        return text
        return ""

    def _resolve_output_artifact_text(self, *, run_id: str, meta: Dict[str, Any]) -> str:
        if self._gateway is None:
            return ""

        preferred_run_ids: List[str] = []
        for candidate in (
            str(meta.get("sub_run_id") or "").strip(),
            str(meta.get("artifact_run_id") or "").strip(),
            str(run_id or "").strip(),
        ):
            if candidate and candidate not in preferred_run_ids:
                preferred_run_ids.append(candidate)

        ordered: List[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        explicit_artifact_id = ""
        artifact = meta.get("artifact") if isinstance(meta.get("artifact"), dict) else None
        if isinstance(artifact, dict):
            explicit_artifact_id = self._artifact_id_from_value(artifact)
        if not explicit_artifact_id:
            explicit_artifact_id = str(meta.get("artifact_id") or meta.get("$artifact") or "").strip()
        if explicit_artifact_id:
            for preferred_run_id in preferred_run_ids:
                key = (preferred_run_id, explicit_artifact_id)
                if key not in seen:
                    ordered.append(key)
                    seen.add(key)
        for preferred_run_id in preferred_run_ids:
            for key in reversed(self._output_artifact_candidates):
                if key in seen or key[0] != preferred_run_id:
                    continue
                ordered.append(key)
                seen.add(key)
        for key in reversed(self._output_artifact_candidates):
            if key in seen:
                continue
            ordered.append(key)
            seen.add(key)

        for artifact_run_id, artifact_id in ordered:
            try:
                raw, content_type = self._gateway.download_run_artifact_content(
                    run_id=artifact_run_id,
                    artifact_id=artifact_id,
                    max_bytes=5_000_000,
                    timeout_s=60.0,
                )
            except Exception as e:
                warnings.warn(f"#FALLBACK: failed to load output artifact {artifact_id}: {e}")
                continue

            decoded = raw.decode("utf-8", errors="replace").strip()
            payload: Any = None
            if "json" in str(content_type or "").lower() or decoded.startswith(("{", "[")):
                try:
                    payload = json.loads(decoded)
                except Exception:
                    payload = None

            text = self._text_from_output_payload(payload)
            if not text and decoded and not decoded.startswith(("{", "[")):
                text = decoded
            if not text:
                continue

            meta.setdefault("artifact_run_id", artifact_run_id)
            meta.setdefault("artifact_id", artifact_id)
            meta.setdefault("artifact_content_type", str(content_type or "").strip())
            meta["kind"] = "recovered_output_artifact"
            return text
        return ""

    def _materialize_assistant_content(
        self,
        *,
        run_id: str,
        content: str,
        meta: Optional[Dict[str, Any]],
        final: bool,
    ) -> tuple[str, Dict[str, Any]]:
        text = str(content or "")
        merged_meta = dict(meta or {})
        rid = str(run_id or "").strip()
        if rid:
            merged_meta.setdefault("run_id", rid)
        if text.strip() or not final:
            return text, merged_meta

        recovered = self._resolve_output_artifact_text(run_id=rid, meta=merged_meta)
        if recovered:
            return recovered, merged_meta

        artifact = merged_meta.get("artifact") if isinstance(merged_meta.get("artifact"), dict) else None
        image_artifact = (
            merged_meta.get("image_artifact")
            if isinstance(merged_meta.get("image_artifact"), dict)
            else None
        )
        video_artifact = (
            merged_meta.get("video_artifact")
            if isinstance(merged_meta.get("video_artifact"), dict)
            else None
        )
        audio_artifact = (
            merged_meta.get("audio_artifact")
            if isinstance(merged_meta.get("audio_artifact"), dict)
            else None
        )
        content_type = ""
        for candidate in (image_artifact, video_artifact, audio_artifact, artifact):
            if not isinstance(candidate, dict):
                continue
            content_type = str(candidate.get("content_type") or "").strip().lower()
            if content_type:
                break

        if content_type.startswith("image/") or image_artifact:
            fallback = "Generated image ready."
        elif content_type.startswith("video/") or video_artifact:
            fallback = "Generated video ready."
        elif content_type.startswith("audio/") or audio_artifact:
            fallback = "Generated audio ready."
        else:
            activity = str(self._run_activity_by_run.get(rid) or "").strip()
            if activity:
                merged_meta.setdefault("run_activity", activity)
            merged_meta["kind"] = "runtime_empty_response"
            merged_meta["empty_response"] = True
            return "", merged_meta

        activity = str(self._run_activity_by_run.get(rid) or "").strip()
        if activity:
            merged_meta.setdefault("run_activity", activity)
        merged_meta["kind"] = "fallback_completion"
        merged_meta["empty_response"] = True
        return fallback, merged_meta

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

    def submit_wait_response(self, *, run_id: str, wait_key: str, payload: Dict[str, Any]) -> None:
        """Submit a runtime wait response through Gateway without owning the wait.

        The ledger follower must continue observing Runtime while a local dialog
        is open. This method sends the command as a client action; Runtime then
        records the accepted/resolved state, which all viewers replay.
        """
        rid = str(run_id or "").strip()
        key = str(wait_key or "").strip()
        if not rid or not key:
            return

        def _send() -> None:
            try:
                self._submit_resume(run_id=rid, wait_key=key, payload=dict(payload or {}))
            except Exception as exc:
                self.error_occurred.emit(f"Failed to submit runtime wait response: {exc}")

        threading.Thread(target=_send, name="abstractassistant-wait-submit", daemon=True).start()

    def _handle_events(self, *, run_id: str, rec: Dict[str, Any]) -> None:
        self._update_follow_run_id_from_record(run_id=run_id, rec=rec)
        self._record_output_artifact_candidates(run_id=run_id, rec=rec)
        self._record_run_stats(run_id=run_id, rec=rec)
        events = self._adapter.handle_record(rec)
        for ev in events:
            if isinstance(ev, dict) and run_id:
                ev.setdefault("run_id", run_id)
            typ = ev.get("type") if isinstance(ev, dict) else None
            if typ == "assistant":
                if not self._is_foreground_run(run_id):
                    continue
                history_changed = False
                try:
                    meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else {}
                    content, meta = self._materialize_assistant_content(
                        run_id=run_id,
                        content=str(ev.get("content") or ""),
                        meta=meta,
                        final=bool(ev.get("final")),
                    )
                    ev["content"] = content
                    if self._should_append_assistant(content, meta=meta):
                        if bool(ev.get("final")):
                            meta = self._meta_with_run_stats(meta, run_id=run_id)
                            ev["meta"] = meta
                        self._llm_manager.append_message(
                            role="assistant",
                            content=content,
                            metadata=meta or None,
                            ts=str(ev.get("ts") or ""),
                        )
                        history_changed = True
                except Exception as e:
                    warnings.warn(f"Failed to append assistant message: {e}")
                ev["history_changed"] = history_changed
                self.event_emitted.emit(ev)
                continue

            if typ == "tool_request":
                wait_key = str(ev.get("wait_key") or "").strip()
                if wait_key:
                    self._pending_tool_approval_wait = {
                        "run_id": str(run_id or "").strip(),
                        "wait_key": wait_key,
                    }
                self.event_emitted.emit(ev)
                continue

            if typ == "ask_user":
                wait_key = str(ev.get("wait_key") or "").strip()
                if wait_key:
                    self._pending_ask_user_wait = {
                        "run_id": str(run_id or "").strip(),
                        "wait_key": wait_key,
                    }
                self.event_emitted.emit(ev)
                continue

            if typ == "tool":
                msg = ev.get("message") if isinstance(ev, dict) else None
                if isinstance(msg, dict):
                    try:
                        self._llm_manager.append_message(
                            role="tool",
                            content=str(msg.get("content") or ""),
                            metadata=msg.get("metadata") if isinstance(msg.get("metadata"), dict) else None,
                            ts=str(msg.get("ts") or ""),
                        )
                    except Exception as e:
                        warnings.warn(f"Failed to append tool message: {e}")
                self.event_emitted.emit(ev)
                continue

            self.event_emitted.emit(ev)

    def _should_append_assistant(self, content: str, *, meta: Optional[Dict[str, Any]] = None) -> bool:
        text = str(content or "").strip()
        if not text:
            return False
        candidate_meta = dict(meta or {})
        candidate_kind = str(candidate_meta.get("kind") or "").strip().lower()
        candidate_run_id = str(candidate_meta.get("run_id") or "").strip()
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
                if last_text != text:
                    return True
                last_meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
                last_kind = str((last_meta or {}).get("kind") or "").strip().lower()
                last_run_id = str((last_meta or {}).get("run_id") or "").strip()
                if candidate_kind == "fallback_completion" and last_kind == "fallback_completion":
                    return candidate_run_id != last_run_id
                return False
        except Exception:
            return True
        return True

    def _session_has_assistant_for_run(self, run_id: str) -> bool:
        rid = str(run_id or "").strip()
        if not rid or self._llm_manager is None:
            return False
        try:
            messages = self._llm_manager.session_messages()
        except Exception:
            return False
        if not isinstance(messages, list):
            return False
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            if str(msg.get("role") or "") != "assistant":
                continue
            if str(msg.get("run_id") or "").strip() == rid and str(msg.get("content") or "").strip():
                return True
            meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
            if str((meta or {}).get("run_id") or "").strip() == rid and str(msg.get("content") or "").strip():
                return True
        return False

    @staticmethod
    def _latest_assistant_seed_for_run(messages: List[Dict[str, Any]], *, run_id: str) -> Optional[Dict[str, Any]]:
        rid = str(run_id or "").strip()
        if not rid:
            return None
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            if str(msg.get("role") or "") != "assistant":
                continue
            if str(msg.get("content") or "").strip() and str(msg.get("run_id") or "").strip() == rid:
                return dict(msg)
        return None

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

    def _record_run_stats(self, *, run_id: str, rec: Dict[str, Any]) -> None:
        rid = str(run_id or "").strip()
        if not rid or not isinstance(rec, dict):
            return
        stats = self._stats_by_run.setdefault(
            rid,
            {
                "duration_ms": 0,
                "llm_calls": 0,
                "tool_calls": 0,
                "tool_call_details": [],
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "_min_ms": None,
                "_max_ms": None,
            },
        )
        started_ms = _parse_iso_ms(rec.get("started_at"))
        ended_ms = _parse_iso_ms(rec.get("ended_at"))
        at_ms = ended_ms if ended_ms is not None else started_ms
        if at_ms is not None:
            min_ms = stats.get("_min_ms")
            max_ms = stats.get("_max_ms")
            stats["_min_ms"] = at_ms if min_ms is None else min(min_ms, at_ms)
            stats["_max_ms"] = at_ms if max_ms is None else max(max_ms, at_ms)
            stats["duration_ms"] = max(0, int(stats["_max_ms"]) - int(stats["_min_ms"]))

        if str(rec.get("status") or "").strip().lower() != "completed":
            return
        effect = rec.get("effect") if isinstance(rec.get("effect"), dict) else {}
        effect_type = str(effect.get("type") or "").strip()
        result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
        if effect_type == "llm_call":
            stats["llm_calls"] = int(stats.get("llm_calls") or 0) + 1
            usage = result.get("usage") or result.get("token_usage") or result.get("tokens")
            if not isinstance(usage, dict):
                output = result.get("output")
                if isinstance(output, dict):
                    usage = output.get("usage") or output.get("token_usage") or output.get("tokens")
            parsed = _parse_usage_summary(usage)
            if parsed is not None:
                bucket = stats["usage"]
                bucket["input_tokens"] += parsed["input_tokens"]
                bucket["output_tokens"] += parsed["output_tokens"]
                bucket["total_tokens"] += parsed["total_tokens"] or (parsed["input_tokens"] + parsed["output_tokens"])
        elif effect_type == "tool_calls":
            calls = extract_tool_call_details_from_record(rec, run_id=rid)
            if calls:
                stats["tool_calls"] = int(stats.get("tool_calls") or 0) + len(calls)
                details = stats.setdefault("tool_call_details", [])
                if isinstance(details, list):
                    details.extend(_compact_tool_call_for_ui(dict(call)) for call in calls)

    def _meta_with_run_stats(self, meta: Dict[str, Any], *, run_id: str) -> Dict[str, Any]:
        merged = dict(meta or {})
        rid = str(run_id or "").strip()
        if rid:
            merged.setdefault("run_id", rid)
        stats = self._stats_by_run.get(rid)
        if isinstance(stats, dict):
            merged["_assistant_stats"] = {
                "run_id": rid,
                "duration_ms": int(stats.get("duration_ms") or 0),
                "llm_calls": int(stats.get("llm_calls") or 0),
                "tool_calls": int(stats.get("tool_calls") or 0),
                "tool_call_details": list(stats.get("tool_call_details") or []),
                "usage": dict(stats.get("usage") or {}),
            }
        return merged

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
                    controller.replay_terminal_ledger(
                        run_id=run_id,
                        after=0,
                        on_record=lambda rid, rec: self._handle_events(run_id=rid, rec=rec),
                    )
                    self._seed_history_from_gateway(run_id=run_id)
                    self.event_emitted.emit({"type": "status", "status": status})
                    return
                self._seed_history_from_gateway(run_id=run_id)
                self._emit_run_activity(run_id=run_id)
            else:
                attachments = self._upload_attachments(session_id=session_id) if self._attachments else []
                if self._append_user_message:
                    try:
                        metadata = None
                        if attachments:
                            preview_items: List[Dict[str, Any]] = []
                            for index, attachment in enumerate(attachments):
                                item = dict(attachment) if isinstance(attachment, dict) else {}
                                if 0 <= index < len(self._attachments):
                                    item["local_path"] = str(self._attachments[index])
                                preview_items.append(item)
                            metadata = {
                                "attachments": preview_items,
                                "media": preview_items,
                            }
                        self._llm_manager.append_message(
                            role="user",
                            content=self._user_text,
                            metadata=metadata,
                        )
                        self.event_emitted.emit({"type": "user_message_appended", "content": self._user_text})
                    except Exception as e:
                        warnings.warn(f"Failed to append user message: {e}")

                primary_image_artifact = self._pick_primary_image_artifact(attachments)
                input_data = build_run_input_data(
                    prompt=self._user_text,
                    system=self._system_prompt_extra,
                    attachments=attachments,
                    allowed_tools=self._allowed_tools,
                    tool_policy=self._tool_policy,
                    primary_image_artifact=primary_image_artifact,
                )

                entry = self._resolve_entrypoint()
                run_id = self._gateway.start_run(
                    flow_id=entry["flow_id"],
                    input_data=input_data,
                    bundle_id=entry["bundle_id"],
                    bundle_version=str(entry.get("bundle_version") or "") or None,
                    session_id=session_id,
                    registry_scope=str(entry.get("registry_scope") or "") or None,
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

            self._seed_history_from_gateway(run_id=run_id)
            final_status = controller.get_run_status(run_id=run_id)
            if final_status not in {"completed", "failed", "cancelled"}:
                final_status = "completed"
            self.event_emitted.emit({"type": "status", "status": final_status})
        except Exception as e:
            if self._debug:
                import traceback

                traceback.print_exc()
            self.error_occurred.emit(str(e))
