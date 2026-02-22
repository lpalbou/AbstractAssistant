"""Tests for gateway run controller behavior."""

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
