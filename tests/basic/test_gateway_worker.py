"""Basic coverage for gateway worker completion fallbacks."""

from __future__ import annotations

import threading

import pytest

from abstractassistant.gateway.adapter import GatewayEventAdapter
from abstractassistant.ui.gateway_worker import GatewayWorker


class _Signal:
    def __init__(self) -> None:
        self.items: list[object] = []

    def emit(self, item: object) -> None:
        self.items.append(item)


@pytest.mark.basic
def test_gateway_worker_empty_final_reply_is_not_materialized_as_assistant_text() -> None:
    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = None
    worker._run_activity_by_run = {"run-1": "Running (abc123): search online for Genentech roles"}

    content, meta = GatewayWorker._materialize_assistant_content(
        worker,
        run_id="run-1",
        content="",
        meta={"tool_calls": 3, "tool_results": 3},
        final=True,
    )

    assert content == ""
    assert meta["kind"] == "runtime_empty_response"
    assert meta["empty_response"] is True
    assert meta["run_id"] == "run-1"
    assert meta["run_activity"] == "Running (abc123): search online for Genentech roles"


@pytest.mark.basic
def test_gateway_worker_prefers_explicit_final_artifact_for_recovery() -> None:
    downloads: list[tuple[str, str]] = []

    class _Gateway:
        def download_run_artifact_content(
            self, *, run_id: str, artifact_id: str, max_bytes: int, timeout_s: float
        ):
            downloads.append((run_id, artifact_id))
            return b'{"answer": "Recovered from explicit artifact."}', "application/json"

    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = _Gateway()
    worker._run_activity_by_run = {}
    worker._output_artifact_candidates = [("run-1", "old-artifact")]
    worker._seen_output_artifacts = {("run-1", "old-artifact")}

    content, meta = GatewayWorker._materialize_assistant_content(
        worker,
        run_id="run-1",
        content="",
        meta={"artifact": {"$artifact": "final-artifact", "content_type": "application/json"}},
        final=True,
    )

    assert content == "Recovered from explicit artifact."
    assert downloads == [("run-1", "final-artifact")]
    assert meta["kind"] == "recovered_output_artifact"
    assert meta["artifact_id"] == "final-artifact"


@pytest.mark.basic
def test_gateway_worker_does_not_append_empty_runtime_diagnostic() -> None:
    class _LLMManager:
        @staticmethod
        def session_messages():
            return []

    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = None
    worker._llm_manager = _LLMManager()

    assert (
        GatewayWorker._should_append_assistant(
            worker,
            "",
            meta={"kind": "runtime_empty_response", "run_id": "run-new"},
        )
        is False
    )


@pytest.mark.basic
def test_gateway_worker_attaches_tool_call_details_to_run_stats() -> None:
    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._stats_by_run = {}

    GatewayWorker._record_run_stats(
        worker,
        run_id="run-tools",
        rec={
            "status": "completed",
            "effect": {
                "type": "tool_calls",
                "payload": {
                    "tool_calls": [
                        {"name": "execute_command", "arguments": {"command": "pwd"}},
                        {"name": "web_search", "arguments": {"query": "Genentech roles"}},
                    ]
                },
            },
        },
    )

    meta = GatewayWorker._meta_with_run_stats(worker, {}, run_id="run-tools")

    assert meta["_assistant_stats"]["tool_calls"] == 2
    assert [call["name"] for call in meta["_assistant_stats"]["tool_call_details"]] == [
        "execute_command",
        "web_search",
    ]


@pytest.mark.basic
def test_gateway_worker_tool_wait_event_does_not_block_ledger_following() -> None:
    submitted = threading.Event()
    commands: list[dict] = []

    class _Gateway:
        def submit_command(self, *, command: dict) -> dict:
            commands.append(command)
            submitted.set()
            return {"ok": True}

    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = _Gateway()
    worker._llm_manager = None
    worker._adapter = GatewayEventAdapter()
    worker._root_run_id = "run-1"
    worker._follow_run_id = ""
    worker._stats_by_run = {}
    worker._run_activity_by_run = {}
    worker._output_artifact_candidates = []
    worker._seen_output_artifacts = set()
    worker._tool_approval_event = threading.Event()
    worker._ask_user_event = threading.Event()
    worker._pending_tool_approval_wait = None
    worker._pending_ask_user_wait = None
    worker.event_emitted = _Signal()
    worker.error_occurred = _Signal()

    GatewayWorker._handle_events(
        worker,
        run_id="run-1",
        rec={
            "result": {
                "wait": {
                    "reason": "job",
                    "wait_key": "tool_approval:1",
                    "details": {
                        "tool_calls": [
                            {"name": "web_search", "arguments": {"query": "runtime replay"}}
                        ]
                    },
                }
            }
        },
    )

    assert [ev["type"] for ev in worker.event_emitted.items] == ["tool_request"]
    assert commands == []

    worker.provide_tool_approval(True)

    assert submitted.wait(timeout=1.0)
    assert commands[0]["run_id"] == "run-1"
    assert commands[0]["type"] == "resume"
    assert commands[0]["payload"]["wait_key"] == "tool_approval:1"
    assert commands[0]["payload"]["payload"] == {"approved": True}


@pytest.mark.basic
def test_gateway_worker_completed_attach_replays_before_completed_status() -> None:
    final_record = {
        "status": "completed",
        "result": {"output": {"response": "Recovered runtime answer."}},
    }

    class _Gateway:
        def get_run(self, *, run_id: str) -> dict:
            return {"status": "completed"}

        def get_ledger(self, *, run_id: str, after: int, limit: int) -> dict:
            if int(after) == 0:
                return {"items": [final_record], "next_after": 1}
            return {"items": [], "next_after": int(after)}

        def get_run_history_bundle(self, **kwargs) -> dict:
            return {"root_run_id": "run-1", "session": {"turns": []}, "ledgers": {}}

    class _LLMManager:
        active_session_id = "session-1"

        def __init__(self) -> None:
            self.messages: list[dict] = []
            self.last_run_id = ""

        def gateway_client(self):
            return None

        def set_last_run_id(self, run_id: str) -> None:
            self.last_run_id = run_id

        def append_message(self, **kwargs) -> None:
            self.messages.append(dict(kwargs))

        def replace_gateway_messages(self, messages, *, last_run_id=None) -> bool:
            return False

        def session_messages(self) -> list[dict]:
            return list(self.messages)

    llm_manager = _LLMManager()
    worker = GatewayWorker(
        llm_manager=llm_manager,
        user_text="",
        attachments=[],
        bundle_id="bundle",
        flow_id="flow",
        bundle_version="version",
        registry_scope="tenant_catalog",
        attach_run_id="run-1",
    )
    worker._gateway = _Gateway()
    worker.event_emitted = _Signal()
    worker.error_occurred = _Signal()

    worker.run()

    emitted_types = [ev.get("type") for ev in worker.event_emitted.items if isinstance(ev, dict)]
    assert emitted_types[:2] == ["assistant", "status"]
    assert worker.event_emitted.items[0]["content"] == "Recovered runtime answer."
    assert worker.event_emitted.items[1]["status"] == "completed"
    assert llm_manager.messages[-1]["content"] == "Recovered runtime answer."


@pytest.mark.basic
def test_gateway_worker_terminal_attach_preserves_failed_status() -> None:
    class _Gateway:
        def get_run(self, *, run_id: str) -> dict:
            return {"status": "failed"}

        def get_ledger(self, *, run_id: str, after: int, limit: int) -> dict:
            return {"items": [], "next_after": int(after)}

        def get_run_history_bundle(self, **kwargs) -> dict:
            return {"root_run_id": "run-1", "session": {"turns": []}, "ledgers": {}}

    class _LLMManager:
        active_session_id = "session-1"

        def gateway_client(self):
            return None

        def set_last_run_id(self, run_id: str) -> None:
            self.last_run_id = run_id

        def replace_gateway_messages(self, messages, *, last_run_id=None) -> bool:
            return False

        def session_messages(self) -> list[dict]:
            return []

    worker = GatewayWorker(
        llm_manager=_LLMManager(),
        user_text="",
        attachments=[],
        bundle_id="bundle",
        flow_id="flow",
        bundle_version="version",
        registry_scope="tenant_catalog",
        attach_run_id="run-1",
    )
    worker._gateway = _Gateway()
    worker.event_emitted = _Signal()
    worker.error_occurred = _Signal()

    worker.run()

    statuses = [
        ev.get("status")
        for ev in worker.event_emitted.items
        if isinstance(ev, dict) and ev.get("type") == "status"
    ]
    assert statuses[-1] == "failed"


@pytest.mark.basic
def test_gateway_worker_history_seed_failure_emits_replay_degraded() -> None:
    class _Gateway:
        def get_run_history_bundle(self, **kwargs) -> dict:
            raise RuntimeError("history unavailable")

    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = _Gateway()
    worker._llm_manager = object()
    worker.event_emitted = _Signal()

    GatewayWorker._seed_history_from_gateway(worker, run_id="run-1")

    assert worker.event_emitted.items == [
        {
            "type": "replay_degraded",
            "run_id": "run-1",
            "message": "Gateway history replay failed: history unavailable",
        }
    ]
