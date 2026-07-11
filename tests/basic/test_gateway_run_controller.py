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


def test_stream_run_retries_transient_connection_errors() -> None:
    """A gateway restart (connection refused) must not kill the follower: the
    run is durable server-side, so the stream retries with backoff and picks
    up the final answer once the gateway is back."""
    import urllib.error

    final_record = {"status": "completed", "result": {"output": {"response": "after blip"}}}

    class _Gateway:
        def __init__(self) -> None:
            self.stream_calls = 0
            self.status_checked = False

        def stream_ledger(self, **kwargs) -> None:
            self.stream_calls += 1
            if self.stream_calls <= 2:
                raise urllib.error.URLError(ConnectionRefusedError("gateway restarting"))
            raise GatewayStreamIdle("idle in test")

        def get_run(self, *, run_id: str) -> dict:
            self.status_checked = True
            return {"status": "completed"}

        def get_ledger(self, *, run_id: str, after: int, limit: int):
            if self.status_checked and int(after) == 0:
                return {"items": [final_record], "next_after": 1}
            return {"items": [], "next_after": int(after)}

    offline: list[str] = []
    online: list[bool] = []
    records: list[dict] = []
    gateway = _Gateway()
    ctrl = GatewayRunController(
        gateway=gateway,
        terminal_replay_max_wait_s=0.05,
        terminal_replay_interval_s=0.01,
    )
    # Shrink the retry backoff so the test is fast.
    ctrl._sleep_with_stop = lambda _s, _stop: None  # type: ignore[method-assign]

    after, sub, completed = ctrl.stream_run(
        run_id="root",
        after=0,
        seen_sub_runs=set(),
        on_record=lambda _rid, rec: records.append(rec),
        should_stop=lambda: False,
        on_offline=offline.append,
        on_online=lambda: online.append(True),
    )

    assert completed is True
    assert records == [final_record]
    assert gateway.stream_calls == 3
    assert len(offline) == 2


def test_stream_run_marks_online_on_idle_timeout() -> None:
    """Mid-run the SSE stream normally exits via GatewayStreamIdle; that path
    must clear offline state, otherwise an OFFLINE pill sticks after a
    transient reconnect for the rest of the run."""
    class _Gateway:
        def __init__(self) -> None:
            self.calls = 0

        def stream_ledger(self, **kwargs) -> None:
            self.calls += 1
            raise GatewayStreamIdle("idle in test")

        def get_run(self, *, run_id: str) -> dict:
            # First status check: still running; second: terminal so we stop.
            return {"status": "completed" if self.calls >= 2 else "running"}

        def get_ledger(self, *, run_id: str, after: int, limit: int):
            return {"items": [], "next_after": int(after)}

    online: list[bool] = []
    ctrl = GatewayRunController(gateway=_Gateway())
    ctrl._sleep_with_stop = lambda _s, _stop: None  # type: ignore[method-assign]

    ctrl.stream_run(
        run_id="root",
        after=0,
        seen_sub_runs=set(),
        on_record=lambda _rid, _rec: None,
        should_stop=lambda: False,
        on_online=lambda: online.append(True),
    )

    assert online, "on_online must fire on idle timeout (connection is healthy)"


def test_stream_run_record_callback_error_is_not_retried() -> None:
    """An exception from on_record must not be misclassified as a transient
    transport error (which would retry past the record's cursor and drop it)."""
    class _Gateway:
        def __init__(self) -> None:
            self.calls = 0

        def stream_ledger(self, *, run_id, after, on_step, **kwargs) -> None:
            self.calls += 1
            on_step({"cursor": 1, "record": {"status": "running"}})

        def get_run(self, *, run_id: str) -> dict:
            return {"status": "running"}

        def get_ledger(self, *, run_id: str, after: int, limit: int):
            return {"items": [], "next_after": int(after)}

    gateway = _Gateway()
    ctrl = GatewayRunController(gateway=gateway)
    ctrl._sleep_with_stop = lambda _s, _stop: None  # type: ignore[method-assign]

    def _raise(_rid, _rec):
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        ctrl.stream_run(
            run_id="root",
            after=0,
            seen_sub_runs=set(),
            on_record=_raise,
            should_stop=lambda: False,
        )
    assert gateway.calls == 1, "callback error must not trigger a transient retry"


def test_stream_run_gives_up_after_bounded_transient_failures() -> None:
    import urllib.error

    class _Gateway:
        def stream_ledger(self, **kwargs) -> None:
            raise urllib.error.URLError(ConnectionRefusedError("gateway down"))

    ctrl = GatewayRunController(gateway=_Gateway(), max_transient_stream_failures=2)
    ctrl._sleep_with_stop = lambda _s, _stop: None  # type: ignore[method-assign]

    with pytest.raises(urllib.error.URLError):
        ctrl.stream_run(
            run_id="root",
            after=0,
            seen_sub_runs=set(),
            on_record=lambda _rid, _rec: None,
            should_stop=lambda: False,
        )


def test_stream_run_does_not_retry_fatal_http_errors() -> None:
    from abstractassistant.gateway.client import GatewayHttpError

    class _Gateway:
        def __init__(self) -> None:
            self.stream_calls = 0

        def stream_ledger(self, **kwargs) -> None:
            self.stream_calls += 1
            raise GatewayHttpError("stream_ledger failed: unauthorized", status=401)

    gateway = _Gateway()
    ctrl = GatewayRunController(gateway=gateway)

    with pytest.raises(GatewayHttpError):
        ctrl.stream_run(
            run_id="root",
            after=0,
            seen_sub_runs=set(),
            on_record=lambda _rid, _rec: None,
            should_stop=lambda: False,
        )
    assert gateway.stream_calls == 1


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
