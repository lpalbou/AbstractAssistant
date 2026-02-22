"""Run state machine unit tests."""

import pytest

from abstractassistant.ui.run_state import RunStateMachine


@pytest.mark.basic
def test_run_state_machine_emits_fallback_when_no_final() -> None:
    states = []
    fallback = []

    sm = RunStateMachine(
        on_state_change=lambda st: states.append(st),
        on_missing_final=lambda: fallback.append(True),
        debug=False,
    )
    sm.start_run()
    sm.mark_completed()

    assert states[0] == "running"
    assert states[-1] == "completed"
    assert fallback == [True]


@pytest.mark.basic
def test_run_state_machine_no_fallback_when_final_exists() -> None:
    states = []
    fallback = []

    sm = RunStateMachine(
        on_state_change=lambda st: states.append(st),
        on_missing_final=lambda: fallback.append(True),
        debug=False,
    )
    sm.start_run()
    sm.mark_final_output()
    sm.mark_completed()

    assert states[0] == "running"
    assert states[-1] == "completed"
    assert fallback == []


@pytest.mark.basic
def test_run_state_machine_speaking_delays_completion() -> None:
    states = []
    fallback = []

    sm = RunStateMachine(
        on_state_change=lambda st: states.append(st),
        on_missing_final=lambda: fallback.append(True),
        debug=False,
    )
    sm.start_run()
    sm.mark_final_output()
    sm.set_speaking(True)
    sm.mark_completed()
    sm.set_speaking(False)

    assert "speaking" in states
    assert states[-1] == "completed"
    assert fallback == []


@pytest.mark.basic
def test_run_state_machine_offline_state() -> None:
    states = []

    sm = RunStateMachine(on_state_change=lambda st: states.append(st), debug=False)
    sm.start_run()
    sm.mark_status("offline")

    assert states[-1] == "offline"
    assert sm.is_run_active()
