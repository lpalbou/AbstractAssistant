"""
Basic tests for the gateway SSE parser.
"""

from abstractassistant.gateway.sse_parser import SseParser


def test_sse_parser_single_event() -> None:
    parser = SseParser()
    chunk = "event: step\ndata: {\"cursor\":1,\"record\":{\"status\":\"completed\"}}\n\n"
    events = parser.push(chunk)
    assert len(events) == 1
    assert events[0].event == "step"
    assert "\"cursor\":1" in events[0].data


def test_sse_parser_multiline_data() -> None:
    parser = SseParser()
    chunk = "event: step\ndata: {\"cursor\":1,\ndata: \"record\":{}}\n\n"
    events = parser.push(chunk)
    assert len(events) == 1
    assert "record" in events[0].data
