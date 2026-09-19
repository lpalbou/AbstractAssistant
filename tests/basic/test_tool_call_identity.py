"""Regression pins (2026-09-17): a tool call's identity is NOT the model's `call_id`.

Operator report: an answer's footer read "tools : 3", and the Tools-used dialog it
opens listed one. The run (7818f273) had made three calls — camera_list_devices,
camera_open, camera_capture_video — one per model response, and the model numbers its
calls per response, so all three carried `call_id: "0"`.

Everything that treated `call_id` as unique folded them together:
- the dialog's ledger lookup deduped on it            → 1 of 3 listed;
- the live adapter's replay guard keyed on it          → results 2 and 3 dropped;
- the activity card named its rows `tool:<call_id>`    → one row, overwritten twice,
  left spinning on the last call because its result never arrived.

The runtime mints `runtime_call_id` per executed call and repeats it on that call's
started / waiting / completed records. `step_id` is NOT usable: it changes across an
approval wait (started c1b14d70 → completed ca0d4093 in the real ledger), so it cannot
pair a start with its result. These tests use that exact shape.
"""

from __future__ import annotations

from typing import Any, Dict, List

from abstractassistant.controller import AssistantController
from abstractassistant.gateway.adapter import GatewayEventAdapter
from abstractassistant.gateway.history_seed import tool_messages_from_record
from abstractassistant.gateway.tool_usage import (
    extract_tool_call_details_from_record,
    extract_tool_call_details_from_scratchpad,
    pair_results_with_calls,
    tool_call_uid,
)
from abstractassistant.ui.activity import RunActivityModel

RUN = "run-1"
_TOOLS = ["camera_list_devices", "camera_open", "camera_capture_video"]


def _call(name: str, n: int, *, runtime_id: bool = True) -> Dict[str, Any]:
    call = {"name": name, "arguments": {"n": n}, "call_id": "0"}  # the model's number: always "0"
    if runtime_id:
        call["runtime_call_id"] = f"rtcall_{n}"
    return call


def _records(*, runtime_id: bool = True, approval: bool = True) -> List[Dict[str, Any]]:
    """One tool per model response, as the real run did. With `approval`, the completed
    record gets a DIFFERENT step_id than the started one, exactly like the real ledger."""
    out: List[Dict[str, Any]] = []
    for n, name in enumerate(_TOOLS):
        call = _call(name, n, runtime_id=runtime_id)
        effect = {"type": "tool_calls", "payload": {"tool_calls": [dict(call)]}}
        out.append({"run_id": RUN, "step_id": f"start-{n}", "node_id": "act", "status": "started", "effect": effect})
        result = {"call_id": "0", "name": name, "success": True, "output": f"out-{n}"}
        if runtime_id:
            result["runtime_call_id"] = call["runtime_call_id"]
        out.append(
            {
                "run_id": RUN,
                "step_id": f"done-{n}" if approval else f"start-{n}",
                "node_id": "act",
                "status": "completed",
                "effect": effect,
                "result": {"results": [result]},
            }
        )
    return out


class _Gateway:
    def __init__(self, records: List[Dict[str, Any]], *, page: int = 2000, overlap: int = 0) -> None:
        self._records, self._page, self._overlap = records, page, overlap

    def get_ledger(self, *, run_id: str, after: int = 0, limit: int = 2000) -> Dict[str, Any]:
        start = max(0, after - self._overlap) if after else 0
        items = self._records[start : after + self._page]
        return {"items": [{"record": r} for r in items], "next_after": after + self._page if items else after}


def _controller(gateway: _Gateway) -> AssistantController:
    controller = AssistantController.__new__(AssistantController)
    controller.gateway = gateway
    return controller


def test_the_dialog_lists_every_call_even_when_the_model_reuses_its_number() -> None:
    calls = _controller(_Gateway(_records())).tool_call_details_for_run(run_id=RUN)
    assert [c["name"] for c in calls] == _TOOLS
    assert [c.get("success") for c in calls] == [True, True, True]
    assert len({c["call_uid"] for c in calls}) == 3


def test_an_overlapping_ledger_page_still_lists_each_call_once() -> None:
    """What the dedupe is FOR. Removing it would be the wrong fix."""
    gateway = _Gateway(_records(), page=3, overlap=2)
    calls = _controller(gateway).tool_call_details_for_run(run_id=RUN)
    assert [c["name"] for c in calls] == _TOOLS


def test_ledgers_without_runtime_call_id_still_list_every_call() -> None:
    calls = _controller(_Gateway(_records(runtime_id=False))).tool_call_details_for_run(run_id=RUN)
    assert [c["name"] for c in calls] == _TOOLS
    assert len({c["call_uid"] for c in calls}) == 3


def test_tool_call_uid_is_never_the_models_call_id() -> None:
    assert tool_call_uid({"call_id": "0", "runtime_call_id": "rtcall_9"}) == "rtcall_9"
    assert tool_call_uid({"call_id": "0"}) == ""
    assert tool_call_uid(None) == ""


def test_results_pair_by_runtime_id_then_unambiguous_call_id_then_position() -> None:
    calls = [_call("a", 1), _call("b", 2)]  # both call_id "0"
    results = [
        {"call_id": "0", "runtime_call_id": "rtcall_2", "success": False, "error": "boom"},
        {"call_id": "0", "runtime_call_id": "rtcall_1", "success": True},
    ]
    paired = pair_results_with_calls(calls, results)
    assert [p["runtime_call_id"] for p in paired] == ["rtcall_1", "rtcall_2"]

    # No runtime ids and a shared call_id: the old dict lookup gave BOTH calls the
    # last result. Position is the only honest pairing left.
    legacy_calls = [{"name": "a", "call_id": "0"}, {"name": "b", "call_id": "0"}]
    legacy_results = [{"call_id": "0", "success": True}, {"call_id": "0", "success": False}]
    assert [p["success"] for p in pair_results_with_calls(legacy_calls, legacy_results)] == [True, False]

    # Distinct call_ids out of order, no runtime ids: call_id is unambiguous, use it.
    ooo_calls = [{"name": "a", "call_id": "x"}, {"name": "b", "call_id": "y"}]
    ooo_results = [{"call_id": "y", "success": False}, {"call_id": "x", "success": True}]
    assert [p["success"] for p in pair_results_with_calls(ooo_calls, ooo_results)] == [True, False]


def test_a_failed_second_call_is_not_reported_with_the_first_calls_success() -> None:
    record = {
        "run_id": RUN,
        "step_id": "s",
        "status": "completed",
        "effect": {"type": "tool_calls", "payload": {"tool_calls": [_call("a", 1), _call("b", 2)]}},
        "result": {
            "results": [
                {"call_id": "0", "runtime_call_id": "rtcall_1", "success": True},
                {"call_id": "0", "runtime_call_id": "rtcall_2", "success": False, "error": "denied"},
            ]
        },
    }
    details = extract_tool_call_details_from_record(record)
    assert [(d["name"], d["success"]) for d in details] == [("a", True), ("b", False)]
    assert details[1]["error"] == "denied"
    messages = tool_messages_from_record(record)
    assert [m["metadata"]["success"] for m in messages] == [True, False]
    assert [m["metadata"]["call_uid"] for m in messages] == ["rtcall_1", "rtcall_2"]


def test_scratchpad_fallback_keeps_calls_that_share_a_call_id() -> None:
    scratchpad = {"cycles": [{"i": n, "tool_calls": [{"name": name, "call_id": "0"}]} for n, name in enumerate(_TOOLS)]}
    assert [c["name"] for c in extract_tool_call_details_from_scratchpad(scratchpad)] == _TOOLS


def _replay(records: List[Dict[str, Any]]):
    adapter, model = GatewayEventAdapter(), RunActivityModel()
    delivered = 0
    for record in records:
        for event in adapter.handle_record(record):
            if event.get("type") == "tool":
                delivered += 1
            if event.get("type") in {"tool_started", "tool"}:
                model.apply_event(event)
    return delivered, [(s.payload.get("name"), s.status) for s in model.steps if s.kind == "tool"]


def test_the_live_card_shows_every_tool_finishing() -> None:
    delivered, rows = _replay(_records())
    assert delivered == 3
    assert rows == [(name, "ok") for name in _TOOLS]


def test_a_replayed_record_does_not_repeat_its_result() -> None:
    records = _records()
    delivered, rows = _replay(records + records[-1:])
    assert delivered == 3 and len(rows) == 3


def test_the_live_card_survives_a_runtime_without_runtime_call_ids() -> None:
    """Older records: the model's number is all there is. A FINISHED row must not be
    taken over by the next call that happens to carry the same number."""
    delivered, rows = _replay(_records(runtime_id=False))
    assert delivered == 3
    assert rows == [(name, "ok") for name in _TOOLS]
