"""
Ledger event helpers for the gateway-first AbstractAssistant adapter.

These utilities mirror the parsing logic in `abstractcode/web`.
"""

from typing import Any, Dict, Optional, Tuple, List


from .types import StepRecord, WaitState, ToolCall


def normalize_ui_event_name(name: str) -> str:
    """Normalize UI event names to the canonical `abstract.*` namespace."""
    raw = str(name or "").strip()
    if raw.startswith("abstractcode."):
        return "abstract." + raw[len("abstractcode.") :]
    return raw


def event_name_from_wait_key(wait_key: str) -> str:
    """Extract the event name from a wait_key (evt:<name>:...)."""
    wk = str(wait_key or "").strip()
    if wk.startswith("evt:"):
        parts = wk.split(":", 3)
        if len(parts) >= 2:
            return str(parts[1] or "").strip()
    return wk


def extract_emit_event(rec: StepRecord | None) -> Optional[Tuple[str, Any, Optional[str]]]:
    """Extract an emit_event effect payload from a ledger record."""
    if not rec or not isinstance(rec, dict):
        return None
    eff = rec.get("effect")
    if not isinstance(eff, dict):
        return None
    if str(eff.get("type") or "") != "emit_event":
        return None
    payload = eff.get("payload")
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("name") or payload.get("event_name") or "").strip()
    if not name:
        return None
    scope = payload.get("scope")
    scope_s = str(scope).strip() if isinstance(scope, str) else None
    return normalize_ui_event_name(name), payload.get("payload"), scope_s


def parse_status_payload(payload: Any) -> Dict[str, Any]:
    """Parse the abstract.status payload into a {text, duration_s} dict."""
    if isinstance(payload, str):
        return {"text": payload.strip(), "duration_s": -1}
    if not isinstance(payload, dict):
        return {"text": str(payload if payload is not None else "").strip(), "duration_s": -1}
    text = str(payload.get("text") or payload.get("value") or "").strip()
    duration_raw = payload.get("duration") if "duration" in payload else payload.get("duration_s")
    duration_s = float(duration_raw) if isinstance(duration_raw, (int, float)) else -1
    return {"text": text, "duration_s": duration_s}


def extract_flow_end_output(rec: StepRecord | None) -> Optional[Dict[str, Any]]:
    """Extract the flow end response from a ledger record."""
    if not rec or not isinstance(rec, dict):
        return None
    out0 = rec.get("result", {}).get("output") if isinstance(rec.get("result"), dict) else None
    if isinstance(out0, str):
        response = out0.strip()
        if response:
            return {"response": response, "meta": None}
    if isinstance(out0, dict):
        def pick_textish(v: Any) -> str:
            if isinstance(v, str):
                return v.strip()
            if v is None:
                return ""
            if isinstance(v, (int, float, bool)):
                return str(v)
            return ""

        msg = (
            pick_textish(out0.get("answer"))
            or pick_textish(out0.get("response"))
            or pick_textish(out0.get("message"))
            or pick_textish(out0.get("text"))
            or pick_textish(out0.get("content"))
        )
        meta = dict(out0.get("meta")) if isinstance(out0.get("meta"), dict) else {}
        for key in (
            "artifact",
            "image_artifact",
            "video_artifact",
            "audio_artifact",
            "music_artifact",
            "artifact_ref",
            "artifact_id",
            "content_type",
            "outputs",
            "resources",
            "success",
            "scratchpad",
        ):
            if key in out0 and out0.get(key) is not None:
                meta[key] = out0.get(key)
        artifact = meta.get("artifact")
        if not isinstance(artifact, dict):
            artifact = out0.get("artifact_ref")
            if isinstance(artifact, dict):
                meta["artifact"] = artifact
        content_type = str((artifact or {}).get("content_type") or meta.get("content_type") or "").strip().lower()
        if isinstance(artifact, dict) and content_type.startswith("image/") and "image_artifact" not in meta:
            meta["image_artifact"] = artifact
        if isinstance(artifact, dict) and content_type.startswith("video/") and "video_artifact" not in meta:
            meta["video_artifact"] = artifact
        if isinstance(artifact, dict) and content_type.startswith("audio/") and "audio_artifact" not in meta:
            meta["audio_artifact"] = artifact
        if msg or meta:
            return {"response": msg, "meta": meta or None}
    return None


def extract_wait_from_record(rec: StepRecord | None) -> Optional[WaitState]:
    """Extract wait state from a ledger record.

    The runtime stores wait state at ``record.result.wait`` (see
    ``StepRecord.finish_waiting`` in abstractruntime).  This is the
    canonical location; we read it directly.
    """
    if not rec or not isinstance(rec, dict):
        return None
    result = rec.get("result")
    if not isinstance(result, dict):
        return None
    wait = result.get("wait")
    if isinstance(wait, dict):
        return wait  # type: ignore[return-value]
    return None


def _coerce_wait_reason(raw: Any) -> str:
    if raw is None:
        return ""
    if hasattr(raw, "value"):
        try:
            return str(raw.value or "").strip()
        except Exception:
            pass
    return str(raw or "").strip()


def is_tool_approval_wait(wait: WaitState | None) -> bool:
    if not wait or not isinstance(wait, dict):
        return False
    details = wait.get("details")
    if not isinstance(details, dict):
        wait_key = str(wait.get("wait_key") or "").strip().lower()
        if wait_key.startswith("tool_approval"):
            return True
        return False
    mode = str(details.get("mode") or "").strip().lower()
    if mode == "approval_required":
        return True
    executor = details.get("executor")
    if isinstance(executor, dict):
        kind = str(executor.get("kind") or "").strip().lower()
        if kind == "tool_approval":
            return True
    wait_key = str(wait.get("wait_key") or "").strip().lower()
    if wait_key.startswith("tool_approval"):
        return True
    return False


def extract_tool_calls_from_wait(wait: WaitState | None) -> List[ToolCall]:
    """Return tool calls embedded in a wait state (if any)."""
    if not wait or not isinstance(wait, dict):
        return []
    details = wait.get("details")
    if not isinstance(details, dict):
        return []
    tool_calls = details.get("tool_calls")
    if isinstance(tool_calls, list):
        return tool_calls
    tool_calls = details.get("tool_calls_for_evidence")
    return tool_calls if isinstance(tool_calls, list) else []
