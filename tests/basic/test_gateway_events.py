"""
Basic tests for gateway ledger event helpers.
"""

from abstractassistant.gateway.events import (
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


def test_extract_wait_and_tool_calls() -> None:
    rec = {"wait": {"reason": "job", "details": {"tool_calls": [{"name": "read_file"}]}}}
    wait = extract_wait_from_record(rec)
    assert wait is not None
    calls = extract_tool_calls_from_wait(wait)
    assert len(calls) == 1


def test_extract_wait_fallback_from_result() -> None:
    import warnings

    rec = {"result": {"wait": {"reason": "job", "details": {"tool_calls": [{"name": "read_file"}]}}}}
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        wait = extract_wait_from_record(rec)
        assert wait is not None
        assert any("#FALLBACK" in str(w.message) for w in captured)
