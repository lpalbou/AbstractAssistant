"""Gateway generated-media event rendering."""

from __future__ import annotations

import pytest

from abstractassistant.gateway.adapter import GatewayEventAdapter
from abstractassistant.gateway.generated_media import (
    build_generated_image_assistant_message,
    choose_generated_image_format,
    parse_image_generation_intent,
    session_memory_run_id,
)
from abstractassistant.core.transcript_summary import build_display_messages


@pytest.mark.basic
def test_generated_image_event_becomes_renderable_artifact_thumbnail() -> None:
    rec = {
        "effect": {
            "type": "emit_event",
            "payload": {
                "name": "abstract.media.image.generated",
                "payload": {
                    "run_id": "run_1",
                    "prompt": "a tiny castle",
                    "image_artifact": {
                        "$artifact": "art_img",
                        "filename": "generated.png",
                        "content_type": "image/png",
                    },
                },
            },
        }
    }

    events = GatewayEventAdapter().handle_record(rec)
    messages = [
        {
            "role": "assistant",
            "content": str(events[0]["content"]),
            "run_id": "run_1",
            "metadata": events[0]["meta"],
        }
    ]
    display = build_display_messages(messages)

    assert events[0]["type"] == "assistant"
    assert display[0]["tool_links"][0]["kind"] == "artifact"
    assert display[0]["image_thumbnails"][0]["kind"] == "artifact"
    assert display[0]["image_thumbnails"][0]["run_id"] == "run_1"


@pytest.mark.basic
def test_parse_explicit_chat_image_generation_intents() -> None:
    direct = parse_image_generation_intent("/image a tiny castle, 1024x768 webp")
    assert direct is not None
    assert direct.prompt == "a tiny castle, 1024x768 webp"
    assert direct.width == 1024
    assert direct.height == 768
    assert direct.format == "webp"

    natural = parse_image_generation_intent("Please generate an image of a tiny castle")
    assert natural is not None
    assert natural.prompt == "a tiny castle"

    assert parse_image_generation_intent("Draw a tiny castle") is not None
    assert parse_image_generation_intent("Create an icon button in PyQt") is None
    assert parse_image_generation_intent("Render a React component") is None
    assert parse_image_generation_intent("How do I generate an image with this model?") is None


@pytest.mark.basic
def test_generated_image_direct_message_renders_thumbnail_without_message_run_id() -> None:
    run_id = session_memory_run_id("session-1")
    msg = build_generated_image_assistant_message(
        run_id=run_id,
        prompt="a tiny castle",
        provider="openai-compatible",
        model="image-model",
        fmt=choose_generated_image_format(
            parse_image_generation_intent("/image a tiny castle") or pytest.fail("missing intent"),
            ["jpeg", "webp"],
        ),
        response={
            "ok": True,
            "run_id": run_id,
            "request_id": "req_1",
            "image_artifact": {
                "$artifact": "art_img",
                "filename": "generated.webp",
                "content_type": "image/webp",
            },
        },
    )

    assert msg is not None
    display = build_display_messages([msg])
    thumbs = display[0]["image_thumbnails"]
    assert thumbs[0]["kind"] == "artifact"
    assert thumbs[0]["target"] == "art_img"
    assert thumbs[0]["run_id"] == run_id
    assert thumbs[0]["content_type"] == "image/webp"
