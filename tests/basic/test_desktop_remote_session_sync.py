"""A selected remote conversation follows Gateway history, including the same run."""
from __future__ import annotations

from pathlib import Path
import threading

import pytest

from test_sessions_from_gateway import FakeGateway, _close, _contents, _manager, _palette, _pump_until


SID = "phone-selected-session"
RID = "remote-root"
PROMPT = "Search the internet for the answer"
ANSWER = "The completed answer from the other client."


def _world(gw: FakeGateway, *, status: str = "waiting", answer: str = "", blank: bool = False) -> None:
    gw.page = {"items": [{"run_id": RID, "session_id": SID, "status": status,
                          "created_at": "2026-10-30T04:00:00Z", "updated_at": "2026-10-30T04:01:00Z"}],
               "has_more": False}
    gw.input_data = {RID: {"prompt": PROMPT}}
    gw.bundles = {RID: {"root_run_id": RID, "input_data": {} if blank else {"prompt": PROMPT},
                        "session": {"session_id": SID, "turns": [] if blank else [
                            {"run_id": RID, "prompt": PROMPT, "answer": answer, "status": status,
                             "created_at": "2026-10-30T04:00:00Z", "updated_at": "2026-10-30T04:01:00Z"}]},
                        "ledgers": {}}}


def _selected_palette(tmp_path: Path, gw: FakeGateway, monkeypatch):
    import abstractassistant.app as app_module

    # Isolate this feature from bootstrap's unrelated capability/event workers.
    monkeypatch.setattr(app_module.AssistantPalette, "_start_bootstrap", lambda self: None)
    manager = _manager(tmp_path / "data", gw.url)
    manager.refresh_sessions_from_gateway()
    manager.switch_session(SID)
    with monkeypatch.context() as opening:
        # Tests choose the invalidation trigger, rather than racing initial show.
        opening.setattr(app_module.AssistantPalette, "_schedule_session_refresh", lambda self: None)
        window, app = _palette(tmp_path, gw.url, monkeypatch)
    window._bootstrapping = False
    assert window._active_session_id() == SID
    return window, app


@pytest.mark.basic
def test_manager_rehydrates_completion_when_the_cached_row_and_run_id_are_unchanged(tmp_path):
    with FakeGateway() as gw:
        _world(gw)
        manager = _manager(tmp_path / "data", gw.url)
        manager.refresh_sessions_from_gateway()
        manager.switch_session(SID)
        assert manager.sync_session_from_gateway()["changed"]
        assert _contents(manager) == [("user", PROMPT)]
        assert manager.get_last_run_id() == RID
        assert manager._session_cache.row(SID).state == "waiting"

        # The shared run finishes remotely; its ID and the cached list stay put.
        _world(gw, status="completed", answer=ANSWER)
        assert manager.sync_session_from_gateway() == {"changed": True, "error": ""}
        assert _contents(manager) == [("user", PROMPT), ("assistant", ANSWER)]
        assert manager.get_last_run_id() == RID
        assert manager._session_cache.row(SID).state == "waiting"
        assert (manager._session_cache.data_dir_for(SID) / "session.json").exists()


@pytest.mark.basic
def test_remote_finished_event_populates_the_selected_blank_transcript(tmp_path, monkeypatch):
    with FakeGateway() as gw:
        _world(gw, blank=True)
        window, app = _selected_palette(tmp_path, gw, monkeypatch)
        try:
            manager = window._controller.llm_manager
            assert _pump_until(app, lambda: not window._state("_attachment_backfill_running", False)
                               and not window._state("_sessions_refresh_running", False))
            assert _contents(manager) == []
            assert not (manager._session_cache.data_dir_for(SID) / "session.json").exists()

            _world(gw, status="completed", answer=ANSWER)
            window._on_me_event({"sequence": 12, "type": "run.finished", "data": {
                "run_id": RID, "session_id": SID, "status": "completed"}}, True)

            assert _pump_until(app, lambda: _contents(manager) == [("user", PROMPT), ("assistant", ANSWER)]
                               and len(window._history_cards_by_key) == 2)
            assert manager._session_cache.row(SID).state == "done"
            assert manager.get_last_run_id() == RID
            assert window._worker is None  # Reading a final answer needs no recovery run or TTS.
        finally:
            _close(window, app)


@pytest.mark.basic
def test_remote_finish_during_an_unchanged_inflight_sync_gets_one_followup(tmp_path, monkeypatch):
    with FakeGateway() as gw:
        _world(gw)
        manager = _manager(tmp_path / "data", gw.url)
        manager.refresh_sessions_from_gateway()
        manager.switch_session(SID)
        manager.sync_session_from_gateway()
        window, app = _selected_palette(tmp_path, gw, monkeypatch)
        fetched, release = threading.Event(), threading.Event()
        try:
            manager = window._controller.llm_manager
            client = manager.gateway_client()
            get_bundle = client.get_run_history_bundle
            calls = []

            def blocked_first(**kwargs):
                bundle = get_bundle(**kwargs)
                calls.append(kwargs["run_id"])
                if len(calls) == 1:
                    fetched.set()
                    assert release.wait(5), "test failed to release first history read"
                return bundle

            monkeypatch.setattr(client, "get_run_history_bundle", blocked_first)
            monkeypatch.setattr(window._controller, "probe_reattach_candidate", lambda: None)
            window._sync_session_from_gateway()
            assert _pump_until(app, fetched.is_set)
            _world(gw, status="completed", answer=ANSWER)
            window._on_me_event({"sequence": 13, "type": "run.finished", "data": {
                "run_id": RID, "session_id": SID, "status": "completed"}}, True)
            assert _pump_until(app, lambda: bool(window._state("_session_sync_pending", False)))
            release.set()
            assert _pump_until(app, lambda: len(window._history_cards_by_key) == 2
                               and not window._state("_attachment_backfill_running", False))
            assert calls == [RID, RID]
            assert _contents(manager)[-1] == ("assistant", ANSWER)
        finally:
            release.set()
            _close(window, app)


@pytest.mark.basic
@pytest.mark.parametrize("trigger", ["reopen", "reconnect"])
def test_reopen_or_reconnect_refreshes_a_known_remote_root_without_a_new_live_event(tmp_path, monkeypatch, trigger):
    with FakeGateway() as gw:
        _world(gw)
        manager = _manager(tmp_path / "data", gw.url)
        manager.refresh_sessions_from_gateway()
        manager.switch_session(SID)
        manager.sync_session_from_gateway()
        window, app = _selected_palette(tmp_path, gw, monkeypatch)
        try:
            monkeypatch.setattr(window, "_schedule_automations_refresh", lambda: None)
            _world(gw, status="completed", answer=ANSWER)
            if trigger == "reopen":
                window.hide()
                window.show()
            else:
                window._on_me_events_state("live")
            assert _pump_until(app, lambda: len(window._history_cards_by_key) == 2)
            assert _contents(window._controller.llm_manager)[-1] == ("assistant", ANSWER)
            assert window._worker is None
        finally:
            _close(window, app)


@pytest.mark.basic
def test_a_queued_old_session_completion_never_redraws_or_attaches_it_and_syncs_the_new_selection(tmp_path, monkeypatch):
    with FakeGateway() as gw:
        _world(gw, status="completed", answer=ANSWER)
        window, app = _selected_palette(tmp_path, gw, monkeypatch)
        try:
            # B has a distinct complete history; A's completion is queued in Qt.
            second_sid, second_run = "second-phone-session", "second-root"
            second = dict(gw.page["items"][0], session_id=second_sid, run_id=second_run)
            gw.page["items"].insert(0, second)
            gw.input_data[second_run] = {"prompt": "Question B"}
            gw.bundles[second_run] = {"root_run_id": second_run, "session": {
                "session_id": second_sid, "turns": [{"run_id": second_run, "prompt": "Question B",
                    "answer": "Answer B", "created_at": "2026-10-30T04:00:00Z"}]}, "ledgers": {}}
            controller = window._controller
            controller.refresh_sessions()
            controller.switch_session(second_sid)
            captured, redraws = [], []
            window.reattach_candidate.disconnect()
            window.reattach_candidate.connect(captured.append)
            refresh = window.refresh_history
            monkeypatch.setattr(window, "refresh_history", lambda: (redraws.append(window._active_session_id()), refresh()))
            monkeypatch.setattr(controller, "probe_reattach_candidate", lambda: None)
            window._attachment_backfill_running = True
            window._sync_session_from_gateway()  # queues B behind A
            window._on_session_sync_completed({"session_id": SID, "result": {"changed": True},
                "candidate": {"run_id": RID, "status": "waiting"}, "attention_request": None})
            assert _pump_until(app, lambda: _contents(controller.llm_manager) == [("user", "Question B"), ("assistant", "Answer B")]
                               and not window._state("_attachment_backfill_running", False))
            assert redraws == [second_sid] and captured == []
            assert controller.last_run_id() == second_run and window._worker is None
        finally:
            _close(window, app)


@pytest.mark.basic
def test_an_unscoped_pending_sync_cannot_attach_before_new_attention_navigation(tmp_path, monkeypatch):
    with FakeGateway() as gw:
        _world(gw)
        window, app = _selected_palette(tmp_path, gw, monkeypatch)
        try:
            captured, followups = [], []
            window.reattach_candidate.disconnect()
            window.reattach_candidate.connect(captured.append)
            window.session_sync_again.disconnect()
            window.session_sync_again.connect(lambda: followups.append(True))
            request = (SID, "newly-validated-root", object())
            window._attention_reattach_request = request
            window._session_sync_pending = True
            window._on_session_sync_completed({"session_id": SID, "result": {"changed": False},
                "candidate": {"run_id": RID, "status": "waiting"}, "attention_request": None})
            assert captured == [] and followups == [True]
            assert window._attention_reattach_request is request
        finally:
            _close(window, app)


@pytest.mark.basic
def test_history_sync_probes_an_unfollowed_live_root_even_when_messages_and_id_match(tmp_path, monkeypatch):
    with FakeGateway() as gw:
        _world(gw)
        manager = _manager(tmp_path / "data", gw.url)
        manager.refresh_sessions_from_gateway()
        manager.switch_session(SID)
        manager.sync_session_from_gateway()
        window, app = _selected_palette(tmp_path, gw, monkeypatch)
        try:
            controller = window._controller
            assert controller.last_run_id() == RID
            probes, candidates = [], []
            monkeypatch.setattr(controller, "probe_reattach_candidate", lambda: (
                probes.append(RID) or {"run_id": RID, "status": "waiting", "waiting": {"wait_key": "gate-two"}}))
            window.reattach_candidate.disconnect()
            window.reattach_candidate.connect(candidates.append)
            window._worker = None
            window._sync_session_from_gateway()

            assert _pump_until(app, lambda: bool(candidates))
            assert probes and candidates[-1]["run_id"] == RID
            assert candidates[-1]["session_id"] == SID
            assert controller.last_run_id() == RID
        finally:
            _close(window, app)


@pytest.mark.basic
def test_session_list_arriving_after_an_empty_sync_rebuilds_the_transcript(tmp_path, monkeypatch):
    with FakeGateway() as gw:
        _world(gw, status="completed", answer=ANSWER)
        window, app = _selected_palette(tmp_path, gw, monkeypatch)
        try:
            manager = window._controller.llm_manager
            manager._session_cache.set_rows([], truncated=False)
            assert window._controller.last_run_id() is None
            window._sync_session_from_gateway()
            assert _pump_until(app, lambda: not window._state("_attachment_backfill_running", False))
            assert _contents(manager) == []

            window._refresh_sessions_from_gateway()
            assert _pump_until(app, lambda: _contents(manager) == [("user", PROMPT), ("assistant", ANSWER)]
                               and len(window._history_cards_by_key) == 2)
            assert manager.get_last_run_id() == RID
            assert window._worker is None
        finally:
            _close(window, app)
