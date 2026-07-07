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
