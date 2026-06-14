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
