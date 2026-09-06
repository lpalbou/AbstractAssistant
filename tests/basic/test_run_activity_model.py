"""RunActivityModel honesty rules + RunActivityCard contract (headless)."""

from __future__ import annotations

import dataclasses
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from abstractassistant.theme import THEME
from abstractassistant.ui.activity import (
    ACTIVITY_QSS,
    ActivityStep,
    ActivityStepList,
    RunActivityCard,
    RunActivityModel,
    ThinkingDotsWidget,
    format_duration,
)


_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class _Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


T0 = "2026-09-05T10:00:00+00:00"
T1 = "2026-09-05T10:00:01.800+00:00"
T2 = "2026-09-05T10:00:42+00:00"


def _cycle(n: int, ts: str = "") -> dict:
    payload = {"type": "cycle", "iteration": n, "run_id": "r1"}
    if ts:
        payload["ts"] = ts
    return payload


def _tool_started(*tools: dict) -> dict:
    return {"type": "tool_started", "tools": list(tools), "run_id": "r1"}


def _tool_result(name: str, *, call_id=None, success=True, content="ok", error=None, ts="") -> dict:
    return {
        "type": "tool",
        "run_id": "r1",
        "message": {
            "role": "tool",
            "content": content,
            "ts": ts,
            "metadata": {"name": name, "call_id": call_id, "success": success, "error": error},
        },
    }


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_header_before_any_event_and_for_reattached_runs() -> None:
    model = RunActivityModel("r1")
    assert model.header_text() == "Running…"
    assert model.header_tone() == "thinking"
    assert model.current_step() is None

    reattached = RunActivityModel("r1", reattached=True)
    assert reattached.header_text() == "Reattached — following the run"
    assert reattached.elapsed_s() is None
    assert reattached.summary()["elapsed_ms"] is None


@pytest.mark.basic
def test_cycle_opens_running_step_and_marks_previous_cycle_ok() -> None:
    model = RunActivityModel("r1")
    assert model.apply_event(_cycle(1, T0)) == ["cycle:1"]
    step = model.steps[0]
    assert (step.kind, step.status, step.tone) == ("cycle", "running", "thinking")
    assert step.title_plain == "Thinking · cycle 1"
    assert step.started_ts == T0
    assert model.header_text() == "Thinking · cycle 1"

    changed = model.apply_event(_cycle(2))
    assert changed == ["cycle:1", "cycle:2"]
    assert model.step("cycle:1").status == "ok"
    assert model.step("cycle:2").status == "running"
    assert model.step("cycle:2").started_ts == ""  # no ts → nothing fabricated
    assert model.header_text() == "Thinking · cycle 2"


@pytest.mark.basic
def test_cycle_result_closes_cycle_with_prose_detail_and_never_prompt_text() -> None:
    model = RunActivityModel("r1")
    model.apply_event(_cycle(1, T0))
    content = "## Plan\n\nI **should** check the [README](http://x.y) first. " + "x" * 200
    changed = model.apply_event(
        {"type": "cycle_result", "iteration": 1, "content": content, "reasoning": "why", "ts": T2}
    )
    assert changed == ["cycle:1"]
    step = model.step("cycle:1")
    assert step.status == "ok"
    assert step.ended_ts == T2
    assert step.detail.startswith("Plan. I should check the README first.")
    assert "**" not in step.detail and "http" not in step.detail
    assert len(step.detail) <= 90 and step.detail.endswith("…")
    assert step.payload["content"] == content and step.payload["reasoning"] == "why"
    # The run_activity prompt echo (finding 21) never becomes a step.
    assert model.apply_event({"type": "run_activity", "summary": "Running (abc): the user prompt"}) == []
    assert all("the user prompt" not in s.title_plain for s in model.steps)


@pytest.mark.basic
def test_tool_started_opens_one_step_per_entry_with_call_id_or_name_counter() -> None:
    model = RunActivityModel("r1")
    changed = model.apply_event(
        _tool_started(
            {"name": "read_file", "arguments": {"file_path": "README.md"}, "call_id": "c1", "ts": T0},
            {"name": "web_search", "arguments_preview": "{'query': 'x'}"},
            {"name": "web_search", "arguments_text": '{"query": "y"}'},
        )
    )
    assert changed == ["tool:c1", "tool:web_search#1", "tool:web_search#2"]
    first = model.step("tool:c1")
    assert (first.kind, first.status, first.tone) == ("tool", "running", "tool")
    assert first.title_plain == 'read_file(file_path="README.md")'
    assert "<span" in first.title_html and "README.md" in first.title_html
    assert first.started_ts == T0
    assert first.payload["arguments_text"] == '{"file_path": "README.md"}'
    assert model.step("tool:web_search#2").title_plain == 'web_search(query="y")'
    assert model.header_text() == 'Running web_search(query="y")'
    assert model.header_tone() == "tool"


@pytest.mark.basic
def test_tool_result_matches_call_id_then_first_running_tool_by_name() -> None:
    model = RunActivityModel("r1")
    model.apply_event(
        _tool_started(
            {"name": "web_search", "arguments": {"query": "a"}},
            {"name": "web_search", "arguments": {"query": "b"}},
            {"name": "read_file", "arguments": {"file_path": "x"}, "call_id": "c9"},
        )
    )
    # No call_id → FIFO by name: the OLDEST running web_search closes first.
    assert model.apply_event(_tool_result("web_search", content="second")) == ["tool:web_search#1"]
    assert model.step("tool:web_search#1").status == "ok"
    assert model.step("tool:web_search#2").status == "running"
    assert model.apply_event(_tool_result("web_search")) == ["tool:web_search#2"]
    # call_id wins over name order.
    assert model.apply_event(_tool_result("read_file", call_id="c9")) == ["tool:c9"]
    # A result with no matching start (reattach) still produces a closed step.
    changed = model.apply_event(_tool_result("list_files", call_id="c77", content="a\nb"))
    assert changed == ["tool:c77"]
    assert model.step("tool:c77").status == "ok"


@pytest.mark.basic
def test_tool_result_status_and_detail_follow_metadata_success() -> None:
    model = RunActivityModel("r1")
    model.apply_event(
        _tool_started(
            {"name": "a", "call_id": "1"}, {"name": "b", "call_id": "2"}, {"name": "c", "call_id": "3"}
        )
    )
    model.apply_event(_tool_result("a", call_id="1", success=True, content="line one\nline two"))
    model.apply_event(_tool_result("b", call_id="2", success=False, content="x", error="rate limited\nretry later"))
    model.apply_event(_tool_result("c", call_id="3", success=None, content="k" * 200))
    ok, failed, unknown = model.step("tool:1"), model.step("tool:2"), model.step("tool:3")
    assert (ok.status, ok.tone, ok.detail) == ("ok", "ok", "line one line two")
    assert (failed.status, failed.tone, failed.detail) == ("failed", "danger", "rate limited")
    assert (unknown.status, unknown.tone) == ("info", "info")
    assert len(unknown.detail) <= 90 and unknown.detail.endswith("…")
    assert model.summary()["tool_failures"] == 1


@pytest.mark.basic
def test_duration_only_when_both_timestamps_parse() -> None:
    model = RunActivityModel("r1")
    model.apply_event(
        _tool_started(
            {"name": "a", "call_id": "1", "ts": T0},
            {"name": "b", "call_id": "2"},  # no start ts
            {"name": "c", "call_id": "3", "ts": T0},
        )
    )
    model.apply_event(_tool_result("a", call_id="1", ts=T1))
    model.apply_event(_tool_result("b", call_id="2", ts=T1))
    model.apply_event(_tool_result("c", call_id="3", ts=""))  # no end ts
    assert model.step("tool:1").duration_text() == "1.8 s"
    assert model.step("tool:2").duration_text() == ""
    assert model.step("tool:3").duration_text() == ""
    assert model.step("tool:2").duration_ms() is None

    model.apply_event(_cycle(1, T0))
    model.apply_event({"type": "cycle_result", "iteration": 1, "content": "x", "ts": T2})
    assert model.step("cycle:1").duration_text() == "0:42"


@pytest.mark.basic
def test_format_duration_copy() -> None:
    assert format_duration(None) == ""
    assert format_duration(1800) == "1.8 s"
    assert format_duration(42_000) == "0:42"
    assert format_duration(65_000) == "1:05"
    assert format_duration(3_723_000) == "1:02:03"


@pytest.mark.basic
def test_tool_request_opens_wait_and_resolve_wait_outcomes() -> None:
    model = RunActivityModel("r1")
    calls = [{"name": "execute_command", "arguments": {"command": "ls"}}, {"name": "read_file"}, {"name": "x"}]
    changed = model.apply_event({"type": "tool_request", "tool_calls": calls, "wait_key": "tool_calls:r1:act"})
    assert changed == ["wait:tool_calls:r1:act:1"]
    step = model.steps[-1]
    assert (step.kind, step.status, step.tone) == ("wait_approval", "waiting", "attention")
    assert step.title_plain == "Needs your approval · execute_command +2 more"
    assert model.header_text() == "Needs your approval · execute_command +2 more"
    assert model.header_tone() == "attention"
    assert step.payload["tool_calls"] == calls

    # Deferred: the row closes as info but the run is still parked on it.
    assert model.resolve_wait("tool_calls:r1:act", "deferred") == step.step_id
    assert (step.status, step.title_plain) == ("info", "Deferred — run is waiting")
    assert step.is_pending_wait and model.current_step() is step
    assert model.header_text() == "Needs your approval · execute_command +2 more"

    assert model.resolve_wait("tool_calls:r1:act", "approved") == step.step_id
    assert (step.status, step.tone, step.title_plain) == ("ok", "ok", "Approved by you")
    assert not step.is_pending_wait and model.current_step() is None

    # The SAME stable key is a NEW question next time (occurrence counter).
    model.apply_event({"type": "tool_request", "tool_calls": calls[:1], "wait_key": "tool_calls:r1:act"})
    second = model.steps[-1]
    assert second.step_id == "wait:tool_calls:r1:act:2"
    assert second.title_plain == "Needs your approval · execute_command"
    model.resolve_wait("tool_calls:r1:act", "denied")
    assert (second.status, second.tone, second.title_plain) == ("denied", "danger", "Denied by you")
    assert step.status == "ok"  # the earlier occurrence is untouched

    model.apply_event({"type": "tool_request", "tool_calls": calls[:2], "wait_key": "tool_calls:r1:act"})
    model.resolve_wait("tool_calls:r1:act", "auto_approved")
    third = model.steps[-1]
    assert third.status == "ok"
    assert third.title_plain == "Auto-approved (trusted in this chat) · execute_command +1 more"
    assert model.header_text() == "Auto-approved · execute_command"
    assert model.resolve_wait("nope", "approved") is None
    assert model.summary()["waits"] == 3


@pytest.mark.basic
def test_ask_user_opens_wait_input_and_answer_outcomes() -> None:
    model = RunActivityModel("r1")
    prompt = "Which **folder** should I use?\n\n" + "a" * 100
    changed = model.apply_event({"type": "ask_user", "prompt": prompt, "wait_key": "user:r1:ask", "step_id": "s7"})
    assert changed == ["wait:user:r1:ask:s7"]
    step = model.steps[-1]
    assert (step.kind, step.status) == ("wait_input", "waiting")
    assert step.title_plain.startswith("Asked you: “Which folder should I use?")
    assert step.title_plain.endswith("…”") and len(step.title_plain) <= len("Asked you: “”") + 80
    assert model.header_text() == "Waiting for your answer"

    model.resolve_wait("user:r1:ask", "dismissed")
    assert (step.status, step.title_plain) == ("info", "Dismissed — run is waiting")
    assert model.header_text() == "Waiting for your answer"  # still parked
    model.resolve_wait("user:r1:ask", "answered")
    assert (step.status, step.tone, step.title_plain) == ("ok", "ok", "You answered")


@pytest.mark.basic
def test_offline_status_opens_net_step_and_thinking_reconnects_it() -> None:
    model = RunActivityModel("r1")
    model.apply_event(_cycle(1))
    assert model.apply_event({"type": "status", "status": "offline", "reason": "connection refused"}) == ["net:1"]
    step = model.step("net:1")
    assert (step.kind, step.status, step.tone) == ("offline", "running", "offline")
    assert step.title_plain == "Gateway unreachable — retrying"
    assert step.detail == "connection refused"
    assert model.header_text() == "Gateway unreachable — retrying"
    assert model.header_tone() == "offline"
    # A repeated offline mark updates the same step instead of stacking rows.
    assert model.apply_event({"type": "status", "status": "offline", "reason": "timeout"}) == ["net:1"]
    assert len([s for s in model.steps if s.kind == "offline"]) == 1

    assert model.apply_event({"type": "status", "status": "thinking"}) == ["net:1"]
    assert (step.status, step.tone, step.title_plain) == ("ok", "ok", "Reconnected")
    assert model.header_text() == "Thinking · cycle 1"  # back to the live step


@pytest.mark.basic
def test_other_statuses_create_no_steps() -> None:
    model = RunActivityModel("r1")
    for text in ("thinking", "completed", "Working", "ready"):
        assert model.apply_event({"type": "status", "status": text}) == []
    assert model.apply_event({"type": "history_seeded", "changed": True}) == []
    assert model.apply_event({"type": "user_message_appended", "content": "hi"}) == []
    assert model.apply_event({"type": "unknown_kind"}) == []
    assert model.apply_event("not a dict") == []
    assert model.steps == []


@pytest.mark.basic
def test_error_and_replay_degraded_become_danger_steps() -> None:
    model = RunActivityModel("r1")
    assert model.apply_event({"type": "error", "error": "step failed: boom"}) == ["err:1"]
    err = model.step("err:1")
    assert (err.kind, err.status, err.tone, err.title_plain) == ("error", "failed", "danger", "step failed: boom")
    assert model.header_text() == "step failed: boom" and model.header_tone() == "danger"
    assert model.apply_event({"type": "replay_degraded", "message": "Gateway replay is degraded."}) == ["err:2"]
    replay = model.step("err:2")
    assert (replay.kind, replay.status, replay.tone) == ("replay", "failed", "danger")


@pytest.mark.basic
def test_final_assistant_finishes_model_without_claiming_unseen_outcomes() -> None:
    clock = _Clock(100.0)
    model = RunActivityModel("r1", clock=clock)
    model.apply_event(_cycle(1))
    model.apply_event(_tool_started({"name": "slow", "call_id": "s"}))
    clock.now = 141.0
    changed = model.apply_event({"type": "assistant", "final": True, "content": "done"})
    assert sorted(changed) == ["cycle:1", "tool:s"]
    assert model.finished and model.final_status == "completed"
    assert model.header_text() == "Done" and model.header_tone() == "ok"
    assert model.step("cycle:1").status == "ok"
    assert model.step("tool:s").status == "info"  # no result observed → not "ok"
    clock.now = 999.0
    assert model.elapsed_s() == 41.0  # frozen at finish
    assert model.summary() == {
        "cycles": 1,
        "tools": 1,
        "tool_failures": 0,
        "waits": 0,
        "elapsed_ms": 41000,
        "steps": 2,
    }
    assert model.summary_text() == "1 cycle · 1 tool · 0:41"
    # Non-final assistant chunks change nothing.
    fresh = RunActivityModel("r2")
    assert fresh.apply_event({"type": "assistant", "final": False, "content": "…"}) == []
    assert not fresh.finished
    fresh.finish("stopped")
    assert fresh.header_text() == "Stopped"


@pytest.mark.basic
def test_note_local_header_copy_and_pause_lifecycle() -> None:
    model = RunActivityModel("r1")
    model.apply_event(_cycle(1))
    steer_id = model.note_local("steer", "please focus on the failing tests " + "z" * 100)
    steer = model.step(steer_id)
    assert steer.kind == "steer" and steer.status == "info"
    assert steer.title_plain.startswith("You steered: “please focus on the failing tests")
    assert model.header_text().startswith("Steering: “please focus on the failing tests")
    assert model.header_text().endswith("…”")

    pause_id = model.note_local("pause", "")
    pause = model.step(pause_id)
    assert (pause.kind, pause.tone, pause.status) == ("pause", "paused", "running")
    assert model.header_text() == "Pause requested…" and model.header_tone() == "paused"
    assert model.apply_event({"type": "status", "status": "paused"}) == [pause_id]
    assert (pause.status, pause.title_plain) == ("info", "Paused")
    assert model.header_text() == "Paused"

    resume_id = model.note_local("resume", "")
    assert model.step(resume_id).kind == "resume"
    assert model.header_text() == "Resumed"
    model.apply_event(_tool_started({"name": "read_file", "call_id": "c1"}))
    assert model.header_text() == "Running read_file()"

    stop_id = model.note_local("stop", "Stopping…")
    assert model.step(stop_id).kind == "stop"
    assert model.header_text() == "Stopping…"
    # Explicit tone/status still win over the kind defaults.
    custom = model.step(model.note_local("pause", "Pause was not accepted by the gateway", tone="danger", status="failed"))
    assert (custom.tone, custom.status) == ("danger", "failed")


@pytest.mark.basic
def test_to_log_entries_match_run_activity_dialog_kinds() -> None:
    model = RunActivityModel("r1")
    model.apply_event(_cycle(1, T0))
    model.apply_event({"type": "cycle_result", "iteration": 1, "content": "thought", "reasoning": "why", "ts": T1})
    model.apply_event(_tool_started({"name": "read_file", "arguments": {"file_path": "a.md"}, "call_id": "c1", "ts": T1}))
    model.apply_event(_tool_result("read_file", call_id="c1", content="# a", ts=T2))
    model.apply_event({"type": "tool_request", "tool_calls": [{"name": "x"}], "wait_key": "k"})
    model.apply_event({"type": "status", "status": "offline", "reason": "down"})
    model.note_local("steer", "go")
    entries = model.to_log_entries()
    assert [e["kind"] for e in entries] == ["cycle", "thinking", "tools", "tool_result", "waiting", "status", "status"]
    assert entries[0] == {"kind": "cycle", "n": 1, "ts": T0}
    assert entries[1] == {"kind": "thinking", "n": 1, "content": "thought", "reasoning": "why", "ts": T1}
    assert entries[2]["tools"] == [
        {"name": "read_file", "arguments_text": '{"file_path": "a.md"}', "arguments_preview": '{"file_path": "a.md"}'}
    ]
    assert entries[2]["ts"] == T1
    assert entries[3] == {"kind": "tool_result", "name": "read_file", "preview": "# a", "ts": T2}
    assert entries[4] == {"kind": "waiting", "text": "Needs your approval · x", "ts": ""}
    assert entries[5]["text"] == "Gateway unreachable — retrying · down"
    assert entries[6]["text"] == "You steered: “go”"


@pytest.mark.basic
def test_steps_are_bounded_dropping_oldest_closed_steps_first() -> None:
    model = RunActivityModel("r1", max_steps=10)
    # A wait nobody answered stays open across cycles (a running TOOL would
    # not: the next cycle closes it as info, see test_cycle_* rules).
    model.apply_event({"type": "tool_request", "tool_calls": [{"name": "x"}], "wait_key": "k"})
    for n in range(1, 15):
        model.apply_event(_cycle(n))
    assert len(model.steps) <= 10
    assert model.step("wait:k:1") is not None  # open steps survive the cut
    assert model.steps[0].step_id == "wait:k:1"
    assert model.step("cycle:1") is None
    assert model.step("cycle:14").status == "running"


@pytest.mark.basic
def test_activity_step_dataclass_defaults() -> None:
    step = ActivityStep(step_id="x:1", kind="cycle", title_plain="t")
    assert (step.title_html, step.tone, step.status, step.detail, step.payload) == ("", "info", "info", "", {})
    assert step.duration_ms() is None and step.duration_text() == ""
    assert dataclasses.is_dataclass(step)


# --------------------------------------------------------------------------- #
# Widgets (headless)
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_run_activity_card_shows_and_elides_status_text_like_thinking_card() -> None:
    _app()
    card = RunActivityCard(status_text="Running assistant workflow...")
    assert card.objectName() == "thinkingIndicator"
    assert card._bubble.objectName() == "thinkingBubble"
    assert card._status.objectName() == "thinkingStatusText"
    assert card._status.text() == "Running assistant workflow..."
    assert card._bubble.property("tone") == "thinking"

    card.set_status("")
    assert card._status.isHidden()

    long_text = "Tool: execute_command command=" + "x" * 400
    card.sync_to_viewport_width(320)
    assert card._max_text_px == 224
    card.set_status(long_text)
    assert card._status.text().endswith("…")
    assert len(card._status.text()) < len(long_text)

    card.set_status("Needs your approval · execute_command", tone="attention")
    assert card._bubble.property("tone") == "attention"
    assert card._status.property("tone") == "attention"
    card.set_status("x", tone="bogus")
    assert card._bubble.property("tone") == "thinking"
    assert card._elapsed.isHidden()  # no model → no elapsed claim


@pytest.mark.basic
def test_run_activity_card_set_model_builds_recent_rows_and_more_link() -> None:
    _app()
    model = RunActivityModel("r1")
    for n in range(1, 7):
        model.apply_event(_cycle(n))
    card = RunActivityCard()
    assert not card.is_expanded() and card._steps_host.isHidden()
    card.set_model(model)
    assert list(card._rows.keys()) == ["cycle:3", "cycle:4", "cycle:5", "cycle:6"]
    assert card._more_link.objectName() == "activityMoreLink"
    assert card._more_link.text() == "2 earlier steps…"
    assert not card._more_link.isHidden()
    row = card._rows["cycle:6"]
    assert row.objectName() == "activityStepRow"
    assert row.property("status") == "running" and row.height() == 22
    assert row._title.objectName() == "activityStepTitle"
    assert row._meta.objectName() == "activityStepMeta"
    assert row.toolTip() == "Thinking · cycle 6"

    card.set_expanded(True)
    assert card.is_expanded() and not card._steps_host.isHidden()
    card._more_link.click()
    assert len(card._rows) == 6
    # The link stays: it folds the earlier steps back away.
    assert not card._more_link.isHidden()
    assert card._more_link.text() == "Show only the last 4 steps"
    card._more_link.click()
    assert list(card._rows.keys()) == ["cycle:3", "cycle:4", "cycle:5", "cycle:6"]
    assert card._more_link.text() == "2 earlier steps…"

    # Incremental refresh updates rows in place when the visible set is unchanged.
    model.apply_event({"type": "cycle_result", "iteration": 6, "content": "done", "ts": T2})
    before = card._rows["cycle:6"]
    card.refresh(["cycle:6"])
    assert card._rows["cycle:6"] is before and before.property("status") == "ok"
    assert not card._elapsed.isHidden()
    assert re.fullmatch(r"\d+:\d\d", card._elapsed.text())

    reattached = RunActivityModel("r2", reattached=True)
    card.set_model(reattached)
    assert card._elapsed.isHidden()
    card.set_model(None)
    assert card._rows == {} and card._more_link.isHidden()


@pytest.mark.basic
def test_run_activity_card_review_link_emits_step_id() -> None:
    _app()
    model = RunActivityModel("r1")
    model.apply_event({"type": "tool_request", "tool_calls": [{"name": "execute_command"}], "wait_key": "k"})
    model.apply_event({"type": "ask_user", "prompt": "Which?", "wait_key": "q"})
    card = RunActivityCard()
    card.set_model(model)
    received: list = []
    card.review_requested.connect(received.append)
    approval_row = card._rows["wait:k:1"]
    answer_row = card._rows["wait:q:1"]
    assert approval_row._link.text() == "Review" and not approval_row._link.isHidden()
    assert answer_row._link.text() == "Answer"
    approval_row._link.click()
    answer_row._link.click()
    assert received == ["wait:k:1", "wait:q:1"]
    # A settled wait loses its link; a deferred one keeps it (the run is parked).
    model.resolve_wait("k", "approved")
    model.resolve_wait("q", "dismissed")
    card.refresh(["wait:k:1", "wait:q:1"])
    assert approval_row._link.isHidden()
    assert not answer_row._link.isHidden()


@pytest.mark.basic
def test_run_activity_card_controls_emit_signals() -> None:
    _app()
    card = RunActivityCard()
    fired: list = []
    card.pause_requested.connect(lambda: fired.append("pause"))
    card.resume_requested.connect(lambda: fired.append("resume"))
    card.stop_requested.connect(lambda: fired.append("stop"))
    card.log_requested.connect(lambda: fired.append("log"))
    for button in (card.pause_button, card.log_button, card.expand_button, card.stop_button):
        assert button.objectName() == "iconButton"
        assert (button.width(), button.height()) == (22, 22)
    card.pause_button.click()
    card.set_paused(True)
    assert card.is_paused()
    card.pause_button.click()
    card.log_button.click()
    card.show_stop_button(True)
    card.stop_button.click()
    assert fired == ["pause", "resume", "log", "stop"]
    card.expand_button.click()
    assert card.is_expanded()
    card.expand_button.click()
    assert not card.is_expanded()


@pytest.mark.basic
def test_activity_step_list_shows_every_step_read_only() -> None:
    _app()
    model = RunActivityModel("r1")
    for n in range(1, 8):
        model.apply_event(_cycle(n))
    model.apply_event({"type": "tool_request", "tool_calls": [{"name": "x"}], "wait_key": "k"})
    widget = ActivityStepList(model)
    rows = widget.rows()
    assert len(rows) == 8
    assert widget.objectName() == "activityStepList"
    assert all(row._link.isHidden() for row in rows)  # read-only: no Review links
    widget.set_model(None)
    assert widget.rows() == []


@pytest.mark.basic
def test_thinking_dots_timer_only_runs_while_visible() -> None:
    _app()
    dots = ThinkingDotsWidget()
    assert dots._timer.interval() == 33
    assert not dots._timer.isActive()
    dots.show()
    assert dots._timer.isActive()
    dots.hide()
    assert not dots._timer.isActive()


@pytest.mark.basic
def test_activity_qss_uses_theme_tokens_only() -> None:
    assert "qlineargradient" not in ACTIVITY_QSS and "qradialgradient" not in ACTIVITY_QSS
    theme_values = {
        str(value).lower() for value in dataclasses.asdict(THEME).values() if isinstance(value, str)
    }
    hexes = set(re.findall(r"#[0-9a-fA-F]{6}\b", ACTIVITY_QSS))
    assert hexes, "the stylesheet paints nothing"
    assert {h.lower() for h in hexes} <= theme_values
    for selector in (
        'QFrame#thinkingBubble[tone="attention"]',
        'QFrame#thinkingBubble[tone="paused"]',
        'QFrame#thinkingBubble[tone="offline"]',
        'QFrame#thinkingBubble[tone="ok"]',
        'QFrame#thinkingBubble[tone="danger"]',
        'QLabel#thinkingStatusText[tone="attention"]',
        "QLabel#activityElapsed",
        "QFrame#activityStepRow",
        "QLabel#activityStepTitle",
        "QLabel#activityStepMeta",
        "QPushButton#activityMoreLink",
        "QFrame#thinkingBubble QPushButton#iconButton",
    ):
        assert selector in ACTIVITY_QSS, selector
