"""Words for gateway events the palette shows.

The run itself is read as AbstractRuntime's replay view (`gateway.replay_view`); nothing here
parses ledger records.
"""

from __future__ import annotations

from typing import Any, Dict


def tool_policy_decision_text(event: Dict[str, Any]) -> str:
    """``Allowed by this chat's policy: fetch_url`` / ``Denied by …``."""
    names = [str(t.get("name") or "") for t in (event.get("tools") or []) if isinstance(t, dict) and t.get("name")]
    verb = "Denied" if str(event.get("decision") or "") == "denied" else "Allowed"
    text = f"{verb} by this chat's policy"
    return f"{text}: {', '.join(names)}" if names else text

