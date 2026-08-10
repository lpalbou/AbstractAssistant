"""Streaming-TTS latency contract.

These guard the mechanism behind the operator report "for long answers it
computes the whole voice instead of streaming" (measured live 2026-08-02):

  the client echoed the gateway's ADVERTISED `active_model` back as a request
  pin without a provider; /voice/tts/stream rejected that half-pin with a 404
  BEFORE any audio, and the client silently degraded to the single-shot
  artifact lane, which cannot emit a sample until the LAST one is synthesized
  (TTFV 3.3 s @200 chars, 17.5 s @1k, 46.8 s @5k, and no audio at all @15k —
  the artifact request hit its 120 s timeout). With the pin dropped, the same
  texts stream first audio in 0.65-0.97 s, flat in length.

Contract, in order of defence:
  1. never pin the gateway's own advertised default (only a user/env choice),
  2. a pre-audio stream rejection retries the stream UNPINNED before conceding,
  3. choosing the artifact lane for a long text is never silent,
  4. playback starts on the FIRST chunk and stays ordered.
"""

from __future__ import annotations

import base64
import io
import threading
import time
import wave
from types import SimpleNamespace

import pytest

from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager


def _wav_bytes(*, frames: int = 240, value: int = 0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(int(value).to_bytes(2, "little", signed=True) * frames)
    return buf.getvalue()


def _wait_for(predicate, *, timeout_s: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


class _StreamingGateway:
    """Gateway advertising streaming TTS with an advertised active_model."""

    def __init__(self, *, chunk_frames: tuple[int, ...] = (240,)) -> None:
        self._cfg = SimpleNamespace(timeout_s=30.0)
        self.chunk_frames = tuple(chunk_frames)
        self.stream_calls: list[dict] = []
        self.artifact_calls: list[dict] = []
        self.stream_done = threading.Event()
        self.release_done = threading.Event()
        self.release_done.set()

    def discovery_capabilities(self):
        return {
            "capabilities": {
                "contracts": {
                    "version": 1,
                    "assistant": {
                        "voice": {
                            "tts": {
                                "available": True,
                                "formats": ["wav"],
                                "active_model": "advertised-default-model",
                                "streaming": True,
                                "delivery_modes": ["artifact", "stream"],
                                "stream_endpoint": "/api/gateway/runs/{run_id}/voice/tts/stream",
                                "stream_transport": "jsonl",
                            },
                            "stt": {"available": False},
                        }
                    },
                }
            }
        }

    def voice_tts_stream(self, *, run_id, text, provider=None, voice=None, fmt=None,
                         request_id=None, model=None, profile=None, quality_preset=None,
                         timeout_s=None):
        self.stream_calls.append({"provider": provider, "voice": voice, "profile": profile,
                                  "model": model, "fmt": fmt})
        yield {"type": "runtime_start", "ok": True}
        for i, frames in enumerate(self.chunk_frames):
            yield {
                "type": "audio",
                "sequence": i,
                "content_type": "audio/wav",
                "audio_b64": base64.b64encode(_wav_bytes(frames=frames, value=i + 1)).decode("ascii"),
            }
        self.release_done.wait(timeout=5.0)
        self.stream_done.set()
        yield {"type": "done", "ok": True}

    def voice_tts(self, *, run_id, text, provider=None, voice=None, fmt=None, request_id=None,
                  model=None, profile=None, quality_preset=None, timeout_s=None):
        self.artifact_calls.append({"provider": provider, "model": model, "chars": len(text or "")})
        return {"audio_artifact": {"$artifact": "art_1"}}

    def download_run_artifact_content(self, *, run_id, artifact_id, max_bytes=25_000_000, timeout_s=None):
        return _wav_bytes(), "audio/wav"


class _PinRejectingGateway(_StreamingGateway):
    """Mirrors the live gateway: a pinned model the stream route cannot resolve
    fails the whole stream leg with an `error` event before any audio."""

    on_reject = None  # optional hook fired just before the rejection event

    def voice_tts_stream(self, *, run_id, text, provider=None, voice=None, fmt=None,
                         request_id=None, model=None, profile=None, quality_preset=None,
                         timeout_s=None):
        self.stream_calls.append({"provider": provider, "voice": voice, "profile": profile,
                                  "model": model, "fmt": fmt})
        yield {"type": "runtime_start", "ok": True}
        if model and not provider:
            if callable(self.on_reject):
                self.on_reject()
            yield {
                "type": "error",
                "ok": False,
                "error": f"audio/speech failed (404): The model `{model}` does not exist",
            }
            return
        for i, frames in enumerate(self.chunk_frames):
            yield {
                "type": "audio",
                "sequence": i,
                "content_type": "audio/wav",
                "audio_b64": base64.b64encode(_wav_bytes(frames=frames, value=i + 1)).decode("ascii"),
            }
        self.stream_done.set()
        yield {"type": "done", "ok": True}


class _ArtifactOnlyGateway(_StreamingGateway):
    """Streaming advertised, but every stream attempt dies before audio."""

    def voice_tts_stream(self, *, run_id, text, provider=None, voice=None, fmt=None,
                         request_id=None, model=None, profile=None, quality_preset=None,
                         timeout_s=None):
        self.stream_calls.append({"provider": provider, "model": model})
        yield {"type": "runtime_start", "ok": True}
        yield {"type": "error", "ok": False, "error": "engine unavailable"}


class _ManagerStub:
    def __init__(self, gateway) -> None:
        self.active_session_id = "sess_latency"
        self._gateway = gateway
        self.current_tts_provider = ""
        self.current_tts_model = ""
        self.current_tts_voice = ""
        self.current_tts_voice_mode = ""

    def gateway_client(self):
        return self._gateway


class _PlayerStub:
    """Queueing player: play_audio hands samples to the device immediately."""

    def __init__(self) -> None:
        self.is_playing = False
        self.on_audio_start = None
        self.on_audio_end = None
        self.on_audio_chunk = None
        self.playback_complete_callback = None
        self.play_calls: list[tuple[int, float]] = []  # (n_samples, first_value)

    def play_audio(self, audio_array, *, sample_rate: int | None = None):
        first = float(audio_array[0]) if len(audio_array) else 0.0
        self.play_calls.append((len(audio_array), first))
        if callable(self.on_audio_start):
            self.on_audio_start()

    def pause(self) -> bool:
        return True

    def resume(self) -> bool:
        return True

    def stop_stream(self) -> None:
        self.is_playing = False


def _wire_player(vm: GatewayVoiceManager, monkeypatch: pytest.MonkeyPatch) -> _PlayerStub:
    player = _PlayerStub()
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)
    return player


@pytest.mark.basic
def test_advertised_active_model_is_never_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gateway's own advertised default must not come back as a request pin.

    Live proof of the cost: model="supertonic-3" with no provider →
    `audio/speech failed (404)` on /voice/tts/stream before any audio.
    """
    gateway = _StreamingGateway()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    _wire_player(vm, monkeypatch)

    assert vm._selected_tts_model() is None
    assert vm.speak("hello unpinned") is True
    assert gateway.stream_done.wait(timeout=2.0)
    assert gateway.stream_calls, "the stream lane must be used"
    assert gateway.stream_calls[0]["model"] is None
    assert gateway.artifact_calls == []


@pytest.mark.basic
def test_explicit_model_override_is_still_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """A user-chosen model (settings override) is still honored."""
    gateway = _StreamingGateway()
    manager = _ManagerStub(gateway)
    manager.current_tts_provider = "supertonic"
    manager.current_tts_model = "supertonic-3"
    vm = GatewayVoiceManager(llm_manager=manager, debug_mode=False)
    _wire_player(vm, monkeypatch)

    assert vm.speak("hello pinned") is True
    assert gateway.stream_done.wait(timeout=2.0)
    assert gateway.stream_calls[0]["model"] == "supertonic-3"
    assert gateway.stream_calls[0]["provider"] == "supertonic"


@pytest.mark.basic
def test_env_model_override_is_still_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _StreamingGateway()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    _wire_player(vm, monkeypatch)
    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_MODEL", "env-model")

    assert vm._selected_tts_model() == "env-model"
    assert vm.speak("hello env pin") is True
    assert gateway.stream_done.wait(timeout=2.0)
    assert gateway.stream_calls[0]["model"] == "env-model"


@pytest.mark.basic
def test_pre_audio_stream_rejection_retries_unpinned_before_artifact_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pin the stream route cannot resolve must not cost the streaming lane."""
    gateway = _PinRejectingGateway()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _wire_player(vm, monkeypatch)
    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_MODEL", "unresolvable-model")

    with pytest.warns(UserWarning, match="retrying the stream with gateway defaults"):
        assert vm.speak("hello rejected pin") is True
        assert gateway.stream_done.wait(timeout=2.0)
        assert _wait_for(lambda: len(player.play_calls) == 1)

    assert [c["model"] for c in gateway.stream_calls] == ["unresolvable-model", None]
    assert gateway.artifact_calls == [], "the whole-message artifact lane must not be used"


@pytest.mark.basic
def test_unpinned_retry_fires_completion_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry must not double-fire (or swallow) the terminal signal.

    Both the rejected leg and the retried leg have a completion-owning
    `finally`; a card stuck on "speaking" and a card that resets twice are
    both regressions.
    """
    gateway = _PinRejectingGateway()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    _wire_player(vm, monkeypatch)
    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_MODEL", "unresolvable-model")

    ends: list[int] = []
    completions: list[int] = []
    vm.on_speech_end = lambda: ends.append(1)

    with pytest.warns(UserWarning):
        assert vm.speak("retry completion", callback=lambda: completions.append(1)) is True
        assert gateway.stream_done.wait(timeout=2.0)
        assert _wait_for(lambda: completions == [1])

    time.sleep(0.2)  # let any stray second completion land
    assert ends == [1], f"on_speech_end must fire exactly once, got {ends}"
    assert completions == [1], f"callback must fire exactly once, got {completions}"


@pytest.mark.basic
def test_stop_during_rejected_stream_skips_the_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stop must end the speech, not trigger a second (unpinned) attempt."""
    gateway = _PinRejectingGateway()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _wire_player(vm, monkeypatch)
    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_MODEL", "unresolvable-model")

    # The stop lands after the pinned leg opened, just before its rejection.
    gateway.on_reject = vm.stop_speaking

    completions: list[int] = []
    assert vm.speak("stopped rejected stream", callback=lambda: completions.append(1)) is True
    assert _wait_for(lambda: completions == [1], timeout_s=3.0)
    time.sleep(0.15)

    assert len(gateway.stream_calls) == 1, "a stopped speech must not start a retry"
    assert gateway.artifact_calls == []
    assert player.play_calls == []


@pytest.mark.basic
def test_unpinned_stream_failure_does_not_retry_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """No pins to drop (or already retried) → exactly one stream attempt."""
    gateway = _ArtifactOnlyGateway()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    _wire_player(vm, monkeypatch)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)

    with pytest.warns(UserWarning):
        assert vm.speak("hello dead stream") is True
        assert _wait_for(lambda: bool(gateway.artifact_calls))

    assert len(gateway.stream_calls) == 1


@pytest.mark.basic
def test_artifact_lane_for_long_text_is_never_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The degradation the operator reports must be visible in triage."""
    gateway = _ArtifactOnlyGateway()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    _wire_player(vm, monkeypatch)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)
    long_text = "This is a long assistant answer. " * 200

    with pytest.warns(UserWarning, match="nothing is audible until the whole message"):
        assert vm.speak(long_text) is True
        assert _wait_for(lambda: bool(gateway.artifact_calls))

    assert gateway.artifact_calls[0]["chars"] == len(long_text.strip())


@pytest.mark.basic
def test_declining_the_stream_lane_is_never_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conceding the artifact lane before even trying to stream must be said."""
    gateway = _StreamingGateway()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    _wire_player(vm, monkeypatch)
    monkeypatch.setattr(vm, "_gateway_tts_streaming_available", lambda: False)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)

    with pytest.warns(UserWarning, match="not using the gateway TTS streaming lane"):
        assert vm.speak("hello no streaming lane") is True
        assert _wait_for(lambda: bool(gateway.artifact_calls))

    assert gateway.stream_calls == []


@pytest.mark.basic
def test_playback_starts_on_first_chunk_not_after_stream_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    """First decoded chunk goes to the device while the stream is still open."""
    gateway = _StreamingGateway(chunk_frames=(240, 480))
    gateway.release_done.clear()  # hold the `done` event back
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _wire_player(vm, monkeypatch)

    assert vm.speak("hello early playback") is True
    assert _wait_for(lambda: len(player.play_calls) >= 1)
    assert not gateway.stream_done.is_set(), "audio must reach the device before the stream ends"

    gateway.release_done.set()
    assert gateway.stream_done.wait(timeout=2.0)


@pytest.mark.basic
def test_stream_chunks_reach_the_device_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ordering/gapless invariant: chunks are queued once, in arrival order."""
    gateway = _StreamingGateway(chunk_frames=(240, 480, 720))
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _wire_player(vm, monkeypatch)

    assert vm.speak("hello ordered stream") is True
    assert gateway.stream_done.wait(timeout=2.0)
    assert _wait_for(lambda: len(player.play_calls) == 3)

    assert [n for n, _ in player.play_calls] == [240, 480, 720]
    # Chunk N carries sample value N+1 (scaled int16) — proves no reordering.
    assert [round(v * 32768.0) for _, v in player.play_calls] == [1, 2, 3]
