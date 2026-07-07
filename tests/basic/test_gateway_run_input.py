"""Gateway run input tests."""

from __future__ import annotations

import pytest

from abstractassistant.gateway.run_input import build_run_input_data


@pytest.mark.basic
def test_build_run_input_omits_blank_provider_and_model() -> None:
    payload = build_run_input_data(prompt="hello")

    assert "provider" not in payload
    assert "model" not in payload
    assert payload["_runtime"] == {}


@pytest.mark.basic
def test_build_run_input_omits_local_chat_history_by_default() -> None:
    payload = build_run_input_data(
        prompt="hello",
        messages=[
            {"role": "user", "content": "old local prompt"},
            {"role": "assistant", "content": "old local answer"},
        ],
    )

    assert payload["context"] == {"task": "hello", "messages": []}
    assert payload["use_context"] is False
    assert payload["_runtime"] == {}


@pytest.mark.basic
def test_build_run_input_includes_primary_image_context() -> None:
    artifact = {"$artifact": "img_1", "artifact_id": "img_1", "content_type": "image/png"}

    payload = build_run_input_data(
        prompt="edit this",
        primary_image_artifact=artifact,
    )

    assert payload["primary_image_artifact"] == artifact
    assert payload["has_primary_image_context"] is True
    assert payload["context"]["primary_image_artifact"] == artifact
