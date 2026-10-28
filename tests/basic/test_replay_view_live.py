"""The replay view in the worker and the CLI: live text beside the view, answers by identity,
the labeled local fold on an older gateway, stats from the view.

Until the runtime and gateway put an ephemeral text delta on `/view/stream`, the reply being
written comes from the ledger stream's `llm.delta` frames (`LiveText`); the committed message
comes from the view and replaces it, and a delta arriving after it is dropped.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

import pytest

pytest.importorskip("abstractruntime.replay")

from abstractassistant.gateway.replay_view import LiveText, ViewProjector, follow_run, stats_from_view  # noqa: E402
from abstractassistant.ui.gateway_worker import GatewayWorker  # noqa: E402

ROOT = "run-1"


class _Signal:
    def __init__(self, on_emit=None) -> None:
        self.items: List[Dict[str, Any]] = []
        self._on_emit = on_emit

    def emit(self, item: Dict[str, Any]) -> None:
        self.items.append(item)
        if self._on_emit:
            self._on_emit(item)


class _LLM:
    active_session_id = "s"

    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []

    def append_message(self, **kw) -> None:
        self.messages.append(dict(kw))

    def session_messages(self) -> List[Dict[str, Any]]:
        return list(self.messages)


def _view(status: str, *, activities=(), messages=(), seq: int = 1, interaction=None) -> Dict[str, Any]:
    return {
        "version": "replay_view_v1", "root_run_id": ROOT, "status": status, "display_status": None,
        "cursor": {"token": f"run-1:{seq}", "records": seq, "runs": {ROOT: seq}},
        "runs": [{"run_id": ROOT, "status": status, "order": [ROOT]}],
        "interaction": interaction, "open_waits": [], "usage": {"llm_calls": 1, "input_tokens": 9, "output_tokens": 3,
                                                                  "total_tokens": 12},
        "messages": list(messages), "activities": list(activities), "artifacts": [], "warnings": [],
    }


def _llm_activity(status: str) -> Dict[str, Any]:
    return {"id": f"{ROOT}:x1", "run_id": ROOT, "kind": "llm", "status": status, "step_ids": ["call-1"],
            "started_at": "2026-10-28T10:00:00+00:00", "ended_at": "2026-10-28T10:00:02+00:00",
            "order": ["2026-10-28T10:00:00+00:00", ROOT, 1]}


FINAL = {"id": f"{ROOT}:final", "role": "assistant", "kind": "final", "text": "Hello there.", "run_id": ROOT,
         "order": ["2026-10-28T10:00:03+00:00", ROOT, 3], "artifact_ids": []}


def _delta(text: str, *, snapshot: bool = False) -> Dict[str, Any]:
    return {"run_id": ROOT, "root_run_id": ROOT, "parent_run_id": None, "node_id": "reason", "call_id": "call-1",
            "seq": 1, "text": text, "channel": "content", "snapshot": snapshot}


class _ViewGateway:
    """Gateway 0.17.0 shape: the view routes plus the ledger stream's live frames, in a scripted
    order: live text, then the committed message on the view stream, then a LATE delta."""

    def __init__(self) -> None:
        self.live_sent = threading.Event()
        self.final_shown = threading.Event()
        self.late_sent = threading.Event()
        self.ledger_after: List[int] = []

    def supports_replay_view(self) -> bool:
        return True

    def get_run_view(self, *, run_id: str, etag=None, at=None, timeout_s=None):
        return 200, '"run-1:1"', _view("running", activities=[_llm_activity("running")], seq=1)

    def stream_ledger(self, *, run_id, after, on_step, stop_signal=None, timeout_s=None, max_idle_s=None,
                      on_delta=None, on_open=None):
        self.ledger_after.append(after)
        if len(self.ledger_after) > 1:
            while not stop_signal.is_set():
                time.sleep(0.01)
            return
        on_open()
        on_delta("llm.delta", _delta("Hel", snapshot=True))
        on_delta("llm.delta", _delta("lo"))
        self.live_sent.set()
        assert self.final_shown.wait(5)
        on_delta("llm.delta", _delta(" (late)"))
        self.late_sent.set()
        while not stop_signal.is_set():
            time.sleep(0.01)

    def stream_run_view(self, *, run_id, on_frame, last_event_id=None, stop_signal=None, timeout_s=None,
                        max_idle_s=None, on_open=None):
        on_open()
        assert self.live_sent.wait(5)
        done = _view("completed", activities=[_llm_activity("completed")], messages=[FINAL], seq=3)
        on_frame("delta", "run-1:3", done)
        assert self.late_sent.wait(5)
        on_frame("done", "", {"run_id": ROOT})


def _worker(gateway, on_emit=None) -> GatewayWorker:
    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = gateway
    worker._llm_manager = _LLM()
    worker._run_activity_by_run = {}
    worker._output_artifact_candidates = []
    worker._seen_output_artifacts = set()
    worker._pending_tool_approval_wait = None
    worker._pending_ask_user_wait = None
    worker._offline = False
    worker.event_emitted = _Signal(on_emit)
    worker.error_occurred = _Signal()
    return worker


@pytest.mark.basic
def test_live_text_appears_then_the_committed_message_replaces_it_and_a_late_delta_is_dropped():
    gw = _ViewGateway()
    worker = _worker(gw, on_emit=lambda ev: ev.get("type") == "assistant" and gw.final_shown.set())

    status = worker._follow_view(run_id=ROOT, attach=False)

    assert status == "completed"
    kinds = [(e["type"], e.get("text") or e.get("content")) for e in worker.event_emitted.items
             if e["type"] in ("assistant_delta", "assistant_delta_reset", "assistant")]
    # The reply streamed live, then the view's committed message arrived (the palette drops its
    # live card on `assistant`), and the late delta for the finished call never reached it.
    assert kinds == [("assistant_delta_reset", None), ("assistant_delta", "Hel"), ("assistant_delta", "lo"),
                     ("assistant", "Hello there.")]
    assert worker._llm_manager.messages[-1]["content"] == "Hello there."
    stats = worker._llm_manager.messages[-1]["metadata"]["_assistant_stats"]
    assert stats["usage"]["total_tokens"] == 12 and stats["llm_calls"] == 1
    # The live stream starts after the records the view already holds.
    assert gw.ledger_after[0] == 1


class _OldGateway:
    """An AbstractGateway before 0.17.0: no view routes; ledger pages and run summaries."""

    def __init__(self, records: List[Dict[str, Any]], status: str = "completed") -> None:
        self.records, self.status = records, status

    def supports_replay_view(self) -> bool:
        return False

    def get_ledger(self, *, run_id, after, limit):
        items = self.records[after:after + limit] if run_id == ROOT else []
        return {"items": items, "next_after": after + len(items)}

    def get_run(self, run_id):
        return {"run_id": run_id, "status": self.status, "output": {"response": "Folded here."}}

    def get_run_input_data(self, *, run_id):
        return {"input_data": {"prompt": "hi"}}


@pytest.mark.basic
def test_an_older_gateway_is_folded_locally_and_says_so():
    worker = _worker(_OldGateway([{"run_id": ROOT, "step_id": "a", "node_id": "end", "status": "completed",
                                   "idempotency_key": "system:completion:end",
                                   "result": {"output": {"response": "Folded here."}}}]))
    assert worker._follow_view(run_id=ROOT, attach=False) == "completed"
    types = [e["type"] for e in worker.event_emitted.items]
    assert types[0] == "replay_mode" and "no replay view" in worker.event_emitted.items[0]["message"]
    assert [e["content"] for e in worker.event_emitted.items if e["type"] == "assistant"] == ["Folded here."]


@pytest.mark.basic
def test_a_gateway_whose_discovery_fails_is_an_error_not_the_legacy_path():
    class _Broken:
        def supports_replay_view(self):
            raise RuntimeError("openapi.json unreachable")

    with pytest.raises(RuntimeError, match="unreachable"):
        follow_run(gateway=_Broken(), run_id=ROOT, on_view=lambda v: None, should_stop=lambda: False)


@pytest.mark.basic
def test_approvals_are_answered_by_identity_through_commands():
    submitted = threading.Event()
    commands: List[Dict[str, Any]] = []

    class _Gw:
        def submit_command(self, *, command):
            commands.append(command)
            submitted.set()
            return {"ok": True}

    worker = _worker(_Gw())
    proj = ViewProjector()

    def _ask(key: str, rid: str) -> Dict[str, Any]:
        return {"kind": "tool_approval", "run_id": rid, "wait_key": key, "step_id": "s",
                "tool_calls": [{"id": "c", "name": "web_search", "arguments": {}}],
                "command": {"type": "resume", "run_id": rid, "payload": {"wait_key": key}}}

    worker._emit_ui_events(run_id=ROOT, events=proj.project(_view("waiting", interaction=_ask("tool_approval:1", "child-1"))))
    worker._emit_ui_events(run_id=ROOT, events=proj.project(_view("waiting", interaction=_ask("tool_approval:2", "child-2"), seq=2)))
    reqs = [e for e in worker.event_emitted.items if e["type"] == "tool_request"]
    assert [r["run_id"] for r in reqs] == ["child-1", "child-2"]
    assert [e["wait_key"] for e in worker.event_emitted.items if e["type"] == "interaction_closed"] == ["tool_approval:1"]
    worker.provide_tool_approval(True, run_id=reqs[0]["run_id"], wait_key=reqs[0]["wait_key"])
    assert submitted.wait(2)
    assert commands[0]["run_id"] == "child-1"
    assert commands[0]["payload"] == {"wait_key": "tool_approval:1", "payload": {"approved": True}}
    assert worker._pending_tool_approval_wait == {"run_id": "child-2", "wait_key": "tool_approval:2"}


@pytest.mark.basic
def test_stats_come_from_the_view():
    view = _view("completed", activities=[
        _llm_activity("completed"),
        {"id": f"{ROOT}:t1", "run_id": ROOT, "kind": "tool", "status": "completed",
         "started_at": "2026-10-28T10:00:02+00:00", "ended_at": "2026-10-28T10:00:05+00:00",
         "tool_calls": [{"id": "rt1", "name": "read_file", "arguments": {"p": 1}, "status": "completed"},
                        {"id": "rt2", "name": "write_file", "arguments": {}, "status": "failed", "error": "no"}]},
    ])
    stats = stats_from_view(view)
    assert stats["duration_ms"] == 5000
    assert stats["tool_calls"] == 2
    assert [d["success"] for d in stats["tool_call_details"]] == [True, False]


@pytest.mark.basic
def test_live_text_keeps_going_when_its_stream_fails_and_reports_it_once():
    calls: List[int] = []
    got: List[Dict[str, Any]] = []

    class _Gw:
        def stream_ledger(self, *, run_id, after, on_step, stop_signal, timeout_s, max_idle_s, on_delta, on_open):
            calls.append(after)
            if len(calls) == 1:
                raise ConnectionError("reset")
            on_open()
            on_step({"cursor": 4, "record": {}})
            on_delta("llm.delta", _delta("x"))
            stop_signal.wait(5)

    with pytest.warns(UserWarning, match="live reply stream failed"):
        lt = LiveText(gateway=_Gw(), run_id=ROOT, on_delta=got.append, after=2).start()
        deadline = time.monotonic() + 5
        while len(got) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        lt.stop()
    assert [e["type"] for e in got] == ["assistant_delta_reset", "assistant_delta"]
    assert calls[:2] == [2, 2]


@pytest.mark.basic
def test_cli_run_streams_live_text_then_prints_the_committed_final_once(monkeypatch, capsys):
    from abstractassistant import cli

    started: List[Dict[str, Any]] = []
    live_done = threading.Event()

    class _Gateway:
        def start_run(self, **kwargs):
            started.append(kwargs)
            return ROOT

        def supports_replay_view(self):
            return True

        def get_run_view(self, *, run_id, etag=None, at=None, timeout_s=None):
            return 200, '"run-1:1"', _view("running", activities=[_llm_activity("running")], seq=1)

        def stream_ledger(self, *, run_id, after, on_step, stop_signal, timeout_s, max_idle_s, on_delta, on_open):
            on_open()
            on_delta("llm.delta", dict(_delta("Bon"), seq=1))
            on_delta("llm.delta", dict(_delta("jour"), seq=2))
            on_delta("llm.delta_end", {"call_id": "call-1", "seq": 3, "reason": "completed", "run_id": ROOT})
            live_done.set()
            stop_signal.wait(5)

        def stream_run_view(self, *, run_id, on_frame, last_event_id=None, stop_signal=None, timeout_s=None,
                            max_idle_s=None, on_open=None):
            on_open()
            assert live_done.wait(5)
            final = dict(FINAL, text="Bonjour")
            on_frame("delta", "run-1:3", _view("completed", activities=[_llm_activity("completed")],
                                                messages=[final], seq=3))
            on_frame("done", "", {})

        def get_run_history_bundle(self, **kwargs):
            raise RuntimeError("no history in unit test")

    class _CliLLM:
        active_session_id = "s"

        def append_message(self, **kwargs):
            pass

        def set_last_run_id(self, run_id):
            pass

    class _Controller:
        def __init__(self, **kwargs):
            self.gateway = _Gateway()
            self.llm_manager = _CliLLM()

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
            return {"stream": False}

        def live_replies_advertised(self):
            return True

    import abstractassistant.controller as controller_module

    monkeypatch.setattr(controller_module, "AssistantController", _Controller)
    monkeypatch.setattr(cli, "_build_config_from_args", lambda args: object())
    args = cli.create_parser().parse_args(["run", "--prompt", "salut", "--stream", "on"])
    assert cli._run_gateway_command(args) == 0
    captured = capsys.readouterr()
    assert captured.err == "Bonjour\n"
    assert captured.out.count("Bonjour") == 1
    assert started[0]["input_data"]["_runtime"]["stream"] is True


from abstractassistant.gateway.replay_view import follow_run_ledger_locally, follow_run_view  # noqa: E402


@pytest.mark.basic
def test_a_stream_that_ends_without_done_is_reconnected_calmly():
    calls: List[float] = []

    class _Gw:
        def get_run_view(self, **kw):
            return 200, '"run-1:1"', _view("running", seq=1)

        def stream_run_view(self, *, on_open=None, **kw):
            calls.append(time.monotonic())
            on_open()  # connected, then the proxy closes it cleanly

    t0 = time.monotonic()
    follow_run_view(gateway=_Gw(), run_id=ROOT, on_view=lambda v: None, should_stop=lambda: time.monotonic() - t0 > 1.0)
    assert 2 <= len(calls) <= 6, len(calls)  # backed off, not millions of reconnects


@pytest.mark.basic
def test_back_online_when_a_reconnect_connects_and_blips_do_not_accumulate():
    from abstractassistant.gateway.client import GatewayStreamIdle

    marks: List[str] = []
    n = {"i": 0}

    class _Gw:
        def get_run_view(self, **kw):
            return 200, '"run-1:1"', _view("waiting", seq=1)

        def stream_run_view(self, *, on_frame, on_open=None, **kw):
            n["i"] += 1
            if n["i"] % 2:
                raise ConnectionError("blip")  # every other attempt: 10 blips in total
            on_open()  # back, only keep-alives
            if n["i"] >= 20:
                on_frame("done", "", {})
                return
            raise GatewayStreamIdle("idle")

    follow_run_view(gateway=_Gw(), run_id=ROOT, on_view=lambda v: None, should_stop=lambda: False,
                    on_offline=lambda r: marks.append("off"), on_online=lambda: marks.append("on"),
                    max_transient_failures=3)
    assert marks[:2] == ["off", "on"]  # online again on connect, without any frame
    assert n["i"] == 20  # 10 separated blips never reached the limit of 3 consecutive


@pytest.mark.basic
def test_local_fold_reads_a_failed_pass_again():
    recs = [{"run_id": ROOT, "step_id": "a", "node_id": "end", "status": "completed",
             "idempotency_key": "system:completion:end", "result": {"output": {"response": "Kept."}}}]
    state = {"fail": True}

    class _Gw(_OldGateway):
        def get_run(self, run_id):
            if state.pop("fail", False):
                raise ConnectionError("blip after the ledger page was read")
            return super().get_run(run_id)

    fold = follow_run_ledger_locally(gateway=_Gw(recs), run_id=ROOT, on_view=lambda v: None,
                                     should_stop=lambda: False)
    assert [m["text"] for m in fold.view["messages"] if m["kind"] == "final"] == ["Kept."]
    assert fold.view["cursor"]["runs"][ROOT] == 1


@pytest.mark.basic
def test_a_media_only_answer_still_reaches_the_transcript():
    class _Gw(_OldGateway):
        def get_run(self, run_id):
            return {"run_id": run_id, "status": "completed", "output": {"image_artifact": {"$artifact": "img1"}}}

    recs = [{"run_id": ROOT, "step_id": "a", "node_id": "end", "status": "completed",
             "idempotency_key": "system:completion:end",
             "result": {"output": {"image_artifact": {"$artifact": "img1", "content_type": "image/png"}}}}]
    worker = _worker(_Gw(recs))
    assert worker._follow_view(run_id=ROOT, attach=False) == "completed"
    finals = [e for e in worker.event_emitted.items if e["type"] == "assistant" and e["final"]]
    assert len(finals) == 1
    assert finals[0]["content"] == "Generated image ready."
    assert finals[0]["meta"]["image_artifact"] == {"$artifact": "img1"}


@pytest.mark.basic
def test_a_failed_run_says_why():
    class _Gw(_OldGateway):
        def get_run(self, run_id):
            return {"run_id": run_id, "status": "failed", "error": "provider unreachable"}

    worker = _worker(_Gw([]))
    assert worker._follow_view(run_id=ROOT, attach=False) == "failed"
    assert [e["error"] for e in worker.event_emitted.items if e["type"] == "error"] == ["provider unreachable"]
