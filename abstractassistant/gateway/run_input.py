"""
Build gateway run input data for assistant-compatible agent workflows.

Ported from `abstractcode/web/src/lib/run_input.ts` (simplified).
"""

from typing import Any, Dict, List, Optional


def _to_chat_messages(messages: List[Dict[str, Any]], keep: int) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip()
        if role not in {"user", "assistant", "system"}:
            continue
        content = str(m.get("content") or "")
        if not content.strip():
            continue
        out.append({"role": role, "content": content})
    if keep <= 0:
        return out
    return out[-keep:]


def build_run_input_data(
    *,
    prompt: str,
    system: str = "",
    messages: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    allowed_tools: Optional[List[str]] = None,
    tool_policy: Optional[Dict[str, Any]] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    max_iterations: int = 50,
    use_context: bool = False,
    use_session_history: bool = True,
    primary_image_artifact: Optional[Dict[str, Any]] = None,
    provider: str = "",
    model: str = "",
    base_url: str = "",
) -> Dict[str, Any]:
    """Build workflow input without desktop-owned routing or history authority.

    Provider/model routing is normally resolved by Gateway/Core capability
    defaults. ``provider``/``model``/``base_url`` are an OPTIONAL LOCAL OVERRIDE
    for this app only, sent on BOTH channels so it covers the whole workflow
    without ever mutating the gateway's global default:
      - TOP-LEVEL ``provider``/``model`` flow through the start node's pins into
        every node that reads them — critically the router ``llm_call`` node,
        which does NOT read ``_runtime`` (verified live: a ``_runtime``-only
        override leaves the router on the gateway default, so an online-only
        default still breaks the FIRST call offline).
      - ``_runtime.provider``/``model`` covers agent-style nodes and any future
        node that inherits run-scoped defaults (the gateway seeds its own
        default there only when empty — bundle_host).
    Both provider and model are required for the override to take effect (a
    half-pin is dropped). ``base_url`` is best-effort: endpoint-profile
    providers (``endpoint:<id>``) carry their own base_url via the gateway's
    live resolver; a plain provider inherits the runtime's construction kwargs.
    ``messages`` is opt-in because canonical history belongs to Runtime/Gateway:
    ``use_session_history`` (default on) asks the gateway to seed
    ``context.messages`` from the session's durable prior turns at run start
    (agora `durable-sessions` contract v1), so the tray and CLI callers pass
    only the prompt plus artifact references and the server owns the replay.
    """
    prompt_s = str(prompt or "")
    system_s = str(system or "")

    attachments_list = [dict(a) for a in attachments or [] if isinstance(a, dict) and a.get("$artifact")]
    messages_list = _to_chat_messages(messages or [], keep=200) if use_context else []
    primary_image = (
        dict(primary_image_artifact)
        if isinstance(primary_image_artifact, dict) and str(primary_image_artifact.get("$artifact") or "").strip()
        else None
    )

    ctx: Dict[str, Any] = {"task": prompt_s, "messages": messages_list}
    if attachments_list:
        ctx["attachments"] = attachments_list
        ctx["media"] = attachments_list
    if primary_image is not None:
        ctx["primary_image_artifact"] = primary_image

    runtime_ns: Dict[str, Any] = {}
    if isinstance(temperature, (int, float)):
        runtime_ns["temperature"] = float(temperature)
    if isinstance(seed, int):
        runtime_ns["seed"] = int(seed)
    if allowed_tools is not None:
        runtime_ns["allowed_tools"] = [str(t).strip() for t in allowed_tools if str(t).strip()]

    # Local provider/model override for THIS app. Both are required; a half-pin
    # is dropped so we never send a provider without a model (or vice versa).
    provider_s = str(provider or "").strip()
    model_s = str(model or "").strip()
    base_url_s = str(base_url or "").strip()
    override_active = bool(provider_s and model_s)
    if override_active:
        runtime_ns["provider"] = provider_s
        runtime_ns["model"] = model_s
        if base_url_s:
            runtime_ns["base_url"] = base_url_s

    if isinstance(tool_policy, dict):
        auto_raw = tool_policy.get("auto_approve_tools") or tool_policy.get("autoApproveTools") or tool_policy.get("autoApprove")
        req_raw = tool_policy.get("require_approval_tools") or tool_policy.get("requireApprovalTools") or tool_policy.get("requireApproval")

        def _coerce_list(raw: Any) -> list[str]:
            if raw is None:
                return []
            if isinstance(raw, str):
                items = [s.strip() for s in raw.split(",")]
                return [s for s in items if s]
            if isinstance(raw, (list, tuple, set)):
                out: list[str] = []
                for item in raw:
                    s = str(item or "").strip()
                    if s:
                        out.append(s)
                return out
            return []

        auto_list = _coerce_list(auto_raw)
        req_list = _coerce_list(req_raw)
        if auto_list or req_list:
            runtime_ns["tool_policy"] = {
                "auto_approve_tools": auto_list,
                "require_approval_tools": req_list,
            }

    out: Dict[str, Any] = {
        "prompt": prompt_s,
        "context": ctx,
        "use_context": bool(use_context),
        "use_session_history": bool(use_session_history),
        "_runtime": runtime_ns,
        "max_iterations": max(1, int(max_iterations)),
        "has_primary_image_context": primary_image is not None,
    }
    # Top-level pins: the start node feeds these to every node that reads
    # provider/model — including the router llm_call node that ignores _runtime.
    # Without this, an override would miss the FIRST call of every run.
    if override_active:
        out["provider"] = provider_s
        out["model"] = model_s
        if base_url_s:
            out["base_url"] = base_url_s
    if system_s:
        out["system"] = system_s

    if attachments_list:
        out["attachments"] = attachments_list
    if primary_image is not None:
        out["primary_image_artifact"] = primary_image

    if allowed_tools is not None:
        out["tools"] = runtime_ns.get("allowed_tools", [])

    if isinstance(temperature, (int, float)):
        out["temperature"] = float(temperature)
    if isinstance(seed, int):
        out["seed"] = int(seed)

    return out
