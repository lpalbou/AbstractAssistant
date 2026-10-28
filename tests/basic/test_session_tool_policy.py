"""Chat-wide tool approval through the gateway's session tool policy (contract v1).

With ``capabilities.session_tool_policy.supported`` the "allow all" grant is a
server-side policy written BEFORE the shown wait is answered, so later covered
calls never produce a wait (no approval flash). Without it, the old in-memory
grant is the explicit, logged fallback. The runtime's
``abstract.tool_policy_decision`` record is an activity line, never a wait.
"""

from __future__ import annotations

import logging
import os
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abstractassistant.app import AssistantPalette
from abstractassistant.controller import AssistantController
from abstractassistant.gateway import client as client_mod
from abstractassistant.gateway.adapter import GatewayEventAdapter
from abstractassistant.gateway.capabilities import AssistantCapabilities
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig
from abstractassistant.ui.activity import RunActivityModel

_POLICY_BLOCK = {
    "supported": True,
    "version": 1,
    "endpoint": "/api/gateway/sessions/{session_id}/tool-policy",
    "methods": ["GET", "PUT", "POST", "DELETE"],
    "approve": ["tools", "kinds", "all", "max_risk_rank"],
    "deny": ["tools", "kinds"],
    "ask": True,
    "record": "abstract.tool_policy_decision",
}

_ITEMS = [
    {"name": "read_file", "selected_mode": "ask", "risk_tier": "observe", "risk_rank": 1},
    {"name": "write_file", "selected_mode": "ask", "risk_tier": "act", "risk_rank": 2},
    {"name": "send_email", "selected_mode": "ask", "risk_tier": "outreach", "risk_rank": 3},
]


class _Gateway:
    """Records every policy call in a shared journal (with the worker's answer)."""

    def __init__(self, journal: List[Any], *, clamped: Any = None, fail: str = "") -> None:
        self.journal = journal
        self.clamped = clamped or []
        self.fail = fail
        self.stored: Dict[str, Any] = {}

    def _policy(self, sid: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "version": 1,
            "session_id": sid,
            "revision": 1,
            "approve": {"read_file": "all", "write_file": "all"},
            "deny": {},
            "ask": list(body.get("ask") or []),
            "request": body,
            "clamped": list(self.clamped),
            "set_by": {"tenant_id": "default", "user_id": "me", "client": body.get("client")},
            "set_at": "2026-10-27T10:00:00+00:00",
        }

    def post_session_tool_policy(self, sid: str, body: Dict[str, Any]) -> Dict[str, Any]:
        self.journal.append(("POST", sid, body))
        if self.fail == "POST":
            raise RuntimeError("chat tool policy not saved: 422")
        self.stored[sid] = self._policy(sid, body)
        return {"session_id": sid, "policy": self.stored[sid]}

    def delete_session_tool_policy(self, sid: str) -> Dict[str, Any]:
        self.journal.append(("DELETE", sid))
        if self.fail == "DELETE":
            raise RuntimeError("chat tool policy not reset: 503")
        self.stored.pop(sid, None)
        return {"session_id": sid, "policy": None, "revision": 2}

    def get_session_tool_policy(self, sid: str) -> Dict[str, Any]:
        self.journal.append(("GET", sid))
        return {"session_id": sid, "policy": self.stored.get(sid)}


def _controller(
    journal: List[Any], *, supported: bool, caps_failure: Any = None, **gateway_kwargs: Any
) -> AssistantController:
    caps_block = {"session_tool_policy": dict(_POLICY_BLOCK)} if supported else {"streaming": {"deltas": True}}
    caps = AssistantCapabilities.from_discovery_response({"capabilities": caps_block})

    def gateway_capabilities(**_: Any) -> AssistantCapabilities:
        if isinstance(caps_failure, Exception):
            raise caps_failure
        if caps_failure:
            return AssistantCapabilities.unavailable(error=str(caps_failure))
        return caps

    controller = AssistantController.__new__(AssistantController)
    controller._session_auto_approve_all = set()
    controller.llm_manager = SimpleNamespace(active_session_id="chat-a", gateway_capabilities=gateway_capabilities)
    controller.gateway = _Gateway(journal, **gateway_kwargs)
    controller.preferences = SimpleNamespace(tool_preferences={"send_email": "ask", "write_file": "approve"})
    controller.tool_inventory = lambda: {"items": [dict(i) for i in _ITEMS]}  # type: ignore[method-assign]
    return controller


class _Worker:
    def __init__(self, journal: List[Any]) -> None:
        self.journal = journal

    def provide_tool_approval(self, approved: bool, **kwargs: Any) -> None:
        self.journal.append(("ANSWER", approved, kwargs.get("wait_key")))


def _palette(controller: AssistantController, journal: List[Any]) -> SimpleNamespace:
    host = SimpleNamespace(
        _controller=controller,
        _worker=_Worker(journal),
        _activity_model=None,
        _deferred_tool_request=None,
        banners=[],
        statuses=[],
    )
    host._state = lambda name, default=None: getattr(host, name, default)
    host._clear_user_wait = lambda key: None
    host._active_session_id = lambda: str(controller.active_session_id or "")
    host._set_banner = lambda text="", tone="info", key="": host.banners.append((text, tone, key))
    host._clear_banner = lambda key: None
    host._refresh_tool_indicator = lambda: None
    host._set_history_status = lambda text, **_: host.statuses.append(text)
    host._resume_voice_after_dialog = lambda: None
    host._report_session_grant = lambda ok, result: AssistantPalette._report_session_grant(host, ok, result)
    return host


def _decide(host: SimpleNamespace, decision: str, *, rank: int = 2) -> None:
    AssistantPalette._on_tool_decision(
        host,
        decision,
        {
            "run_id": "run-1",
            "wait_key": "tool_calls:run-1:agent",
            "tool_calls": [{"name": "read_file", "arguments": {"path": "README.md"}}],
            "trust_rank": rank,
        },
    )


# --------------------------------------------------------------------------- client


@pytest.mark.basic
def test_client_session_tool_policy_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Dict[str, Any]] = []

    def fake_request_json(**kwargs: Any) -> Dict[str, Any]:
        calls.append(kwargs)
        return {"session_id": "s 1", "policy": None}

    monkeypatch.setattr(client_mod, "_request_json", fake_request_json)
    gw = GatewayClient(GatewayClientConfig(base_url="http://gateway", auth_token="tok"))
    body = {"approve": {"all": True, "max_risk_rank": 2}, "client": "abstractassistant-desktop"}
    gw.get_session_tool_policy("s 1")
    gw.put_session_tool_policy("s 1", body)
    gw.post_session_tool_policy("s 1", body)
    gw.delete_session_tool_policy("s 1")
    url = "http://gateway/api/gateway/sessions/s%201/tool-policy"
    assert [(c["method"], c["url"], c.get("body")) for c in calls] == [
        ("GET", url, None),
        ("PUT", url, body),
        ("POST", url, body),
        ("DELETE", url, None),
    ]
    with pytest.raises(ValueError):
        gw.post_session_tool_policy("", body)


@pytest.mark.basic
def test_capability_gate_is_supported_true_only() -> None:
    def caps(block: Any) -> AssistantCapabilities:
        return AssistantCapabilities.from_discovery_response({"capabilities": block})

    assert caps({"session_tool_policy": dict(_POLICY_BLOCK)}).session_tool_policy_supported() is True
    assert caps({"session_tool_policy": {"supported": "yes"}}).session_tool_policy_supported() is False
    assert caps({}).session_tool_policy_supported() is False


# --------------------------------------------------------------------------- server path


@pytest.mark.basic
def test_allow_all_writes_the_policy_before_the_shown_wait_is_answered() -> None:
    journal: List[Any] = []
    controller = _controller(journal, supported=True)
    host = _palette(controller, journal)

    _decide(host, "session", rank=3)

    assert journal == [
        (
            "POST",
            "chat-a",
            {
                "approve": {"all": True, "max_risk_rank": 3},
                "client": "abstractassistant-desktop",
                "ask": ["send_email"],
            },
        ),
        ("ANSWER", True, "tool_calls:run-1:agent"),
    ]
    assert controller.session_tool_policy_mode == "server"
    assert controller.session_trust_path() == "server"
    assert controller.session_tool_auto_approval_active()
    # The server holds the grant: a wait that still arrives is a genuine
    # question, never auto-answered here; and runs are not widened locally.
    assert controller.should_auto_approve_tool_batch([{"name": "read_file"}]) is False
    assert controller.tool_policy_for_run()["require_approval_tools"] == ["read_file", "write_file", "send_email"]
    assert host.banners == []


@pytest.mark.basic
def test_clamped_selectors_are_reported_to_the_user() -> None:
    journal: List[Any] = []
    clamped = [{"selector": "all", "name": "send_email", "reason": "not_authorized"}]
    controller = _controller(journal, supported=True, clamped=clamped)
    host = _palette(controller, journal)

    _decide(host, "session")

    assert any("send_email (not authorized)" in text and key == "trust" for text, _tone, key in host.banners)
    assert journal[-1][0] == "ANSWER"


@pytest.mark.basic
def test_a_refused_policy_write_is_said_and_the_call_is_approved_once() -> None:
    journal: List[Any] = []
    controller = _controller(journal, supported=True, fail="POST")
    host = _palette(controller, journal)

    _decide(host, "session")

    assert [entry[0] for entry in journal] == ["POST", "ANSWER"]
    assert journal[-1][1] is True
    assert not controller.session_tool_auto_approval_active()  # no silent local grant
    assert any("was not saved" in text and tone == "error" for text, tone, _key in host.banners)


@pytest.mark.basic
def test_revoke_deletes_the_server_policy() -> None:
    journal: List[Any] = []
    controller = _controller(journal, supported=True)
    controller.grant_session_tool_auto_approval(max_rank=2)
    controller.revoke_session_tool_auto_approval()
    assert journal[-1] == ("DELETE", "chat-a")
    assert not controller.session_tool_auto_approval_active()


@pytest.mark.basic
def test_a_refused_reset_keeps_the_grant_shown() -> None:
    journal: List[Any] = []
    controller = _controller(journal, supported=True, fail="DELETE")
    controller.grant_session_tool_auto_approval(max_rank=2)
    with pytest.raises(RuntimeError):
        controller.revoke_session_tool_auto_approval()
    assert controller.session_tool_auto_approval_active()


@pytest.mark.basic
def test_sync_mirrors_a_stored_policy_and_its_reset() -> None:
    journal: List[Any] = []
    controller = _controller(journal, supported=True)
    controller.gateway.stored["chat-a"] = controller.gateway._policy(
        "chat-a", {"approve": {"all": True, "max_risk_rank": 3}}
    )
    controller.sync_session_tool_policy()
    assert controller.session_trust_path() == "server"
    assert controller.session_trust_rank() == 3
    controller.gateway.stored.clear()
    controller.sync_session_tool_policy()
    assert not controller.session_tool_auto_approval_active()


@pytest.mark.basic
def test_a_second_allow_all_never_narrows_the_chats_grant() -> None:
    journal: List[Any] = []
    controller = _controller(journal, supported=True)
    controller.grant_session_tool_auto_approval(max_rank=3)
    result = controller.grant_session_tool_auto_approval(max_rank=1)
    assert [entry[2]["approve"]["max_risk_rank"] for entry in journal] == [3, 3]
    assert result["max_risk_rank"] == 3 == controller.session_trust_rank()


@pytest.mark.basic
@pytest.mark.parametrize("failure", ["timed out", TimeoutError("timed out")])
def test_unreadable_capabilities_grant_nothing_and_say_why(failure: Any) -> None:
    journal: List[Any] = []
    controller = _controller(journal, supported=True, caps_failure=failure)
    host = _palette(controller, journal)

    _decide(host, "session")

    # The shown call is approved once; no policy write, no local grant.
    assert journal == [("ANSWER", True, "tool_calls:run-1:agent")]
    assert controller.session_tool_policy_mode == "unavailable"
    assert not controller.session_tool_auto_approval_active()
    assert controller.should_auto_approve_tool_batch([{"name": "read_file"}]) is False
    assert any(
        "was not saved" in text and "timed out" in text and tone == "error" for text, tone, _key in host.banners
    )


# --------------------------------------------------------------------------- local fallback


@pytest.mark.basic
def test_without_the_capability_the_local_grant_is_the_reported_fallback(caplog: pytest.LogCaptureFixture) -> None:
    journal: List[Any] = []
    controller = _controller(journal, supported=False)
    host = _palette(controller, journal)

    with caplog.at_level(logging.WARNING, logger="abstractassistant.controller"):
        _decide(host, "session", rank=2)

    assert journal == [("ANSWER", True, "tool_calls:run-1:agent")]  # no policy route called
    assert controller.session_tool_policy_mode == "local"
    assert controller.session_trust_path() == "local"
    assert "LOCAL fallback" in caplog.text
    # ...and the person is told too, not only the log.
    assert any("in this app only" in text and key == "trust" for text, _tone, key in host.banners)
    assert controller.should_auto_approve_tool_batch([{"name": "read_file"}, {"name": "write_file"}]) is True
    assert controller.should_auto_approve_tool_batch([{"name": "send_email"}]) is False
    controller.revoke_session_tool_auto_approval()
    assert journal == [("ANSWER", True, "tool_calls:run-1:agent")]  # no DELETE either
    assert controller.sync_session_tool_policy() is None


# --------------------------------------------------------------------------- ledger record


def _decision_record(decision: str = "auto_approved") -> Dict[str, Any]:
    return {
        "step_id": "step-9",
        "status": "completed",
        "ended_at": "2026-10-27T10:00:05+00:00",
        "effect": {
            "type": "emit_event",
            "payload": {
                "name": "abstract.tool_policy_decision",
                "scope": "run",
                "payload": {
                    "decision": decision,
                    "source": "session_policy",
                    "session_id": "chat-a",
                    "node_id": "agent",
                    "tool_calls": [{"call_id": "c1", "name": "fetch_url", "matched": "kind:web"}],
                    "policy": {
                        "revision": 5,
                        "set_by": {"tenant_id": "default", "user_id": "admin", "client": "panel-chat"},
                        "set_at": "2026-10-27T10:00:00+00:00",
                    },
                },
            },
        },
        "result": {"emitted": True, "tool_policy_decision": {"decision": decision, "count": 1}},
    }


@pytest.mark.basic
def test_policy_decision_record_is_an_activity_line_not_a_wait() -> None:
    events = GatewayEventAdapter().handle_record(_decision_record())
    assert [e["type"] for e in events] == ["tool_policy_decision"]
    model = RunActivityModel(run_id="run-1")
    for event in events:
        model.apply_event(event)
    assert [(s.kind, s.status, s.title_plain) for s in model.steps] == [
        ("policy", "ok", "Allowed by this chat's policy: fetch_url")
    ]
    assert "admin" in model.steps[0].detail
    assert model.summary()["waits"] == 0
    assert model.current_step() is None


@pytest.mark.basic
def test_denied_policy_decision_reads_as_denied() -> None:
    events = GatewayEventAdapter().handle_record(_decision_record("denied"))
    model = RunActivityModel(run_id="run-1")
    model.apply_event(events[0])
    assert (model.steps[0].status, model.steps[0].title_plain) == (
        "denied",
        "Denied by this chat's policy: fetch_url",
    )
