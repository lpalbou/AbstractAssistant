"""Gateway client method contract tests."""

from __future__ import annotations

from http.client import HTTPMessage
import pytest

from abstractassistant.gateway import client as client_mod
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig


@pytest.mark.basic
def test_gateway_client_openapi_document_uses_root_openapi_path(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs)
        return {"info": {"title": "AbstractGateway"}}

    monkeypatch.setattr(client_mod, "_request_json", fake_request_json)
    gw = GatewayClient(GatewayClientConfig(base_url="http://gateway", auth_token="tok"))

    payload = gw.openapi_document()

    assert payload["info"]["title"] == "AbstractGateway"
    assert calls[0]["url"] == "http://gateway/openapi.json"


@pytest.mark.basic
def test_gateway_client_new_contract_methods_build_expected_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "run_id": "r1"}

    monkeypatch.setattr(client_mod, "_request_json", fake_request_json)
    gw = GatewayClient(GatewayClientConfig(base_url="http://gateway", auth_token="tok"))

    gw.discovery_capabilities()
    gw.get_capability_defaults()
    gw.list_visualflows()
    gw.create_visualflow(
        name="Assistant",
        description="Managed assistant flow",
        interfaces=["abstractassistant.agent.v1"],
        nodes=[{"id": "start"}],
        edges=[{"id": "edge"}],
        entry_node="start",
    )
    gw.get_visualflow(flow_id="flow123")
    gw.update_visualflow(flow_id="flow123", description="Updated flow")
    gw.publish_visualflow(flow_id="flow123", bundle_id="assistant-default", overwrite=True)
    gw.promote_workflow_catalog_bundle(bundle_id="assistant-default", bundle_version="0.0.0", make_default=False)
    gw.voice_voices(provider="openai", model="tts-1", compact=True, providers_only=True)
    gw.audio_speech_models(provider="openai", providers_only=True)
    gw.audio_transcription_models(provider="whisper", providers_only=True)
    gw.audio_music_providers(task="text_to_music")
    gw.audio_music_models(task="text_to_music", provider="acemusic")
    gw.vision_provider_models(task="text_to_image", provider="mflux", providers_only=True)
    gw.vision_adapters(model="AbstractFramework/qwen-image-2512-8bit", task="text_to_image", provider="mlx-gen")
    gw.discovery_provider_models(provider_name="lmstudio", capability_route="input.image,output.text")
    gw.set_capability_default(
        route_key="output.voice",
        provider="openai",
        model="tts-1",
        options={"voice": "alloy"},
    )
    gw.clear_capability_default(route_key="output.voice")
    gw.voice_tts(run_id="r1", text="say it", provider="openai", profile="alloy", fmt="wav", model="tts-model")
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
        count=2,
        seeds=[101, 102],
        lora_adapters=[{"source": "adapter-a", "scale": 0.8}],
        guidance_2=3.5,
    )
    gw.image_edit(
        run_id="r1",
        prompt="make it warmer",
        image_artifact={"$artifact": "img"},
        mask_artifact={"$artifact": "mask"},
        image_provider="mflux",
        image_model="flux-edit",
        strength=0.6,
        options={"count": 2, "seeds": [201, 202], "lora_adapters": [{"source": "adapter-b"}]},
    )
    gw.image_upscale(
        run_id="r1",
        image_artifact={"$artifact": "img"},
        image_provider="mlx-gen",
        image_model="seedvr2",
        resolution="2x",
        options={"softness": 0.25},
    )
    gw.video_generate(
        run_id="r1",
        prompt="spin the product",
        video_provider="mlx-gen",
        video_model="wan-t2v",
        frames=33,
        fps=24,
        options={"count": 2, "seeds": [301, 302], "lora_adapters": [{"source": "adapter-c"}], "flow_shift": 3.0},
    )
    gw.video_from_image(
        run_id="r1",
        prompt="zoom in slowly",
        image_artifact={"$artifact": "img"},
        video_provider="mlx-gen",
        video_model="wan-i2v",
        options={"strength": 0.7, "guidance_2": 4.5},
    )
    gw.music_generate(
        run_id="r1",
        prompt="warm piano loop",
        task="text_to_music",
        music_provider="acemusic",
        music_model="ace-step",
    )
    gw.sandbox_generate(
        provider="ovh",
        model="gpt-oss-20b",
        prompt="hello",
        messages=[{"role": "assistant", "content": "earlier"}],
        attachments=[{"$artifact": "art_1", "content_type": "image/png"}],
        system_prompt="system",
        max_tokens=400,
    )

    urls = [str(c["url"]) for c in calls]
    assert urls[0] == "http://gateway/api/gateway/discovery/capabilities"
    assert urls[1] == "http://gateway/api/gateway/config/capability-defaults"
    assert urls[2] == "http://gateway/api/gateway/visualflows"
    assert urls[3] == "http://gateway/api/gateway/visualflows"
    assert calls[3]["body"]["interfaces"] == ["abstractassistant.agent.v1"]
    assert urls[4] == "http://gateway/api/gateway/visualflows/flow123"
    assert urls[5] == "http://gateway/api/gateway/visualflows/flow123"
    assert calls[5]["body"]["description"] == "Updated flow"
    assert urls[6] == "http://gateway/api/gateway/visualflows/flow123/publish"
    assert calls[6]["body"]["bundle_id"] == "assistant-default"
    assert urls[7] == "http://gateway/api/gateway/admin/workflow-catalog/promote"
    assert calls[7]["body"]["bundle_id"] == "assistant-default"
    assert calls[7]["body"]["bundle_version"] == "0.0.0"
    assert calls[7]["body"]["make_default"] is False
    assert urls[8] == "http://gateway/api/gateway/voice/voices?provider=openai&model=tts-1&compact=true&providers_only=true"
    assert urls[9] == "http://gateway/api/gateway/audio/speech/models?provider=openai&providers_only=true"
    assert urls[10] == "http://gateway/api/gateway/audio/transcriptions/models?provider=whisper&providers_only=true"
    assert urls[11] == "http://gateway/api/gateway/audio/music/providers?task=text_to_music"
    assert urls[12] == "http://gateway/api/gateway/audio/music/models?task=text_to_music&provider=acemusic"
    assert urls[13] == "http://gateway/api/gateway/vision/provider_models?task=text_to_image&provider=mflux&providers_only=true"
    assert urls[14] == "http://gateway/api/gateway/vision/adapters?model=AbstractFramework%2Fqwen-image-2512-8bit&task=text_to_image&provider=mlx-gen"
    assert urls[15] == "http://gateway/api/gateway/discovery/providers/lmstudio/models?capability_route=input.image%2Coutput.text"
    assert urls[16] == "http://gateway/api/gateway/config/capability-defaults/output/voice"
    assert calls[16]["body"]["options"] == {"voice": "alloy"}
    assert urls[17] == "http://gateway/api/gateway/config/capability-defaults/output/voice"
    assert calls[18]["body"]["provider"] == "openai"
    assert calls[18]["body"]["model"] == "tts-model"
    assert calls[18]["body"]["profile"] == "alloy"
    assert calls[19]["body"]["model"] == "stt-model"
    assert "/api/gateway/sessions/s1/prompt_cache/status?" in urls[20]
    assert urls[21] == "http://gateway/api/gateway/sessions/s1/prompt_cache/prepare"
    assert urls[22] == "http://gateway/api/gateway/sessions/s1/prompt_cache/clear"
    assert urls[23] == "http://gateway/api/gateway/sessions/s1/prompt_cache/rebuild"
    assert urls[24] == "http://gateway/api/gateway/runs/r1/images/generate"
    assert urls[25] == "http://gateway/api/gateway/runs/r1/images/edit"
    assert urls[26] == "http://gateway/api/gateway/runs/r1/images/upscale"
    assert urls[27] == "http://gateway/api/gateway/runs/r1/videos/generate"
    assert urls[28] == "http://gateway/api/gateway/runs/r1/videos/from_image"
    assert urls[29] == "http://gateway/api/gateway/runs/r1/music/generate"
    assert urls[30] == "http://gateway/api/gateway/sandbox/generate"
    assert calls[21]["body"]["system_prompt"] == "system"
    assert calls[21]["body"]["pinned_attachments"] == [{"$artifact": "a1"}]
    assert calls[23]["body"]["modules"] == [{"module_id": "system"}]
    assert calls[24]["body"]["format"] == "webp"
    assert calls[24]["body"]["width"] == 512
    assert calls[24]["body"]["provider"] == "chat-provider"
    assert calls[24]["body"]["model"] == "chat-model"
    assert calls[24]["body"]["image_provider"] == "vision-provider"
    assert calls[24]["body"]["image_model"] == "vision-model"
    assert calls[24]["body"]["count"] == 2
    assert calls[24]["body"]["seeds"] == [101, 102]
    assert calls[24]["body"]["lora_adapters"] == [{"source": "adapter-a", "scale": 0.8}]
    assert calls[24]["body"]["guidance_2"] == 3.5
    assert calls[25]["body"]["mask_artifact"] == {"$artifact": "mask"}
    assert calls[25]["body"]["count"] == 2
    assert calls[25]["body"]["seeds"] == [201, 202]
    assert calls[25]["body"]["lora_adapters"] == [{"source": "adapter-b"}]
    assert calls[26]["body"]["resolution"] == "2x"
    assert calls[26]["body"]["softness"] == 0.25
    assert calls[27]["body"]["video_provider"] == "mlx-gen"
    assert calls[27]["body"]["count"] == 2
    assert calls[27]["body"]["seeds"] == [301, 302]
    assert calls[27]["body"]["lora_adapters"] == [{"source": "adapter-c"}]
    assert calls[27]["body"]["flow_shift"] == 3.0
    assert calls[28]["body"]["image_artifact"] == {"$artifact": "img"}
    assert calls[28]["body"]["strength"] == 0.7
    assert calls[28]["body"]["guidance_2"] == 4.5
    assert calls[29]["body"]["music_provider"] == "acemusic"
    assert calls[30]["body"]["provider"] == "ovh"
    assert calls[30]["body"]["model"] == "gpt-oss-20b"
    assert calls[30]["body"]["messages"] == [{"role": "assistant", "content": "earlier"}]
    assert calls[30]["body"]["attachments"] == [{"$artifact": "art_1", "content_type": "image/png"}]
    assert calls[24]["timeout_s"] >= 180.0


@pytest.mark.basic
def test_gateway_client_session_auth_headers_cover_gets_and_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "run_id": "r1"}

    monkeypatch.setattr(client_mod, "_request_json", fake_request_json)
    gw = GatewayClient(
        GatewayClientConfig(
            base_url="http://gateway",
            auth_mode="session",
            session_id="agws_test",
            csrf_token="agcsrf_test",
        )
    )

    gw.gateway_me()
    gw.start_run(flow_id="chat", input_data={"prompt": "Hello"})

    assert calls[0]["headers"] == {"X-AbstractGateway-Session": "agws_test"}
    assert calls[1]["headers"] == {
        "X-AbstractGateway-Session": "agws_test",
        "X-AbstractGateway-CSRF": "agcsrf_test",
    }


@pytest.mark.basic
def test_gateway_client_session_login_parses_gateway_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        def __init__(self) -> None:
            self.headers = HTTPMessage()
            self.headers.add_header("Set-Cookie", "abstractgateway_session=agws_cookie; Path=/; HttpOnly")
            self.headers.add_header("Set-Cookie", "abstractgateway_csrf=agcsrf_cookie; Path=/")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"ok": true, "session": {"expires_at": "2026-06-12T12:00:00+00:00"}}'

    monkeypatch.setattr(client_mod.urllib.request, "urlopen", lambda req, timeout=0: _Response())

    gw = GatewayClient(GatewayClientConfig(base_url="http://gateway"))

    payload = gw.session_login(user_id="alice", token="secret", remember=True)

    assert payload["ok"] is True
    assert gw.config.auth_mode == "session"
    assert gw.config.user_id == "alice"
    assert gw.config.session_id == "agws_cookie"
    assert gw.config.csrf_token == "agcsrf_cookie"
    assert gw.config.session_expires_at == "2026-06-12T12:00:00+00:00"
