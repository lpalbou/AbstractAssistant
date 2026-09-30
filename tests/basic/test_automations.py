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
        # `GET /api/gateway/me/email` (framework backlog 0992): None = the route is absent (404).
        self.my_email: Optional[Dict[str, Any]] = None
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
        if path == "/api/gateway/me/email" and method == "GET":
            if self.my_email is None:
                return 404, {"detail": "Not Found"}
            if self.my_email.get("_refuse"):
                return 403, {"detail": {"reason_code": "email_principal_refused", "message": "Entities have no mailbox."}}
            return 200, copy.deepcopy(self.my_email)
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
            return 200, {
                "session_id": sid,
                "run_id": rid,
                "session_kind": "discussion",
                "workspace_root": f"/data/discussions/{sid}",
                "mounted_workspace": f"/data/automations/{aid}/workspace",
            }
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
    # A run in progress = the gateway's current_occurrence, never last_occurrence.
    busy = automation_controls(triage)  # the fixture's current_occurrence: run #7
    assert busy["run_now"][0] is False and busy["stop_current"][0] is True
    assert busy["run_now"][1] == "An occurrence is in progress."
    inferred = automation_controls(dict(triage, current_occurrence=None))  # last_occurrence says "waiting"
    assert inferred["run_now"][0] is True and inferred["stop_current"][0] is False
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
    assert rows[0].state_chip is not None and rows[1].state_chip is None
    assert rows[0].meta_text.startswith("every 30 minutes (UTC) · last ")
    assert rows[2].state_button.state_control == "resume" and rows[2].meta_text.endswith("next —")
    # The fixture's current_occurrence (#7): the card says so and pulses.
    assert rows[0].result_label.toolTip() == "Run #7 running" and rows[0].state_button.pulsing is True
    assert rows[1].state_button.pulsing is False
    assert switcher.tab_buttons["automations"].text() == "Automations · 4 · 4 new"
    # Regular rows below; the discussion carries its badge.
    assert [r.session_id for r in switcher._rows] == ["disc-1", "sess_chat"]
    about = switcher._rows[0].about_button
    assert about is not None and about.full_text == "about automation Inbox triage"
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

        def switcher_tab(self) -> str:
            return getattr(self, "_tab", "sessions")

        def set_switcher_tab(self, tab: str) -> None:
            self._tab = tab

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
    # A run in progress (current_occurrence): run now off, stop current on, said in the header.
    assert "run #7 running" in view.meta_label.text()
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


# ------------------------------------------- Run now: shared icon and hint

KIT_CONTROLS = Path(__file__).resolve().parents[3] / "abstractuic" / "ui-kit" / "src" / "automations" / "automation_controls.json"
VENDORED_CONTROLS = Path(rules.__file__).resolve().parent.parent / "assets" / "automation_controls.json"


@pytest.mark.basic
def test_the_vendored_controls_file_is_the_kits_canonical_file() -> None:
    """Operator 2026-09-28: one shared "Run now" icon and tooltip in every client.
    The Assistant keeps a byte-identical copy of the kit's file (the root
    identity-sync check guards it across repos; this guards it in a checkout)."""
    if not KIT_CONTROLS.exists():
        pytest.skip(f"the kit checkout is not beside this repo ({KIT_CONTROLS}); the root identity-sync check covers it")
    assert VENDORED_CONTROLS.read_bytes() == KIT_CONTROLS.read_bytes()


@pytest.mark.basic
def test_run_now_hint_states_the_runtime_facts_and_adds_the_dynamic_lines() -> None:
    hint = rules.CONTROL_HINTS["run_now"]
    assert hint.startswith("Run it once now, without waiting for the schedule.")
    assert "the next scheduled run keeps its time, or starts right after this run if its time comes first" in hint
    assert "Does not count toward a run limit." in hint and "Works while paused; it stays paused." in hint
    assert "Not available while a run is in progress." in hint
    growing = {"next_fire_at": "2026-09-27T07:00:00.412307+00:00", "context_mode": "growing"}
    assert rules.control_hint("run_now", growing) == (
        f"{hint}\nNext scheduled run: 2026-09-27 07:00 UTC.\nGrowing context: later runs see this run in their history."
    )
    assert rules.control_hint("run_now", {"context_mode": "independent"}) == hint
    assert rules.control_hint("pause", growing) == rules.CONTROL_HINTS["pause"]


@pytest.mark.basic
def test_the_run_now_glyph_is_the_kits_play_circle() -> None:
    _qt()
    from abstractassistant import icons

    glyph = rules.RUN_NOW_GLYPH
    assert glyph["name"] == "playCircle" and glyph["view_box"] == "0 0 16 16"
    document = icons._kit_glyph_document("play-circle", "#123456")
    assert glyph["svg"].replace("currentColor", "#123456") in document
    assert 'viewBox="0 0 16 16"' in document and 'stroke-width="1.4"' in document
    image = icons.symbol_icon("play-circle", color="#123456", size=12).pixmap(24, 24).toImage()
    assert any(image.pixelColor(x, y).alpha() > 0 for x in range(24) for y in range(24)), "the glyph draws"


@pytest.mark.basic
def test_run_now_carries_the_shared_icon_and_hint_in_the_palette(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_automation(NEWS)
    view = window.automation_view
    button = view.control_buttons["run_now"]
    assert button.isEnabled()
    summary = stub.summary(NEWS)
    expected = rules.control_hint("run_now", summary)
    assert button.toolTip() == expected and button.accessibleDescription() == expected
    assert "Next scheduled run: 2026-09-27 08:00 UTC." in button.toolTip()
    from abstractassistant import icons
    from abstractassistant.theme import THEME

    assert not button.icon().isNull()
    assert button.icon().cacheKey() == icons.symbol_icon("play-circle", color=THEME.text_secondary, size=12).cacheKey()
    # Every other control carries its own hint.
    for control in ("pause", "stop_current", "revise", "archive"):
        assert rules.CONTROL_HINTS[control] in view.control_buttons[control].toolTip()
    # After the command is confirmed the button gets its icon back.
    button.click()
    view.end_pending()
    assert button.text() == "Run now" and not button.icon().isNull()


@pytest.mark.basic
def test_a_disabled_run_now_says_why_first_then_the_hint(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_automation(TRIAGE)
    button = window.automation_view.control_buttons["run_now"]
    assert not button.isEnabled()
    assert button.toolTip() == "An occurrence is in progress.\n" + rules.control_hint("run_now", stub.summary(TRIAGE))
    assert button.toolTip().endswith("Growing context: later runs see this run in their history.")


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
    banner = window.banner_label.text()
    assert banner == (
        "Discussion opened from occurrence 6: the automation's history up to that point is in context; "
        f"its files are mounted read-only at /data/automations/{TRIAGE}/workspace; "
        "this session has its own writable workspace."
    )


@pytest.mark.basic
def test_a_discuss_response_without_workspaces_is_said() -> None:
    text, tone = rules.discussion_banner({"session_id": "s", "run_id": "r"}, occurrence_index=3)
    assert tone == "warn" and "did not report its workspaces" in text


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
    listed = {r.automation_id: r.meta_text.split(" · ")[0] for r in switcher.automation_rows}
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
    assert switcher.tab_bar.isVisibleTo(switcher) is shown
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


@pytest.mark.basic
@pytest.mark.parametrize(
    "markdown, raw, tag",
    [
        ("[Trigger schedule@1 · occurrence 1]\n## Heading here\nbody", "## ", "<h2"),
        ("Intro line\n- item one\n- item two", "- item", "<li"),
        ("Intro line\n1. first\n2. second", "1. first", "<li"),
        ('Intro line\n```json\n{"a": 1}\n```', "```", "monospace"),
        ("Intro line\n| A | B |\n|---|---|\n| 1 | 2 |", "|---|", "<table"),
    ],
)
def test_the_chat_answer_renderer_handles_blocks_right_after_a_text_line(markdown, raw, tag) -> None:
    """CommonMark: headings and fences interrupt a paragraph; a list and a table
    right after a line render too — no blank line needed (answers and
    automation turns rendered as answers)."""
    global _APP
    _APP = _qt()
    import abstractassistant.app as app_module
    from abstractassistant.utils.markdown_renderer import MarkdownRenderer

    card = app_module.MessageCard(
        message={"role": "assistant", "content": markdown, "ts": "2026-09-27T00:00:00Z"},
        message_key="md",
        renderer=MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *a: None,
        bubble_width=500,
    )
    browsers = card.findChildren(app_module.AutoSizingTextBrowser)
    text = "\n".join(b.toPlainText() for b in browsers)
    html = "".join(b.toHtml() for b in browsers)
    assert raw not in text, f"{raw!r} shown literally"
    assert tag in html
    card.deleteLater()



@pytest.mark.basic
def test_the_task_turn_renders_markdown_while_a_chat_prompt_stays_literal(palette, stub) -> None:
    """The fixture's task turn is "[Trigger …]\n## Inbox triage\n…" (composed by
    the automation): the user bubble renders it as markdown; the chat's user
    bubble with the same text stays literal (a person's typed prompt)."""
    import abstractassistant.app as app_module

    window, _controller = palette
    row = next(r for r in _fixture("occurrences.json")["items"] if r["index"] == 1)
    assert row["user_turn"].startswith("[Trigger ") and "\n## Inbox triage\n" in row["user_turn"]
    window._poll_automations()
    window._open_automation(TRIAGE)
    pair = next(p for p in window.automation_view.pairs if p.index == 1)
    task = pair.trigger_text
    assert type(task) is app_module.MessageCard
    body = task.findChildren(app_module.AutoSizingTextBrowser)
    assert any("<h2" in b.toHtml() for b in body)
    assert not any("## Inbox triage" in b.toPlainText() for b in body)

    chat = app_module.MessageCard(
        message={"role": "user", "content": row["user_turn"], "ts": row["fired_at"]},
        message_key="chat",
        renderer=window._renderer,
        on_open_artifact=lambda *a: None,
        bubble_width=400,
    )
    assert any("## Inbox triage" in b.toPlainText() for b in chat.findChildren(app_module.AutoSizingTextBrowser))
    chat.deleteLater()



@pytest.mark.basic
def test_discuss_wording_matches_the_web_and_the_captured_response_carries_both_workspaces(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_automation(TRIAGE)
    pair = next(p for p in window.automation_view.pairs if p.index == 6)
    assert pair.discuss_button.text() == "Discuss — fork at this occurrence (own workspace, automation files read-only)"
    assert pair.discuss_button.toolTip() == (
        "Starts a new session that forks this automation at #6 with its full history (runs 1–6). It works in its "
        "own writable workspace; the automation's files are mounted read-only for the file tools (shell commands are "
        "not sandboxed), and nothing is written back into the automation's session."
    )
    captured = next(c for c in _fixture("commands.json")["items"] if c["name"] == "discuss")
    text, tone = rules.discussion_banner(captured["response"], occurrence_index=captured["request"]["body"]["occurrence_index"])
    assert tone == "info" and captured["response"]["mounted_workspace"] in text


# ------------------------------------------- layout: the chat's geometry


def _settle() -> None:
    from PyQt5.QtCore import QCoreApplication, QEvent

    for _ in range(4):
        _APP.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _tall_palette(window, height: int = 900) -> None:
    """A tall palette on a screen big enough to honour it (the offscreen
    screen is 800x600, and the palette clamps to its screen)."""
    from PyQt5.QtCore import QRect

    window._available_screen_geometry = lambda: QRect(0, 0, 1600, 1200)
    import dataclasses

    window._controller.preferences = dataclasses.replace(window._controller.preferences, window_width=620, window_height=height)
    window.resize(620, height)
    window.show()
    window._reflow_shell()
    _settle()


def _list_extent(view) -> tuple:
    """(content widget height, bottom of the last row + the layout's margins)."""
    layout = view.list_layout
    rows = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget() is not None]
    margins = layout.contentsMargins()
    bottom = max(r.geometry().bottom() + 1 for r in rows) + margins.bottom()
    stacked = sum(r.height() for r in rows) + layout.spacing() * (len(rows) - 1) + margins.top() + margins.bottom()
    return view.list_host.height(), bottom, stacked


@pytest.mark.basic
def test_the_occurrence_list_ends_at_its_last_row(palette, stub) -> None:
    """Defect 2026-09-27: under the last occurrence the list kept a band of
    empty space as tall as half the view (1400 px on an 86-run automation):
    the content widget was sized to the SUM of its rows' minimum heights —
    each word-wrapped caption/Discuss label counted at its narrowest width —
    instead of their height at the real width."""
    window, _controller = palette
    rows = copy.deepcopy(_fixture("occurrences.json")["items"])
    stub.occurrences[TRIAGE] = [r for r in rows if r["index"] in {5, 6, 7}]
    _tall_palette(window)
    window._poll_automations()
    window._open_automation(TRIAGE)
    _settle()
    view = window.automation_view
    assert [p.index for p in view.pairs] == [5, 6, 7]
    viewport = view.scroll.viewport().height()
    assert viewport > 500, "the view must be tall for the measurement to mean anything"

    def check(label: str) -> None:
        # The cause, measured: no row may claim a minimum height above the
        # height it is laid out at (the scroll area never sizes its content
        # below the sum of those minimums).
        for pair in view.pairs:
            assert pair.minimumSizeHint().height() <= pair.height(), f"{label}: #{pair.index} claims more than it shows"
            button = pair.discuss_button
            assert button.minimumSizeHint().height() <= button.height() or not button.isVisible()
        assert view.list_host.minimumSizeHint().height() <= _list_extent(view)[2]
        host, bottom, stacked = _list_extent(view)
        assert bottom == stacked, f"{label}: rows overlap or leave holes"
        if stacked > viewport:
            assert host - bottom <= view.list_layout.spacing(), f"{label}: {host - bottom} px of empty space after the last row"
        else:
            assert host == viewport, f"{label}: a short list fills the viewport, no more"
        bar = view.scroll.verticalScrollBar()
        assert bar.maximum() == max(0, host - viewport)

    check("3 occurrences")
    assert _list_extent(view)[2] > viewport, "3 fixture occurrences overflow a 900-px palette"
    # A refresh that removes rows, then one that adds them back.
    view.set_occurrences([r for r in rows if r["index"] in {6, 7}], next_cursor=None)
    _settle()
    check("2 occurrences")
    view.set_occurrences(rows, next_cursor=None)
    _settle()
    check("7 occurrences")


@pytest.mark.basic
def test_an_occurrence_is_a_chat_exchange_with_the_chats_edges(palette, stub) -> None:
    """Ruling 2026-09-27: automation turns use the chat's rendering container.
    The task is the chat's user bubble (right), the answer the chat's
    assistant card (left), Discuss a compact action under the card, and no
    frame around the pair; the edges are the chat's at the same width."""
    import abstractassistant.app as app_module
    from PyQt5.QtCore import QPoint
    from PyQt5.QtWidgets import QFrame, QWidget

    window, controller = palette
    _tall_palette(window)
    window._poll_automations()
    window._open_automation(TRIAGE)
    _settle()
    view = window.automation_view
    assert view.scroll.verticalScrollBar().isVisible(), "the list scrolls (the chat is compared scrolled too)"
    names = {w.objectName() for w in view.findChildren(QWidget)}
    assert not names & {"autoTrigger", "autoAnswer"}, "no frame around the pair"

    def left(w) -> int:
        return w.mapTo(window, QPoint(0, 0)).x()

    def right(w) -> int:
        return left(w) + w.width()

    edges = set()
    for pair in view.pairs:
        assert type(pair) is not QFrame and not isinstance(pair, QFrame)
        task = pair.trigger_text
        assert type(task) is app_module.MessageCard and task._bubble.objectName() == "userBubble"
        # The caption sits above the task bubble, right-aligned with it.
        assert pair.task_meta.geometry().bottom() < task.geometry().top()
        edges.add(("task-right", right(task._bubble)))
        card = pair.answer_text if pair.answer_text is not None else pair.note
        assert card is not None
        if pair.answer_text is not None:
            assert type(card) is app_module.MessageCard and card._bubble.objectName() == "assistantBubble"
            box = card._bubble
        else:
            box = card  # a failure / wait / nothing-yet note, the same column
        edges.add(("answer-left", left(box)))
        # Discuss: under the card, right-aligned with it, label unchanged.
        row = pair.discuss_row
        assert row.mapTo(window, QPoint(0, 0)).y() >= box.mapTo(window, QPoint(0, box.height())).y()
        assert right(pair.discuss_button) == right(box)
        assert pair.discuss_button.text() == "Discuss — fork at this occurrence (own workspace, automation files read-only)"
        assert pair.discuss_button.height() < 40, "one compact line at this width"
        assert not pair.discuss_box.isVisible()
    # The information stays: failed reason + red tone, waiting highlighted.
    failed = next(p for p in view.pairs if p.index == 5)
    assert failed.note.property("tone") == "failed" and "IMAP read timed out" in failed.note.findChildren(type(view.title_label))[0].text()
    assert failed.status_meta.property("tone") == "failed" and failed.badge.text().startswith("Failed after 3")
    waiting = next(p for p in view.pairs if p.index == 7)
    assert waiting.note.property("tone") == "waiting" and waiting.wait_inputs
    notified = next(p for p in view.pairs if p.index == 2)
    assert notified.badge.text() == "Notified" and notified.answer.property("tone") == "notified"
    # The widths are the chat's rule for the list's viewport width.
    vw = view.scroll.viewport().width()
    for pair in view.pairs:
        assert pair.trigger_text._bubble.width() == app_module._message_bubble_width(vw, role="user")
        assert pair.answer.width() == app_module._message_bubble_width(vw, role="assistant")
        if pair.answer_text is not None:
            assert pair.answer_text._bubble.width() == pair.answer.width()
    task_right = {x for k, x in edges if k == "task-right"}
    answer_left = {x for k, x in edges if k == "answer-left"}
    assert len(task_right) == 1 and len(answer_left) == 1, edges

    # The chat, scrolled too, at the same palette width.
    window._close_automation_view()
    controller._messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}\n\n" + "line\n\n" * 6, "ts": "2026-09-27T09:00:00Z"}
        for i in range(12)
    ]
    window.refresh_history()
    _settle()
    assert window.history_scroll.verticalScrollBar().isVisible()
    cards = [c for c in window.history_host.findChildren(app_module.MessageCard)]
    user = next(c for c in cards if c._bubble.objectName() == "userBubble")
    answer = next(c for c in cards if c._bubble.objectName() == "assistantBubble")
    assert right(user._bubble) == task_right.pop(), "task bubble right edge = chat user bubble right edge"
    assert left(answer._bubble) == answer_left.pop(), "answer card left edge = chat card left edge"


@pytest.mark.basic
def test_discuss_opens_its_prompt_under_the_card(palette, stub) -> None:
    window, _controller = palette
    _tall_palette(window)
    window._poll_automations()
    window._open_automation(TRIAGE)
    _settle()
    pair = next(p for p in window.automation_view.pairs if p.index == 6)
    assert not pair.discuss_box.isVisible()
    pair.discuss_button.click()
    _settle()
    assert pair.discuss_box.isVisible()
    assert pair.discuss_box.geometry().top() >= pair.discuss_row.geometry().bottom()
    assert pair.discuss_edit.placeholderText() == "What do you want to discuss about this result?"



@pytest.mark.basic
def test_switcher_inline_controls_edit_and_tab_go_through_the_palette(palette, stub) -> None:
    window, controller = palette
    window._poll_automations()
    window._on_switcher_automation_control(NEWS, "pause")
    sent = stub.calls("POST", f"{AUTOMATIONS_PATH}/{NEWS}/commands")[-1]["body"]
    assert sent["type"] == "automation.pause"
    assert window._automations.summary(NEWS)["status"] == "paused"
    # The card's one button, clicked in the real switcher: resume goes to the gateway.
    from abstractassistant.ui.session_switcher import SessionSwitcher

    switcher = SessionSwitcher()
    switcher.automation_control_requested.connect(window._on_switcher_automation_control)
    window._apply_automations_to_switcher(switcher)
    switcher.set_tab("automations")
    card = next(r for r in switcher.automation_tab_rows if r.automation_id == NEWS)
    assert card.state_button.state_control == "resume"
    card.state_button.click()
    assert stub.calls("POST", f"{AUTOMATIONS_PATH}/{NEWS}/commands")[-1]["body"]["type"] == "automation.resume"
    assert window._automations.summary(NEWS)["status"] == "active"
    switcher.deleteLater()
    window._on_switcher_tab_changed("automations")
    assert controller.switcher_tab() == "automations"



@pytest.mark.basic
def test_new_automation_from_the_switcher_creates_and_selects_the_row(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_new_automation_sheet()
    sheet = window._schedule_sheet
    assert sheet.standalone is True and sheet.prompt_edit.toPlainText() == ""
    assert sheet.preset_combo.currentText() == "every 8 hours"
    sheet.prompt_edit.setPlainText("Check the price of TTE.PA")
    before = {s["automation_id"] for s in stub.summaries}
    sheet.submit_button.click()
    body = stub.calls("POST", AUTOMATIONS_PATH)[-1]["body"]
    assert body["target"]["input_data"] == {"prompt": "Check the price of TTE.PA"}
    created = next(s["automation_id"] for s in stub.summaries if s["automation_id"] not in before)
    switcher = window._session_switcher
    assert switcher.tab == "automations"
    assert created in [r.automation_id for r in switcher.automation_tab_rows]
    assert switcher.selected_automation_id == created


def _held_commands(window) -> List[tuple]:
    """Hold command callbacks (the gateway 'thinking'); the test releases them."""
    held: List[tuple] = []
    window._automations.command = lambda aid, control, done: held.append((aid, control, done))
    return held


def _card(switcher, aid):
    return next(r for r in switcher.automation_tab_rows if r.automation_id == aid)


@pytest.mark.basic
def test_the_card_button_is_pending_until_the_gateway_confirms(palette, stub) -> None:
    from abstractassistant.ui.session_switcher import SessionSwitcher

    window, _controller = palette
    window._poll_automations()
    switcher = SessionSwitcher()
    window._session_switcher = switcher
    switcher.automation_control_requested.connect(window._on_switcher_automation_control)
    window._apply_automations_to_switcher(switcher)
    switcher.set_tab("automations")
    switcher.show()  # the palette refreshes an open switcher on every poll
    real_command = window._automations.command
    held = _held_commands(window)

    card = _card(switcher, NEWS)
    card.state_button.click()
    # Immediately: disabled, spinner, "Pausing…", exactly one command.
    assert not card.state_button.isEnabled() and card.state_button.toolTip() == "Pausing…"
    assert [(a, c) for a, c, _ in held] == [(NEWS, "pause")]
    card.state_button.click()
    card._clicked("pause")
    assert len(held) == 1, "never the same command twice while pending"
    # A poll that brings a CHANGED summary (not yet the new state) keeps it pending.
    stub.summary(NEWS)["updated_at"] = "2026-09-27T09:00:00+00:00"
    window._poll_automations()
    card = _card(switcher, NEWS)
    assert switcher.is_pending(NEWS) and not card.state_button.isEnabled()
    # The gateway applies it; the result arrives; the refresh shows "paused".
    window._automations.command = real_command
    real_command(NEWS, "pause", held[0][2])
    card = _card(switcher, NEWS)
    assert not switcher.is_pending(NEWS)
    assert card.state_button.isEnabled() and card.state_button.state_control == "resume"
    switcher.deleteLater()


@pytest.mark.basic
def test_a_refused_command_brings_the_button_back_with_the_reason(palette, stub) -> None:
    from abstractassistant.ui.session_switcher import SessionSwitcher

    window, _controller = palette
    window._poll_automations()
    switcher = SessionSwitcher()
    window._session_switcher = switcher
    switcher.automation_control_requested.connect(window._on_switcher_automation_control)
    window._apply_automations_to_switcher(switcher)
    switcher.set_tab("automations")
    held = _held_commands(window)
    _card(switcher, NEWS).state_button.click()
    busy = AutomationApiError(status=409, reason_code="automation_busy", message="An occurrence is already running.")
    held[0][2](False, busy)
    card = _card(switcher, NEWS)
    assert card.state_button.isEnabled() and card.pending is None
    assert "Last attempt failed" in card.state_button.toolTip() and "already running" in card.state_button.toolTip()
    assert "already running" in switcher.status_text
    # A second click is a new action: a fresh command.
    card.state_button.click()
    assert len(held) == 2
    switcher.deleteLater()


@pytest.mark.basic
def test_the_views_controls_are_pending_until_the_state_changes(palette, stub, tmp_path) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_automation(NEWS)
    view = window.automation_view
    held = _held_commands(window)
    view.control_buttons["pause"].click()
    assert view.pending == "pause" and view.control_buttons["pause"].text() == "Pausing…"
    assert not any(b.isEnabled() for b in view.control_buttons.values())
    assert len(held) == 1
    window.resize(560, 760)
    window.show()
    _APP.processEvents()
    window.grab().save(str(tmp_path / "view-pending.png"))
    # The result arrives but the state has not changed yet: still pending.
    held[0][2](True, {"command_id": "c", "accepted": True, "duplicate": False, "seq": 1})
    assert view.pending == "pause"
    # The next summary shows "paused": confirmed.
    stub.summary(NEWS)["status"] = "paused"
    window._poll_automations()
    assert view.pending is None and view.control_buttons["resume"].isEnabled()
    assert view.control_buttons["pause"].text() == "Pause"
    # A refusal: back at once, the reason shown.
    view.control_buttons["resume"].click()
    held[1][2](False, AutomationApiError(status=409, reason_code="invalid_state", message="Automation is archived."))
    assert view.pending is None and view.control_buttons["resume"].isEnabled()
    assert "archived" in view.error_label.text().lower()


@pytest.mark.basic
def test_the_view_never_infers_a_run_in_progress_from_the_last_occurrence(palette, stub) -> None:
    """One source for "a run is in progress" in the whole app: current_occurrence."""
    window, _controller = palette
    news = stub.summary(NEWS)
    news["last_occurrence"] = dict(news["last_occurrence"], status="running")
    news.pop("current_occurrence", None)
    window._poll_automations()
    window._open_automation(NEWS)
    view = window.automation_view
    assert view.control_buttons["run_now"].isEnabled() and not view.control_buttons["stop_current"].isEnabled()
    assert "running" not in view.meta_label.text()
    news["current_occurrence"] = {"index": 7, "run_id": "r7", "attempt": 1, "status": "admitted"}
    window._poll_automations()
    assert not view.control_buttons["run_now"].isEnabled() and view.control_buttons["stop_current"].isEnabled()
    assert "run #7 running" in view.meta_label.text()
    # The pending confirmations read it too: Stop is confirmed once it is gone.
    from abstractassistant.core.automations import command_confirmed

    assert command_confirmed("stop_current", news, dict(news, current_occurrence=None)) is True
    assert command_confirmed("stop_current", news, dict(news, last_occurrence=dict(news["last_occurrence"], status="running"))) is False


# ------------------------------------------- email automations (0992 WP6)

EMAIL_USABLE = {"configured": True, "enabled": True, "admin_enabled": True, "effective_enabled": True}
EMAIL_TEXT = json.loads(VENDORED_CONTROLS.read_text(encoding="utf-8"))["email"]
# The runtime's descriptor as `GET /trigger-sources` lists it (abstractruntime feat/email-accounts).
EMAIL_SOURCE = {"id": "email.received", "version": 1, "label": "When an email arrives", "config_schema": {"type": "object"},
                "event_schema": {"type": "object"}, "capabilities": {"kind": "event", "inbox": "email", "content_trust": "untrusted"}, "available": True}


@pytest.mark.basic
def test_the_email_trigger_needs_the_gateway_to_list_it(palette, stub) -> None:
    stub.my_email = dict(EMAIL_USABLE)
    window, _controller = palette
    window._poll_automations()
    window._open_schedule_sheet()
    sheet = window._schedule_sheet
    item = sheet.preset_combo.model().item(sheet.preset_combo.findData("email"))
    assert sheet.notify_email.isEnabled() and not item.isEnabled()
    assert "email.received@1" in item.toolTip()


@pytest.mark.basic
def test_email_wording_is_the_vendored_kit_section() -> None:
    assert rules.EMAIL_TEXT == EMAIL_TEXT
    assert EMAIL_TEXT["not_set_up"] == "Email isn't set up — open My email"
    assert EMAIL_TEXT["trigger_label"] == "When an email arrives" and EMAIL_TEXT["notify_label"] == "Email me the result"


@pytest.mark.basic
def test_email_rules_mirror_the_kit() -> None:
    assert rules.parse_entry_list(" A@x.test, b@x.test;\nA@X.test  c@y.test ") == ["a@x.test", "b@x.test", "c@y.test"]
    assert rules.is_plain_address("a@x.test") and not rules.is_plain_address("A <a@x.test>") and not rules.is_plain_address("a@b@c")
    assert rules.is_plain_domain("x.test") and not rules.is_plain_domain("*.x.test") and not rules.is_plain_domain("x")
    assert rules.email_usable(EMAIL_USABLE) and not rules.email_usable({"configured": True, "effective_enabled": False}) and not rules.email_usable(None)
    default = rules.EmailTriggerForm()
    assert rules.email_trigger_config(default) == ({"uses_model": True, "every": "1h", "max_batch": 100}, [])
    assert rules.email_trigger_config(rules.EmailTriggerForm(uses_model=False))[0]["every"] == "60s"
    config, errors = rules.email_trigger_config(rules.EmailTriggerForm(
        from_in="Boss@Example.test, a@x.test", from_domain_in="Example.org", to_in="me@example.test",
        subject_contains="  invoice ", has_attachment="yes", every_amount=10, every_unit="m", max_batch=20,
    ))
    assert errors == [] and config == {"uses_model": True, "every": "10m", "max_batch": 20, "filter": {
        "from_in": ["boss@example.test", "a@x.test"], "from_domain_in": ["example.org"], "to_in": ["me@example.test"],
        "subject_contains": "invoice", "has_attachment": True}}
    bad = rules.email_trigger_config(rules.EmailTriggerForm(from_in="nope, ok@x.test", from_domain_in="*.x.test"))[1]
    assert len(bad) == 2 and "nope" in bad[0] and "ok@x.test" not in bad[0] and "*.x.test" in bad[1]
    assert rules.email_trigger_config(rules.EmailTriggerForm(every_amount=0, every_unit="m"))[1]
    assert rules.email_trigger_config(rules.EmailTriggerForm(max_batch=1001))[1]
    assert trigger_summary({"source_id": "email.received", "source_version": 1, "config": config}) == (
        "when an email arrives · from boss@example.test, a@x.test, example.org · to me@example.test · "
        "subject contains “invoice” · with attachments · checked every 10 minutes · up to 20 per run"
    )
    assert rules.email_allowed_recipients("self", "x@y.test") == (["self"], [])
    assert rules.email_allowed_recipients("list", "Boss@example.test, self") == (["self", "boss@example.test"], [])
    assert rules.email_allowed_recipients("list", " ")[1] and "nope" in rules.email_allowed_recipients("list", "nope")[1][0]
    assert rules.notify_for(True) == {"channels": ["console", "email"]} and rules.notify_for(False) == {"channels": ["console"]}


@pytest.mark.basic
def test_email_create_body_and_defaults() -> None:
    body, errors = build_create_request(
        prompt="Summarise new invoices", when=ScheduleWhen("every", 8, "h"), context="independent",
        target={"flow_id": "@default", "interface": "i"}, request_id="rq",
        trigger="email", email=rules.EmailTriggerForm(from_domain_in="example.org"),
        notify_email=True, email_recipients=("list", "boss@example.test"),
    )
    assert errors == [] and body == {
        "request_id": "rq", "title": "Summarise new invoices",
        "target": {"flow_id": "@default", "interface": "i", "input_data": {"prompt": "Summarise new invoices"}},
        "trigger": {"source_id": "email.received", "source_version": 1, "config": {"uses_model": True, "every": "1h", "max_batch": 100, "filter": {"from_domain_in": ["example.org"]}}},
        "context": {"mode": "independent"},
        "policy": {"tool_approval": "auto", "email_allowed_recipients": ["self", "boss@example.test"]},
        "notify": {"channels": ["console", "email"]},
    }
    plain, errors = build_create_request(
        prompt="x", when=ScheduleWhen("every", 5, "m"), context="independent", target={"flow_id": "@default", "interface": "i"},
        request_id="r", notify_email=False, email_recipients=("self", ""),
    )
    assert errors == [] and "notify" not in plain and plain["policy"] == {"tool_approval": "auto"}
    bad, errors = build_create_request(
        prompt="x", when=ScheduleWhen("once", at=""), context="independent", target={"flow_id": "@default", "interface": "i"},
        request_id="r", trigger="email", email=rules.EmailTriggerForm(to_in="bad"),
    )
    assert bad is None and len(errors) == 1 and "bad" in errors[0]


@pytest.mark.basic
def test_email_revise_drops_start_at_and_merges_policy() -> None:
    summary = dict(_summary_fixture(NEWS), trigger={"binding_id": "b", "source_id": "email.received", "source_version": 1,
        "config": {"account": "self", "folder": "INBOX", "uses_model": True, "every": "1h", "max_batch": 100, "start_at": "2026-09-30T00:00:00Z", "filter": {"from_in": ["a@x.test"]}}})
    same, errors = rules.revise_changes(summary, title=summary["title"], every="1h", context=summary["context_mode"])
    assert same is None and errors == []
    changes, errors = rules.revise_changes(summary, title=summary["title"], every="2h", context=summary["context_mode"],
                                           definition={"policy": {"email_allowed_recipients": ["self"]}, "notify": {"channels": ["console"]}},
                                           notify_email=True, email_recipients=("list", "boss@example.test"))
    assert errors == [] and changes == {
        "trigger": {"source_id": "email.received", "source_version": 1, "config": {"account": "self", "folder": "INBOX", "uses_model": True, "every": "2h", "max_batch": 100, "filter": {"from_in": ["a@x.test"]}}},
        "notify": {"channels": ["console", "email"]},
        "policy": {"email_allowed_recipients": ["self", "boss@example.test"]},
    }
    assert rules.revise_changes(summary, title=summary["title"], every="30s", context=summary["context_mode"])[1]


@pytest.mark.basic
def test_client_reads_my_email_and_types_a_refusal(stub) -> None:
    stub.my_email = dict(EMAIL_USABLE)
    assert _client(stub).my_email()["effective_enabled"] is True
    assert stub.calls("GET", "/api/gateway/me/email")[-1]["path"] == "/api/gateway/me/email"
    stub.my_email = {"_refuse": True}
    with pytest.raises(AutomationApiError) as exc:
        _client(stub).my_email()
    assert exc.value.status == 403 and exc.value.reason_code == "email_principal_refused"
    assert _client(stub).console_url() == f"{stub.url}/console#users"


@pytest.mark.basic
def test_schedule_sheet_without_email_shows_the_notice_and_sends_nothing_email(palette, stub) -> None:
    window, _controller = palette
    window._poll_automations()
    window._open_schedule_sheet()
    sheet = window._schedule_sheet
    assert sheet.email_notice.isVisibleTo(sheet) and EMAIL_TEXT["open_my_email"] in sheet.email_notice.text()
    assert "Email isn" in sheet.email_notice.text()
    assert not sheet.notify_email.isEnabled() and not sheet.recipients_list.isEnabled()
    assert sheet.preset_combo.findText(EMAIL_TEXT["trigger_label"]) >= 0
    email_index = sheet.preset_combo.findText(EMAIL_TEXT["trigger_label"])
    assert not sheet.preset_combo.model().item(email_index).isEnabled()
    sheet.submit_button.click()
    body = stub.calls("POST", AUTOMATIONS_PATH)[-1]["body"]
    assert body["trigger"]["source_id"] == "schedule" and "notify" not in body and body["policy"] == {"tool_approval": "auto"}


@pytest.mark.basic
def test_schedule_sheet_creates_an_email_automation(palette, stub) -> None:
    stub.my_email = dict(EMAIL_USABLE)
    stub.trigger_sources = {"items": stub.trigger_sources["items"] + [EMAIL_SOURCE]}
    window, _controller = palette
    window._poll_automations()
    window._open_schedule_sheet()
    sheet = window._schedule_sheet
    assert not sheet.email_notice.isVisibleTo(sheet)
    sheet.preset_combo.setCurrentIndex(sheet.preset_combo.findText(EMAIL_TEXT["trigger_label"]))
    assert sheet.email_box.isVisibleTo(sheet) and not sheet.custom_host.isVisibleTo(sheet)
    assert sheet.email_every_amount.value() == 1 and sheet.email_every_unit.currentData() == "h"
    assert sheet.email_rule.text() == EMAIL_TEXT["interval_rule"]
    assert sheet.preview_label.text() == "when an email arrives · checked every hour · up to 100 per run"
    sheet.email_from_in.setText("boss@example.test")
    sheet.email_has_attachment.setCurrentIndex(sheet.email_has_attachment.findData("yes"))
    sheet.notify_email.setChecked(True)
    sheet.recipients_list.setChecked(True)
    sheet.recipients_edit.setText("colleague@example.test")
    sheet.submit_button.click()
    body = stub.calls("POST", AUTOMATIONS_PATH)[-1]["body"]
    assert body["trigger"] == {"source_id": "email.received", "source_version": 1, "config": {"uses_model": True, "every": "1h", "max_batch": 100, "filter": {"from_in": ["boss@example.test"], "has_attachment": True}}}
    assert body["notify"] == {"channels": ["console", "email"]}
    assert body["policy"] == {"tool_approval": "auto", "email_allowed_recipients": ["self", "colleague@example.test"]}


@pytest.mark.basic
def test_open_my_email_opens_the_gateway_console(palette, stub, monkeypatch) -> None:
    window, _controller = palette
    import abstractassistant.app as app_module

    opened: List[str] = []
    monkeypatch.setattr(app_module, "activate_message_link", lambda href, **_kw: opened.append(href) or "")
    window._poll_automations()
    window._open_schedule_sheet()
    window._schedule_sheet.open_my_email_requested.emit()
    assert opened == [f"{stub.url}/console#users"]


@pytest.mark.basic
def test_the_view_edits_an_email_triggers_interval(palette, stub) -> None:
    window, _controller = palette
    email_summary = dict(_summary_fixture(NEWS), trigger={"binding_id": "b", "source_id": "email.received", "source_version": 1,
        "config": {"uses_model": True, "every": "1h", "max_batch": 100, "start_at": "2026-09-30T00:00:00Z"}})
    stub.summaries = [email_summary]
    window._poll_automations()
    window._open_automation(NEWS)
    view = window.automation_view
    assert "when an email arrives" in view.meta_label.text()
    assert view.edit_every.isEnabled() and view.edit_every.text() == "1h"
    view.edit_box.show()
    view.edit_every.setText("3h")
    view._save_edit()
    changes = stub.calls("PATCH")[-1]["body"]["changes"]
    assert changes == {"trigger": {"source_id": "email.received", "source_version": 1, "config": {"uses_model": True, "every": "3h", "max_batch": 100}}}
