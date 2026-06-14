"""Gateway voice manager regression tests."""

from __future__ import annotations

import io
import sys
from types import SimpleNamespace
import wave

import pytest

from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager


class _GatewayStub:
    def __init__(self) -> None:
        self._cfg = SimpleNamespace(timeout_s=30.0)
        self.calls: list[tuple[str, float]] = []

    def voice_tts(self, *, run_id: str, text: str, provider=None, voice=None, fmt=None, request_id=None, model=None, profile=None, timeout_s=None):
        self.calls.append(("voice_tts", float(timeout_s or self._cfg.timeout_s)))
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

    def voice_tts(self, *, run_id: str, text: str, provider=None, voice=None, fmt=None, request_id=None, model=None, profile=None, timeout_s=None):
        self.tts_kwargs = {"provider": provider, "voice": voice, "profile": profile, "fmt": fmt, "model": model}
        return super().voice_tts(
            run_id=run_id,
            text=text,
            provider=provider,
            voice=voice,
            profile=profile,
            fmt=fmt,
            request_id=request_id,
            model=model,
            timeout_s=timeout_s,
        )


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

    def pause(self) -> bool:
        self.pause_calls += 1
        return True

    def resume(self) -> bool:
        self.resume_calls += 1
        return True

    def stop_stream(self) -> None:
        self.stop_calls += 1
        self.is_playing = False


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * 240)
    return buf.getvalue()


@pytest.mark.basic
def test_gateway_voice_manager_temporarily_raises_tts_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _GatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)

    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)

    assert vm.speak("hello from timeout test") is True
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
    expected_fmt = "wav" if sys.platform == "darwin" and vm._supports_inprocess_audio_player() else "mp3"
    assert gateway.tts_kwargs == {"provider": None, "voice": None, "profile": "alloy", "fmt": expected_fmt, "model": "tts-model"}


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
    expected_fmt = "wav" if sys.platform == "darwin" and vm._supports_inprocess_audio_player() else "mp3"
    assert gateway.tts_kwargs == {"provider": "supertonic", "voice": None, "profile": "M1", "fmt": expected_fmt, "model": "supertonic-3"}


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
