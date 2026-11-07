"""The voice turn's recording ends by itself (0.18.2): about one second of
silence after speech, or nothing said in time — like the Apple Watch's orb.

The pure rule (`UtteranceEndpoint`) and the voice manager's use of it in
`begin_hold(on_utterance_end=…)`, with a fake microphone and a fake
voice-activity detector (loud frames are speech), so nothing touches a real
device or the gateway.
"""

from __future__ import annotations

import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager
from abstractassistant.core.utterance_endpoint import UtteranceEndpoint


# --------------------------------------------------------------------------- the rule


def _feed(endpoint: UtteranceEndpoint, frames: list[bool]):
    reasons = [endpoint.push(f) for f in frames]
    return [r for r in reasons if r is not None]


@pytest.mark.basic
def test_about_one_second_of_silence_after_speech_ends_the_utterance() -> None:
    endpoint = UtteranceEndpoint(frame_ms=30)
    assert _feed(endpoint, [True] * 20) == []  # 0.6 s of speech
    assert endpoint.heard
    assert _feed(endpoint, [False] * 33) == []  # 0.99 s: not yet
    assert _feed(endpoint, [False]) == ["silence"]  # 1.02 s
    assert endpoint.ended == "silence"
    assert _feed(endpoint, [True, False] * 50) == []  # once ended, it stays ended


@pytest.mark.basic
def test_a_pause_shorter_than_the_silence_keeps_the_utterance_going() -> None:
    endpoint = UtteranceEndpoint(frame_ms=30)
    assert _feed(endpoint, [True] * 20 + [False] * 25 + [True] * 10 + [False] * 33) == []
    assert endpoint.ended is None


@pytest.mark.basic
def test_nothing_said_ends_the_turn_with_nothing_heard() -> None:
    endpoint = UtteranceEndpoint(frame_ms=30, wait_for_speech_s=5.0)
    frames = [False] * (5000 // 30 + 1)
    assert _feed(endpoint, frames) == ["no_speech"]
    assert not endpoint.heard


@pytest.mark.basic
def test_a_click_or_a_cough_is_not_speech_but_restarts_the_wait() -> None:
    endpoint = UtteranceEndpoint(frame_ms=30, min_speech_ms=300, wait_for_speech_s=1.0)
    assert _feed(endpoint, [False] * 30 + [True] * 4) == []  # 120 ms burst
    assert not endpoint.heard
    assert _feed(endpoint, [False] * 32) == []  # the wait restarted at the burst
    assert _feed(endpoint, [False]) == ["no_speech"]


@pytest.mark.basic
def test_the_longest_utterance_ends_the_turn() -> None:
    endpoint = UtteranceEndpoint(frame_ms=30, max_s=1.2)
    assert _feed(endpoint, [True] * 40) == ["max_duration"]
    assert endpoint.heard


# --------------------------------------------------------------------------- the manager


class _FakeStream:
    instances: list = []

    def __init__(self, *, samplerate, channels, dtype, blocksize, callback):
        self.samplerate = samplerate
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

    def frames(self, count: int, *, loud: bool) -> None:
        for _ in range(count):
            n = self.blocksize
            amplitude = 6000 if loud else 30
            block = (np.sin(np.linspace(0, 40 * np.pi, n)) * amplitude).astype(np.int16).reshape(-1, 1)
            self.callback(block, n, None, None)


class _LoudIsSpeech:
    """Stands in for webrtcvad: a loud frame is speech."""

    def __init__(self, aggressiveness=1, sample_rate=16000, debug_mode=False):
        assert sample_rate == 16000

    def is_speech(self, frame: bytes) -> bool:
        samples = np.frombuffer(frame, dtype=np.int16)
        return bool(samples.size and np.abs(samples).max() > 1000)


@pytest.fixture
def manager(monkeypatch):
    import abstractvoice.vad as vad

    _FakeStream.instances.clear()
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(InputStream=_FakeStream))
    monkeypatch.setattr(vad, "VoiceDetector", _LoudIsSpeech)
    m = GatewayVoiceManager(llm_manager=SimpleNamespace())
    monkeypatch.setattr(m, "supports_stt", lambda: True)
    monkeypatch.setattr(m, "_default_stt_language", lambda: "en")
    return m


@pytest.mark.basic
def test_silence_after_speech_ends_the_recording_once_and_later_audio_is_not_kept(manager, monkeypatch) -> None:
    ended: list = []
    levels: list = []
    assert manager.begin_hold(on_audio_level=levels.append, on_utterance_end=ended.append) is True
    stream = _FakeStream.instances[-1]
    assert stream.blocksize == 480  # 30 ms frames, what the detector expects
    stream.frames(10, loud=False)
    assert not manager.hold_heard_speech()
    stream.frames(20, loud=True)
    assert manager.hold_heard_speech()
    stream.frames(34, loud=False)
    assert ended == ["silence"]
    kept = sum(int(c.size) for c in manager._hold_chunks)
    stream.frames(50, loud=True)  # the room after the turn: never recorded, never re-ended
    assert ended == ["silence"]
    assert sum(int(c.size) for c in manager._hold_chunks) == kept
    assert levels and max(levels) > 0.15

    words: list = []
    done = threading.Event()

    class Adapter:
        def transcribe_from_array(self, audio, sample_rate, language=None, **kw):
            return "what is the weather"

    monkeypatch.setattr(manager, "_make_stt_adapter", lambda: Adapter())
    manager._hold_started -= 2.0  # the frames above took two seconds of real time
    assert manager.end_hold(on_transcription=lambda t: (words.append(t), done.set())) is True
    assert done.wait(5.0)
    assert words == ["what is the weather"]
    assert stream.closed and not manager.hold_heard_speech()


@pytest.mark.basic
def test_a_quiet_room_ends_the_recording_with_nothing_heard(manager) -> None:
    ended: list = []
    manager.begin_hold(on_utterance_end=ended.append)
    stream = _FakeStream.instances[-1]
    stream.frames(5000 // 30 + 1, loud=False)
    assert ended == ["no_speech"]
    assert not manager.hold_heard_speech()
    manager.cancel_hold()
    assert stream.closed


@pytest.mark.basic
def test_a_plain_hold_has_no_endpoint(manager) -> None:
    """Hold to talk keeps its rule: the release, not a silence, ends it."""
    manager.begin_hold()
    stream = _FakeStream.instances[-1]
    stream.frames(5000 // 30 + 40, loud=False)
    assert manager.is_holding()
    assert not manager.hold_heard_speech()
    manager.cancel_hold()
