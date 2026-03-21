"""Gateway bundle discovery helpers (agent template selection)."""

from typing import Any, Dict, List


def _entrypoints_from_bundles_response(bundles_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    items = bundles_response.get("items")
    if not isinstance(items, list):
        items = []
    default_bundle_id = str(bundles_response.get("default_bundle_id") or "").strip()
    for b in items:
        if not isinstance(b, dict):
            continue
        bundle_id = str(b.get("bundle_id") or "").strip()
        eps = b.get("entrypoints")
        if not bundle_id or not isinstance(eps, list):
            continue
        default_entrypoint = str(b.get("default_entrypoint") or "").strip()
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
                    "default_bundle": bundle_id == default_bundle_id,
                    "default_entrypoint": flow_id == default_entrypoint,
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
    eps = _entrypoints_from_bundles_response(bundles_response)
    candidates = [e for e in eps if "abstractcode.agent.v1" in (e.get("interfaces") or [])]

    bundle_id_s = str(bundle_id or "").strip()
    flow_id_s = str(flow_id or "").strip()
    visible_bundle_ids = {
        str(b.get("bundle_id") or "").strip()
        for b in items
        if isinstance(b, dict) and str(b.get("bundle_id") or "").strip()
    }

    if not candidates:
        if bundle_id_s and bundle_id_s in visible_bundle_ids:
            raise RuntimeError(f"Gateway bundle '{bundle_id_s}' has no abstractcode.agent.v1 entrypoints")
        if bundle_id_s:
            raise RuntimeError(
                f"Gateway bundle '{bundle_id_s}' is not available. "
                "Check workflow bundle loading on the gateway (for local dev, ABSTRACTGATEWAY_FLOWS_DIR)."
            )
        raise RuntimeError(
            "Gateway exposes no abstractcode.agent.v1 entrypoints. "
            "Check workflow bundle loading on the gateway (for local dev, ABSTRACTGATEWAY_FLOWS_DIR)."
        )

    if bundle_id_s:
        candidates = [c for c in candidates if c.get("bundle_id") == bundle_id_s]
        if not candidates:
            if bundle_id_s in visible_bundle_ids:
                raise RuntimeError(f"Gateway bundle '{bundle_id_s}' has no abstractcode.agent.v1 entrypoints")
            raise RuntimeError(
                f"Gateway bundle '{bundle_id_s}' is not available. "
                "Check workflow bundle loading on the gateway (for local dev, ABSTRACTGATEWAY_FLOWS_DIR)."
            )

    if flow_id_s:
        matching = [c for c in candidates if c.get("flow_id") == flow_id_s]
        if len(matching) == 1:
            c = matching[0]
            return {"bundle_id": c["bundle_id"], "flow_id": c["flow_id"]}
        if len(matching) > 1 and not bundle_id_s:
            raise RuntimeError(f"Gateway flow_id '{flow_id_s}' is ambiguous; select a workflow")
        raise RuntimeError(f"Gateway bundle '{bundle_id_s}' does not expose flow_id '{flow_id_s}'")

    if bundle_id_s:
        default_entry = [c for c in candidates if bool(c.get("default_entrypoint"))]
        if len(default_entry) == 1:
            c = default_entry[0]
            return {"bundle_id": c["bundle_id"], "flow_id": c["flow_id"]}
        if len(candidates) == 1:
            c = candidates[0]
            return {"bundle_id": c["bundle_id"], "flow_id": c["flow_id"]}
        raise RuntimeError(f"Gateway bundle '{bundle_id_s}' exposes multiple abstractcode.agent.v1 entrypoints; select a workflow")

    default_bundle_default_entry = [
        c for c in candidates if bool(c.get("default_bundle")) and bool(c.get("default_entrypoint"))
    ]
    if len(default_bundle_default_entry) == 1:
        c = default_bundle_default_entry[0]
        return {"bundle_id": c["bundle_id"], "flow_id": c["flow_id"]}

    default_bundle_candidates = [c for c in candidates if bool(c.get("default_bundle"))]
    if len(default_bundle_candidates) == 1:
        c = default_bundle_candidates[0]
        return {"bundle_id": c["bundle_id"], "flow_id": c["flow_id"]}

    if len(candidates) == 1:
        c = candidates[0]
        return {"bundle_id": c["bundle_id"], "flow_id": c["flow_id"]}

    raise RuntimeError("Gateway exposes multiple abstractcode.agent.v1 entrypoints and no default; select a workflow")


def list_agent_entrypoints(*, bundles_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return all abstractcode.agent.v1 entrypoints for UI selection."""
    eps = _entrypoints_from_bundles_response(bundles_response)
    return [e for e in eps if "abstractcode.agent.v1" in (e.get("interfaces") or [])]
