"""Construct the REAL AssistantPalette headless with a stub controller.

Most palette tests build the window via ``__new__`` and poke one method; this
suite exercises ``__init__`` end to end (header status sink, composer voice
strip, hands-free conversation start/stop) so wiring mistakes surface here
instead of at first launch.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

from PyQt5.QtWidgets import QApplication

from abstractassistant.app import AssistantPalette
from abstractassistant.preferences import AssistantPreferences, GatewayConnectionPreferences


_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class _Voice:
    def __init__(self) -> None:
        self.on_speech_start = None
        self.on_speech_error = None
        self.mode = ""
        self.listening = False
        self.spoken: list[str] = []

    def supports_tts(self) -> bool:
        return True

    def supports_stt(self) -> bool:
        return True

    def is_speaking(self) -> bool:
        return False

    def is_paused(self) -> bool:
        return False

    def set_voice_mode(self, mode: str) -> None:
        self.mode = mode

    def set_audio_meter_callback(self, cb) -> None:
        self.meter = cb

    def listen(self, **kwargs) -> bool:
        self.listening = True
        return True

    def stop_listening(self) -> None:
        self.listening = False

    def stop_speaking(self) -> None:
        pass

    def pause_listening(self) -> bool:
        return True

    def resume_listening(self) -> bool:
        return True

    def speak(self, text: str, callback=None) -> bool:
        self.spoken.append(text)
        return True

    def set_quality_preset(self, preset: str) -> None:
        pass


class _Store:
    def __init__(self, prefs: AssistantPreferences) -> None:
        self._prefs = prefs

    def load(self) -> AssistantPreferences:
        return self._prefs

    def save(self, prefs: AssistantPreferences) -> None:
        self._prefs = prefs


class _Controller:
    def __init__(self) -> None:
        self.preferences = AssistantPreferences(hotkey_enabled=False, window_width=520, window_height=420)
        self.preferences_store = _Store(self.preferences)
        self.voice_manager = _Voice()
        self.connection = GatewayConnectionPreferences()
        self.active_session_id = "sess-1"
        self.built: list[dict] = []

    # --- used by __init__ / refreshes
    def prefetch(self) -> None:
        return None

    def probe_reattach_candidate(self, **kwargs):
        return None

    def session_messages(self) -> list:
        return []

    def list_sessions(self) -> list:
        return [{"session_id": "sess-1", "title": "Smoke", "created_at": "", "updated_at": ""}]

    def connection_status(self) -> dict:
        return {"ok": True, "principal": {"user_id": "admin"}, "auth": {"mode": "users"}, "routing": {}}

    def supports_tts(self) -> bool:
        return True

    def supports_stt(self) -> bool:
        return True

    def workflow_options(self) -> list:
        return [SimpleNamespace(bundle_id="b", flow_id="f", bundle_version="1", registry_scope="tenant_catalog")]

    def workflow_status(self):
        return SimpleNamespace(error="")

    def current_workflow(self):
        return SimpleNamespace(bundle_id="b", flow_id="f", bundle_version="1", registry_scope="tenant_catalog")

    def workspace_root_status(self) -> dict:
        return {"root": "", "source": "gateway"}

    def last_run_id(self) -> str:
        return ""

    def save_preferences(self, prefs) -> None:
        self.preferences = prefs

    def update_preferences(self, **updates):
        payload = self.preferences.to_dict()
        payload.update(updates)
        self.preferences = AssistantPreferences.from_dict(payload)
        return self.preferences

    def submission_plan(self, **kwargs) -> dict:
        return {"ready": True, "system_prompt_extra": ""}

    def append_user_message(self, content: str, metadata=None) -> str:
        return "mid-1"

    def remove_message(self, message_id: str) -> bool:
        return True

    def build_chat_worker(self, **kwargs):
        self.built.append(dict(kwargs))
        raise RuntimeError("no gateway in the smoke test")


def _wait_for_bootstrap(window, *, timeout_s: float = 3.0) -> None:
    """The bootstrap thread emits `bootstrap_ready` asynchronously; let it
    land before a test pokes state it would refresh."""
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline and window.__dict__.get("_bootstrapping", True):
        _app().processEvents()
        time.sleep(0.01)
    _app().processEvents()


@pytest.fixture
def palette():
    _app()
    controller = _Controller()
    window = AssistantPalette(controller=controller, debug=False)
    _wait_for_bootstrap(window)
    yield window, controller
    try:
        window.shutdown()
    except Exception:
        pass
    window.deleteLater()
    _app().processEvents()


@pytest.mark.basic
def test_sending_interrupts_reply_audio_and_clears_its_card(palette, monkeypatch):
    window, controller = palette
    events = []
    monkeypatch.setattr(controller.voice_manager, "stop_speaking", lambda: events.append("stop"))
    monkeypatch.setattr(controller, "append_user_message", lambda *a, **kw: events.append("send") or "new")
    monkeypatch.setattr(window, "_set_message_voice_card_state", lambda key, state: events.append((key, state)))
    window._active_spoken_message_key = "old"
    window._active_spoken_message_phase = "synthesizing"
    window.prompt_edit.setPlainText("Anything about AI?")
    window._submit()
    assert events.index("stop") < events.index("send")
    assert ("old", "idle") in events
    assert window._active_spoken_message_key == ""
    assert window._active_spoken_message_phase == "idle"


@pytest.mark.basic
def test_palette_builds_and_title_is_the_status_sink(palette) -> None:
    window, _controller = palette
    assert window.title_label.text() == "AbstractAssistant"
    window._set_status("Thinking…", tone="busy")
    assert window.title_label.text() == "Thinking…"
    assert window.title_label.property("tone") == "busy"
    window._set_status("Ready")
    assert window.title_label.text() == "AbstractAssistant"
    assert window.title_label.property("tone") == "idle"


@pytest.mark.basic
def test_palette_voice_conversation_starts_listens_and_ends(palette) -> None:
    window, controller = palette
    assert window.voice_strip.isHidden()
    assert window.conversation_button.isEnabled()

    window._start_voice_conversation()
    _app().processEvents()
    assert window._voice_conversation_active is True
    assert window._voice_conversation.state == "listening"
    assert controller.voice_manager.mode == "wait"
    assert controller.voice_manager.listening is True
    assert not window.voice_strip.isHidden()
    assert window.voice_strip.state == "listening"
    assert window.conversation_button.isChecked()
    assert not window.mic_button.isEnabled()
    assert window.title_label.text() == "Listening"
    # The spoken-style addendum only applies while the conversation runs.
    assert "spoken voice conversation" in window._voice_system_prompt()

    window._end_voice_conversation()
    _app().processEvents()
    assert window._voice_conversation_active is False
    assert window.voice_strip.isHidden()
    assert not window.conversation_button.isChecked()
    assert window.mic_button.isEnabled()
    assert controller.voice_manager.listening is False
    assert window._voice_system_prompt() == ""


@pytest.mark.basic
def test_palette_voice_send_routes_through_submit_with_the_addendum(palette) -> None:
    window, controller = palette
    window._start_voice_conversation()
    _app().processEvents()

    window._voice_conversation.heard("what time is it")
    # The debounce timer would fire ~0.8 s later; flush it explicitly here.
    window._voice_conversation.send_now()
    _app().processEvents()

    # build_chat_worker was reached with the voice addendum (and raised, so
    # the loop went back to listening instead of wedging in "thinking").
    assert controller.built and "spoken voice conversation" in controller.built[-1]["system_prompt_extra"]
    assert window._voice_conversation.state == "listening"
    window._end_voice_conversation()


@pytest.mark.basic
def test_palette_run_start_failed_restores_the_turn(palette) -> None:
    window, _controller = palette
    window._pending_user_message_id = "mid-1"
    window._pending_submission = {"prompt": "write report.md", "attachments": []}
    window._run_busy = True
    window._run_has_final_output = False
    window.prompt_edit.clear()

    window._on_worker_event(
        {"type": "run_start_failed", "error": "workspace_allowed_paths entry escapes the gateway policy", "prompt": "write report.md"}
    )
    _app().processEvents()

    assert window.prompt_edit.toPlainText() == "write report.md"
    assert window._run_busy is False
    assert "Not sent" in window.banner_label.text()
    assert window.title_label.text() == "Not sent"


@pytest.mark.basic
def test_palette_auto_speak_toggle_during_a_conversation_ends_it_and_keeps_the_choice(palette) -> None:
    window, controller = palette
    controller.preferences = controller.update_preferences(auto_speak=False)
    window.auto_speak.setChecked(False)
    window._start_voice_conversation()
    _app().processEvents()
    assert window.auto_speak.isChecked() is False  # forced ON internally, the button reflects the saved value

    # The user turns the speaker on while talking: the conversation ends and the
    # new choice survives (the pre-conversation value is not restored over it).
    window.auto_speak.setChecked(True)
    window._persist_auto_speak()
    _app().processEvents()
    assert window._voice_conversation_active is False
    assert window.auto_speak.isChecked() is True
    assert controller.preferences.auto_speak is True
