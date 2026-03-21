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
    assert cfg.gateway.use_gateway is True
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
def test_from_dict_can_disable_gateway_without_explicit_gateway_url(monkeypatch) -> None:
    monkeypatch.delenv("ABSTRACTGATEWAY_URL", raising=False)
    monkeypatch.delenv("ABSTRACTFLOW_GATEWAY_URL", raising=False)
    monkeypatch.delenv("ABSTRACTGATEWAY_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ABSTRACTFLOW_GATEWAY_AUTH_TOKEN", raising=False)

    cfg = Config.from_dict({"gateway": {"use_gateway": False}})

    assert cfg.gateway.use_gateway is False
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
