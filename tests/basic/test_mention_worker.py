"""`@entity` mentions, desktop: the worker's send path (ui/gateway_worker.py) over a fake gateway.

The order the palette relies on: the chips ride the start; a message that names entities and not
`@agent` starts no agent run; the entities are asked one after the other (ask -> answer -> next
ask); a refusal is signalled before the next ask; mentions_done comes once, before the run's end.
No test reaches a gateway: the worker's gateway is a recording fake."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

import pytest

from abstractassistant.core.mentions import Mention, MentionsSummary
from abstractassistant.gateway.client import GatewayCodedError
from abstractassistant.ui import gateway_worker as worker_module
from abstractassistant.ui.gateway_worker import GatewayWorker

CASTOR = Mention(id="castor", name="Castor", kind="entity", index=0, start=0)
NERIN = Mention(id="nerin", name="Nerin", kind="entity", index=1, start=8)
AGENT = Mention(id="agent", name="Assistant", kind="agent", index=2, start=15)
TEXT = "@Castor @Nerin @Assistant hello"


class _Log:
    def __init__(self) -> None:
        self.items: List[Any] = []
        self.lock = threading.Lock()

    def add(self, *item: Any) -> None:
        with self.lock:
            self.items.append(item)


class _Signal:
    def __init__(self, log: _Log, name: str) -> None:
        self._log, self._name = log, name

    def emit(self, *args: Any) -> None:
        self._log.add(self._name, *args)


class _Gateway:
    """Records every call; `refusals` maps an entity to the error its mention raises."""

    def __init__(self, log: _Log, *, agent: str = "not_addressed", refusals: Optional[Dict[str, BaseException]] = None,
                 on_post=None) -> None:
        self.log, self.agent, self.refusals, self.on_post = log, agent, dict(refusals or {}), on_post
        self.starts: List[Dict[str, Any]] = []
        self.posts: List[Dict[str, Any]] = []

    def start_run(self, **kwargs: Any) -> str:
        self.starts.append({"plain": True, **kwargs})
        self.log.add("start_run")
        return "run-agent"

    def start_run_with_mentions(self, *, mentions: List[str], **kwargs: Any) -> Dict[str, Any]:
        self.starts.append({"mentions": list(mentions), **kwargs})
        self.log.add("start_run_with_mentions", tuple(mentions))
        if self.agent == "not_addressed":
            return {"agent": "not_addressed", "run_id": "", "turn_id": "turn-kept"}
        return {"agent": "started", "run_id": "run-agent", "turn_id": "run-agent"}

    def post_mention(self, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.posts.append({"session_id": session_id, **payload})
        entity = payload["entity"]
        self.log.add("post", entity)
        if self.on_post is not None:
            self.on_post(entity)
        refusal = self.refusals.get(entity)
        if refusal is not None:
            raise refusal
        if entity == "malformed":
            return {"reply": "no turn id"}
        return {
            "run_id": f"turn-{entity}",
            "reply": f"{entity} says hi",
            "mention_index": payload["mention_index"],
            "author": {"kind": "entity", "name": entity.title(), "entity_id": f"entity:{entity}", "identity_ref": None, "avatar": None},
            "notices": [],
            "mirrors": [],
        }

    # what the started-agent path reads besides the view
    def get_run(self, run_id: str) -> Dict[str, Any]:
        return {"status": "completed"}

    def get_run_input_data(self, *, run_id: str, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        self.log.add("get_run_input_data", run_id)
        return {}

    def attachments_upload(self, **kwargs: Any) -> Dict[str, Any]:
        self.log.add("upload")
        return {"attachment": {"$artifact": "a1"}}


class _Manager:
    active_session_id = "sess-1"

    def __init__(self, log: _Log) -> None:
        self.log = log
        self.messages: List[Dict[str, Any]] = []
        self.last_run_id = ""

    def gateway_client(self):  # pragma: no cover - the test sets the gateway
        return None

    def set_last_run_id(self, run_id: str) -> None:
        self.last_run_id = run_id

    def append_message(self, **kwargs: Any) -> str:
        self.messages.append(dict(kwargs))
        self.log.add("append", kwargs["role"], kwargs["content"])
        return f"m{len(self.messages)}"

    def session_messages(self) -> List[Dict[str, Any]]:
        return list(self.messages)


def _worker(gateway: _Gateway, log: _Log, mentions, *, text: str = TEXT, resend=None, append_user: bool = True,
            attachments: Optional[List[str]] = None) -> GatewayWorker:
    manager = _Manager(log)
    worker = GatewayWorker(
        llm_manager=manager,
        user_text=text,
        attachments=attachments or [],
        append_user_message=append_user,
        bundle_id="bundle",
        flow_id="flow",
        bundle_version="1.0.0",
        registry_scope="tenant_catalog",
    )
    worker._gateway = gateway
    for name in ("event_emitted", "error_occurred", "warning_occurred", "mention_asked", "mention_answered",
                 "mention_skipped", "mentions_done"):
        setattr(worker, name, _Signal(log, name))
    worker._follow_view = lambda *, run_id, attach: (log.add("follow", run_id), "completed")[1]
    worker.set_mentions(mentions, resend=resend)
    return worker


def _shape(log: _Log) -> List[Any]:
    """The log without the payload objects (mention -> its id)."""
    out: List[Any] = []
    for item in log.items:
        name, *args = item
        if name == "event_emitted":
            ev = args[0]
            if ev.get("type") in ("status", "agent_not_addressed"):
                out.append(("event", ev["type"], ev.get("status") or ev.get("turn_id")))
            continue
        if name in ("mention_asked", "mention_skipped", "mention_answered"):
            out.append((name, args[0].id, *(args[1:] if name == "mention_skipped" else [args[1].run_id] if name == "mention_answered" else [])))
            continue
        if name == "mentions_done":
            out.append((name,))
            continue
        out.append(item)
    return out


def _summary(log: _Log) -> MentionsSummary:
    done = [item[1] for item in log.items if item[0] == "mentions_done"]
    assert len(done) == 1, f"mentions_done must come exactly once, got {len(done)}"
    return done[0]


@pytest.mark.basic
def test_a_message_to_entities_only_starts_no_agent_and_asks_each_in_turn() -> None:
    log = _Log()
    gateway = _Gateway(log, agent="not_addressed")
    worker = _worker(gateway, log, [CASTOR, NERIN], text="@Castor @Nerin hello")
    worker.run()

    assert gateway.starts and all("plain" not in s for s in gateway.starts)  # never the plain agent start
    assert gateway.starts[0]["mentions"] == ["castor", "nerin"]  # no "agent" chip
    assert _shape(log) == [
        ("append", "user", "@Castor @Nerin hello"),
        ("start_run_with_mentions", ("castor", "nerin")),
        ("event", "agent_not_addressed", "turn-kept"),
        ("event", "status", "thinking"),
        ("mention_asked", "castor"),
        ("post", "castor"),
        ("append", "assistant", "castor says hi"),
        ("mention_answered", "castor", "turn-castor"),
        ("mention_asked", "nerin"),
        ("post", "nerin"),
        ("append", "assistant", "nerin says hi"),
        ("mention_answered", "nerin", "turn-nerin"),
        ("mentions_done",),
        ("event", "status", "completed"),
    ]  # no `follow`: no agent run is followed; no workspace/input reads of the kept turn
    assert [p["repeat_of"] for p in gateway.posts] == ["turn-kept", "turn-kept"]
    assert [p["mention_id"] for p in gateway.posts] == ["turn-kept:castor:0", "turn-kept:nerin:1"]
    assert [p["session_id"] for p in gateway.posts] == ["sess-1", "sess-1"]
    summary = _summary(log)
    assert summary.agent_addressed is False and summary.turn_id == "turn-kept" and summary.status_line == ""
    manager = worker._llm_manager
    assert manager.messages[0]["metadata"]["mentions"][0]["id"] == "castor"  # the user row keeps its chips
    answers = [m for m in manager.messages if m["role"] == "assistant"]
    assert [m["metadata"]["author"]["name"] for m in answers] == ["Castor", "Nerin"]
    assert manager.last_run_id == "turn-nerin"  # the newest turn: a later history read includes the answers


@pytest.mark.basic
def test_a_refused_entity_is_signalled_before_the_next_one_is_asked() -> None:
    log = _Log()
    gateway = _Gateway(log, refusals={"castor": GatewayCodedError("x", status=409, code="in_another_conversation", detail="busy")})
    _worker(gateway, log, [CASTOR, NERIN]).run()
    shape = _shape(log)
    assert shape.index(("mention_skipped", "castor", "Castor is in another conversation.")) < shape.index(("mention_asked", "nerin"))
    assert ("mention_answered", "castor", "turn-castor") not in shape
    assert ("mention_answered", "nerin", "turn-nerin") in shape
    assert _summary(log).status_line == "Castor is in another conversation."


@pytest.mark.basic
def test_with_the_agent_chip_the_agent_runs_and_the_entities_answer_beside_it() -> None:
    log = _Log()
    gateway = _Gateway(log, agent="started")
    worker = _worker(gateway, log, [CASTOR, AGENT])
    worker.run()
    shape = _shape(log)
    assert gateway.starts[0]["mentions"] == ["castor", "agent"]
    assert ("follow", "run-agent") in shape  # the agent's run is followed
    assert [p["repeat_of"] for p in gateway.posts] == ["run-agent"]
    assert shape.index(("mentions_done",)) < shape.index(("event", "status", "completed"))
    assert shape[-1] == ("event", "status", "completed")
    summary = _summary(log)
    assert summary.agent_addressed is True and summary.turn_id == "run-agent"
    assert [m.id for m, _ in summary.answered] == ["castor"]


@pytest.mark.basic
def test_a_message_without_chips_is_sent_as_today() -> None:
    log = _Log()
    gateway = _Gateway(log)
    _worker(gateway, log, []).run()
    shape = _shape(log)
    assert gateway.starts == [{"plain": True, **{k: v for k, v in gateway.starts[0].items() if k != "plain"}}]
    assert not gateway.posts
    assert not [s for s in shape if s[0].startswith("mention")]
    assert ("follow", "run-agent") in shape


@pytest.mark.basic
def test_an_entity_that_cannot_answer_stops_and_the_same_words_resend_only_the_unsent() -> None:
    sentence = "Castor cannot answer right now. Try again in a moment."
    log = _Log()
    gateway = _Gateway(log, refusals={"castor": GatewayCodedError("x", status=503, code="entity_cannot_answer", detail=sentence)})
    _worker(gateway, log, [CASTOR, NERIN], text="hi both").run()
    first = _summary(log)
    assert first.stopped == sentence and first.status_line == sentence
    assert [m.id for m in first.unsent] == ["castor", "nerin"]
    assert [p["entity"] for p in gateway.posts] == ["castor"]  # nerin was not asked
    assert first.resend is not None

    log2 = _Log()
    gateway2 = _Gateway(log2)
    _worker(gateway2, log2, [CASTOR, NERIN], text=" hi both ", resend=first.resend).run()
    shape = _shape(log2)
    assert not gateway2.starts  # no new turn of the person
    assert ("upload",) not in shape and not [s for s in shape if s[0] == "append" and s[1] == "user"]
    assert [(p["entity"], p["repeat_of"], p["mention_id"], p["text"]) for p in gateway2.posts] == [
        ("castor", "turn-kept", "turn-kept:castor:0", "hi both"),
        ("nerin", "turn-kept", "turn-kept:nerin:1", "hi both"),
    ]
    assert _summary(log2).answered and _summary(log2).stopped is None


@pytest.mark.basic
def test_new_attachment_after_a_failed_mention_starts_a_new_turn_and_is_uploaded(tmp_path) -> None:
    log = _Log()
    first_gateway = _Gateway(log, refusals={"nerin": GatewayCodedError(
        "busy", status=503, code="entity_cannot_answer", detail="Nerin cannot answer right now.")})
    _worker(first_gateway, log, [CASTOR, NERIN], text="hi").run()
    first = _summary(log)
    assert [mention.id for mention in first.unsent] == ["nerin"]
    held = first.resend
    assert held is not None
    image = tmp_path / "new.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nnew attachment")

    next_log = _Log()
    gateway = _Gateway(next_log)
    worker = _worker(gateway, next_log, list(first.unsent), text="hi", resend=held, attachments=[str(image)])
    worker.run()

    assert ("upload",) in _shape(next_log)
    assert len(gateway.starts) == 1
    assert gateway.starts[0]["mentions"] == ["nerin"]
    assert [post["entity"] for post in gateway.posts] == ["nerin"]
    assert gateway.starts[0]["input_data"]["attachments"] == [{"$artifact": "a1"}]
    assert [row for row in worker._llm_manager.messages if row["role"] == "user"]
    assert _summary(next_log).answered


@pytest.mark.basic
def test_a_malformed_door_answer_stops_with_a_sentence() -> None:
    log = _Log()
    malformed = Mention(id="malformed", name="Malformed", kind="entity", index=0)
    _worker(_Gateway(log), log, [malformed, NERIN]).run()
    summary = _summary(log)
    assert summary.stopped == "Malformed did not answer: The gateway answered the mention of Malformed without its turn."
    assert [m.id for m in summary.unsent] == ["malformed", "nerin"]


@pytest.mark.basic
def test_a_stop_while_an_entity_answers_asks_no_one_more_and_keeps_nothing_after_it() -> None:
    log = _Log()
    stopped = {"now": False}
    gateway = _Gateway(log, on_post=lambda entity: stopped.__setitem__("now", True))
    worker = _worker(gateway, log, [CASTOR, NERIN])
    worker.isInterruptionRequested = lambda: stopped["now"]  # the person pressed Stop mid-answer
    worker.run()
    shape = _shape(log)
    assert [p["entity"] for p in gateway.posts] == ["castor"]
    assert not [s for s in shape if s[0] == "mention_answered"]
    assert not [m for m in worker._llm_manager.messages if m["role"] == "assistant"]
    summary = _summary(log)
    assert summary.aborted is True and [m.id for m in summary.unsent] == ["castor", "nerin"]
    assert shape[-1] == ("event", "status", "cancelled")


@pytest.mark.basic
def test_set_mentions_takes_only_chips_and_only_before_the_start() -> None:
    log = _Log()
    worker = _worker(_Gateway(log), log, [])
    with pytest.raises(TypeError):
        worker.set_mentions([{"id": "castor"}])  # type: ignore[list-item]


@pytest.mark.basic
def test_the_view_of_a_turn_no_agent_answers_gets_no_empty_answer_notice(monkeypatch) -> None:
    log = _Log()
    worker = GatewayWorker(llm_manager=_Manager(log), user_text="", bundle_id="", flow_id="", attach_run_id="turn-kept")
    worker._gateway = _Gateway(log)
    worker.event_emitted = _Signal(log, "event_emitted")

    class _Fold:
        def __init__(self, view: Dict[str, Any]) -> None:
            self.view = view

    def fake_follow(*, gateway, run_id, on_view, **_: Any):
        view = {"root_run_id": run_id, "status": "completed", "agent_addressed": False, "messages": [
            {"id": "u", "role": "user", "text": "@Castor hi", "run_id": run_id}]}
        on_view(view)
        return _Fold(view)

    monkeypatch.setattr(worker_module, "follow_run", fake_follow)
    assert worker._follow_view(run_id="turn-kept", attach=True) == "completed"
    assert not [i for i in log.items if i[0] == "event_emitted" and i[1].get("type") == "assistant"]
