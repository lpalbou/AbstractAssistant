"""
Build gateway run input data for assistant-compatible agent workflows.

Ported from `abstractcode/web/src/lib/run_input.ts` (simplified).
"""

import warnings
from typing import Any, Dict, List, Optional

from ..assistant_workflow import SOUND_OUTPUT_SPEC


# Media route overrides ride dedicated input pins on the managed orchestrator
# workflow (the media nodes read them as their provider/model inputs; absent
# pins leave the output spec bare so the gateway default applies). One route
# key maps to one (provider_pin, model_pin) pair.
MEDIA_OVERRIDE_INPUT_KEYS: Dict[str, tuple] = {
    "output.image.text_to_image": ("image_provider", "image_model"),
    "output.image.image_to_image": ("image_edit_provider", "image_edit_model"),
    "output.image.image_upscale": ("image_upscale_provider", "image_upscale_model"),
    "output.video.text_to_video": ("video_provider", "video_model"),
    "output.video.image_to_video": ("image_to_video_provider", "image_to_video_model"),
    "output.music": ("music_provider", "music_model"),
}

# The sound path is an llm_call node whose generation target is its output
# SPEC object, so the override rides inside that spec (a bare provider/model
# pin on the node would select the TEXT model, not the audio backend).
SOUND_OVERRIDE_ROUTE_KEY = "output.sound"


def apply_media_overrides(out: Dict[str, Any], media_overrides: Optional[Dict[str, Dict[str, Any]]]) -> None:
    """Fold per-route media overrides into workflow input pins (in place).

    Every override requires BOTH provider and model — a half-pin is dropped
    with a warning (same contract as the chat-text override: half overrides
    are indistinguishable from misconfiguration and would send a broken pin).
    """
    if not isinstance(media_overrides, dict):
        return
    for route_key, override in media_overrides.items():
        key = str(route_key or "").strip()
        if not isinstance(override, dict):
            continue
        provider = str(override.get("provider") or "").strip()
        model = str(override.get("model") or "").strip()
        if not provider or not model:
            if provider or model:
                warnings.warn(f"#FALLBACK: dropping half-specified media override for {key} (need provider AND model)")
            continue
        if key == SOUND_OVERRIDE_ROUTE_KEY:
            spec = dict(SOUND_OUTPUT_SPEC)
            spec["provider"] = provider
            spec["model"] = model
            out["sound_output"] = spec
            continue
        pins = MEDIA_OVERRIDE_INPUT_KEYS.get(key)
        if not pins:
            warnings.warn(f"#FALLBACK: ignoring media override for unknown route {key}")
            continue
        provider_pin, model_pin = pins
        out[provider_pin] = provider
        out[model_pin] = model


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
    media_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    thinking: str = "",
    speculation: Any = None,
    stream: Optional[bool] = None,
    workspace_root: str = "",
    workspace_access_mode: str = "",
    workspace_allowed_paths: Optional[List[str]] = None,
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
    ``media_overrides`` maps capability route keys (output.image.*, output.video.*,
    output.music, output.sound) to {provider, model} — per-run local overrides
    that ride the managed workflow's media input pins (see apply_media_overrides).
    ``thinking`` is the reasoning effort (gateway contract
    ``thinking_control``: none|minimal|low|medium|high|xhigh); it rides
    ``_runtime.thinking``, the documented inheritance lane every LLM/agent node
    reads (a top-level pin would need a flow input the orchestrator lacks).
    ``stream`` asks for live replies (``_runtime.stream``, contract S): True
    streams the model's text as it is written, False pins it off, None sends
    NOTHING so the gateway's own ``agents.streaming_default`` applies.
    ``workspace_root`` / ``workspace_access_mode`` / ``workspace_allowed_paths``
    scope the run's filesystem tools; the gateway sanitizes them against its own
    policy and may clamp or refuse them. Blanks send nothing (server-managed).
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

    thinking_s = str(thinking or "").strip().lower()
    if thinking_s:
        runtime_ns["thinking"] = thinking_s
    if speculation is not None:
        from abstractassistant.speculation import normalize_speculation
        runtime_ns["speculation"] = normalize_speculation(speculation)
    if stream is not None:
        if not isinstance(stream, bool):
            raise ValueError(f"stream must be None, True or False, not {stream!r}")
        runtime_ns["stream"] = stream

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

    # Per-run media model overrides (image/video/music/sound) — local to this
    # app, delivered as workflow input pins; the gateway default is untouched.
    apply_media_overrides(out, media_overrides)

    # Workspace scope for the run's filesystem tools (the runtime's
    # workspace-scoped tools read these keys from run vars; the gateway
    # sanitizes them at start). Only non-blank values are sent.
    root_s = str(workspace_root or "").strip()
    if root_s:
        out["workspace_root"] = root_s
    mode_s = str(workspace_access_mode or "").strip().lower()
    if mode_s:
        out["workspace_access_mode"] = mode_s
    allowed = [str(p or "").strip() for p in (workspace_allowed_paths or []) if str(p or "").strip()]
    if allowed:
        out["workspace_allowed_paths"] = allowed

    return out
