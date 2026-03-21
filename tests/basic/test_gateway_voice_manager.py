"""Gateway voice manager regression tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager


class _GatewayStub:
    def __init__(self) -> None:
        self._cfg = SimpleNamespace(timeout_s=30.0)
        self.calls: list[tuple[str, float]] = []

    def voice_tts(self, *, run_id: str, text: str, voice=None, fmt=None, request_id=None):
        self.calls.append(("voice_tts", float(self._cfg.timeout_s)))
        return {"audio_artifact": {"$artifact": "art_1"}}

    def download_run_artifact_content(self, *, run_id: str, artifact_id: str, max_bytes: int = 25_000_000):
        self.calls.append(("download", float(self._cfg.timeout_s)))
        return b"RIFF....", "audio/wav"


class _ManagerStub:
    def __init__(self, gateway: _GatewayStub) -> None:
        self.active_session_id = "sess_probe"
        self._gateway = gateway

    def gateway_client(self) -> _GatewayStub:
        return self._gateway


@pytest.mark.basic
def test_gateway_voice_manager_temporarily_raises_tts_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _GatewayStub()
    vm = GatewayVoiceManager(llm_manager=_ManagerStub(gateway), debug_mode=False)

    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: True)

    assert vm.speak("hello from timeout test") is True
    assert gateway.calls == [("voice_tts", 120.0), ("download", 120.0)]
    assert gateway._cfg.timeout_s == 30.0
