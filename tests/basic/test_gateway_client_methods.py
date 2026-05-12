"""Gateway client method contract tests."""

from __future__ import annotations

import pytest

from abstractassistant.gateway import client as client_mod
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig


@pytest.mark.basic
def test_gateway_client_new_contract_methods_build_expected_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "run_id": "r1"}

    monkeypatch.setattr(client_mod, "_request_json", fake_request_json)
    gw = GatewayClient(GatewayClientConfig(base_url="http://gateway", auth_token="tok"))

    gw.discovery_capabilities()
    gw.voice_voices()
    gw.audio_speech_models()
    gw.audio_transcription_models()
    gw.vision_provider_models(task="text_to_image")
    gw.voice_tts(run_id="r1", text="say it", profile="alloy", fmt="wav", model="tts-model")
    gw.audio_transcribe(run_id="r1", audio_artifact={"$artifact": "aud"}, language="en", model="stt-model")
    gw.session_prompt_cache_status(session_id="s1", provider="p", model="m", bundle_id="b", flow_id="f")
    gw.session_prompt_cache_prepare(
        session_id="s1",
        provider="p",
        model="m",
        bundle_id="b",
        flow_id="f",
        system_prompt="system",
        pinned_attachments=[{"$artifact": "a1"}],
    )
    gw.session_prompt_cache_clear(session_id="s1", provider="p", model="m")
    gw.session_prompt_cache_rebuild(session_id="s1", provider="p", model="m", modules=[{"module_id": "system"}])
    gw.image_generate(
        run_id="r1",
        prompt="paint it",
        provider="chat-provider",
        model="chat-model",
        image_provider="vision-provider",
        image_model="vision-model",
        fmt="webp",
        width=512,
        height=512,
    )

    urls = [str(c["url"]) for c in calls]
    assert urls[0] == "http://gateway/api/gateway/discovery/capabilities"
    assert urls[1] == "http://gateway/api/gateway/voice/voices"
    assert urls[2] == "http://gateway/api/gateway/audio/speech/models"
    assert urls[3] == "http://gateway/api/gateway/audio/transcriptions/models"
    assert urls[4] == "http://gateway/api/gateway/vision/provider_models?task=text_to_image"
    assert calls[5]["body"]["model"] == "tts-model"
    assert calls[5]["body"]["profile"] == "alloy"
    assert calls[6]["body"]["model"] == "stt-model"
    assert "/api/gateway/sessions/s1/prompt_cache/status?" in urls[7]
    assert urls[8] == "http://gateway/api/gateway/sessions/s1/prompt_cache/prepare"
    assert urls[9] == "http://gateway/api/gateway/sessions/s1/prompt_cache/clear"
    assert urls[10] == "http://gateway/api/gateway/sessions/s1/prompt_cache/rebuild"
    assert urls[11] == "http://gateway/api/gateway/runs/r1/images/generate"
    assert calls[8]["body"]["system_prompt"] == "system"
    assert calls[8]["body"]["pinned_attachments"] == [{"$artifact": "a1"}]
    assert calls[10]["body"]["modules"] == [{"module_id": "system"}]
    assert calls[11]["body"]["format"] == "webp"
    assert calls[11]["body"]["width"] == 512
    assert calls[11]["body"]["provider"] == "chat-provider"
    assert calls[11]["body"]["model"] == "chat-model"
    assert calls[11]["body"]["image_provider"] == "vision-provider"
    assert calls[11]["body"]["image_model"] == "vision-model"
    assert calls[11]["timeout_s"] >= 180.0
