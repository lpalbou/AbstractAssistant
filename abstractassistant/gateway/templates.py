"""
Gateway bundle discovery helpers (agent template selection).

Mirrors `abstractcode/web` entrypoint selection logic.
"""

from typing import Any, Dict, List, Optional
import warnings


def _entrypoints_from_bundles(items: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for b in items or []:
        if not isinstance(b, dict):
            continue
        bundle_id = str(b.get("bundle_id") or "").strip()
        eps = b.get("entrypoints")
        if not bundle_id or not isinstance(eps, list):
            continue
        for ep in eps:
            if not isinstance(ep, dict):
                continue
            flow_id = str(ep.get("flow_id") or "").strip()
            if not flow_id:
                continue
            interfaces = [str(x or "").strip() for x in ep.get("interfaces") or [] if str(x or "").strip()]
            out.append(
                {
                    "bundle_id": bundle_id,
                    "flow_id": flow_id,
                    "interfaces": interfaces,
                    "name": str(ep.get("name") or "").strip() or f"{bundle_id}:{flow_id}",
                }
            )
    return out


def select_agent_template(
    *,
    bundles_response: Dict[str, Any],
    bundle_id: str,
    flow_id: str,
) -> Dict[str, str]:
    """Select an abstractcode.agent.v1 entrypoint from bundles."""
    items = bundles_response.get("items")
    if not isinstance(items, list):
        items = []
    eps = _entrypoints_from_bundles(items)
    candidates = [e for e in eps if "abstractcode.agent.v1" in (e.get("interfaces") or [])]

    bundle_id_s = str(bundle_id or "").strip()
    flow_id_s = str(flow_id or "").strip()

    if bundle_id_s:
        candidates = [c for c in candidates if c.get("bundle_id") == bundle_id_s]

    if flow_id_s:
        for c in candidates:
            if c.get("flow_id") == flow_id_s:
                return {"bundle_id": c["bundle_id"], "flow_id": c["flow_id"]}
        raise RuntimeError(f"Gateway bundle '{bundle_id_s}' does not expose flow_id '{flow_id_s}'")

    if bundle_id_s and len(candidates) == 1:
        return {"bundle_id": candidates[0]["bundle_id"], "flow_id": candidates[0]["flow_id"]}

    if bundle_id_s:
        # Try "first" candidate in this bundle.
        if candidates:
            warnings.warn("#FALLBACK: gateway flow_id missing; using first entrypoint in bundle")
            return {"bundle_id": candidates[0]["bundle_id"], "flow_id": candidates[0]["flow_id"]}
        raise RuntimeError(f"Gateway bundle '{bundle_id_s}' has no abstractcode.agent.v1 entrypoints")

    if candidates:
        warnings.warn("#FALLBACK: gateway bundle_id missing; using first abstractcode.agent.v1 entrypoint")
        return {"bundle_id": candidates[0]["bundle_id"], "flow_id": candidates[0]["flow_id"]}

    raise RuntimeError("Gateway has no abstractcode.agent.v1 entrypoints available")


def list_agent_entrypoints(*, bundles_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return all abstractcode.agent.v1 entrypoints for UI selection."""
    items = bundles_response.get("items")
    if not isinstance(items, list):
        items = []
    eps = _entrypoints_from_bundles(items)
    return [e for e in eps if "abstractcode.agent.v1" in (e.get("interfaces") or [])]
