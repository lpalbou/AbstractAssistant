"""The desktop's copy of a replay view, checked against AbstractRuntime's conformance cases.

The gateway's `/view` serves `replay(records, snapshots).to_json()` (it runs these same cases in
its own tests). Here the gateway's stream is simulated by the runtime's own incremental fold:
one `view` frame, then one `delta` per chunk of records. The client's copy (`ViewFold`, which
uses the runtime's `apply_delta`) must equal the expected view; skipping a delta must make it
differ, and a delta delivered twice or late must not change it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("abstractruntime.replay")

from abstractruntime.replay import ReplayView, apply_delta  # noqa: E402
from abstractruntime.replay.conformance import case_names, load_case  # noqa: E402

from abstractassistant.gateway.replay_view import ViewFold, ViewOutOfSync, ViewProjector  # noqa: E402

CASES = case_names()


def _frames(name: str, chunk: int = 2):
    """(expected_view, [('view', v0), ('delta', d1), ...]) as the gateway's stream sends them."""
    case = load_case(name)
    root = case["manifest"]["root_run_id"]
    records = []
    for rid in sorted(case["records"]):
        records.extend(case["records"][rid])
    rv = ReplayView(root)
    rv.apply(records[:chunk], runs_by_id=case["runs"])
    frames = [("view", rv.to_json())]
    for i in range(chunk, len(records), chunk):
        frames.append(("delta", rv.apply(records[i:i + chunk])))
    return case["expected_view"], frames


def test_there_are_fifteen_cases():
    assert len(CASES) >= 15


@pytest.mark.parametrize("name", CASES)
def test_folded_view_equals_the_gateway_view(name):
    expected, frames = _frames(name)
    fold = ViewFold()
    for event, data in frames:
        fold.apply_frame(event, data)
    assert fold.view == expected
    assert fold.dropped == 0


@pytest.mark.parametrize("name", CASES)
def test_a_skipped_delta_is_visible(name):
    expected, frames = _frames(name)
    deltas = [i for i, (ev, d) in enumerate(frames) if ev == "delta" and (d.get("messages") or d.get("activities") or d.get("runs"))]
    if not deltas:
        pytest.skip("no delta carrying items in this case")
    # Skip the delta that changes the most items: the copy must no longer equal the view.
    skip = max(deltas, key=lambda i: sum(len(frames[i][1].get(k) or []) for k in ("messages", "activities", "runs", "artifacts")))
    fold = ViewFold()
    for i, (event, data) in enumerate(frames):
        if i != skip:
            fold.apply_frame(event, data)
    # A later delta may re-send an item the skipped one changed; at least the skipped delta's
    # change must be observable somewhere unless every item was re-sent whole later.
    later_ids = {(k, (it.get("run_id") if k == "runs" else it.get("id"))) for _, d in frames[skip + 1:] for k in ("messages", "activities", "runs", "artifacts") for it in d.get(k) or []}
    skipped_ids = {(k, (it.get("run_id") if k == "runs" else it.get("id"))) for k in ("messages", "activities", "runs", "artifacts") for it in frames[skip][1].get(k) or []}
    if skipped_ids <= later_ids:
        pytest.skip("every item of the skipped delta is re-sent later")
    assert fold.view != expected


@pytest.mark.parametrize("name", CASES)
def test_a_delta_delivered_twice_or_late_is_dropped(name):
    expected, frames = _frames(name)
    fold = ViewFold()
    replayed = 0
    for i, (event, data) in enumerate(frames):
        fold.apply_frame(event, data)
        if event == "delta":
            assert fold.apply_frame("delta", data) is False  # the same delta again
            replayed += 1
            if i >= 2 and frames[i - 1][0] == "delta":
                fold.apply_frame("delta", frames[i - 1][1])  # an older one, late
    assert fold.view == expected
    assert fold.dropped >= replayed


def test_without_the_guard_a_late_delta_rolls_the_copy_back():
    # The guard is what keeps the copy right: the runtime's apply_delta alone would regress it.
    rolled_back = 0
    for name in CASES:
        expected, frames = _frames(name, chunk=1)
        view = None
        for event, data in frames:
            view = data if event == "view" else apply_delta(view, data)
        for event, data in frames[1:-1]:
            if apply_delta(view, data) != view:
                rolled_back += 1
                break
    assert rolled_back > 0


def test_a_delta_before_any_view_is_refused():
    with pytest.raises(ViewOutOfSync):
        ViewFold().apply_frame("delta", {"cursor": {"token": "x:1", "runs": {"x": 1}}})


def test_delegated_child_approval_reaches_the_approval_sheet_with_the_child_run():
    case = load_case("a_delegated_child_approval")
    view = case["expected_view"]
    events = ViewProjector().project(view)
    reqs = [e for e in events if e["type"] == "tool_request"]
    assert len(reqs) == 1
    it = view["interaction"]
    assert reqs[0]["run_id"] == it["run_id"] != view["root_run_id"]
    assert reqs[0]["wait_key"] == it["wait_key"]
    assert reqs[0]["command"] == it["command"]
    assert [e for e in events if e["type"] == "status"] == [{"type": "status", "status": "waiting"}]


def test_an_interaction_answered_elsewhere_closes_and_is_never_asked_twice():
    open_view = load_case("a_delegated_child_approval")["expected_view"]
    proj = ViewProjector()
    proj.project(open_view)
    closed = dict(open_view, interaction=None, status="running")
    events = proj.project(closed)
    assert {"type": "interaction_closed", "wait_key": open_view["interaction"]["wait_key"]} in events
    assert not [e for e in proj.project(open_view) if e["type"] == "tool_request"]


def test_final_answer_and_tools_project_once():
    for name in CASES:
        view = load_case(name)["expected_view"]
        proj = ViewProjector()
        first = proj.project(view)
        assert proj.project(view) == [], name
        finals = [e for e in first if e["type"] == "assistant" and e["final"]]
        assert len(finals) <= 1, name
        tool_rows = sum(1 for a in view["activities"] for r in a.get("tool_calls") or [] if r.get("status") not in ("running", "waiting"))
        assert len([e for e in first if e["type"] == "tool"]) == tool_rows, name


def test_attach_shows_only_the_open_question():
    view = load_case("g_ask_user")["expected_view"]
    proj = ViewProjector()
    proj.suppress_history(view)
    events = proj.project(view)
    assert not [e for e in events if e["type"] in ("assistant", "tool", "tool_started", "cycle")]
    if view.get("interaction"):
        assert [e for e in events if e["type"] in ("ask_user", "tool_request")]
