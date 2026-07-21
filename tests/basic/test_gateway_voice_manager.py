"""Gateway voice manager regression tests."""

from __future__ import annotations

import io
import base64
import sys
import threading
import time
from types import SimpleNamespace
import wave

import pytest

from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager


class _GatewayStub:
    def __init__(self) -> None:
        self._cfg = SimpleNamespace(timeout_s=30.0)
        self.calls: list[tuple[str, float]] = []

    def voice_tts(self, *, run_id: str, text: str, provider=None, voice=None, fmt=None, request_id=None, model=None, profile=None, quality_preset=None, timeout_s=None):
        self.calls.append(("voice_tts", float(timeout_s or self._cfg.timeout_s)))
        self.quality_preset = quality_preset
        return {"audio_artifact": {"$artifact": "art_1"}}

    def download_run_artifact_content(self, *, run_id: str, artifact_id: str, max_bytes: int = 25_000_000, timeout_s=None):
        self.calls.append(("download", float(timeout_s or self._cfg.timeout_s)))
        return b"RIFF....", "audio/wav"


class _CapabilityGatewayStub(_GatewayStub):
    def __init__(self) -> None:
        super().__init__()
        self.tts_kwargs = {}

    def discovery_capabilities(self):
        return {
            "capabilities": {
                "contracts": {
                    "version": 1,
                    "assistant": {
                        "voice": {
                            "tts": {
                                "available": True,
                                "formats": ["mp3"],
                                "voices": [{"id": "alloy", "label": "Alloy"}],
                                "active_model": "tts-model",
                            },
                            "stt": {
                                "available": False,
                                "content_types": ["audio/wav"],
                                "max_upload_bytes": 1_000_000,
                            },
                        }
                    },
                }
            }
        }

    def voice_tts(self, *, run_id: str, text: str, provider=None, voice=None, fmt=None, request_id=None, model=None, profile=None, quality_preset=None, timeout_s=None):
        self.tts_kwargs = {"provider": provider, "voice": voice, "profile": profile, "fmt": fmt, "model": model, "quality_preset": quality_preset}
        return super().voice_tts(
            run_id=run_id,
            text=text,
            provider=provider,
            voice=voice,
            profile=profile,
            fmt=fmt,
            request_id=request_id,
            model=model,
            quality_preset=quality_preset,
            timeout_s=timeout_s,
        )


class _StreamingGatewayStub(_CapabilityGatewayStub):
    def __init__(self, *, audio_chunks: int = 1) -> None:
        super().__init__()
        self.audio_chunks = int(audio_chunks)
        self.stream_started = threading.Event()
        self.stream_done = threading.Event()

    def discovery_capabilities(self):
        payload = super().discovery_capabilities()
        tts = payload["capabilities"]["contracts"]["assistant"]["voice"]["tts"]
        tts["streaming"] = True
        tts["delivery_modes"] = ["artifact", "stream"]
        tts["stream_endpoint"] = "/api/gateway/runs/{run_id}/voice/tts/stream"
        tts["stream_transport"] = "jsonl"
        tts["formats"] = ["wav"]
        return payload

    def voice_tts_stream(self, *, run_id: str, text: str, provider=None, voice=None, fmt=None, request_id=None, model=None, profile=None, quality_preset=None, timeout_s=None):
        self.calls.append(("voice_tts_stream", float(timeout_s or self._cfg.timeout_s)))
        self.tts_kwargs = {"provider": provider, "voice": voice, "profile": profile, "fmt": fmt, "model": model, "quality_preset": quality_preset}
        self.stream_started.set()
        yield {"type": "runtime_start", "ok": True}
        for i in range(max(1, self.audio_chunks)):
            yield {
                "type": "audio",
                "sequence": i,
                "content_type": "audio/wav",
                "audio_b64": base64.b64encode(_wav_bytes()).decode("ascii"),
            }
        self.stream_done.set()
        yield {"type": "done", "ok": True, "audio_artifact": {"$artifact": "art_stream"}}


class _BlockingStreamingGatewayStub(_StreamingGatewayStub):
    def __init__(self) -> None:
        super().__init__(audio_chunks=1)
        self.release_audio = threading.Event()

    def voice_tts_stream(self, *, run_id: str, text: str, provider=None, voice=None, fmt=None, request_id=None, model=None, profile=None, quality_preset=None, timeout_s=None):
        self.calls.append(("voice_tts_stream", float(timeout_s or self._cfg.timeout_s)))
        self.tts_kwargs = {"provider": provider, "voice": voice, "profile": profile, "fmt": fmt, "model": model, "quality_preset": quality_preset}
        self.stream_started.set()
        yield {"type": "runtime_start", "ok": True}
        self.release_audio.wait(timeout=5.0)
        yield {
            "type": "audio",
            "sequence": 0,
            "content_type": "audio/wav",
            "audio_b64": base64.b64encode(_wav_bytes()).decode("ascii"),
        }
        self.stream_done.set()
        yield {"type": "done", "ok": True, "audio_artifact": {"$artifact": "art_stream"}}


class _SecondChunkGateStreamingGatewayStub(_StreamingGatewayStub):
    def __init__(self) -> None:
        super().__init__(audio_chunks=2)
        self.first_audio_ready = threading.Event()
        self.release_second_audio = threading.Event()
        self.second_audio_ready = threading.Event()

    def voice_tts_stream(self, *, run_id: str, text: str, provider=None, voice=None, fmt=None, request_id=None, model=None, profile=None, quality_preset=None, timeout_s=None):
        self.calls.append(("voice_tts_stream", float(timeout_s or self._cfg.timeout_s)))
        self.tts_kwargs = {"provider": provider, "voice": voice, "profile": profile, "fmt": fmt, "model": model, "quality_preset": quality_preset}
        self.stream_started.set()
        yield {"type": "runtime_start", "ok": True}
        self.first_audio_ready.set()
        yield {
            "type": "audio",
            "sequence": 0,
            "content_type": "audio/wav",
            "audio_b64": base64.b64encode(_wav_bytes()).decode("ascii"),
        }
        self.release_second_audio.wait(timeout=5.0)
        self.second_audio_ready.set()
        yield {
            "type": "audio",
            "sequence": 1,
            "content_type": "audio/wav",
            "audio_b64": base64.b64encode(_wav_bytes()).decode("ascii"),
        }
        self.stream_done.set()
        yield {"type": "done", "ok": True, "audio_artifact": {"$artifact": "art_stream"}}


class _BlockingArtifactGatewayStub(_CapabilityGatewayStub):
    """Artifact-only gateway whose synthesis blocks until released.

    Models the real behavior where /voice/tts synthesizes the whole message
    server-side (tens of seconds for long texts) before responding.
    """

    def __init__(self) -> None:
        super().__init__()
        self.tts_started = threading.Event()
        self.release_tts = threading.Event()

    def voice_tts(self, **kwargs):
        self.tts_started.set()
        self.release_tts.wait(timeout=5.0)
        return super().voice_tts(**kwargs)


class _ManagerStub:
    def __init__(self, gateway: _GatewayStub) -> None:
        self.active_session_id = "sess_probe"
        self._gateway = gateway
        self.current_tts_provider = ""
        self.current_tts_model = ""
        self.current_tts_voice = ""
        self.current_tts_voice_mode = ""

    def gateway_client(self) -> _GatewayStub:
        return self._gateway


class _InProcessPlayerStub:
    def __init__(self) -> None:
        self.is_playing = False
        self.auto_end = False
        self.on_audio_start = None
        self.on_audio_end = None
        self.on_audio_chunk = None
        self.playback_complete_callback = None
        self.pause_calls = 0
        self.resume_calls = 0
        self.stop_calls = 0
        self.play_calls: list[tuple[object, int | None]] = []

    def play_audio(self, audio_array, *, sample_rate: int | None = None):
        self.play_calls.append((audio_array, sample_rate))
        self.is_playing = True
        if callable(self.on_audio_start):
            self.on_audio_start()
        if self.auto_end and callable(self.on_audio_end):
            self.is_playing = False
            self.on_audio_end()

    def pause(self) -> bool:
        self.pause_calls += 1
        return True

    def resume(self) -> bool:
        self.resume_calls += 1
        return True

    def stop_stream(self) -> None:
        self.stop_calls += 1
        self.is_playing = False


class _QueuedInProcessPlayerStub(_InProcessPlayerStub):
    def play_audio(self, audio_array, *, sample_rate: int | None = None):
        self.play_calls.append((audio_array, sample_rate))
        self.is_playing = False
        if callable(self.on_audio_start):
            self.on_audio_start()


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * 240)
    return buf.getvalue()


def _wait_for(predicate, *, timeout_s: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


@pytest.mark.basic
def test_gateway_voice_manager_temporarily_raises_tts_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _GatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)

    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)

    assert vm.speak("hello from timeout test") is True
    # speak() dispatches asynchronously: wait for the worker to finish.
    assert _wait_for(lambda: len(gateway.calls) == 2)
    assert gateway.calls == [("voice_tts", 120.0), ("download", 120.0)]
    assert gateway._cfg.timeout_s == 30.0


@pytest.mark.basic
def test_gateway_voice_manager_uses_advertised_tts_format_and_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _CapabilityGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)

    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_VOICE", "alloy")
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)

    assert vm.supports_tts() is True
    assert vm.supports_stt() is False
    assert vm.speak("hello from caps") is True
    assert _wait_for(lambda: bool(gateway.tts_kwargs))
    expected_fmt = "wav" if sys.platform == "darwin" and vm._supports_inprocess_audio_player() else "mp3"
    assert gateway.tts_kwargs == {"provider": None, "voice": None, "profile": "alloy", "fmt": expected_fmt, "model": "tts-model", "quality_preset": None}


@pytest.mark.basic
def test_gateway_voice_manager_prefers_advertised_streaming_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _StreamingGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _InProcessPlayerStub()
    player.auto_end = True

    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_VOICE", "alloy")
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)

    assert vm.speak("hello from stream") is True
    assert gateway.stream_done.wait(timeout=2.0)
    assert _wait_for(lambda: len(player.play_calls) == 1)
    assert gateway.calls == [("voice_tts_stream", 120.0)]
    assert gateway.tts_kwargs == {"provider": None, "voice": None, "profile": "alloy", "fmt": "wav", "model": "tts-model", "quality_preset": None}


@pytest.mark.basic
def test_gateway_voice_manager_queues_stream_chunks_without_per_chunk_end(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _StreamingGatewayStub(audio_chunks=2)
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _QueuedInProcessPlayerStub()
    starts = []

    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_VOICE", "alloy")
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)
    vm.on_speech_start = lambda: starts.append("start")

    assert vm.speak("hello from queued stream") is True
    assert gateway.stream_done.wait(timeout=2.0)
    assert _wait_for(lambda: len(player.play_calls) == 2)
    assert gateway.calls == [("voice_tts_stream", 120.0)]
    assert starts == ["start"]


@pytest.mark.basic
def test_gateway_voice_manager_stream_speak_returns_before_first_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _BlockingStreamingGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _InProcessPlayerStub()
    player.auto_end = True

    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_VOICE", "alloy")
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)

    started_at = time.monotonic()
    assert vm.speak("hello from nonblocking stream") is True
    elapsed_s = time.monotonic() - started_at
    assert elapsed_s < 0.25
    assert gateway.stream_started.wait(timeout=1.0)
    assert player.play_calls == []

    gateway.release_audio.set()
    assert gateway.stream_done.wait(timeout=2.0)
    assert len(player.play_calls) == 1


@pytest.mark.basic
def test_gateway_voice_manager_stream_pause_before_first_audio_blocks_playback_until_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _BlockingStreamingGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _InProcessPlayerStub()
    player.auto_end = True

    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_VOICE", "alloy")
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)

    assert vm.speak("hello from paused preaudio stream") is True
    assert gateway.stream_started.wait(timeout=1.0)
    assert vm.pause() is True
    assert vm.is_paused() is True

    gateway.release_audio.set()
    time.sleep(0.15)
    assert player.play_calls == []

    assert vm.resume() is True
    assert gateway.stream_done.wait(timeout=2.0)
    assert len(player.play_calls) == 1


@pytest.mark.basic
def test_gateway_voice_manager_stream_stop_before_first_audio_does_not_fallback_or_play(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _BlockingStreamingGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _InProcessPlayerStub()
    player.auto_end = True

    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_VOICE", "alloy")
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)

    assert vm.speak("hello from stopped preaudio stream") is True
    assert gateway.stream_started.wait(timeout=1.0)
    vm.stop_speaking()
    gateway.release_audio.set()
    time.sleep(0.15)

    assert player.play_calls == []
    assert gateway.calls == [("voice_tts_stream", 120.0)]


class _QualityControlsGatewayStub(_CapabilityGatewayStub):
    def discovery_capabilities(self):
        payload = super().discovery_capabilities()
        tts = payload["capabilities"]["contracts"]["assistant"]["voice"]["tts"]
        tts["controls"] = {"quality_preset": {"supported": True, "values": ["low", "standard", "high"]}}
        return payload


@pytest.mark.basic
def test_gateway_voice_manager_sends_quality_preset_when_advertised(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _QualityControlsGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    vm.set_quality_preset("low")

    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)

    assert vm.speak("hello quality") is True
    assert _wait_for(lambda: bool(gateway.tts_kwargs))
    assert gateway.tts_kwargs["quality_preset"] == "low"


@pytest.mark.basic
def test_gateway_voice_manager_omits_quality_preset_when_not_advertised(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _CapabilityGatewayStub()  # no controls.quality_preset advertised
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    vm.set_quality_preset("low")

    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)

    with pytest.warns(UserWarning, match="quality_preset"):
        assert vm.speak("hello no preset") is True
        assert _wait_for(lambda: bool(gateway.tts_kwargs))
    assert gateway.tts_kwargs["quality_preset"] is None


@pytest.mark.basic
def test_gateway_voice_manager_artifact_speak_returns_before_synthesis(monkeypatch: pytest.MonkeyPatch) -> None:
    """speak() must never block the caller on synthesis (GUI-thread freeze fix)."""
    gateway = _BlockingArtifactGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)

    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_speak_gateway_stream", lambda **kwargs: None)
    played = []
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: played.append(1) or True)

    started_at = time.monotonic()
    assert vm.speak("hello from long synthesis") is True
    elapsed_s = time.monotonic() - started_at
    assert elapsed_s < 0.25
    assert gateway.tts_started.wait(timeout=1.0)
    assert played == []

    gateway.release_tts.set()
    assert _wait_for(lambda: played == [1])


@pytest.mark.basic
def test_gateway_voice_manager_artifact_stop_during_synthesis_cancels_and_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop during artifact synthesis: no zombie playback, exactly one completion."""
    gateway = _BlockingArtifactGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)

    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_speak_gateway_stream", lambda **kwargs: None)
    played = []
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: played.append(1) or True)
    completions = []

    assert vm.speak("hello cancelled synthesis", callback=lambda: completions.append(1)) is True
    assert gateway.tts_started.wait(timeout=1.0)
    vm.stop_speaking()
    gateway.release_tts.set()

    assert _wait_for(lambda: len(completions) == 1)
    time.sleep(0.1)
    assert played == []
    assert completions == [1]


@pytest.mark.basic
def test_gateway_voice_manager_artifact_pause_during_synthesis_holds_playback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pause while synthesizing holds playback until resume (honest pause)."""
    gateway = _BlockingArtifactGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)

    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_speak_gateway_stream", lambda **kwargs: None)
    played = []
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: played.append(1) or True)

    assert vm.speak("hello paused synthesis") is True
    assert gateway.tts_started.wait(timeout=1.0)
    assert vm.pause() is True
    assert vm.is_paused() is True

    gateway.release_tts.set()
    time.sleep(0.15)
    assert played == []

    assert vm.resume() is True
    assert _wait_for(lambda: played == [1])


@pytest.mark.basic
def test_gateway_voice_manager_speak_failure_fires_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """A background failure must fire the completion callback (UI reset)."""
    gateway = _GatewayStub()

    def _boom(**kwargs):
        raise RuntimeError("synthesis exploded")

    gateway.voice_tts = _boom  # type: ignore[assignment]
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)

    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_speak_gateway_stream", lambda **kwargs: None)
    played = []
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: played.append(1) or True)
    completions = []
    ends = []
    vm.on_speech_end = lambda: ends.append(1)

    with pytest.warns(UserWarning, match="gateway TTS failed"):
        assert vm.speak("hello failing synthesis", callback=lambda: completions.append(1)) is True
        assert _wait_for(lambda: completions == [1])
    assert ends == [1]
    assert played == []


@pytest.mark.basic
def test_gateway_voice_manager_warns_when_streaming_advertised_but_player_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silent degradation guard: advertised streaming + no sounddevice = loud #FALLBACK."""
    gateway = _StreamingGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)

    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: False)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: None)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)

    with pytest.warns(UserWarning, match="streaming TTS is advertised but the in-process"):
        assert vm.speak("hello degraded stream") is True
        assert _wait_for(lambda: ("voice_tts", 120.0) in gateway.calls)


@pytest.mark.basic
def test_gateway_voice_manager_stream_stop_fires_completion_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stopping a stream before audio must still fire the completion callback."""
    gateway = _BlockingStreamingGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _InProcessPlayerStub()
    player.auto_end = True

    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)
    completions = []

    assert vm.speak("hello stopped stream completion", callback=lambda: completions.append(1)) is True
    assert gateway.stream_started.wait(timeout=1.0)
    vm.stop_speaking()
    gateway.release_audio.set()

    assert _wait_for(lambda: completions == [1])
    assert player.play_calls == []


@pytest.mark.basic
def test_gateway_voice_manager_stream_pause_holds_later_chunks_until_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _SecondChunkGateStreamingGatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _InProcessPlayerStub()
    player.auto_end = True

    monkeypatch.setenv("ABSTRACTASSISTANT_GATEWAY_TTS_VOICE", "alloy")
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)

    assert vm.speak("hello from paused multichunk stream") is True
    assert gateway.first_audio_ready.wait(timeout=1.0)
    assert _wait_for(lambda: len(player.play_calls) == 1, timeout_s=1.0)

    assert vm.pause() is True
    gateway.release_second_audio.set()
    assert gateway.second_audio_ready.wait(timeout=1.0)
    time.sleep(0.15)
    assert len(player.play_calls) == 1

    assert vm.resume() is True
    assert gateway.stream_done.wait(timeout=2.0)
    assert len(player.play_calls) == 2


@pytest.mark.basic
def test_gateway_voice_manager_passes_selected_tts_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _CapabilityGatewayStub()
    manager = _ManagerStub(gateway)
    manager.current_tts_provider = "supertonic"
    manager.current_tts_model = "supertonic-3"
    manager.current_tts_voice = "M1"
    manager.current_tts_voice_mode = "profile"
    vm = GatewayVoiceManager(llm_manager=manager, debug_mode=False)

    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)

    assert vm.speak("hello from provider") is True
    assert _wait_for(lambda: bool(gateway.tts_kwargs))
    expected_fmt = "wav" if sys.platform == "darwin" and vm._supports_inprocess_audio_player() else "mp3"
    assert gateway.tts_kwargs == {"provider": "supertonic", "voice": None, "profile": "M1", "fmt": expected_fmt, "model": "supertonic-3", "quality_preset": None}


@pytest.mark.basic
def test_gateway_voice_manager_prefers_wav_on_macos_with_inprocess_player(monkeypatch: pytest.MonkeyPatch) -> None:
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(_GatewayStub()), debug_mode=False)

    monkeypatch.setattr("abstractassistant.core.gateway_voice_manager.sys.platform", "darwin")
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)

    assert vm._preferred_tts_format() == "wav"


@pytest.mark.basic
def test_gateway_voice_manager_inprocess_pause_resume_updates_state(monkeypatch: pytest.MonkeyPatch) -> None:
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(_GatewayStub()), debug_mode=False)
    player = _InProcessPlayerStub()

    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)
    vm._inprocess_player = player

    assert vm._play_audio_bytes_inprocess(_wav_bytes(), callback=None) is True
    assert vm.is_speaking() is True
    assert vm.pause() is True
    assert player.pause_calls == 1
    assert vm.is_paused() is True
    assert vm.resume() is True
    assert player.resume_calls == 1
    assert vm.is_speaking() is True


@pytest.mark.basic
def test_gateway_voice_manager_inprocess_pause_is_not_synced_to_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(_GatewayStub()), debug_mode=False)
    player = _InProcessPlayerStub()

    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)
    vm._inprocess_player = player

    assert vm._play_audio_bytes_inprocess(_wav_bytes(), callback=None) is True
    assert vm.pause() is True
    player.is_playing = False

    assert vm.get_state() == "paused"
    assert vm.is_paused() is True


@pytest.mark.basic
def test_gateway_voice_manager_stream_playback_is_not_idle_while_paused() -> None:
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(_GatewayStub()), debug_mode=False)
    player = _InProcessPlayerStub()
    vm._inprocess_player = player
    vm._playback_backend = "inprocess"
    with vm._state_lock:
        vm._paused = True
        vm._speaking = False

    assert vm._stream_playback_idle(player) is False


@pytest.mark.basic
def test_gateway_voice_manager_stream_success_fires_completion_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful stream must fire on_speech_end + callback exactly once.

    Regression: `_finish_stream_playback` returned None, so its caller's
    `finally` (`completion_owned` was falsey) fired the terminal signal a
    SECOND time — a message card that reset then re-armed, and full-voice mode
    seeing a spurious second completion. The method now reports ownership.
    """
    gateway = _StreamingGatewayStub(audio_chunks=1)
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)
    player = _InProcessPlayerStub()
    player.auto_end = True

    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: player)

    ends: list[int] = []
    completions: list[int] = []
    vm.on_speech_end = lambda: ends.append(1)

    assert vm.speak("stream success exactly once", callback=lambda: completions.append(1)) is True
    assert gateway.stream_done.wait(timeout=2.0)
    assert _wait_for(lambda: completions == [1])
    # Give any stray finally-block completion a chance to (wrongly) fire.
    time.sleep(0.2)
    assert ends == [1], f"on_speech_end must fire exactly once, got {ends}"
    assert completions == [1], f"callback must fire exactly once, got {completions}"
