"""`@entity` mentions, desktop: the planner (core/mentions.py, a port of web/src/lib/mentions.ts),
the gateway client's mention calls over a fake transport, and the history that reads them back.

No test reaches a gateway: the client's `urlopen` is replaced by a fake that records the request."""

from __future__ import annotations

import io
import json
import urllib.error
import warnings
from http.client import HTTPMessage
from typing import Any, Dict, List, Optional

import pytest

from abstractassistant.core import mentions as M
from abstractassistant.core.mentions import Mention, MentionAnswer, MentionRequest
from abstractassistant.gateway import client as client_module
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig, GatewayCodedError
from abstractassistant.gateway.history_seed import seed_messages_from_history_bundle
from abstractassistant.gateway.replay_view import ViewProjector

CASTOR = Mention(id="castor", name="Castor", kind="entity", index=0, start=0)
NERIN = Mention(id="nerin", name="Nerin", kind="entity", index=1, start=12)
AGENT = Mention(id="agent", name="Assistant", kind="agent", index=2, start=20)

ROSTER = {
    "entities": [
        {
            "slug": "castor",
            "name": "Castor",
            "identity": {"avatar": {"style": "orb", "color": "#3366ff"}},
            "state": {"state": "awake", "mode": "visiting"},
        },
        {"slug": "nerin", "name": "", "identity": None, "state": {"state": "asleep"}},
        {"slug": "broken", "error": "unreadable manifest: boom"},
        {"slug": "quiet", "name": "Quiet"},
    ]
}


# ---------------------------------------------------------------------------------------------
# The roster
# ---------------------------------------------------------------------------------------------


@pytest.mark.basic
def test_the_roster_offers_the_agent_first_then_the_listed_entities_with_their_looks() -> None:
    roster = M.EntityRoster.from_payload(ROSTER)
    assert [(c.id, c.name, c.kind) for c in roster.candidates] == [
        ("agent", "Assistant", "agent"),
        ("castor", "Castor", "entity"),
        ("nerin", "nerin", "entity"),  # no display name: the slug
        ("quiet", "Quiet", "entity"),
    ]  # the row the gateway marks broken (`error`) is not offered
    assert roster.candidates[1].avatar == M.AvatarLook(style="orb", color="#3366ff")
    assert roster.candidates[2].avatar is None
    assert roster.look_of(CASTOR) == M.AvatarLook(style="orb", color="#3366ff")
    assert roster.look_of(AGENT) is None


@pytest.mark.basic
def test_a_row_without_a_slug_is_said_and_not_offered() -> None:
    with pytest.warns(UserWarning, match="no slug"):
        names = M.entity_candidates({"entities": [{"name": "Ghost"}, {"slug": "castor"}]})
    assert [c.id for c in names] == ["castor"]


@pytest.mark.basic
def test_the_chip_card_says_the_entity_state() -> None:
    cards = M.entity_mention_cards(ROSTER)
    assert cards["castor"].sentence == "Castor is in a conversation."
    assert cards["nerin"].sentence == "nerin is asleep."
    assert cards["quiet"].sentence == ""
    assert "broken" not in cards


@pytest.mark.basic
def test_matching_follows_the_typed_prefix_of_the_name_or_id_in_any_case() -> None:
    roster = M.EntityRoster.from_payload(ROSTER)
    assert [c.id for c in roster.match("CA")] == ["castor"]
    assert [c.id for c in roster.match("ag")] == ["agent"]
    assert [c.id for c in roster.match("")] == ["agent", "castor", "nerin", "quiet"]
    assert roster.match("zz") == []


# ---------------------------------------------------------------------------------------------
# A message's chips
# ---------------------------------------------------------------------------------------------


@pytest.mark.basic
def test_a_chip_is_structured_and_refuses_an_unknown_kind() -> None:
    with pytest.raises(ValueError):
        Mention(id="castor", name="Castor", kind="person", index=0)
    with pytest.raises(ValueError):
        Mention(id="", name="Castor", kind="entity", index=0)
    assert CASTOR.to_dict() == {"id": "castor", "name": "Castor", "kind": "entity", "index": 0, "start": 0}


@pytest.mark.basic
def test_the_start_names_the_chips_in_pick_order_once_with_the_agent_as_agent() -> None:
    later_castor = Mention(id="castor", name="Castor", kind="entity", index=3)
    assert M.start_run_mentions([AGENT, NERIN, CASTOR, later_castor]) == ["castor", "nerin", "agent"]
    assert M.start_run_mentions([]) == []


@pytest.mark.basic
def test_mention_ids_are_built_from_the_message_key() -> None:
    assert M.mention_message_key("run-1") == "run-1"
    minted = M.mention_message_key("", mint=lambda: "msg-x")
    assert minted == "msg-x"
    assert M.mention_message_key(None).startswith("msg-")
    assert M.mention_id("run-1", NERIN) == "run-1:nerin:1"
    with pytest.raises(ValueError):
        M.mention_id("", NERIN)


@pytest.mark.basic
def test_a_resend_asks_only_the_unsent_chips_with_their_first_index() -> None:
    held = M.MentionResend(session_id="s", text="hi all", repeat_of="run-1", message_key="run-1", unsent=(NERIN,))
    quiet = Mention(id="quiet", name="Quiet", kind="entity", index=0)
    again = M.mention_resend(held, " hi all ", [NERIN, quiet])
    assert [(m.id, m.index) for m in again or []] == [("nerin", 1), ("quiet", 2)]
    assert M.mention_resend(held, "something else", [NERIN]) is None
    assert M.mention_resend(held, "hi all", []) is None
    assert M.mention_resend(held, "hi all", [NERIN, AGENT]) is None  # @agent: a new message
    assert M.mention_resend(None, "hi all", [NERIN]) is None


# ---------------------------------------------------------------------------------------------
# Delivery: order, refusals, sentences
# ---------------------------------------------------------------------------------------------


class _Refusal(Exception):
    def __init__(self, status: int, code: str = "", detail: str = "") -> None:
        super().__init__(detail or f"HTTP {status}")
        self.status = status
        self.code = code
        self.detail = detail


def _answer(request: MentionRequest, name: str) -> MentionAnswer:
    return MentionAnswer(
        run_id=f"turn-{request.entity}",
        reply=f"{name} here.",
        mention_index=request.mention_index,
        author={"kind": "entity", "name": name, "entity_id": f"entity:{request.entity}", "identity_ref": None, "avatar": None},
    )


def _deliver(mentions, refusals: Optional[Dict[str, BaseException]] = None, **kw):
    log: List[Any] = []
    requests: List[MentionRequest] = []
    names = {m.id: m.name for m in mentions}

    def post(request: MentionRequest) -> MentionAnswer:
        requests.append(request)
        log.append(("post", request.entity))
        refusal = (refusals or {}).get(request.entity)
        if refusal is not None:
            raise refusal
        return _answer(request, names[request.entity])

    outcome = M.deliver_mentions(
        text="hi all",
        mentions=mentions,
        post=post,
        on_asked=lambda m: log.append(("asked", m.id)),
        on_answer=lambda m, a: log.append(("answered", m.id, a.run_id)),
        on_skipped=lambda m, s: log.append(("skipped", m.id, s)),
        **kw,
    )
    return outcome, log, requests


@pytest.mark.basic
def test_entities_are_asked_one_after_the_other_in_their_order_each_once() -> None:
    twice = Mention(id="castor", name="Castor", kind="entity", index=3)
    outcome, log, requests = _deliver([NERIN, AGENT, CASTOR, twice], repeat_of="run-1")
    assert log == [
        ("asked", "castor"),
        ("post", "castor"),
        ("answered", "castor", "turn-castor"),
        ("asked", "nerin"),
        ("post", "nerin"),
        ("answered", "nerin", "turn-nerin"),
    ]  # the agent chip rode the start; an entity named twice is asked once
    assert [r.to_payload() for r in requests] == [
        {"entity": "castor", "text": "hi all", "mention_index": 0, "mention_id": "run-1:castor:0", "repeat_of": "run-1"},
        {"entity": "nerin", "text": "hi all", "mention_index": 1, "mention_id": "run-1:nerin:1", "repeat_of": "run-1"},
    ]
    assert outcome.message == "run-1"
    assert [a.run_id for _, a in outcome.answered] == ["turn-castor", "turn-nerin"]
    assert M.mention_status_line(outcome) == ""


@pytest.mark.basic
def test_a_mention_without_a_turn_mints_one_key_and_sends_no_repeat_of() -> None:
    outcome, _, requests = _deliver([CASTOR, NERIN])
    assert outcome.message.startswith("msg-")
    assert [r.mention_id for r in requests] == [f"{outcome.message}:castor:0", f"{outcome.message}:nerin:1"]
    assert all("repeat_of" not in r.to_payload() for r in requests)


@pytest.mark.basic
def test_an_entity_elsewhere_or_hidden_is_skipped_with_its_sentence_before_the_next_is_asked() -> None:
    quiet = Mention(id="quiet", name="Quiet", kind="entity", index=2)
    outcome, log, _ = _deliver(
        [CASTOR, NERIN, quiet],
        refusals={
            "castor": _Refusal(409, "in_another_conversation", "busy"),
            "nerin": _Refusal(404, "entity_not_found", "There is no entity called 'nerin'."),
        },
    )
    assert log == [
        ("asked", "castor"),
        ("post", "castor"),
        ("skipped", "castor", "Castor is in another conversation."),
        ("asked", "nerin"),
        ("post", "nerin"),
        ("skipped", "nerin", "Nerin cannot be mentioned here."),
        ("asked", "quiet"),
        ("post", "quiet"),
        ("answered", "quiet", "turn-quiet"),
    ]
    assert M.mention_status_line(outcome) == "Castor is in another conversation. Nerin cannot be mentioned here."
    assert outcome.stopped is None and not outcome.unsent


@pytest.mark.basic
def test_a_gateway_without_the_door_says_so_once_and_asks_no_one_else() -> None:
    outcome, log, _ = _deliver([CASTOR, NERIN], refusals={"castor": _Refusal(404)})
    assert outcome.unavailable is True
    assert [e for e in log if e[0] == "post"] == [("post", "castor")]
    assert M.mention_status_line(outcome) == M.MENTIONS_UNAVAILABLE
    method_missing, _, _ = _deliver([CASTOR], refusals={"castor": _Refusal(405)})
    assert method_missing.unavailable is True


@pytest.mark.basic
def test_an_entity_that_cannot_answer_stops_the_rest_with_the_gateway_sentence() -> None:
    sentence = "Castor cannot answer right now. Try again in a moment."
    outcome, log, _ = _deliver(
        [CASTOR, NERIN], refusals={"castor": _Refusal(503, "entity_cannot_answer", sentence)}, repeat_of="run-1"
    )
    assert outcome.stopped == sentence
    assert outcome.unsent == [CASTOR, NERIN]
    assert ("asked", "nerin") not in log
    summary = M.MentionsSummary.of(outcome, session_id="s1", text="hi all", turn_id="run-1", agent_addressed=False)
    assert summary.status_line == sentence
    assert summary.resend == M.MentionResend(
        session_id="s1", text="hi all", repeat_of="run-1", message_key="run-1", unsent=(CASTOR, NERIN)
    )


@pytest.mark.basic
def test_an_unknown_turn_and_a_failed_call_each_stop_with_one_sentence() -> None:
    unknown, _, _ = _deliver([NERIN], refusals={"nerin": _Refusal(422, "repeat_of_unknown", "x")})
    assert unknown.stopped == "Nerin was not asked: the gateway did not find your message in this conversation."
    refused, _, _ = _deliver([NERIN], refusals={"nerin": ConnectionRefusedError("Connection refused")})
    assert refused.stopped == "Nerin did not answer: Connection refused"
    assert refused.unsent == [NERIN]


@pytest.mark.basic
def test_a_stop_before_an_ask_asks_no_one_more() -> None:
    stop = {"now": False}

    def answered(m: Mention, a: MentionAnswer) -> None:
        stop["now"] = True

    log: List[Any] = []
    outcome = M.deliver_mentions(
        text="hi",
        mentions=[CASTOR, NERIN],
        post=lambda r: (log.append(r.entity), _answer(r, r.entity))[1],
        should_stop=lambda: stop["now"],
        on_answer=answered,
    )
    assert log == ["castor"]
    assert outcome.aborted is True and outcome.unsent == [NERIN]


@pytest.mark.basic
def test_the_door_answer_is_read_loudly() -> None:
    request = MentionRequest(entity="castor", text="hi", mention_index=0, mention_id="k:castor:0")
    with pytest.raises(RuntimeError, match="Castor"):
        M.mention_answer_from({"reply": "hello"}, request, name="Castor")
    answer = M.mention_answer_from(
        {
            "run_id": "turn-9",
            "reply": "hello",
            "author": {"kind": "entity", "name": "Castor", "entity_id": "entity:castor", "identity_ref": None, "avatar": {"style": "orb", "color": "#fff"}},
            "notices": [{"kind": "memory", "record_id": "r1", "title": "Noted"}, "junk"],
            "mirrors": [],
        },
        request,
    )
    assert (answer.run_id, answer.reply, answer.mention_index) == ("turn-9", "hello", 0)
    assert answer.author and answer.author["name"] == "Castor" and answer.author["avatar"] == {"style": "orb", "color": "#fff"}
    assert answer.notices == ({"kind": "memory", "record_id": "r1", "title": "Noted"},)
    meta = M.mention_answer_metadata(answer, CASTOR, repeat_of="run-1")
    assert meta["author"]["kind"] == "entity" and meta["run_id"] == "turn-9" and meta["repeat_of"] == "run-1"
    assert M.bubble_author(meta) == meta["author"]
    assert M.bubble_author({"author": {"kind": "agent", "name": "x"}}) is None
    assert M.bubble_author(None) is None


@pytest.mark.basic
def test_a_malformed_author_is_said_not_kept() -> None:
    with pytest.warns(UserWarning, match="not an author"):
        assert M.read_author({"kind": "robot"}) is None
    assert M.read_author(None) is None


@pytest.mark.basic
def test_a_view_of_a_turn_no_agent_answers_is_known_from_the_view_body() -> None:
    assert M.view_agent_not_addressed({"agent_addressed": False}) is True
    assert M.view_agent_not_addressed({"messages": []}) is False
    assert M.view_agent_not_addressed(None) is False


# ---------------------------------------------------------------------------------------------
# The client, over a fake transport
# ---------------------------------------------------------------------------------------------


class _Resp:
    def __init__(self, body: Dict[str, Any]) -> None:
        self._raw = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def _http_error(url: str, status: int, body: Any, code_header: str = "") -> urllib.error.HTTPError:
    headers = HTTPMessage()
    if code_header:
        headers["X-Gateway-Error-Code"] = code_header
    raw = (json.dumps(body) if not isinstance(body, str) else body).encode("utf-8")
    return urllib.error.HTTPError(url, status, "refused", headers, io.BytesIO(raw))


@pytest.fixture()
def transport(monkeypatch):
    calls: List[Dict[str, Any]] = []
    answers: List[Any] = []

    def fake_urlopen(req, timeout=None):
        calls.append(
            {
                "url": req.full_url,
                "method": req.get_method(),
                "body": json.loads(req.data.decode("utf-8")) if req.data else None,
                "timeout": timeout,
                "headers": dict(req.header_items()),
            }
        )
        answer = answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return _Resp(answer)

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)
    client = GatewayClient(GatewayClientConfig(base_url="http://127.0.0.1:9", auth_token="t"))
    return client, calls, answers


@pytest.mark.basic
def test_the_client_posts_one_mention_to_the_door_and_returns_its_answer(transport) -> None:
    client, calls, answers = transport
    answers.append({"run_id": "turn-1", "reply": "hi", "author": None})
    body = MentionRequest(entity="castor", text="hi all", mention_index=0, mention_id="k:castor:0", repeat_of="run-1").to_payload()
    out = client.post_mention("sess one/2", body)
    assert out["run_id"] == "turn-1"
    assert calls[0]["url"] == "http://127.0.0.1:9/api/gateway/sessions/sess%20one%2F2/mentions"
    assert calls[0]["method"] == "POST" and calls[0]["body"] == body
    assert calls[0]["timeout"] == client_module.MENTION_TIMEOUT_S


@pytest.mark.parametrize(
    "status, body, header, refusal, detail",
    [
        (409, {"detail": "Castor is talking with someone else.", "code": "in_another_conversation", "session_id": "s"}, "in_another_conversation", "elsewhere", "Castor is talking with someone else."),
        (409, {"detail": "busy", "code": "in_another_conversation"}, "", "elsewhere", "busy"),  # body code only
        (404, {"detail": "There is no entity called 'nerin'.", "code": "entity_not_found"}, "entity_not_found", "not_offered", "There is no entity called 'nerin'."),
        (404, {"detail": "Not Found"}, "", "route_missing", "Not Found"),  # a gateway without the route
        (503, {"detail": "Castor cannot answer right now.", "code": "entity_cannot_answer"}, "entity_cannot_answer", "cannot_answer", "Castor cannot answer right now."),
        (422, {"detail": "That earlier message is not one of your own turns.", "code": "repeat_of_unknown"}, "repeat_of_unknown", "repeat_unknown", "That earlier message is not one of your own turns."),
        (500, "Internal Server Error", "", "failed", "Internal Server Error"),
    ],
)
@pytest.mark.basic
def test_the_client_keeps_the_gateway_code_so_every_refusal_maps(transport, status, body, header, refusal, detail) -> None:
    client, _, answers = transport
    answers.append(_http_error("http://x", status, body, header))
    with pytest.raises(GatewayCodedError) as caught:
        client.post_mention("s1", {"entity": "castor", "text": "hi", "mention_index": 0, "mention_id": "k"})
    assert caught.value.status == status
    assert caught.value.detail == detail
    assert M.mention_refusal(caught.value) == refusal


@pytest.mark.basic
def test_a_door_answer_without_its_turn_is_an_error_not_an_answer(transport) -> None:
    client, _, answers = transport
    answers.append({"reply": "hi"})
    with pytest.raises(RuntimeError, match="without its turn"):
        client.post_mention("s1", {"entity": "castor", "text": "hi", "mention_index": 0, "mention_id": "k"})


@pytest.mark.basic
def test_the_start_with_chips_says_whether_the_agent_was_addressed(transport) -> None:
    client, calls, answers = transport
    answers.append({"run_id": "turn-7", "turn_id": "turn-7", "agent": "not_addressed"})
    kept = client.start_run_with_mentions(mentions=["castor"], flow_id="@default", interface="i", input_data={"prompt": "hi"}, session_id="s1")
    assert kept == {"agent": "not_addressed", "run_id": "", "turn_id": "turn-7"}
    assert calls[0]["body"]["mentions"] == ["castor"] and calls[0]["body"]["session_id"] == "s1"
    answers.append({"run_id": "run-8", "agent": "started", "resolved_workflow": {"name": "Assistant"}})
    started = client.start_run_with_mentions(mentions=["castor", "agent"], flow_id="f", bundle_id="b", bundle_version="1", input_data={}, session_id="s1")
    assert started == {"agent": "started", "run_id": "run-8", "turn_id": "run-8"}
    assert client.last_resolved_workflow == {"name": "Assistant"}
    answers.append({"run_id": "run-9"})  # an older gateway: no `agent`, the agent ran
    assert client.start_run_with_mentions(mentions=["castor"], flow_id="f", input_data={}, session_id="s1")["run_id"] == "run-9"
    answers.append({"agent": "not_addressed"})
    with pytest.raises(RuntimeError, match="no turn id"):
        client.start_run_with_mentions(mentions=["castor"], flow_id="f", input_data={}, session_id="s1")
    answers.append(_http_error("http://x", 404, {"detail": "There is no entity called 'zed'.", "code": "entity_not_found"}, "entity_not_found"))
    with pytest.raises(GatewayCodedError, match="There is no entity called 'zed'."):
        client.start_run_with_mentions(mentions=["zed"], flow_id="f", input_data={}, session_id="s1")


@pytest.mark.basic
def test_the_entity_list_is_read_as_is_and_a_malformed_one_is_an_error(transport) -> None:
    client, calls, answers = transport
    answers.append(ROSTER)
    assert client.list_entities() is not None and calls[0]["url"].endswith("/api/gateway/entities")
    assert calls[0]["method"] == "GET"
    answers.append({"items": []})
    with pytest.raises(RuntimeError, match="entities"):
        client.list_entities()


# ---------------------------------------------------------------------------------------------
# Reading the answers back: the history seed and the replay view
# ---------------------------------------------------------------------------------------------


def _author(kind: str, name: Optional[str]) -> Dict[str, Any]:
    return {"kind": kind, "name": name, "entity_id": f"entity:{name.lower()}" if kind == "entity" and name else None, "identity_ref": None, "avatar": None}


def _turn(run_id: str, prompt: str, answer: str, created: str, updated: str, *, author=None, repeat_of=None, prompt_author=None) -> Dict[str, Any]:
    row: Dict[str, Any] = {"run_id": run_id, "prompt": prompt, "answer": answer, "created_at": created, "updated_at": updated}
    if author is not None or prompt_author is not None:
        row["author"] = author
        row["prompt_author"] = prompt_author
        row["repeat_of"] = repeat_of
    return row


def _seed(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return seed_messages_from_history_bundle({"root_run_id": turns[-1]["run_id"], "session": {"turns": turns}})


@pytest.mark.basic
def test_a_reloaded_chat_shows_the_words_once_and_each_answer_as_its_author_in_time_order() -> None:
    person = _author("person", "laurent")
    turns = [
        _turn("run-1", "hi all", "Agent answer.", "2026-11-11T10:00:00Z", "2026-11-11T10:01:00Z", author=_author("agent", "Assistant"), prompt_author=person),
        _turn("m-1", "hi all", "Castor answer.", "2026-11-11T10:00:01Z", "2026-11-11T10:00:20Z", author=_author("entity", "Castor"), prompt_author=person, repeat_of="run-1"),
        _turn("m-2", "hi all", "Nerin answer.", "2026-11-11T10:00:21Z", "2026-11-11T10:00:40Z", author=_author("entity", "Nerin"), prompt_author=person, repeat_of="run-1"),
    ]
    seeded = _seed(turns)
    assert [(m["role"], m["content"]) for m in seeded] == [
        ("user", "hi all"),
        ("assistant", "Castor answer."),
        ("assistant", "Nerin answer."),
        ("assistant", "Agent answer."),
    ]
    assert seeded[0]["metadata"]["author"] == person
    assert [M.bubble_author(m["metadata"])["name"] if M.bubble_author(m["metadata"]) else None for m in seeded[1:]] == ["Castor", "Nerin", None]
    assert seeded[1]["metadata"]["repeat_of"] == "run-1"


@pytest.mark.basic
def test_words_kept_without_an_agent_show_once_before_the_entities() -> None:
    person = _author("person", None)
    turns = [
        _turn("p-1", "@Castor hello", "", "2026-11-11T10:00:00Z", "2026-11-11T10:00:00Z", author=_author("agent", None), prompt_author=person),
        _turn("m-1", "@Castor hello", "Hello!", "2026-11-11T10:00:01Z", "2026-11-11T10:00:09Z", author=_author("entity", "Castor"), prompt_author=person, repeat_of="p-1"),
    ]
    assert [(m["role"], m["content"]) for m in _seed(turns)] == [("user", "@Castor hello"), ("assistant", "Hello!")]


@pytest.mark.basic
def test_repeats_of_a_turn_not_in_the_bundle_keep_the_words_once() -> None:
    turns = [
        _turn("m-1", "hi", "A", "2026-11-11T10:00:01Z", "2026-11-11T10:00:09Z", author=_author("entity", "Castor"), repeat_of="gone"),
        _turn("m-2", "hi", "B", "2026-11-11T10:00:10Z", "2026-11-11T10:00:19Z", author=_author("entity", "Nerin"), repeat_of="gone"),
    ]
    assert [(m["role"], m["content"]) for m in _seed(turns)] == [("user", "hi"), ("assistant", "A"), ("assistant", "B")]


@pytest.mark.basic
def test_turns_from_an_older_gateway_seed_exactly_as_before() -> None:
    turns = [
        _turn("run-1", "hi", "hello", "2026-11-11T10:00:00Z", "2026-11-11T10:00:05Z"),
        _turn("run-2", "hi", "hello again", "2026-11-11T10:01:00Z", "2026-11-11T10:01:05Z"),
    ]
    seeded = _seed(turns)
    assert [m["content"] for m in seeded] == ["hi", "hello", "hi", "hello again"]
    assert "metadata" not in seeded[0]
    assert "author" not in seeded[1]["metadata"]


@pytest.mark.basic
def test_the_replay_view_names_who_wrote_each_answer() -> None:
    projector = ViewProjector()
    view = {
        "root_run_id": "m-1",
        "status": "completed",
        "messages": [
            {"id": "u", "role": "user", "text": "hi", "run_id": "m-1", "author": _author("person", None)},
            {"id": "a", "role": "assistant", "kind": "final", "text": "Hello!", "run_id": "m-1", "author": _author("entity", "Castor")},
        ],
    }
    events = [e for e in projector.project(view) if e["type"] == "assistant"]
    assert events[0]["meta"]["author"]["name"] == "Castor"
    older = ViewProjector().project({"root_run_id": "r", "messages": [{"id": "a", "role": "assistant", "kind": "final", "text": "x"}]})
    assert "author" not in [e for e in older if e["type"] == "assistant"][0]["meta"]
