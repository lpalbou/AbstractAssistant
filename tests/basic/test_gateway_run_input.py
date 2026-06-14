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


@pytest.mark.basic
def test_build_run_input_includes_primary_image_context() -> None:
    artifact = {"$artifact": "img_1", "artifact_id": "img_1", "content_type": "image/png"}

    payload = build_run_input_data(
        prompt="edit this",
        provider="",
        model="",
        primary_image_artifact=artifact,
    )

    assert payload["primary_image_artifact"] == artifact
    assert payload["has_primary_image_context"] is True
    assert payload["context"]["primary_image_artifact"] == artifact
