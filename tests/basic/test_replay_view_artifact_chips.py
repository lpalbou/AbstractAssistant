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


def _view(artifact_ids, artifacts):
    return {
        "root_run_id": ROOT,
        "status": "completed",
        "runs": [{"run_id": ROOT, "status": "completed"}],
        "activities": [],
        "artifacts": artifacts,
        "messages": [
            {"id": f"{ROOT}:final", "role": "assistant", "kind": "final", "text": "Daily news.",
             "run_id": ROOT, "order": ["2026-10-28T13:15:49+00:00", ROOT, 6], "artifact_ids": artifact_ids},
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
