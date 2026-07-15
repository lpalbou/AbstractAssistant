"""
Translate gateway ledger records into AbstractAssistant UI events.

This adapter is intentionally minimal and mirrors the behavior of
`abstractcode/web` for status/messages/waits.
"""

from typing import Any, Dict, List, Optional

from .events import (
    event_name_from_wait_key,
    extract_emit_event,
    extract_flow_end_output,
    extract_tool_calls_from_wait,
    extract_wait_from_record,
    is_tool_approval_wait,
    _coerce_wait_reason,
    normalize_ui_event_name,
    parse_status_payload,
)
from .history_seed import tool_messages_from_record
from .types import StepRecord, WaitState


class GatewayEventAdapter:
    """Adapter that maps ledger records into AbstractAssistant event dicts."""

    def __init__(self) -> None:
        self._seen_wait_keys: set[str] = set()
        self._seen_tool_call_ids: set[str] = set()
        self._cycles_by_run: Dict[str, int] = {}

    def seed_seen_wait_keys(self, wait_keys) -> None:
        """Mark wait keys as already-handled so replaying a run's ledger does
        not re-emit already-resolved tool-approval / ask-user waits (used on
        reattach, where the whole ledger replays from the start)."""
        for key in wait_keys or []:
            k = str(key or "").strip()
            if k:
                self._seen_wait_keys.add(k)

    def seed_tool_call_ids(self, call_ids: List[str]) -> None:
        for cid in call_ids:
            c = str(cid or "").strip()
            if c:
                self._seen_tool_call_ids.add(c)

    def handle_record(self, rec: StepRecord | None) -> List[Dict[str, Any]]:
        """Return UI events derived from a single ledger record."""
        events: List[Dict[str, Any]] = []
        record_ts = ""
        if isinstance(rec, dict):
            record_ts = str(rec.get("ended_at") or rec.get("started_at") or "").strip()

        # Realtime run activity (2026-07-10): STARTED records carry the full effect payload
        # BEFORE execution, so the user can see what the agent is doing while the call is
        # still in flight — a reasoning cycle beginning, or a tool launching with its args.
        # Previously only tool RESULTS surfaced; the in-flight phase was a silent "thinking".
        if isinstance(rec, dict):
            raw_status = rec.get("status")
            status0 = str(getattr(raw_status, "value", raw_status) or "").strip().lower()
            effect = rec.get("effect") if isinstance(rec.get("effect"), dict) else {}
            etype = str(effect.get("type") or "").strip().lower()
            if status0 == "started" and etype == "llm_call" and str(rec.get("node_id") or "") == "reason":
                rid = str(rec.get("run_id") or "")
                n = int(self._cycles_by_run.get(rid, 0)) + 1
                self._cycles_by_run[rid] = n
                events.append({"type": "cycle", "iteration": n})
            elif status0 == "started" and etype == "tool_calls":
                payload0 = effect.get("payload") if isinstance(effect.get("payload"), dict) else {}
                tools: List[Dict[str, Any]] = []
                for tc in payload0.get("tool_calls") or []:
                    if not (isinstance(tc, dict) and str(tc.get("name") or "").strip()):
                        continue
                    args = tc.get("arguments")
                    try:
                        preview = str(args) if args else ""
                    except Exception:
                        preview = ""
                    if len(preview) > 120:
                        #[WARNING:TRUNCATION] bounded args preview for the activity line
                        preview = preview[:119] + "…"
                    tools.append({"name": str(tc.get("name")).strip(), "arguments_preview": preview})
                if tools:
                    events.append({"type": "tool_started", "tools": tools})

        emit = extract_emit_event(rec)
        if emit:
            name, payload, _scope = emit
            if name == "abstract.status":
                parsed = parse_status_payload(payload)
                text = str(parsed.get("text") or "").strip()
                if text and text.lower() not in {"ready", "completed"}:
                    events.append({"type": "status", "status": text})
            elif name == "abstract.message":
                text = ""
                if isinstance(payload, str):
                    text = payload
                elif isinstance(payload, dict):
                    text = str(payload.get("text") or payload.get("message") or "")
                text = text.strip()
                if text:
                    # For now, render messages as assistant content in the tray UI.
                    events.append({"type": "assistant", "content": text, "final": False, "ts": record_ts})
            elif name == "abstract.media.image.generated" and isinstance(payload, dict):
                artifact = payload.get("image_artifact")
                if isinstance(artifact, dict) and str(artifact.get("$artifact") or "").strip():
                    prompt = str(payload.get("prompt") or "").strip()
                    meta = {"image_artifact": dict(artifact), "generated_media": dict(payload)}
                    events.append(
                        {
                            "type": "assistant",
                            "content": "Generated image" + (f": {prompt}" if prompt else ""),
                            "meta": meta,
                            "final": False,
                            "ts": record_ts,
                        }
                    )

        wait = extract_wait_from_record(rec)
        if wait:
            events.extend(self._wait_events(wait))

        for msg in tool_messages_from_record(rec or {}):
            meta = msg.get("metadata") if isinstance(msg, dict) else None
            call_id = str(meta.get("call_id") or "").strip() if isinstance(meta, dict) else ""
            if call_id:
                if call_id in self._seen_tool_call_ids:
                    continue
                self._seen_tool_call_ids.add(call_id)
            events.append({"type": "tool", "message": msg})

        out = extract_flow_end_output(rec)
        if out:
            events.append(
                {
                    "type": "assistant",
                    "content": out.get("response", ""),
                    "meta": out.get("meta"),
                    "final": True,
                    "ts": record_ts,
                }
            )

        if rec and isinstance(rec, dict):
            status = str(rec.get("status") or "").strip().lower()
            if status == "failed":
                err = str(rec.get("error") or rec.get("result", {}).get("error") or "step failed").strip()
                events.append({"type": "error", "error": err})

        return events

    def _wait_events(self, wait: WaitState) -> List[Dict[str, Any]]:
        """Convert a wait state into UI events."""
        events: List[Dict[str, Any]] = []
        wait_key = str(wait.get("wait_key") or "").strip()
        reason = _coerce_wait_reason(wait.get("reason"))
        if wait_key and wait_key in self._seen_wait_keys:
            return []

        tool_calls = extract_tool_calls_from_wait(wait)
        approval_wait = is_tool_approval_wait(wait)
        if tool_calls or approval_wait:
            events.append({"type": "tool_request", "tool_calls": tool_calls, "wait_key": wait_key})
            if wait_key:
                self._seen_wait_keys.add(wait_key)
            return events

        if reason == "event":
            ev_name = normalize_ui_event_name(event_name_from_wait_key(wait_key))
            if ev_name == "abstract.ask":
                prompt = str(wait.get("prompt") or "Input required:").strip()
                events.append({"type": "ask_user", "prompt": prompt, "wait_key": wait_key})
                if wait_key:
                    self._seen_wait_keys.add(wait_key)
                return events

        if reason == "user":
            prompt = str(wait.get("prompt") or "Input required:").strip()
            events.append({"type": "ask_user", "prompt": prompt, "wait_key": wait_key})
            if wait_key:
                self._seen_wait_keys.add(wait_key)

        return events
