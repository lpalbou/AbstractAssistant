"""Assistant-side view of the Gateway thin-client capability contract."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import threading
import time
import warnings
from typing import Any, Dict, List, Optional


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

    def automations_available(self) -> bool:
        """Contract F: the gateway advertises the Automations API as
        ``contracts.common.automations.available``; absent or not ``true`` =
        no Automations surface in this app."""
        return _as_dict(self.common.get("automations")).get("available") is True

    def tts(self) -> Dict[str, Any]:
        return _as_dict(_dig(self.assistant, "voice", "tts"))

    def stt(self) -> Dict[str, Any]:
        return _as_dict(_dig(self.assistant, "voice", "stt"))

    def tts_available(self) -> bool:
        return bool(self.tts().get("available"))

    def tts_streaming_available(self) -> bool:
        tts = self.tts()
        delivery_modes = _as_list_of_strings(tts.get("delivery_modes"))
        return bool(tts.get("streaming") is True and "stream" in delivery_modes and self.tts_stream_endpoint())

    def tts_stream_endpoint(self) -> str:
        endpoint = self.tts().get("stream_endpoint")
        return str(endpoint or "").strip() if isinstance(endpoint, str) else ""

    def stt_available(self) -> bool:
        return bool(self.stt().get("available"))

    def tts_formats(self) -> List[str]:
        formats = _as_list_of_strings(self.tts().get("formats"))
        return formats or ["wav"]

    def tts_models_endpoint(self) -> str:
        endpoint = self.tts().get("models_endpoint")
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


# A FAILED capabilities fetch is cached only briefly: serving it like a good
# snapshot under stale_ok pinned "TTS unavailable" for the whole app lifetime
# after one startup hiccup — voice went silently dead (2026-07-28).
_FAILURE_RETRY_GRACE_S = 5.0


def _spawn_capabilities_refresh(gateway: Any) -> None:
    """Refetch capabilities on a background thread (single-flight per client).

    stale_ok readers (voice support checks on the GUI thread) must never block
    on HTTP; when they see a failure snapshot, the refresh runs here so the
    NEXT check self-heals."""
    if getattr(gateway, "_assistant_capabilities_refresh_inflight", False):
        return
    try:
        setattr(gateway, "_assistant_capabilities_refresh_inflight", True)
    except Exception:
        return

    def _worker() -> None:
        try:
            get_cached_assistant_capabilities(gateway, force=True)
        except Exception:
            pass
        finally:
            try:
                setattr(gateway, "_assistant_capabilities_refresh_inflight", False)
            except Exception:
                pass

    try:
        threading.Thread(
            target=_worker, name="assistant-capabilities-refresh", daemon=True
        ).start()
    except Exception:
        try:
            setattr(gateway, "_assistant_capabilities_refresh_inflight", False)
        except Exception:
            pass


def get_cached_assistant_capabilities(
    gateway: Any,
    *,
    ttl_s: float = 60.0,
    force: bool = False,
    stale_ok: bool = False,
) -> AssistantCapabilities:
    """Return a short-lived cache of Gateway's assistant contract.

    Healthy snapshots satisfy stale_ok readers indefinitely (capabilities
    rarely change; settings paths force-refresh). FAILURE snapshots do not:
    they are served only within a short grace window, after which stale_ok
    readers get the cached failure plus a background refresh (non-blocking
    self-heal) and TTL readers refetch synchronously."""

    now = time.monotonic()
    cached = getattr(gateway, "_assistant_capabilities_cache", None)
    if not force and isinstance(cached, AssistantCapabilities) and cached.fetched_at:
        age = now - float(cached.fetched_at)
        if cached.error:
            if age < _FAILURE_RETRY_GRACE_S:
                return cached
            if stale_ok:
                _spawn_capabilities_refresh(gateway)
                return cached
            # TTL readers fall through to a synchronous refetch.
        elif bool(stale_ok) or age < float(ttl_s):
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
