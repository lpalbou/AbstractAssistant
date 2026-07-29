"""Output-volume visibility: correct playback at inaudible volume must be
distinguishable from a hang (2026-07-28 audit: all software layers delivered
loud audio while the system output volume sat at 6/100)."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager


def _manager() -> GatewayVoiceManager:
    return GatewayVoiceManager(llm_manager=SimpleNamespace(), debug_mode=False)


@pytest.mark.basic
def test_output_volume_state_parses_osascript(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "abstractassistant.core.gateway_voice_manager.sys",
        SimpleNamespace(platform="darwin"),
    )

    def _fake_run(*args, **kwargs):
        return SimpleNamespace(
            stdout="output volume:6, input volume:57, alert volume:100, output muted:false",
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    volume, muted = _manager().output_volume_state()
    assert volume == 6
    assert muted is False


@pytest.mark.basic
def test_output_volume_state_parses_muted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "abstractassistant.core.gateway_voice_manager.sys",
        SimpleNamespace(platform="darwin"),
    )

    def _fake_run(*args, **kwargs):
        return SimpleNamespace(
            stdout="output volume:80, input volume:57, alert volume:100, output muted:true",
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)
    volume, muted = _manager().output_volume_state()
    assert volume == 80
    assert muted is True


@pytest.mark.basic
def test_output_volume_state_degrades_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "abstractassistant.core.gateway_voice_manager.sys",
        SimpleNamespace(platform="darwin"),
    )

    def _boom(*args, **kwargs):
        raise OSError("no osascript")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert _manager().output_volume_state() == (None, None)


@pytest.mark.basic
def test_output_volume_state_non_macos_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "abstractassistant.core.gateway_voice_manager.sys",
        SimpleNamespace(platform="linux"),
    )
    assert _manager().output_volume_state() == (None, None)
