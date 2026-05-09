"""Helpers for Gateway-backed generated media turns."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Dict, List, Optional


_SAFE_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_SESSION_MEMORY_RUN_PREFIX = "session_memory_"

_IMAGE_OBJECT_RE = re.compile(
    r"\b(image|picture|pic|photo|illustration|drawing|artwork|poster|wallpaper|logo|icon|avatar|sticker)\b",
    flags=re.I,
)
_DIRECT_IMAGE_ACTION_RE = re.compile(
    r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
    r"(?:draw|paint|illustrate)\s+"
    r"(?!(?:a\s+)?(?:conclusion|comparison|distinction)\b)"
    r"(?!(?:the\s+)?(?:button|component|widget|view|element)\b)",
    flags=re.I,
)
_ACTION_IMAGE_OBJECT_RE = re.compile(
    r"\b(?:generate|create|make|design)\s+(?:me\s+)?(?:(?:an?|the)\s+)?"
    r"(?:(?:[\w'-]+)\s+){0,3}"
    r"(?:image|picture|pic|photo|illustration|drawing|artwork|poster|wallpaper|logo|icon|avatar|sticker)\b"
    r"(?!\s+(?:button|component|widget|view|tag|element|field|input|upload|gallery|viewer|class|function|script|tool|parser|endpoint|api|file|path|url|metadata|prompt|model))",
    flags=re.I,
)
_SHOW_ME_IMAGE_RE = re.compile(
    r"\bshow\s+me\s+(?:(?:an?|the)\s+)?(?:(?:[\w'-]+)\s+){0,3}"
    r"(?:image|picture|pic|photo|illustration|drawing|artwork|poster|wallpaper|logo|icon|avatar|sticker)\b",
    flags=re.I,
)
_QUESTION_ABOUT_IMAGES_RE = re.compile(
    r"^\s*(how|what|why|when|where|explain|tell\s+me|help\s+me\s+understand)\b",
    flags=re.I,
)
_COMMAND_RE = re.compile(r"^\s*/(?:image|img|imagine|generate-image)\b(?:\s+|:|-)*(?P<prompt>.*)$", flags=re.I | re.S)
_SIZE_RE = re.compile(r"\b(?P<w>[1-9][0-9]{1,4})\s*[xX]\s*(?P<h>[1-9][0-9]{1,4})\b")


@dataclass(frozen=True)
class ImageGenerationIntent:
    """Parsed image-generation request from a chat turn."""

    prompt: str
    format: str = "png"
    size: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


def session_memory_run_id(session_id: str) -> str:
    """Mirror Gateway's stable session-memory run id for direct media artifacts."""

    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("session_id is required")
    if _SAFE_RUN_ID_PATTERN.match(sid):
        rid = f"{_SESSION_MEMORY_RUN_PREFIX}{sid}"
        if _SAFE_RUN_ID_PATTERN.match(rid):
            return rid
    digest = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:32]
    return f"{_SESSION_MEMORY_RUN_PREFIX}sha_{digest}"


def parse_image_generation_intent(text: str) -> Optional[ImageGenerationIntent]:
    """Return an intent for explicit image-generation requests, else None."""

    raw = str(text or "").strip()
    if not raw:
        return None

    command = _COMMAND_RE.match(raw)
    if command:
        prompt = _clean_image_prompt(command.group("prompt") or raw)
        if not prompt:
            return None
        return _intent_from_prompt(prompt, source_text=raw)

    if _QUESTION_ABOUT_IMAGES_RE.match(raw):
        return None

    has_image_object = bool(_IMAGE_OBJECT_RE.search(raw))
    has_direct_image_action = bool(_DIRECT_IMAGE_ACTION_RE.search(raw))
    has_image_action_object = bool(_ACTION_IMAGE_OBJECT_RE.search(raw))
    show_me_image = bool(_SHOW_ME_IMAGE_RE.search(raw) and has_image_object)
    if not (has_direct_image_action or has_image_action_object or show_me_image):
        return None

    prompt = _clean_image_prompt(raw)
    return _intent_from_prompt(prompt or raw, source_text=raw)


def choose_generated_image_format(intent: ImageGenerationIntent, supported_formats: List[str]) -> str:
    """Pick the requested image format if supported, otherwise prefer png."""

    supported = [str(x or "").strip().lower() for x in (supported_formats or []) if str(x or "").strip()]
    if not supported:
        supported = ["png"]

    requested = str(intent.format or "png").strip().lower() or "png"
    aliases = {"jpg": "jpeg"}
    requested = aliases.get(requested, requested)
    if requested in supported:
        return requested
    if requested == "jpeg" and "jpg" in supported:
        return "jpg"
    if "png" in supported:
        return "png"
    return supported[0]


def build_generated_image_assistant_message(
    *,
    run_id: str,
    prompt: str,
    response: Dict[str, Any],
    provider: str = "",
    model: str = "",
    fmt: str = "png",
) -> Optional[Dict[str, Any]]:
    """Build a persisted assistant message that the transcript renderer can thumbnail."""

    if not isinstance(response, dict):
        return None
    image_artifact = response.get("image_artifact")
    if not isinstance(image_artifact, dict):
        return None
    artifact_id = str(image_artifact.get("$artifact") or image_artifact.get("artifact_id") or "").strip()
    if not artifact_id:
        return None

    rid = str(run_id or response.get("run_id") or "").strip()
    prompt_s = str(prompt or "").strip()
    request_id = str(response.get("request_id") or "").strip()

    generated_media: Dict[str, Any] = {
        "run_id": rid,
        "request_id": request_id,
        "prompt": prompt_s,
        "provider": str(provider or "").strip() or None,
        "model": str(model or "").strip() or None,
        "format": str(fmt or "png").strip().lower() or "png",
        "image_artifact": dict(image_artifact),
    }
    generated_media = {k: v for k, v in generated_media.items() if v is not None and v != ""}

    return {
        "role": "assistant",
        "content": generated_image_message_content(prompt_s),
        "metadata": {
            "kind": "generated_image",
            "run_id": rid,
            "image_artifact": dict(image_artifact),
            "generated_media": generated_media,
        },
    }


def generated_image_message_content(prompt: str, *, max_prompt_chars: int = 160) -> str:
    prompt_s = " ".join(str(prompt or "").strip().split())
    if not prompt_s:
        return "Generated image."
    if len(prompt_s) > int(max_prompt_chars):
        prompt_s = prompt_s[: max(0, int(max_prompt_chars) - 1)].rstrip() + "..."
    return f"Generated image: {prompt_s}"


def _intent_from_prompt(prompt: str, *, source_text: str) -> Optional[ImageGenerationIntent]:
    prompt_s = str(prompt or "").strip()
    if not prompt_s:
        return None

    fmt = "png"
    src = str(source_text or "")
    if re.search(r"\bwebp\b", src, flags=re.I):
        fmt = "webp"
    elif re.search(r"\b(?:jpe?g|jpg)\b", src, flags=re.I):
        fmt = "jpeg"

    width: Optional[int] = None
    height: Optional[int] = None
    size: Optional[str] = None
    m = _SIZE_RE.search(src)
    if m:
        try:
            w = int(m.group("w"))
            h = int(m.group("h"))
            if 1 <= w <= 8192 and 1 <= h <= 8192:
                width = w
                height = h
                size = f"{w}x{h}"
        except Exception:
            width = None
            height = None
            size = None

    return ImageGenerationIntent(prompt=prompt_s, format=fmt, size=size, width=width, height=height)


def _clean_image_prompt(text: str) -> str:
    prompt = str(text or "").strip()
    if not prompt:
        return ""

    prompt = re.sub(r"^\s*(please\s+)?(?:can|could|would)\s+you\s+", "", prompt, flags=re.I)
    prompt = re.sub(r"^\s*please\s+", "", prompt, flags=re.I)
    prompt = re.sub(
        r"^\s*(?:generate|create|make|design|draw|render|paint|illustrate)\s+(?:me\s+)?",
        "",
        prompt,
        flags=re.I,
    )
    prompt = re.sub(r"^\s*show\s+me\s+", "", prompt, flags=re.I)
    prompt = re.sub(
        r"^\s*(?:an?|the)?\s*(?:image|picture|pic|photo|illustration|drawing|artwork|poster|wallpaper|logo|icon|avatar|sticker)\s*(?:of|for|showing|with)?\s+",
        "",
        prompt,
        flags=re.I,
    )
    prompt = re.sub(r"^\s*(?:of|for|showing|with)\s+", "", prompt, flags=re.I)
    return prompt.strip(" \t\r\n:.-")
