"""Remote one-off approvals close here too, and the next gate remains discoverable."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtTest import QTest

from abstractassistant.core.attention import AttentionModel
from test_automations import palette, stub  # noqa: F401 (fixtures)


def _event(seq, typ, key, *, run="leaf", step="one", session="phone-session"):
    return {"sequence": seq, "type": typ, "data": {"kind": "approval", "run_id": run,
            "session_id": session, "wait_key": key, "step_id": step,
            "record_key": f"wait:{run}:{key}:{step}"}}


def _prepare(palette):
    window, controller = palette
    controller.active_session_id = "phone-session"
    window._attention = AttentionModel()
    window._pending_user_waits = {}
    window._worker = None
    window._voice_is_speaking = lambda: False
    window._show_thinking_indicator = lambda: False
    return window, controller


@pytest.mark.basic
def test_remote_approval_withdraws_old_sheet_and_the_next_gate_stays_visible(palette, stub):
    window, _ = _prepare(palette)
    window._on_me_event(_event(513, "attention.raised", "first"), False)
    window._open_approval_sheet(tool_calls=[{"name": "read_file", "arguments": {"path": "note.txt"}}],
                                run_id="leaf", wait_key="first", step_id="one")
    sheet = window._approval_sheet
    decisions = []
    sheet.decided.connect(lambda *args: decisions.append(args))
    assert window._tray_feedback_state() == "waiting"
    window._on_me_event(_event(518, "attention.seen", "first"), False)
    assert not window._pending_user_waits and not sheet.isVisible()
    assert window._tray_feedback_state() == "idle"
    window._on_me_event(_event(519, "attention.raised", "second", step="two"), False)
    assert [wait.wait_key for kind, wait in window._attention_targets() if kind == "wait"] == ["second"]
    assert window._tray_feedback_state() == "waiting"
    assert not window.attention_badge.isHidden()
    assert not decisions and not stub.calls("POST", "/api/gateway/commands")


@pytest.mark.basic
def test_a_late_old_step_or_other_run_seen_cannot_withdraw_the_current_gate(palette):
    window, _ = _prepare(palette)
    window._note_user_wait(wait_key="same-key", kind="approval", label="Current", run_id="leaf", step_id="two")
    window._on_me_event(_event(10, "attention.seen", "same-key", step="one"), False)
    window._on_me_event(_event(11, "attention.seen", "same-key", run="old-session-run", step="two", session="old-session"), False)
    assert window._pending_user_waits["same-key"]["step_id"] == "two"
    assert window._tray_feedback_state() == "waiting"


@pytest.mark.basic
def test_remote_question_close_never_answers_or_recreates_a_deferred_question(palette, monkeypatch):
    window, _ = _prepare(palette)
    monkeypatch.setattr(window, "_surface_for_prompt", lambda **kwargs: None)
    resumed = []
    voice = SimpleNamespace(state="listening", pause=lambda: True, resume=lambda: resumed.append(True))
    window._voice_conversation = voice
    payload = {"type": "ask_user", "run_id": "leaf", "wait_key": "ask", "step_id": "one", "prompt": "Which file?"}
    window._open_ask_dialog(payload)
    dialog = window._ask_dialog
    decisions = []
    dialog.finished.connect(lambda *args: decisions.append(args))
    window._deferred_ask_payload = dict(payload)
    window._on_me_event(_event(1, "attention.seen", "ask"), False)
    assert window._ask_dialog is None and not dialog.isVisible()
    assert window._deferred_ask_payload is None and not window._pending_user_waits
    assert decisions == []
    assert resumed == [True]


@pytest.mark.basic
def test_resolving_one_gate_keeps_voice_paused_until_the_last_queued_gate_is_gone(palette):
    window, _ = _prepare(palette)
    resumed = []
    window._voice_conversation = SimpleNamespace(state="listening", pause=lambda: True,
                                                resume=lambda: resumed.append(True))
    for key, step in (("first", "one"), ("second", "two")):
        window._open_approval_sheet(tool_calls=[{"name": "read_file", "arguments": {"path": "note.txt"}}],
                                    run_id="leaf", wait_key=key, step_id=step)
    window._on_me_event(_event(518, "attention.seen", "first"), False)
    assert resumed == [] and window._approval_sheet.current_batch["wait_key"] == "second"
    window._on_me_event(_event(520, "attention.seen", "second", step="two"), False)
    assert resumed == [True] and not window._pending_user_waits


@pytest.mark.basic
def test_resolved_activity_is_neutral_and_does_not_resolve_the_next_gate(palette):
    from abstractassistant.ui.activity import RunActivityModel

    window, _ = _prepare(palette)
    model = window._activity_model = RunActivityModel(run_id="root")
    for key, step in (("first", "one"), ("second", "two")):
        model.apply_event({"type": "tool_request", "run_id": "leaf", "wait_key": key, "step_id": step,
                           "tool_calls": [{"name": "read_file", "arguments": {"path": "note.txt"}}]})
        window._note_user_wait(wait_key=key, kind="approval", label="Read", run_id="leaf", step_id=step)
    window._on_me_event(_event(518, "attention.seen", "first"), False)
    first, second = [step for step in model.steps if step.kind == "wait_approval"]
    assert first.title_plain == "Request resolved" and first.status == "info"
    assert second.status == "waiting" and "second" in window._pending_user_waits


@pytest.mark.basic
@pytest.mark.parametrize("decision", ["approved", "denied"])
def test_the_echo_of_a_local_decision_does_not_replace_its_activity_outcome(palette, decision):
    from abstractassistant.ui.activity import RunActivityModel

    window, _ = _prepare(palette)
    model = window._activity_model = RunActivityModel(run_id="root")
    model.apply_event({"type": "tool_request", "run_id": "leaf", "wait_key": "first", "step_id": "one",
                       "tool_calls": [{"name": "read_file", "arguments": {"path": "note.txt"}}]})
    model.resolve_wait("first", decision)
    step = next(step for step in model.steps if step.kind == "wait_approval")
    previous = (step.title_plain, step.status, dict(step.payload))
    window._on_me_event(_event(518, "attention.seen", "first"), False)
    assert (step.title_plain, step.status, step.payload) == previous


@pytest.mark.basic
def test_attention_open_uses_validated_root_even_when_the_session_and_cached_run_are_unchanged(palette, monkeypatch):
    window, controller = _prepare(palette)
    monkeypatch.setattr(controller, "last_run_id", lambda: "root")
    monkeypatch.setattr(controller, "sync_session_from_gateway", lambda: {"changed": False}, raising=False)
    monkeypatch.setattr(controller, "probe_reattach_candidate", lambda: {"run_id": "root", "status": "waiting"})
    captured = []
    window.reattach_candidate.disconnect()
    window.reattach_candidate.connect(captured.append)
    window._attachment_backfill_running = False
    window._on_attention_open({"live": True, "session_id": "phone-session", "run_id": "leaf", "root_run_id": "root"})
    end = time.monotonic() + 2
    while not captured and time.monotonic() < end:
        QTest.qWait(10)
    assert window.isVisible() and len(captured) == 1
    assert captured[0]["run_id"] == "root" and captured[0]["session_id"] == "phone-session"
    assert captured[0]["attention_request"] is window._attention_reattach_request


@pytest.mark.basic
def test_clicking_the_second_gate_follows_its_parent_root_and_displays_it_without_answering(palette, stub, monkeypatch):
    window, controller = _prepare(palette)
    reads, attached, answers = [], [], []

    class Gateway:
        def get_run(self, run_id):
            reads.append(run_id)
            return {"run_id": run_id, "session_id": "phone-session", "status": "waiting",
                    "waiting": {"wait_key": "second" if run_id == "leaf" else "subworkflow:child"},
                    "parent_run_id": {"leaf": "parent", "parent": "root", "root": None}[run_id]}

    class Worker(QObject):
        event_emitted = pyqtSignal(object)
        error_occurred = pyqtSignal(str)
        warning_occurred = pyqtSignal(str)
        finished = pyqtSignal()

        def start(self):
            QTimer.singleShot(0, lambda: self.event_emitted.emit({"type": "tool_request", "run_id": "leaf",
                "wait_key": "second", "step_id": "two", "tool_calls": [{"name": "read_file", "arguments": {"path": "note.txt"}}]}))

        def provide_tool_approval(self, *args, **kwargs):
            answers.append((args, kwargs))

    worker = Worker()
    monkeypatch.setattr(controller, "llm_manager", SimpleNamespace(gateway_client=lambda: Gateway()), raising=False)
    monkeypatch.setattr(controller, "last_run_id", lambda: "root")
    monkeypatch.setattr(controller, "sync_session_from_gateway", lambda: {"changed": False}, raising=False)
    monkeypatch.setattr(controller, "probe_reattach_candidate", lambda: {"run_id": "root", "status": "waiting"})
    monkeypatch.setattr(controller, "build_attach_worker", lambda rid: (attached.append(rid) or worker), raising=False)
    monkeypatch.setattr(controller, "should_auto_approve_tool_batch", lambda calls: False, raising=False)
    monkeypatch.setattr(window, "_surface_for_prompt", lambda **kwargs: None)
    window._attachment_backfill_running = False
    window._on_me_event(_event(519, "attention.raised", "second", step="two"), False)
    window._open_attention()
    end = time.monotonic() + 3
    while "second" not in window._pending_user_waits and time.monotonic() < end:
        QTest.qWait(10)
    assert attached == ["root"] and window._worker is worker
    assert window._pending_user_waits["second"]["step_id"] == "two"
    assert window._approval_sheet.current_batch["wait_key"] == "second"
    assert window._approval_sheet.isVisible()
    assert reads == ["leaf", "leaf", "parent", "root"]
    assert answers == [] and not stub.calls("POST", "/api/gateway/commands")


@pytest.mark.basic
def test_attention_open_does_not_attach_an_unrelated_latest_root(palette, monkeypatch):
    window, controller = _prepare(palette)
    monkeypatch.setattr(controller, "last_run_id", lambda: "other-root")
    monkeypatch.setattr(controller, "sync_session_from_gateway", lambda: {"changed": False}, raising=False)
    monkeypatch.setattr(controller, "probe_reattach_candidate", lambda: {"run_id": "other-root", "status": "waiting"})
    captured = []
    window.reattach_candidate.disconnect()
    window.reattach_candidate.connect(captured.append)
    window._attachment_backfill_running = False
    window._on_attention_open({"live": True, "session_id": "phone-session", "run_id": "leaf", "root_run_id": "expected-root"})
    end = time.monotonic() + 2
    while window._attachment_backfill_running and time.monotonic() < end:
        QTest.qWait(10)
    QTest.qWait(30)
    assert captured == []


@pytest.mark.basic
def test_switching_sessions_sets_the_attention_root_guard_before_any_sync_starts(palette, monkeypatch):
    window, controller = _prepare(palette)
    started = []
    monkeypatch.setattr(controller, "switch_session", lambda sid: setattr(controller, "active_session_id", sid), raising=False)
    monkeypatch.setattr(window, "_sync_session_from_gateway", lambda: started.append(window._attention_reattach_request))
    window._on_attention_open({"live": True, "session_id": "new-phone-session", "root_run_id": "expected-root"})
    assert started and all(request[:2] == ("new-phone-session", "expected-root") for request in started)


@pytest.mark.basic
def test_unknown_wait_ancestry_does_not_open_an_unrelated_session_run(palette, monkeypatch):
    window, controller = _prepare(palette)
    switched = []
    monkeypatch.setattr(controller, "switch_session", switched.append, raising=False)
    window._on_attention_open({"live": True, "session_id": "other-session", "run_id": "unknown-leaf", "root_run_id": ""})
    assert switched == [] and window._worker is None
    assert "Could not confirm the waiting run" in window.banner_label.text()


@pytest.mark.basic
def test_delayed_attention_open_and_reattach_do_not_hijack_a_newly_selected_session(palette):
    window, controller = _prepare(palette)
    token = object()
    window._attention_open_token = token
    controller.active_session_id = "another-session"
    window._on_attention_open({"token": token, "opened_from": "phone-session", "live": True,
                              "session_id": "phone-session", "run_id": "leaf", "root_run_id": "root"})
    window._on_reattach_candidate({"session_id": "phone-session", "run_id": "root", "status": "waiting"})
    assert controller.active_session_id == "another-session" and window._worker is None


@pytest.mark.basic
def test_a_late_old_session_resolution_cannot_clear_a_new_sessions_gate(palette, monkeypatch):
    window, controller = _prepare(palette)
    monkeypatch.setattr(controller, "switch_session", lambda sid: setattr(controller, "active_session_id", sid), raising=False)
    monkeypatch.setattr(window, "_sync_session_from_gateway", lambda: None)
    window._note_user_wait(wait_key="same-key", kind="approval", label="Old", run_id="old-run", step_id="old-step")
    window._switch_to_session("new-session")
    window._note_user_wait(wait_key="same-key", kind="approval", label="New", run_id="new-run", step_id="new-step")
    window._on_me_event(_event(518, "attention.seen", "same-key", run="old-run", step="old-step"), False)
    assert window._pending_user_waits["same-key"]["run_id"] == "new-run"
    assert window._active_session_id() == "new-session" and window._tray_feedback_state() == "waiting"


@pytest.mark.basic
def test_a_late_reattach_request_cannot_replace_a_new_attention_navigation(palette, monkeypatch):
    window, controller = _prepare(palette)
    monkeypatch.setattr(controller, "last_run_id", lambda: "root")
    attached = []
    monkeypatch.setattr(controller, "build_attach_worker", attached.append, raising=False)
    previous = ("phone-session", "root", object())
    window._attention_reattach_request = ("phone-session", "root", object())
    window._on_reattach_candidate({"session_id": "phone-session", "run_id": "root", "status": "waiting",
                                  "attention_request": previous})
    assert attached == [] and window._worker is None
