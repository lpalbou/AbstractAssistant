"""Automations v1 in the Assistant (mission A), against the kit's canonical
fixtures served by a loopback HTTP stub with the contract's paths and error
envelope (contract F). No real gateway: the stub listens on 127.0.0.1 with an
OS-assigned port, and the suite's socket guard refuses anything else.

Covers: the ten client calls (paths and bodies exact, errors typed from
`detail.reason_code`), grouping by `automation_id`, controls (run now while
paused), chat pairs, the regular list without automation/occurrence sessions,
Schedule-this create body, notifications (once per item, never for quiet
ticks), the switcher's Automations section rendered headless, the palette's
automation view (controls, discuss → session switch, a wait answered), and the
three operator scenarios walked end to end against the stub.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

import pytest

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abstractassistant.core import automations as rules
from abstractassistant.core.automations import (
    NotificationLedger,
    ScheduleWhen,
    automation_controls,
    build_create_request,
    group_by_automation,
    new_attention_notices,
    occurrence_views,
    target_from_workflow,
    trigger_summary,
)
from abstractassistant.core.gateway_sessions import fold_session_rows
from abstractassistant.gateway.automations import (
    AUTOMATIONS_PATH,
    AutomationApiError,
    AutomationsClient,
)
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig
from abstractassistant.preferences import WorkflowSelection

FIXTURES = Path(__file__).parent / "fixtures" / "automations"
FIXTURE_FILES = (
    "attention.json",
    "commands.json",
    "errors.json",
    "list.json",
    "occurrences.json",
    "trigger-sources.json",
)
NEWS = "fddce731-4abf-54d3-81b9-15856efbfd7a"
TRIAGE = "53443dd0-25c4-5fa8-bdad-e1ac3fdfff8e"
JOURNAL = "69892c76-5362-5646-a528-b9f982c8d993"
LEGACY = "6e02471f-51ab-499f-a882-2249078e30d0"


def _summary_fixture(aid: str) -> Dict[str, Any]:
    return copy.deepcopy(next(s for s in _fixture("list.json")["items"] if s["automation_id"] == aid))


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------------- fixtures


@pytest.mark.basic
def test_vendored_fixtures_match_their_recorded_checksums() -> None:
    """Byte-identical copies of abstractuic's canonical fixtures: every file
    is listed, and every listed file hashes to its recorded SHA-256."""
    listed: Dict[str, str] = {}
    for line in (FIXTURES / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            listed[name.strip()] = digest
    assert set(listed) == set(FIXTURE_FILES)
    for name in FIXTURE_FILES:
        path = FIXTURES / name
        assert path.is_file(), f"missing fixture {name}"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == listed[name], f"{name} drifted from CHECKSUMS.sha256"


# ----------------------------------------------------------------- the stub


class StubGateway:
    """Contract-F routes over the fixtures, with the state changes the
    contract describes (pause gates scheduled runs only, run now allowed while
    paused, archive keeps history, revise bumps the revision)."""

    def __init__(self) -> None:
        self.summaries: List[Dict[str, Any]] = copy.deepcopy(_fixture("list.json")["items"])
        self.occurrences: Dict[str, List[Dict[str, Any]]] = {TRIAGE: copy.deepcopy(_fixture("occurrences.json")["items"])}
        self.attention: Dict[str, List[Dict[str, Any]]] = {TRIAGE: copy.deepcopy(_fixture("attention.json")["items"])}
        self.errors = {item["body"]["detail"]["reason_code"]: item for item in _fixture("errors.json")["items"]}
        self.trigger_sources = _fixture("trigger-sources.json")
        # The capabilities descriptor G advertises (contract F).
        self.capabilities: Dict[str, Any] = {
            "capabilities": {
                "contracts": {
                    "version": 1,
                    "common": {
                        "automations": {
                            "available": True,
                            "version": 1,
                            "endpoint": AUTOMATIONS_PATH,
                            "trigger_sources_endpoint": "/api/gateway/trigger-sources",
                        }
                    },
                }
            }
        }
        self.requests: List[Dict[str, Any]] = []
        self.created: Dict[str, Dict[str, Any]] = {}
        self.run_rows: List[Dict[str, Any]] = [
            {"run_id": "chat-run-1", "session_id": "sess_chat", "status": "completed", "created_at": "2026-09-27T06:00:00Z", "updated_at": "2026-09-27T06:00:10Z", "session_kind": "chat"},
            # An id that LOOKS like an automation is still a chat: kind rules, never prefixes.
            {"run_id": "decoy-run", "session_id": "automation:decoy", "status": "completed", "created_at": "2026-09-27T05:00:00Z", "updated_at": "2026-09-27T05:00:10Z", "session_kind": "chat"},
            # The growing triage controller root: an automation session.
            {"run_id": TRIAGE, "session_id": "automation-session-triage", "status": "running", "created_at": "2026-09-27T04:00:00Z", "updated_at": "2026-09-27T06:30:04Z", "session_kind": "automation", "automation_id": TRIAGE, "role": "controller"},
        ] + [
            {"run_id": o["run_id"], "session_id": f"occ-{o['index']}", "status": o["status"], "created_at": o["fired_at"], "updated_at": o["fired_at"], "session_kind": "occurrence", "automation_id": TRIAGE, "role": "occurrence", "occurrence_index": o["index"], "parent_run_id": TRIAGE}
            for o in _fixture("occurrences.json")["items"]
        ]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def summary(self, aid: str) -> Optional[Dict[str, Any]]:
        return next((s for s in self.summaries if s["automation_id"] == aid), None)

    def calls(self, method: str = "", path_prefix: str = "") -> List[Dict[str, Any]]:
        return [r for r in self.requests if (not method or r["method"] == method) and r["path"].startswith(path_prefix)]

    # ------------------------------------------------------------ routing

    def route(self, method: str, path: str, query: Dict[str, List[str]], body: Any):
        if path == "/api/gateway/discovery/capabilities" and method == "GET":
            return 200, self.capabilities
        if path == "/api/gateway/trigger-sources" and method == "GET":
            return 200, self.trigger_sources
        if path == "/api/gateway/commands" and method == "POST":
            return self._run_command(body)
        if path == "/api/gateway/runs" and method == "GET":
            return 200, {"items": list(self.run_rows), "has_more": False}
        if path == AUTOMATIONS_PATH:
            if "changed_since" in query:
                return self._error("unsupported_feature")
            if method == "GET":
                return 200, {"items": copy.deepcopy(self.summaries), "next_cursor": None}
            if method == "POST":
                return self._create(body)
        prefix = AUTOMATIONS_PATH + "/"
        if not path.startswith(prefix):
            return 404, {"detail": "Not Found"}
        parts = path[len(prefix):].split("/")
        aid, tail = parts[0], "/".join(parts[1:])
        summary = self.summary(aid)
        if summary is None:
            return self._error("automation_not_found")
        if tail == "" and method == "GET":
            return 200, {"definition": {"title": summary["title"]}, "active_revision": summary["revision"], "summary": summary}
        if tail == "" and method == "PATCH":
            return self._revise(summary, body)
        if tail == "commands" and method == "POST":
            return self._command(summary, body)
        if tail == "occurrences" and method == "GET":
            return 200, {"items": copy.deepcopy(self.occurrences.get(aid, [])), "next_cursor": None}
        if tail == "attention" and method == "GET":
            return 200, {"items": copy.deepcopy(self.attention.get(aid, [])), "next_cursor": None}
        if tail == "seen" and method == "POST":
            att = summary["attention"]
            att.update({"unseen_count": 0, "unread": False, "items": []})
            self.attention[aid] = []
            return 200, {"attention_cursor": body["attention_cursor"]}
        if tail == "discuss" and method == "POST":
            rid = str(uuid.uuid5(uuid.UUID(aid), "discuss:" + body["request_id"]))
            sid = str(uuid.uuid5(uuid.UUID(aid), "discussion-session:" + body["request_id"]))
            self.run_rows.append({"run_id": rid, "session_id": sid, "status": "running", "created_at": "2026-09-27T07:00:00Z", "updated_at": "2026-09-27T07:00:01Z", "session_kind": "discussion", "automation_id": aid, "role": "discussion"})
            return 200, {"session_id": sid, "run_id": rid, "session_kind": "discussion"}
        return 404, {"detail": "Not Found"}

    def _error(self, code: str, **extra: Any):
        item = copy.deepcopy(self.errors[code])
        item["body"]["detail"].update(extra)
        return item["status"], item["body"]

    def _receipt(self, command_id: str, seq: int = 1) -> Dict[str, Any]:
        return {"command_id": command_id, "accepted": True, "duplicate": False, "seq": seq}

    def _create(self, body: Dict[str, Any]):
        if body["request_id"] in self.created:
            return 200, self.created[body["request_id"]]
        aid = str(uuid.uuid5(uuid.NAMESPACE_URL, "automation:" + body["request_id"]))
        summary = {
            "automation_id": aid,
            "title": body["title"],
            "status": "active",
            "trigger": {"binding_id": str(uuid.uuid4()), **body["trigger"]},
            "context_mode": body.get("context", {}).get("mode", "independent"),
            "next_fire_at": "2026-09-27T12:00:00Z",
            "occurrence_count": 0,
            "attention": {"pending_waits": 0, "unread": False, "unseen_count": 0, "cursor": "att1:0", "items": [], "waits": []},
            "legacy": False,
            "revision": 1,
            "updated_at": "2026-09-27T07:00:00Z",
            "capabilities": ["revise", "pause", "resume", "run_now", "stop_current", "archive", "discuss"],
            "session_kind": "automation",
        }
        self.summaries.append(summary)
        response = {"automation_id": aid, "revision": 1, "summary": summary}
        self.created[body["request_id"]] = response
        return 200, response

    def _revise(self, summary: Dict[str, Any], body: Dict[str, Any]):
        expected = body.get("expected_revision")
        if expected is not None and expected != summary["revision"]:
            return self._error("revision_conflict", command_id=body["command_id"])
        changes = body["changes"]
        if "title" in changes:
            summary["title"] = changes["title"]
        if "context" in changes:
            summary["context_mode"] = changes["context"]["mode"]
        if "trigger" in changes:
            summary["trigger"] = {"binding_id": str(uuid.uuid4()), **changes["trigger"]}
        summary["revision"] += 1
        return 200, self._receipt(body["command_id"], 41)

    def _command(self, summary: Dict[str, Any], body: Dict[str, Any]):
        type_ = body["type"]
        if summary["status"] == "archived":
            return self._error("invalid_state", command_id=body["command_id"])
        if type_ == "automation.pause":
            summary["status"] = "paused"
        elif type_ == "automation.resume":
            summary["status"] = "active"
        elif type_ == "automation.archive":
            summary["status"] = "archived"
        elif type_ == "automation.run_now":
            last = summary.get("last_occurrence") or {}
            if last.get("status") in {"running", "waiting"}:
                return self._error("automation_busy", command_id=body["command_id"])
            summary["occurrence_count"] += 1
            summary["last_occurrence"] = {"run_id": str(uuid.uuid4()), "index": summary["occurrence_count"], "status": "running", "attempts": 1, "fired_at": "2026-09-27T07:01:00Z", "excerpt": "", "notify": None}
        return 200, self._receipt(body["command_id"], 42)

    def _run_command(self, body: Dict[str, Any]):
        # Answering an occurrence's wait: the occurrence completes.
        if body.get("type") == "resume":
            for aid, rows in self.occurrences.items():
                for row in rows:
                    if row["run_id"] == body["run_id"] and row["waits"]:
                        row["waits"] = []
                        row["status"] = "completed"
                        row["answer"] = f"Replied: {json.dumps(body['payload']['payload'], sort_keys=True)}"
                        att = self.summary(aid)["attention"]
                        att["pending_waits"] = 0
                        att["waits"] = []
        return 200, {"accepted": True}

    def _handler(self):
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                return

            def _serve(self, method: str) -> None:
                parts = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw) if raw else None
                stub.requests.append({"method": method, "path": parts.path, "query": parse_qs(parts.query), "body": body, "headers": dict(self.headers)})
                status, payload = stub.route(method, parts.path, parse_qs(parts.query), body)
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                self._serve("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._serve("POST")

            def do_PATCH(self) -> None:  # noqa: N802
                self._serve("PATCH")

        return Handler


@pytest.fixture
def stub():
    gateway = StubGateway()
    yield gateway
    gateway.close()


def _gateway(stub: StubGateway) -> GatewayClient:
    return GatewayClient(GatewayClientConfig(base_url=stub.url, auth_token="test-token", timeout_s=5.0))


def _client(stub: StubGateway) -> AutomationsClient:
    return AutomationsClient(_gateway(stub))


# --------------------------------------------------------------- the client


@pytest.mark.basic
def test_client_sends_the_exact_paths_and_bodies_of_contract_f(stub) -> None:
    client = _client(stub)
    commands = {c["name"]: c for c in _fixture("commands.json")["items"]}

    page = client.list()
    assert [s["automation_id"] for s in page["items"]] == [TRIAGE, NEWS, JOURNAL, LEGACY]
    assert client.get(NEWS)["summary"]["title"] == "AI news monitor"

    revise = commands["revise"]["request"]
    receipt = client.revise(NEWS, changes=revise["body"]["changes"], expected_revision=1, command_id=revise["body"]["command_id"])
    assert receipt["command_id"] == revise["body"]["command_id"]
    sent = stub.calls("PATCH")[-1]
    assert (sent["path"], sent["body"]) == (revise["path"], revise["body"])

    for name in ("pause", "run_now while paused", "resume", "archive"):
        request = commands[name]["request"]
        aid = request["path"].split("/")[4]
        client.command(aid, request["body"]["type"], command_id=request["body"]["command_id"])
        sent = stub.calls("POST", AUTOMATIONS_PATH)[-1]
        assert (sent["method"], sent["path"], sent["body"]) == (request["method"], request["path"], request["body"])

    assert client.occurrences(TRIAGE)["items"][0]["index"] == 7
    assert stub.calls("GET")[-1]["path"] == f"{AUTOMATIONS_PATH}/{TRIAGE}/occurrences"
    assert client.attention(TRIAGE)["items"][0]["cursor"] == "att1:1"
    assert stub.calls("GET")[-1]["path"] == f"{AUTOMATIONS_PATH}/{TRIAGE}/attention"

    out = client.discuss(TRIAGE, occurrence_index=6, prompt="Why nothing urgent?", request_id="req-d1")
    assert out["session_kind"] == "discussion"
    sent = stub.calls("POST")[-1]
    assert sent["path"] == f"{AUTOMATIONS_PATH}/{TRIAGE}/discuss"
    assert sent["body"] == {"request_id": "req-d1", "occurrence_index": 6, "prompt": "Why nothing urgent?"}

    assert client.seen(TRIAGE, "att1:2") == {"attention_cursor": "att1:2"}
    assert stub.calls("POST")[-1]["body"] == {"attention_cursor": "att1:2"}

    body, errors = build_create_request(
        prompt="Watch AI news", when=ScheduleWhen("every", 8, "h"), context="independent",
        target={"bundle_ref": "b@1", "flow_id": "f"}, request_id="req-c1",
    )
    assert not errors
    created = client.create(body)
    assert stub.calls("POST")[-1]["path"] == AUTOMATIONS_PATH and stub.calls("POST")[-1]["body"] == body
    assert created["summary"]["title"] == "Watch AI news"

    assert [s["id"] for s in client.trigger_sources()["items"]] == ["schedule", "manual"]
    assert stub.calls("GET")[-1]["path"] == "/api/gateway/trigger-sources"

    # Auth rides every call; v1 never sends changed_since.
    assert all(r["headers"].get("Authorization") == "Bearer test-token" for r in stub.requests)
    assert not any("changed_since" in r["query"] for r in stub.requests)


@pytest.mark.basic
def test_every_error_envelope_becomes_a_typed_error(stub) -> None:
    items = _fixture("errors.json")["items"]
    for item in items:
        stub.route = lambda *_a, item=item: (item["status"], item["body"])  # type: ignore[assignment]
        with pytest.raises(AutomationApiError) as caught:
            _client(stub).list()
        detail = item["body"]["detail"]
        assert (caught.value.status, caught.value.reason_code, caught.value.message) == (item["status"], detail["reason_code"], detail["message"])
        assert caught.value.field == detail.get("field")
        assert caught.value.command_id == detail.get("command_id")
    # A non-2xx without the envelope never passes for a result.
    stub.route = lambda *_a: (404, {"detail": "Not Found"})  # type: ignore[assignment]
    with pytest.raises(AutomationApiError) as caught:
        _client(stub).list()
    assert (caught.value.status, caught.value.reason_code) == (404, "invalid_response")
    # Nor does a 2xx that is not a JSON object.
    stub.route = lambda *_a: (200, [1, 2])  # type: ignore[assignment]
    with pytest.raises(AutomationApiError) as caught:
        _client(stub).list()
    assert caught.value.reason_code == "invalid_response"


@pytest.mark.basic
def test_an_unreachable_gateway_is_a_typed_error_with_no_answer() -> None:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]  # closed again: connection refused
    client = AutomationsClient(GatewayClient(GatewayClientConfig(base_url=f"http://127.0.0.1:{port}", timeout_s=2.0)))
    with pytest.raises(AutomationApiError) as caught:
        client.list()
    assert (caught.value.status, caught.value.reason_code) == (0, "unreachable")


@pytest.mark.basic
def test_the_wait_answer_is_the_existing_resume_command(stub) -> None:
    _gateway(stub).submit_wait_response(
        run_id="ade23773-2d37-5460-973c-08d35f7af010",
        wait_key="ask_user:reply-landlord",
        payload={"response": "Reply: Tuesday works"},
    )
    sent = stub.calls("POST", "/api/gateway/commands")[-1]["body"]
    assert sent["type"] == "resume" and sent["run_id"] == "ade23773-2d37-5460-973c-08d35f7af010"
    assert sent["payload"] == {"wait_key": "ask_user:reply-landlord", "payload": {"response": "Reply: Tuesday works"}}


# ------------------------------------------------------------------ the rules


@pytest.mark.basic
def test_the_section_groups_by_automation_id_never_by_session() -> None:
    items = _fixture("list.json")["items"]
    # The same automation twice (a second page repeating it) is still ONE row.
    grouped = group_by_automation(items + [dict(items[0], title="Inbox triage (renamed)")])
    assert [s["automation_id"] for s in grouped] == [TRIAGE, NEWS, JOURNAL, LEGACY]
    assert grouped[0]["title"] == "Inbox triage (renamed)"
    assert [trigger_summary(s["trigger"]) for s in items] == [
        "every 30 minutes (UTC)",
        "every 8 hours (UTC)",
        "every 7 days (UTC) · 12 runs max",
        "every hour (UTC)",
    ]


@pytest.mark.basic
def test_controls_follow_status_and_run_now_stays_enabled_while_paused() -> None:
    news, triage, journal, legacy_row = (_summary_fixture(a) for a in (NEWS, TRIAGE, JOURNAL, LEGACY))
    paused = automation_controls(journal)
    assert paused["run_now"][0] is True, "run now must stay enabled while paused"
    assert paused["pause"][0] is False and paused["resume"][0] is True
    active = automation_controls(news)
    assert active["pause"][0] is True and active["resume"][0] is False and active["run_now"][0] is True
    assert active["stop_current"][0] is False
    busy = automation_controls(triage)  # the last occurrence is waiting
    assert busy["run_now"][0] is False and busy["stop_current"][0] is True
    archived = automation_controls(dict(news, status="archived"))
    assert not any(enabled for enabled, _ in archived.values())
    legacy = automation_controls(legacy_row)  # the real legacy row: capabilities ["legacy"]
    assert not any(enabled for enabled, _ in legacy.values())
    # Archived rows only offer discuss (capabilities per status).
    assert automation_controls(dict(news, status="archived", capabilities=["discuss"]))["discuss"][0] is False
    assert automation_controls(dict(news, capabilities=["pause"]))["discuss"][0] is False
    assert not any(enabled for enabled, _ in automation_controls(news, busy=True).values())


@pytest.mark.basic
def test_occurrences_read_as_chat_pairs_oldest_first() -> None:
    views = occurrence_views(_fixture("occurrences.json")["items"])
    assert [v.row["index"] for v in views] == [1, 2, 3, 4, 5, 6, 7]
    tones = {v.row["index"]: v.tone for v in views}
    assert tones == {1: "quiet", 2: "notified", 3: "quiet", 4: "quiet", 5: "failed", 6: "quiet", 7: "waiting"}
    by_index = {v.row["index"]: v for v in views}
    assert by_index[5].badge == "Failed after 3 attempts"
    assert by_index[3].status_text == "completed after 2 attempts"
    assert by_index[7].can_discuss is False and by_index[6].can_discuss is True


@pytest.mark.basic
def test_the_regular_list_keeps_chats_and_discussions_only() -> None:
    occurrences = _fixture("occurrences.json")["items"]
    rows = [
        {"run_id": "r-chat", "session_id": "sess_a", "status": "completed", "created_at": "2026-09-27T06:00:00Z", "session_kind": "chat"},
        {"run_id": "r-decoy", "session_id": "automation:decoy", "status": "completed", "created_at": "2026-09-27T05:00:00Z", "session_kind": "chat"},
        {"run_id": "r-decoy2", "session_id": "scheduled:decoy", "status": "completed", "created_at": "2026-09-27T05:00:00Z"},
        {"run_id": TRIAGE, "session_id": "automation-session", "status": "running", "created_at": "2026-09-27T04:00:00Z", "session_kind": "automation", "automation_id": TRIAGE},
        {"run_id": "r-disc", "session_id": "disc-1", "status": "completed", "created_at": "2026-09-27T07:00:00Z", "session_kind": "discussion", "automation_id": TRIAGE},
    ] + [
        # Turn roots include ROOT-less occurrences of independent automations.
        {"run_id": o["run_id"], "session_id": f"occ-{o['index']}", "status": o["status"], "created_at": o["fired_at"], "session_kind": "occurrence", "automation_id": TRIAGE}
        for o in occurrences
    ]
    folded, _ = fold_session_rows({"items": rows, "has_more": False})
    kinds = {row.session_id: (row.session_kind, row.automation_id) for row in folded}
    assert kinds == {
        "sess_a": ("chat", ""),
        "automation:decoy": ("chat", ""),
        "scheduled:decoy": ("", ""),
        "disc-1": ("discussion", TRIAGE),
    }


@pytest.mark.basic
def test_schedule_this_builds_the_exact_create_body() -> None:
    chosen = WorkflowSelection(bundle_id="abstractassistant.agent", flow_id="main", bundle_version="0.0.3", interface="abstractassistant.agent.v1")
    assert target_from_workflow(chosen) == {"bundle_ref": "abstractassistant.agent@0.0.3", "flow_id": "main"}
    default = WorkflowSelection(bundle_id="x", flow_id="@default", interface="abstractassistant.agent.v1")
    assert target_from_workflow(default) == {"flow_id": "@default", "interface": "abstractassistant.agent.v1"}
    assert target_from_workflow(None) is None

    body, errors = build_create_request(
        prompt="  Search the news about AI agents and summarise what changed.\nKeep it short. ",
        when=ScheduleWhen("every", 8, "h"),
        context="growing",
        target=target_from_workflow(chosen),
        request_id="req-42",
        start_at="2026-09-28 08:00",
    )
    assert errors == []
    assert body == {
        "request_id": "req-42",
        "title": "Search the news about AI agents and summarise what changed.",
        "target": {
            "bundle_ref": "abstractassistant.agent@0.0.3",
            "flow_id": "main",
            "input_data": {"prompt": "Search the news about AI agents and summarise what changed.\nKeep it short."},
        },
        "trigger": {"source_id": "schedule", "source_version": 1, "config": {"every": "8h", "start_at": "2026-09-28T08:00:00Z"}},
        "context": {"mode": "growing"},
        "policy": {"tool_approval": "auto"},
    }
    once, errors = build_create_request(
        prompt="Remind me", when=ScheduleWhen("once", at="2026-09-28 09:30"), context="independent",
        target={"flow_id": "@default", "interface": "i"}, request_id="r",
    )
    assert once["trigger"]["config"] == {"start_at": "2026-09-28T09:30:00Z"} and errors == []
    missing, errors = build_create_request(prompt="", when=ScheduleWhen("every", 0, "h"), context="independent", target=None, request_id="r")
    assert missing is None and len(errors) == 3


@pytest.mark.basic
def test_notifications_fire_once_per_item_and_never_for_quiet_ticks(tmp_path) -> None:
    summaries = _fixture("list.json")["items"]
    ledger = NotificationLedger(tmp_path / "notified.json")
    pages = {TRIAGE: _fixture("attention.json")["items"]}
    first = new_attention_notices(summaries, pages, ledger)
    assert [(n.kind, n.title) for n in first] == [
        ("notify", "2 urgent emails"),
        ("failure", "Inbox triage failed"),
        ("wait", "Inbox triage is waiting for you"),
        ("wait", "Inbox triage needs your approval"),
    ]
    ledger.add(n.key for n in first)
    assert new_attention_notices(summaries, pages, ledger) == []
    # A relaunch does not replay them.
    assert new_attention_notices(summaries, pages, NotificationLedger(tmp_path / "notified.json")) == []
    # A quiet tick (completed, notify null, no attention item) never notifies,
    # even when it is new; the news monitor's last run is exactly that.
    news = _summary_fixture(NEWS)
    quiet = dict(news, last_occurrence=dict(news["last_occurrence"], index=7, run_id="new-quiet"))
    assert new_attention_notices([quiet], {}, NotificationLedger()) == []


@pytest.mark.basic
def test_seen_acknowledges_the_last_displayed_item_not_the_latest_cursor() -> None:
    triage = _summary_fixture(TRIAGE)
    # More unseen items exist than the summary displays (<= 20): the latest
    # cursor is beyond the last displayed item and must stay unseen.
    beyond = dict(triage, attention=dict(triage["attention"], cursor="att1:9", unseen_count=9))
    assert rules.attention_ack_cursor(beyond) == "att1:2"
    assert rules.attention_ack_cursor(_summary_fixture(NEWS)) is None


# --------------------------------------------------------------------- Qt


def _qt():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


_APP = None


@pytest.mark.basic
def test_headless_switcher_renders_the_automations_section_from_the_fixtures(tmp_path) -> None:
    global _APP
    _APP = _qt()
    from abstractassistant.core.session_digest import SessionDigest
    from abstractassistant.ui.session_switcher import SessionSwitcher

    switcher = SessionSwitcher()
    chosen: List[str] = []
    switcher.automation_chosen.connect(chosen.append)
    switcher.set_automations(_fixture("list.json")["items"])
    switcher.set_digests(
        [
            SessionDigest(session_id="sess_chat", title="Release prep", updated_at="2026-09-27T06:00:00Z"),
            SessionDigest(session_id="disc-1", title="Why nothing urgent?", updated_at="2026-09-27T07:00:00Z", session_kind="discussion", automation_id=TRIAGE),
        ],
        active_session_id="sess_chat",
    )
    switcher.resize(460, 640)
    switcher.show()
    _APP.processEvents()
    rows = switcher.automation_rows
    assert [r.automation_id for r in rows] == [TRIAGE, NEWS, JOURNAL, LEGACY]
    assert rows[0].badge_text == "2 NEW · WAITING"
    assert rows[0].cadence_label.text() == "every 30 minutes (UTC) · Active · growing"
    assert rows[2].next_label.text() == "paused"
    # The real gateway sends an empty excerpt while waiting: the question shows.
    assert "waiting for you: The landlord asks" in rows[0].excerpt_label.text()
    assert switcher._automation_label.text() == "AUTOMATIONS · 4 NEW"
    # Regular rows below; the discussion carries its badge.
    assert [r.session_id for r in switcher._rows] == ["disc-1", "sess_chat"]
    about = switcher._rows[0].about_button
    assert about is not None and about.text() == "about automation Inbox triage"
    assert switcher._rows[1].about_button is None
    about.click()
    assert chosen == [TRIAGE]
    image = switcher.grab()
    assert not image.isNull() and image.width() >= 400
    image.save(str(tmp_path / "switcher.png"))
    switcher.close()
    switcher.deleteLater()


# -------------------------------------------------------------- the palette


def _smoke():
    spec = importlib.util.spec_from_file_location("_palette_smoke_harness", Path(__file__).parent / "test_palette_smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def palette(stub, tmp_path, monkeypatch):
    global _APP
    _APP = _qt()
    import abstractassistant.app as app_module

    # Headless review method: no native traffic-light bridge, no global hotkey.
    monkeypatch.setattr(app_module, "_MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE", False)
    smoke = _smoke()
    gateway = _gateway(stub)

    class Controller(smoke._Controller):
        def __init__(self) -> None:
            super().__init__()
            self.opened: List[Dict[str, str]] = []
            self._messages = [{"role": "user", "content": "Summarise today's AI news in five bullets."}, {"role": "assistant", "content": "…"}]

        def automations_client(self):
            return AutomationsClient(gateway)

        def automation_notification_ledger_path(self):
            return tmp_path / "automations_notified.json"

        def automations_available(self) -> bool:
            # The real read: the gateway's capabilities call, freshly fetched.
            from abstractassistant.gateway.capabilities import get_cached_assistant_capabilities

            caps = get_cached_assistant_capabilities(gateway, force=True)
            if caps.error:
                raise RuntimeError(caps.error)
            return caps.automations_available()

        def session_messages(self):
            return list(self._messages)

        def last_user_prompt(self) -> str:
            return "Summarise today's AI news in five bullets."

        def current_workflow(self):
            return WorkflowSelection(bundle_id="abstractassistant.agent", flow_id="main", bundle_version="0.0.3", label="Assistant")

        def answer_wait(self, *, run_id, wait_key, kind, answer):
            from abstractassistant.gateway.client import wait_answer_payload

            return gateway.submit_wait_response(run_id=run_id, wait_key=wait_key, payload=wait_answer_payload(kind, answer))

        def open_gateway_session(self, session_id, *, run_id):
            self.opened.append({"session_id": session_id, "run_id": run_id})
            self.active_session_id = session_id

    controller = Controller()
    window = app_module.AssistantPalette(controller=controller, debug=False)
    smoke._wait_for_bootstrap(window)
    window._automations.synchronous = True
    notified: List[tuple] = []
    monkeypatch.setattr(window, "_notify", lambda title, message, **_kw: notified.append((title, message)))
    window._notified = notified
    yield window, controller
    try:
        window.shutdown()
    except Exception:
        pass
    window.deleteLater()
    _APP.processEvents()


@pytest.mark.basic
def test_palette_poll_notifies_once_and_opens_an_automation_with_its_controls(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    assert [t for t, _ in window._notified] == [
        "2 urgent emails",
        "Inbox triage failed",
        "Inbox triage is waiting for you",
        "Inbox triage needs your approval",
    ]
    window._poll_automations()
    assert len(window._notified) == 4, "a second poll must not notify again"
    assert window._automations.unread == 4  # 2 unseen + 2 waits
    assert window._automations_menu_action is None or "new" in window._automations_menu_action.text()

    window._open_automation(TRIAGE)
    view = window.automation_view
    assert view.isVisibleTo(window) and not window.history_scroll.isVisibleTo(window)
    assert [p.index for p in view.pairs] == [1, 2, 3, 4, 5, 6, 7]
    tones = [p.answer.property("tone") for p in view.pairs]
    assert tones == ["quiet", "notified", "quiet", "quiet", "failed", "quiet", "waiting"]
    # The failed pair shows its failure reason and attempts.
    failed_texts = [w.text() for w in view.pairs[4].answer.findChildren(type(view.title_label))]
    assert any("IMAP read timed out" in t and "3 attempts" in t for t in failed_texts)
    # Viewing acknowledged the DISPLAYED items (the last one's cursor).
    assert stub.calls("POST", f"{AUTOMATIONS_PATH}/{TRIAGE}/seen")[-1]["body"] == {"attention_cursor": "att1:2"}
    # Busy (waiting occurrence): run now off, stop current on.
    assert not view.control_buttons["run_now"].isEnabled()
    assert view.control_buttons["stop_current"].isEnabled()
    window._close_automation_view()
    assert window.history_scroll.isVisibleTo(window) and not view.isVisibleTo(window)


@pytest.mark.basic
def test_run_now_while_paused_and_archive_confirmed_in_the_palette(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_automation(JOURNAL)
    view = window.automation_view
    assert view.control_buttons["run_now"].isEnabled() and view.control_buttons["resume"].isEnabled()
    assert not view.control_buttons["pause"].isEnabled()
    view.control_buttons["run_now"].click()
    sent = stub.calls("POST", f"{AUTOMATIONS_PATH}/{JOURNAL}/commands")[-1]["body"]
    assert sent["type"] == "automation.run_now"
    assert stub.summary(JOURNAL)["status"] == "paused", "run now does not resume"
    # Archive asks inside the palette first; nothing is sent until confirmed.
    before = len(stub.calls("POST", f"{AUTOMATIONS_PATH}/{JOURNAL}/commands"))
    view.control_buttons["archive"].click()
    assert view.archive_confirm.isVisibleTo(view)
    assert len(stub.calls("POST", f"{AUTOMATIONS_PATH}/{JOURNAL}/commands")) == before
    view.archive_yes.click()
    assert stub.calls("POST", f"{AUTOMATIONS_PATH}/{JOURNAL}/commands")[-1]["body"]["type"] == "automation.archive"
    assert stub.summary(JOURNAL)["status"] == "archived"
    assert not any(b.isEnabled() for b in view.control_buttons.values())


@pytest.mark.basic
def test_a_gateway_error_ends_the_action_and_a_lost_answer_retries_with_the_same_id(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_automation(NEWS)
    view = window.automation_view
    view.control_buttons["pause"].click()
    view.control_buttons["resume"].setEnabled(True)
    stub.summary(NEWS)["status"] = "archived"  # the gateway now refuses
    view.control_buttons["resume"].click()
    assert "does not allow" in view.error_label.text()
    assert not view.retry_button.isVisibleTo(view), "a gateway answer ends the action: no same-id retry"
    ids = [c["body"]["command_id"] for c in stub.calls("POST", f"{AUTOMATIONS_PATH}/{NEWS}/commands")]
    assert len(set(ids)) == len(ids)

    # No gateway answer (connection refused): Retry re-sends the SAME id.
    hub = window._automations
    real_factory = hub._client_factory
    attempts: List[str] = []

    class Lost:
        def command(self, aid, type_, *, command_id):
            attempts.append(command_id)
            raise AutomationApiError(status=0, reason_code="unreachable", message="refused")

    hub._client_factory = lambda: Lost()
    stub.summary(NEWS)["status"] = "active"
    view.set_summary(stub.summary(NEWS))
    view.control_buttons["pause"].click()
    assert view.retry_button.isVisibleTo(view)
    hub._client_factory = real_factory
    view.retry_button.click()
    sent = stub.calls("POST", f"{AUTOMATIONS_PATH}/{NEWS}/commands")[-1]["body"]
    assert sent["command_id"] == attempts[0]
    assert stub.summary(NEWS)["status"] == "paused"


@pytest.mark.basic
def test_edit_sends_only_the_changed_fields_with_the_expected_revision(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_automation(NEWS)
    view = window.automation_view
    view.control_buttons["revise"].click()
    assert view.edit_box.isVisibleTo(view)
    view.edit_title.setText("AI news monitor (EU)")
    view.edit_every.setText("6h")
    view.edit_save.click()
    sent = stub.calls("PATCH")[-1]["body"]
    assert sent["expected_revision"] == 1
    assert sent["changes"] == {
        "title": "AI news monitor (EU)",
        "trigger": {"source_id": "schedule", "source_version": 1, "config": {"start_at": "2026-09-25T08:00:00.108652+00:00", "anchor": "2026-09-25T08:00:00.108652+00:00", "every": "6h"}},
    }
    view.control_buttons["revise"].click()
    view.edit_every.setText("6 hours")
    view.edit_save.click()
    assert "whole number" in view.error_label.text()
    assert len(stub.calls("PATCH")) == 1


@pytest.mark.basic
def test_discuss_switches_to_the_returned_session(palette, stub) -> None:
    window, controller = palette
    window._poll_automations()
    window._open_automation(TRIAGE)
    view = window.automation_view
    pair = next(p for p in view.pairs if p.index == 6)
    assert pair.discuss_button.isEnabled()
    assert not next(p for p in view.pairs if p.index == 7).discuss_button.isEnabled()
    pair.discuss_button.click()
    pair.discuss_edit.setText("Why was nothing urgent?")
    pair.discuss_send.click()
    sent = stub.calls("POST", f"{AUTOMATIONS_PATH}/{TRIAGE}/discuss")[-1]["body"]
    assert sent["occurrence_index"] == 6 and sent["prompt"] == "Why was nothing urgent?"
    discussion = next(r for r in stub.run_rows if r["session_kind"] == "discussion")
    assert controller.opened == [{"session_id": discussion["session_id"], "run_id": discussion["run_id"]}]
    assert not view.isVisibleTo(window), "the discussion replaces the automation view"


@pytest.mark.basic
def test_schedule_this_conversation_prefills_and_creates(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_schedule_sheet()
    sheet = window._schedule_sheet
    assert sheet.prompt_edit.toPlainText() == "Summarise today's AI news in five bullets."
    assert sheet.schedule_available is True
    assert sheet.preset_combo.currentText() == "every 8 hours"
    assert sheet.preview_label.text() == "every 8 hours (UTC), first run now"
    sheet.growing.setChecked(True)
    sheet.submit_button.click()
    body = stub.calls("POST", AUTOMATIONS_PATH)[-1]["body"]
    assert body == {
        "request_id": sheet.request_id,
        "title": "Summarise today's AI news in five bullets.",
        "target": {"bundle_ref": "abstractassistant.agent@0.0.3", "flow_id": "main", "input_data": {"prompt": "Summarise today's AI news in five bullets."}},
        "trigger": {"source_id": "schedule", "source_version": 1, "config": {"every": "8h"}},
        "context": {"mode": "growing"},
        "policy": {"tool_approval": "auto"},
    }
    created = stub.summaries[-1]["automation_id"]
    assert window._automation_view_id == created and window.automation_view.isVisibleTo(window)


# ---------------------------------------------------- the operator scenarios


def _schedule(window, *, prompt: str, preset: str, growing: bool = False) -> str:
    window._poll_automations()  # the clock button acts only once automations are confirmed
    window._open_schedule_sheet()
    sheet = window._schedule_sheet
    sheet.prompt_edit.setPlainText(prompt)
    sheet.preset_combo.setCurrentIndex(sheet.preset_combo.findText(preset))
    (sheet.growing if growing else sheet.independent).setChecked(True)
    sheet.submit_button.click()
    return window._automation_view_id


@pytest.mark.basic
def test_scenario_three_news_monitors(palette, stub) -> None:
    window, _controller = palette
    ids = [
        _schedule(window, prompt="Watch AI chip news", preset="every 8 hours"),
        _schedule(window, prompt="Watch EU AI regulation news", preset="every 24 hours"),
        _schedule(window, prompt="Watch open-weight model releases", preset="every hour"),
    ]
    assert len(set(ids)) == 3
    window._close_automation_view()
    window._poll_automations()
    from abstractassistant.ui.session_switcher import SessionSwitcher

    switcher = SessionSwitcher()
    window._session_switcher = switcher
    window._apply_automations_to_switcher(switcher)
    listed = {r.automation_id: r.cadence for r in switcher.automation_rows}
    assert {listed[i] for i in ids} == {"every 8 hours (UTC)", "every 24 hours (UTC)", "every hour (UTC)"}
    switcher.deleteLater()


@pytest.mark.basic
def test_scenario_email_triage_wait_answered_from_the_palette(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    assert ("Inbox triage is waiting for you", "The landlord asks whether Tuesday works for the boiler inspection. Reply now?") in window._notified
    window._open_automation(TRIAGE)
    waiting = next(p for p in window.automation_view.pairs if p.index == 7)
    choice = waiting.wait_inputs[0]["choices"][0]
    assert choice.text() == "Reply: Tuesday works"
    choice.click()
    sent = stub.calls("POST", "/api/gateway/commands")[-1]["body"]
    assert sent["type"] == "resume" and sent["run_id"] == "ade23773-2d37-5460-973c-08d35f7af010"
    assert sent["payload"] == {"wait_key": "user:ade23773-2d37-5460-973c-08d35f7af010:ask", "payload": {"response": "Reply: Tuesday works"}}
    # The same shape the real gateway accepted (commands.json).
    captured = next(c["request"]["body"] for c in _fixture("commands.json")["items"] if c["name"] == "answer ask_user wait")
    assert (captured["type"], captured["run_id"], captured["payload"]["wait_key"], set(captured["payload"]["payload"])) == (
        sent["type"], sent["run_id"], sent["payload"]["wait_key"], {"response"})
    # The occurrence completed; the view reloaded it.
    done = next(p for p in window.automation_view.pairs if p.index == 7)
    assert done.answer.property("tone") != "waiting" and 'Replied: {"response": "Reply: Tuesday works"}' in done.answer_text._content
    # Quiet ticks of the triage never notified: only the notify, the failure and the two waits did.
    assert len(window._notified) == 4


@pytest.mark.basic
def test_scenario_weekly_journal_growing(palette, stub) -> None:
    window, _controller = palette
    aid = _schedule(window, prompt="Summarise this week's journal entries", preset="every 7 days", growing=True)
    body = stub.calls("POST", AUTOMATIONS_PATH)[-1]["body"]
    assert body["trigger"]["config"] == {"every": "7d"} and body["context"] == {"mode": "growing"}
    summary = stub.summary(aid)
    assert trigger_summary(summary["trigger"]) == "every 7 days (UTC)"
    assert "Growing" in window.automation_view.meta_label.text()


@pytest.mark.basic
@pytest.mark.parametrize(
    "descriptor, shown",
    [
        (None, False),  # capabilities without `automations`
        ({"available": False}, False),
        ({"available": "yes"}, False),  # only a literal true counts
        ({"available": True, "version": 1, "endpoint": AUTOMATIONS_PATH}, True),
    ],
)
def test_the_section_follows_the_capabilities_descriptor(palette, stub, descriptor, shown) -> None:
    window, _controller = palette
    common = stub.capabilities["capabilities"]["contracts"]["common"]
    if descriptor is None:
        common.pop("automations")
    else:
        common["automations"] = descriptor
    before = len(stub.calls("GET", AUTOMATIONS_PATH))
    window._poll_automations()
    assert window._automations.available is shown
    # Not advertised: the automation routes are not even asked.
    assert (len(stub.calls("GET", AUTOMATIONS_PATH)) > before) is shown
    from abstractassistant.ui.session_switcher import SessionSwitcher
    from PyQt5.QtWidgets import QMenu

    switcher = SessionSwitcher()
    window._apply_automations_to_switcher(switcher)
    assert (len(switcher.automation_rows) == 4) is shown
    assert (switcher._automation_label is not None) is shown
    import abstractassistant.app as app_module

    menu = app_module._build_tray_menu(palette=window, quit_app=lambda: None)
    action = next(a for a in menu.actions() if a.text().startswith("Automations"))
    assert action.isVisible() is shown
    assert isinstance(menu, QMenu)
    switcher.deleteLater()


@pytest.mark.basic
def test_unreadable_capabilities_are_an_error_not_an_absent_api(palette, stub) -> None:
    window, _controller = palette
    real = stub.route
    stub.route = lambda m, p, q, b: (503, {"detail": "down"}) if p == "/api/gateway/discovery/capabilities" else real(m, p, q, b)  # type: ignore[assignment]
    window._poll_automations()
    assert window._automations.available is None and window._automations.error


@pytest.mark.basic
def test_a_poll_never_wipes_an_answer_being_typed(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_automation(TRIAGE)
    waiting = next(p for p in window.automation_view.pairs if p.index == 7)
    waiting.wait_inputs[0]["edit"].setText("Tuesday is fine, 10:00")
    stub.summary(TRIAGE)["next_fire_at"] = "2026-09-27T07:30:00Z"  # the summary moves on
    window._poll_automations()
    assert window.automation_view.summary["next_fire_at"] == "2026-09-27T07:30:00Z"
    still = next(p for p in window.automation_view.pairs if p.index == 7)
    assert still is waiting and still.wait_inputs[0]["edit"].text() == "Tuesday is fine, 10:00"


@pytest.mark.basic
def test_the_runs_filters_are_read_from_the_capabilities() -> None:
    from abstractassistant.gateway.capabilities import AssistantCapabilities

    advertised = AssistantCapabilities.from_discovery_response(
        {"capabilities": {"contracts": {"common": {"runs": {"list": {"filters": ["limit", "root_only", "session_kind"]}}}}}}
    )
    assert "session_kind" in advertised.runs_list_filters()
    assert AssistantCapabilities.from_discovery_response({"capabilities": {"contracts": {"common": {}}}}).runs_list_filters() == []


@pytest.mark.basic
def test_a_waiting_row_without_an_excerpt_shows_the_question() -> None:
    global _APP
    _APP = _qt()
    from abstractassistant.ui.automations import AutomationRow

    triage = _summary_fixture(TRIAGE)
    triage["last_occurrence"]["excerpt"] = ""  # what the gateway sends while an occurrence waits
    triage.pop("next_fire_at", None)
    row = AutomationRow(triage)
    assert row.excerpt_label.text().startswith("#7 waiting: waiting for you: The landlord asks")
    assert row.next_label.text() == "waiting"
    row.deleteLater()



@pytest.mark.basic
def test_wait_answers_are_chosen_by_the_waits_kind() -> None:
    from abstractassistant.gateway.client import wait_answer_payload

    assert wait_answer_payload("ask_user", "Tuesday works") == {"response": "Tuesday works"}
    assert wait_answer_payload("tool_approval", True) == {"approved": True}
    assert wait_answer_payload("tool_approval", False) == {"approved": False}
    assert wait_answer_payload("event", {"key": "value"}) == {"payload": {"key": "value"}}
    assert wait_answer_payload("event", 42) == {"payload": 42}
    for kind, answer in (("tool_approval", "yes"), ("event", object()), ("", "x"), ("user", "x")):
        with pytest.raises(ValueError):
            wait_answer_payload(kind, answer)


def _typed_wait_row(kind: str, **extra: Any) -> Dict[str, Any]:
    row = copy.deepcopy(_fixture("occurrences.json")["items"][0])  # occurrence 7, waiting
    row["waits"] = [dict({k: v for k, v in row["waits"][0].items() if k != "choices"}, kind=kind, **extra)] if kind else [
        {k: v for k, v in row["waits"][0].items() if k != "kind"}
    ]
    return row


@pytest.mark.basic
def test_a_tool_approval_wait_lists_its_calls_and_answers_approved(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_automation(TRIAGE)
    pair = next(p for p in window.automation_view.pairs if p.index == 7)
    texts = [w.text() for w in pair.answer.findChildren(type(window.automation_view.title_label))]
    assert any("send_email" in t and "clara@example.com" in t for t in texts), texts
    entry = next(e for e in pair.wait_inputs if e["kind"] == "tool_approval")
    assert entry["edit"] is None, "an approval is Approve / Deny, never free text"
    entry["approve"].click()
    sent = stub.calls("POST", "/api/gateway/commands")[-1]["body"]
    expected = next(c["request"]["body"] for c in _fixture("commands.json")["items"] if c["name"] == "answer tool_approval wait")
    assert (sent["type"], sent["run_id"], sent["payload"]) == (expected["type"], expected["run_id"], expected["payload"])


@pytest.mark.basic
def test_an_event_wait_answers_with_an_object_and_a_kindless_wait_cannot_be_answered(palette, stub) -> None:
    window, _controller = palette
    stub.occurrences[TRIAGE] = [_typed_wait_row("event")]
    window._poll_automations()
    window._open_automation(TRIAGE)
    entry = window.automation_view.pairs[0].wait_inputs[0]
    assert entry["choices"] == [], "no choice buttons for an event"
    before = len(stub.calls("POST", "/api/gateway/commands"))
    entry["edit"].setText("go ahead")  # not JSON: refused in place, nothing sent
    entry["send"].click()
    assert len(stub.calls("POST", "/api/gateway/commands")) == before
    assert "not valid JSON" in entry["error"].text()
    entry["edit"].setText('{"decision": "go"}')
    entry["send"].click()
    assert stub.calls("POST", "/api/gateway/commands")[-1]["body"]["payload"]["payload"] == {"payload": {"decision": "go"}}

    # The canonical fixtures predate D1 (no `kind`): nothing is guessed.
    stub.occurrences[TRIAGE] = [_typed_wait_row("")]
    before = len(stub.calls("POST", "/api/gateway/commands"))
    window._open_automation(TRIAGE)
    pair = window.automation_view.pairs[0]
    entry = pair.wait_inputs[0]
    assert entry["edit"] is None and entry["choices"] == [] and "approve" not in entry
    texts = [w.text() for w in pair.answer.findChildren(type(window.automation_view.title_label))]
    assert any("did not say what answer it expects" in t for t in texts)
    assert len(stub.calls("POST", "/api/gateway/commands")) == before


@pytest.mark.basic
def test_schedule_sheet_states_the_tool_consent_and_can_ask_each_time(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_schedule_sheet()
    sheet = window._schedule_sheet
    assert sheet.tools_auto.isChecked()
    assert sheet.tools_auto.text() == "Tools run without asking (you approve them now by creating this automation)"
    sheet.tools_ask.setChecked(True)
    sheet.submit_button.click()
    assert stub.calls("POST", AUTOMATIONS_PATH)[-1]["body"]["policy"] == {"tool_approval": "ask"}


@pytest.mark.basic
def test_the_clock_button_acts_only_once_automations_are_confirmed(palette, stub) -> None:
    window, _controller = palette
    # Before any poll: hidden, and opening the sheet calls no automation route.
    assert not window.schedule_button.isVisibleTo(window)
    window._open_schedule_sheet()
    assert window._schedule_sheet is None
    assert not stub.calls(path_prefix="/api/gateway/automations") and not stub.calls(path_prefix="/api/gateway/trigger-sources")
    # Not advertised: still hidden, still nothing called.
    stub.capabilities["capabilities"]["contracts"]["common"].pop("automations")
    window._poll_automations()
    assert not window.schedule_button.isVisibleTo(window)
    window._open_schedule_sheet()
    assert window._schedule_sheet is None
    assert not stub.calls(path_prefix="/api/gateway/automations") and not stub.calls(path_prefix="/api/gateway/trigger-sources")
    # Advertised: shown and working.
    stub.capabilities["capabilities"]["contracts"]["common"]["automations"] = {"available": True}
    window._poll_automations()
    assert window.schedule_button.isVisibleTo(window)
    window._open_schedule_sheet()
    assert window._schedule_sheet is not None


@pytest.mark.basic
def test_a_legacy_row_opens_read_only_without_calling_its_routes(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    before = len(stub.calls(path_prefix=f"{AUTOMATIONS_PATH}/{LEGACY}"))
    window._open_automation(LEGACY)
    view = window.automation_view
    assert "older scheduled run" in view.notice_label.text()
    assert not any(b.isEnabled() for b in view.control_buttons.values())
    assert len(stub.calls(path_prefix=f"{AUTOMATIONS_PATH}/{LEGACY}")) == before


@pytest.mark.basic
def test_a_duplicate_receipt_reads_as_already_received(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_automation(NEWS)
    duplicate = next(c["response"] for c in _fixture("commands.json")["items"] if c["request"]["body"] and c["response"].get("duplicate"))
    real = stub.route
    stub.route = lambda m, p, q, b: (200, dict(duplicate, command_id=b["command_id"])) if p.endswith("/commands") and m == "POST" else real(m, p, q, b)  # type: ignore[assignment]
    window.automation_view.control_buttons["pause"].click()
    assert window.automation_view.notice_label.text().endswith("(already received)")
    assert not window.automation_view.error_row.isVisibleTo(window.automation_view)



@pytest.mark.basic
def test_occurrence_turns_render_through_the_chat_message_widget(palette, stub, tmp_path) -> None:
    from abstractassistant.app import AutoSizingTextBrowser, MessageCard

    window, _controller = palette
    # Occurrence #2 of the canonical fixtures answers in real markdown:
    # a heading, a pipe table and a fenced JSON block.
    assert "|---|" in next(r for r in _fixture("occurrences.json")["items"] if r["index"] == 2)["answer"]
    window.resize(560, 760)
    window.show()
    window._poll_automations()
    window._open_automation(TRIAGE)
    _APP.processEvents()
    pair = next(p for p in window.automation_view.pairs if p.index == 2)
    assert type(pair.answer_text) is MessageCard and type(pair.trigger_text) is MessageCard
    browsers = pair.answer_text.findChildren(AutoSizingTextBrowser)
    shown = "\n".join(b.toPlainText() for b in browsers)
    html = "".join(b.toHtml() for b in browsers)
    assert "2 emails need a reply today" in shown and "Clara (accountant)" in shown and '"urgent": 2' in shown
    for raw in ("|---|", "## ", "```", "| From |"):
        assert raw not in shown, f"raw markdown {raw!r} shown as text"
    assert "<table" in html
    image = window.grab()
    assert not image.isNull()
    image.save(str(tmp_path / "automation_view.png"))
