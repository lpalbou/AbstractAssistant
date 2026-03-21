"""Gateway run input tests."""

from __future__ import annotations

import pytest

from abstractassistant.gateway.run_input import build_run_input_data


@pytest.mark.basic
def test_build_run_input_omits_blank_provider_and_model() -> None:
    payload = build_run_input_data(prompt="hello", provider="", model="")

    assert "provider" not in payload
    assert "model" not in payload
    assert payload["_runtime"] == {}


@pytest.mark.basic
def test_build_run_input_includes_selected_provider_and_model() -> None:
    payload = build_run_input_data(prompt="hello", provider="openai", model="gpt-4.1-mini")

    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-4.1-mini"
    assert payload["_runtime"]["provider"] == "openai"
    assert payload["_runtime"]["model"] == "gpt-4.1-mini"
