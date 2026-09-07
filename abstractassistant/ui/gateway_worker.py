"""
Gateway worker for AbstractAssistant.

Runs gateway ledger replay + streaming in a background QThread.
"""

from __future__ import annotations

import json
import os
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
from ..gateway.run_stats import aggregate_run_stats, observe_record


class GatewayWorker(QThread):
    """Worker thread that drives a gateway-first run (ledger replay + SSE)."""

    event_emitted = pyqtSignal(object)  # dict payloads
    # Fatal: the follower is finished. The palette tears the worker down.
    error_occurred = pyqtSignal(str)
    # Non-fatal: something the user should know (a wait answer that did not
    # reach the gateway) while the follower keeps running. Never tear down.
    warning_occurred = pyqtSignal(str)

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
        provider_override: Optional[str] = None,
        model_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
        media_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        thinking: str = "",
        workspace_root: str = "",
        workspace_access_mode: str = "",
        workspace_allowed_paths: Optional[List[str]] = None,
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
        # LOCAL provider/model override for the chat text route (never a gateway
        # mutation): both must be set to take effect (a half-pin is dropped).
        self._provider_override = str(provider_override or "").strip()
        self._model_override = str(model_override or "").strip()
        self._base_url_override = str(base_url_override or "").strip()
        # LOCAL media route overrides ({route_key: {provider, model}}) — ride
        # the managed workflow's media input pins per run.
        self._media_overrides = dict(media_overrides) if isinstance(media_overrides, dict) else None
        # Run scope: reasoning effort (`_runtime.thinking`) and the local
        # workspace grant; blanks are omitted from the run input.
        self._thinking = str(thinking or "").strip().lower()
        self._workspace_root = str(workspace_root or "").strip()
        self._workspace_access_mode = str(workspace_access_mode or "").strip().lower()
        self._workspace_allowed_paths = [
            str(p or "").strip() for p in (workspace_allowed_paths or []) if str(p or "").strip()
        ]
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
        self._final_observed = False
        self._stats_by_run: Dict[str, Dict[str, Any]] = {}
        self._run_activity_by_run: Dict[str, str] = {}
        self._output_artifact_candidates: List[tuple[str, str]] = []
        self._seen_output_artifacts: set[tuple[str, str]] = set()

    def provide_tool_approval(
        self,
        approved: bool,
        *,
        run_id: Optional[str] = None,
        wait_key: Optional[str] = None,
    ) -> None:
        """Answer a tool-approval wait.

        Callers should pass the ``run_id``/``wait_key`` carried by the
        ``tool_request`` event so the answer targets that exact wait. Without
        them, the last observed wait is used (#FALLBACK) — a second approval
        request arriving while a dialog is open would overwrite that slot and
        misroute the answer.
        """
        self._tool_approval_decision = bool(approved)
        self._tool_approval_event.set()
        rid = str(run_id or "").strip()
        key = str(wait_key or "").strip()
        # Require BOTH kwargs to key by identity; a lone kwarg (XOR) would
        # stitch a mixed run_id/wait_key from the pending slot and could clear
        # the wrong record — treat it as unkeyed and fall back wholesale.
        if not (rid and key):
            wait = dict(self._pending_tool_approval_wait or {})
            rid = str(wait.get("run_id") or "").strip()
            key = str(wait.get("wait_key") or "").strip()
            if rid and key:
                warnings.warn(
                    "#FALLBACK: tool approval answered without explicit run_id/wait_key; "
                    "using last observed wait"
                )
        if not rid or not key:
            return
        pending = self._pending_tool_approval_wait or {}
        if str(pending.get("run_id") or "") == rid and str(pending.get("wait_key") or "") == key:
            self._pending_tool_approval_wait = None
        payload: Dict[str, Any] = {"approved": bool(approved)}
        if not approved:
            payload["reason"] = "Denied by user"
        self.submit_wait_response(run_id=rid, wait_key=key, payload=payload)

    def provide_user_response(
        self,
        response: str,
        *,
        run_id: Optional[str] = None,
        wait_key: Optional[str] = None,
    ) -> None:
        """Answer an ask-user wait (keyed like :meth:`provide_tool_approval`)."""
        self._ask_user_response = str(response or "")
        self._ask_user_event.set()
        rid = str(run_id or "").strip()
        key = str(wait_key or "").strip()
        # Require BOTH kwargs to key by identity (see provide_tool_approval).
        if not (rid and key):
            wait = dict(self._pending_ask_user_wait or {})
            rid = str(wait.get("run_id") or "").strip()
            key = str(wait.get("wait_key") or "").strip()
            if rid and key:
                warnings.warn(
                    "#FALLBACK: ask-user answered without explicit run_id/wait_key; "
                    "using last observed wait"
                )
        if not rid or not key:
            return
        pending = self._pending_ask_user_wait or {}
        if str(pending.get("run_id") or "") == rid and str(pending.get("wait_key") or "") == key:
            self._pending_ask_user_wait = None
        self.submit_wait_response(
            run_id=rid,
            wait_key=key,
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

    def _attachment_preview_items(
        self, attachments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Uploaded refs paired with the local path they came from.

        Each item carries the gateway's `$artifact` and `run_id` (so the file
        can be fetched back forever) plus `local_path` (so the common case
        needs no fetch at all).
        """
        items: List[Dict[str, Any]] = []
        for index, attachment in enumerate(attachments or []):
            item = dict(attachment) if isinstance(attachment, dict) else {}
            if 0 <= index < len(self._attachments):
                item["local_path"] = str(self._attachments[index])
            items.append(item)
        return items

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

    def _all_ledger_wait_occurrences(self, bundle: Dict[str, Any]) -> list:
        """Every wait occurrence (wait_key, step_id) in the bundle's ledgers,
        in per-ledger record order (a wait_key repeats across occurrences —
        one waiting record = one occurrence)."""
        occurrences: list = []
        ledgers = bundle.get("ledgers") if isinstance(bundle, dict) else None
        if not isinstance(ledgers, dict):
            return occurrences
        for ledger in ledgers.values():
            items = ledger.get("items") if isinstance(ledger, dict) else None
            if not isinstance(items, list):
                continue
            for it in items:
                rec = it.get("record") if isinstance(it, dict) else None
                if not isinstance(rec, dict):
                    continue
                wait = extract_wait_from_record(rec)
                if isinstance(wait, dict):
                    key = str(wait.get("wait_key") or "").strip()
                    if key:
                        occurrences.append((key, str(rec.get("step_id") or "").strip()))
        return occurrences

    def _answered_wait_occurrences(self, bundle: Dict[str, Any]) -> list:
        """Wait occurrences that were ANSWERED, per ledger.

        A resume record carries the `wait_key` it answers, so within one
        ledger the Nth waiting record for a key is answered by the Nth resume
        for that key. Anything left over is still pending.

        This replaces asking the run for its "current" wait, which read the
        ROOT run while the approval the user must answer lives on the AGENT
        SUBRUN: the root waits on `subworkflow:<child>` and never on
        `tool_approval:<child>:act:<hash>`, so the pending child approval was
        seeded as already-handled and its dialog never re-opened. One real run
        sat parked on that for 16 minutes.
        """
        answered: list = []
        ledgers = bundle.get("ledgers") if isinstance(bundle, dict) else None
        if not isinstance(ledgers, dict):
            return answered
        for ledger in ledgers.values():
            items = ledger.get("items") if isinstance(ledger, dict) else None
            if not isinstance(items, list):
                continue
            waits: Dict[str, list] = {}
            resumes: Dict[str, int] = {}
            for it in items:
                rec = it.get("record") if isinstance(it, dict) else None
                if not isinstance(rec, dict):
                    continue
                wait = extract_wait_from_record(rec)
                if isinstance(wait, dict):
                    key = str(wait.get("wait_key") or "").strip()
                    if key:
                        waits.setdefault(key, []).append(str(rec.get("step_id") or "").strip())
                    continue
                effect = rec.get("effect") if isinstance(rec.get("effect"), dict) else {}
                if str(effect.get("type") or "") == "resume":
                    payload = effect.get("payload") if isinstance(effect.get("payload"), dict) else {}
                    key = str(payload.get("wait_key") or "").strip()
                    if key:
                        resumes[key] = resumes.get(key, 0) + 1
            for key, steps in waits.items():
                for step in steps[: resumes.get(key, 0)]:
                    answered.append((key, step))
        return answered

    def _suppress_resolved_waits_for_attach(self, run_id: str) -> None:
        """On reattach, mark the ANSWERED wait occurrences as seen so the
        full-ledger replay does not re-open dialogs the user already dealt
        with (answering a stale wait fails its resume and can leave the run
        tree in a bad state) — and leave every UNANSWERED one alone, so a
        still-pending approval is raised again.

        Occurrences are (wait_key, step_id) pairs: the runtime reuses stable
        wait keys for repeated waits from the same node, so a key alone cannot
        tell an answered wait from its pending successor.
        """
        if self._gateway is None:
            return
        try:
            bundle = self._gateway.get_run_history_bundle(
                run_id=run_id,
                include_subruns=True,
                include_session=False,
                ledger_mode="tail",
                ledger_max_items=2000,
            )
        except Exception:
            return
        occurrences = self._answered_wait_occurrences(bundle)
        if occurrences:
            self._adapter.seed_handled_wait_occurrences(occurrences)

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

        # The prompt is deliberately NOT echoed into the status line: the user
        # just typed it, and the live activity model replaces this placeholder
        # with the real current step as soon as the first event lands.
        del prompt
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
                # The follower is still alive and still useful; a failed answer
                # submission is a warning to retry, not a reason to tear down
                # the worker (which used to leave later waits unanswerable).
                self.warning_occurred.emit(
                    f"Your answer did not reach the gateway ({exc}). The run is still waiting; try again."
                )

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
                    # A final answer with content is now in the transcript
                    # (either appended above or already present as the latest
                    # assistant message): the live path is authoritative and
                    # the post-run history reseed must not run.
                    if bool(ev.get("final")) and str(content or "").strip():
                        self._final_observed = True
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
        # `connection` is the UI's signal (rendered as a reconnecting state
        # while the run stays busy); the legacy `status: offline` stays for
        # any consumer that still reads it.
        self.event_emitted.emit({"type": "connection", "state": "offline", "reason": str(reason or "")})
        self.event_emitted.emit({"type": "status", "status": "offline", "reason": str(reason or "")})

    def _mark_online(self) -> None:
        if not self._offline:
            return
        self._offline = False
        self.event_emitted.emit({"type": "connection", "state": "online"})
        self.event_emitted.emit({"type": "status", "status": "thinking"})

    def _remember_workspace_root(self, *, run_id: str, requested: str = "") -> None:
        """Read back the folder the gateway gave this run and pin it to the session.

        When the run carried no `workspace_root`, the gateway mints a fresh
        per-run folder; without remembering it, the next turn of the same
        conversation starts in another empty folder and multi-turn file work
        silently breaks. The gateway's `input_data` view is the source of
        truth for what was actually granted (it resolves and may clamp paths).
        """
        root = ""
        try:
            data = self._gateway.get_run_input_data(run_id=run_id) if self._gateway is not None else None
            inner = data.get("input_data") if isinstance(data, dict) else None
            if isinstance(inner, dict):
                root = str(inner.get("workspace_root") or "").strip()
            if not root and isinstance(data, dict):
                workspace = data.get("workspace")
                if isinstance(workspace, dict):
                    root = str(workspace.get("root") or workspace.get("workspace_root") or "").strip()
        except Exception as exc:
            warnings.warn(f"#FALLBACK: could not read the run's workspace root: {exc}")
        if not root:
            return
        wanted = str(requested or "").strip()
        same = False
        if wanted:
            try:
                same = os.path.realpath(root) == os.path.realpath(wanted)
            except Exception:
                same = root == wanted
        source = "local" if wanted and same else "gateway"
        if not wanted:
            # Only a gateway-minted folder is pinned to the chat; a folder the
            # user chose stays a preference (clearing it later must not leave
            # the chat silently glued to it).
            try:
                if self._llm_manager is not None and hasattr(self._llm_manager, "set_session_workspace_root"):
                    self._llm_manager.set_session_workspace_root(root)
            except Exception:
                pass
        self.event_emitted.emit({"type": "workspace", "root": root, "source": source, "run_id": run_id})

    def _record_run_stats(self, *, run_id: str, rec: Dict[str, Any]) -> None:
        observe_record(self._stats_by_run, run_id=run_id, rec=rec)

    def _meta_with_run_stats(self, meta: Dict[str, Any], *, run_id: str) -> Dict[str, Any]:
        merged = dict(meta or {})
        rid = str(run_id or "").strip()
        if rid:
            merged.setdefault("run_id", rid)
        # Aggregate across every run this worker followed: agent workflows
        # execute llm_call/tool_calls effects in sub-runs while the final
        # answer event fires on the root run, so the root bucket alone
        # understates (often to zero) the real token/tool activity.
        stats = aggregate_run_stats(self._stats_by_run)
        if isinstance(stats, dict):
            merged["_assistant_stats"] = {"run_id": rid, **stats}
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
                # Reattach replays the whole ledger from the start; suppress
                # already-resolved waits so answered dialogs don't re-open.
                self._suppress_resolved_waits_for_attach(run_id)
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
                preview_items = self._attachment_preview_items(attachments)
                if preview_items and not self._append_user_message:
                    # The message was already shown with local paths only. Hand
                    # the durable artifact ids back so its preview survives the
                    # local file being deleted.
                    self.event_emitted.emit(
                        {"type": "attachments_uploaded", "attachments": preview_items}
                    )
                if self._append_user_message:
                    try:
                        metadata = (
                            {"attachments": preview_items, "media": preview_items}
                            if preview_items
                            else None
                        )
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
                    provider=self._provider_override,
                    model=self._model_override,
                    base_url=self._base_url_override,
                    media_overrides=self._media_overrides,
                    thinking=self._thinking,
                    workspace_root=self._workspace_root,
                    workspace_access_mode=self._workspace_access_mode,
                    workspace_allowed_paths=self._workspace_allowed_paths,
                )

                try:
                    entry = self._resolve_entrypoint()
                    run_id = self._gateway.start_run(
                        flow_id=entry["flow_id"],
                        input_data=input_data,
                        bundle_id=entry["bundle_id"],
                        bundle_version=str(entry.get("bundle_version") or "") or None,
                        session_id=session_id,
                        registry_scope=str(entry.get("registry_scope") or "") or None,
                    )
                except Exception as exc:
                    # Nothing started: the palette restores the composer text,
                    # drops the phantom user turn and shows the gateway's
                    # reason (a refused workspace grant, a missing workflow…).
                    self.event_emitted.emit(
                        {
                            "type": "run_start_failed",
                            "error": str(exc) or exc.__class__.__name__,
                            "prompt": self._user_text,
                            "attachments": list(self._attachments),
                        }
                    )
                    return
                if self._llm_manager:
                    self._llm_manager.set_last_run_id(run_id)
                self._root_run_id = str(run_id or "")
                self._follow_run_id = ""
                self._emit_run_activity(run_id=run_id, fallback_prompt=self._user_text)
                self._remember_workspace_root(run_id=run_id, requested=self._workspace_root)

            self.event_emitted.emit({"type": "status", "status": "thinking"})
            self._offline = False

            controller.follow_run(
                root_run_id=run_id,
                on_record=lambda rid, rec: self._handle_events(run_id=rid, rec=rec),
                should_stop=self.isInterruptionRequested,
                on_offline=self._mark_offline,
                on_online=self._mark_online,
            )

            # The live-followed final answer (with its run-tree stats) is
            # authoritative. Reseeding from the history bundle here would
            # REPLACE the transcript with the gateway's bundle view — which can
            # lack the answer entirely (missing session turns force the
            # recovery path) and rebuilds every message. Reseed only as a gap
            # filler when no final answer was observed on the stream.
            if not self._final_observed:
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
