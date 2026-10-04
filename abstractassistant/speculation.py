"""Thin-client MTP intent; capability authority stays with Core/Gateway.

The choices and sentences mirror the shared route picker of the other apps
(ui-kit ``speculation_control.ts`` + ``speculation_select.tsx``: one "MTP
depth" list — inherit, Off, then each depth the gateway advertises), so the
Assistant says exactly what AbstractCode and the gateway console say.
"""
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


def speculation_capability(payload: Any) -> Optional[dict]:
    """The gateway's ``execution.speculation`` card (kit
    ``speculationCapability``): None when discovery did not describe MTP."""
    execution = payload.get("execution") if isinstance(payload, dict) else None
    caps = execution.get("speculation") if isinstance(execution, dict) else None
    if not isinstance(caps, dict) or not isinstance(caps.get("supported"), bool):
        return None
    depths = caps.get("supported_depths") if caps["supported"] else []
    depths = sorted({n for n in depths if isinstance(n, int) and not isinstance(n, bool) and n > 0}) if isinstance(depths, list) else []
    return {
        "supported": caps["supported"],
        "ready": caps.get("ready") if isinstance(caps.get("ready"), bool) else None,
        "reason": caps.get("reason") if isinstance(caps.get("reason"), str) else None,
        "supported_depths": depths,
        "default": caps["effective_default"] if "effective_default" in caps else caps.get("default"),
        "requires_reload": caps.get("requires_reload") if isinstance(caps.get("requires_reload"), bool) else None,
    }


def speculation_options(payload: Any, saved: Any = None):
    """(choices, note). No model heuristics or invented depths when discovery
    is unavailable."""
    caps = speculation_capability(payload)
    depths = caps["supported_depths"] if caps else []
    inherited = caps["default"] if caps else None
    caption = "Gateway default"
    if inherited is False or isinstance(inherited, dict) and inherited.get("mode") == "off":
        caption += " (Off)"
    elif isinstance(inherited, dict) and isinstance(inherited.get("num_draft_tokens"), int):
        caption += f" (depth {inherited['num_draft_tokens']})"
    choices = [(None, caption), (False, "Off")]
    for depth in depths:
        choices.append((normalize_speculation({"mode": "native_mtp", "num_draft_tokens": depth}), f"Depth {depth}"))
    if isinstance(saved, dict) and saved.get("num_draft_tokens") not in depths:
        choices.append((saved, f"Depth {saved.get('num_draft_tokens')} (saved; not available)"))
    if caps is None:
        note = "MTP capability unknown; no depth is assumed."
    elif caps["reason"]:
        note = caps["reason"]
    elif caps["requires_reload"]:
        note = "Model reload required before MTP can run."
    elif caps["ready"] is False:
        note = "MTP is supported but not ready on this instance."
    elif caps["ready"] is None and caps["supported"]:
        note = "MTP support verified; loaded-instance readiness is unknown."
    elif not caps["supported"]:
        note = "MTP is not supported on this model/backend."
    else:
        note = ""
    return choices, note


def speculation_configurable(payload: Any, saved: Any = None) -> bool:
    """False only when the gateway SAYS the selected model/backend has no MTP
    and nothing is pinned: then there is nothing to choose (the list is shown
    disabled with the gateway's sentence). A pinned value stays changeable so
    it can be put back on Gateway default."""
    caps = speculation_capability(payload)
    if caps is not None and caps["supported"] is False and saved is None:
        return False
    return True
