"""Tests for gateway run controller behavior."""

import pytest

from abstractassistant.gateway.client import GatewayStreamIdle
from abstractassistant.gateway.run_controller import GatewayRunController


class _DummyGateway:
    def __init__(self, items):
        self._items = list(items)

    def get_ledger(self, *, run_id: str, after: int, limit: int):
        start = int(after)
        end = start + int(limit)
        slice_items = self._items[start:end]
        return {"items": slice_items, "next_after": start + len(slice_items)}


def test_replay_ledger_picks_latest_subworkflow_wait():
    items = [
        {"wait": {"reason": "subworkflow", "details": {"sub_run_id": "first"}}},
        {"wait": {"reason": "user", "wait_key": "user:1"}},
        {"result": {"wait": {"reason": "subworkflow", "wait_key": "subworkflow:second"}}},
    ]
    ctrl = GatewayRunController(gateway=_DummyGateway(items))
    next_after, sub = ctrl.replay_ledger(run_id="r1", after=0, on_record=lambda _rid, _rec: None)
    assert next_after == 3
    assert sub == "second"


def test_follow_run_replays_final_ledger_after_terminal_status() -> None:
    final_record = {"status": "completed", "result": {"output": {"response": "final answer"}}}

    class _Gateway:
        def __init__(self) -> None:
            self.status_checked = False

        def get_ledger(self, *, run_id: str, after: int, limit: int):
            if not self.status_checked:
                return {"items": [], "next_after": int(after)}
            if int(after) == 0:
                return {"items": [final_record], "next_after": 1}
            return {"items": [], "next_after": int(after)}

        def stream_ledger(self, **kwargs) -> None:
            raise GatewayStreamIdle("idle in test")

        def get_run(self, *, run_id: str) -> dict:
            self.status_checked = True
            return {"status": "completed"}

    records: list[dict] = []
    ctrl = GatewayRunController(
        gateway=_Gateway(),
        terminal_replay_max_wait_s=0.05,
        terminal_replay_interval_s=0.01,
    )

    ctrl.follow_run(
        root_run_id="root",
        on_record=lambda _rid, rec: records.append(rec),
        should_stop=lambda: False,
    )

    assert records == [final_record]


def test_follow_run_waits_for_late_terminal_ledger_row() -> None:
    final_record = {"status": "completed", "result": {"output": {"response": "late answer"}}}

    class _Gateway:
        def __init__(self) -> None:
            self.status_checked = False
            self.terminal_replay_calls = 0

        def get_ledger(self, *, run_id: str, after: int, limit: int):
            if not self.status_checked:
                return {"items": [], "next_after": int(after)}
            self.terminal_replay_calls += 1
            if self.terminal_replay_calls == 2 and int(after) == 0:
                return {"items": [final_record], "next_after": 1}
            return {"items": [], "next_after": int(after)}

        def stream_ledger(self, **kwargs) -> None:
            raise GatewayStreamIdle("idle in test")

        def get_run(self, *, run_id: str) -> dict:
            self.status_checked = True
            return {"status": "completed"}

    records: list[dict] = []
    gateway = _Gateway()
    ctrl = GatewayRunController(
        gateway=gateway,
        terminal_replay_max_wait_s=0.1,
        terminal_replay_interval_s=0.01,
    )

    ctrl.follow_run(
        root_run_id="root",
        on_record=lambda _rid, rec: records.append(rec),
        should_stop=lambda: False,
    )

    assert records == [final_record]
    assert gateway.terminal_replay_calls >= 2


def test_follow_run_does_not_complete_when_terminal_replay_fails() -> None:
    class _Gateway:
        def __init__(self) -> None:
            self.status_checked = False

        def get_ledger(self, *, run_id: str, after: int, limit: int):
            if self.status_checked:
                raise RuntimeError("ledger unavailable")
            return {"items": [], "next_after": int(after)}

        def stream_ledger(self, **kwargs) -> None:
            raise GatewayStreamIdle("idle in test")

        def get_run(self, *, run_id: str) -> dict:
            self.status_checked = True
            return {"status": "completed"}

    ctrl = GatewayRunController(
        gateway=_Gateway(),
        terminal_replay_max_wait_s=0.05,
        terminal_replay_interval_s=0.01,
    )

    with pytest.raises(RuntimeError, match="ledger unavailable"):
        ctrl.follow_run(
            root_run_id="root",
            on_record=lambda _rid, _rec: None,
            should_stop=lambda: False,
        )
