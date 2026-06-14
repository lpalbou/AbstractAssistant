"""Gateway capability contract helpers."""

from __future__ import annotations

import pytest

from abstractassistant.gateway.capabilities import get_cached_assistant_capabilities
from abstractassistant.gateway.session_cache import merge_prompt_cache_runtime_hint, prepare_session_prompt_cache


def _discovery_response() -> dict:
    return {
        "capabilities": {
            "contracts": {
                "version": 1,
                "assistant": {
                    "artifacts": {
                        "content": {
                            "available": True,
                            "endpoint": "/api/gateway/runs/{run_id}/artifacts/{artifact_id}/content",
                        }
                    },
                    "voice": {
                        "tts": {
                            "available": True,
                            "formats": ["mp3", "wav"],
                            "voices": [{"id": "alloy", "label": "Alloy"}],
                            "models_endpoint": "/api/gateway/audio/speech/models",
                            "active_model": "tts-1",
                        },
                        "stt": {
                            "available": True,
                            "content_types": ["audio/wav"],
                            "max_upload_bytes": 1234,
                            "active_model": "stt-1",
                        },
                    },
                    "media": {
                        "generated_image": {
                            "direct_endpoint": {
                                "available": True,
                                "route_available": True,
                                "formats": ["png", "webp"],
                                "provider_models_endpoint": "/api/gateway/vision/provider_models",
                                "provider_models_task": "text_to_image",
                                "adapter_catalog_endpoint": "/api/gateway/vision/adapters",
                                "supports_batch": True,
                                "batch_count_field": "count",
                                "batch_seed_field": "seeds",
                                "supports_lora_adapters": True,
                            }
                        },
                        "generated_video": {
                            "direct_endpoint": {
                                "available": True,
                                "route_available": True,
                                "provider_models_task": "text_to_video",
                                "supports_flow_shift": True,
                            }
                        }
                    },
                    "prompt_cache": {"session_lifecycle": True},
                },
            }
        }
    }


class _GatewayStub:
    def __init__(self) -> None:
        self.discovery_calls = 0
        self.prepare_calls: list[dict] = []

    def discovery_capabilities(self) -> dict:
        self.discovery_calls += 1
        return _discovery_response()

    def session_prompt_cache_prepare(self, **kwargs) -> dict:
        self.prepare_calls.append(dict(kwargs))
        return {
            "supported": True,
            "ok": True,
            "runtime_hint": {
                "prompt_cache_key": "cache-key",
                "_runtime": {
                    "prompt_cache": {
                        "key": "cache-key",
                        "namespace": "cache-ns",
                        "mode": "keyed",
                        "version": 1,
                    }
                },
            },
        }


@pytest.mark.basic
def test_assistant_capabilities_parse_and_cache_gateway_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _GatewayStub()
    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_VOICE", "alloy")

    first = get_cached_assistant_capabilities(gateway)
    second = get_cached_assistant_capabilities(gateway)

    assert gateway.discovery_calls == 1
    assert first is second
    assert first.tts_available() is True
    assert first.stt_available() is True
    assert first.preferred_tts_format() == "wav"
    assert first.selected_tts_voice() == "alloy"
    assert first.selected_tts_model() == "tts-1"
    assert first.tts_models_endpoint() == "/api/gateway/audio/speech/models"
    assert first.selected_stt_model() == "stt-1"
    assert first.stt_upload_content_type_for_wav() == "audio/wav"
    assert first.stt_max_upload_bytes() == 1234
    assert first.generated_image_direct_available() is True
    assert first.generated_image_formats() == ["png", "webp"]
    assert first.generated_image_provider_models_endpoint() == "/api/gateway/vision/provider_models"
    assert first.generated_image_provider_models_task() == "text_to_image"
    assert first.direct_media_adapter_catalog_endpoint("generated_image") == "/api/gateway/vision/adapters"
    assert first.direct_media_supports_batch("generated_image") is True
    assert first.direct_media_batch_count_field("generated_image") == "count"
    assert first.direct_media_batch_seed_field("generated_image") == "seeds"
    assert first.direct_media_supports_lora_adapters("generated_image") is True
    assert first.direct_media_supports_flow_shift("generated_video") is True
    assert first.session_prompt_cache_available() is True
    assert first.artifact_content_available() is True


@pytest.mark.basic
def test_merge_prompt_cache_runtime_hint_sets_runtime_prompt_cache() -> None:
    input_data = {"_runtime": {"provider": "stub"}}

    merged = merge_prompt_cache_runtime_hint(
        input_data,
        {"_runtime": {"prompt_cache": {"key": "k", "namespace": "ns", "mode": "keyed"}}},
    )

    assert merged is True
    assert input_data["_runtime"]["provider"] == "stub"
    assert input_data["_runtime"]["prompt_cache"] == {"key": "k", "namespace": "ns", "mode": "keyed"}


@pytest.mark.basic
def test_prepare_session_prompt_cache_merges_gateway_runtime_hint() -> None:
    gateway = _GatewayStub()
    input_data = {"_runtime": {"provider": "stub", "model": "m"}}

    response = prepare_session_prompt_cache(
        gateway=gateway,
        session_id="sess",
        provider="stub",
        model="model",
        bundle_id="assistant",
        flow_id="root",
        template_id="assistant:root",
        input_data=input_data,
        system_prompt="You are helpful",
        attachments=[{"$artifact": "art_1"}],
    )

    assert response and response["ok"] is True
    assert input_data["_runtime"]["prompt_cache"]["key"] == "cache-key"
    assert gateway.prepare_calls[0]["session_id"] == "sess"
    assert gateway.prepare_calls[0]["pinned_attachments"] == [{"$artifact": "art_1"}]
