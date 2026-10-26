"""A message that was never sent keeps its words, its files and its recording.

Two defects found by the 2026-10-26 Apple-lessons audit (backlog 1056, rows 1
and 2) and reproduced by its adversary:

1. A send with attachments to a gateway that refuses the connection failed in
   `_upload_attachments`, OUTSIDE the start guard: it surfaced as "The run
   failed", the shown turn stayed, and the composer (already cleared) and the
   attachments were lost. A `build_chat_worker` exception took the same path.
   Now both are a turn that never started: `run_start_failed`.
2. A failed hold-to-talk transcription threw the recording away (it lived only
   in the worker closure). Now it is kept, with Retry (the same audio) and
   Discard, and nothing resends on its own — the watch's "Not sent." rule.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

import threading
import time

import numpy as np
import pytest
from PyQt5.QtCore import QThread, pyqtSignal

import test_run_lifecycle_fixes as life  # noqa: E402 (tests/basic is on sys.path)
from test_palette_smoke import _app, palette  # noqa: E402,F401 (fixture)

from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager


class _RefusingGateway(life._StartGateway):
    def attachments_upload(self, **kwargs):
        raise ConnectionRefusedError(61, "Connection refused")


def _png(tmp_path):
    path = tmp_path / "shot.png"
    path.write_bytes(b"\x89PNG....")
    return str(path)


# --------------------------------------------------------------------------- 1. send


@pytest.mark.basic
def test_a_refused_attachment_upload_is_a_turn_that_never_started(monkeypatch, tmp_path) -> None:
    import abstractassistant.ui.gateway_worker as module

    monkeypatch.setattr(module, "GatewayRunController", lambda **kw: object())
    gateway = _RefusingGateway()
    worker = life._worker(gateway)
    worker._attachments = [_png(tmp_path)]
    worker.run()

    failed = [e for e in worker.event_emitted.items if e.get("type") == "run_start_failed"]
    assert failed, worker.event_emitted.items
    assert "refused" in failed[0]["error"].lower()
    assert failed[0]["prompt"] == "write report.md"
    assert failed[0]["attachments"] == worker._attachments
    assert worker.error_occurred.items == []  # not "The run failed"
    assert gateway.started == []


class _RealWorkerThread(QThread):
    """The real GatewayWorker.run() against a refusing gateway, on a thread,
    with Qt signals: the palette sees exactly what the worker emits."""

    event_emitted = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    warning_occurred = pyqtSignal(str)

    def __init__(self, *, prompt: str, attachments: list) -> None:
        super().__init__()
        self._prompt = prompt
        self._files = attachments

    def run(self) -> None:
        inner = life._worker(_RefusingGateway())
        inner._user_text = self._prompt
        inner._attachments = list(self._files)
        inner.event_emitted = self.event_emitted
        inner.error_occurred = self.error_occurred
        inner.warning_occurred = self.warning_occurred
        inner.run()


def _wait_until_idle(window, thread=None, timeout_s: float = 3.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline and (
        (thread is not None and thread.isRunning()) or window.__dict__.get("_worker") is not None
    ):
        _app().processEvents()
        time.sleep(0.01)
    _app().processEvents()


@pytest.mark.basic
def test_the_palette_gives_back_the_words_and_files_of_a_refused_send(palette, monkeypatch, tmp_path) -> None:
    window, controller = palette
    import abstractassistant.ui.gateway_worker as module

    monkeypatch.setattr(module, "GatewayRunController", lambda **kw: object())
    shot = _png(tmp_path)
    removed: list = []
    monkeypatch.setattr(controller, "remove_message", lambda mid: removed.append(mid) or True)
    holder: dict = {}

    def build(**kwargs):
        holder["thread"] = _RealWorkerThread(prompt=kwargs["prompt"], attachments=kwargs["attachments"])
        return holder["thread"]

    monkeypatch.setattr(controller, "build_chat_worker", build)
    window.prompt_edit.setPlainText("summarise this screenshot")
    window._attachments = [shot]
    window._submit()
    _wait_until_idle(window, holder["thread"])

    assert window.prompt_edit.toPlainText() == "summarise this screenshot"
    assert window._attachments == [shot]
    assert removed == ["mid-1"]  # the shown turn is withdrawn
    assert "Not sent" in window.banner_label.text()
    assert "The run failed" not in window.banner_label.text()
    assert window._run_busy is False


@pytest.mark.basic
def test_a_worker_that_cannot_be_built_is_also_a_turn_that_never_started(palette, monkeypatch, tmp_path) -> None:
    window, controller = palette
    shot = _png(tmp_path)
    removed: list = []
    monkeypatch.setattr(controller, "remove_message", lambda mid: removed.append(mid) or True)

    def build(**kwargs):
        raise ConnectionRefusedError(61, "Connection refused")

    monkeypatch.setattr(controller, "build_chat_worker", build)
    window.prompt_edit.setPlainText("summarise this screenshot")
    window._attachments = [shot]
    window._submit()
    _app().processEvents()

    assert window.prompt_edit.toPlainText() == "summarise this screenshot"
    assert window._attachments == [shot]
    assert removed == ["mid-1"]
    assert "Not sent" in window.banner_label.text()
    assert "The run failed" not in window.banner_label.text()
    assert window._run_busy is False


# --------------------------------------------------------------------------- 2. recording


class _Adapter:
    def __init__(self, outcomes: list) -> None:
        self.outcomes = list(outcomes)
        self.calls: list = []

    def transcribe_from_array(self, audio, sample_rate, language=None):
        self.calls.append(audio)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _held_manager(adapter: _Adapter) -> GatewayVoiceManager:
    manager = GatewayVoiceManager.__new__(GatewayVoiceManager)
    manager._hold_stream = object()
    manager._close_hold_stream = lambda: None
    manager._hold_lock = threading.Lock()
    manager._hold_chunks = [np.ones(GatewayVoiceManager.HOLD_SAMPLE_RATE * 2, dtype=np.int16)]
    manager._hold_started = time.monotonic() - 2.0
    manager._make_stt_adapter = lambda: adapter
    manager._default_stt_language = lambda: None
    return manager


def _settle(predicate, timeout_s: float = 2.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline and not predicate():
        time.sleep(0.01)


@pytest.mark.basic
def test_a_failed_transcription_keeps_the_recording_until_retry_or_discard() -> None:
    adapter = _Adapter([ConnectionRefusedError(61, "Connection refused"), "hello there"])
    manager = _held_manager(adapter)
    got: list = []
    assert manager.end_hold(lambda text: got.append(("text", text)), lambda err: got.append(("error", err)))
    _settle(lambda: bool(got))

    assert got == [("error", "[Errno 61] Connection refused")]
    assert manager.has_failed_hold()
    assert manager.failed_hold_seconds() == pytest.approx(2.0, abs=0.01)
    time.sleep(0.2)
    assert len(adapter.calls) == 1  # nothing resends on its own

    assert manager.retry_failed_hold(lambda text: got.append(("text", text)), lambda err: got.append(("error", err)))
    _settle(lambda: len(got) == 2)
    assert got[-1] == ("text", "hello there")
    assert adapter.calls[1] is adapter.calls[0]  # the SAME recording went again
    assert not manager.has_failed_hold()
    assert manager.retry_failed_hold(lambda text: None) is False  # nothing left to retry

    # Discard forgets it.
    adapter2 = _Adapter([RuntimeError("STT route failed")])
    manager2 = _held_manager(adapter2)
    errors: list = []
    manager2.end_hold(lambda text: None, errors.append)
    _settle(lambda: bool(errors))
    assert manager2.has_failed_hold()
    assert manager2.discard_failed_hold() is True
    assert not manager2.has_failed_hold()


@pytest.mark.basic
def test_the_palette_offers_retry_and_discard_for_a_kept_recording(palette, monkeypatch) -> None:
    window, controller = palette
    voice = controller.voice_manager
    state = {"kept": True, "retried": 0, "discarded": 0}
    voice.has_failed_hold = lambda: state["kept"]
    voice.failed_hold_seconds = lambda: 3.0

    def retry(on_transcription, on_error=None):
        state["retried"] += 1
        return True

    def discard():
        state["discarded"] += 1
        state["kept"] = False
        return True

    voice.retry_failed_hold = retry
    voice.discard_failed_hold = discard

    window._on_hold_transcription_failed("[Errno 61] Connection refused")
    banner = window.kept_recording_banner
    assert not banner.isHidden()
    text = banner.text()
    assert "Not sent." in text and "kept:retry" in text and "kept:discard" in text
    assert "Connection refused" in text

    window._on_kept_recording_link("kept:retry")
    assert state["retried"] == 1
    assert "again" in banner.text()

    window._on_kept_recording_link("kept:discard")
    assert state["discarded"] == 1
    assert banner.isHidden()
