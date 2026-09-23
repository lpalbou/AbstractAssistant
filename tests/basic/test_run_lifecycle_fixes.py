"""Run lifecycle fixes: per-session workspace, start failures that keep the
user's turn, non-fatal wait-answer errors, honest STT pins, persona-preserving
system prompt."""

from __future__ import annotations

import os

# Before ANY PyQt import: a tray icon is a real QPixmap render, and it aborts
# the process if Qt came up on the platform plugin the desktop would use.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from abstractassistant.config import Config
from abstractassistant.controller import AssistantController
from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.core.session_store import SessionSnapshot, SessionStore
from abstractassistant.preferences import AssistantPreferences
from abstractassistant.ui.gateway_worker import GatewayWorker

_APP = None


class _Signal:
    def __init__(self) -> None:
        self.items: list = []

    def emit(self, payload) -> None:
        self.items.append(payload)


def _manager(tmp_path: Path) -> LLMManager:
    return LLMManager(config=Config.default(), data_dir=tmp_path / "data")


# --------------------------------------------------------------------------- session workspace


@pytest.mark.basic
def test_session_snapshot_round_trips_workspace_root_and_stays_backward_compatible(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "session.json")
    snap = SessionSnapshot(session_id="s1", actor_id="gateway", messages=[], workspace_root="/srv/ws/abc")
    store.save(snap)
    assert store.load().workspace_root == "/srv/ws/abc"

    # Older files without the key still load (blank root).
    (tmp_path / "old.json").write_text('{"session_id": "s2", "actor_id": "gateway", "messages": []}', encoding="utf-8")
    assert SessionStore(tmp_path / "old.json").load().workspace_root == ""


@pytest.mark.basic
def test_llm_manager_remembers_workspace_root_per_session_and_across_appends(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    first = manager.active_session_id
    manager.set_session_workspace_root("/gw/workspaces/one")
    manager.append_message(role="user", content="hello")  # must not drop the root
    manager.set_last_run_id("run-1")
    assert manager.session_workspace_root() == "/gw/workspaces/one"

    second = manager.create_new_session()
    assert second != first
    assert manager.session_workspace_root() == ""  # a new conversation, a new folder

    manager.switch_session(first)
    assert manager.session_workspace_root() == "/gw/workspaces/one"


@pytest.mark.basic
def test_llm_manager_remove_message_drops_only_the_named_turn(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    keep_id = manager.append_message(role="user", content="keep")
    drop_id = manager.append_message(role="user", content="never started")
    assert manager.remove_message(drop_id) is True
    assert [m["message_id"] for m in manager.session_messages()] == [keep_id]
    assert manager.remove_message("missing") is False


@pytest.mark.basic
def test_controller_run_scope_prefers_local_root_then_session_root_then_nothing() -> None:
    controller = object.__new__(AssistantController)
    controller.preferences = AssistantPreferences()
    controller.llm_manager = SimpleNamespace(session_workspace_root=lambda: "/gw/workspaces/one")
    assert controller.run_scope()["workspace_root"] == "/gw/workspaces/one"
    assert controller.workspace_root_status() == {"root": "/gw/workspaces/one", "source": "session"}

    controller.preferences = AssistantPreferences(workspace_root="/Users/me/site")
    assert controller.run_scope()["workspace_root"] == "/Users/me/site"
    assert controller.workspace_root_status()["source"] == "local"

    controller.preferences = AssistantPreferences()
    controller.llm_manager = SimpleNamespace(session_workspace_root=lambda: "")
    assert controller.run_scope()["workspace_root"] == ""
    assert controller.workspace_root_status() == {"root": "", "source": "gateway"}


# --------------------------------------------------------------------------- worker


class _StartGateway:
    def __init__(self, *, fail: str = "", granted_root: str = "/gw/workspaces/minted") -> None:
        self.fail = fail
        self.granted_root = granted_root
        self.started: list[dict] = []

    def start_run(self, **kwargs) -> str:
        if self.fail:
            raise RuntimeError(self.fail)
        self.started.append(dict(kwargs))
        return "run-9"

    def get_run_input_data(self, *, run_id: str) -> dict:
        return {"run_id": run_id, "input_data": {"prompt": "x", "workspace_root": self.granted_root}}


class _LLM:
    def __init__(self) -> None:
        self.active_session_id = "sess-1"
        self.last_run_id = ""
        self.workspace_root = ""
        self.messages: list = []

    def append_message(self, **kwargs) -> str:
        self.messages.append(kwargs)
        return "mid"

    def set_last_run_id(self, run_id: str) -> None:
        self.last_run_id = run_id

    def set_session_workspace_root(self, root: str) -> None:
        self.workspace_root = root

    def session_messages(self) -> list:
        return []


def _worker(gateway, **extra) -> GatewayWorker:
    worker = GatewayWorker.__new__(GatewayWorker)
    worker._gateway = gateway
    worker._llm_manager = _LLM()
    worker._user_text = "write report.md"
    worker._attachments = []
    worker._system_prompt_extra = ""
    worker._allowed_tools = None
    worker._tool_policy = None
    worker._append_user_message = False
    worker._provider_override = ""
    worker._model_override = ""
    worker._base_url_override = ""
    worker._media_overrides = None
    worker._thinking = ""
    worker._speculation = None
    worker._workspace_root = extra.get("workspace_root", "")
    worker._workspace_access_mode = ""
    worker._workspace_allowed_paths = []
    worker._debug = False
    worker._attach_run_id = ""
    worker._primary_image_artifact = None
    worker._root_run_id = ""
    worker._follow_run_id = ""
    worker._final_observed = False
    worker._offline = False
    worker._stats_by_run = {}
    worker._run_activity_by_run = {}
    worker._output_artifact_candidates = []
    worker._seen_output_artifacts = set()
    worker._pending_tool_approval_wait = None
    worker._pending_ask_user_wait = None
    worker._tool_approval_event = threading.Event()
    worker._ask_user_event = threading.Event()
    worker.event_emitted = _Signal()
    worker.error_occurred = _Signal()
    worker.warning_occurred = _Signal()
    worker._resolve_entrypoint = lambda: {"flow_id": "chat", "bundle_id": "b", "bundle_version": "1", "registry_scope": "tenant_catalog"}
    worker._emit_run_activity = lambda **kwargs: None
    worker._seed_history_from_gateway = lambda **kwargs: None
    worker.isInterruptionRequested = lambda: True  # stop following immediately
    return worker


@pytest.mark.basic
def test_worker_start_failure_emits_run_start_failed_instead_of_a_fatal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _StartGateway(fail="start_run failed: workspace_allowed_paths entry escapes the gateway policy")
    worker = _worker(gateway)

    import abstractassistant.ui.gateway_worker as module

    class _Controller:
        def __init__(self, **kwargs) -> None:
            pass

    monkeypatch.setattr(module, "GatewayRunController", _Controller)
    worker.run()

    types = [e.get("type") for e in worker.event_emitted.items]
    assert "run_start_failed" in types
    failed = next(e for e in worker.event_emitted.items if e.get("type") == "run_start_failed")
    assert "escapes the gateway policy" in failed["error"]
    assert failed["prompt"] == "write report.md"
    assert worker.error_occurred.items == []  # not fatal: the palette restores the turn


@pytest.mark.basic
def test_worker_reads_back_the_granted_workspace_and_pins_it_to_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _StartGateway(granted_root="/gw/workspaces/minted")
    worker = _worker(gateway)

    import abstractassistant.ui.gateway_worker as module

    class _Controller:
        def __init__(self, **kwargs) -> None:
            pass

        def follow_run(self, **kwargs) -> None:
            return None

        def get_run_status(self, *, run_id: str) -> str:
            return "completed"

    monkeypatch.setattr(module, "GatewayRunController", _Controller)
    worker.run()

    assert worker._llm_manager.workspace_root == "/gw/workspaces/minted"
    ws = next(e for e in worker.event_emitted.items if e.get("type") == "workspace")
    assert ws == {"type": "workspace", "root": "/gw/workspaces/minted", "source": "gateway", "run_id": "run-9"}


@pytest.mark.basic
def test_worker_wait_answer_failure_is_a_warning_not_a_teardown() -> None:
    worker = _worker(_StartGateway())

    def _boom(**kwargs):
        raise RuntimeError("503 gateway busy")

    worker._submit_resume = _boom
    worker.submit_wait_response(run_id="run-9", wait_key="tool_calls:x", payload={"approved": True})
    # The submission thread is short-lived; join it through the module's thread list.
    import time

    deadline = time.time() + 2.0
    while time.time() < deadline and not worker.warning_occurred.items:
        time.sleep(0.02)
    assert worker.error_occurred.items == []
    assert worker.warning_occurred.items and "did not reach the gateway" in worker.warning_occurred.items[0]


# --------------------------------------------------------------------------- misc controller


@pytest.mark.basic
def test_system_prompt_for_run_keeps_the_workflow_persona_in_front_of_an_addendum() -> None:
    controller = object.__new__(AssistantController)
    assert controller.system_prompt_for_run("") == ""
    combined = controller.system_prompt_for_run("You are in a spoken voice conversation.")
    assert combined.startswith("You are AbstractAssistant")
    assert combined.rstrip().endswith("You are in a spoken voice conversation.")


@pytest.mark.basic
def test_save_tool_preference_updates_one_key(tmp_path: Path) -> None:
    from abstractassistant.preferences import PreferencesStore

    controller = object.__new__(AssistantController)
    controller.preferences_store = PreferencesStore(tmp_path / "preferences.json")
    controller.preferences = AssistantPreferences(tool_preferences={"read_file": "approve"})
    controller.voice_manager = SimpleNamespace(set_quality_preset=lambda preset: None)
    controller._cache_lock = threading.RLock()
    controller._cache_epoch = 0
    controller._workflow_cache = None
    controller._workflow_cache_at = 0.0
    controller._tool_inventory_cache = None
    controller._tool_inventory_cache_at = 0.0
    controller._workspace_policy_cache = None
    controller._workspace_policy_cache_at = 0.0
    controller._model_capabilities_cache = {}
    controller._route_map_cache = None
    controller._route_map_cache_at = 0.0

    controller.save_tool_preference("execute_command", "approve")
    controller.save_tool_preference("bogus", "maybe")  # ignored

    assert controller.preferences.tool_preferences == {"read_file": "approve", "execute_command": "approve"}


@pytest.mark.basic
def test_stt_model_is_pinned_only_when_the_user_chose_one(monkeypatch: pytest.MonkeyPatch) -> None:
    from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager

    manager = GatewayVoiceManager.__new__(GatewayVoiceManager)
    manager._llm_manager = SimpleNamespace(current_stt_model="", current_stt_provider="")
    manager._assistant_capabilities = lambda: SimpleNamespace(selected_stt_model=lambda: "large-v3")  # gateway default
    monkeypatch.delenv("ABSTRACTASSISTANT_GATEWAY_STT_MODEL", raising=False)
    monkeypatch.delenv("ABSTRACTASSISTANT_STT_MODEL", raising=False)
    assert manager._selected_stt_model() is None  # the gateway default is never echoed as a half-pin

    manager._llm_manager = SimpleNamespace(current_stt_model="whisper-small", current_stt_provider="faster-whisper")
    assert manager._selected_stt_model() == "whisper-small"


@pytest.mark.basic
def test_run_activity_summary_never_echoes_the_prompt() -> None:
    """The status line names the run state, not the user's own words (which
    the transcript already shows); the activity model takes over after the
    first event."""
    worker = _worker(_StartGateway())
    worker._gateway = SimpleNamespace(
        get_run=lambda run_id: {"status": "running"},
        get_run_input_data=lambda run_id: {"input_data": {"prompt": "write report.md"}},
    )
    summary = worker._build_run_activity_summary(run_id="run-1234567", fallback_prompt="write report.md")
    assert summary == "Running (234567)"
    assert "report.md" not in summary


@pytest.mark.basic
def test_reattaching_to_a_run_cancelled_before_the_relaunch() -> None:
    """Reopening the app on a run that was CANCELLED in a previous process.

    Two things went wrong on that screen, both visible in one screenshot: the
    banner said "The workflow completed, but it returned no written reply" for
    a run the user had stopped half an hour earlier, and the palette showed
    live run controls (Stop, pause) for a run that had already ended. The stop
    flag only knows about a cancel THIS process issued, and the reattach path
    announced every recovery as a run "in progress".
    """
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtWidgets import QApplication

    import abstractassistant.app as app_module

    QApplication.instance() or QApplication([])

    palette = app_module.AssistantPalette.__new__(app_module.AssistantPalette)
    recorded: list = []
    palette._set_status = lambda text="", **kw: recorded.append(("status", text))
    palette._set_history_status = lambda text="", **kw: recorded.append(("history", text))
    palette._refresh_tray_feedback = lambda *a, **k: None
    palette._clear_run_activity = lambda: None
    palette._invalidate_session_digests = lambda: None
    palette._show_thinking_indicator = lambda: False
    palette.refresh_history = lambda *a, **k: None
    palette._set_banner = lambda *a, **k: None
    palette._finish_activity = lambda outcome: recorded.append(("activity", outcome))
    palette._set_send_button_busy = lambda busy: recorded.append(("busy", bool(busy)))
    palette.sender = lambda: None
    palette._worker = None

    # --- the run reports how it ended, exactly as the worker emits it
    app_module.AssistantPalette._on_worker_event(
        palette, {"type": "status", "status": "cancelled"}
    )
    assert palette._last_run_status == "cancelled"

    # --- and the finish must say so, without this process having stopped it
    assert palette._cancel_requested is False
    palette._run_has_final_output = False
    app_module.AssistantPalette._on_worker_finished(palette)

    said = [text for kind, text in recorded if kind == "history"]
    assert "Run stopped." in said, said
    assert not any("returned no written reply" in t for t in said), said

    # --- a terminal run is recovered quietly: no busy send button, no
    #     "in progress" copy that implies it can still be steered or stopped
    recorded.clear()
    palette._worker = None
    palette._controller = SimpleNamespace(
        last_run_id=lambda: "run-x",
        build_attach_worker=lambda run_id: SimpleNamespace(
            event_emitted=_Signal(), error_occurred=_Signal(), finished=_Signal(),
            start=lambda: None,
        ),
    )
    for signal in ("event_emitted", "error_occurred", "finished"):
        pass
    worker = palette._controller.build_attach_worker("run-x")
    for name in ("event_emitted", "error_occurred", "finished"):
        getattr(worker, name).connect = lambda *a, **k: None
    palette._controller.build_attach_worker = lambda run_id: worker
    app_module.RunActivityModel  # the handler builds one

    app_module.AssistantPalette._on_reattach_candidate(
        palette, {"run_id": "run-x", "status": "cancelled"}
    )
    assert palette._run_busy is False, "a finished run must not present as busy"
    assert ("busy", False) in recorded, "the Stop button must not appear for a finished run"
    copy = [t for kind, t in recorded if kind in {"status", "history"}]
    assert not any("in progress" in t for t in copy), copy


@pytest.mark.basic
def test_a_run_parked_on_the_user_is_impossible_to_miss() -> None:
    """A run waiting on an approval had no persistent signal at all.

    One sat parked for 15m52s in complete silence: the approval event never
    reached the client, and nothing on screen or in the tray said the run was
    stopped and needed an answer. The dialog alone is not enough — it can be
    missed, deferred, or (as happened) never arrive.
    """
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtWidgets import QApplication

    import abstractassistant.app as app_module

    # Rendering a tray icon needs a QApplication, and something must HOLD it:
    # an unreferenced QApplication is collected and the next QPixmap aborts
    # the process.
    global _APP
    _APP = QApplication.instance() or QApplication([])

    class _Label:
        """Just enough of QLabel for `_set_banner`.

        Creating real widgets here aborts the process under the offscreen
        platform in this suite, and none of the behaviour under test needs
        one — the notice is text plus visibility.
        """

        def __init__(self) -> None:
            self._text = ""
            self._visible = False
            self.props: dict = {}

        def setText(self, text) -> None:  # noqa: N802 (Qt API)
            self._text = str(text)

        def text(self) -> str:
            return self._text

        def clear(self) -> None:
            self._text = ""

        def setMinimumHeight(self, _value) -> None:  # noqa: N802
            pass

        def setMaximumHeight(self, _value) -> None:  # noqa: N802
            pass

        def setProperty(self, key, value) -> None:  # noqa: N802
            self.props[key] = value

        def show(self) -> None:
            self._visible = True

        def hide(self) -> None:
            self._visible = False

        def isVisible(self) -> bool:  # noqa: N802
            return self._visible

    palette = app_module.AssistantPalette.__new__(app_module.AssistantPalette)
    palette.banner_label = _Label()
    palette._refresh_widget_style = lambda _w: None
    palette._voice_is_speaking = lambda: False
    palette._show_thinking_indicator = lambda: False
    palette._tray_completion_unread = False

    state = app_module.AssistantPalette._tray_feedback_state
    note = app_module.AssistantPalette._note_user_wait
    clear = app_module.AssistantPalette._clear_user_wait

    assert state(palette) == "idle"
    assert not palette.banner_label.isVisible()

    note(palette, wait_key="w1", kind="approval", label="execute_command")
    assert state(palette) == "waiting"
    said = palette.banner_label.text()
    assert "waiting for you to approve" in said and "execute_command" in said

    # "Waiting on you" outranks "working": working resolves itself, this
    # cannot until the user answers.
    palette._show_thinking_indicator = lambda: True
    assert state(palette) == "waiting"
    palette._show_thinking_indicator = lambda: False

    # A transient notice may cover it, but the tray never lies, and the notice
    # comes back when that transient one goes.
    app_module.AssistantPalette._set_banner(palette, "Speaking on a device", tone="info", key="speech")
    assert state(palette) == "waiting"
    app_module.AssistantPalette._clear_banner(palette, "speech")
    assert "waiting for you to approve" in palette.banner_label.text()

    # A second wait is counted; answering one leaves the other standing.
    note(palette, wait_key="w2", kind="ask", label="Which branch?")
    assert "2 pending" in palette.banner_label.text()
    clear(palette, "w1")
    assert state(palette) == "waiting"

    # Answering the last one puts everything back.
    clear(palette, "w2")
    assert state(palette) == "idle"
    assert not palette.banner_label.isVisible()

    # The badge must be its OWN picture, not a recoloured idle or busy disc.
    waiting = app_module._tray_feedback_icon(state="waiting").pixmap(44, 44).toImage()
    idle = app_module._tray_feedback_icon(state="idle").pixmap(44, 44).toImage()
    busy = app_module._tray_feedback_icon(state="busy").pixmap(44, 44).toImage()
    assert waiting != idle and waiting != busy
