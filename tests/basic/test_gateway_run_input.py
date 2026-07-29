"""Gateway run input tests."""

from __future__ import annotations

import pytest

from abstractassistant.gateway.run_input import (
    MEDIA_OVERRIDE_INPUT_KEYS,
    build_run_input_data,
)


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
def test_build_run_input_media_overrides_ride_workflow_pins() -> None:
    """Media route overrides map to the managed workflow's per-run input pins
    (provider+model pairs; sound rides a full output spec). Absent routes add
    no keys, so the gateway default keeps applying."""
    payload = build_run_input_data(
        prompt="make a picture",
        media_overrides={
            "output.image.text_to_image": {"provider": "mlx-gen", "model": "AbstractFramework/flux-x"},
            "output.video.image_to_video": {"provider": "mlx-gen", "model": "AbstractFramework/wan-x"},
            "output.music": {"provider": "stable-audio-3", "model": "stabilityai/custom-music"},
            "output.sound": {"provider": "stable-audio-3", "model": "stabilityai/custom-sfx"},
        },
    )

    assert payload["image_provider"] == "mlx-gen"
    assert payload["image_model"] == "AbstractFramework/flux-x"
    assert payload["image_to_video_provider"] == "mlx-gen"
    assert payload["image_to_video_model"] == "AbstractFramework/wan-x"
    assert payload["music_provider"] == "stable-audio-3"
    assert payload["music_model"] == "stabilityai/custom-music"
    # Sound overrides ride INSIDE the output spec (the sound node is an
    # llm_call whose generation target is the spec, not the node's provider).
    assert payload["sound_output"] == {
        "modality": "sound",
        "task": "text_to_audio",
        "format": "wav",
        "provider": "stable-audio-3",
        "model": "stabilityai/custom-sfx",
    }
    # Routes without an override add no pins at all.
    assert "video_provider" not in payload
    assert "image_edit_provider" not in payload
    assert "image_upscale_provider" not in payload
    # Media overrides never leak into the chat-text channels.
    assert "provider" not in payload
    assert "model" not in payload
    assert "provider" not in payload["_runtime"]


@pytest.mark.basic
def test_build_run_input_media_override_half_pin_dropped() -> None:
    payload = build_run_input_data(
        prompt="hi",
        media_overrides={
            "output.image.text_to_image": {"provider": "mlx-gen"},  # no model
            "output.music": {"model": "stabilityai/custom"},  # no provider
            "output.sound": {"provider": "stable-audio-3"},  # no model
        },
    )

    assert "image_provider" not in payload
    assert "music_model" not in payload
    assert "sound_output" not in payload


@pytest.mark.basic
def test_media_override_route_keys_cover_the_settings_contract() -> None:
    """Every media route offered in settings must have a delivery pin mapping
    (or the sound special case) — an offered-but-unmapped route would be the
    dishonest override the 2026-07-18 scope cut existed to prevent."""
    from abstractassistant.preferences import LOCAL_OVERRIDE_ROUTE_KEYS

    media_keys = {
        k
        for k in LOCAL_OVERRIDE_ROUTE_KEYS
        if k not in {"output.text", "output.voice", "input.voice"}
    }
    mapped = set(MEDIA_OVERRIDE_INPUT_KEYS) | {"output.sound"}
    assert media_keys == mapped


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
