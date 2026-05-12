"""Gateway session prompt-cache helpers for thin assistant runs."""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional

from .capabilities import AssistantCapabilities, get_cached_assistant_capabilities


def merge_prompt_cache_runtime_hint(input_data: Dict[str, Any], runtime_hint: Dict[str, Any]) -> bool:
    """Merge Gateway's prompt-cache runtime hint into run input."""
    if not isinstance(input_data, dict) or not isinstance(runtime_hint, dict):
        return False

    prompt_cache = None
    runtime = runtime_hint.get("_runtime")
    if isinstance(runtime, dict):
        prompt_cache = runtime.get("prompt_cache")
    if not isinstance(prompt_cache, dict):
        key = str(runtime_hint.get("prompt_cache_key") or "").strip()
        namespace = str(runtime_hint.get("namespace") or "").strip()
        if key:
            prompt_cache = {"key": key}
            if namespace:
                prompt_cache["namespace"] = namespace

    if not isinstance(prompt_cache, dict) or not str(prompt_cache.get("key") or "").strip():
        return False

    runtime_out = input_data.setdefault("_runtime", {})
    if not isinstance(runtime_out, dict):
        runtime_out = {}
        input_data["_runtime"] = runtime_out
    runtime_out["prompt_cache"] = dict(prompt_cache)
    return True


def prepare_session_prompt_cache(
    *,
    gateway: Any,
    session_id: str,
    provider: str,
    model: str,
    bundle_id: str,
    flow_id: str,
    input_data: Dict[str, Any],
    system_prompt: str = "",
    attachments: Optional[List[Dict[str, Any]]] = None,
    template_id: str = "",
    capabilities: Optional[AssistantCapabilities] = None,
) -> Optional[Dict[str, Any]]:
    """Prepare Gateway-owned session cache and merge any runtime hint."""
    caps = capabilities or get_cached_assistant_capabilities(gateway)
    if not caps.session_prompt_cache_available():
        return None

    sid = str(session_id or "").strip()
    provider_s = str(provider or "").strip()
    model_s = str(model or "").strip()
    if not sid or not provider_s or not model_s:
        return None

    try:
        response = gateway.session_prompt_cache_prepare(
            session_id=sid,
            provider=provider_s,
            model=model_s,
            bundle_id=str(bundle_id or "").strip() or None,
            flow_id=str(flow_id or "").strip() or None,
            template_id=str(template_id or "").strip() or None,
            system_prompt=str(system_prompt or "").strip() or None,
            pinned_attachments=[dict(a) for a in (attachments or []) if isinstance(a, dict)] or None,
            make_default=False,
        )
    except Exception as e:
        warnings.warn(f"#FALLBACK: gateway session prompt-cache prepare failed: {e}")
        return None

    if not isinstance(response, dict):
        return None
    runtime_hint = response.get("runtime_hint")
    if isinstance(runtime_hint, dict) and response.get("supported") is not False:
        merge_prompt_cache_runtime_hint(input_data, runtime_hint)
    return response

