"""Attachments must outlive the local file they were sent from.

The gateway already stores every attachment as a durable artifact (the worker
uploads the bytes before the run starts). The client used to record only the
local path, so a screenshot dragged out of the macOS screenshot UI — which
macOS later deletes from `/var/folders/.../TemporaryItems/` — lost its preview
forever. These tests pin the round trip: the durable id is recorded on the
message, and it is fetched from the run that OWNS it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from abstractassistant.controller import AssistantController
from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.ui.gateway_worker import GatewayWorker


@pytest.mark.basic
def test_worker_publishes_durable_refs_for_an_already_shown_message() -> None:
    """The palette shows the turn immediately, before the upload returns: the
    worker must hand the artifact ids back instead of dropping them."""
    worker = GatewayWorker.__new__(GatewayWorker)
    worker._attachments = ["/tmp/Screenshot 2026-09-06.png", "/tmp/report.pdf"]

    items = GatewayWorker._attachment_preview_items(
        worker,
        [
            {"$artifact": "abc123", "run_id": "session_memory_s1", "filename": "shot.png"},
            {"$artifact": "def456", "run_id": "session_memory_s1", "filename": "report.pdf"},
        ],
    )

    assert [item["$artifact"] for item in items] == ["abc123", "def456"]
    # The local path rides along so the common case needs no fetch at all...
    assert items[0]["local_path"] == "/tmp/Screenshot 2026-09-06.png"
    # ...and the owning run is kept, which is what makes the fetch work later.
    assert items[0]["run_id"] == "session_memory_s1"

    # Fewer refs than paths (a partial upload) must not mis-pair or crash.
    short = GatewayWorker._attachment_preview_items(worker, [{"$artifact": "abc123"}])
    assert len(short) == 1 and short[0]["local_path"] == "/tmp/Screenshot 2026-09-06.png"
    assert GatewayWorker._attachment_preview_items(worker, []) == []


@pytest.mark.basic
def test_download_uses_the_run_that_owns_the_artifact(tmp_path) -> None:
    """The gateway's download route is run-scoped: an uploaded attachment
    belongs to the session's upload run, never to the chat run that carried it,
    so passing the chat run id would 404."""
    controller = AssistantController.__new__(AssistantController)
    seen: list[tuple] = []

    class _Gateway:
        def download_run_artifact_content(self, *, run_id, artifact_id, **_kw):
            seen.append((run_id, artifact_id))
            return b"bytes", "image/png"

    class _Manager:
        data_dir = str(tmp_path)

    controller.gateway = _Gateway()
    controller.llm_manager = _Manager()
    # Distinct names per artifact so the on-disk download cache cannot answer
    # the second call before it reaches the gateway.
    controller._artifact_cache_filename = lambda *, artifact_id, **kw: f"{artifact_id}.png"

    try:
        AssistantController.download_artifact(
            controller,
            run_id="run_chat_turn",
            artifact={
                "$artifact": "abc123",
                "run_id": "session_memory_s1",
                "filename": "shot.png",
                "local_path": "/tmp/gone-for-good.png",
            },
        )
    except Exception:
        # Writing the file may fail in a sandbox; the routing is what matters.
        pass

    assert seen and seen[0][0] == "session_memory_s1", "owner run must win"

    # With no recorded owner, the caller's run id is still used.
    seen.clear()
    try:
        AssistantController.download_artifact(
            controller, run_id="run_chat_turn", artifact={"$artifact": "no_owner"}
        )
    except Exception:
        pass
    assert seen and seen[0][0] == "run_chat_turn"


@pytest.mark.basic
def test_merge_message_metadata_updates_the_message_in_place(tmp_path) -> None:
    manager = LLMManager.__new__(LLMManager)
    import threading

    from abstractassistant.core.session_store import SessionSnapshot

    manager._snapshot_lock = threading.RLock()
    saved: list = []
    snapshot = SessionSnapshot(
        session_id="s1",
        actor_id="a1",
        messages=[
            {"message_id": "m1", "role": "user", "content": "one", "metadata": {"a": 1}},
            {"message_id": "m2", "role": "user", "content": "two"},
        ],
        last_run_id="run_1",
        workspace_root="/tmp/ws",
    )
    manager._gateway_snapshot = snapshot
    manager._ensure_gateway_snapshot = lambda: manager._gateway_snapshot
    manager._save_gateway_snapshot = lambda snap: saved.append(snap)

    assert manager.merge_message_metadata("m2", {"attachments": [{"$artifact": "x"}]})
    messages = manager._gateway_snapshot.messages
    assert messages[1]["metadata"]["attachments"] == [{"$artifact": "x"}]
    # The other message and the snapshot's own fields are untouched.
    assert messages[0]["metadata"] == {"a": 1}
    assert manager._gateway_snapshot.last_run_id == "run_1"
    assert manager._gateway_snapshot.workspace_root == "/tmp/ws"
    assert len(saved) == 1

    # Merging keeps keys that were already there.
    assert manager.merge_message_metadata("m1", {"b": 2})
    assert manager._gateway_snapshot.messages[0]["metadata"] == {"a": 1, "b": 2}

    # Unknown ids and empty payloads are no-ops, and never write.
    saved.clear()
    assert manager.merge_message_metadata("nope", {"b": 2}) is False
    assert manager.merge_message_metadata("m1", {}) is False
    assert manager.merge_message_metadata("", {"b": 2}) is False
    assert saved == []


@pytest.mark.basic
def test_history_seeding_keeps_a_turn_s_attachments() -> None:
    """The runtime's history bundle carries each turn's artifact refs. Dropping
    them is why reopening an old session showed no attachments at all."""
    from abstractassistant.gateway.history_seed import _seed_from_session_turns

    refs = [{"$artifact": "abc", "run_id": "session_memory_s1", "filename": "shot.png"}]
    seeded = _seed_from_session_turns(
        {
            "session": {
                "turns": [
                    {
                        "run_id": "run_1",
                        "prompt": "look at this",
                        "answer": "I see it.",
                        "attachments": refs,
                    },
                    {"run_id": "run_2", "prompt": "and now?", "answer": "Done."},
                ]
            }
        }
    )

    users = [m for m in seeded if m["role"] == "user"]
    assert users[0]["metadata"]["attachments"] == refs
    assert users[0]["metadata"]["media"] == refs
    # A turn without attachments gains no empty metadata.
    assert "metadata" not in users[1]


def _manager_with_messages(messages, *, last_run_id="run_1", bundle=None, fail=False):
    """An LLMManager wired to a fake gateway, saving nowhere."""
    import threading

    from abstractassistant.core.session_store import SessionSnapshot

    manager = LLMManager.__new__(LLMManager)
    manager._snapshot_lock = threading.RLock()
    manager._gateway_snapshot = SessionSnapshot(
        session_id="s1",
        actor_id="a1",
        messages=messages,
        last_run_id=last_run_id,
        workspace_root="/tmp/ws",
    )
    manager._ensure_gateway_snapshot = lambda: manager._gateway_snapshot
    manager.saved = []
    manager._save_gateway_snapshot = lambda snap: manager.saved.append(snap)

    class _Client:
        def get_run_history_bundle(self, **_kw):
            if fail:
                raise RuntimeError("gateway down")
            return bundle or {}

    manager.gateway_client = lambda: _Client()
    return manager


@pytest.mark.basic
def test_backfill_matches_turns_by_prompt_not_by_position() -> None:
    """A runtime `ask_user` answer is a user row locally but NOT a turn, so the
    two sequences do not line up — matching by index mis-assigns files."""
    refs = [{"$artifact": "abc", "run_id": "session_memory_s1", "filename": "a.png"}]
    messages = [
        {"message_id": "m1", "role": "user", "content": "first question"},
        {"message_id": "m2", "role": "assistant", "content": "answer"},
        # Not a turn: it would take the attachment if we counted positions.
        {"message_id": "m3", "role": "user", "content": "[User response]: yes"},
        {"message_id": "m4", "role": "user", "content": "look at this"},
    ]
    manager = _manager_with_messages(
        messages,
        bundle={
            "session": {
                "turns": [
                    {"prompt": "first question", "attachments": []},
                    {"prompt": "look at this", "attachments": refs},
                ]
            }
        },
    )

    assert manager.backfill_attachments_from_gateway() == 1
    stored = manager._gateway_snapshot.messages
    assert stored[3]["metadata"]["attachments"] == refs
    assert "metadata" not in stored[2] or not stored[2].get("metadata")
    # Saved exactly once, and the snapshot's own fields are untouched.
    assert len(manager.saved) == 1
    assert manager._gateway_snapshot.last_run_id == "run_1"


@pytest.mark.basic
def test_backfill_keeps_a_local_path_that_still_works() -> None:
    messages = [
        {
            "message_id": "m1",
            "role": "user",
            "content": "look",
            "metadata": {
                "attachments": [{"filename": "a.png", "local_path": "/tmp/a.png"}]
            },
        }
    ]
    manager = _manager_with_messages(
        messages,
        bundle={
            "session": {
                "turns": [
                    {
                        "prompt": "look",
                        "attachments": [
                            {"$artifact": "abc", "run_id": "own", "filename": "a.png"}
                        ],
                    }
                ]
            }
        },
    )

    assert manager.backfill_attachments_from_gateway() == 1
    item = manager._gateway_snapshot.messages[0]["metadata"]["attachments"][0]
    # The durable ref is added; the fast local path is not thrown away.
    assert item["$artifact"] == "abc" and item["local_path"] == "/tmp/a.png"


@pytest.mark.basic
def test_backfill_is_a_no_op_when_there_is_nothing_to_read() -> None:
    refs = [{"$artifact": "abc", "filename": "a.png"}]
    bundle = {"session": {"turns": [{"prompt": "look", "attachments": refs}]}}
    messages = [{"message_id": "m1", "role": "user", "content": "look"}]

    # The synthetic upload run has no turns: don't even ask.
    asked = _manager_with_messages(
        messages, last_run_id="session_memory_s1", bundle=bundle
    )
    assert asked.backfill_attachments_from_gateway() == 0
    assert asked.saved == []

    # A gateway that is down must not lose the transcript.
    with pytest.warns(UserWarning):
        broken = _manager_with_messages(messages, bundle=bundle, fail=True)
        assert broken.backfill_attachments_from_gateway() == 0
    assert broken.saved == []

    # Nothing new to add: no rewrite.
    already = _manager_with_messages(
        [
            {
                "message_id": "m1",
                "role": "user",
                "content": "look",
                "metadata": {"attachments": refs},
            }
        ],
        bundle=bundle,
    )
    assert already.backfill_attachments_from_gateway() == 0
    assert already.saved == []


@pytest.mark.basic
def test_palette_records_uploaded_refs_on_the_pending_turn() -> None:
    from abstractassistant.app import AssistantPalette

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._pending_user_message_id = "m7"
    merged: list = []
    refreshed: list = []
    palette._controller = type(
        "C",
        (),
        {
            "merge_message_metadata": lambda self, mid, meta: (
                merged.append((mid, meta)),
                True,
            )[1]
        },
    )()
    palette.refresh_history = lambda request=None: refreshed.append(True)

    items = [{"$artifact": "abc", "run_id": "session_memory_s1", "local_path": "/tmp/a.png"}]
    AssistantPalette._on_attachments_uploaded(palette, items)

    assert merged == [("m7", {"attachments": items, "media": items})]
    assert refreshed == [True]

    # Nothing to record, or no turn to record it on: no write, no reflow.
    merged.clear()
    refreshed.clear()
    AssistantPalette._on_attachments_uploaded(palette, [])
    palette._pending_user_message_id = ""
    AssistantPalette._on_attachments_uploaded(palette, items)
    assert merged == [] and refreshed == []
