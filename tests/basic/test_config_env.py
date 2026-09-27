"""Config env resolution tests."""

from __future__ import annotations

import pytest

from abstractassistant.config import Config, resolve_gateway_connection


@pytest.mark.basic
def test_default_config_reads_gateway_env(monkeypatch) -> None:
    monkeypatch.setenv("ABSTRACTGATEWAY_URL", "http://127.0.0.1:9090")
    monkeypatch.setenv("ABSTRACTGATEWAY_AUTH_TOKEN", "secret-token")
    monkeypatch.delenv("ABSTRACTFLOW_GATEWAY_URL", raising=False)
    monkeypatch.delenv("ABSTRACTFLOW_GATEWAY_AUTH_TOKEN", raising=False)

    cfg = Config.default()

    assert cfg.gateway.url == "http://127.0.0.1:9090"
    assert cfg.gateway.auth_token == "secret-token"
    assert cfg.to_dict()["gateway"]["auth_token"] == "<redacted>"


@pytest.mark.basic
def test_default_config_reads_legacy_gateway_env(monkeypatch) -> None:
    monkeypatch.delenv("ABSTRACTGATEWAY_URL", raising=False)
    monkeypatch.delenv("ABSTRACTGATEWAY_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ABSTRACTFLOW_GATEWAY_URL", "http://127.0.0.1:9191")
    monkeypatch.setenv("ABSTRACTFLOW_GATEWAY_AUTH_TOKEN", "legacy-token")

    cfg = Config.default()

    assert cfg.gateway.url == "http://127.0.0.1:9191"
    assert cfg.gateway.auth_token == "legacy-token"


@pytest.mark.basic
def test_from_dict_defaults_gateway_url_without_env(monkeypatch) -> None:
    monkeypatch.delenv("ABSTRACTGATEWAY_URL", raising=False)
    monkeypatch.delenv("ABSTRACTFLOW_GATEWAY_URL", raising=False)
    monkeypatch.delenv("ABSTRACTGATEWAY_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ABSTRACTFLOW_GATEWAY_AUTH_TOKEN", raising=False)

    cfg = Config.from_dict({})

    assert cfg.gateway.url == "http://127.0.0.1:8080"


@pytest.mark.basic
def test_from_dict_gateway_overrides_take_precedence_over_env(monkeypatch) -> None:
    monkeypatch.setenv("ABSTRACTGATEWAY_URL", "http://127.0.0.1:9090")
    monkeypatch.setenv("ABSTRACTGATEWAY_AUTH_TOKEN", "env-token")

    cfg = Config.from_dict(
        {
            "gateway": {
                "url": "http://127.0.0.1:8080",
                "auth_token": "arg-token",
            }
        }
    )

    assert cfg.gateway.url == "http://127.0.0.1:8080"
    assert cfg.gateway.auth_token == "arg-token"


@pytest.mark.basic
def test_resolve_gateway_connection_defaults_url_and_requires_token(monkeypatch) -> None:
    monkeypatch.delenv("ABSTRACTGATEWAY_URL", raising=False)
    monkeypatch.delenv("ABSTRACTFLOW_GATEWAY_URL", raising=False)
    monkeypatch.delenv("ABSTRACTGATEWAY_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ABSTRACTFLOW_GATEWAY_AUTH_TOKEN", raising=False)

    with pytest.raises(ValueError, match="ABSTRACTGATEWAY_AUTH_TOKEN"):
        resolve_gateway_connection(require_auth_token=True)

    url, token = resolve_gateway_connection()
    assert url == "http://127.0.0.1:8080"
    assert token == ""


@pytest.mark.basic
def test_default_gateway_url_is_this_computers_gateway_by_the_gateways_rule(tmp_path, monkeypatch) -> None:
    """The installer moves the gateway off a busy 8080; without a flag, env or saved
    sign-in the Assistant must follow it, by the gateway's own rule (local_gateway).

    Seam test against the REAL gateway (monorepo runs); the CI-runnable cases with a
    stub gateway are in test_gateway_url_resolution.py."""
    first_run = pytest.importorskip("abstractgateway.first_run")
    if not hasattr(first_run, "local_gateway"):
        pytest.skip("the installed abstractgateway predates local_gateway (0.6.0)")
    from abstractgateway.runtime_config import write_network_setting

    from abstractassistant import config as config_mod

    monkeypatch.setenv("ABSTRACTGATEWAY_DATA_DIR", str(tmp_path))
    assert config_mod._local_gateway_url() == "http://127.0.0.1:8080"
    write_network_setting(tmp_path, mode="localhost", port=18081, internet_acknowledged=None, actor="test")
    assert config_mod._local_gateway_url() == "http://127.0.0.1:18081"


@pytest.mark.basic
def test_a_sign_in_saved_against_the_old_default_follows_the_moved_gateway(tmp_path, monkeypatch) -> None:
    from abstractassistant import preferences
    from abstractassistant.preferences import GatewayConnectionPreferences, GatewayConnectionStore

    monkeypatch.setattr(preferences, "DEFAULT_GATEWAY_URL", "http://127.0.0.1:8081")
    store = GatewayConnectionStore(tmp_path / "gateway_connection.json")
    store.save(GatewayConnectionPreferences(base_url="http://127.0.0.1:8080", auth_mode="session", session_id="s1"))
    loaded = store.load()
    assert loaded.base_url == "http://127.0.0.1:8081" and loaded.session_id == "s1"
    store.save(GatewayConnectionPreferences(base_url="http://127.0.0.1:18850"))
    assert store.load().base_url == "http://127.0.0.1:18850"  # a URL chosen on purpose is kept
