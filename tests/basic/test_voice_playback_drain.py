"""Exercise drain policy with virtual time and real generation/pause state."""

import threading
from types import SimpleNamespace

import pytest

from abstractassistant.core import gateway_voice_manager as module


class Clock:
    now = 0.0
    tick = None

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.tick:
            self.tick(self.now)
        assert self.now < 10, "drain failed to terminate"


class Player:
    def __init__(self):
        self.is_playing = True
        self.written = 0
        self.recoveries = 0
        self.active = True

    def playback_status(self):
        return dict(frames_written=self.written, pending_frames=int(self.is_playing),
                    stream_active=self.active, paused=False, sample_rate=48000,
                    callback_error="")

    def recover_stream(self, *, cancelled):
        self.recoveries += 1
        return not cancelled()


@pytest.fixture
def drain(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(module, "time", clock)
    vm = module.GatewayVoiceManager(llm_manager=SimpleNamespace())
    player = Player()
    notices = []
    vm.on_speech_notice = notices.append
    return vm, player, clock, notices


def test_pause_can_outlast_entire_playback_budget_even_with_stale_end_event(drain):
    vm, player, clock, notices = drain
    vm._paused = True
    ended = threading.Event()
    ended.set()  # delayed end notification from a previous temporary queue gap

    def tick(now):
        if now >= 2:
            vm._paused = False
            player.written += 1
        if now >= 2.15:
            player.is_playing = False
    clock.tick = tick
    assert vm._wait_for_stream_playback_drain(player, ended, timeout_s=.09)
    assert clock.now >= 2.15
    assert player.recoveries == 0
    assert notices == []


def test_progressing_audio_has_no_wall_clock_completion_deadline(drain):
    vm, player, clock, _ = drain
    def tick(now):
        player.written += 480
        if now >= 1:
            player.is_playing = False
    clock.tick = tick
    assert vm._wait_for_stream_playback_drain(player, threading.Event(), timeout_s=.09)
    assert clock.now >= 1
    assert player.recoveries == 0


@pytest.mark.parametrize("active", [False, True])
def test_stalled_output_recovers_once_then_continues(drain, active):
    vm, player, clock, notices = drain
    player.active = active  # both inactive and active-but-not-consuming outputs
    def tick(now):
        if player.recoveries:
            player.written += 480
            if now > .3:
                player.is_playing = False
    clock.tick = tick
    assert vm._wait_for_stream_playback_drain(player, threading.Event(), timeout_s=.09)
    assert player.recoveries == 1
    assert len(notices) == 1


def test_stale_completion_event_cannot_hide_failed_output(drain):
    vm, player, clock, _ = drain
    ended = threading.Event()
    ended.set()
    assert not vm._wait_for_stream_playback_drain(player, ended, timeout_s=.09)
    assert player.recoveries == 1
    assert .18 <= clock.now < .3  # bounded second stall; no infinite reopen loop


@pytest.mark.parametrize("superseded", [False, True])
def test_cancelled_or_superseded_generation_exits_without_waiting(drain, superseded):
    vm, player, clock, _ = drain
    vm._stream_id = "next" if superseded else "current"
    stopped = threading.Event()
    if not superseded:
        stopped.set()
    assert not vm._wait_for_stream_playback_drain(
        player, threading.Event(), timeout_s=100, stream_id="current", stop_gate=stopped)
    assert clock.now == 0
    assert player.recoveries == 0


def test_stop_during_pause_ends_wait_promptly(drain, monkeypatch):
    vm, player, clock, _ = drain
    stopped = threading.Event()
    vm._paused = True
    clock.tick = lambda now: stopped.set()
    monkeypatch.setattr(stopped, "wait", clock.sleep)
    assert not vm._wait_for_stream_playback_drain(
        player, threading.Event(), timeout_s=100, stop_gate=stopped)
    assert clock.now == .03
    assert player.recoveries == 0


def test_recovery_does_not_report_success_for_superseded_generation(drain, monkeypatch):
    vm, player, clock, notices = drain
    vm._stream_id = "current"
    def recover(*, cancelled):
        vm._stream_id = "next"
        assert cancelled()
        return False
    monkeypatch.setattr(player, "recover_stream", recover)
    assert not vm._wait_for_stream_playback_drain(
        player, threading.Event(), timeout_s=.09, stream_id="current")
    assert notices == []


def test_old_player_without_telemetry_keeps_pause_aware_duration_budget(drain):
    vm, _, clock, _ = drain
    player = SimpleNamespace(is_playing=True)
    assert not vm._wait_for_stream_playback_drain(player, threading.Event(), timeout_s=.09)
    assert .09 <= clock.now < .15


def test_gui_stop_during_native_reopen_retires_without_waiting(monkeypatch):
    import time
    import numpy as np
    from abstractvoice.tts.tts_engine import NonBlockingAudioPlayer

    vm = module.GatewayVoiceManager(llm_manager=SimpleNamespace())
    player = NonBlockingAudioPlayer()
    vm._inprocess_player = player
    vm._playback_backend = "inprocess"
    vm._speaking = True
    _, _, stopped = vm._start_stream_control()
    player.audio_queue.put(np.ones(10, dtype=np.float32))
    player.is_playing = True
    opening, release, finished = threading.Event(), threading.Event(), threading.Event()
    results = []
    def open_output():
        opening.set()
        assert release.wait(2)
    monkeypatch.setattr(player, "start_stream", open_output)
    def recover():
        try:
            results.append(player.recover_stream(cancelled=stopped.is_set))
        finally:
            finished.set()
    worker = threading.Thread(target=recover, daemon=True)
    worker.start()
    try:
        assert opening.wait(1)
        before = time.monotonic()
        vm.stop_speaking()  # caller is the GUI; hardware open is still blocked
        assert time.monotonic() - before < .2
        assert stopped.is_set()
        assert vm._inprocess_player is None
        assert not vm.is_speaking()
        newer_player = object()
        vm._inprocess_player = newer_player
        vm._speaking = True
        release.set()
        assert finished.wait(1)
        assert results == [False]
        assert player.playback_status()["pending_frames"] == 0
        assert vm._inprocess_player is newer_player
        assert vm._speaking
    finally:
        release.set()
        worker.join(2)


@pytest.mark.parametrize("message_key", ["id:same-card", ""])
def test_retired_completion_cannot_finish_new_card_or_voice_conversation(message_key):
    from abstractassistant.app import AssistantPalette

    old_token, new_token = object(), object()
    outcomes = []
    palette = SimpleNamespace(
        _active_speech_request_token=new_token,
        _on_message_speech_finished=lambda key: outcomes.append(key),
        _on_voice_speech_finished=lambda: outcomes.append("conversation"),
    )
    palette._state = lambda name, default=None: getattr(palette, name, default)
    AssistantPalette._on_speech_request_finished(palette, old_token, message_key)
    assert outcomes == []
    assert palette._active_speech_request_token is new_token
    AssistantPalette._on_speech_request_finished(palette, new_token, message_key)
    assert outcomes == [message_key or "conversation"]
    # Even a duplicate native completion cannot finish the same request twice.
    AssistantPalette._on_speech_request_finished(palette, new_token, message_key)
    assert len(outcomes) == 1
