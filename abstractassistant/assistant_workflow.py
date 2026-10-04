"""Canonical gateway workflow definition for the tray assistant."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


MANAGED_ASSISTANT_WORKFLOW_NAME = "AbstractAssistant Orchestrator"
MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID = "abstractassistant-orchestrator"
MANAGED_ASSISTANT_WORKFLOW_MARKER = "managed-by=abstractassistant;scope=tenant-catalog"

# BUMP THIS whenever the managed workflow below changes in a way that must reach
# gateways. It is what lets two builds of the app coexist on one machine.
#
# The app reconciles its managed workflow at launch: if the gateway's stored copy
# differs from this build's, it republishes and promotes. With nothing ordering the two,
# an OLDER build "fixed the drift" by DOWNGRADING a newer workflow — and the newer build
# put it back on its next launch. Measured 2026-09-17: the installed app (Sep 7 build) and
# the source tree flipped the catalog default four times in 17 minutes. Every flip makes
# the gateway rebuild its host: 40-60 s of failed health probes while a 15 GB model
# reloads, and every in-process prompt cache gone. A build now publishes only when its
# revision is >= the stored one; a NEWER stored workflow is used as it is.
#   1 = everything before revisions existed (no marker in the description)
#   2 = route_call pins `tools: []` / `temperature: 0.0` (2026-09-17)
#   3 = explicit agent tool defaults for callers without chat tool selections
#   4 = the router's typed `seconds` argument reaches the sound/music nodes (R10.1, 2026-10-04)
MANAGED_ASSISTANT_WORKFLOW_REVISION = 4
_REVISION_MARKER_PREFIX = "workflow-revision="


def managed_workflow_revision_of(flow: Any) -> int:
    """The revision a stored managed workflow declares (1 when it declares none)."""
    description = str((flow or {}).get("description") or "") if isinstance(flow, dict) else ""
    match = re.search(re.escape(_REVISION_MARKER_PREFIX) + r"(\d+)", description)
    return int(match.group(1)) if match else 1


ASSISTANT_INTERFACE = "abstractassistant.agent.v1"

_BASE_SYSTEM_PROMPT = (
    "You are AbstractAssistant, a concise desktop assistant running through AbstractGateway. "
    "Use tools when the request needs live information, web access, files, repositories, or device actions. "
    "Use the gateway-provided defaults instead of inventing providers or models. "
    "When you use web tools, summarize with direct source references. "
    "Do not claim you cannot browse if web_search or fetch_url are available. "
    "If the user asks for generated media, the workflow will route the request to the proper gateway media capability."
)

_ROUTER_SYSTEM_PROMPT = (
    "You are routing a single assistant request. "
    "Choose the smallest correct execution mode. "
    "Return JSON only. "
    "Use mode=chat for ordinary answers, reasoning, browsing, tools, files, coding, or anything that should stay in the assistant agent. "
    "Use image, edit_image, upscale_image, video, image_to_video, music, or sound only for explicit media generation or transformation requests. "
    "If the request needs a source image for editing, upscaling, or image-to-video and no primary image is available, use mode=need_source_image. "
    "For chat, leave media_prompt empty and assistant_message empty. "
    "For media modes, assistant_message must be a short user-facing confirmation sentence and media_prompt must be the literal prompt to send to the media model. "
    "Do not use a top-level prompt key in place of media_prompt. "
    "For music and sound, set seconds to the clip length the user asked for, as a number of seconds; "
    "set seconds to null when the user named no length."
)

_ROUTER_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": [
                "chat",
                "image",
                "edit_image",
                "upscale_image",
                "video",
                "image_to_video",
                "music",
                "sound",
                "need_source_image",
            ],
        },
        "assistant_message": {"type": "string"},
        "media_prompt": {"type": "string"},
        "prompt": {"type": "string"},
        # The clip length is a typed argument the router fills (R10.1): no code
        # reads durations out of the prompt text.
        "seconds": {
            "type": ["number", "null"],
            "description": (
                "Length of the music or sound clip in seconds, as the user asked (a 3 s gunshot = 3). "
                "null when no length was named: sound effects then last 5 s, music 30 s."
            ),
        },
    },
    "required": ["mode", "assistant_message", "media_prompt"],
}

_ROUTER_TEMPLATE = (
    "Route this request for AbstractAssistant.\n"
    "User prompt:\n"
    "{{ prompt }}\n\n"
    "Primary image available: {{ has_primary_image_context }}\n"
)

_NEED_IMAGE_RESPONSE = (
    "Attach an image, then ask again. This request needs a source image for editing, upscaling, or image-to-video."
)

# Base output spec for the sound path. The client sends the same object (plus
# provider/model when the user set a local override). Modality is "sound", not
# "audio": the "audio" alias dispatches to the TTS engine registry at
# generation time (live 2026-07-28: a pinned sound provider was rejected as
# "Unknown tts_engine"), while "sound" routes to the sound-effects capability
# (abstractmusic/stable-audio class) that both honors a pinned provider/model
# and resolves the gateway's output.sound default when the spec is bare.
SOUND_OUTPUT_SPEC: Dict[str, Any] = {"modality": "sound", "task": "text_to_audio", "format": "wav"}

# Start-node input keys for per-run media model overrides. Every key is
# OPTIONAL: absent means the pin resolves to None, the media node leaves its
# output spec bare, and the gateway default applies (simple by default).
# When present, the pin value rides into the media node's provider/model
# inputs — the highest resolution rung — so THIS RUN uses the override
# without ever touching the gateway's own defaults.
MEDIA_OVERRIDE_INPUT_PINS = (
    "image_provider",
    "image_model",
    "image_edit_provider",
    "image_edit_model",
    "image_upscale_provider",
    "image_upscale_model",
    "video_provider",
    "video_model",
    "image_to_video_provider",
    "image_to_video_model",
    "music_provider",
    "music_model",
    "sound_output",
)


def _pin(pin_id: str, label: str, pin_type: str, description: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {"id": pin_id, "label": label, "type": pin_type}
    if description:
        out["description"] = description
    return out


def _node(
    node_id: str,
    node_type: str,
    *,
    x: float,
    y: float,
    label: str,
    icon: str,
    color: str,
    inputs: Optional[List[Dict[str, Any]]] = None,
    outputs: Optional[List[Dict[str, Any]]] = None,
    pin_defaults: Optional[Dict[str, Any]] = None,
    effect_config: Optional[Dict[str, Any]] = None,
    switch_config: Optional[Dict[str, Any]] = None,
    break_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "nodeType": node_type,
        "label": label,
        "icon": icon,
        "headerColor": color,
        "inputs": list(inputs or []),
        "outputs": list(outputs or []),
    }
    if pin_defaults:
        data["pinDefaults"] = dict(pin_defaults)
    if effect_config:
        data["effectConfig"] = dict(effect_config)
    if switch_config:
        data["switchConfig"] = dict(switch_config)
    if break_config:
        data["breakConfig"] = dict(break_config)
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": x, "y": y},
        "data": data,
        "label": None,
        "icon": None,
        "headerColor": None,
        "inputs": [],
        "outputs": [],
    }


def _edge(edge_id: str, source: str, source_handle: str, target: str, target_handle: str, *, animated: bool = False) -> Dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "sourceHandle": source_handle,
        "target": target,
        "targetHandle": target_handle,
        "animated": animated,
    }


def managed_assistant_visualflow() -> Dict[str, Any]:
    start = _node(
        "start",
        "on_flow_start",
        x=-960.0,
        y=0.0,
        label="On Flow Start",
        icon="&#x1F3C1;",
        color="#C0392B",
        outputs=[
            _pin("exec-out", "", "execution"),
            _pin("use_context", "use_context", "boolean"),
            _pin("context", "context", "object"),
            _pin("provider", "provider", "provider"),
            _pin("model", "model", "model"),
            _pin("system", "system", "string"),
            _pin("prompt", "prompt", "string"),
            _pin("tools", "tools", "tools"),
            _pin("max_iterations", "max_iterations", "number"),
            _pin("max_in_tokens", "max_in_tokens", "number"),
            _pin("temperature", "temperature", "number"),
            _pin("seed", "seed", "number"),
            _pin("resp_schema", "resp_schema", "object"),
            _pin("primary_image_artifact", "primary_image_artifact", "artifact_image"),
            _pin("has_primary_image_context", "has_primary_image_context", "boolean"),
            # Per-run media model overrides (all optional; absent = gateway default).
            _pin("image_provider", "image_provider", "string"),
            _pin("image_model", "image_model", "string"),
            _pin("image_edit_provider", "image_edit_provider", "string"),
            _pin("image_edit_model", "image_edit_model", "string"),
            _pin("image_upscale_provider", "image_upscale_provider", "string"),
            _pin("image_upscale_model", "image_upscale_model", "string"),
            _pin("video_provider", "video_provider", "string"),
            _pin("video_model", "video_model", "string"),
            _pin("image_to_video_provider", "image_to_video_provider", "string"),
            _pin("image_to_video_model", "image_to_video_model", "string"),
            _pin("music_provider", "music_provider", "string"),
            _pin("music_model", "music_model", "string"),
            _pin("sound_output", "sound_output", "object"),
        ],
        pin_defaults={
            "use_context": True,
            "system": _BASE_SYSTEM_PROMPT,
            # Automations and direct API callers do not necessarily supply the
            # chat client's selected tools. Declare this workflow's baseline,
            # as basic-agent does; explicit inputs (including []) override it.
            # Optional communications tools remain gated by the gateway.
            "tools": [
                "edit_file", "analyze_code", "execute_command", "fetch_url",
                "list_files", "read_file", "search_files", "web_search", "write_file",
            ],
            "max_iterations": 24,
            "temperature": 0.2,
            "seed": -1,
            "has_primary_image_context": False,
            # The sound node's output spec always arrives via this pin; the
            # default keeps the no-override run identical to the old static
            # node config (provider/model ride the same object when set).
            "sound_output": dict(SOUND_OUTPUT_SPEC),
        },
    )

    route_vars = _node(
        "route_vars",
        "make_object",
        x=-640.0,
        y=-120.0,
        label="Build Route Vars",
        icon="{}",
        color="#3498DB",
        inputs=[
            _pin("prompt", "prompt", "string"),
            _pin("has_primary_image_context", "has_primary_image_context", "boolean"),
        ],
        outputs=[_pin("result", "result", "object")],
    )

    route_prompt = _node(
        "route_prompt",
        "string_template",
        x=-360.0,
        y=-120.0,
        label="Route Prompt",
        icon="&#x1F9FE;",
        color="#E74C3C",
        inputs=[
            _pin("template", "template", "string"),
            _pin("vars", "vars", "object"),
        ],
        outputs=[_pin("result", "result", "string")],
        pin_defaults={"template": _ROUTER_TEMPLATE},
    )

    route_call = _node(
        "route_call",
        "llm_call",
        x=-80.0,
        y=-120.0,
        label="Route Request",
        icon="&#x1F4AD;",
        color="#3498DB",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("provider", "provider", "provider_text"),
            _pin("model", "model", "model"),
            _pin("system", "system", "string"),
            _pin("prompt", "prompt", "string"),
            _pin("resp_schema", "resp_schema", "object"),
            # DECLARED so they can be pinned shut. An llm_call node inherits every
            # same-named key of the previous exec node's output, and the node before
            # this one is `start`, whose output carries the agent's `tools` (30) and
            # `temperature` (0.2). Undeclared, the router ran with all 30 tool schemas
            # and AbstractCore's tools+structured TWO-PASS flow: an unstructured
            # tool-enabled generation first, then the structured one — 12-28 s per
            # turn for a routing decision (measured 2026-09-16, Qwen3.8-27B). A
            # declared pin's default outranks the inherited key.
            _pin("tools", "tools", "tools"),
            _pin("temperature", "temperature", "number"),
        ],
        outputs=[
            _pin("exec-out", "", "execution"),
            _pin("response", "response", "string"),
            _pin("data", "data", "object"),
            _pin("meta", "meta", "object"),
            _pin("success", "success", "boolean"),
        ],
        pin_defaults={
            "system": _ROUTER_SYSTEM_PROMPT,
            "resp_schema": _ROUTER_SCHEMA,
            "tools": [],
            "temperature": 0.0,
        },
        effect_config={"provider": "", "model": "", "temperature": 0.0, "structured_output_fallback": True},
    )

    route_break = _node(
        "route_break",
        "break_object",
        x=220.0,
        y=-120.0,
        label="Split Route",
        icon="&#x1F9E9;",
        color="#3498DB",
        inputs=[_pin("object", "object", "object")],
        outputs=[
            _pin("mode", "mode", "string"),
            _pin("assistant_message", "assistant_message", "string"),
            _pin("media_prompt", "media_prompt", "string"),
            _pin("prompt", "prompt", "string"),
            _pin("seconds", "seconds", "number"),
        ],
        break_config={"selectedPaths": ["mode", "assistant_message", "media_prompt", "prompt", "seconds"]},
    )

    route_media_prompt = _node(
        "route_media_prompt",
        "coalesce",
        x=500.0,
        y=40.0,
        label="Resolve Media Prompt",
        icon="&#x21C4;",
        color="#3498DB",
        inputs=[
            _pin("a", "a", "any"),
            _pin("b", "b", "any"),
        ],
        outputs=[_pin("result", "result", "any")],
    )

    route_switch = _node(
        "route_switch",
        "switch",
        x=500.0,
        y=-120.0,
        label="Route Mode",
        icon="&#x1F500;",
        color="#F39C12",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("value", "value", "string"),
        ],
        outputs=[
            _pin("case:chat", "chat", "execution"),
            _pin("case:image", "image", "execution"),
            _pin("case:edit_image", "edit_image", "execution"),
            _pin("case:upscale_image", "upscale_image", "execution"),
            _pin("case:video", "video", "execution"),
            _pin("case:image_to_video", "image_to_video", "execution"),
            _pin("case:music", "music", "execution"),
            _pin("case:sound", "sound", "execution"),
            _pin("case:need_source_image", "need_source_image", "execution"),
            _pin("default", "default", "execution"),
        ],
        switch_config={
            "cases": [
                {"id": "chat", "value": "chat"},
                {"id": "image", "value": "image"},
                {"id": "edit_image", "value": "edit_image"},
                {"id": "upscale_image", "value": "upscale_image"},
                {"id": "video", "value": "video"},
                {"id": "image_to_video", "value": "image_to_video"},
                {"id": "music", "value": "music"},
                {"id": "sound", "value": "sound"},
                {"id": "need_source_image", "value": "need_source_image"},
            ]
        },
    )

    agent = _node(
        "assistant_agent",
        "agent",
        x=820.0,
        y=-360.0,
        label="Assistant Agent",
        icon="&#x1F916;",
        color="#4488FF",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("use_context", "use_context", "boolean"),
            _pin("context", "context", "object"),
            _pin("provider", "provider", "provider"),
            _pin("model", "model", "model"),
            _pin("system", "system", "string"),
            _pin("prompt", "prompt", "string"),
            _pin("tools", "tools", "tools"),
            _pin("max_iterations", "max_iterations", "number"),
            _pin("max_in_tokens", "max_in_tokens", "number"),
            _pin("temperature", "temperature", "number"),
            _pin("seed", "seed", "number"),
            _pin("resp_schema", "resp_schema", "object"),
        ],
        outputs=[
            _pin("exec-out", "", "execution"),
            _pin("response", "response", "string"),
            _pin("success", "success", "boolean"),
            _pin("meta", "meta", "object"),
            _pin("scratchpad", "scratchpad", "object"),
        ],
        pin_defaults={
            "use_context": True,
            "system": _BASE_SYSTEM_PROMPT,
            "max_iterations": 24,
            "temperature": 0.2,
            "seed": -1,
        },
    )

    image = _node(
        "generate_image",
        "generate_image",
        x=820.0,
        y=-120.0,
        label="Generate Image",
        icon="&#x1F5BC;",
        color="#0EA5A4",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("prompt", "prompt", "string"),
            _pin("image_provider", "image_provider", "string"),
            _pin("image_model", "image_model", "string"),
        ],
        outputs=[
            _pin("exec-out", "", "execution"),
            _pin("image_artifact", "image_artifact", "artifact_image"),
            _pin("artifact_ref", "artifact_ref", "artifact"),
            _pin("artifact_id", "artifact_id", "string"),
            _pin("content_type", "content_type", "string"),
            _pin("outputs", "outputs", "object"),
            _pin("meta", "meta", "object"),
            _pin("success", "success", "boolean"),
        ],
    )

    edit_image = _node(
        "edit_image",
        "edit_image",
        x=820.0,
        y=120.0,
        label="Edit Image",
        icon="&#x1F58C;",
        color="#0EA5A4",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("prompt", "prompt", "string"),
            _pin("image_artifact", "image_artifact", "artifact_image"),
            _pin("image_provider", "image_provider", "string"),
            _pin("image_model", "image_model", "string"),
        ],
        outputs=[
            _pin("exec-out", "", "execution"),
            _pin("image_artifact", "image_artifact", "artifact_image"),
            _pin("artifact_ref", "artifact_ref", "artifact"),
            _pin("artifact_id", "artifact_id", "string"),
            _pin("content_type", "content_type", "string"),
            _pin("outputs", "outputs", "object"),
            _pin("meta", "meta", "object"),
            _pin("success", "success", "boolean"),
        ],
    )

    upscale_image = _node(
        "upscale_image",
        "upscale_image",
        x=820.0,
        y=360.0,
        label="Restore / Upscale Image",
        icon="&#x1F50D;",
        color="#0EA5A4",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("image_artifact", "image_artifact", "artifact_image"),
            _pin("image_provider", "image_provider", "string"),
            _pin("image_model", "image_model", "string"),
        ],
        outputs=[
            _pin("exec-out", "", "execution"),
            _pin("image_artifact", "image_artifact", "artifact_image"),
            _pin("artifact_ref", "artifact_ref", "artifact"),
            _pin("artifact_id", "artifact_id", "string"),
            _pin("content_type", "content_type", "string"),
            _pin("outputs", "outputs", "object"),
            _pin("meta", "meta", "object"),
            _pin("success", "success", "boolean"),
        ],
    )

    video = _node(
        "generate_video",
        "generate_video",
        x=820.0,
        y=600.0,
        label="Generate Video",
        icon="&#x1F3AC;",
        color="#0EA5A4",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("prompt", "prompt", "string"),
            _pin("video_provider", "video_provider", "string"),
            _pin("video_model", "video_model", "string"),
        ],
        outputs=[
            _pin("exec-out", "", "execution"),
            _pin("video_artifact", "video_artifact", "artifact_video"),
            _pin("artifact_ref", "artifact_ref", "artifact"),
            _pin("artifact_id", "artifact_id", "string"),
            _pin("content_type", "content_type", "string"),
            _pin("outputs", "outputs", "object"),
            _pin("meta", "meta", "object"),
            _pin("success", "success", "boolean"),
        ],
    )

    image_to_video = _node(
        "image_to_video",
        "image_to_video",
        x=820.0,
        y=840.0,
        label="Image To Video",
        icon="&#x1F39E;",
        color="#0EA5A4",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("prompt", "prompt", "string"),
            _pin("source_image", "source_image", "artifact_image"),
            _pin("video_provider", "video_provider", "string"),
            _pin("video_model", "video_model", "string"),
        ],
        outputs=[
            _pin("exec-out", "", "execution"),
            _pin("video_artifact", "video_artifact", "artifact_video"),
            _pin("artifact_ref", "artifact_ref", "artifact"),
            _pin("artifact_id", "artifact_id", "string"),
            _pin("content_type", "content_type", "string"),
            _pin("outputs", "outputs", "object"),
            _pin("meta", "meta", "object"),
            _pin("success", "success", "boolean"),
        ],
    )

    music = _node(
        "generate_music",
        "generate_music",
        x=820.0,
        y=1080.0,
        label="Generate Music",
        icon="&#x1F3B5;",
        color="#0EA5A4",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("prompt", "prompt", "string"),
            _pin("music_provider", "music_provider", "string"),
            _pin("music_model", "music_model", "string"),
            _pin("duration_s", "duration_s", "number"),
        ],
        outputs=[
            _pin("exec-out", "", "execution"),
            _pin("music_artifact", "music_artifact", "artifact_audio"),
            _pin("audio_artifact", "audio_artifact", "artifact_audio"),
            _pin("artifact_ref", "artifact_ref", "artifact"),
            _pin("artifact_id", "artifact_id", "string"),
            _pin("content_type", "content_type", "string"),
            _pin("outputs", "outputs", "object"),
            _pin("meta", "meta", "object"),
            _pin("success", "success", "boolean"),
        ],
    )

    sound = _node(
        "generate_sound",
        "llm_call",
        x=820.0,
        y=1320.0,
        label="Generate Sound",
        icon="&#x1F50A;",
        color="#3498DB",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("prompt", "prompt", "string"),
            _pin("output", "output", "object"),
        ],
        outputs=[
            _pin("exec-out", "", "execution"),
            _pin("response", "response", "string"),
            _pin("artifact_ref", "artifact_ref", "artifact"),
            _pin("artifact_id", "artifact_id", "string"),
            _pin("audio_artifact", "audio_artifact", "artifact_audio"),
            _pin("outputs", "outputs", "object"),
            _pin("resources", "resources", "object"),
            _pin("meta", "meta", "object"),
            _pin("success", "success", "boolean"),
        ],
        # The connected start.sound_output edge always delivers the spec (the
        # start pin has the same default); this node-local default remains as
        # a safety net for older stored copies of the flow.
        pin_defaults={"output": dict(SOUND_OUTPUT_SPEC)},
        effect_config={"provider": "", "model": "", "temperature": 0.2},
    )

    # The sound node's output spec = the start pin's spec + the router's clip length
    # (`duration_s`; None when the user named none, so the engine's 5 s default applies).
    sound_spec = _node(
        "sound_spec",
        "set",
        x=560.0,
        y=1320.0,
        label="Sound Length",
        icon="{}",
        color="#3498DB",
        inputs=[
            _pin("object", "object", "object"),
            _pin("key", "key", "string"),
            _pin("value", "value", "any"),
        ],
        outputs=[_pin("result", "result", "object")],
        pin_defaults={"key": "duration_s"},
    )

    need_image_message = _node(
        "need_image_message",
        "string_template",
        x=820.0,
        y=1560.0,
        label="Need Source Image",
        icon="&#x1F9FE;",
        color="#E74C3C",
        inputs=[_pin("template", "template", "string")],
        outputs=[_pin("result", "result", "string")],
        pin_defaults={"template": _NEED_IMAGE_RESPONSE},
    )

    end_chat = _node(
        "end_chat",
        "on_flow_end",
        x=1180.0,
        y=-360.0,
        label="On Flow End",
        icon="&#x23F9;",
        color="#C0392B",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("response", "response", "string"),
            _pin("success", "success", "boolean"),
            _pin("meta", "meta", "object"),
            _pin("scratchpad", "scratchpad", "object"),
        ],
    )

    def _media_end(node_id: str, y: float, extra_inputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        return _node(
            node_id,
            "on_flow_end",
            x=1180.0,
            y=y,
            label="On Flow End",
            icon="&#x23F9;",
            color="#C0392B",
            inputs=[
                _pin("exec-in", "", "execution"),
                _pin("response", "response", "string"),
                _pin("success", "success", "boolean"),
                _pin("meta", "meta", "object"),
                _pin("artifact", "artifact", "artifact"),
                _pin("artifact_id", "artifact_id", "string"),
                _pin("content_type", "content_type", "string"),
                _pin("outputs", "outputs", "object"),
                _pin("resources", "resources", "object"),
                *extra_inputs,
            ],
        )

    end_image = _media_end("end_image", -120.0, [_pin("image_artifact", "image_artifact", "artifact_image")])
    end_edit = _media_end("end_edit", 120.0, [_pin("image_artifact", "image_artifact", "artifact_image")])
    end_upscale = _media_end("end_upscale", 360.0, [_pin("image_artifact", "image_artifact", "artifact_image")])
    end_video = _media_end("end_video", 600.0, [_pin("video_artifact", "video_artifact", "artifact_video")])
    end_image_to_video = _media_end("end_image_to_video", 840.0, [_pin("video_artifact", "video_artifact", "artifact_video")])
    end_music = _media_end(
        "end_music",
        1080.0,
        [
            _pin("music_artifact", "music_artifact", "artifact_audio"),
            _pin("audio_artifact", "audio_artifact", "artifact_audio"),
        ],
    )
    end_sound = _media_end("end_sound", 1320.0, [_pin("audio_artifact", "audio_artifact", "artifact_audio")])
    end_need_image = _node(
        "end_need_image",
        "on_flow_end",
        x=1180.0,
        y=1560.0,
        label="On Flow End",
        icon="&#x23F9;",
        color="#C0392B",
        inputs=[
            _pin("exec-in", "", "execution"),
            _pin("response", "response", "string"),
            _pin("success", "success", "boolean"),
        ],
        pin_defaults={"success": True},
    )

    nodes = [
        start,
        route_vars,
        route_prompt,
        route_call,
        route_break,
        route_media_prompt,
        route_switch,
        agent,
        image,
        edit_image,
        upscale_image,
        video,
        image_to_video,
        music,
        sound,
        sound_spec,
        need_image_message,
        end_chat,
        end_image,
        end_edit,
        end_upscale,
        end_video,
        end_image_to_video,
        end_music,
        end_sound,
        end_need_image,
    ]

    edges = [
        _edge("start-route-vars-prompt", "start", "prompt", "route_vars", "prompt"),
        _edge("start-route-vars-image", "start", "has_primary_image_context", "route_vars", "has_primary_image_context"),
        _edge("route-vars-prompt-vars", "route_vars", "result", "route_prompt", "vars"),
        _edge("route-prompt-to-call", "route_prompt", "result", "route_call", "prompt"),
        _edge("start-to-route-call", "start", "exec-out", "route_call", "exec-in", animated=True),
        _edge("route-call-to-break", "route_call", "data", "route_break", "object"),
        _edge("route-call-to-switch-exec", "route_call", "exec-out", "route_switch", "exec-in", animated=True),
        _edge("route-break-to-switch-value", "route_break", "mode", "route_switch", "value"),
        _edge("route-break-media-prompt-primary", "route_break", "media_prompt", "route_media_prompt", "a"),
        _edge("route-break-media-prompt-fallback", "route_break", "prompt", "route_media_prompt", "b"),
        _edge("switch-chat", "route_switch", "case:chat", "assistant_agent", "exec-in", animated=True),
        _edge("start-agent-use-context", "start", "use_context", "assistant_agent", "use_context"),
        _edge("start-agent-context", "start", "context", "assistant_agent", "context"),
        _edge("start-agent-provider", "start", "provider", "assistant_agent", "provider"),
        _edge("start-agent-model", "start", "model", "assistant_agent", "model"),
        _edge("start-agent-system", "start", "system", "assistant_agent", "system"),
        _edge("start-agent-prompt", "start", "prompt", "assistant_agent", "prompt"),
        _edge("start-agent-tools", "start", "tools", "assistant_agent", "tools"),
        _edge("start-agent-max-iterations", "start", "max_iterations", "assistant_agent", "max_iterations"),
        _edge("start-agent-max-in-tokens", "start", "max_in_tokens", "assistant_agent", "max_in_tokens"),
        _edge("start-agent-temperature", "start", "temperature", "assistant_agent", "temperature"),
        _edge("start-agent-seed", "start", "seed", "assistant_agent", "seed"),
        _edge("start-agent-resp-schema", "start", "resp_schema", "assistant_agent", "resp_schema"),
        _edge("agent-end-exec", "assistant_agent", "exec-out", "end_chat", "exec-in", animated=True),
        _edge("agent-end-response", "assistant_agent", "response", "end_chat", "response"),
        _edge("agent-end-success", "assistant_agent", "success", "end_chat", "success"),
        _edge("agent-end-meta", "assistant_agent", "meta", "end_chat", "meta"),
        _edge("agent-end-scratchpad", "assistant_agent", "scratchpad", "end_chat", "scratchpad"),
        _edge("switch-image", "route_switch", "case:image", "generate_image", "exec-in", animated=True),
        _edge("route-break-image-prompt", "route_media_prompt", "result", "generate_image", "prompt"),
        _edge("start-image-provider", "start", "image_provider", "generate_image", "image_provider"),
        _edge("start-image-model", "start", "image_model", "generate_image", "image_model"),
        _edge("image-end-exec", "generate_image", "exec-out", "end_image", "exec-in", animated=True),
        _edge("route-break-image-response", "route_break", "assistant_message", "end_image", "response"),
        _edge("image-end-success", "generate_image", "success", "end_image", "success"),
        _edge("image-end-meta", "generate_image", "meta", "end_image", "meta"),
        _edge("image-end-artifact", "generate_image", "artifact_ref", "end_image", "artifact"),
        _edge("image-end-image-artifact", "generate_image", "image_artifact", "end_image", "image_artifact"),
        _edge("image-end-artifact-id", "generate_image", "artifact_id", "end_image", "artifact_id"),
        _edge("image-end-content-type", "generate_image", "content_type", "end_image", "content_type"),
        _edge("image-end-outputs", "generate_image", "outputs", "end_image", "outputs"),
        _edge("switch-edit", "route_switch", "case:edit_image", "edit_image", "exec-in", animated=True),
        _edge("route-break-edit-prompt", "route_media_prompt", "result", "edit_image", "prompt"),
        _edge("start-edit-source", "start", "primary_image_artifact", "edit_image", "image_artifact"),
        _edge("start-edit-provider", "start", "image_edit_provider", "edit_image", "image_provider"),
        _edge("start-edit-model", "start", "image_edit_model", "edit_image", "image_model"),
        _edge("edit-end-exec", "edit_image", "exec-out", "end_edit", "exec-in", animated=True),
        _edge("route-break-edit-response", "route_break", "assistant_message", "end_edit", "response"),
        _edge("edit-end-success", "edit_image", "success", "end_edit", "success"),
        _edge("edit-end-meta", "edit_image", "meta", "end_edit", "meta"),
        _edge("edit-end-artifact", "edit_image", "artifact_ref", "end_edit", "artifact"),
        _edge("edit-end-image-artifact", "edit_image", "image_artifact", "end_edit", "image_artifact"),
        _edge("edit-end-artifact-id", "edit_image", "artifact_id", "end_edit", "artifact_id"),
        _edge("edit-end-content-type", "edit_image", "content_type", "end_edit", "content_type"),
        _edge("edit-end-outputs", "edit_image", "outputs", "end_edit", "outputs"),
        _edge("switch-upscale", "route_switch", "case:upscale_image", "upscale_image", "exec-in", animated=True),
        _edge("start-upscale-source", "start", "primary_image_artifact", "upscale_image", "image_artifact"),
        _edge("start-upscale-provider", "start", "image_upscale_provider", "upscale_image", "image_provider"),
        _edge("start-upscale-model", "start", "image_upscale_model", "upscale_image", "image_model"),
        _edge("upscale-end-exec", "upscale_image", "exec-out", "end_upscale", "exec-in", animated=True),
        _edge("route-break-upscale-response", "route_break", "assistant_message", "end_upscale", "response"),
        _edge("upscale-end-success", "upscale_image", "success", "end_upscale", "success"),
        _edge("upscale-end-meta", "upscale_image", "meta", "end_upscale", "meta"),
        _edge("upscale-end-artifact", "upscale_image", "artifact_ref", "end_upscale", "artifact"),
        _edge("upscale-end-image-artifact", "upscale_image", "image_artifact", "end_upscale", "image_artifact"),
        _edge("upscale-end-artifact-id", "upscale_image", "artifact_id", "end_upscale", "artifact_id"),
        _edge("upscale-end-content-type", "upscale_image", "content_type", "end_upscale", "content_type"),
        _edge("upscale-end-outputs", "upscale_image", "outputs", "end_upscale", "outputs"),
        _edge("switch-video", "route_switch", "case:video", "generate_video", "exec-in", animated=True),
        _edge("route-break-video-prompt", "route_media_prompt", "result", "generate_video", "prompt"),
        _edge("start-video-provider", "start", "video_provider", "generate_video", "video_provider"),
        _edge("start-video-model", "start", "video_model", "generate_video", "video_model"),
        _edge("video-end-exec", "generate_video", "exec-out", "end_video", "exec-in", animated=True),
        _edge("route-break-video-response", "route_break", "assistant_message", "end_video", "response"),
        _edge("video-end-success", "generate_video", "success", "end_video", "success"),
        _edge("video-end-meta", "generate_video", "meta", "end_video", "meta"),
        _edge("video-end-artifact", "generate_video", "artifact_ref", "end_video", "artifact"),
        _edge("video-end-video-artifact", "generate_video", "video_artifact", "end_video", "video_artifact"),
        _edge("video-end-artifact-id", "generate_video", "artifact_id", "end_video", "artifact_id"),
        _edge("video-end-content-type", "generate_video", "content_type", "end_video", "content_type"),
        _edge("video-end-outputs", "generate_video", "outputs", "end_video", "outputs"),
        _edge("switch-image-to-video", "route_switch", "case:image_to_video", "image_to_video", "exec-in", animated=True),
        _edge("route-break-image-to-video-prompt", "route_media_prompt", "result", "image_to_video", "prompt"),
        _edge("start-image-to-video-source", "start", "primary_image_artifact", "image_to_video", "source_image"),
        _edge("start-image-to-video-provider", "start", "image_to_video_provider", "image_to_video", "video_provider"),
        _edge("start-image-to-video-model", "start", "image_to_video_model", "image_to_video", "video_model"),
        _edge("image-to-video-end-exec", "image_to_video", "exec-out", "end_image_to_video", "exec-in", animated=True),
        _edge("route-break-image-to-video-response", "route_break", "assistant_message", "end_image_to_video", "response"),
        _edge("image-to-video-end-success", "image_to_video", "success", "end_image_to_video", "success"),
        _edge("image-to-video-end-meta", "image_to_video", "meta", "end_image_to_video", "meta"),
        _edge("image-to-video-end-artifact", "image_to_video", "artifact_ref", "end_image_to_video", "artifact"),
        _edge("image-to-video-end-video-artifact", "image_to_video", "video_artifact", "end_image_to_video", "video_artifact"),
        _edge("image-to-video-end-artifact-id", "image_to_video", "artifact_id", "end_image_to_video", "artifact_id"),
        _edge("image-to-video-end-content-type", "image_to_video", "content_type", "end_image_to_video", "content_type"),
        _edge("image-to-video-end-outputs", "image_to_video", "outputs", "end_image_to_video", "outputs"),
        _edge("switch-music", "route_switch", "case:music", "generate_music", "exec-in", animated=True),
        _edge("route-break-music-prompt", "route_media_prompt", "result", "generate_music", "prompt"),
        _edge("start-music-provider", "start", "music_provider", "generate_music", "music_provider"),
        _edge("start-music-model", "start", "music_model", "generate_music", "music_model"),
        _edge("route-break-music-seconds", "route_break", "seconds", "generate_music", "duration_s"),
        _edge("music-end-exec", "generate_music", "exec-out", "end_music", "exec-in", animated=True),
        _edge("route-break-music-response", "route_break", "assistant_message", "end_music", "response"),
        _edge("music-end-success", "generate_music", "success", "end_music", "success"),
        _edge("music-end-meta", "generate_music", "meta", "end_music", "meta"),
        _edge("music-end-artifact", "generate_music", "artifact_ref", "end_music", "artifact"),
        _edge("music-end-music-artifact", "generate_music", "music_artifact", "end_music", "music_artifact"),
        _edge("music-end-audio-artifact", "generate_music", "audio_artifact", "end_music", "audio_artifact"),
        _edge("music-end-artifact-id", "generate_music", "artifact_id", "end_music", "artifact_id"),
        _edge("music-end-content-type", "generate_music", "content_type", "end_music", "content_type"),
        _edge("music-end-outputs", "generate_music", "outputs", "end_music", "outputs"),
        _edge("switch-sound", "route_switch", "case:sound", "generate_sound", "exec-in", animated=True),
        _edge("route-break-sound-prompt", "route_media_prompt", "result", "generate_sound", "prompt"),
        _edge("start-sound-output", "start", "sound_output", "sound_spec", "object"),
        _edge("route-break-sound-seconds", "route_break", "seconds", "sound_spec", "value"),
        _edge("sound-spec-output", "sound_spec", "result", "generate_sound", "output"),
        _edge("sound-end-exec", "generate_sound", "exec-out", "end_sound", "exec-in", animated=True),
        _edge("route-break-sound-response", "route_break", "assistant_message", "end_sound", "response"),
        _edge("sound-end-success", "generate_sound", "success", "end_sound", "success"),
        _edge("sound-end-meta", "generate_sound", "meta", "end_sound", "meta"),
        _edge("sound-end-artifact", "generate_sound", "artifact_ref", "end_sound", "artifact"),
        _edge("sound-end-audio-artifact", "generate_sound", "audio_artifact", "end_sound", "audio_artifact"),
        _edge("sound-end-artifact-id", "generate_sound", "artifact_id", "end_sound", "artifact_id"),
        _edge("sound-end-outputs", "generate_sound", "outputs", "end_sound", "outputs"),
        _edge("sound-end-resources", "generate_sound", "resources", "end_sound", "resources"),
        _edge("switch-need-image-default", "route_switch", "case:need_source_image", "end_need_image", "exec-in", animated=True),
        _edge("need-image-message-end", "need_image_message", "result", "end_need_image", "response"),
        _edge("switch-default", "route_switch", "default", "assistant_agent", "exec-in", animated=True),
    ]

    return {
        "name": MANAGED_ASSISTANT_WORKFLOW_NAME,
        "description": (
            "Canonical catalog workflow for the compact AbstractAssistant tray surface. "
            f"{MANAGED_ASSISTANT_WORKFLOW_MARKER};"
            f"{_REVISION_MARKER_PREFIX}{MANAGED_ASSISTANT_WORKFLOW_REVISION}"
        ),
        "interfaces": [ASSISTANT_INTERFACE],
        "nodes": nodes,
        "edges": edges,
        "entryNode": "start",
    }


def normalized_managed_visualflow() -> Dict[str, Any]:
    payload = managed_assistant_visualflow()
    return {
        "name": payload["name"],
        "description": payload["description"],
        "interfaces": list(payload["interfaces"]),
        "nodes": list(payload["nodes"]),
        "edges": list(payload["edges"]),
        "entryNode": payload["entryNode"],
    }
