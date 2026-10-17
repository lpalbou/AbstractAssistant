"""Hold to talk (operator 2026-10-17: "keep press to record; only one mic icon").

The composer's microphone button records while it is held and, on release,
transcribes through the gateway and SENDS the words — the Code TUI's
hold-Space principle. A tap records nothing. The hands-free voice
conversation keeps ⌘⇧V and the mic's right-click menu.
"""

from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager


class _FakeStream:
    """A sounddevice.InputStream stand-in that lets the test push audio."""

    instances: list = []

    def __init__(self, *, samplerate, channels, dtype, blocksize, callback):
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.blocksize = blocksize
        self.callback = callback
        self.started = False
        self.closed = False
        _FakeStream.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.closed = True

    def push(self, seconds: float, amplitude: int = 4000) -> None:
        n = int(self.samplerate * seconds)
        block = (np.sin(np.linspace(0, 200 * np.pi, n)) * amplitude).astype(np.int16).reshape(-1, 1)
        self.callback(block, n, None, None)


@pytest.fixture
def manager(monkeypatch):
    _FakeStream.instances.clear()
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(InputStream=_FakeStream))
    m = GatewayVoiceManager(llm_manager=SimpleNamespace())
    monkeypatch.setattr(m, "supports_stt", lambda: True)
    monkeypatch.setattr(m, "_default_stt_language", lambda: "en")
    return m


def _wait(event: threading.Event) -> None:
    assert event.wait(5.0), "the transcription callback did not fire"


@pytest.mark.basic
def test_hold_records_then_transcribes_and_reports_the_words(manager, monkeypatch) -> None:
    heard: list = []
    seen: dict = {}
    done = threading.Event()

    class Adapter:
        def transcribe_from_array(self, audio, sample_rate, language=None, **kw):
            seen["samples"] = int(audio.size)
            seen["rate"] = sample_rate
            seen["language"] = language
            seen["dtype"] = str(audio.dtype)
            return "  who are you  "

    monkeypatch.setattr(manager, "_make_stt_adapter", lambda: Adapter())
    levels: list = []
    assert manager.begin_hold(on_audio_level=levels.append) is True
    assert manager.is_holding()
    stream = _FakeStream.instances[-1]
    assert (stream.samplerate, stream.channels, stream.dtype) == (16000, 1, "int16")
    assert stream.started
    stream.push(0.5)
    manager._hold_started -= 1.0  # the user held for a second
    assert manager.end_hold(on_transcription=lambda t: (heard.append(t), done.set())) is True
    assert not manager.is_holding() and stream.closed
    _wait(done)
    assert heard == ["who are you"]
    assert seen == {"samples": 8000, "rate": 16000, "language": "en", "dtype": "float32"}
    assert levels and 0.0 < max(levels) <= 1.0


@pytest.mark.basic
def test_a_tap_is_dropped_without_transcribing(manager, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(manager, "_make_stt_adapter", lambda: calls.append("adapter"))
    manager.begin_hold()
    _FakeStream.instances[-1].push(0.05)
    assert manager.end_hold(on_transcription=lambda t: calls.append(t)) is False
    assert calls == [] and not manager.is_holding()
    # A long enough hold with (almost) no audio frames is a tap as well.
    manager.begin_hold()
    manager._hold_started -= 2.0
    assert manager.end_hold(on_transcription=lambda t: calls.append(t)) is False
    assert calls == []


@pytest.mark.basic
def test_transcription_errors_reach_on_error_not_the_words(manager, monkeypatch) -> None:
    done = threading.Event()
    errors: list = []
    heard: list = []

    class Adapter:
        def transcribe_from_array(self, *a, **k):
            raise RuntimeError("gateway said no")

    monkeypatch.setattr(manager, "_make_stt_adapter", lambda: Adapter())
    manager.begin_hold()
    _FakeStream.instances[-1].push(0.6)
    manager._hold_started -= 1.0
    assert manager.end_hold(on_transcription=heard.append, on_error=lambda m: (errors.append(m), done.set())) is True
    _wait(done)
    assert errors == ["gateway said no"] and heard == []


@pytest.mark.basic
def test_cancel_and_the_continuous_listener_share_the_microphone(manager, monkeypatch) -> None:
    stopped: list = []
    manager._listening = True
    monkeypatch.setattr(manager, "stop_listening", lambda: (stopped.append(True), setattr(manager, "_listening", False)))
    manager.begin_hold()
    assert stopped == [True], "a hold stops the continuous recognizer first"
    manager.cancel_hold()
    assert not manager.is_holding() and _FakeStream.instances[-1].closed
    assert manager.end_hold(on_transcription=lambda t: None) is False


@pytest.mark.basic
def test_microphone_failure_is_a_runtime_error(manager, monkeypatch) -> None:
    class Broken:
        def __init__(self, **kw):
            raise OSError("no input device")

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(InputStream=Broken))
    with pytest.raises(RuntimeError, match="Microphone unavailable: no input device"):
        manager.begin_hold()
    assert not manager.is_holding()


# --------------------------------------------------------------- the palette's flow


class _Button:
    def __init__(self) -> None:
        self.checked: list = []
        self.tooltips: list = []

    def setChecked(self, value: bool) -> None:
        self.checked.append(bool(value))

    def setToolTip(self, text: str) -> None:
        self.tooltips.append(str(text))


class _Manager:
    def __init__(self, *, holding_after_begin: bool = True, end_result: bool = True) -> None:
        self.holding = False
        self.holding_after_begin = holding_after_begin
        self.end_result = end_result
        self.begin_calls = 0
        self.end_callbacks: dict = {}

    def begin_hold(self, on_audio_level=None):
        self.begin_calls += 1
        self.holding = self.holding_after_begin
        return True

    def is_holding(self):
        return self.holding

    def end_hold(self, on_transcription, on_error=None):
        self.holding = False
        self.end_callbacks = {"on_transcription": on_transcription, "on_error": on_error}
        return self.end_result

    def cancel_hold(self):
        self.holding = False


def _palette(manager: _Manager, *, conversation_active: bool = False):
    from abstractassistant.app import AssistantPalette

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._controller = SimpleNamespace(voice_manager=manager)
    palette._listening = False
    palette.mic_button = _Button()
    palette.statuses: list = []
    palette.sent: list = []
    palette.draft = ""
    state = {"_voice_conversation_active": conversation_active}
    palette._state = lambda key, default=None: state.get(key, default)
    palette._set_status = lambda text, tone="neutral": palette.statuses.append((text, tone))
    palette._append_prompt_text = lambda text: setattr(palette, "draft", f"{palette.draft} {text}".strip())
    palette._submit = lambda: palette.sent.append(palette.draft)
    palette._toggle_listening = lambda: setattr(palette, "_listening", False)
    palette.voice_level_received = SimpleNamespace(emit=lambda level: None)
    palette.hold_transcription_received = SimpleNamespace(emit=lambda text: AssistantPalette._on_hold_transcription(palette, text))
    palette.hold_transcription_failed = SimpleNamespace(emit=lambda msg: AssistantPalette._on_hold_transcription_failed(palette, msg))
    return palette, AssistantPalette


@pytest.mark.basic
def test_press_records_release_sends_the_words() -> None:
    manager = _Manager()
    palette, P = _palette(manager)
    P._begin_hold_to_talk(palette)
    assert manager.begin_calls == 1
    assert palette.mic_button.checked == [True]
    assert palette.statuses[-1] == ("Listening — release to send", "busy")
    P._end_hold_to_talk(palette)
    assert palette.mic_button.checked[-1] is False
    assert palette.statuses[-1] == ("Transcribing…", "busy")
    manager.end_callbacks["on_transcription"]("who are you")
    assert palette.sent == ["who are you"]
    assert palette.statuses[-1] == ("Ready", "neutral")


@pytest.mark.basic
def test_the_words_join_a_draft_and_go_out_together() -> None:
    manager = _Manager()
    palette, P = _palette(manager)
    palette.draft = "Please answer in French:"
    P._begin_hold_to_talk(palette)
    P._end_hold_to_talk(palette)
    manager.end_callbacks["on_transcription"]("who are you")
    assert palette.sent == ["Please answer in French: who are you"]


@pytest.mark.basic
def test_a_tap_sends_nothing_and_says_how_to_hold() -> None:
    manager = _Manager(end_result=False)
    palette, P = _palette(manager)
    P._begin_hold_to_talk(palette)
    P._end_hold_to_talk(palette)
    assert palette.sent == []
    assert palette.statuses[-1] == ("Hold the microphone button while you speak", "info")


@pytest.mark.basic
def test_empty_transcripts_and_failures_are_said_not_sent() -> None:
    manager = _Manager()
    palette, P = _palette(manager)
    P._begin_hold_to_talk(palette)
    P._end_hold_to_talk(palette)
    manager.end_callbacks["on_transcription"]("   ")
    assert palette.sent == [] and palette.statuses[-1] == ("Nothing was heard", "info")
    P._begin_hold_to_talk(palette)
    P._end_hold_to_talk(palette)
    manager.end_callbacks["on_error"]("gateway said no")
    assert palette.sent == [] and palette.statuses[-1] == ("Transcription failed: gateway said no", "error")


@pytest.mark.basic
def test_no_hold_during_a_voice_conversation_and_a_release_without_a_hold_is_quiet() -> None:
    manager = _Manager()
    palette, P = _palette(manager, conversation_active=True)
    P._begin_hold_to_talk(palette)
    assert manager.begin_calls == 0 and palette.statuses == []
    palette, P = _palette(_Manager(holding_after_begin=False))
    P._end_hold_to_talk(palette)
    assert palette.statuses == [] and palette.sent == []


@pytest.mark.basic
def test_microphone_failure_is_reported_in_the_status_line() -> None:
    class Failing(_Manager):
        def begin_hold(self, on_audio_level=None):
            raise RuntimeError("Microphone unavailable: no input device")

    palette, P = _palette(Failing())
    P._begin_hold_to_talk(palette)
    assert palette.mic_button.checked == [False]
    assert palette.statuses[-1] == ("Microphone unavailable: Microphone unavailable: no input device", "error")


@pytest.mark.basic
def test_the_composer_has_one_mic_and_the_conversation_button_is_hidden() -> None:
    """The source of truth: the composer row adds the mic, hides the conversation toggle."""
    import inspect

    from abstractassistant import app as app_module

    src = inspect.getsource(app_module.AssistantPalette)
    assert "self.mic_button.pressed.connect(self._begin_hold_to_talk)" in src
    assert "self.mic_button.released.connect(self._end_hold_to_talk)" in src
    assert "self.conversation_button.hide()" in src
    assert "composer.addWidget(self.conversation_button)" not in src
    assert "self.mic_button.clicked.connect(self._toggle_listening)" not in src
