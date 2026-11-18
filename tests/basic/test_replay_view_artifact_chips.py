"""QA 2026-10-28 (b): an automation answer showed two raw-id chips that could not be opened.

They were the run's bookkeeping, offloaded by size into the artifact store: the agent's system
prompt (referenced under `output.scratchpad.node_traces...`, owned by a child run, and not even
listed by the view) and the step list (`output.scratchpad.steps`). The palette shows only what
the person can use, names it readably, and opens it through the run that owns it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("abstractruntime.replay")

from abstractassistant.app import _artifact_label, _message_media_artifacts  # noqa: E402
from abstractassistant.gateway.replay_view import ViewProjector, final_fallback_event  # noqa: E402

ROOT = "68c30dd3-root"
CHILD = "d072afe8-child"


def _view(artifact_ids, artifacts, source="ledger"):
    return {
        "root_run_id": ROOT,
        "status": "completed",
        "runs": [{"run_id": ROOT, "status": "completed"}],
        "activities": [],
        "artifacts": artifacts,
        "messages": [
            {"id": f"{ROOT}:final", "role": "assistant", "kind": "final", "text": "Daily news.",
             "run_id": ROOT, "order": ["2026-10-28T13:15:49+00:00", ROOT, 6], "artifact_ids": artifact_ids,
             "source": source},
        ],
    }


def _final_meta(view):
    events = ViewProjector().project(view)
    finals = [e for e in events if e.get("type") == "assistant" and e.get("final")]
    assert finals, events
    return finals[-1]["meta"]


def test_bookkeeping_refs_are_not_attachments():
    view = _view(
        ["7c8efef3e20a049b68dcbb8c88b9f863", "f738932866ed174741b3a42601cf24eb"],
        [{"id": "f738932866ed174741b3a42601cf24eb", "run_id": ROOT, "path": "output.scratchpad.steps"}],
    )
    with pytest.warns(UserWarning, match="not listed by the replay view"):
        meta = _final_meta(view)
    assert "artifact" not in meta and "media" not in meta and "artifact_id" not in meta
    message = {"role": "assistant", "content": "Daily news.", "metadata": meta}
    assert _message_media_artifacts(message) == []


def test_a_real_output_artifact_is_kept_with_its_owner_run_and_a_readable_label():
    view = _view(
        ["aa11", "bb22", "cc33"],
        [
            {"id": "aa11", "run_id": CHILD, "path": "output.image_artifact"},
            {"id": "bb22", "run_id": ROOT, "path": "output.report"},
            {"id": "cc33", "run_id": ROOT, "path": "output.scratchpad.node_traces.reason.steps[0].result.metadata._provider_request.payload.messages"},
        ],
    )
    meta = _final_meta(view)
    assert meta["image_artifact"] == {"$artifact": "aa11", "run_id": CHILD}
    assert meta["artifact"] == {"$artifact": "bb22", "run_id": ROOT}
    assert "media" not in meta
    shown = _message_media_artifacts({"role": "assistant", "content": "x", "metadata": meta})
    assert [a["$artifact"] for a in shown] == ["aa11", "bb22"]
    labels = [_artifact_label(a) for a in shown]
    assert labels == ["Image", "Attachment"]
    assert all("aa11" not in label and "bb22" not in label for label in labels)


def test_a_final_built_from_the_run_snapshot_keeps_its_unlisted_refs():
    """No completion record folded (legacy or windowed ledger): the view lists nothing of the
    output, so an unlisted ref may be the answer's image; it is kept, opened through the run."""
    meta = _final_meta(_view(["img9"], [], source="run_output"))
    assert meta["artifact"] == {"$artifact": "img9"}


def test_final_fallback_skips_bookkeeping_refs():
    view = _view([], [
        {"id": "f738", "run_id": ROOT, "path": "output.scratchpad.steps"},
        {"id": "img1", "run_id": ROOT, "path": "output.image_artifact"},
    ])
    view["messages"] = []
    meta = final_fallback_event(view)["meta"]
    assert meta.get("image_artifact") == {"$artifact": "img1", "run_id": ROOT}
    assert "artifact" not in meta and "media" not in meta


def test_label_never_shows_the_id_and_names_kind_and_size():
    assert _artifact_label({"$artifact": "7c8efef3e20a049b68dcbb8c88b9f863"}) == "Attachment"
    assert _artifact_label({"$artifact": "x", "content_type": "text/plain", "size_bytes": 4340}) == "Document · 4.2 KB"
    assert _artifact_label({"$artifact": "x", "content_type": "audio/wav"}) == "Audio"
    assert _artifact_label({"$artifact": "x", "filename": "tts.wav"}) == "tts.wav"


def test_a_generated_image_first_referenced_in_the_output_media_list_is_an_image() -> None:
    """2026-11-18 (Windows, FLUX.2 klein through the image-generation flow): the view names an
    artifact by its EARLIEST reference, here `outputs.image[0].artifact_ref`. It was attached as
    a plain file, so the replayed answer showed no picture (AbstractCode's web UI did)."""
    from abstractassistant.gateway.replay_view import _media_meta

    arts = {"img": {"id": "img", "run_id": "run-1", "path": "outputs.image[0].artifact_ref"},
            "vid": {"id": "vid", "run_id": "run-1", "path": "outputs.video[0].artifact_ref"},
            "doc": {"id": "doc", "run_id": "run-1", "path": "outputs.files[0].artifact_ref"}}
    meta: dict = {}
    _media_meta(meta, ["img", "vid", "doc"], arts, source="ledger")
    assert meta["image_artifact"] == {"$artifact": "img", "run_id": "run-1"}
    assert meta["video_artifact"] == {"$artifact": "vid", "run_id": "run-1"}
    assert meta["artifact"] == {"$artifact": "doc", "run_id": "run-1"}  # not a medium: a file, as before


def test_a_reopened_conversation_keeps_the_picture_its_answer_generated() -> None:
    """2026-11-18: reopening a conversation rebuilds it from the gateway's session turns. A turn
    lists every artifact of its run; the generated picture was dropped with the bookkeeping, so
    the answer came back as text only (the web apps showed the picture)."""
    from abstractassistant.gateway.history_seed import seed_messages_from_history_bundle

    run = "be6bcfee-run"
    bundle = {"root_run_id": run, "session": {"turns": [{
        "run_id": run, "prompt": "generate an image of a ship", "answer": "Generating an image of a ship.",
        "created_at": "2026-11-18T02:03:48+00:00", "updated_at": "2026-11-18T02:05:33+00:00",
        "artifacts": [
            {"artifact_id": "snap", "run_id": run, "content_type": "application/json", "tags": {"kind": "workflow_snapshot"}},
            {"artifact_id": "trace", "run_id": run, "content_type": "application/json", "tags": {"kind": "json", "source": "run_output_offload"}},
            {"artifact_id": "img", "run_id": run, "content_type": "image/png", "size_bytes": 1509739,
             "tags": {"kind": "generated_media", "modality": "image", "task": "image_generation"}},
        ],
    }]}}
    answer = next(m for m in seed_messages_from_history_bundle(bundle) if m["role"] == "assistant")
    media = _message_media_artifacts(answer)
    assert [(m["$artifact"], m["modality"], m["run_id"]) for m in media] == [("img", "image", run)]
