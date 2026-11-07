"""Reasoning effort and MTP follow the SELECTED model (operator rule 2026-11-07).

- MTP is offered and sent only when the gateway's capability card for that model says it is
  supported, at a depth the card lists. No card, an unsupported card or an unlisted depth sends
  nothing (not even "Off").
- Changing the model or provider resets reasoning and MTP to the gateway default (nothing sent).
- A saved reasoning level or MTP depth the current model cannot use is never sent.

The same rule as the shared kit controls (AbstractUIC ui-kit ``model_options.ts``:
``reasoningFacts``, ``usableSpeculation``, ``usableReasoning``, ``sendableModelOptions``), so the
desktop Assistant decides exactly what the web apps decide. Served facts only: no model-name
heuristics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from .speculation import normalize_speculation, speculation_capability


def _safe_speculation(value: Any) -> Optional[Union[bool, dict]]:
    try:
        return normalize_speculation(value)
    except ValueError:
        return None


def reasoning_facts(payload: Any) -> Dict[str, Any]:
    """What the gateway serves about a model's reasoning: ``levels`` and ``support``
    (``thinking_support``; None = not said). Accepts the discovery payload or its
    ``capabilities`` card."""
    root = payload if isinstance(payload, dict) else {}
    caps = root.get("capabilities") if isinstance(root.get("capabilities"), dict) else root
    values = caps.get("reasoning_levels") or caps.get("thinking_levels")
    levels: List[str] = []
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str) and value.strip() and value not in levels:
                levels.append(value)
    control = caps.get("thinking_control") if isinstance(caps.get("thinking_control"), dict) else {}
    if not levels and caps.get("thinking_support") is True and control.get("prompt_disable_token"):
        levels = ["off", "auto"]
    support = caps.get("thinking_support")
    return {"levels": levels, "support": support if isinstance(support, bool) else None}


def usable_speculation(value: Any, payload: Any) -> Optional[Union[bool, dict]]:
    """The MTP value the model can use, or None (= send nothing)."""
    normalized = _safe_speculation(value)
    if normalized is None:
        return None
    caps = speculation_capability(payload)
    if not caps or not caps["supported"]:
        return None
    if normalized is False:
        return False
    return normalized if normalized["num_draft_tokens"] in caps["supported_depths"] else None


def usable_reasoning(value: Any, payload: Any) -> str:
    """The reasoning level the model can use, or "" (= send nothing). Unknown facts keep the level."""
    level = value.strip() if isinstance(value, str) else ""
    if not level:
        return ""
    facts = reasoning_facts(payload)
    if facts["support"] is False:
        return ""
    if facts["levels"] and level not in facts["levels"]:
        return ""
    return level


def sendable_model_options(reasoning: Any, speculation: Any, payload: Any) -> Tuple[str, Optional[Union[bool, dict]]]:
    """Only the options the model's capability card allows: (reasoning, speculation), where ""
    and None mean "send nothing". ``payload`` None = the card could not be read: then no MTP is
    sent and the reasoning level is kept (unknown is not unsupported)."""
    return usable_reasoning(reasoning, payload), usable_speculation(speculation, payload)


__all__ = ["reasoning_facts", "sendable_model_options", "usable_reasoning", "usable_speculation"]
