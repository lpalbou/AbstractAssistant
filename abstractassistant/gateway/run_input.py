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
    primary_image_artifact: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build workflow input without desktop-owned routing or history authority.

    Provider/model routing is resolved by Gateway/Core capability defaults.
    ``messages`` is opt-in because canonical history belongs to Runtime/Gateway;
    v2 and CLI callers should pass only the prompt plus artifact references.
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
        "_runtime": runtime_ns,
        "max_iterations": max(1, int(max_iterations)),
        "has_primary_image_context": primary_image is not None,
    }
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
