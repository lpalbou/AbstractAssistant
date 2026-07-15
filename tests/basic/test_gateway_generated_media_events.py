"""Gateway generated-media event rendering."""

from __future__ import annotations

import pytest

from abstractassistant.gateway.adapter import GatewayEventAdapter
from abstractassistant.gateway.generated_media import session_memory_run_id


@pytest.mark.basic
def test_generated_image_event_carries_renderable_artifact_metadata() -> None:
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

    assert events[0]["type"] == "assistant"
    assert "a tiny castle" in str(events[0]["content"])
    meta = events[0]["meta"]
    assert meta["image_artifact"]["$artifact"] == "art_img"
    assert meta["image_artifact"]["content_type"] == "image/png"
    assert meta["generated_media"]["run_id"] == "run_1"


@pytest.mark.basic
def test_session_memory_run_id_is_stable_and_safe() -> None:
    rid = session_memory_run_id("session-1")
    assert rid == "session_memory_session-1"
    # Unsafe characters fall back to a hashed, still-stable id.
    hashed = session_memory_run_id("sess/with:odd chars")
    assert hashed.startswith("session_memory_sha_")
    assert hashed == session_memory_run_id("sess/with:odd chars")
