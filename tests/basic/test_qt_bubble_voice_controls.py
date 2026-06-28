"""Qt bubble voice-control regressions."""

from __future__ import annotations

import pytest
import time

from abstractassistant.ui import qt_bubble
from abstractassistant.ui.qt_bubble import QtChatBubble


class _ComboStub:
    def __init__(self, value: str) -> None:
        self.value = value

    def itemData(self, _index: int):
        return self.value


class _RunStateStub:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def set_speaking(self, value: bool) -> None:
        self.log.append(f"speaking:{bool(value)}")


class _VoiceStub:
    def __init__(self, log: list[str], *, on_stop=None) -> None:
        self.log = log
        self.on_stop = on_stop

    def stop(self) -> None:
        self.log.append("stop")
        if self.on_stop:
            self.on_stop()


class _SpeakingVoiceStub(_VoiceStub):
    def get_state(self) -> str:
        return "speaking"

    def is_speaking(self) -> bool:
        return True

    def pause(self) -> bool:
        self.log.append("pause")
        return True


class _PausedVoiceStub(_VoiceStub):
    def get_state(self) -> str:
        return "paused"

    def is_paused(self) -> bool:
        return True


class _ToggleStub:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.checked = False

    def blockSignals(self, value: bool) -> bool:
        self.log.append(f"block:{bool(value)}")
        return False

    def set_enabled(self, value: bool) -> None:
        self.checked = bool(value)
        self.log.append(f"toggle:{bool(value)}")


class _ManagerStub:
    def __init__(self, log: list[str]) -> None:
        self.active_session_id = "sess_old"
        self.log = log

    def switch_session(self, session_id: str) -> None:
        self.log.append(f"switch:{session_id}")
        self.active_session_id = session_id

    def create_new_session(self) -> str:
        self.log.append("create")
        self.active_session_id = "sess_new"
        return "sess_new"

    def refresh(self) -> None:
        self.log.append("refresh")


class _ScrollBarStub:
    def __init__(self, value: int = 42, maximum: int = 100) -> None:
        self._value = value
        self._maximum = maximum
        self.set_values: list[int] = []

    def value(self) -> int:
        return self._value

    def maximum(self) -> int:
        return self._maximum

    def setValue(self, value: int) -> None:
        self._value = int(value)
        self.set_values.append(int(value))


class _ScrollAreaStub:
    def __init__(self, bar: _ScrollBarStub) -> None:
        self._bar = bar

    def verticalScrollBar(self) -> _ScrollBarStub:
        return self._bar


class _HistoryDialogStub:
    def __init__(self, bar: _ScrollBarStub) -> None:
        self.scroll_area = _ScrollAreaStub(bar)
        self.refresh_calls: list[list[dict]] = []
        self.update_calls: list[list[dict]] = []

    def isVisible(self) -> bool:
        return True

    def refresh_messages(self, message_history: list[dict]) -> None:
        self.refresh_calls.append(list(message_history))

    def update_message_history(self, message_history: list[dict]) -> None:
        self.update_calls.append(list(message_history))


def _bubble(log: list[str]) -> QtChatBubble:
    bubble = QtChatBubble.__new__(QtChatBubble)
    bubble.debug = False
    bubble.use_gateway = False
    bubble.llm_manager = _ManagerStub(log)
    bubble.voice_manager = _VoiceStub(log)
    bubble._run_state = _RunStateStub(log)
    bubble.session_combo = _ComboStub("sess_new")
    bubble.history_dialog = None
    bubble._suppress_history_updates_until = 0.0
    bubble.attached_files = []
    bubble.message_file_attachments = {}
    bubble._update_tts_toggle_state = lambda: log.append("tts_state")
    bubble._save_tool_prefs_for_session = lambda _sid=None: log.append("save_prefs")
    bubble._load_tool_prefs_for_session = lambda _sid=None: log.append("load_prefs")
    bubble._refresh_tool_inventory = lambda: log.append("refresh_tools")
    bubble.update_attached_files_display = lambda: log.append("attachments")
    bubble._update_message_history_from_session = lambda: log.append("history")
    bubble._update_token_count_from_session = lambda: log.append("tokens")
    bubble._rebuild_chat_display = lambda: log.append("rebuild")
    bubble._reload_session_combo = lambda **_kwargs: log.append("reload")
    bubble._show_info = lambda *_args, **_kwargs: log.append("info")
    bubble._show_warning = lambda *_args, **_kwargs: log.append("warning")
    return bubble


@pytest.mark.basic
def test_switch_session_stops_voice_before_switching() -> None:
    log: list[str] = []
    bubble = _bubble(log)

    QtChatBubble._on_session_combo_changed(bubble, 0)

    assert "stop" in log
    assert "switch:sess_new" in log
    assert log.index("stop") < log.index("switch:sess_new")


@pytest.mark.basic
def test_new_session_stops_voice_before_creating_session() -> None:
    log: list[str] = []
    bubble = _bubble(log)

    QtChatBubble._start_new_session(bubble)

    assert "stop" in log
    assert "create" in log
    assert log.index("stop") < log.index("create")


@pytest.mark.basic
def test_tts_toggle_preserves_visible_history_scroll(monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[str] = []
    bar = _ScrollBarStub(value=42, maximum=100)
    bubble = _bubble(log)
    bubble.history_dialog = _HistoryDialogStub(bar)
    bubble.tts_enabled = True
    bubble.voice_manager = _VoiceStub(log, on_stop=lambda: bar.setValue(bar.maximum()))
    bubble.llm_manager.update_session_mode = lambda tts_mode=False: log.append(f"mode:{bool(tts_mode)}")

    monkeypatch.setattr(qt_bubble.QTimer, "singleShot", lambda _delay, callback: callback())

    QtChatBubble.on_tts_toggled(bubble, False)

    assert bar.value() == 42
    assert bar.set_values[-1] == 42


@pytest.mark.basic
def test_tts_toggle_click_pauses_speaking_without_disabling_or_scrolling(monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[str] = []
    bar = _ScrollBarStub(value=37, maximum=100)
    bubble = _bubble(log)
    bubble.history_dialog = _HistoryDialogStub(bar)
    bubble.tts_enabled = True
    bubble.voice_manager = _SpeakingVoiceStub(log, on_stop=lambda: bar.setValue(bar.maximum()))
    bubble.tts_toggle = _ToggleStub(log)
    bubble.llm_manager.update_session_mode = lambda tts_mode=False: log.append(f"mode:{bool(tts_mode)}")

    monkeypatch.setattr(qt_bubble.QTimer, "singleShot", lambda _delay, callback: callback())

    QtChatBubble.on_tts_toggled(bubble, False)

    assert "pause" in log
    assert "stop" not in log
    assert "mode:False" not in log
    assert bubble.tts_enabled is True
    assert bubble.tts_toggle.checked is True
    assert bar.value() == 37


@pytest.mark.basic
def test_manual_voice_control_suppresses_visible_history_refresh() -> None:
    bar = _ScrollBarStub(value=12, maximum=100)
    history = _HistoryDialogStub(bar)
    bubble = QtChatBubble.__new__(QtChatBubble)
    bubble.debug = False
    bubble.history_dialog = history
    bubble.message_history = [{"type": "assistant", "content": "answer"}]
    bubble._suppress_history_updates_until = time.monotonic() + 10.0

    QtChatBubble._rebuild_chat_display(bubble)

    assert history.refresh_calls == []


@pytest.mark.basic
def test_manual_voice_control_suppresses_auto_history_show() -> None:
    log: list[str] = []
    bubble = QtChatBubble.__new__(QtChatBubble)
    bubble.debug = False
    bubble._suppress_history_updates_until = time.monotonic() + 10.0
    bubble._is_voice_mode_active = lambda: False
    bubble.show_history = lambda _checked=True: log.append("show")
    bubble.history_button = None

    QtChatBubble._show_history_if_voice_mode_off(bubble)

    assert log == []


@pytest.mark.basic
def test_manual_voice_control_ignores_late_speech_end_callback() -> None:
    log: list[str] = []
    callbacks: list[str] = []
    bubble = QtChatBubble.__new__(QtChatBubble)
    bubble.debug = False
    bubble._suppress_history_updates_until = time.monotonic() + 10.0
    bubble.response_callback = callbacks.append
    bubble._pending_response = "answer"
    bubble._update_tts_toggle_state = lambda: log.append("tts_state")
    bubble.tts_toggle = _ToggleStub(log)
    bubble._run_state = _RunStateStub(log)
    bubble._is_full_voice_running = lambda: False

    QtChatBubble._on_speech_ended_main_thread(bubble)

    assert callbacks == []
    assert hasattr(bubble, "_pending_response")
    assert "tts_state" not in log
    assert "speaking:False" not in log


@pytest.mark.basic
def test_paused_voice_state_ignores_speech_end_callback_after_suppression_window() -> None:
    log: list[str] = []
    callbacks: list[str] = []
    bubble = QtChatBubble.__new__(QtChatBubble)
    bubble.debug = False
    bubble._suppress_history_updates_until = 0.0
    bubble.voice_manager = _PausedVoiceStub(log)
    bubble.response_callback = callbacks.append
    bubble._pending_response = "answer"
    bubble._update_tts_toggle_state = lambda: log.append("tts_state")
    bubble.tts_toggle = _ToggleStub(log)
    bubble._run_state = _RunStateStub(log)
    bubble._is_full_voice_running = lambda: False

    QtChatBubble._on_speech_ended_main_thread(bubble)

    assert callbacks == []
    assert hasattr(bubble, "_pending_response")
    assert "tts_state" not in log
    assert "speaking:False" not in log


@pytest.mark.basic
def test_speech_end_callback_emits_pending_response_when_not_suppressed() -> None:
    log: list[str] = []
    callbacks: list[str] = []
    bubble = QtChatBubble.__new__(QtChatBubble)
    bubble.debug = False
    bubble._suppress_history_updates_until = 0.0
    bubble.response_callback = callbacks.append
    bubble._pending_response = "answer"
    bubble._update_tts_toggle_state = lambda: log.append("tts_state")
    bubble.tts_toggle = _ToggleStub(log)
    bubble._run_state = _RunStateStub(log)
    bubble._is_full_voice_running = lambda: False

    QtChatBubble._on_speech_ended_main_thread(bubble)

    assert callbacks == ["answer"]
    assert "_pending_response" not in vars(bubble)
    assert "tts_state" in log
    assert "speaking:False" in log
