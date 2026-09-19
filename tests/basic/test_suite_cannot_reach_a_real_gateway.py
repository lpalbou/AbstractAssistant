"""The suite's own safety net (see tests/conftest.py for the incident it exists for)."""

from __future__ import annotations

import socket

import pytest


def test_the_environment_offers_no_real_gateway() -> None:
    from abstractassistant.config import Config

    config = Config()
    assert config.gateway.url == "http://127.0.0.1:9"
    assert config.gateway.auth_token == ""


@pytest.mark.parametrize("address", [("127.0.0.1", 8080), ("localhost", 8080), ("93.184.216.34", 443), ("::1", 8080)])
def test_sockets_refuse_the_dev_gateway_and_the_outside_world(address) -> None:
    family = socket.AF_INET6 if ":" in address[0] else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock, pytest.raises(AssertionError, match="Tests must use fake"):
        sock.connect(address)


def test_other_loopback_ports_still_work_for_local_fakes() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect(server.getsockname())
