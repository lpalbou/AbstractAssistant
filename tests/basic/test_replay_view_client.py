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
    closed = dict(open_view, interaction=None, status="running",
                  open_waits=[w for w in open_view["open_waits"] if not w["person_facing"]])
    events = proj.project(closed)
    assert [e["wait_key"] for e in events if e["type"] == "interaction_closed"] == [open_view["interaction"]["wait_key"]]
    assert not [e for e in proj.project(open_view) if e["type"] == "tool_request"]


def test_final_answer_and_tools_project_once():
    for name in CASES:
        view = load_case(name)["expected_view"]
        proj = ViewProjector()
        first = proj.project(view)
        assert proj.project(view) == [], name
        finals = [e for e in first if e["type"] == "assistant" and e["final"]]
        assert len(finals) <= 1, name
        tool_rows = sum(1 for a in view["activities"] if a.get("kind") == "tool"
                        for r in a.get("tool_calls") or [] if r.get("status") not in ("running", "waiting"))
        assert len([e for e in first if e["type"] == "tool"]) == tool_rows, name


def test_attach_shows_only_the_open_question():
    view = load_case("g_ask_user")["expected_view"]
    proj = ViewProjector()
    proj.suppress_history(view)
    events = proj.project(view)
    # Only the final answer passes (the worker appends it when the seeded transcript lacks it).
    assert not [e for e in events if e["type"] in ("tool", "tool_started", "cycle")]
    assert all(e["final"] for e in events if e["type"] == "assistant")
    if view.get("interaction"):
        assert [e for e in events if e["type"] in ("ask_user", "tool_request")]


def _ask_view(key: str, seq: int, run_id: str = "r1", *, also_open=()):
    it = {"kind": "ask_user", "run_id": run_id, "wait_key": key, "step_id": f"s{seq}", "seq": seq,
          "prompt": f"Q{seq}?", "choices": None, "allow_free_text": True,
          "command": {"type": "resume", "run_id": run_id, "payload": {"wait_key": key}}}
    waits = [{"run_id": run_id, "kind": "ask_user", "wait_key": key, "seq": seq, "person_facing": True}]
    waits += [dict(w, person_facing=True) for w in also_open]
    return {"root_run_id": "root", "status": "waiting", "interaction": it, "open_waits": waits,
            "runs": [], "messages": [], "activities": [], "artifacts": []}


def test_a_second_question_on_the_same_wait_key_is_asked():
    """The runtime reuses a node's wait key for every question: each occurrence is asked."""
    proj = ViewProjector()
    first = proj.project(_ask_view("ask:node", 3))
    assert [e["prompt"] for e in first if e["type"] == "ask_user"] == ["Q3?"]
    # Answered, and the next question arrives in the same delta: close Q3, then ask Q5.
    events = proj.project(_ask_view("ask:node", 5))
    assert [e["type"] for e in events if e["type"] in ("interaction_closed", "ask_user")] == ["interaction_closed", "ask_user"]
    assert [e["prompt"] for e in events if e["type"] == "ask_user"] == ["Q5?"]


def test_an_older_open_approval_stays_open_while_a_newer_one_is_asked():
    proj = ViewProjector()
    a = {"run_id": "c1", "kind": "ask_user", "wait_key": "ask:a", "seq": 2}
    proj.project(_ask_view("ask:a", 2, "c1"))
    events = proj.project(_ask_view("ask:b", 4, "c2", also_open=[a]))
    assert not [e for e in events if e["type"] == "interaction_closed"]  # A is still open
    assert [e["wait_key"] for e in events if e["type"] == "ask_user"] == ["ask:b"]
    # B answered: A is the interaction again; it is still on screen, so it is not asked twice.
    events = proj.project(_ask_view("ask:a", 2, "c1"))
    assert [e["wait_key"] for e in events if e["type"] == "interaction_closed"] == ["ask:b"]
    assert not [e for e in events if e["type"] == "ask_user"]
