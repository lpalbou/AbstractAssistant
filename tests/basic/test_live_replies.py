"""Live replies (contract S): the run stream's `llm.delta` / `llm.delta_end`.

Covers the whole client path against a fake LOOPBACK SSE gateway (no live
stack): the client surfaces the volatile events without moving the ledger
cursor, the controller emits a reset on every (re)connect, the worker drops
deltas for a call whose durable record it holds, the palette grows ONE live
card per call and replaces it with the final message, the preference maps to
`_runtime.stream` in three states, and the CLI prints deltas then the final.
"""

from __future__ import annotations

import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")


# --------------------------------------------------------------- fake gateway


def _step(cursor: int, *, step_id: str = "", effect: str = "emit_event", status: str = "completed") -> str:
    record = {"step_id": step_id or f"step-{cursor}", "status": status, "effect": {"type": effect}, "node_id": "n"}
    return f"id: {cursor}\nevent: step\ndata: {json.dumps({'cursor': cursor, 'record': record})}\n\n"


def _delta(call_id: str, seq: int, text: str, *, channel: str = "content", snapshot: bool = False, **extra) -> str:
    data = {
        "kind": "llm.delta",  # S-1: the runtime's own field rides along (ignored)
        "run_id": extra.pop("run_id", "run-1"),
        "root_run_id": extra.pop("root_run_id", "run-1"),
        "parent_run_id": extra.pop("parent_run_id", None),
        "node_id": extra.pop("node_id", "reason"),
        "call_id": call_id,
        "seq": seq,
        "text": text,
        "channel": channel,
        "snapshot": snapshot,
        **extra,
    }
    return f"event: llm.delta\ndata: {json.dumps(data)}\n\n"


def _delta_end(call_id: str, seq: int, reason: str = "completed", **extra) -> str:
    data = {"kind": "llm.delta_end", "run_id": "run-1", "root_run_id": "run-1", "node_id": "reason",
            "call_id": call_id, "seq": seq, "reason": reason, **extra}
    return f"event: llm.delta_end\ndata: {json.dumps(data)}\n\n"


class _FakeGateway:
    """Serves one scripted SSE body per stream connection, then status."""

    def __init__(self, connections: List[List[str]], statuses: List[str]) -> None:
        self.connections = list(connections)
        self.statuses = list(statuses)
        self.stream_requests: List[Dict[str, Any]] = []
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):  # noqa: D401
                return

            def _json(self, payload: Any) -> None:
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                url = urlparse(self.path)
                if url.path.endswith("/ledger/stream"):
                    outer.stream_requests.append(
                        {"after": parse_qs(url.query).get("after", [""])[0],
                         "last_event_id": self.headers.get("Last-Event-ID")}
                    )
                    body = "".join(outer.connections.pop(0) if outer.connections else [])
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    self.wfile.write(body.encode())
                    self.wfile.flush()
                    return
                if url.path.endswith("/ledger"):
                    after = int(parse_qs(url.query).get("after", ["0"])[0])
                    self._json({"items": [], "next_after": after})
                    return
                if url.path.startswith("/api/gateway/runs/"):
                    status = outer.statuses.pop(0) if len(outer.statuses) > 1 else outer.statuses[0]
                    self._json({"status": status})
                    return
                self.send_response(404)
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def _client(url: str):
    from abstractassistant.gateway import GatewayClient, GatewayClientConfig

    return GatewayClient(GatewayClientConfig(base_url=url))


# ------------------------------------------------------------------ client


@pytest.mark.basic
def test_client_surfaces_deltas_without_touching_the_cursor() -> None:
    body = [
        _step(1),
        _delta("call-a", 3, "Hello", snapshot=True, truncated=True),
        _delta("call-a", 4, " world"),
        _step(2),
        _delta_end("call-a", 5),
    ]
    order: List[Any] = []
    with _FakeGateway([body], ["completed"]) as gw:
        _client(gw.url).stream_ledger(
            run_id="run-1",
            after=0,
            on_step=lambda ev: order.append(("step", ev["cursor"])),
            on_delta=lambda name, data: order.append((name, data.get("seq"))),
            on_open=lambda: order.append(("open", None)),
            timeout_s=5,
        )
        assert gw.stream_requests == [{"after": "0", "last_event_id": None}]
    assert order == [
        ("open", None),
        ("step", 1),
        ("llm.delta", 3),
        ("llm.delta", 4),
        ("step", 2),
        ("llm.delta_end", 5),
    ]


@pytest.mark.basic
def test_client_drops_deltas_when_no_hook_is_given() -> None:
    steps: List[int] = []
    with _FakeGateway([[_delta("call-a", 1, "x"), _step(7)]], ["completed"]) as gw:
        _client(gw.url).stream_ledger(run_id="run-1", after=0, on_step=lambda ev: steps.append(ev["cursor"]), timeout_s=5)
    assert steps == [7]


@pytest.mark.basic
def test_controller_resets_on_every_connect_and_resumes_from_the_step_cursor(monkeypatch) -> None:
    from abstractassistant.gateway.run_controller import GatewayRunController

    first = [_step(1), _delta("call-a", 40, "Hel", snapshot=True), _delta("call-a", 41, "lo")]
    second = [_delta("call-a", 41, "Hello", snapshot=True), _delta("call-a", 42, "!"), _step(2), _delta_end("call-a", 43)]
    events: List[Dict[str, Any]] = []
    with _FakeGateway([first, second], ["running", "completed"]) as gw:
        controller = GatewayRunController(gateway=_client(gw.url))
        monkeypatch.setattr(GatewayRunController, "_sleep_with_stop", staticmethod(lambda *_a: None))
        after, sub, completed = controller.stream_run(
            run_id="run-1",
            after=0,
            seen_sub_runs=set(),
            on_record=lambda rid, rec: events.append({"type": "record", "step_id": rec["step_id"]}),
            should_stop=lambda: False,
            on_delta=events.append,
        )
        requests = list(gw.stream_requests)
    assert (after, sub, completed) == (2, "", True)
    # The reconnect resumed from the last DURABLE cursor (1), never from a
    # delta seq, and sent no Last-Event-ID.
    assert requests == [{"after": "0", "last_event_id": None}, {"after": "1", "last_event_id": None}]
    kinds = [e["type"] for e in events]
    assert kinds == [
        "assistant_delta_reset", "record", "assistant_delta", "assistant_delta",
        "assistant_delta_reset", "assistant_delta", "assistant_delta", "record", "assistant_delta_end",
    ]
    snap = events[5]
    assert snap["snapshot"] is True and snap["text"] == "Hello" and snap["run_id"] == "run-1"
    assert snap["subagent"] is False


@pytest.mark.basic
def test_a_failing_delta_handler_never_ends_the_follow(monkeypatch) -> None:
    from abstractassistant.gateway.run_controller import GatewayRunController

    records: List[str] = []

    def _boom(ev):
        if ev["type"] == "assistant_delta":
            raise RuntimeError("ui exploded")

    with _FakeGateway([[_delta("c", 1, "x"), _step(1)]], ["completed"]) as gw:
        controller = GatewayRunController(gateway=_client(gw.url))
        with pytest.warns(UserWarning, match="live reply handler failed"):
            result = controller.stream_run(
                run_id="run-1", after=0, seen_sub_runs=set(),
                on_record=lambda rid, rec: records.append(rec["step_id"]),
                should_stop=lambda: False, on_delta=_boom,
            )
    assert result == (1, "", True)
    assert records == ["step-1"]


# ------------------------------------------------------------------ parsing


@pytest.mark.basic
def test_parsing_is_tolerant_and_reports_lineage_and_unavailable() -> None:
    from abstractassistant.gateway.live_deltas import to_ui_event

    ev = to_ui_event("llm.delta", {"kind": "llm.delta", "run_id": "child", "root_run_id": "root",
                                   "parent_run_id": "root", "node_id": "agent", "call_id": "c", "seq": 1,
                                   "text": "t", "channel": "reasoning", "future_field": 1})
    assert ev["channel"] == "reasoning" and ev["subagent"] is True and ev["node_id"] == "agent"
    end = to_ui_event("llm.delta_end", {"call_id": "c", "seq": 2, "reason": "unavailable", "detail": "usage_unavailable"},
                      run_id="root")
    assert end["reason"] == "unavailable" and end["detail"] == "usage_unavailable" and end["run_id"] == "root"
    with pytest.warns(UserWarning):
        assert to_ui_event("llm.delta", {"call_id": "c", "seq": 1, "text": "x", "channel": "tool"}) is None
    with pytest.warns(UserWarning):
        assert to_ui_event("llm.delta", {"call_id": "c", "text": "x", "channel": "content"}) is None


@pytest.mark.basic
def test_live_reply_snapshot_replaces_and_duplicates_are_ignored() -> None:
    from abstractassistant.gateway.live_deltas import LiveReply

    reply = LiveReply(run_id="r", call_id="c")
    assert reply.apply_delta({"channel": "content", "seq": 1, "text": "Hel"})
    assert reply.apply_delta({"channel": "content", "seq": 2, "text": "lo"})
    assert not reply.apply_delta({"channel": "content", "seq": 2, "text": "lo"})  # replay
    assert reply.apply_delta({"channel": "reasoning", "seq": 2, "text": "hmm"})  # own channel
    assert reply.apply_delta({"channel": "content", "seq": 5, "text": "Hello, w", "snapshot": True, "truncated": True})
    assert reply.apply_delta({"channel": "content", "seq": 6, "text": "orld"})
    assert (reply.content, reply.reasoning, reply.truncated) == ("Hello, world", "hmm", True)


# ------------------------------------------------------------------- worker


@pytest.mark.basic
def test_worker_drops_deltas_for_a_call_whose_record_it_holds() -> None:
    from abstractassistant.ui.gateway_worker import GatewayWorker

    class _Signal:
        def __init__(self):
            self.items = []

        def emit(self, item):
            self.items.append(item)

    worker = GatewayWorker.__new__(GatewayWorker)
    worker.event_emitted = _Signal()
    worker._handle_delta({"type": "assistant_delta", "call_id": "c1", "run_id": "child", "text": "a"})
    worker._note_finished_llm_call({"step_id": "c1", "status": "completed", "effect": {"type": "llm_call"}})
    worker._handle_delta({"type": "assistant_delta", "call_id": "c1", "run_id": "child", "text": "late"})
    worker._handle_delta({"type": "assistant_delta_end", "call_id": "c1", "reason": "completed"})
    worker._handle_delta({"type": "assistant_delta", "call_id": "c2", "run_id": "child", "text": "b"})
    assert [(e["type"], e.get("text")) for e in worker.event_emitted.items] == [
        ("assistant_delta", "a"),
        ("assistant_delta_end", None),
        ("assistant_delta", "b"),
    ]


# ------------------------------------------------------------------ run input


@pytest.mark.basic
@pytest.mark.parametrize("choice, expected", [("gateway_default", None), ("on", True), ("off", False)])
def test_preference_persists_and_shapes_the_run_input(tmp_path, choice, expected) -> None:
    from abstractassistant.gateway.run_input import build_run_input_data
    from abstractassistant.preferences import AssistantPreferences, PreferencesStore

    store = PreferencesStore(tmp_path / "preferences.json")
    store.save(AssistantPreferences(stream_replies=choice))
    raw = json.loads((tmp_path / "preferences.json").read_text())
    assert raw["stream_replies"] == choice
    prefs = store.load()
    assert prefs.stream_replies == choice
    scope = prefs.run_scope()
    data = build_run_input_data(prompt="hi", stream=scope.get("stream"))
    if expected is None:
        assert "stream" not in scope
        assert "stream" not in data["_runtime"]
    else:
        assert data["_runtime"]["stream"] is expected


@pytest.mark.basic
def test_preference_defaults_and_rejects_nonsense(tmp_path) -> None:
    from abstractassistant.gateway.run_input import build_run_input_data
    from abstractassistant.preferences import AssistantPreferences

    assert AssistantPreferences().stream_replies == "gateway_default"
    assert AssistantPreferences.from_dict({"stream_replies": "sometimes"}).stream_replies == "gateway_default"
    with pytest.raises(ValueError):
        build_run_input_data(prompt="hi", stream="yes")  # type: ignore[arg-type]


@pytest.mark.basic
def test_worker_sends_the_choice_through_build_chat_worker(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController

    controller = AssistantController(config=Config(), data_dir=tmp_path / "data")
    controller.update_preferences(hotkey_enabled=False, stream_replies="off")
    monkeypatch.setattr(
        controller,
        "current_workflow",
        lambda: type("W", (), {"bundle_id": "b", "flow_id": "f", "bundle_version": "", "registry_scope": "",
                               "interface": "", "is_gateway_default": False})(),
    )
    worker = controller.build_chat_worker(prompt="hi")
    assert worker._stream is False
    controller.update_preferences(stream_replies="gateway_default")
    assert controller.build_chat_worker(prompt="hi")._stream is None


# ---------------------------------------------------------------------- CLI


@pytest.mark.basic
def test_cli_prints_content_deltas_once_and_notes_outcomes() -> None:
    from abstractassistant.cli import LiveDeltaPrinter

    out = io.StringIO()
    p = LiveDeltaPrinter(out)
    p({"type": "assistant_delta_reset"})
    p({"type": "assistant_delta", "call_id": "c", "seq": 1, "text": "Hel", "channel": "content", "snapshot": True})
    p({"type": "assistant_delta", "call_id": "c", "seq": 2, "text": "thinking...", "channel": "reasoning"})
    p({"type": "assistant_delta", "call_id": "c", "seq": 3, "text": "lo", "channel": "content"})
    p({"type": "assistant_delta_reset"})  # reconnect: snapshot re-sends the text so far
    p({"type": "assistant_delta", "call_id": "c", "seq": 3, "text": "Hello", "channel": "content", "snapshot": True})
    p({"type": "assistant_delta", "call_id": "c", "seq": 4, "text": "!", "channel": "content"})
    p({"type": "assistant_delta_end", "call_id": "c", "reason": "completed"})
    p({"type": "assistant_delta_end", "call_id": "never-streamed", "reason": "completed"})
    p({"type": "assistant_delta", "call_id": "d", "seq": 1, "text": "bad", "channel": "content"})
    p({"type": "assistant_delta_end", "call_id": "d", "reason": "failed"})
    p({"type": "assistant_delta_end", "call_id": "e", "reason": "unavailable", "detail": "structured_output"})
    p.note_record({"step_id": "f", "status": "completed", "effect": {"type": "llm_call"}})
    p({"type": "assistant_delta", "call_id": "f", "seq": 9, "text": "late", "channel": "content"})
    p.final_seen = True
    p({"type": "assistant_delta", "call_id": "g", "seq": 1, "text": "after final", "channel": "content"})
    assert out.getvalue() == (
        "Hello!\n"
        "bad\n[live reply discarded: failed]\n"
        "[Live reply unavailable for this step: this step returns structured output. "
        "The answer appears when it is finished.]\n"
    )


@pytest.mark.basic
def test_cli_stream_flag_wins_over_the_saved_choice() -> None:
    from abstractassistant.cli import _stream_choice, create_parser

    assert create_parser().parse_args(["run", "--prompt", "x", "--stream", "on"]).stream == "on"
    with pytest.raises(SystemExit):
        create_parser().parse_args(["run", "--prompt", "x", "--stream", "maybe"])
    assert _stream_choice("on", {"stream": False}) is True
    assert _stream_choice("off", {}) is False
    assert _stream_choice(None, {"stream": True}) is True
    assert _stream_choice(None, {}) is None


@pytest.mark.basic
def test_cli_run_streams_to_stderr_and_prints_the_final_once(monkeypatch, capsys) -> None:
    from abstractassistant import cli

    started: List[Dict[str, Any]] = []

    class _Gateway:
        def start_run(self, **kwargs):
            started.append(kwargs)
            return "run-1"

        def get_run_history_bundle(self, **kwargs):
            raise RuntimeError("no history in unit test")

    class _LLM:
        active_session_id = "s"

        def append_message(self, **kwargs):
            pass

        def set_last_run_id(self, run_id):
            pass

    class _Controller:
        def __init__(self, **kwargs):
            self.gateway = _Gateway()
            self.llm_manager = _LLM()

        def current_workflow(self):
            return type("W", (), {"bundle_id": "b", "flow_id": "f", "bundle_version": "", "registry_scope": "",
                                   "is_gateway_default": False})()

        def allowed_tools_for_run(self):
            return None

        def tool_policy_for_run(self):
            return None

        def latest_image_artifact(self):
            return None

        def run_scope(self):
            return {"stream": False}  # saved "off" — the flag overrides it

    class _RunController:
        def __init__(self, gateway, debug=False):
            pass

        def follow_run(self, *, root_run_id, on_record, should_stop, on_delta):
            on_delta({"type": "assistant_delta", "call_id": "c", "seq": 1, "text": "Bon", "channel": "content"})
            on_delta({"type": "assistant_delta", "call_id": "c", "seq": 2, "text": "jour", "channel": "content"})
            on_delta({"type": "assistant_delta_end", "call_id": "c", "reason": "completed"})
            on_record(root_run_id, {"step_id": "c", "status": "completed", "effect": {"type": "llm_call"}})
            on_record(root_run_id, {"step_id": "end", "status": "completed", "result": {"output": {"response": "Bonjour"}}})

        def get_run_status(self, *, run_id):
            return "completed"

    import abstractassistant.controller as controller_module
    import abstractassistant.gateway.run_controller as rc_module

    monkeypatch.setattr(controller_module, "AssistantController", _Controller)
    monkeypatch.setattr(rc_module, "GatewayRunController", _RunController)
    monkeypatch.setattr(cli, "_build_config_from_args", lambda args: object())
    args = cli.create_parser().parse_args(["run", "--prompt", "salut", "--stream", "on"])
    assert cli._run_gateway_command(args) == 0
    captured = capsys.readouterr()
    assert captured.err == "Bonjour\n"
    assert captured.out.count("Bonjour") == 1
    assert started[0]["input_data"]["_runtime"]["stream"] is True


# ------------------------------------------------------------------ palette


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def palette(qapp, tmp_path, monkeypatch):
    import abstractassistant.app as app_module
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.theme import BASE_METRICS, DEFAULT_THEME, activate, activate_metrics

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    app_module._MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE = False
    controller = AssistantController(config=Config(), data_dir=tmp_path / "data")
    controller.update_preferences(hotkey_enabled=False)
    monkeypatch.setattr(controller, "backfill_session_attachments", lambda: 0)
    controller.llm_manager.append_message(role="user", content="tell me a story")
    window = app_module.AssistantPalette(controller=controller)
    window.resize(650, 700)
    window.show()
    window._run_busy = True
    qapp.processEvents()
    try:
        yield window
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()
        activate(DEFAULT_THEME)
        activate_metrics(BASE_METRICS.font_body)


def _live_cards(window):
    from abstractassistant.app import LiveMessageCard

    return [w for w in window.history_host.children() if isinstance(w, LiveMessageCard) and w.isVisible()]


def _d(call_id, seq, text, channel="content", **kw):
    return {"type": "assistant_delta", "run_id": kw.pop("run_id", "run-1"), "call_id": call_id, "seq": seq,
            "text": text, "channel": channel, "snapshot": kw.pop("snapshot", False),
            "truncated": kw.pop("truncated", False), "node_id": kw.pop("node_id", "reason"),
            "subagent": kw.pop("subagent", False)}


def _push(window, qapp, *events):
    for ev in events:
        window._on_worker_event(ev)
    window._flush_live_replies()
    qapp.processEvents()


@pytest.mark.basic
def test_snapshot_then_deltas_grow_one_card_and_the_final_replaces_it(palette, qapp) -> None:
    from abstractassistant.app import MessageCard, LiveMessageCard

    _push(palette, qapp, {"type": "assistant_delta_reset", "run_id": "run-1"},
          _d("c1", 5, "Once upon", snapshot=True), _d("c1", 6, " a time"))
    cards = _live_cards(palette)
    assert len(cards) == 1 and cards[0].content_text == "Once upon a time"
    first = cards[0]
    _push(palette, qapp, _d("c1", 7, ", a fox"), _d("c1", 7, ", a fox"))  # duplicate seq ignored
    assert _live_cards(palette) == [first]  # same widget, grown in place
    assert first.content_text == "Once upon a time, a fox"
    assert "Once upon a time, a fox" in first.content_view.toPlainText()

    palette._controller.llm_manager.append_message(role="assistant", content="Once upon a time, a fox slept.")
    _push(palette, qapp, {"type": "assistant_delta_end", "call_id": "c1", "seq": 8, "reason": "completed"},
          {"type": "assistant", "content": "Once upon a time, a fox slept.", "final": True, "history_changed": True})
    assert _live_cards(palette) == []
    finals = [w for w in palette.history_host.children()
              if isinstance(w, MessageCard) and not isinstance(w, LiveMessageCard) and w.isVisible()
              and w._content == "Once upon a time, a fox slept."]
    assert len(finals) == 1
    # S-2.2: a late or replayed delta never brings the card back.
    _push(palette, qapp, _d("c1", 9, " again", snapshot=True), _d("c9", 1, "new call after the answer"))
    assert _live_cards(palette) == []


@pytest.mark.basic
def test_reasoning_stays_in_the_collapsed_thinking_area(palette, qapp) -> None:
    _push(palette, qapp, _d("c1", 1, "pondering the fox", channel="reasoning"), _d("c1", 2, "The answer"))
    card = _live_cards(palette)[0]
    assert card.content_text == "The answer"
    assert "pondering" not in card.content_view.toPlainText()
    assert card.thinking_toggle.isVisible() and not card.reasoning_view.isVisible()
    card.thinking_toggle.click()
    qapp.processEvents()
    assert card.reasoning_view.isVisible() and card.reasoning_view.toPlainText() == "pondering the fox"


@pytest.mark.basic
def test_failed_call_removes_the_card_and_says_why(palette, qapp) -> None:
    _push(palette, qapp, _d("c1", 1, "half a sent"))
    assert len(_live_cards(palette)) == 1
    _push(palette, qapp, {"type": "assistant_delta_end", "call_id": "c1", "seq": 2, "reason": "failed"})
    assert _live_cards(palette) == []
    assert palette._history_status_text == "Live reply discarded: the model call failed."


@pytest.mark.basic
def test_unavailable_is_a_one_line_note(palette, qapp) -> None:
    _push(palette, qapp, {"type": "assistant_delta_end", "call_id": "cx", "seq": 1, "reason": "unavailable",
                          "detail": "provider_cannot_stream"})
    assert _live_cards(palette) == []
    assert palette._history_status_text == (
        "Live reply unavailable for this step: the model provider cannot stream. The answer appears when it is finished."
    )


@pytest.mark.basic
def test_truncated_is_shown_explicitly(palette, qapp) -> None:
    from abstractassistant.gateway.live_deltas import TRUNCATED_NOTE

    _push(palette, qapp, _d("c1", 1, "tail of a long reply", snapshot=True, truncated=True))
    card = _live_cards(palette)[0]
    assert card.truncated_note.isVisible() and card.truncated_note.text() == TRUNCATED_NOTE


@pytest.mark.basic
def test_reconnect_drops_cards_that_are_not_resent(palette, qapp) -> None:
    _push(palette, qapp, _d("c1", 1, "first call"), _d("c2", 1, "second call"))
    assert {c.call_id for c in _live_cards(palette)} == {"c1", "c2"}
    kept = next(c for c in _live_cards(palette) if c.call_id == "c2")
    _push(palette, qapp, {"type": "assistant_delta_reset", "run_id": "run-1"},
          _d("c2", 4, "second call, continued", snapshot=True))
    cards = _live_cards(palette)
    assert [c.call_id for c in cards] == ["c2"]
    assert cards[0] is kept and cards[0].content_text == "second call, continued"
    # A reset with nothing re-sent clears everything.
    _push(palette, qapp, {"type": "assistant_delta_reset", "run_id": "run-1"})
    assert _live_cards(palette) == []


@pytest.mark.basic
def test_child_run_deltas_are_labelled(palette, qapp) -> None:
    _push(palette, qapp, _d("c1", 1, "searching", run_id="child", node_id="researcher", subagent=True))
    card = _live_cards(palette)[0]
    assert card.caption == "sub-agent · researcher"
    assert card.live_label.text().startswith("sub-agent · researcher")


@pytest.mark.basic
def test_live_card_survives_a_history_rebuild_and_the_run_end_clears_it(palette, qapp) -> None:
    _push(palette, qapp, _d("c1", 1, "streaming"))
    palette.refresh_history()
    qapp.processEvents()
    cards = _live_cards(palette)
    assert len(cards) == 1 and cards[0].content_text == "streaming"
    _push(palette, qapp, _d("c1", 2, " on"))
    assert _live_cards(palette)[0].content_text == "streaming on"
    _push(palette, qapp, {"type": "status", "status": "cancelled"})
    assert _live_cards(palette) == []


@pytest.mark.basic
def test_scroll_follows_only_when_the_user_is_at_the_bottom(palette, qapp) -> None:
    from PyQt5.QtTest import QTest

    bar = palette.history_scroll.verticalScrollBar()
    long_text = "\n\n".join(f"Paragraph {i} of a long streamed reply." for i in range(80))
    _push(palette, qapp, _d("c1", 1, long_text))
    QTest.qWait(250)  # the bottom pin re-applies after the text browser reflows
    assert bar.maximum() > 0
    assert bar.value() == bar.maximum()
    bar.setValue(0)  # the user scrolls up to read
    _push(palette, qapp, _d("c1", 2, "\n\nMore text."))
    QTest.qWait(250)
    assert bar.value() == 0


@pytest.mark.basic
def test_flush_is_throttled_not_per_delta(palette, qapp, monkeypatch) -> None:
    calls: List[int] = []
    original = palette._flush_live_replies
    monkeypatch.setattr(palette, "_flush_live_replies", lambda: calls.append(1) or original())
    # The timer was created with the bound method before the patch on first
    # use; build it now through the patched attribute.
    palette._live_flush_timer = None
    for i in range(50):
        palette._on_worker_event(_d("c1", i + 1, "x"))
    assert calls == []  # nothing repainted synchronously
    timer = palette._live_flush_timer
    assert timer is not None and timer.isActive() and timer.interval() >= palette.LIVE_FLUSH_MIN_MS


# ------------------------------------------------------------------ settings


@pytest.mark.basic
def test_settings_row_saves_the_choice_and_shows_the_gateway_default(qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    from abstractassistant.preferences import AssistantPreferences
    from abstractassistant.ui.settings.pages import ModelsPage

    class _Controller:
        def __init__(self):
            self.preferences = AssistantPreferences()
            self.streaming = {"deltas": True, "default": True}

        def update_preferences(self, **updates):
            payload = self.preferences.to_dict()
            payload.update(updates)
            self.preferences = AssistantPreferences.from_dict(payload)
            return self.preferences

        def gateway_streaming(self):
            return self.streaming

        def workflow_menu(self):
            return []

    controller = _Controller()
    page = ModelsPage(controller)
    page._refresh_stream()
    assert page.stream_combo.itemText(0) == "Gateway default (On)"
    assert page.stream_combo.currentData() == "gateway_default"
    page.stream_combo.setCurrentIndex(page.stream_combo.findData("off"))
    page._on_stream_chosen(page.stream_combo.currentIndex())
    assert controller.preferences.stream_replies == "off"
    assert "only when they are finished" in page.stream_detail.text()
    controller.streaming = {"deltas": False, "default": False}
    page._refresh_stream()
    assert page.stream_combo.currentData() == "off"
    assert "does not advertise live replies" in page.stream_detail.text()
    controller.streaming = None
    page._refresh_stream()
    assert page.stream_combo.itemText(0) == "Gateway default"
    assert "Not connected" in page.stream_detail.text()
