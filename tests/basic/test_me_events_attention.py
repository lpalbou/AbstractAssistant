"""The person's event stream in the desktop app (framework backlog 1047).

- the attention model: unseen = raised minus seen, over automation attention
  (per-automation ``seq``) and human-gated waits (``record_key`` / run + wait key,
  ``run.finished`` closes a run's waits);
- the follower: catch-up pages, then SSE, reconnect with ``Last-Event-ID`` and
  nothing delivered twice; a gateway without the stream (404) is ``unsupported``;
- the palette: banner + tray badge from the model, an OS notification per LIVE
  approval/question raised elsewhere (never for history), automation events
  refetch the automation list (the hub's notification ledger decides what
  notifies), and the timer is only a slow reconciliation while the stream is live.

Fakes only: a loopback HTTP server on a scratch port (tests/conftest.py refuses
:8080 and anything off this machine).
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abstractassistant.core.attention import AttentionModel, attention_banner_text  # noqa: E402
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig  # noqa: E402
from abstractassistant.gateway.me_events import EventFollower, MeEventsClient, SseFrameParser  # noqa: E402

from test_automations import AUTOMATIONS_PATH, TRIAGE, palette, stub  # noqa: E402,F401  (fixtures)


# ------------------------------------------------------------------ helpers


def _ev(sequence: int, typ: str, **data: Any) -> Dict[str, Any]:
    return {"specversion": "1.0", "id": f"{typ}:{sequence}", "type": typ, "source": "/abstractgateway/test", "time": "2026-10-25T12:00:00Z", "data": data, "sequence": sequence}


def _raised(seq: int, aid: str, item_seq: int, kind: str = "notify") -> Dict[str, Any]:
    return _ev(seq, "attention.raised", automation_id=aid, seq=item_seq, kind=kind, record_key=f"automation:completed:{aid}:{item_seq}", run_id="occ", index=1, channels=["console"])


def _wait(seq: int, run_id: str, wait_key: str, *, session_id: str, kind: str = "approval") -> Dict[str, Any]:
    return _ev(seq, "attention.raised", kind=kind, run_id=run_id, session_id=session_id, wait_key=wait_key, step_id="s1", record_key=f"wait:{run_id}:{wait_key}")


class EventsStub:
    """``/me/events`` + ``/me/events/stream`` over an in-memory list."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.status = 200
        self.cond = threading.Condition()
        self.stream_requests: List[Dict[str, Any]] = []
        self.drop = threading.Event()
        self.closed = False
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                url = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                if stub.status != 200:
                    self.send_response(stub.status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"detail":"no"}')
                    return
                if url.path == "/api/gateway/me/events":
                    after, limit = int(query.get("after", 0)), int(query.get("limit", 100))
                    with stub.cond:
                        rest = [e for e in stub.events if e["sequence"] > after]
                        head = stub.events[-1]["sequence"] if stub.events else 0
                    page = rest[:limit]
                    body = {"stream": "user:default:alice", "events": page, "next_after": page[-1]["sequence"] if page else after, "head": head, "more": len(rest) > limit}
                    raw = json.dumps(body).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if url.path == "/api/gateway/me/events/stream":
                    header = self.headers.get("Last-Event-ID")
                    stub.stream_requests.append({"last_event_id": header, "after": query.get("after")})
                    cursor = int(query.get("after") or 0) or int(header or 0)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    stub.drop.clear()
                    try:
                        self.wfile.write(b": stream user:default:alice\n\n")
                        self.wfile.flush()
                        while not stub.closed and not stub.drop.is_set():
                            with stub.cond:
                                fresh = [e for e in stub.events if e["sequence"] > cursor]
                                if not fresh:
                                    stub.cond.wait(0.1)
                                    fresh = [e for e in stub.events if e["sequence"] > cursor]
                            for e in fresh:
                                frame = f"id: {e['sequence']}\nevent: {e['type']}\ndata: {json.dumps(e)}\n\n"
                                self.wfile.write(frame.encode())
                                cursor = e["sequence"]
                            if not fresh:
                                self.wfile.write(b": keep-alive\n\n")
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    return
                self.send_response(404)
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def append(self, event: Dict[str, Any]) -> None:
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()

    def client(self) -> MeEventsClient:
        return MeEventsClient(GatewayClient(GatewayClientConfig(base_url=self.url, auth_token="t", timeout_s=5.0)))

    def close(self) -> None:
        self.closed = True
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def events():
    s = EventsStub()
    yield s
    s.close()


def _until(predicate, timeout_s: float = 6.0, pump=None) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pump is not None:
            pump()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not reached in time")


# ------------------------------------------------------------------- model


@pytest.mark.basic
def test_unseen_is_raised_minus_seen_over_automations_and_waits() -> None:
    m = AttentionModel()
    assert m.apply(_raised(1, "a", 1)) is not None
    assert m.apply(_raised(2, "a", 2)) is not None
    assert m.apply(_raised(3, "b", 1, kind="failure")) is not None
    assert m.apply(_raised(4, "a", 2)) is None, "the same item twice is one item"
    assert (m.new_results, m.needs_you) == (3, 0)
    m.apply(_ev(5, "attention.seen", automation_id="a", seq=1))
    assert m.new_results == 2
    assert m.apply(_raised(6, "a", 1)) is None, "an item already seen never comes back"

    first = m.apply(_wait(7, "run1", "tool_approval:run1:act", session_id="s-other"))
    assert first is not None and first.wait is not None and first.wait.notice_key == "wait:run1:tool_approval:run1:act"
    m.apply(_wait(8, "run2", "ask:run2", session_id="s-here", kind="question"))
    assert m.needs_you == 2 and [w.run_id for w in m.waits_outside("s-here")] == ["run1"]
    # Seen by record key, and a finished run closes its waits.
    m.apply(_ev(9, "attention.seen", record_key="wait:run1:tool_approval:run1:act"))
    m.apply(_ev(10, "run.finished", run_id="run2", session_id="s-here", status="completed", origin=None))
    assert m.needs_you == 0 and m.cursor == 10
    # A seen that arrived before its raise (replayed history) keeps it closed.
    m.apply(_ev(11, "attention.seen", record_key="wait:run3:k"))
    assert m.apply(_wait(12, "run3", "k", session_id="s")) is None and m.needs_you == 0
    m.apply(_ev(13, "attention.seen", automation_id="a", seq=9))
    m.apply(_ev(14, "attention.seen", automation_id="b", seq=1))
    assert m.total == 0


@pytest.mark.basic
def test_banner_words() -> None:
    assert attention_banner_text(needs_you=0, new_results=0) == ""
    assert attention_banner_text(needs_you=1, new_results=0) == "A conversation is waiting for you"
    assert attention_banner_text(needs_you=2, new_results=1) == "2 conversations are waiting for you · 1 new result from your automations"


@pytest.mark.basic
def test_sse_frames_and_keep_alives() -> None:
    p = SseFrameParser()
    lines = [": stream user:default:a", "", "id: 3", "event: run.started", 'data: {"x":1}', "", ": keep-alive", ""]
    frames = [f for f in (p.feed(line + "\n") for line in lines) if f]
    assert frames == [("3", "run.started", '{"x":1}')]


# ---------------------------------------------------------------- follower


@pytest.mark.basic
def test_follower_catches_up_then_streams_and_resumes_with_last_event_id(events) -> None:
    for i in range(1, 1206):  # more than one catch-up page (limit 1000)
        events.events.append(_ev(i, "run.started", run_id=f"r{i}", session_id="s", origin=None))
    got: List[tuple] = []
    follower = EventFollower(events.client, on_event=lambda e, live: got.append((e["sequence"], live)), max_backoff_s=0.2)
    follower.start()
    try:
        _until(lambda: follower.live and follower.cursor == 1205)
        assert [s for s, _ in got] == list(range(1, 1206))
        assert not any(live for _, live in got), "history is never live"
        events.append(_raised(1206, "a", 1))
        _until(lambda: follower.cursor == 1206)
        assert got[-1] == (1206, True)
        # The connection breaks; two events land while away; one more after.
        events.drop.set()
        _until(lambda: len(events.stream_requests) >= 2 and follower.live)
        events.append(_raised(1207, "a", 2))
        events.append(_raised(1208, "a", 3))
        _until(lambda: follower.cursor == 1208)
        assert events.stream_requests[0]["last_event_id"] == "1205"
        assert events.stream_requests[-1]["last_event_id"] == "1206", "the reconnect resumes from the last event consumed"
        seqs = [s for s, _ in got]
        assert seqs == sorted(set(seqs)) and seqs[-3:] == [1206, 1207, 1208], "nothing missed, nothing twice"
    finally:
        follower.stop(join_s=2)


@pytest.mark.basic
def test_a_gateway_without_the_stream_is_unsupported(events) -> None:
    events.status = 404
    follower = EventFollower(events.client, on_event=lambda e, live: None, max_backoff_s=0.2)
    follower.start()
    _until(lambda: follower.state == "unsupported")
    follower.stop(join_s=2)


# ----------------------------------------------------------------- palette


@pytest.mark.basic
def test_palette_banner_tray_and_notifications_follow_the_stream(palette, stub, events) -> None:
    from test_automations import _APP  # the module keeps the QApplication alive
    import test_automations

    from abstractassistant.ui.automations import AUTOMATIONS_RECONCILE_MS

    window, controller = palette
    app = test_automations._APP or _APP
    pump = app.processEvents
    window._poll_automations()  # the automation list as the app had it at start
    notified_at_start = len(window._notified)
    # History: one result seen, one not; a wait in ANOTHER conversation; one here.
    events.events += [
        _raised(1, TRIAGE, 1),
        _ev(2, "attention.seen", automation_id=TRIAGE, seq=1),
        _raised(3, TRIAGE, 2),
        _wait(4, "run-other", "tool_approval:run-other:act", session_id="sess-elsewhere"),
        _wait(5, "run-gone", "ask:run-gone", session_id="sess-elsewhere-2", kind="question"),
    ]
    live_runs = {"run-other"}
    window._wait_is_live = lambda _controller, wait: wait.run_id in live_runs  # GET /runs/{id}, faked
    controller.me_events_client = events.client
    window._start_me_events()
    _until(lambda: window._me_events.live and window._attention.cursor == 5, pump=pump)
    # The verification against the runs drops the wait whose run is not waiting any more.
    _until(lambda: window._attention.needs_you == 1, pump=pump)
    assert window._notified[notified_at_start:] == [], "history never notifies"
    assert not window.attention_banner.isHidden()
    banner = window.attention_banner.text()
    assert "A conversation is waiting for you · 1 new result from your automations" in banner and "attention:wait" in banner
    assert window._tray_feedback_state() == "waiting"
    assert window._automations_timer.interval() == AUTOMATIONS_RECONCILE_MS

    # Live: an approval raised in another conversation notifies once.
    polls_before = len(stub.calls("GET", AUTOMATIONS_PATH))
    events.append(_wait(6, "run-new", "tool_approval:run-new:act", session_id="sess-third"))
    _until(lambda: window._attention.cursor == 6, pump=pump)
    assert window._notified[notified_at_start:] == [("Approval needed", "A conversation is waiting for your answer. Click the menu bar icon to open it.")]
    assert "2 conversations are waiting for you" in window.attention_banner.text()
    # Live automation attention refetches the list (no timer involved).
    events.append(_raised(7, TRIAGE, 3))
    _until(lambda: len(stub.calls("GET", AUTOMATIONS_PATH)) > polls_before, pump=pump)
    # Answered elsewhere: the badge and the banner come down.
    events.append(_ev(8, "attention.seen", record_key="wait:run-new:tool_approval:run-new:act"))
    events.append(_ev(9, "run.finished", run_id="run-other", session_id="sess-elsewhere", status="completed", origin=None))
    events.append(_ev(10, "attention.seen", automation_id=TRIAGE, seq=3))
    _until(lambda: window._attention.cursor == 10, pump=pump)
    pump()
    assert window._attention.total == 0
    assert window.attention_banner.isHidden()
    assert window._tray_feedback_state() != "waiting"
    assert len([n for n in window._notified[notified_at_start:] if n[0] == "Approval needed"]) == 1
