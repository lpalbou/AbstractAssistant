"""QA 2026-10-28 (g): "1 new result" -> Open showed nothing marked.

An automation opens like a conversation (each run one exchange); the run(s) whose results the person
has not seen are marked "New result" and the view opens on the first of them.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLabel  # noqa: E402

from abstractassistant.core.automations import automations_with_new_results, new_result_indices  # noqa: E402


@pytest.fixture()
def app():
    return QApplication.instance() or QApplication([])


SUMMARY = {
    "automation_id": "a1", "title": "Daily news", "status": "active", "revision": 3,
    "trigger": {"source_id": "schedule", "source_version": 1, "config": {"every": "24h"}},
    "context": {"mode": "independent"},
    "attention": {"unseen_count": 1, "items": [{"index": 3, "kind": "result", "title": "Daily news", "cursor": "c3"}], "waits": []},
    "occurrence_count": 3, "controls": {},
}


def _rows():
    return [
        {"index": i, "run_id": f"r{i}", "status": "completed", "fired_at": f"2026-10-2{i}T08:00:00Z",
         "finished_at": f"2026-10-2{i}T08:01:00Z", "user_turn": "Report the news", "answer": f"News {i}",
         "trigger": {"summary": "every day"}}
        for i in (1, 2, 3)
    ]


@pytest.mark.basic
def test_new_result_indices_come_from_the_unseen_attention_items() -> None:
    assert new_result_indices(SUMMARY) == [3]
    assert new_result_indices({"attention": {"items": []}}) == []
    assert new_result_indices({}) == []


@pytest.mark.basic
def test_the_unseen_run_is_marked_and_the_others_are_not(app) -> None:
    from abstractassistant.ui.automations import AutomationView

    view = AutomationView(render_turn=lambda *a, **k: QLabel(""), bubble_width=lambda *a, **k: 400)
    view.set_summary(SUMMARY)
    view.set_new_runs(new_result_indices(SUMMARY))
    view.set_occurrences(_rows(), next_cursor=None)
    marked = {pair.index: pair.new_badge.isVisibleTo(pair) for pair in view.pairs}
    assert marked == {1: False, 2: False, 3: True}
    assert view.first_new_pair() is view.pairs[-1]
    assert view.scroll_to_first_new() is True
    # Closing the view forgets the marks; nothing new -> no target.
    view.set_new_runs([])
    assert view.first_new_pair() is None
    assert view.scroll_to_first_new() is False


@pytest.mark.basic
def test_open_goes_to_the_automation_with_the_new_result() -> None:
    quiet = {**SUMMARY, "automation_id": "a0", "attention": {"unseen_count": 0, "items": []}}
    assert automations_with_new_results([quiet, SUMMARY, SUMMARY]) == ["a1"]
    assert automations_with_new_results([quiet]) == []
