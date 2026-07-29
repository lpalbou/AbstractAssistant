"""Stopping/superseding a TTS stream must CANCEL the server run, not abandon it.

Root cause of the 2026-07-28 "minutes of dead spinner" report: the client
abandoned in-flight streams without cancelling them. The abandoned stream kept
synthesizing under the gateway's per-voice lock, so the next speak() queued
behind its whole remaining synthesis; impatient re-clicks stacked the wait into
minutes. The fix: capture the stream's server child_run_id and cancel it on
stop / on the next dispatch's stop-previous.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager


class _RecordingGateway:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    def cancel_run(self, *, run_id: str, reason: str = "") -> dict:
        self.cancelled.append(str(run_id))
        return {"ok": True}


def _manager(gateway: _RecordingGateway) -> GatewayVoiceManager:
    vm = GatewayVoiceManager(llm_manager=SimpleNamespace(), debug_mode=False)
    # Route _gateway_client() at the cancel worker to our recording gateway.
    vm._gateway_client = lambda: gateway  # type: ignore[method-assign]
    return vm


def _join_cancel_threads() -> None:
    import threading
    import time

    deadline = time.time() + 2.0
    while time.time() < deadline:
        alive = [t for t in threading.enumerate() if t.name == "gateway-tts-cancel"]
        if not alive:
            return
        for t in alive:
            t.join(timeout=0.2)


@pytest.mark.basic
def test_stop_cancels_captured_child_run() -> None:
    gw = _RecordingGateway()
    vm = _manager(gw)
    stream_id, _pause, _stop = vm._start_stream_control()
    vm._record_stream_child_run(stream_id, "child-123")

    vm._stop_stream_control()
    _join_cancel_threads()

    assert gw.cancelled == ["child-123"], "stop must cancel the server-side TTS child run"


@pytest.mark.basic
def test_stop_without_child_run_does_not_call_cancel() -> None:
    gw = _RecordingGateway()
    vm = _manager(gw)
    vm._start_stream_control()  # no child id captured yet (stream never opened)

    vm._stop_stream_control()
    _join_cancel_threads()

    assert gw.cancelled == []


@pytest.mark.basic
def test_record_child_run_ignored_for_stale_stream() -> None:
    """A late child-id from a superseded stream must not overwrite the current
    stream's cancel target (the id is keyed to the stream that owns it)."""
    gw = _RecordingGateway()
    vm = _manager(gw)
    old_stream, _p, _s = vm._start_stream_control()
    new_stream, _p2, _s2 = vm._start_stream_control()  # supersede

    # A straggler event from the OLD stream tries to record its child.
    vm._record_stream_child_run(old_stream, "old-child")
    # The current stream records its own.
    vm._record_stream_child_run(new_stream, "new-child")

    vm._stop_stream_control()
    _join_cancel_threads()

    assert gw.cancelled == ["new-child"]


@pytest.mark.basic
def test_new_stream_clears_previous_child_target() -> None:
    gw = _RecordingGateway()
    vm = _manager(gw)
    s1, _p, _s = vm._start_stream_control()
    vm._record_stream_child_run(s1, "child-A")
    # Minting a new stream clears the cancel target so a later stop of the NEW
    # stream (before it opens) cannot cancel the previous child again.
    vm._start_stream_control()
    vm._stop_stream_control()
    _join_cancel_threads()

    assert gw.cancelled == []
