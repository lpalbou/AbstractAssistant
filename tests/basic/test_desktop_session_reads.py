from __future__ import annotations

from threading import Event, Thread
import pytest
from abstractassistant.core.session_reads import SessionReads


def run(rid="r1", status="completed", **extra):
    return {"session_id": "chat", "run_id": rid, "status": status, **extra}


class Client:
    def __init__(self):
        self.saved = {}
        self.gets = []
        self.posts = []
        self.fail = False
        self.incomplete = False

    def session_reads(self, ids):
        self.gets.append(ids)
        return {
            "items": [row for row in self.saved.values() if row["run_id"] in ids],
            "more": False,
        }

    def mark_session_reads(self, rows):
        self.posts.append(rows)
        if self.fail:
            raise OSError("offline")
        if self.incomplete:
            return {"items": []}
        values = []
        for row in rows:
            key = (row["session_id"], row["run_id"], row["status"])
            self.saved.setdefault(
                key,
                {
                    **row,
                    "sequence": len(self.saved) + 1,
                    "at": "2026-11-01T00:00:00Z",
                    "event_id": str(key),
                },
            )
            values.append(self.saved[key])
        return {"items": values}


def test_listing_never_consumes_and_only_user_waits_need_attention():
    state = SessionReads()
    client = Client()
    state.refresh(client, [run(status="waiting", waiting={"reason": "timer"})])
    assert state.facts("chat") == {"unread": True, "needs_attention": False}
    state.refresh(client, [run(status="waiting", waiting={"reason": "user"})])
    assert state.facts("chat")["needs_attention"] and not client.posts
    state.refresh(
        client,
        [
            run("wake", parent_run_id="controller", role="occurrence", session_kind="chat"),
            run("child", parent_run_id="wake"),
            run("auto", session_kind="automation"),
        ],
    )
    assert [r["run_id"] for r in state.runs] == ["wake"]


def test_confirmed_reads_are_shared_and_request_does_not_consume_answer():
    client = Client()
    a = SessionReads()
    b = SessionReads()
    a.refresh(client, [run(status="running")])
    assert a.consume(client, a.displayed("chat", [{"role": "user", "run_id": "r1"}]))
    a.refresh(client, [run()])
    assert a.facts("chat")["unread"]
    assert not a.displayed("chat", [{"role": "user", "run_id": "r1"}])
    assert a.consume(client, a.displayed("chat", [{"role": "assistant", "run_id": "r1"}]))
    b.refresh(client, [run()])
    assert not b.facts("chat")["unread"]


def test_failed_and_incomplete_writes_retain_unread_and_retry_proven_revision():
    client = Client()
    state = SessionReads()
    state.refresh(client, [run()])
    client.fail = True
    assert not state.consume(client, [run()])
    assert state.facts("chat")["unread"] and state.pending and state.error
    client.fail = False
    client.incomplete = True
    state.refresh(client, [run()])
    assert state.facts("chat")["unread"] and state.pending
    client.incomplete = False
    state.refresh(client, [run()])
    assert not state.facts("chat")["unread"] and not state.pending and not state.error


def test_late_completion_cannot_broaden_captured_display_snapshot():
    client = Client()
    state = SessionReads()
    state.refresh(client, [run(status="running")])
    captured = state.snapshot("chat")
    state.refresh(client, [run()])
    receipts = state.displayed(
        "chat", [{"role": "user", "run_id": "r1"}, {"role": "assistant", "run_id": "r1"}], captured
    )
    assert receipts[0]["status"] == "request"
    state.consume(client, receipts)
    assert state.facts("chat")["unread"]


def test_scope_switch_ignores_late_reads_and_never_copies_pending_proof():
    a, b = Client(), Client()
    state = SessionReads()
    state.refresh(a, [run()])
    started, release = Event(), Event()
    original = a.mark_session_reads

    def delayed(rows):
        started.set()
        release.wait(2)
        return original(rows)

    a.mark_session_reads = delayed
    task = Thread(target=lambda: state.consume(a, [run()]))
    task.start()
    assert started.wait(1)
    state.refresh(b, [run()])
    release.set()
    task.join(2)
    assert state.facts("chat")["unread"] and not b.posts and not state.pending
    assert not state.consume(a, [run()])


def test_large_lists_and_display_batches_are_bounded_and_idempotent():
    client = Client()
    state = SessionReads()
    runs = [run(str(i)) for i in range(205)]
    state.refresh(client, runs)
    assert [len(ids) for ids in client.gets] == [100, 100, 5]
    assert state.consume(client, runs)
    assert [len(rows) for rows in client.posts] == [100, 100, 5]
    assert not state.facts("chat")["unread"]
    state.consume(client, runs)
    assert len(client.posts) == 3


def test_malformed_receipts_do_not_create_false_reads():
    client = Client()
    state = SessionReads()
    state.refresh(client, [run()])
    with pytest.raises(ValueError):
        state.consume(client, [{"run_id": "r1"}])
    client.session_reads = lambda ids: {"items": [run()]}
    state.refresh(client, [run()])
    assert state.error and state.facts("chat")["unread"]


def test_client_encodes_mount_relative_reads_and_archive_without_changing_auth(monkeypatch):
    from urllib.parse import urlparse, parse_qs
    from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig

    client = GatewayClient(
        GatewayClientConfig(base_url="https://gateway.test/prefix", auth_token="test-token")
    )
    calls = []
    monkeypatch.setattr(
        client, "_request_json", lambda **args: calls.append(args) or {"items": [], "more": False}
    )
    assert client.session_reads([])["items"] == [] and not calls
    client.session_reads(["r 1", "r/2", "r 1"])
    url = urlparse(calls[-1]["url"])
    assert url.path == "/prefix/api/gateway/me/session-reads"
    assert parse_qs(url.query)["run_id"] == ["r 1", "r/2"]
    client.mark_session_reads([run()])
    assert calls[-1]["body"] == {"receipts": [run()]}
    client.archive_session("chat/one")
    assert calls[-1]["url"].endswith("/sessions/chat%2Fone/archive")
    assert calls[-1]["method"] == "POST"
    with pytest.raises(ValueError):
        client.session_reads([str(i) for i in range(101)])


def test_archive_requires_the_original_account_and_a_matching_gateway_confirmation():
    from abstractassistant.core.llm_manager import LLMManager
    from types import SimpleNamespace
    manager = LLMManager.__new__(LLMManager)
    calls = []
    a = SimpleNamespace(archive_session=lambda sid: calls.append(sid) or {"session_id": sid, "archived": True})
    b = SimpleNamespace(archive_session=lambda sid: {})
    manager.gateway_client = lambda: b
    with pytest.raises(ValueError, match="account changed"): manager.archive_session("chat", owner=a)
    assert not calls
    manager.gateway_client = lambda: a
    manager.archive_session("chat", owner=a); assert calls == ["chat"]
    a.archive_session = lambda sid: {"session_id": "other", "archived": True}
    with pytest.raises(ValueError, match="did not confirm"): manager.archive_session("chat", owner=a)
