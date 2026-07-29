"""Gateway capability contract helpers."""

from __future__ import annotations

import pytest

from abstractassistant.gateway.capabilities import get_cached_assistant_capabilities


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

    def discovery_capabilities(self) -> dict:
        self.discovery_calls += 1
        return _discovery_response()


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


@pytest.mark.basic
def test_assistant_capabilities_can_use_stale_cache_without_discovery() -> None:
    gateway = _GatewayStub()
    first = get_cached_assistant_capabilities(gateway)
    first.fetched_at = 1.0

    stale = get_cached_assistant_capabilities(gateway, ttl_s=0.001, stale_ok=True)
    refreshed = get_cached_assistant_capabilities(gateway, ttl_s=0.001)

    assert stale is first
    assert refreshed is not first
    assert gateway.discovery_calls == 2


class _FlakyGatewayStub:
    """Fails the first discovery call, succeeds afterwards."""

    def __init__(self) -> None:
        self.discovery_calls = 0

    def discovery_capabilities(self) -> dict:
        self.discovery_calls += 1
        if self.discovery_calls == 1:
            raise RuntimeError("gateway starting up")
        return _discovery_response()


@pytest.mark.basic
def test_assistant_capabilities_failure_snapshot_self_heals(monkeypatch: pytest.MonkeyPatch) -> None:
    """One failed startup fetch must not pin 'TTS unavailable' for the app's
    lifetime: after the failure grace window, stale_ok readers still get a
    non-blocking answer but a background refresh runs, and the NEXT read
    serves the healthy snapshot (this was the silent dead-voice mechanism)."""
    import abstractassistant.gateway.capabilities as caps_mod

    # Run the "background" refresh inline so the test is deterministic.
    refresh_calls: list = []

    def _inline_refresh(gateway) -> None:
        refresh_calls.append(gateway)
        get_cached_assistant_capabilities(gateway, force=True)

    monkeypatch.setattr(caps_mod, "_spawn_capabilities_refresh", _inline_refresh)

    gateway = _FlakyGatewayStub()
    failed = get_cached_assistant_capabilities(gateway)
    assert failed.error
    assert failed.tts_available() is False
    assert gateway.discovery_calls == 1

    # Within the grace window the failure is served as-is (burst absorption).
    within_grace = get_cached_assistant_capabilities(gateway, stale_ok=True)
    assert within_grace is failed
    assert not refresh_calls

    # Age the failure snapshot past the grace window: a stale_ok read returns
    # the cached failure (non-blocking) but triggers the refresh...
    failed.fetched_at = failed.fetched_at - 60.0
    served = get_cached_assistant_capabilities(gateway, stale_ok=True)
    assert served.error
    assert refresh_calls

    # ...and the next read sees the healthy snapshot.
    healed = get_cached_assistant_capabilities(gateway, stale_ok=True)
    assert not healed.error
    assert healed.tts_available() is True


@pytest.mark.basic
def test_assistant_capabilities_failed_ttl_read_refetches_synchronously() -> None:
    """Non-stale_ok readers do not keep a failure alive past the grace window:
    they refetch synchronously (the pre-existing TTL semantics, but with the
    short failure grace instead of the full TTL)."""
    gateway = _FlakyGatewayStub()
    failed = get_cached_assistant_capabilities(gateway)
    assert failed.error

    failed.fetched_at = failed.fetched_at - 60.0
    healed = get_cached_assistant_capabilities(gateway)
    assert not healed.error
    assert gateway.discovery_calls == 2


