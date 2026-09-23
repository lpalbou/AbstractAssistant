from types import SimpleNamespace
import pytest
from abstractassistant.preferences import AssistantPreferences, PreferencesStore
from abstractassistant.speculation import normalize_speculation, speculation_options
from abstractassistant.gateway.run_input import build_run_input_data


@pytest.mark.parametrize("value", [False, {"mode":"native_mtp", "num_draft_tokens":4, "require_acceleration":True}])
def test_preferences_to_run_wire_preserves_explicit_intent(tmp_path, value):
    store = PreferencesStore(tmp_path / "preferences.json")
    store.save(AssistantPreferences(speculation=value, reasoning_effort="high"))
    loaded = store.load()
    assert loaded.speculation == value
    assert loaded.run_scope()["speculation"] == value
    result = build_run_input_data(prompt="hello", speculation=loaded.run_scope()["speculation"])
    assert result["_runtime"]["speculation"] == value
    assert "speculation" not in result


def test_inherit_is_absent_and_malformed_controls_refuse():
    assert "speculation" not in AssistantPreferences().run_scope()
    assert "speculation" not in build_run_input_data(prompt="hello")["_runtime"]
    for value in [True, "off", {"mode":"native_mtp", "num_draft_tokens":True}, {"mode":"native_mtp", "num_draft_tokens":2.5}]:
        with pytest.raises(ValueError):
            normalize_speculation(value)


def test_capability_options_never_infer_from_model_names():
    rows, note = speculation_options({"capabilities":{"speculation":{"native_mtp":True}}})
    assert [value for value, _ in rows] == [None, False]
    assert "unknown" in note
    saved = normalize_speculation({"mode":"native_mtp", "num_draft_tokens":5})
    rows, note = speculation_options({"execution":{"speculation":{"supported":True,"ready":False,"supported_depths":[2,3],"reason":"head_not_loaded"}}}, saved)
    assert len(rows) == 5
    assert "saved; unavailable" in rows[-1][1]
    assert note == "head_not_loaded"


def test_gateway_discovery_sends_provider_separately(monkeypatch):
    from abstractassistant.gateway.client import GatewayClient
    client = GatewayClient.__new__(GatewayClient)
    seen = {}
    monkeypatch.setattr(client, "_url", lambda path, query=None: seen.update(path=path, query=query) or "url")
    monkeypatch.setattr(client, "_request_json", lambda **kwargs: {})
    client.discovery_model_capabilities(model_name="org/model", provider="endpoint:local")
    assert seen["query"] == {"model_name":"org/model", "provider":"endpoint:local"}


def test_unloadable_saved_speculation_falls_back_to_inherit(tmp_path):
    import json
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"speculation": {"mode": "native_mtp", "num_draft_tokens": 0}}))
    loaded = PreferencesStore(path).load()
    assert loaded.speculation is None
    assert "speculation" not in loaded.run_scope()
