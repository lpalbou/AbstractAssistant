"""Controller-level robustness: workflow/tool caching + reattach probe."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from abstractassistant.controller import AssistantController


def _bare_controller() -> AssistantController:
    c = AssistantController.__new__(AssistantController)
    c._cache_ttl_s = 20.0
    c._cache_epoch = 0
    c._workflow_cache = None
    c._workflow_cache_at = 0.0
    c._tool_inventory_cache = None
    c._tool_inventory_cache_at = 0.0
    c._cache_lock = threading.RLock()
    return c


class _CountingWorkflowService:
    def __init__(self) -> None:
        self.calls = 0

    def list_workflows(self) -> List[Any]:
        self.calls += 1
        return [SimpleNamespace(bundle_id="b", flow_id="chat")]


@pytest.mark.basic
def test_workflow_options_are_cached_within_ttl() -> None:
    c = _bare_controller()
    svc = _CountingWorkflowService()
    c.gateway_service = svc  # type: ignore[assignment]

    c.workflow_options()
    c.workflow_options()
    c.workflow_options()

    assert svc.calls == 1


@pytest.mark.basic
def test_invalidate_caches_forces_refetch() -> None:
    c = _bare_controller()
    svc = _CountingWorkflowService()
    c.gateway_service = svc  # type: ignore[assignment]

    c.workflow_options()
    c.invalidate_caches()
    c.workflow_options()

    assert svc.calls == 2


@pytest.mark.basic
def test_expired_cache_refetches() -> None:
    c = _bare_controller()
    svc = _CountingWorkflowService()
    c.gateway_service = svc  # type: ignore[assignment]

    c.workflow_options()
    c._workflow_cache_at = time.monotonic() - 100.0  # force staleness
    c.workflow_options()

    assert svc.calls == 2


class _RunGateway:
    def __init__(self, summary: Dict[str, Any]) -> None:
        self._summary = summary

    def get_run(self, *, run_id: str) -> Dict[str, Any]:
        return dict(self._summary)


def _probe_controller(*, summary: Dict[str, Any], last_run: str, messages: List[Dict[str, Any]]) -> AssistantController:
    c = AssistantController.__new__(AssistantController)
    c.gateway = _RunGateway(summary)  # type: ignore[assignment]
    c.last_run_id = lambda: last_run  # type: ignore[assignment]
    c.session_messages = lambda: list(messages)  # type: ignore[assignment]
    return c


@pytest.mark.basic
def test_reattach_probe_follows_fresh_running_run() -> None:
    now_iso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    c = _probe_controller(
        summary={"status": "running", "updated_at": now_iso, "waiting": {"reason": "tool"}},
        last_run="run-1",
        messages=[],
    )
    candidate = c.probe_reattach_candidate()
    assert candidate is not None
    assert candidate["run_id"] == "run-1"
    assert candidate["status"] == "running"


@pytest.mark.basic
def test_reattach_probe_skips_stale_running_run() -> None:
    old_iso = "2000-01-01T00:00:00+00:00"
    c = _probe_controller(
        summary={"status": "running", "updated_at": old_iso},
        last_run="run-old",
        messages=[],
    )
    assert c.probe_reattach_candidate() is None


@pytest.mark.basic
def test_reattach_probe_recovers_terminal_run_without_answer() -> None:
    c = _probe_controller(
        summary={"status": "completed"},
        last_run="run-done",
        messages=[{"role": "user", "content": "hi"}],
    )
    candidate = c.probe_reattach_candidate()
    assert candidate is not None
    assert candidate["status"] == "completed"


@pytest.mark.basic
def test_reattach_probe_skips_terminal_run_already_answered() -> None:
    c = _probe_controller(
        summary={"status": "completed"},
        last_run="run-done",
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello", "run_id": "run-done"},
        ],
    )
    assert c.probe_reattach_candidate() is None


@pytest.mark.basic
def test_reattach_probe_no_last_run_is_none() -> None:
    c = _probe_controller(summary={"status": "running"}, last_run="", messages=[])
    assert c.probe_reattach_candidate() is None


class _EmptyThenFullWorkflowService:
    def __init__(self) -> None:
        self.calls = 0

    def list_workflows(self) -> List[Any]:
        self.calls += 1
        # First call fails (transient) → empty; second succeeds.
        return [] if self.calls == 1 else [SimpleNamespace(bundle_id="b", flow_id="chat")]


@pytest.mark.basic
def test_empty_workflow_list_is_not_negatively_cached() -> None:
    c = _bare_controller()
    svc = _EmptyThenFullWorkflowService()
    c.gateway_service = svc  # type: ignore[assignment]

    assert c.workflow_options() == []  # transient failure, not cached
    assert c.workflow_options()  # retried immediately, now populated
    assert svc.calls == 2


class _CountingToolGateway:
    def __init__(self) -> None:
        self.calls = 0

    def discovery_tools(self) -> Dict[str, Any]:
        self.calls += 1
        return {"items": [{"name": "web_search", "description": "", "toolset": "internet"}], "tool_mode": ""}


@pytest.mark.basic
def test_tool_inventory_returns_defensive_copy() -> None:
    from abstractassistant.core.tool_policy import ToolApprovalPolicy  # noqa: F401

    c = _bare_controller()
    c.gateway = _CountingToolGateway()  # type: ignore[assignment]
    c.preferences = SimpleNamespace(tool_preferences={})  # type: ignore[assignment]
    c.session_tool_auto_approval_active = lambda **_: False  # type: ignore[assignment]

    first = c.tool_inventory()
    first["items"].append({"name": "poison"})  # mutate the returned copy
    second = c.tool_inventory()

    assert c.gateway.calls == 1  # served from cache (not re-fetched)
    assert all(i.get("name") != "poison" for i in second["items"])  # cache not poisoned


@pytest.mark.basic
def test_reattach_probe_recovers_when_other_runs_stamped_but_not_this() -> None:
    c = _probe_controller(
        summary={"status": "completed"},
        last_run="run-new",
        messages=[
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old answer", "run_id": "run-old"},
            {"role": "user", "content": "new"},
        ],
    )
    candidate = c.probe_reattach_candidate()
    assert candidate is not None
    assert candidate["run_id"] == "run-new"


@pytest.mark.basic
def test_reattach_probe_waiting_run_reattaches_even_when_stale() -> None:
    c = _probe_controller(
        summary={"status": "waiting", "updated_at": "2000-01-01T00:00:00+00:00", "waiting": {"reason": "tool_approval"}},
        last_run="run-wait",
        messages=[],
    )
    candidate = c.probe_reattach_candidate()
    assert candidate is not None
    assert candidate["status"] == "waiting"


@pytest.mark.basic
def test_adapter_seed_seen_wait_keys_suppresses_replayed_waits() -> None:
    from abstractassistant.gateway.adapter import GatewayEventAdapter

    adapter = GatewayEventAdapter()
    adapter.seed_seen_wait_keys(["approval:1", "", None])
    rec = {
        "result": {
            "wait": {
                "wait_key": "approval:1",
                "reason": "tool_approval",
                "tool_calls": [{"name": "write_file", "arguments": {}}],
            }
        }
    }
    assert adapter.handle_record(rec) == []  # already-seen historical wait suppressed
