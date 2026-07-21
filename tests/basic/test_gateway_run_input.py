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
def test_build_run_input_local_override_rides_both_channels() -> None:
    """A local provider/model override rides BOTH channels so it covers the
    whole workflow: the TOP-LEVEL pin reaches the router llm_call node (which
    ignores _runtime — verified live), and _runtime covers agent-style nodes.
    Neither channel mutates the gateway's global default."""
    payload = build_run_input_data(
        prompt="hello",
        provider="lmstudio",
        model="ornith-1.0-35b",
        base_url="http://localhost:1234/v1",
    )

    # _runtime channel (agent-style nodes + future run-scoped defaults).
    assert payload["_runtime"]["provider"] == "lmstudio"
    assert payload["_runtime"]["model"] == "ornith-1.0-35b"
    assert payload["_runtime"]["base_url"] == "http://localhost:1234/v1"
    # Top-level channel (router node coverage — the offline-safe fix).
    assert payload["provider"] == "lmstudio"
    assert payload["model"] == "ornith-1.0-35b"
    assert payload["base_url"] == "http://localhost:1234/v1"


@pytest.mark.basic
def test_build_run_input_half_pin_override_is_dropped() -> None:
    """Provider without model (or vice versa) must not send a broken pin on
    EITHER channel."""
    only_provider = build_run_input_data(prompt="hi", provider="lmstudio")
    assert "provider" not in only_provider["_runtime"]
    assert "provider" not in only_provider

    only_model = build_run_input_data(prompt="hi", model="ornith-1.0-35b")
    assert "model" not in only_model["_runtime"]
    assert "model" not in only_model

    # base_url alone (no provider/model) never leaks into either channel.
    only_base = build_run_input_data(prompt="hi", base_url="http://localhost:1234/v1")
    assert "base_url" not in only_base["_runtime"]
    assert "base_url" not in only_base


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
def test_build_run_input_requests_durable_session_history_by_default() -> None:
    """The server owns conversation replay (durable-sessions contract v1):
    the client asks the gateway to seed context.messages from the session's
    durable prior turns instead of shipping its local transcript."""
    payload = build_run_input_data(prompt="hello")

    assert payload["use_session_history"] is True
    assert payload["context"]["messages"] == []

    opted_out = build_run_input_data(prompt="hello", use_session_history=False)
    assert opted_out["use_session_history"] is False


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
