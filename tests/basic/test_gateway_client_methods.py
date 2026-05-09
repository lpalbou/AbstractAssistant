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
    gw.image_generate(run_id="r1", prompt="paint it", fmt="webp", width=512, height=512)

    urls = [str(c["url"]) for c in calls]
    assert urls[0] == "http://gateway/api/gateway/discovery/capabilities"
    assert "/api/gateway/sessions/s1/prompt_cache/status?" in urls[1]
    assert urls[2] == "http://gateway/api/gateway/sessions/s1/prompt_cache/prepare"
    assert urls[3] == "http://gateway/api/gateway/sessions/s1/prompt_cache/clear"
    assert urls[4] == "http://gateway/api/gateway/sessions/s1/prompt_cache/rebuild"
    assert urls[5] == "http://gateway/api/gateway/runs/r1/images/generate"
    assert calls[2]["body"]["system_prompt"] == "system"
    assert calls[2]["body"]["pinned_attachments"] == [{"$artifact": "a1"}]
    assert calls[4]["body"]["modules"] == [{"module_id": "system"}]
    assert calls[5]["body"]["format"] == "webp"
    assert calls[5]["body"]["width"] == 512
