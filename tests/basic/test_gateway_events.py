"""
Basic tests for gateway ledger event helpers.
"""

from abstractassistant.gateway.events import (
    event_name_from_wait_key,
    extract_emit_event,
    extract_flow_end_output,
    extract_tool_calls_from_wait,
    extract_wait_from_record,
    normalize_ui_event_name,
    parse_status_payload,
)


def test_normalize_ui_event_name() -> None:
    assert normalize_ui_event_name("abstractcode.message") == "abstract.message"
    assert normalize_ui_event_name("abstract.status") == "abstract.status"


def test_event_name_from_wait_key_parses_runtime_shape() -> None:
    """The runtime's event wait keys are evt:{scope}:{scope_id}:{name}
    (abstractruntime core/event_keys.py) — the NAME is the fourth segment.
    Parsing the second segment returned the scope, so abstract.ask event
    waits were never recognized."""
    assert event_name_from_wait_key("evt:run:run-123:abstract.ask") == "abstract.ask"
    assert event_name_from_wait_key("evt:global:global:my-mailbox") == "my-mailbox"
    assert event_name_from_wait_key("evt:session:sess-1:abstract.ask") == "abstract.ask"
    # Legacy short shapes keep their old reading; non-event keys pass through.
    assert event_name_from_wait_key("evt:abstract.ask") == "abstract.ask"
    assert event_name_from_wait_key("user:r1:ask") == "user:r1:ask"


def test_extract_emit_event_and_status() -> None:
    rec = {"effect": {"type": "emit_event", "payload": {"name": "abstract.status", "payload": "Working"}}}
    emit = extract_emit_event(rec)
    assert emit is not None
    name, payload, scope = emit
    assert name == "abstract.status"
    assert payload == "Working"
    assert scope is None
    parsed = parse_status_payload(payload)
    assert parsed["text"] == "Working"


def test_extract_flow_end_output() -> None:
    rec = {"result": {"output": {"response": "Done", "meta": {"ok": True}}}}
    out = extract_flow_end_output(rec)
    assert out is not None
    assert out["response"] == "Done"
    assert out["meta"] == {"ok": True}


def test_extract_flow_end_output_preserves_media_artifacts() -> None:
    artifact = {"$artifact": "img_1", "artifact_id": "img_1", "content_type": "image/png"}
    rec = {
        "result": {
            "output": {
                "response": "Rabbit ready.",
                "meta": {"provider": "mflux"},
                "artifact": artifact,
                "image_artifact": artifact,
                "artifact_id": "img_1",
                "outputs": {"image": [{"artifact_ref": artifact}]},
            }
        }
    }
    out = extract_flow_end_output(rec)
    assert out is not None
    assert out["response"] == "Rabbit ready."
    assert out["meta"]["provider"] == "mflux"
    assert out["meta"]["artifact"] == artifact
    assert out["meta"]["image_artifact"] == artifact
    assert out["meta"]["artifact_id"] == "img_1"


def test_extract_flow_end_output_preserves_bare_artifact_reference() -> None:
    rec = {"result": {"output": {"$artifact": "answer_1", "content_type": "application/json"}}}

    out = extract_flow_end_output(rec)

    assert out is not None
    assert out["response"] == ""
    assert out["meta"]["artifact"] == {"$artifact": "answer_1", "content_type": "application/json"}
    assert out["meta"]["artifact_id"] == "answer_1"


def test_extract_wait_and_tool_calls() -> None:
    rec = {"result": {"wait": {"reason": "job", "details": {"tool_calls": [{"name": "read_file"}]}}}}
    wait = extract_wait_from_record(rec)
    assert wait is not None
    calls = extract_tool_calls_from_wait(wait)
    assert len(calls) == 1


def test_extract_wait_ignores_top_level() -> None:
    """Wait must be at result.wait (canonical StepRecord format); top-level is ignored."""
    rec = {"wait": {"reason": "job", "details": {"tool_calls": [{"name": "read_file"}]}}}
    wait = extract_wait_from_record(rec)
    assert wait is None
