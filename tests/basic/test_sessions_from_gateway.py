"""Sessions come from the gateway; the local files are a rebuildable cache.

Driven against a small local fake gateway (an HTTP stub on 127.0.0.1 serving
the `fixtures/gateway_runs/` answers — the shared shape of `/runs`,
`/runs/{id}/input_data` and `/runs/{id}/history_bundle`). It refuses unknown
`/runs` query parameters with a 400, like the real route. Every test uses its
own data dir; nothing touches ~/.abstractassistant or a real gateway.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

import pytest

from abstractassistant.config import Config
from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.core.session_store import SessionSnapshot, SessionStore

FIXTURES = Path(__file__).parent / "fixtures" / "gateway_runs"
_KNOWN_RUNS_PARAMS = {
    "limit", "offset", "query", "status", "workflow_id", "session_id", "parent_run_id",
    "root_only", "include_ledger_len", "include_metrics", "include_drafts", "session_kind",
}


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeGateway:
    """Serves the fixture world; records every request path."""

    def __init__(self) -> None:
        self.page: Dict[str, Any] = _fixture("runs_page.json")
        self.input_data: Dict[str, Any] = _fixture("input_data.json")
        self.bundles: Dict[str, Any] = _fixture("history_bundles.json")
        self.requests: List[str] = []
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                return

            def _send(self, status: int, payload: Any) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                outer.requests.append(self.path)
                url = urlparse(self.path)
                parts = url.path.strip("/").split("/")
                if url.path == "/api/gateway/runs":
                    unknown = sorted(set(parse_qs(url.query)) - _KNOWN_RUNS_PARAMS)
                    if unknown:
                        self._send(400, {"detail": f"Unknown query parameter(s): {', '.join(unknown)}"})
                        return
                    # Offset paging like the gateway: `has_more` says whether a
                    # next page exists (an explicit True in the page is kept).
                    query = parse_qs(url.query)
                    offset = int((query.get("offset") or ["0"])[0])
                    limit = int((query.get("limit") or ["200"])[0])
                    items = list(outer.page.get("items") or [])
                    served = dict(outer.page)
                    served["items"] = items[offset: offset + limit]
                    served["offset"] = offset
                    served["has_more"] = bool(outer.page.get("has_more")) or offset + limit < len(items)
                    self._send(200, served)
                    return
                if len(parts) == 5 and parts[:3] == ["api", "gateway", "runs"]:
                    run_id, what = parts[3], parts[4]
                    table = outer.input_data if what == "input_data" else outer.bundles if what == "history_bundle" else {}
                    if run_id in table:
                        self._send(200, table[run_id])
                        return
                self._send(404, {"detail": "not found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeGateway":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

    def listing_requests(self) -> List[str]:
        return [p for p in self.requests if urlparse(p).path == "/api/gateway/runs"]


# 127.0.0.1:9 is the discard port: connection refused, immediately.
OFFLINE = "http://127.0.0.1:9"


def _manager(data_dir: Path, url: str) -> LLMManager:
    config = Config()
    config.gateway.url = url
    config.gateway.auth_token = "test-token"
    return LLMManager(config=config, data_dir=data_dir)


def _rows(manager: LLMManager) -> Dict[str, Dict[str, Any]]:
    return {d["session_id"]: d for d in manager.session_digests()}


def _contents(manager: LLMManager) -> List[tuple]:
    return [(m.get("role"), m.get("content")) for m in manager.session_messages()]


GATEWAY_SESSIONS = {"sess_hot", "sess_alpha", "sess_cold", "sess_beta", "sess_unknown"}


# ------------------------------------------------------------------ the list


@pytest.mark.basic
def test_sessions_another_client_created_appear_with_their_first_prompt(tmp_path: Path) -> None:
    with FakeGateway() as gw:
        manager = _manager(tmp_path / "data", gw.url)
        result = manager.refresh_sessions_from_gateway()

    assert result["ok"] is True
    # The exact pinned query reached the gateway (anything else would 400).
    assert gw.listing_requests() == ["/api/gateway/runs?limit=200&offset=0&root_only=true&include_ledger_len=false"]
    rows = _rows(manager)
    # None of these ids was ever minted by this install.
    assert GATEWAY_SESSIONS <= set(rows)
    assert rows["sess_hot"]["display_title"] == "Refactor the router module"
    assert rows["sess_alpha"]["display_title"] == "Plan the Q3 launch checklist"
    assert rows["sess_alpha"]["turns"] == 3
    assert rows["sess_alpha"]["state"] == "waiting"
    assert rows["sess_unknown"]["display_title"] == "Untitled session"
    # Titles are read from the FIRST run of each session.
    assert any(p.startswith("/api/gateway/runs/run_alpha_1/input_data") for p in gw.requests)
    # The fresh install's own new session is listed while active, as new and empty.
    active = manager.active_session_id
    assert active not in GATEWAY_SESSIONS
    assert rows[active]["on_gateway"] is False
    assert rows[active]["messages"] == 0


@pytest.mark.basic
def test_the_list_needs_the_fold_a_gateway_row_never_comes_from_local_files(tmp_path: Path) -> None:
    """Before any gateway answer there is nothing but the active session: the
    rows really come from the gateway fold, not from the data dir."""
    manager = _manager(tmp_path / "data", OFFLINE)
    assert set(_rows(manager)) == {manager.active_session_id}


@pytest.mark.basic
def test_fetched_titles_are_cached_and_not_asked_again(tmp_path: Path) -> None:
    with FakeGateway() as gw:
        manager = _manager(tmp_path / "data", gw.url)
        manager.refresh_sessions_from_gateway()
        first = [p for p in gw.requests if "/input_data" in p]
        manager.refresh_sessions_from_gateway()
        second = [p for p in gw.requests if "/input_data" in p]
    assert first and second == first


@pytest.mark.basic
def test_a_rename_is_a_local_label_over_the_gateway_title(tmp_path: Path) -> None:
    with FakeGateway() as gw:
        manager = _manager(tmp_path / "data", gw.url)
        manager.refresh_sessions_from_gateway()
        manager.rename_session("sess_alpha", "Launch plan")
        assert _rows(manager)["sess_alpha"]["display_title"] == "Launch plan"
        manager.rename_session("sess_alpha", "")
        assert _rows(manager)["sess_alpha"]["display_title"] == "Plan the Q3 launch checklist"


@pytest.mark.basic
def test_a_new_session_is_listed_only_while_active_until_it_has_a_run(tmp_path: Path) -> None:
    with FakeGateway() as gw:
        manager = _manager(tmp_path / "data", gw.url)
        manager.refresh_sessions_from_gateway()
        draft = manager.create_new_session()
        assert draft in _rows(manager)
        manager.switch_session("sess_alpha")
        assert draft not in _rows(manager)
        # Its first run makes it a gateway session: the next list has it.
        gw.page["items"].insert(
            0,
            {"run_id": "run_draft_1", "status": "completed", "session_id": draft,
             "created_at": "2026-09-27T09:00:00+00:00", "updated_at": "2026-09-27T09:00:10+00:00"},
        )
        manager.refresh_sessions_from_gateway()
        assert _rows(manager)[draft]["on_gateway"] is True


# ------------------------------------------------------------- transcripts


@pytest.mark.basic
def test_opening_a_session_replaces_its_cache_with_the_gateway_history(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with FakeGateway() as gw:
        manager = _manager(data, gw.url)
        manager.refresh_sessions_from_gateway()
        # A stale cache: one turn, and an answer the gateway never had.
        SessionStore(manager._session_cache.data_dir_for("sess_alpha") / "session.json").save(
            SessionSnapshot(
                session_id="sess_alpha",
                actor_id="gateway",
                messages=[
                    {"role": "user", "content": "Plan the Q3 launch checklist"},
                    {"role": "assistant", "content": "a stale local answer"},
                ],
            )
        )
        manager.switch_session("sess_alpha")
        # Instant first paint: the cache.
        assert ("assistant", "a stale local answer") in _contents(manager)

        result = manager.sync_session_from_gateway()

    assert result == {"changed": True, "error": ""}
    assert _contents(manager)[:6] == [
        ("user", "Plan the Q3 launch checklist"),
        ("assistant", "Here is the checklist."),
        ("user", "Add the budget line"),
        ("assistant", "Budget added."),
        ("user", "And the staffing risks?"),
        ("assistant", "Two risks stand out."),
    ]
    assert ("assistant", "a stale local answer") not in _contents(manager)
    # Attachments come from the gateway's turn refs.
    budget = manager.session_messages()[2]
    assert budget["metadata"]["attachments"][0]["$artifact"] == "art_budget"
    # The bundle of the session's LATEST root run was asked for.
    assert any(p.startswith("/api/gateway/runs/run_alpha_3/history_bundle") for p in gw.requests)
    assert manager.get_last_run_id() == "run_alpha_3"


@pytest.mark.basic
def test_a_sync_that_lands_after_a_switch_writes_nothing(tmp_path: Path) -> None:
    with FakeGateway() as gw:
        manager = _manager(tmp_path / "data", gw.url)
        manager.refresh_sessions_from_gateway()
        manager.switch_session("sess_alpha")
        client = manager.gateway_client()
        real = client.get_run_history_bundle

        def _slow(**kwargs):
            bundle = real(**kwargs)
            manager.switch_session("sess_cold")  # the user moved on meanwhile
            return bundle

        client.get_run_history_bundle = _slow  # type: ignore[method-assign]
        assert manager.sync_session_from_gateway() == {"changed": False, "error": ""}
    assert manager.active_session_id == "sess_cold"
    assert _contents(manager) == []
    assert not (manager._session_cache.data_dir_for("sess_alpha") / "session.json").exists()


@pytest.mark.basic
def test_clearing_the_cache_loses_nothing_the_gateway_has(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with FakeGateway() as gw:
        manager = _manager(data, gw.url)
        manager.refresh_sessions_from_gateway()
        manager.switch_session("sess_beta")
        manager.sync_session_from_gateway()
        before_rows = {sid: (r["display_title"], r["turns"], r["state"]) for sid, r in _rows(manager).items() if sid in GATEWAY_SESSIONS}
        before_beta = _contents(manager)
        assert before_beta and len(before_rows) == len(GATEWAY_SESSIONS)

        shutil.rmtree(data)

        reopened = _manager(data, gw.url)
        assert not (set(_rows(reopened)) & GATEWAY_SESSIONS), "nothing is listed before the gateway answers"
        reopened.refresh_sessions_from_gateway()
        after_rows = {sid: (r["display_title"], r["turns"], r["state"]) for sid, r in _rows(reopened).items() if sid in GATEWAY_SESSIONS}
        reopened.switch_session("sess_beta")
        assert _contents(reopened) == []  # no cache left to paint
        reopened.sync_session_from_gateway()

    assert after_rows == before_rows
    assert _contents(reopened) == before_beta


# --------------------------------------------------------------- migration


def _legacy_data_dir(data: Path) -> None:
    """The 0.6.1-and-earlier layout: `sessions.json` + `session.json` (the base session)
    + `sessions/<id>/session.json`. Two sessions exist on the gateway
    (sess_beta, the base one, renamed by the user; sess_cold), two do not."""
    data.mkdir(parents=True)

    def _snap(path: Path, sid: str, text: str) -> None:
        SessionStore(path).save(
            SessionSnapshot(
                session_id=sid,
                actor_id=f"actor_{sid}",
                messages=[{"role": "user", "content": text}, {"role": "assistant", "content": f"answer to {text}"}],
                last_run_id=None,
            )
        )

    _snap(data / "session.json", "sess_beta", "Summarize the release notes")
    _snap(data / "sessions" / "sess_cold" / "session.json", "sess_cold", "What is on today's news?")
    _snap(data / "sessions" / "sess_gone_1" / "session.json", "sess_gone_1", "an old local-only question")
    _snap(data / "sessions" / "sess_gone_2" / "session.json", "sess_gone_2", "another local-only question")
    records = [
        {"session_id": "sess_beta", "actor_id": "a", "title": "Release notes", "path": ".",
         "created_at": "2026-09-01T10:00:00+00:00", "updated_at": "2026-09-25T12:30:00+00:00"},
        {"session_id": "sess_cold", "actor_id": "a", "title": "New session", "path": "sessions/sess_cold",
         "created_at": "2026-09-02T10:00:00+00:00", "updated_at": "2026-09-26T07:00:00+00:00"},
        {"session_id": "sess_gone_1", "actor_id": "a", "title": "Old notes", "path": "sessions/sess_gone_1",
         "created_at": "2026-07-01T10:00:00+00:00", "updated_at": "2026-07-01T10:00:00+00:00"},
        {"session_id": "sess_gone_2", "actor_id": "a", "title": "New session", "path": "sessions/sess_gone_2",
         "created_at": "2026-07-02T10:00:00+00:00", "updated_at": "2026-07-02T10:00:00+00:00"},
    ]
    (data / "sessions.json").write_text(
        json.dumps({"active_session_id": "sess_beta", "sessions": records}), encoding="utf-8"
    )


@pytest.mark.basic
def test_migration_keeps_resolving_sessions_and_sets_orphans_aside_once(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _legacy_data_dir(data)
    legacy = data / "sessions-legacy"

    with FakeGateway() as gw:
        manager = _manager(data, gw.url)
        # Step one is local: the old index is kept aside, the base session's
        # transcript moved into the cache layout, all four still listed.
        assert (legacy / "sessions.json").exists()
        assert not (data / "sessions.json").exists()
        assert not (data / "session.json").exists()
        assert {"sess_beta", "sess_cold", "sess_gone_1", "sess_gone_2"} <= set(_rows(manager))
        assert manager.active_session_id == "sess_beta"
        assert ("user", "Summarize the release notes") in _contents(manager)

        result = manager.refresh_sessions_from_gateway()

    assert result["removed"] == 2
    rows = _rows(manager)
    assert "sess_gone_1" not in rows and "sess_gone_2" not in rows
    # Resolving rows are kept, with the user's rename as the local label.
    assert rows["sess_beta"]["display_title"] == "Release notes"
    assert rows["sess_cold"]["display_title"] == "What is on today's news?"
    # The orphans' text is kept, not deleted.
    kept = SessionStore(legacy / "sess_gone_1" / "session.json").load()
    assert kept is not None and kept.messages[0]["content"] == "an old local-only question"
    assert (legacy / "sess_gone_2" / "session.json").exists()
    assert not (data / "sessions" / "sess_gone_1").exists()
    # ONE notice, naming the count and where the text is.
    state = manager.session_list_state()
    assert state["notice"] == (
        "2 local-only sessions from an earlier version were removed from the list; "
        f"their text is kept in {legacy}"
    )
    assert manager.take_session_notice() == state["notice"]
    assert manager.take_session_notice() == ""

    # A second start migrates nothing and says nothing.
    with FakeGateway() as gw:
        again = _manager(data, gw.url)
        assert again.refresh_sessions_from_gateway()["removed"] == 0
    assert again.session_list_state()["notice"] == ""
    assert "sess_gone_1" not in _rows(again)


@pytest.mark.basic
def test_migration_waits_for_a_complete_list(tmp_path: Path) -> None:
    """A truncated page cannot prove a session absent: nothing is dropped."""
    data = tmp_path / "data"
    _legacy_data_dir(data)
    with FakeGateway() as gw:
        gw.page["has_more"] = True
        manager = _manager(data, gw.url)
        assert manager.refresh_sessions_from_gateway()["removed"] == 0
    assert {"sess_gone_1", "sess_gone_2"} <= set(_rows(manager))
    assert (data / "sessions" / "sess_gone_1" / "session.json").exists()
    assert manager.session_list_state()["notice"] == ""


@pytest.mark.basic
def test_an_active_local_only_session_stays_usable_and_its_text_is_copied(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _legacy_data_dir(data)
    index = json.loads((data / "sessions.json").read_text(encoding="utf-8"))
    index["active_session_id"] = "sess_gone_1"
    (data / "sessions.json").write_text(json.dumps(index), encoding="utf-8")
    with FakeGateway() as gw:
        manager = _manager(data, gw.url)
        assert manager.refresh_sessions_from_gateway()["removed"] == 2
    # Still on screen, still writable, listed while active; the text is kept.
    assert manager.active_session_id == "sess_gone_1"
    assert ("user", "an old local-only question") in _contents(manager)
    assert _rows(manager)["sess_gone_1"]["on_gateway"] is False
    assert (data / "sessions-legacy" / "sess_gone_1" / "session.json").exists()


# ----------------------------------------------------------------- offline


@pytest.mark.basic
def test_offline_the_cached_rows_stay_marked_and_nothing_is_deleted(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with FakeGateway() as gw:
        online = _manager(data, gw.url)
        online.refresh_sessions_from_gateway()
        cached = {sid: r["display_title"] for sid, r in _rows(online).items()}

    offline = _manager(data, OFFLINE)
    result = offline.refresh_sessions_from_gateway(timeout_s=2.0)
    assert result["ok"] is False
    state = offline.session_list_state()
    assert state["error"], "the failure is reported for the header marker"
    assert {sid: r["display_title"] for sid, r in _rows(offline).items() if sid in GATEWAY_SESSIONS} == {
        sid: title for sid, title in cached.items() if sid in GATEWAY_SESSIONS
    }

    # The next successful fetch reconciles and clears the marker.
    with FakeGateway() as gw:
        back = _manager(data, gw.url)
        back._session_list_error = "stale"
        assert back.refresh_sessions_from_gateway()["ok"] is True
    assert back.session_list_state()["error"] == ""


@pytest.mark.basic
def test_offline_before_the_migration_lists_every_old_session(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _legacy_data_dir(data)
    manager = _manager(data, OFFLINE)
    manager.refresh_sessions_from_gateway(timeout_s=2.0)
    assert {"sess_beta", "sess_cold", "sess_gone_1", "sess_gone_2"} <= set(_rows(manager))
    assert (data / "sessions" / "sess_gone_2" / "session.json").exists()


# ------------------------------------------------------ unreadable snapshot


@pytest.mark.basic
def test_an_unreadable_cached_transcript_is_rebuilt_from_the_gateway(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with FakeGateway() as gw:
        manager = _manager(data, gw.url)
        manager.refresh_sessions_from_gateway()
        broken = manager._session_cache.data_dir_for("sess_alpha") / "session.json"
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_text("{not json", encoding="utf-8")

        manager.switch_session("sess_alpha")
        assert "could not be read" in manager.session_problem()
        # Never replaced by an empty transcript: the bytes are kept aside.
        aside = [p for p in (data / "sessions-legacy").iterdir() if "unreadable" in p.name]
        assert len(aside) == 1 and aside[0].read_text(encoding="utf-8") == "{not json"

        result = manager.sync_session_from_gateway()

    assert result == {"changed": True, "error": ""}
    assert manager.session_problem() == ""
    rebuilt = SessionStore(broken).read()
    assert rebuilt is not None and len(rebuilt.messages) >= 6


@pytest.mark.basic
def test_an_unreadable_cached_transcript_is_surfaced_when_the_gateway_cannot_rebuild_it(tmp_path: Path) -> None:
    data = tmp_path / "data"
    manager = _manager(data, OFFLINE)
    broken = manager._session_cache.data_dir_for("sess_alpha") / "session.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{not json", encoding="utf-8")
    manager.switch_session("sess_alpha")

    result = manager.sync_session_from_gateway()

    assert result["changed"] is False
    assert "could not be read" in result["error"] and "could not be reached" in result["error"]
    # No empty snapshot was written in its place.
    assert not broken.exists()


# ------------------------------------------------------ headless UI (offscreen)


def _palette(tmp_path: Path, url: str, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PYSTRAY_BACKEND", "dummy")
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtWidgets import QApplication

    import abstractassistant.app as app_module
    from abstractassistant.controller import AssistantController

    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    # Offscreen, the native traffic-light bridge segfaults; the global hotkey
    # must not register either.
    monkeypatch.setattr(app_module, "_MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE", False)
    config = Config()
    config.gateway.url = url
    config.gateway.auth_token = "test-token"
    controller = AssistantController(config=config, data_dir=tmp_path / "data")
    controller.update_preferences(hotkey_enabled=False)
    window = app_module.AssistantPalette(controller=controller)
    window.resize(650, 700)
    window.show()
    _QAPP.processEvents()
    return window, _QAPP


_QAPP = None


def _pump_until(app, predicate, *, seconds: float = 10.0) -> bool:
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _close(window, app) -> None:
    from abstractassistant.theme import BASE_METRICS, DEFAULT_THEME, activate, activate_metrics

    switcher = window._state("_session_switcher")
    if switcher is not None:
        switcher.close()
    window.close()
    window.deleteLater()
    app.processEvents()
    activate(DEFAULT_THEME)
    activate_metrics(BASE_METRICS.font_body)


@pytest.mark.basic
def test_the_switcher_shows_gateway_fed_rows(tmp_path: Path, monkeypatch) -> None:
    with FakeGateway() as gw:
        window, app = _palette(tmp_path, gw.url, monkeypatch)
        try:
            window._open_session_switcher()
            switcher = window._session_switcher
            shown = lambda: {r.session_id for r in switcher.visible_rows()}  # noqa: E731
            assert _pump_until(app, lambda: GATEWAY_SESSIONS <= shown()), shown()
            titles = {r.session_id: r.digest.display_title for r in switcher.visible_rows()}
            assert titles["sess_alpha"] == "Plan the Q3 launch checklist"
            assert titles["sess_hot"] == "Refactor the router module"
            assert switcher.status_text == ""
            # Grouped by recency, as before: every row sits under a group header.
            assert switcher._group_labels

            # Opening the switcher asks the gateway again: a session another
            # client started meanwhile shows up without a relaunch.
            switcher.close()
            gw.page["items"].insert(
                0,
                {"run_id": "run_new_1", "status": "running", "session_id": "sess_from_elsewhere",
                 "created_at": "2026-09-27T09:00:00+00:00", "updated_at": "2026-09-27T09:00:05+00:00"},
            )
            window._open_session_switcher()
            assert _pump_until(app, lambda: "sess_from_elsewhere" in shown()), shown()
        finally:
            _close(window, app)


@pytest.mark.basic
def test_the_switcher_marks_cached_rows_when_the_gateway_is_unreachable(tmp_path: Path, monkeypatch) -> None:
    with FakeGateway() as gw:
        _manager(tmp_path / "data", gw.url).refresh_sessions_from_gateway()
    window, app = _palette(tmp_path, OFFLINE, monkeypatch)
    try:
        window._open_session_switcher()
        switcher = window._session_switcher
        assert GATEWAY_SESSIONS <= {r.session_id for r in switcher.visible_rows()}
        assert _pump_until(app, lambda: switcher.status_text == "Cached — gateway unreachable"), switcher.status_text
        # Still every cached row: nothing was dropped.
        assert GATEWAY_SESSIONS <= {r.session_id for r in switcher.visible_rows()}
    finally:
        _close(window, app)


# ------------------------------------------- review 37: D2, D4, D1, D3, follow-ups


@pytest.mark.basic
def test_removing_a_local_only_session_keeps_its_text(tmp_path: Path) -> None:
    """Offline first start: an old local session is pending (its only copy is
    local). Removing it from the list moves the text, never deletes it."""
    data = tmp_path / "data"
    _legacy_data_dir(data)
    manager = _manager(data, OFFLINE)
    assert "sess_gone_1" in _rows(manager)

    manager.delete_session("sess_gone_1")

    assert "sess_gone_1" not in _rows(manager)
    kept = SessionStore(data / "sessions-legacy" / "sess_gone_1" / "session.json").load()
    assert kept is not None and kept.messages[0]["content"] == "an old local-only question"


def _mixed_page(own: int, other: int) -> Dict[str, Any]:
    items = []
    # Other clients' sessions are the NEWEST, so title priority matters.
    for i in range(other):
        items.append({"run_id": f"run_x{i}", "status": "completed", "session_id": f"acode-{i}",
                      "created_at": f"2026-09-27T{i // 60:02d}:{i % 60:02d}:00+00:00",
                      "updated_at": f"2026-09-27T{i // 60:02d}:{i % 60:02d}:30+00:00"})
    for i in range(own):
        items.append({"run_id": f"run_own{i}", "status": "completed", "session_id": f"sess_own{i}",
                      "created_at": f"2026-09-20T10:{i:02d}:00+00:00",
                      "updated_at": f"2026-09-20T10:{i:02d}:30+00:00"})
    items.sort(key=lambda r: r["updated_at"], reverse=True)
    return {"items": items, "count": len(items), "offset": 0, "has_more": False}


@pytest.mark.basic
def test_every_gateway_session_is_listed_whichever_client_started_it(tmp_path: Path) -> None:
    """Operator ruling 2026-09-27: every client sees the same pool of sessions —
    no own/other scope, no toggle, no id-prefix classification."""
    data = tmp_path / "data"
    with FakeGateway() as gw:
        gw.page = _mixed_page(own=20, other=30)
        manager = _manager(data, gw.url)
        manager.refresh_sessions_from_gateway()
        rows = [r for r in _rows(manager).values() if r["on_gateway"]]
        assert len(rows) == 50
        assert {r["session_id"] for r in rows} >= {"acode-0", "sess_own0"}
        assert all("own" not in r for r in rows)
    assert not hasattr(manager, "show_all_sessions")


@pytest.mark.basic
def test_sessions_are_listed_a_page_at_a_time(tmp_path: Path) -> None:
    """250 sessions: the first 100 and "Load more"; one more page shows 200."""
    data = tmp_path / "data"
    with FakeGateway() as gw:
        gw.page = _mixed_page(own=0, other=250)
        manager = _manager(data, gw.url)
        manager.refresh_sessions_from_gateway()
        on_gateway = lambda: [r for r in _rows(manager).values() if r["on_gateway"]]  # noqa: E731
        assert len(on_gateway()) == 100
        assert manager.session_list_state()["more"] is True
        first = [p for p in gw.listing_requests()]
        assert first == ["/api/gateway/runs?limit=200&offset=0&root_only=true&include_ledger_len=false"]
        manager.load_more_sessions()
        assert len(on_gateway()) == 200
        assert manager.session_list_state()["more"] is True  # 50 more exist
        assert gw.listing_requests()[-1].startswith("/api/gateway/runs?limit=200&offset=200&")
        manager.load_more_sessions()
        assert len(on_gateway()) == 250
        assert manager.session_list_state()["more"] is False
        # Newest first across pages.
        stamps = [r["updated_at"] for r in on_gateway()]
        assert stamps == sorted(stamps, reverse=True)


class _Killed(BaseException):
    """Stands for SIGKILL: nothing after it runs, and no `except Exception` catches it."""


@pytest.mark.basic
@pytest.mark.parametrize("kill_at", ["base_session_move", "index_set_aside", "after_index_set_aside"])
def test_a_crash_during_the_conversion_loses_no_session_and_no_label(tmp_path: Path, monkeypatch, kill_at: str) -> None:
    import abstractassistant.core.session_cache as cache_module

    clean = tmp_path / "clean"
    _legacy_data_dir(clean)
    expected_rows = {sid: r["display_title"] for sid, r in _rows(_manager(clean, OFFLINE)).items()}

    data = tmp_path / "data"
    _legacy_data_dir(data)
    real_move = shutil.move

    def _move(src, dst, *a, **k):
        name = Path(src).name
        if (kill_at == "base_session_move" and Path(src) == data / "session.json") or (
            kill_at == "index_set_aside" and name == "sessions.json"
        ):
            raise _Killed()
        moved = real_move(src, dst, *a, **k)
        if kill_at == "after_index_set_aside" and name == "sessions.json":
            raise _Killed()  # the old index is gone; only the cache can know the sessions now
        return moved

    monkeypatch.setattr(cache_module.shutil, "move", _move)
    with pytest.raises(_Killed):
        _manager(data, OFFLINE)
    monkeypatch.setattr(cache_module.shutil, "move", real_move)

    restarted = _manager(data, OFFLINE)
    assert {sid: r["display_title"] for sid, r in _rows(restarted).items()} == expected_rows
    assert restarted.active_session_id == "sess_beta"
    assert (data / "sessions-legacy" / "sessions.json").exists()
    assert not (data / "sessions.json").exists()


@pytest.mark.basic
def test_an_unreadable_transcript_is_still_reported_after_a_restart(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = _manager(data, OFFLINE)
    broken = first._session_cache.data_dir_for("sess_alpha") / "session.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{not json", encoding="utf-8")
    first.switch_session("sess_alpha")
    assert first.sync_session_from_gateway()["error"]

    # Restart, gateway still unreachable: the session does not open silently.
    second = _manager(data, OFFLINE)
    assert second.active_session_id == "sess_alpha"
    assert "could not be read" in second.session_problem()
    assert "could not be read" in second.sync_session_from_gateway()["error"]

    # Once the gateway rebuilds it, the marker is gone.
    with FakeGateway() as gw:
        third = _manager(data, gw.url)
        third.refresh_sessions_from_gateway()
        assert third.sync_session_from_gateway() == {"changed": True, "error": ""}
    assert third.session_problem() == ""
    assert _manager(data, OFFLINE).session_problem() == ""


@pytest.mark.basic
def test_opening_a_session_moved_to_legacy_says_where_its_text_is(tmp_path: Path) -> None:
    """A stale switcher can still show a session the migration just moved."""
    data = tmp_path / "data"
    _legacy_data_dir(data)
    with FakeGateway() as gw:
        manager = _manager(data, gw.url)
        manager.refresh_sessions_from_gateway()  # moves sess_gone_2 aside
    manager.switch_session("sess_gone_2")
    assert _contents(manager) == []
    notice = manager.session_notice()
    assert str(data / "sessions-legacy" / "sess_gone_2" / "session.json") in notice
    manager.switch_session("sess_beta")
    assert manager.session_notice() == ""


@pytest.mark.basic
def test_a_switch_during_a_sync_gets_its_own_sync_when_that_one_ends() -> None:
    pytest.importorskip("PyQt5.QtWidgets")
    import abstractassistant.app as app_module

    palette = app_module.AssistantPalette.__new__(app_module.AssistantPalette)
    release = threading.Event()
    again: List[int] = []

    class _Controller:
        active_session_id = "sess_a"

        def last_run_id(self):
            return ""

        def sync_session_from_gateway(self):
            release.wait(timeout=5)
            return {"changed": False, "error": ""}

    palette._controller = _Controller()
    palette.session_attachments_restored = type("S", (), {"emit": staticmethod(lambda *a: None)})()
    palette.session_sync_failed = type("S", (), {"emit": staticmethod(lambda *a: None)})()
    palette.session_sync_again = type("S", (), {"emit": staticmethod(lambda *a: again.append(1))})()

    app_module.AssistantPalette._sync_session_from_gateway(palette)
    palette._controller.active_session_id = "sess_b"  # the user switched meanwhile
    app_module.AssistantPalette._sync_session_from_gateway(palette)  # skipped: one at a time
    release.set()
    assert _wait(lambda: again == [1]), again


def _wait(predicate, seconds: float = 5.0) -> bool:
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.mark.basic
def test_the_switcher_lists_every_clients_sessions_with_no_toggle(tmp_path: Path, monkeypatch) -> None:
    with FakeGateway() as gw:
        gw.page["items"].insert(
            0,
            {"run_id": "run_code_1", "status": "completed", "session_id": "acode-42",
             "created_at": "2026-09-27T08:00:00+00:00", "updated_at": "2026-09-27T08:00:05+00:00"},
        )
        window, app = _palette(tmp_path, gw.url, monkeypatch)
        try:
            window._open_session_switcher()
            switcher = window._session_switcher
            shown = lambda: {r.session_id for r in switcher.visible_rows()}  # noqa: E731
            assert _pump_until(app, lambda: (GATEWAY_SESSIONS | {"acode-42"}) <= shown()), shown()
            assert not hasattr(switcher, "scope_button")
        finally:
            _close(window, app)



@pytest.mark.basic
def test_a_sessions_folder_comes_only_from_the_gateway_row(tmp_path: Path) -> None:
    """Operator ruling 2026-09-27: the folder is the `/runs` row's
    `workspace_root`; a folder remembered in the local transcript is never used."""
    from abstractassistant.core.session_store import SessionSnapshot, SessionStore

    data = tmp_path / "data"
    with FakeGateway() as gw:
        for item in gw.page["items"]:
            if item["session_id"] == "sess_hot":
                item["workspace_root"] = "/srv/ws/hot"
        manager = _manager(data, gw.url)
        manager.refresh_sessions_from_gateway()
        # The cache remembers a folder for sess_alpha; the gateway row does not report one.
        SessionStore(data / "sessions" / "sess_alpha" / "session.json").save(
            SessionSnapshot(session_id="sess_alpha", actor_id="gateway", messages=[{"role": "user", "content": "hi"}],
                            last_run_id=None, workspace_root="/Users/me/cached")
        )
        rows = _rows(manager)
    assert (rows["sess_hot"]["workspace_root"], rows["sess_hot"]["workspace_reported"]) == ("/srv/ws/hot", True)
    assert (rows["sess_alpha"]["workspace_root"], rows["sess_alpha"]["workspace_reported"]) == ("", False)
