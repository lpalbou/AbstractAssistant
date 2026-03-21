"""CLI gateway-mode contract tests."""

from __future__ import annotations

import pytest

from abstractassistant.cli import create_parser


@pytest.mark.basic
def test_run_parser_allows_gateway_defaults_without_extra_run_flags() -> None:
    args = create_parser().parse_args(["run", "--prompt", "Hello"])

    assert args.command == "run"
    assert args.prompt == "Hello"
    assert args.gateway_url is None
    assert args.gateway_token is None


@pytest.mark.basic
def test_run_parser_accepts_gateway_override_flags() -> None:
    args = create_parser().parse_args(
        [
            "--gateway-url",
            "http://127.0.0.1:9090",
            "--gateway-token",
            "secret-token",
            "run",
            "--prompt",
            "Hello",
        ]
    )

    assert args.gateway_url == "http://127.0.0.1:9090"
    assert args.gateway_token == "secret-token"
