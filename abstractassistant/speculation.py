"""Thin-client MTP intent; capability authority stays with Core/Gateway.

The choices and sentences mirror the shared route picker of the other apps
(ui-kit ``speculation_control.ts`` + ``speculation_select.tsx``: one "MTP
depth" list — inherit, then, only for a model the gateway says supports MTP,
Off and each depth it advertises), so the Assistant says exactly what
AbstractCode and the gateway console say.
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
    message = caps.get("message")
    return {
        "supported": caps["supported"],
        "ready": caps.get("ready") if isinstance(caps.get("ready"), bool) else None,
        # The gateway's code for why MTP cannot run (shown under Technical details).
        "reason": caps.get("reason") if isinstance(caps.get("reason"), str) else None,
        # The gateway's sentence for people, when it gives one.
        "message": message if isinstance(message, str) and message.strip() else None,
        "supported_depths": depths,
        "default": caps["effective_default"] if "effective_default" in caps else caps.get("default"),
        "requires_reload": caps.get("requires_reload") if isinstance(caps.get("requires_reload"), bool) else None,
    }


# The kit's sentences (speculation_select.tsx), word for word.
SPECULATION_CHECKING = "Checking whether this model supports MTP…"
SPECULATION_UNKNOWN = "MTP is offered when the gateway confirms this model supports it."
SPECULATION_UNSUPPORTED = "This model does not support MTP."


def speculation_view(payload: Any, saved: Any = None, *, loading: bool = False) -> dict:
    """What the MTP depth control shows for the SELECTED model (operator rule 2026-11-07, the
    kit's ``SpeculationSelect``):

    - ``choices``: inherit ("Gateway default"), then — only when the model's capability card says
      MTP is supported — Off and each depth the card lists. Never a "(saved)" depth.
    - ``selected``: the saved value when the card allows it, else None (inherit): a saved depth
      the model cannot use is not shown as chosen (and is never sent, model_options.py).
    - ``enabled``: only when MTP is supported.
    - ``note``: the gateway's ``message`` or the kit's sentence; ``detail``: the gateway's own
      reason code or discovery error, for Technical details.
    - ``state``: loading | supported | unsupported | unknown.
    No model heuristics and no invented depths."""
    from .model_options import usable_speculation

    error = str(payload.get("error") or "").strip() if isinstance(payload, dict) else ""
    caps = None if (loading or error) else speculation_capability(payload)
    supported = bool(caps and caps["supported"])
    caption = "Gateway default"
    if supported:
        inherited = caps["default"]
        if inherited is False or isinstance(inherited, dict) and inherited.get("mode") == "off":
            caption += " (Off)"
        elif isinstance(inherited, dict) and isinstance(inherited.get("num_draft_tokens"), int):
            caption += f" (depth {inherited['num_draft_tokens']})"
    choices = [(None, caption)]
    if supported:
        choices.append((False, "Off"))
        for depth in caps["supported_depths"]:
            choices.append((normalize_speculation({"mode": "native_mtp", "num_draft_tokens": depth}), f"Depth {depth}"))
    if loading:
        note, state = SPECULATION_CHECKING, "loading"
    elif caps is None:
        note, state = SPECULATION_UNKNOWN, "unknown"
    elif not supported:
        note, state = caps["message"] or SPECULATION_UNSUPPORTED, "unsupported"
    else:
        state = "supported"
        if caps["message"]:
            note = caps["message"]
        elif caps["requires_reload"]:
            note = "Model reload required before MTP can run."
        elif caps["ready"] is False:
            note = "MTP is supported but not ready on this instance."
        elif caps["ready"] is None:
            note = "MTP support verified; loaded-instance readiness is unknown."
        else:
            note = ""
    detail = error or (caps["reason"] if caps and caps["reason"] else "")
    return {
        "choices": choices,
        "selected": usable_speculation(saved, payload) if supported else None,
        "enabled": supported,
        "note": note,
        "detail": detail,
        "state": state,
    }
