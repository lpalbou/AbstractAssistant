"""Round 18: dictation sends NO language hint — the Assistant keeps no copy.

Until round 18 ``GatewayVoiceManager`` read abstractcore's LOCAL ``audio.stt_language``
and handed it to ``VoiceRecognizer(language=…)``, so every dictation carried a per-request
``language`` that overrode the account preference the gateway keeps. Now the recognizer is
built with ``language=None`` and the gateway resolves the language (request hint → account
preference → auto) — the one resolver, ``abstractgateway.spoken_language``.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from abstractassistant.core import gateway_voice_manager as gvm_mod
from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager


class _FakeRecognizer:
    built: list = []

    def __init__(self, **kwargs) -> None:
        _FakeRecognizer.built.append(kwargs)

    def set_profile(self, _mode) -> None:
        pass

    def start(self) -> bool:
        return True

    def stop(self) -> None:
        pass


@pytest.mark.basic
def test_dictation_builds_the_recognizer_without_a_language_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local abstractcore config that names a language must NOT reach the recognizer."""
    fake_recognition = types.ModuleType("abstractvoice.recognition")
    fake_recognition.VoiceRecognizer = _FakeRecognizer
    monkeypatch.setitem(sys.modules, "abstractvoice.recognition", fake_recognition)
    # The trap: a device-local config that says German. Reading it is the bug.
    config_reads: list = []

    def _config_manager():
        config_reads.append(True)
        return SimpleNamespace(config=SimpleNamespace(audio=SimpleNamespace(stt_language="de")))

    fake_manager = types.ModuleType("abstractcore.config.manager")
    fake_manager.get_config_manager = _config_manager
    monkeypatch.setitem(sys.modules, "abstractcore.config.manager", fake_manager)

    manager = GatewayVoiceManager(llm_manager=SimpleNamespace())
    monkeypatch.setattr(manager, "supports_stt", lambda: True)
    _FakeRecognizer.built.clear()
    assert manager.listen(on_transcription=lambda _t: None) is True
    try:
        assert len(_FakeRecognizer.built) == 1
        kwargs = _FakeRecognizer.built[0]
        assert "language" in kwargs and kwargs["language"] is None, kwargs.get("language")
        assert config_reads == [], "the voice manager read abstractcore's local config"
    finally:
        manager.stop_listening()


@pytest.mark.basic
def test_no_local_stt_language_copy_remains_in_the_voice_manager() -> None:
    """Grep proof: the module neither names ``stt_language`` nor reads abstractcore's config."""
    source = Path(gvm_mod.__file__).read_text(encoding="utf-8")
    assert "stt_language" not in source
    assert "get_config_manager" not in source
    assert "_default_stt_language" not in source


@pytest.mark.basic
def test_the_stt_adapter_sends_no_language_when_none_is_given(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The adapter passes a caller's explicit hint through unchanged — None now, so the
    transcribe request carries no ``language`` and the gateway applies the account's."""
    from abstractassistant.core.gateway_stt_adapter import GatewaySTTAdapter

    calls: list = []

    class _Gw:
        def attachments_upload(self, **kwargs):
            return {"attachment": {"$artifact": "art_1"}}

        def audio_transcribe(self, **kwargs):
            calls.append(kwargs)
            return {"text": "bonjour"}

    adapter = GatewaySTTAdapter(
        gateway_client_fn=lambda: _Gw(),
        session_id_fn=lambda: "s1",
        run_id_fn=lambda: "r1",
        content_type_fn=lambda: "audio/wav",
        max_upload_bytes_fn=lambda: 1_000_000,
        stt_model_fn=lambda: None,
        stt_provider_fn=lambda: None,
    )
    assert adapter.transcribe_from_bytes(b"RIFF0000WAVE", language=None) == "bonjour"
    assert len(calls) == 1 and calls[0].get("language") is None
