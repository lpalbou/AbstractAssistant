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
def test_gateway_worker_attach_seeding_suppresses_answered_but_reprompts_pending_repeat() -> None:
    """Reattach to a run whose stable wait_key repeated (two approval batches
    from the same act node): the replay must keep the ANSWERED occurrence
    silent and re-open ONLY the pending one. Excluding the pending wait by
    KEY (the old behavior) would also unsuppress its answered predecessor
    and replay a stale dialog."""

    def _wait_rec(step_id: str) -> dict:
        return {
            "run_id": "sub-1",
            "node_id": "act",
            "step_id": step_id,
            "status": "waiting",
            "effect": {"type": "tool_calls", "payload": {}},
            "result": {
                "wait": {
                    "reason": "user",
                    "wait_key": "tool_calls:sub-1:act",
                    "details": {
                        "mode": "approval_required",
                        "tool_calls": [{"name": "execute_command", "arguments": {"command": "ls"}}],
                    },
                }
            },
        }

    resume_rec = {
        "run_id": "sub-1",
        "node_id": "act",
        "step_id": "resume-1",
        "status": "completed",
        "effect": {"type": "resume", "payload": {"wait_key": "tool_calls:sub-1:act"}},
        "result": {},
    }
    replay_records = [_wait_rec("step-1"), resume_rec, _wait_rec("step-2")]

    class _Gateway:
        def get_run_history_bundle(self, **kwargs):
            return {
                "ledgers": {
                    "sub-1": {"items": [{"record": dict(r)} for r in replay_records]},
                }
            }

        def get_run(self, *, run_id: str):
            return {
                "status": "waiting",
                "waiting": {"reason": "user", "wait_key": "tool_calls:sub-1:act"},
            }

    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = _Gateway()
    worker._adapter = GatewayEventAdapter()

    GatewayWorker._suppress_resolved_waits_for_attach(worker, "run-root")

    events: list[dict] = []
    for rec in replay_records:
        events.extend(worker._adapter.handle_record(dict(rec)))
    requests = [e for e in events if e.get("type") == "tool_request"]
    assert len(requests) == 1, f"expected exactly the pending approval, got {requests!r}"


@pytest.mark.basic
def test_gateway_worker_attach_seeding_keeps_terminal_replay_silent() -> None:
    """Attach to a TERMINAL run (not waiting): every historical occurrence is
    seeded and the full replay — waits, resumes, repeated keys — must emit no
    approval dialogs."""

    def _wait_rec(step_id: str) -> dict:
        return {
            "run_id": "sub-1",
            "node_id": "act",
            "step_id": step_id,
            "status": "waiting",
            "effect": {"type": "tool_calls", "payload": {}},
            "result": {
                "wait": {
                    "reason": "user",
                    "wait_key": "tool_calls:sub-1:act",
                    "details": {
                        "mode": "approval_required",
                        "tool_calls": [{"name": "execute_command", "arguments": {"command": "ls"}}],
                    },
                }
            },
        }

    resume_rec = {
        "run_id": "sub-1",
        "node_id": "act",
        "step_id": "resume-1",
        "status": "completed",
        "effect": {"type": "resume", "payload": {"wait_key": "tool_calls:sub-1:act"}},
        "result": {},
    }
    replay_records = [_wait_rec("step-1"), dict(resume_rec), _wait_rec("step-2"), dict(resume_rec, step_id="resume-2")]

    class _Gateway:
        def get_run_history_bundle(self, **kwargs):
            return {
                "ledgers": {
                    "sub-1": {"items": [{"record": dict(r)} for r in replay_records]},
                }
            }

        def get_run(self, *, run_id: str):
            return {"status": "completed", "waiting": None}

    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = _Gateway()
    worker._adapter = GatewayEventAdapter()

    GatewayWorker._suppress_resolved_waits_for_attach(worker, "run-root")

    events: list[dict] = []
    for rec in replay_records:
        events.extend(worker._adapter.handle_record(dict(rec)))
    assert not [e for e in events if e.get("type") == "tool_request"]


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
def test_gateway_worker_final_meta_aggregates_stats_across_run_tree() -> None:
    """Agent workflows execute llm_call/tool_calls effects in sub-runs while the
    final answer fires on the root run: the final message's stats must cover
    every followed run, not just the root bucket (which is often empty)."""
    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._stats_by_run = {}

    GatewayWorker._record_run_stats(
        worker,
        run_id="sub-run",
        rec={
            "status": "completed",
            "started_at": "2026-07-09T10:00:00Z",
            "ended_at": "2026-07-09T10:00:02Z",
            "effect": {"type": "llm_call", "payload": {}},
            "result": {"usage": {"input_tokens": 500, "output_tokens": 40, "total_tokens": 540}},
        },
    )
    GatewayWorker._record_run_stats(
        worker,
        run_id="sub-run",
        rec={
            "status": "completed",
            "started_at": "2026-07-09T10:00:03Z",
            "ended_at": "2026-07-09T10:00:04Z",
            "effect": {
                "type": "tool_calls",
                "payload": {"tool_calls": [{"name": "web_search", "arguments": {"query": "x"}}]},
            },
        },
    )
    # Root run only carries the flow-end record (no effects of its own).
    GatewayWorker._record_run_stats(
        worker,
        run_id="root-run",
        rec={"status": "completed", "started_at": "2026-07-09T10:00:05Z", "ended_at": "2026-07-09T10:00:05Z"},
    )

    meta = GatewayWorker._meta_with_run_stats(worker, {}, run_id="root-run")
    stats = meta["_assistant_stats"]

    assert stats["run_id"] == "root-run"
    assert stats["llm_calls"] == 1
    assert stats["tool_calls"] == 1
    assert stats["usage"]["input_tokens"] == 500
    assert stats["tool_call_details"][0]["name"] == "web_search"
    # Wall-clock span across the tree, not a sum of per-run durations.
    assert stats["duration_ms"] == 5000


@pytest.mark.basic
def test_gateway_worker_tool_call_details_preserve_execution_outcome() -> None:
    """Persisted tool details keep success/error so downstream stats (e.g. file
    activity) can exclude failed calls after replay."""
    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._stats_by_run = {}

    GatewayWorker._record_run_stats(
        worker,
        run_id="run-outcome",
        rec={
            "status": "completed",
            "effect": {
                "type": "tool_calls",
                "payload": {
                    "tool_calls": [
                        {
                            "name": "write_file",
                            "call_id": "c1",
                            "arguments": {"file_path": "a.txt", "content": "x"},
                        },
                        {
                            "name": "edit_file",
                            "call_id": "c2",
                            "arguments": {"file_path": "b.txt", "pattern": "x"},
                        },
                    ]
                },
            },
            "result": {
                "results": [
                    {"call_id": "c1", "success": True},
                    {"call_id": "c2", "success": False, "error": "pattern not found"},
                ]
            },
        },
    )

    meta = GatewayWorker._meta_with_run_stats(worker, {}, run_id="run-outcome")
    details = meta["_assistant_stats"]["tool_call_details"]

    assert [call.get("success") for call in details] == [True, False]
    assert details[1]["error"] == "pattern not found"


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
def test_gateway_worker_keyed_approval_survives_overwritten_pending_wait() -> None:
    """A second tool_request overwrites the single pending-wait slot while the
    first approval dialog is open; answering by identity must still resume the
    FIRST wait (regression for misrouted approvals)."""
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

    def _wait_record(key: str) -> dict:
        return {
            "result": {
                "wait": {
                    "reason": "job",
                    "wait_key": key,
                    "details": {"tool_calls": [{"name": "web_search", "arguments": {}}]},
                }
            }
        }

    GatewayWorker._handle_events(worker, run_id="run-1", rec=_wait_record("tool_approval:1"))
    # Second wait arrives (e.g. from a followed subrun) and overwrites the slot.
    GatewayWorker._handle_events(worker, run_id="run-2", rec=_wait_record("tool_approval:2"))
    assert worker._pending_tool_approval_wait["wait_key"] == "tool_approval:2"

    first_event = worker.event_emitted.items[0]
    worker.provide_tool_approval(
        True,
        run_id=str(first_event.get("run_id") or ""),
        wait_key=str(first_event.get("wait_key") or ""),
    )

    assert submitted.wait(timeout=1.0)
    assert commands[0]["run_id"] == "run-1"
    assert commands[0]["payload"]["wait_key"] == "tool_approval:1"
    # The unrelated pending wait must remain answerable.
    assert worker._pending_tool_approval_wait["wait_key"] == "tool_approval:2"


@pytest.mark.basic
def test_gateway_worker_xor_identity_falls_back_wholesale() -> None:
    """A lone kwarg (run_id XOR wait_key) must not stitch a mixed identity from
    the pending slot; it falls back to the pending wait as a whole."""
    commands: list[dict] = []

    class _Gateway:
        def submit_command(self, *, command: dict) -> dict:
            commands.append(command)
            return {"ok": True}

    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = _Gateway()
    worker._tool_approval_event = threading.Event()
    worker._pending_tool_approval_wait = {"run_id": "run-A", "wait_key": "key-A"}

    # Caller passes only wait_key (a different one) — must NOT pair it with run-A.
    worker.provide_tool_approval(True, wait_key="key-B")
    import time as _t
    _t.sleep(0.2)

    assert commands, "fallback should submit the pending wait"
    assert commands[0]["run_id"] == "run-A"
    assert commands[0]["payload"]["wait_key"] == "key-A"


@pytest.mark.basic
def test_gateway_worker_pending_slot_cleared_only_on_pair_match() -> None:
    """Clearing the pending slot must match on (run_id, wait_key), not wait_key
    alone — wait keys (e.g. 'voice_input') can repeat across runs."""
    class _Gateway:
        def submit_command(self, *, command: dict) -> dict:
            return {"ok": True}

    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = _Gateway()
    worker._tool_approval_event = threading.Event()
    worker._pending_tool_approval_wait = {"run_id": "run-B", "wait_key": "voice_input"}

    # Answer run-A's wait with the same wait_key: run-B's pending slot must survive.
    worker.provide_tool_approval(True, run_id="run-A", wait_key="voice_input")

    assert worker._pending_tool_approval_wait == {"run_id": "run-B", "wait_key": "voice_input"}


@pytest.mark.basic
def test_gateway_worker_keyed_user_response_targets_named_wait() -> None:
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
    worker._ask_user_event = threading.Event()
    worker._pending_ask_user_wait = None

    worker.provide_user_response("blue", run_id="run-9", wait_key="ask:42")

    assert submitted.wait(timeout=1.0)
    assert commands[0]["run_id"] == "run-9"
    assert commands[0]["payload"]["wait_key"] == "ask:42"
    assert commands[0]["payload"]["payload"] == {"response": "blue"}


class _FreshRunGateway:
    """Stub gateway for fresh-run worker paths (start + follow to completion)."""

    def __init__(self, *, ledger_items: list[dict]) -> None:
        self.bundle_calls = 0
        self._ledger_items = list(ledger_items)

    def start_run(self, **kwargs) -> str:
        return "run-live"

    def get_run(self, *, run_id: str) -> dict:
        return {"status": "completed"}

    def get_run_input_data(self, *, run_id: str) -> dict:
        return {"input_data": {"prompt": "hi"}}

    def get_ledger(self, *, run_id: str, after: int, limit: int) -> dict:
        if int(after) == 0:
            return {"items": list(self._ledger_items), "next_after": len(self._ledger_items)}
        return {"items": [], "next_after": int(after)}

    def stream_ledger(self, **kwargs) -> None:
        return None

    def get_run_history_bundle(self, **kwargs) -> dict:
        self.bundle_calls += 1
        return {"root_run_id": "run-live", "session": {"turns": []}, "ledgers": {}}


class _RecordingLLMManager:
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
        self.messages = [dict(m) for m in messages]
        return True

    def session_messages(self) -> list[dict]:
        return list(self.messages)


def _fresh_worker(gateway, llm_manager) -> GatewayWorker:
    worker = GatewayWorker(
        llm_manager=llm_manager,
        user_text="hi",
        attachments=[],
        bundle_id="bundle",
        flow_id="flow",
        bundle_version="version",
        registry_scope="tenant_catalog",
    )
    worker._gateway = gateway
    worker.event_emitted = _Signal()
    worker.error_occurred = _Signal()
    return worker


@pytest.mark.basic
def test_gateway_worker_live_final_is_authoritative_and_skips_reseed() -> None:
    """When the final answer arrived on the live stream, the post-run history
    reseed must not run: it REPLACES the transcript with the gateway's bundle
    view, which can lack the answer entirely (missing session turns force the
    recovery path) and would wipe the live message's run-tree stats."""
    gateway = _FreshRunGateway(
        ledger_items=[
            {
                "status": "completed",
                "started_at": "2026-07-09T10:00:00Z",
                "ended_at": "2026-07-09T10:00:01Z",
                "effect": {"type": "llm_call", "payload": {}},
                "result": {"usage": {"input_tokens": 50, "output_tokens": 7, "total_tokens": 57}},
            },
            {
                "status": "completed",
                "started_at": "2026-07-09T10:00:02Z",
                "ended_at": "2026-07-09T10:00:03Z",
                "result": {"output": {"response": "Live answer."}},
            },
        ]
    )
    llm_manager = _RecordingLLMManager()
    worker = _fresh_worker(gateway, llm_manager)

    worker.run()

    assert gateway.bundle_calls == 0, "post-run reseed must be skipped after a live final"
    finals = [m for m in llm_manager.messages if m.get("role") == "assistant"]
    assert finals and finals[-1]["content"] == "Live answer."
    stats = finals[-1]["metadata"]["_assistant_stats"]
    assert stats["usage"]["input_tokens"] == 50
    assert not [e for e in worker.error_occurred.items]


@pytest.mark.basic
def test_gateway_worker_missed_final_still_reseeds_as_gap_filler() -> None:
    gateway = _FreshRunGateway(
        ledger_items=[{"status": "completed", "result": {}}]
    )
    llm_manager = _RecordingLLMManager()
    worker = _fresh_worker(gateway, llm_manager)

    worker.run()

    assert gateway.bundle_calls >= 1, "reseed must run when no final was observed"


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


@pytest.mark.basic
def test_attach_reprompts_a_pending_approval_that_belongs_to_a_SUBRUN() -> None:
    """Reattach while the pending approval sits on the AGENT SUBRUN.

    This is the production shape, and the one that parked a real run for 16
    minutes: the root run's own pending wait is `subworkflow:<child>`, while
    the approval the user has to answer lives on the child ledger with a
    `tool_approval:<child>:act:<hash>` key. Excluding "the pending wait" by
    reading the ROOT run's waiting key therefore matches nothing on the child,
    so every child approval — including the unanswered one — got seeded as
    already handled and the dialog never opened again.
    """
    root_wait = {
        "run_id": "run-root",
        "node_id": "assistant_agent",
        "step_id": "root-step",
        "status": "waiting",
        "effect": {"type": "start_subworkflow", "payload": {}},
        "result": {"wait": {"reason": "user", "wait_key": "subworkflow:sub-1"}},
    }

    def _approval(step_id: str, key: str) -> dict:
        return {
            "run_id": "sub-1",
            "node_id": "act",
            "step_id": step_id,
            "status": "waiting",
            "effect": {"type": "tool_calls", "payload": {}},
            "result": {
                "wait": {
                    "reason": "user",
                    "wait_key": key,
                    "details": {
                        "mode": "approval_required",
                        "tool_calls": [
                            {"name": "execute_command", "arguments": {"command": "ioreg -r"}}
                        ],
                    },
                }
            },
        }

    def _resume(step_id: str, key: str) -> dict:
        return {
            "run_id": "sub-1",
            "node_id": "act",
            "step_id": step_id,
            "status": "completed",
            "effect": {"type": "resume", "payload": {"wait_key": key}},
            "result": {"resumed": True},
        }

    answered = "tool_approval:sub-1:act:aaaa"
    pending = "tool_approval:sub-1:act:bbbb"
    child_records = [
        _approval("step-a", answered),
        _resume("resume-a", answered),
        _approval("step-b", pending),  # never answered — the run is parked here
    ]

    class _Gateway:
        def get_run_history_bundle(self, **kwargs):
            return {
                "ledgers": {
                    "run-root": {"items": [{"record": dict(root_wait)}]},
                    "sub-1": {"items": [{"record": dict(r)} for r in child_records]},
                }
            }

        def get_run(self, *, run_id: str):
            # The ROOT is what the worker asks about, and the root is waiting
            # on its subworkflow — never on the child's tool approval.
            return {
                "status": "waiting",
                "waiting": {"reason": "user", "wait_key": "subworkflow:sub-1"},
            }

    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = _Gateway()
    worker._adapter = GatewayEventAdapter()

    GatewayWorker._suppress_resolved_waits_for_attach(worker, "run-root")

    events: list[dict] = []
    for rec in [root_wait, *child_records]:
        events.extend(worker._adapter.handle_record(dict(rec)))
    requests = [e for e in events if e.get("type") == "tool_request"]
    assert len(requests) == 1, (
        f"the unanswered approval must be re-raised, got {len(requests)} requests"
    )
    assert requests[0].get("wait_key") == pending
