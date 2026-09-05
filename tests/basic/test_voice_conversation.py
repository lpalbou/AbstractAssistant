"""The hands-free voice conversation loop (Qt-free state machine)."""

from __future__ import annotations

from typing import Callable, List

import pytest

from abstractassistant.core.voice_conversation import (
    VOICE_CONVERSATION_SYSTEM_PROMPT,
    VoiceConversation,
)


class _Voice:
    def __init__(self, *, start_ok: bool = True) -> None:
        self.start_ok = start_ok
        self.calls: List[str] = []
        self.mode = ""
        self.meter = "unset"
        self.paused = False

    def set_voice_mode(self, mode: str) -> None:
        self.mode = mode

    def set_audio_meter_callback(self, cb) -> None:
        self.meter = cb

    def listen(self, **kwargs) -> bool:
        self.calls.append("listen")
        if not self.start_ok:
            raise RuntimeError("Gateway STT unavailable (microphone not available)")
        return True

    def stop_listening(self) -> None:
        self.calls.append("stop_listening")

    def stop_speaking(self) -> None:
        self.calls.append("stop_speaking")

    def pause_listening(self) -> bool:
        self.paused = True
        return True

    def resume_listening(self) -> bool:
        self.paused = False
        return True


class _Scheduler:
    def __init__(self) -> None:
        self.jobs: List[tuple[float, Callable[[], None]]] = []

    def __call__(self, delay: float, fn: Callable[[], None]) -> None:
        self.jobs.append((delay, fn))

    def fire_all(self) -> None:
        jobs, self.jobs = self.jobs, []
        for _delay, fn in jobs:
            fn()


def _loop(voice=None, *, auto_send=True, scheduler=None):
    sent: List[str] = []
    states: List[str] = []
    voice = voice or _Voice()
    conv = VoiceConversation(
        voice_manager=voice,
        on_send=sent.append,
        on_state=states.append,
        on_level=lambda level: None,
        schedule=scheduler,
        debounce_s=0.5 if scheduler is not None else 0.0,
        auto_send=auto_send,
    )
    return conv, voice, sent, states


@pytest.mark.basic
def test_start_opens_the_mic_in_wait_mode_and_listens() -> None:
    conv, voice, _sent, states = _loop()
    assert conv.start() is True
    assert voice.mode == "wait"  # the recognizer pauses while the reply plays
    assert callable(voice.meter)
    assert voice.calls == ["listen"]
    assert states == ["starting", "listening"]
    assert conv.active


@pytest.mark.basic
def test_start_failure_is_an_error_state_with_the_cause() -> None:
    conv, _voice, _sent, states = _loop(_Voice(start_ok=False))
    assert conv.start() is False
    assert conv.state == "error"
    assert "microphone" in conv.error
    assert states[-1] == "error"
    assert not conv.active


@pytest.mark.basic
def test_full_turn_listen_send_think_speak_listen() -> None:
    conv, _voice, sent, states = _loop()
    conv.start()

    conv.heard("what's the weather like")
    assert sent == ["what's the weather like"]
    assert conv.state == "thinking"
    assert conv.turns == 1

    conv.run_finished(will_speak=True)
    assert conv.state == "speaking"
    conv.speech_started()
    conv.speech_finished()
    assert conv.state == "listening"
    assert states[-3:] == ["speaking", "speaking", "listening"]


@pytest.mark.basic
def test_debounce_merges_closely_spaced_utterances_into_one_prompt() -> None:
    scheduler = _Scheduler()
    conv, _voice, sent, _states = _loop(scheduler=scheduler)
    conv.start()

    conv.heard("book a table")
    conv.heard("for two, tonight")
    assert conv.state == "heard"
    assert sent == []
    assert len(scheduler.jobs) == 2  # the second utterance re-armed the timer

    scheduler.fire_all()
    # Only the LAST armed flush is live; the stale one is a no-op.
    assert sent == ["book a table for two, tonight"]
    assert conv.state == "thinking"


@pytest.mark.basic
def test_speech_while_thinking_is_queued_for_the_next_turn_not_steered() -> None:
    conv, _voice, sent, _states = _loop()
    conv.start()
    conv.heard("first question")
    assert conv.state == "thinking"

    conv.heard("and another thing")
    assert sent == ["first question"]
    assert conv.queued_text() == "and another thing"

    conv.run_finished(will_speak=False)
    # No reply to speak: back to listening, and the queued speech goes out.
    assert sent == ["first question", "and another thing"]
    assert conv.state == "thinking"


@pytest.mark.basic
def test_pause_mutes_without_leaving_the_mode_and_resume_listens_again() -> None:
    conv, voice, _sent, _states = _loop()
    conv.start()
    assert conv.pause() is True
    assert conv.state == "paused"
    assert voice.paused is True

    conv.heard("ignored while paused")
    assert conv.pending_text() == ""

    assert conv.resume() is True
    assert conv.state == "listening"
    assert voice.paused is False


@pytest.mark.basic
def test_stop_closes_mic_and_speech_and_drops_pending_text() -> None:
    scheduler = _Scheduler()
    conv, voice, sent, states = _loop(scheduler=scheduler)
    conv.start()
    conv.heard("half a sentence")

    conv.stop()
    scheduler.fire_all()  # the armed flush must be dead after stop()

    assert sent == []
    assert conv.state == "off"
    assert "stop_listening" in voice.calls and "stop_speaking" in voice.calls
    assert voice.meter is None
    assert states[-1] == "off"


@pytest.mark.basic
def test_stop_with_reason_reports_an_error_state() -> None:
    conv, _voice, _sent, _states = _loop()
    conv.start()
    conv.stop(reason="gateway speech input went away")
    assert conv.state == "error"
    assert conv.error == "gateway speech input went away"


@pytest.mark.basic
def test_manual_mode_waits_for_send_now() -> None:
    conv, _voice, sent, _states = _loop(auto_send=False)
    conv.start()
    conv.heard("dictated text")
    assert sent == []
    assert conv.state == "heard"
    assert conv.pending_text() == "dictated text"

    assert conv.send_now() == "dictated text"
    assert sent == ["dictated text"]
    assert conv.state == "thinking"


@pytest.mark.basic
def test_run_failure_keeps_listening() -> None:
    conv, _voice, _sent, _states = _loop()
    conv.start()
    conv.heard("do something")
    conv.run_failed("gateway 500")
    assert conv.state == "listening"
    assert conv.active


@pytest.mark.basic
def test_spoken_style_prompt_forbids_markup_and_asks_for_brevity() -> None:
    text = VOICE_CONVERSATION_SYSTEM_PROMPT.lower()
    assert "markdown" in text
    assert "short" in text or "brief" in text
    assert "voice mode" in text  # the "do not mention" rule
