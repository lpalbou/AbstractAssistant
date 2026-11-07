"""One voice turn per press (Qt-free state machine, 0.18.2).

Before 0.18.2 the orb's voice conversation was a hands-free loop: after each
reply it listened again, and in a quiet room the speech-to-text model turned
silence into "Thank you." four times, each sent as a message. A press is now
ONE utterance, like the Apple Watch's orb.
"""

from __future__ import annotations

from typing import List

import pytest

from abstractassistant.core.voice_conversation import (
    VOICE_CONVERSATION_SYSTEM_PROMPT,
    VoiceConversation,
)


class _Voice:
    """The parts of GatewayVoiceManager a voice turn uses."""

    def __init__(self, *, start_ok: bool = True) -> None:
        self.start_ok = start_ok
        self.calls: List[str] = []
        self.meter = "unset"
        self.holding = False
        self.heard = False
        self.capture_kwargs: dict = {}
        self.transcribe_kwargs: dict = {}

    def set_audio_meter_callback(self, cb) -> None:
        self.meter = cb

    def begin_hold(self, **kwargs) -> bool:
        self.calls.append("begin_hold")
        if not self.start_ok:
            raise RuntimeError("Gateway STT unavailable (microphone not available)")
        self.capture_kwargs = kwargs
        self.holding = True
        return True

    def hold_heard_speech(self) -> bool:
        return self.holding and self.heard

    def end_hold(self, **kwargs) -> bool:
        self.calls.append("end_hold")
        self.transcribe_kwargs = kwargs
        self.holding = False
        return True

    def cancel_hold(self) -> None:
        self.calls.append("cancel_hold")
        self.holding = False

    def stop_speaking(self) -> None:
        self.calls.append("stop_speaking")

    # The continuous recognizer: a voice turn must never use it.
    def listen(self, **kwargs) -> bool:  # pragma: no cover - asserted absent
        self.calls.append("listen")
        return True

    def resume_listening(self) -> bool:  # pragma: no cover - asserted absent
        self.calls.append("resume_listening")
        return True


def _turn(voice=None, *, auto_send=True):
    sent: List[str] = []
    states: List[str] = []
    voice = voice or _Voice()
    conv = VoiceConversation(
        voice_manager=voice,
        on_send=sent.append,
        on_state=states.append,
        on_level=lambda level: None,
        auto_send=auto_send,
    )
    return conv, voice, sent, states


def _start(conv) -> None:
    assert conv.start(
        capture_kwargs={"on_utterance_end": lambda reason: None},
        transcribe_kwargs={"on_transcription": lambda text: None},
    )


@pytest.mark.basic
def test_a_press_opens_the_microphone_for_one_utterance() -> None:
    conv, voice, _sent, states = _turn()
    _start(conv)
    assert voice.calls == ["begin_hold"]  # the one-turn recording, never the recognizer loop
    assert "on_utterance_end" in voice.capture_kwargs
    assert callable(voice.meter)
    assert states == ["starting", "listening"]
    assert conv.active


@pytest.mark.basic
def test_start_failure_is_an_error_state_with_the_cause() -> None:
    conv, _voice, _sent, states = _turn(_Voice(start_ok=False))
    assert conv.start() is False
    assert conv.state == "error"
    assert "microphone" in conv.error
    assert states[-1] == "error"
    assert not conv.active


@pytest.mark.basic
def test_after_one_utterance_nothing_more_is_heard_or_sent() -> None:
    """The operator's report: the loop listened again after the reply and sent
    "Thank you." and "Cough, cough." from a quiet room. One turn, then off."""
    conv, voice, sent, states = _turn()
    _start(conv)
    voice.heard = True

    conv.utterance_ended()  # about one second of silence after speech
    assert voice.calls == ["begin_hold", "end_hold"]
    assert conv.state == "transcribing"

    conv.transcribed("what's the weather like")
    assert sent == ["what's the weather like"]
    assert conv.state == "thinking"

    conv.run_finished(will_speak=True)
    assert conv.state == "speaking"
    conv.speech_finished()

    assert conv.state == "off"
    assert conv.outcome == "answered"
    assert not conv.active
    # Nothing reopened the microphone after the reply.
    assert "listen" not in voice.calls and "resume_listening" not in voice.calls
    assert voice.calls.count("begin_hold") == 1
    # A transcript arriving now (a late one, or silence turned into words)
    # is never sent.
    conv.transcribed("Thank you.")
    conv.utterance_ended()
    assert sent == ["what's the weather like"]
    assert states[-1] == "off"


@pytest.mark.basic
def test_a_reply_with_nothing_to_speak_also_ends_the_turn() -> None:
    conv, voice, sent, _states = _turn()
    _start(conv)
    voice.heard = True
    conv.utterance_ended()
    conv.transcribed("set a timer")
    conv.run_finished(will_speak=False)
    assert conv.state == "off"
    assert sent == ["set a timer"]
    assert voice.calls.count("begin_hold") == 1


@pytest.mark.basic
def test_silence_with_no_speech_ends_the_turn_with_nothing_sent() -> None:
    conv, voice, sent, _states = _turn()
    _start(conv)
    voice.heard = False
    conv.utterance_ended()  # the endpoint's "no_speech"
    assert conv.state == "off"
    assert conv.outcome == "nothing_heard"
    assert "end_hold" not in voice.calls  # nothing went to the gateway
    assert "cancel_hold" in voice.calls
    assert sent == []


@pytest.mark.basic
def test_a_press_while_listening_sends_what_was_said() -> None:
    conv, voice, sent, _states = _turn()
    _start(conv)
    voice.heard = True
    assert conv.finish_listening() is True  # the orb, pressed mid-turn
    assert "end_hold" in voice.calls
    conv.transcribed("call mum")
    assert sent == ["call mum"]


@pytest.mark.basic
def test_a_press_while_listening_cancels_when_nothing_was_said() -> None:
    conv, voice, sent, _states = _turn()
    _start(conv)
    assert conv.finish_listening() is False
    assert conv.state == "off"
    assert conv.outcome == "nothing_heard"
    assert "end_hold" not in voice.calls
    assert sent == []


@pytest.mark.basic
def test_an_empty_transcript_sends_nothing() -> None:
    conv, voice, sent, _states = _turn()
    _start(conv)
    voice.heard = True
    conv.utterance_ended()
    conv.transcribed("   ")
    assert sent == []
    assert conv.outcome == "nothing_heard"


@pytest.mark.basic
def test_a_failed_transcription_ends_the_turn_with_nothing_sent() -> None:
    conv, voice, sent, _states = _turn()
    _start(conv)
    voice.heard = True
    conv.utterance_ended()
    conv.transcription_failed("gateway refused the connection")
    assert conv.state == "off"
    assert conv.outcome == "not_sent"
    assert sent == []


@pytest.mark.basic
def test_stop_cancels_the_recording_and_any_speech() -> None:
    conv, voice, sent, states = _turn()
    _start(conv)
    voice.heard = True
    conv.stop()  # Esc
    assert sent == []
    assert conv.state == "off"
    assert conv.outcome == "cancelled"
    assert "end_hold" not in voice.calls
    assert "cancel_hold" in voice.calls and "stop_speaking" in voice.calls
    assert voice.meter is None
    assert states[-1] == "off"


@pytest.mark.basic
def test_stop_with_reason_reports_an_error_state() -> None:
    conv, _voice, _sent, _states = _turn()
    _start(conv)
    conv.stop(reason="gateway speech input went away")
    assert conv.state == "error"
    assert conv.error == "gateway speech input went away"


@pytest.mark.basic
def test_a_failed_run_ends_the_turn() -> None:
    conv, voice, _sent, _states = _turn()
    _start(conv)
    voice.heard = True
    conv.utterance_ended()
    conv.transcribed("do something")
    conv.run_failed("gateway 500")
    assert conv.state == "off"
    assert conv.outcome == "failed"
    assert voice.calls.count("begin_hold") == 1


@pytest.mark.basic
def test_handing_the_words_to_the_message_box_ends_the_turn() -> None:
    conv, voice, _sent, _states = _turn(auto_send=False)
    _start(conv)
    voice.heard = True
    conv.utterance_ended()
    conv.transcribed("dictated text")
    conv.hand_over()
    assert conv.state == "off"
    assert conv.outcome == "handed_over"


@pytest.mark.basic
def test_spoken_style_prompt_forbids_markup_and_asks_for_brevity() -> None:
    text = VOICE_CONVERSATION_SYSTEM_PROMPT.lower()
    assert "markdown" in text
    assert "short" in text or "brief" in text
    assert "voice mode" in text  # the "do not mention" rule


@pytest.mark.basic
def test_a_silent_or_stalled_microphone_still_ends_the_turn() -> None:
    """Review A6: the turn polls the recording's wall-clock limits on a timer, so a
    microphone that delivers no frames (no endpoint callback ever) still ends it."""
    jobs: list = []
    voice = _Voice()
    reasons = [None, None, "no_speech"]
    voice.poll_hold_endpoint = lambda: reasons.pop(0) if reasons else None
    conv = VoiceConversation(voice_manager=voice, on_send=lambda t: None,
                             schedule=lambda delay, fn: jobs.append((delay, fn)))
    _start(conv)
    assert len(jobs) == 1 and jobs[0][0] <= 0.5
    for _ in range(3):
        _delay, fn = jobs.pop(0)
        fn()
    assert conv.state == "off" and conv.outcome == "nothing_heard"
    assert jobs == []  # the watch stops with the turn

    jobs.clear()
    voice2 = _Voice()
    voice2.heard = True
    voice2.poll_hold_endpoint = lambda: "silence"
    conv2 = VoiceConversation(voice_manager=voice2, on_send=lambda t: None,
                              schedule=lambda delay, fn: jobs.append((delay, fn)))
    _start(conv2)
    jobs.pop(0)[1]()
    assert conv2.state == "transcribing" and "end_hold" in voice2.calls
