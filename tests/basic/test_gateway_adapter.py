"""
Basic tests for gateway ledger -> UI event adapter.
"""

from abstractassistant.gateway.adapter import GatewayEventAdapter


def test_adapter_emits_status_and_message() -> None:
    adapter = GatewayEventAdapter()
    rec = {"effect": {"type": "emit_event", "payload": {"name": "abstract.status", "payload": "Thinking"}}}
    events = adapter.handle_record(rec)
    assert events and events[0]["type"] == "status"


def test_adapter_emits_tool_request() -> None:
    adapter = GatewayEventAdapter()
    rec = {
        "result": {
            "wait": {
                "reason": "job",
                "wait_key": "tool:1",
                "details": {"tool_calls": [{"name": "read_file", "arguments": {"path": "README.md"}}]},
            }
        }
    }
    events = adapter.handle_record(rec)
    assert events and events[0]["type"] == "tool_request"


def test_adapter_emits_final_event_for_bare_artifact_output() -> None:
    adapter = GatewayEventAdapter()
    rec = {"result": {"output": {"$artifact": "answer_1", "content_type": "application/json"}}}

    events = adapter.handle_record(rec)

    assert events == [
        {
            "type": "assistant",
            "content": "",
            "meta": {
                "$artifact": "answer_1",
                "artifact": {"$artifact": "answer_1", "content_type": "application/json"},
                "artifact_id": "answer_1",
                "content_type": "application/json",
            },
            "final": True,
            "ts": "",
        }
    ]


def test_adapter_emits_cycle_for_reason_llm_call_started() -> None:
    """STARTED llm_call records on the agent's reason node become numbered cycle events
    (2026-07-10: live 'thinking, Nth pass' visibility), counted per run."""
    adapter = GatewayEventAdapter()
    rec = {
        "run_id": "r1",
        "node_id": "reason",
        "status": "started",
        "effect": {"type": "llm_call", "payload": {}},
    }
    assert {"type": "cycle", "iteration": 1} in adapter.handle_record(dict(rec))
    assert {"type": "cycle", "iteration": 2} in adapter.handle_record(dict(rec))
    # Independent counter per run id (subruns count on their own).
    assert {"type": "cycle", "iteration": 1} in adapter.handle_record(dict(rec, run_id="r2"))
    # Non-reason llm_call starts do not produce cycle events.
    assert not [
        e for e in adapter.handle_record(dict(rec, node_id="finalize")) if e.get("type") == "cycle"
    ]


def test_adapter_emits_tool_started_with_args_preview() -> None:
    """STARTED tool_calls records surface the launch (name + args preview) BEFORE
    execution; previously only tool results were visible."""
    adapter = GatewayEventAdapter()
    rec = {
        "run_id": "r1",
        "node_id": "act",
        "status": "started",
        "effect": {
            "type": "tool_calls",
            "payload": {"tool_calls": [{"name": "read_file", "arguments": {"file_path": "README.md"}}]},
        },
    }
    events = [e for e in adapter.handle_record(rec) if e.get("type") == "tool_started"]
    assert events
    tools = events[0]["tools"]
    assert tools[0]["name"] == "read_file"
    assert "README.md" in tools[0]["arguments_preview"]

    # Completed records must NOT re-announce the launch.
    done = dict(rec, status="completed")
    assert not [e for e in adapter.handle_record(done) if e.get("type") == "tool_started"]
