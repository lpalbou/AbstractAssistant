"""Assistant-side view of the Gateway thin-client capability contract."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import time
import warnings
from typing import Any, Dict, List, Optional


AGENT_INTERFACE_PREFERENCE = (
    "abstractassistant.agent.v1",
    "abstract.agent.v1",
    "abstractcode.agent.v1",
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list_of_strings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _dig(obj: Dict[str, Any], *path: str) -> Any:
    cur: Any = obj
    for part in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


@dataclass
class AssistantCapabilities:
    """Parsed `capabilities.contracts.assistant` with conservative helpers."""

    raw: Dict[str, Any] = field(default_factory=dict)
    assistant: Dict[str, Any] = field(default_factory=dict)
    common: Dict[str, Any] = field(default_factory=dict)
    version: int = 0
    fetched_at: float = 0.0
    error: str = ""

    @classmethod
    def from_discovery_response(cls, response: Dict[str, Any], *, fetched_at: Optional[float] = None) -> "AssistantCapabilities":
        caps = _as_dict(response.get("capabilities")) if isinstance(response, dict) else {}
        contracts = _as_dict(caps.get("contracts"))
        version = 0
        try:
            version = int(contracts.get("version") or 0)
        except Exception:
            version = 0
        return cls(
            raw=caps,
            assistant=_as_dict(contracts.get("assistant")),
            common=_as_dict(contracts.get("common")),
            version=version,
            fetched_at=float(fetched_at if fetched_at is not None else time.monotonic()),
        )

    @classmethod
    def unavailable(cls, *, error: str = "") -> "AssistantCapabilities":
        return cls(error=str(error or ""), fetched_at=time.monotonic())

    def contract_loaded(self) -> bool:
        return bool(self.version >= 1 and self.assistant)

    def tts(self) -> Dict[str, Any]:
        return _as_dict(_dig(self.assistant, "voice", "tts"))

    def stt(self) -> Dict[str, Any]:
        return _as_dict(_dig(self.assistant, "voice", "stt"))

    def tts_available(self) -> bool:
        return bool(self.tts().get("available"))

    def stt_available(self) -> bool:
        return bool(self.stt().get("available"))

    def tts_formats(self) -> List[str]:
        formats = _as_list_of_strings(self.tts().get("formats"))
        return formats or ["wav"]

    def tts_models_endpoint(self) -> str:
        endpoint = self.tts().get("models_endpoint")
        return str(endpoint or "").strip() if isinstance(endpoint, str) else ""

    def stt_models_endpoint(self) -> str:
        endpoint = self.stt().get("models_endpoint")
        return str(endpoint or "").strip() if isinstance(endpoint, str) else ""

    def tts_catalog_endpoint(self) -> str:
        endpoint = self.tts().get("catalog_endpoint")
        return str(endpoint or "").strip() if isinstance(endpoint, str) else ""

    def selected_tts_model(self) -> Optional[str]:
        preferred = str(
            os.getenv("ABSTRACTASSISTANT_GATEWAY_TTS_MODEL")
            or os.getenv("ABSTRACTASSISTANT_TTS_MODEL")
            or ""
        ).strip()
        if preferred:
            return preferred
        for key in ("active_model", "selected_model", "default_model", "model"):
            value = self.tts().get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def preferred_tts_format(self) -> str:
        formats = [f.lower() for f in self.tts_formats()]
        if "wav" in formats:
            return "wav"
        return formats[0] if formats else "wav"

    def tts_content_type(self, fmt: str) -> str:
        content_types = self.tts().get("content_types")
        if isinstance(content_types, dict):
            value = content_types.get(str(fmt or "").strip().lower())
            if isinstance(value, str) and value.strip():
                return value.strip()
        f = str(fmt or "").strip().lower()
        if f in {"mp3", "mpeg"}:
            return "audio/mpeg"
        if f in {"wav", "wave"}:
            return "audio/wav"
        return "application/octet-stream"

    def tts_voices(self) -> List[Dict[str, Any]]:
        voices = self.tts().get("voices")
        if not isinstance(voices, list):
            return []
        out: List[Dict[str, Any]] = []
        for voice in voices:
            if isinstance(voice, dict) and str(voice.get("id") or "").strip():
                out.append(dict(voice))
        return out

    def selected_tts_voice(self) -> Optional[str]:
        preferred = str(
            os.getenv("ABSTRACTASSISTANT_GATEWAY_TTS_VOICE")
            or os.getenv("ABSTRACTASSISTANT_TTS_VOICE")
            or ""
        ).strip()
        if not preferred:
            return None
        voices = self.tts_voices()
        if not voices:
            return preferred
        ids = {
            str(v.get("id") or "").strip()
            for v in voices
            if str(v.get("id") or "").strip()
        }
        ids.update(
            str(v.get("qualified_id") or "").strip()
            for v in voices
            if str(v.get("qualified_id") or "").strip()
        )
        if preferred in ids:
            return preferred
        warnings.warn(f"#FALLBACK: configured TTS voice '{preferred}' is not advertised by the gateway")
        return None

    def stt_content_types(self) -> List[str]:
        return _as_list_of_strings(self.stt().get("content_types"))

    def selected_stt_model(self) -> Optional[str]:
        preferred = str(
            os.getenv("ABSTRACTASSISTANT_GATEWAY_STT_MODEL")
            or os.getenv("ABSTRACTASSISTANT_STT_MODEL")
            or ""
        ).strip()
        if preferred:
            return preferred
        for key in ("active_model", "selected_model", "default_model", "model"):
            value = self.stt().get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def stt_upload_content_type_for_wav(self) -> str:
        content_types = [ct.lower() for ct in self.stt_content_types()]
        if not content_types or "audio/wav" in content_types:
            return "audio/wav"
        if "application/octet-stream" in content_types:
            return "application/octet-stream"
        return ""

    def stt_max_upload_bytes(self) -> int:
        raw = self.stt().get("max_upload_bytes")
        try:
            value = int(raw or 0)
        except Exception:
            return 0
        return max(0, value)

    def artifact_content_available(self) -> bool:
        item = _as_dict(_dig(self.assistant, "artifacts", "content"))
        if "available" in item:
            return bool(item.get("available"))
        endpoint = str(item.get("endpoint") or "").strip()
        return bool(endpoint)

    def session_prompt_cache_available(self) -> bool:
        pc = _as_dict(self.assistant.get("prompt_cache"))
        return bool(pc.get("session_lifecycle"))

    def _media_entry(self, key: str) -> Dict[str, Any]:
        return _as_dict(_dig(self.assistant, "media", key))

    def _direct_media_entry(self, key: str) -> Dict[str, Any]:
        return _as_dict(_dig(self.assistant, "media", key, "direct_endpoint"))

    def direct_media_available(self, key: str) -> bool:
        direct = self._direct_media_entry(key)
        return bool(direct.get("available") and direct.get("route_available", True))

    def direct_media_route_available(self, key: str) -> bool:
        direct = self._direct_media_entry(key)
        if "route_available" in direct:
            return bool(direct.get("route_available"))
        return bool(direct.get("available"))

    def direct_media_config_hint(self, key: str) -> str:
        direct = self._direct_media_entry(key)
        hint = direct.get("config_hint")
        return str(hint or "").strip() if isinstance(hint, str) else ""

    def generated_image_direct_available(self) -> bool:
        return self.direct_media_available("generated_image")

    def generated_image_formats(self) -> List[str]:
        direct = self._direct_media_entry("generated_image")
        formats = _as_list_of_strings(direct.get("formats"))
        return formats or ["png"]

    def generated_image_provider_models_endpoint(self) -> str:
        direct = self._direct_media_entry("generated_image")
        endpoint = direct.get("provider_models_endpoint")
        return str(endpoint or "").strip() if isinstance(endpoint, str) else ""

    def generated_image_provider_models_task(self) -> str:
        direct = self._direct_media_entry("generated_image")
        task = direct.get("provider_models_task")
        return str(task or "").strip() if isinstance(task, str) and task.strip() else "text_to_image"

    def direct_media_adapter_catalog_endpoint(self, key: str) -> str:
        direct = self._direct_media_entry(key)
        endpoint = direct.get("adapter_catalog_endpoint")
        return str(endpoint or "").strip() if isinstance(endpoint, str) else ""

    def direct_media_supports_batch(self, key: str) -> bool:
        direct = self._direct_media_entry(key)
        return bool(direct.get("supports_batch"))

    def direct_media_batch_count_field(self, key: str) -> str:
        direct = self._direct_media_entry(key)
        field = direct.get("batch_count_field")
        return str(field or "").strip() if isinstance(field, str) else ""

    def direct_media_batch_seed_field(self, key: str) -> str:
        direct = self._direct_media_entry(key)
        field = direct.get("batch_seed_field")
        return str(field or "").strip() if isinstance(field, str) else ""

    def direct_media_supports_lora_adapters(self, key: str) -> bool:
        direct = self._direct_media_entry(key)
        return bool(direct.get("supports_lora_adapters"))

    def direct_media_supports_flow_shift(self, key: str) -> bool:
        direct = self._direct_media_entry(key)
        return bool(direct.get("supports_flow_shift"))

    def edited_image_direct_available(self) -> bool:
        return self.direct_media_available("edited_image")

    def upscaled_image_direct_available(self) -> bool:
        return self.direct_media_available("upscaled_image")

    def generated_video_direct_available(self) -> bool:
        return self.direct_media_available("generated_video")

    def image_to_video_direct_available(self) -> bool:
        return self.direct_media_available("image_to_video")

    def generated_voice_direct_available(self) -> bool:
        return self.direct_media_available("generated_voice")

    def generated_music_direct_available(self) -> bool:
        return self.direct_media_available("generated_music")


def get_cached_assistant_capabilities(
    gateway: Any,
    *,
    ttl_s: float = 60.0,
    force: bool = False,
) -> AssistantCapabilities:
    """Return a short-lived cache of Gateway's assistant contract."""

    now = time.monotonic()
    cached = getattr(gateway, "_assistant_capabilities_cache", None)
    if (
        not force
        and isinstance(cached, AssistantCapabilities)
        and cached.fetched_at
        and (now - float(cached.fetched_at)) < float(ttl_s)
    ):
        return cached

    try:
        fn = getattr(gateway, "discovery_capabilities", None)
        if not callable(fn):
            raise RuntimeError("gateway client does not expose discovery_capabilities")
        response = fn()
        if not isinstance(response, dict):
            raise RuntimeError("gateway capabilities response was not an object")
        parsed = AssistantCapabilities.from_discovery_response(response, fetched_at=now)
    except Exception as e:
        parsed = AssistantCapabilities.unavailable(error=str(e))

    try:
        setattr(gateway, "_assistant_capabilities_cache", parsed)
    except Exception:
        pass
    return parsed
