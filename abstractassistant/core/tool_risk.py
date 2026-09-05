"""Human-readable risk facts for a tool, derived from the gateway inventory.

The gateway's ``/discovery/tools`` items carry the risk classification the
runtime enforces (``risk_tier``, ``approval_default``, ``mutating``,
``destructive_capable``, ``remote_write_capable``, ``captures_environment``,
``comms_send``). The assistant never invents its own classification: it only
turns those fields into a badge, a tone and one plain sentence so the approval
popup and the Tools settings say the same thing the gateway enforces.
"""

from __future__ import annotations

from typing import Any, Dict, List


# risk_tier -> (badge label, visual tone, ordering rank)
_RISK_TIERS: Dict[str, tuple[str, str, int]] = {
    "observe": ("Reads only", "observe", 1),
    "act": ("Makes changes", "act", 2),
    "outreach": ("Reaches outside", "outreach", 3),
    "destroy": ("Destructive", "destroy", 4),
}


def _flag(item: Dict[str, Any], key: str) -> bool:
    value = item.get(key)
    return value is True


def describe_tool_risk(item: Dict[str, Any] | None) -> Dict[str, Any]:
    """Return ``{tier, label, tone, rank, facts, sentence, approval_default}``.

    ``facts`` is a short list of concrete capabilities (``"writes files"``,
    ``"sends messages"``...). ``sentence`` is the one-line explanation for a
    card. Unknown/missing metadata degrades to a neutral "Risk not classified"
    badge rather than a fabricated safe one.
    """
    data = dict(item or {})
    tier = str(data.get("risk_tier") or "").strip().lower()
    label, tone, rank = _RISK_TIERS.get(tier, ("Risk not classified", "unknown", 0))

    facts: List[str] = []
    if _flag(data, "destructive_capable"):
        facts.append("can delete or overwrite")
    elif _flag(data, "mutating"):
        facts.append("changes files or state")
    if _flag(data, "comms_send"):
        facts.append("sends messages on your behalf")
    if _flag(data, "remote_write_capable"):
        facts.append("reaches remote services")
    if _flag(data, "captures_environment"):
        facts.append("captures your camera, screen or surroundings")
    if not facts and tier == "observe":
        facts.append("read-only")

    approval_default = str(data.get("approval_default") or "").strip().lower()
    if approval_default == "auto":
        gate = "the gateway runs it without asking by default"
    elif approval_default == "ask":
        gate = "the gateway asks before running it by default"
    else:
        gate = ""

    sentence_bits = [label.lower()] if tier in _RISK_TIERS else []
    if facts:
        sentence_bits.append(", ".join(facts))
    sentence = "; ".join(bit for bit in sentence_bits if bit)
    if gate:
        sentence = f"{sentence} — {gate}." if sentence else f"{gate}."
    elif sentence:
        sentence = f"{sentence}."
    if sentence:
        sentence = sentence[0].upper() + sentence[1:]

    return {
        "tier": tier if tier in _RISK_TIERS else "",
        "label": label,
        "tone": tone,
        "rank": rank,
        "facts": facts,
        "sentence": sentence,
        "approval_default": approval_default,
    }


def risk_rank(item: Dict[str, Any] | None) -> int:
    return int(describe_tool_risk(item).get("rank") or 0)


__all__ = ["describe_tool_risk", "risk_rank"]
