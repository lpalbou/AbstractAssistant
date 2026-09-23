"""Thin-client MTP intent; capability authority stays with Core/Gateway."""
from typing import Any, Optional, Union


def normalize_speculation(value: Any) -> Optional[Union[bool, dict]]:
    if value is False or isinstance(value, dict) and value.get("mode") == "off":
        return False
    if value is None:
        return None
    if isinstance(value, dict) and value.get("mode") == "native_mtp":
        depth = value.get("num_draft_tokens")
        if isinstance(depth, int) and not isinstance(depth, bool) and depth > 0:
            return {"mode": "native_mtp", "num_draft_tokens": depth, "require_acceleration": True}
    raise ValueError("MTP must be off or a native_mtp request with a positive integer depth")


def speculation_options(payload: Any, saved: Any = None):
    """No model heuristics or invented depths when discovery is unavailable."""
    execution = payload.get("execution") if isinstance(payload, dict) else None
    caps = execution.get("speculation") if isinstance(execution, dict) else None
    if not isinstance(caps, dict):
        caps = {}
    depths = caps.get("supported_depths", []) if caps.get("supported") is True else []
    depths = sorted({n for n in depths if isinstance(n, int) and not isinstance(n, bool) and n > 0}) if isinstance(depths, list) else []
    inherited = caps.get("effective_default", caps.get("default"))
    caption = "Gateway default"
    if inherited is False or isinstance(inherited, dict) and inherited.get("mode") == "off":
        caption += " (Off)"
    elif isinstance(inherited, dict) and isinstance(inherited.get("num_draft_tokens"), int):
        caption += f" (depth {inherited['num_draft_tokens']})"
    choices = [(None, caption), (False, "Off")]
    for depth in depths:
        choices.append((normalize_speculation({"mode": "native_mtp", "num_draft_tokens": depth}), f"Depth {depth}"))
    if isinstance(saved, dict) and saved.get("num_draft_tokens") not in depths:
        choices.append((saved, f"Depth {saved.get('num_draft_tokens')} (saved; unavailable)"))
    note = str(caps.get("reason") or "")
    if not note:
        if not caps:
            note = "MTP capability unknown; no depth is assumed."
        elif caps.get("supported") is not True:
            note = "MTP is not supported on this model/backend."
        elif caps.get("requires_reload"):
            note = "Model reload required before MTP can run."
        elif caps.get("ready") is not True:
            note = "MTP is supported; loaded-instance readiness is not confirmed."
    return choices, note
