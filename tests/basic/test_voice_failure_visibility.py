"""Regression tests: a speak() that does not play must always say WHY.

Live 2026-08-02, session sess_ec807fb784d942298db98d271e51903e ("The Garden in
the Log"): clicking the speaker on a 3,549-char reply had its pinned voice
model rejected by the gateway (404) after 0.5 s, timed out the retried stream
after 120 s, timed out the single-shot fallback after another 120 s, emitted
three `#FALLBACK` warnings nobody can see in a GUI, and told the user NOTHING —
the card simply went back to idle. These tests pin the visible-failure
contract at both layers: the voice manager reports a concrete cause through
`on_speech_error`, and the palette turns that into a banner.
"""

from __future__ import annotations

import base64
import io
import threading
import time
import wave
from types import SimpleNamespace

import pytest

from abstractassistant import app as _app_module
from abstractassistant.app import AssistantPalette
from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager
from abstractassistant.core.speech_text import speech_plain_text

_PALETTE_SOURCE = __import__("pathlib").Path(_app_module.__file__).read_text(
    encoding="utf-8"
)


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * 240)
    return buf.getvalue()


def _wait_for(predicate, *, timeout_s: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


class _Gateway:
    """Minimal gateway stub; the streaming lane is opt-in per test."""

    def __init__(self) -> None:
        self._cfg = SimpleNamespace(timeout_s=30.0)
        self.streaming = False
        self.stream_events: list[dict] = []
        self.artifact_error: Exception | None = None

    def discovery_capabilities(self):
        tts = {
            "available": True,
            "formats": ["wav"],
            "voices": [],
            "active_model": "gateway-default-model",
        }
        if self.streaming:
            tts.update(
                {
                    "streaming": True,
                    "delivery_modes": ["artifact", "stream"],
                    "stream_endpoint": "/api/gateway/runs/{run_id}/voice/tts/stream",
                    "stream_transport": "jsonl",
                }
            )
        return {
            "capabilities": {
                "contracts": {
                    "version": 1,
                    "assistant": {
                        "voice": {
                            "tts": tts,
                            "stt": {"available": False, "content_types": ["audio/wav"]},
                        }
                    },
                }
            }
        }

    def voice_tts(self, **kwargs):
        if self.artifact_error is not None:
            raise self.artifact_error
        return {"audio_artifact": {"$artifact": "art_1"}}

    def download_run_artifact_content(self, **kwargs):
        return _wav_bytes(), "audio/wav"

    def voice_tts_stream(self, **kwargs):
        for event in self.stream_events:
            yield event


class _Manager:
    def __init__(self, gateway: _Gateway) -> None:
        self.active_session_id = "sess_probe"
        self._gateway = gateway
        self.current_tts_provider = ""
        self.current_tts_model = ""
        self.current_tts_voice = ""
        self.current_tts_voice_mode = ""

    def gateway_client(self) -> _Gateway:
        return self._gateway


def _manager_with_errors(gateway: _Gateway) -> tuple[GatewayVoiceManager, list[str]]:
    vm = GatewayVoiceManager(llm_manager=_Manager(gateway), debug_mode=False)
    reported: list[str] = []
    vm.on_speech_error = reported.append
    return vm, reported


# --------------------------------------------------------------------------
# Voice manager: synchronous refusals
# --------------------------------------------------------------------------


@pytest.mark.basic
def test_speak_reports_when_there_is_nothing_to_say() -> None:
    vm, reported = _manager_with_errors(_Gateway())

    with pytest.warns(UserWarning):
        assert vm.speak("   \n  ") is False

    assert len(reported) == 1
    assert "nothing to read aloud" in reported[0].lower()


@pytest.mark.basic
def test_speak_refusal_names_the_missing_audio_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"TTS unsupported" must say WHICH side is missing: the two causes need
    opposite user actions (install voice extras vs fix the gateway)."""
    vm, reported = _manager_with_errors(_Gateway())
    monkeypatch.setattr(vm, "_audio_player_available", lambda: False)

    with pytest.warns(UserWarning):
        assert vm.speak("hello") is False

    assert len(reported) == 1
    assert "audio output backend" in reported[0]


@pytest.mark.basic
def test_speak_refusal_names_the_unreachable_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _Gateway()

    def _boom():
        raise RuntimeError("connection refused")

    gateway.discovery_capabilities = _boom  # type: ignore[assignment]
    vm, reported = _manager_with_errors(gateway)
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)

    with pytest.warns(UserWarning):
        assert vm.speak("hello") is False

    assert len(reported) == 1
    assert "gateway could not be reached" in reported[0]
    assert "connection refused" in reported[0]


# --------------------------------------------------------------------------
# Voice manager: asynchronous failures (the operator's actual case)
# --------------------------------------------------------------------------


@pytest.mark.basic
def test_stream_rejection_then_fallback_failure_reports_the_whole_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live 2026-08-02 failure, in miniature.

    Stream rejected pre-audio + artifact fallback raising = exactly one
    user-visible report naming BOTH causes, and the completion still fires
    once so the card leaves "synthesizing"."""
    gateway = _Gateway()
    gateway.streaming = True
    gateway.stream_events = [
        {"type": "runtime_start", "ok": True},
        {
            "type": "error",
            "ok": False,
            "error": "audio/speech failed (404): The model `x-3` does not exist",
        },
    ]
    gateway.artifact_error = TimeoutError()

    vm, reported = _manager_with_errors(gateway)
    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: object())

    completions: list[int] = []
    with pytest.warns(UserWarning):
        assert vm.speak("a long reply", callback=lambda: completions.append(1)) is True
        assert _wait_for(lambda: completions == [1])

    assert len(reported) == 1, reported
    assert "404" in reported[0]
    assert "x-3" in reported[0]
    # str(TimeoutError()) is "" — the reason must still name the failure.
    assert "TimeoutError" in reported[0]


@pytest.mark.basic
def test_artifact_leg_failure_reports_a_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _Gateway()
    gateway.artifact_error = RuntimeError("gateway said 500")
    vm, reported = _manager_with_errors(gateway)
    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_speak_gateway_stream", lambda **kwargs: None)

    completions: list[int] = []
    with pytest.warns(UserWarning):
        assert vm.speak("hello", callback=lambda: completions.append(1)) is True
        assert _wait_for(lambda: completions == [1])

    assert len(reported) == 1
    assert "gateway said 500" in reported[0]


@pytest.mark.basic
def test_playback_refusal_after_successful_synthesis_reports_a_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audio arrived but nothing could play it: still a visible failure."""
    gateway = _Gateway()
    vm, reported = _manager_with_errors(gateway)
    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_speak_gateway_stream", lambda **kwargs: None)
    monkeypatch.setattr(
        vm, "_play_audio_bytes", lambda audio_bytes, content_type, callback=None: False
    )

    completions: list[int] = []
    with pytest.warns(UserWarning):
        assert vm.speak("hello", callback=lambda: completions.append(1)) is True
        assert _wait_for(lambda: completions == [1])

    assert len(reported) == 1
    assert "played locally" in reported[0]


@pytest.mark.basic
def test_mid_stream_abort_reports_partial_playback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audio started, then the gateway sent an empty chunk: say it was cut."""
    gateway = _Gateway()
    gateway.streaming = True
    gateway.stream_events = [
        {"type": "runtime_start", "ok": True},
        {"type": "audio", "audio_b64": base64.b64encode(_wav_bytes()).decode("ascii")},
        {"type": "audio", "audio_b64": ""},
    ]

    vm, reported = _manager_with_errors(gateway)
    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_begin_stream_playback", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: object())
    monkeypatch.setattr(
        vm, "_configure_stream_playback_callbacks", lambda player, drained: None
    )
    monkeypatch.setattr(
        vm, "_queue_stream_wav_chunk", lambda audio_bytes, *, playback_drained: 0.01
    )

    completions: list[int] = []
    with pytest.warns(UserWarning):
        assert vm.speak("hello", callback=lambda: completions.append(1)) is True
        assert _wait_for(lambda: completions == [1])

    assert len(reported) == 1
    assert "part-way" in reported[0]


@pytest.mark.basic
def test_undecodable_chunk_reports_a_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _Gateway()
    gateway.streaming = True
    gateway.stream_events = [
        {"type": "runtime_start", "ok": True},
        {"type": "audio", "audio_b64": base64.b64encode(b"not-a-wav").decode("ascii")},
    ]

    vm, reported = _manager_with_errors(gateway)
    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_begin_stream_playback", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: object())
    monkeypatch.setattr(
        vm, "_configure_stream_playback_callbacks", lambda player, drained: None
    )

    completions: list[int] = []
    with pytest.warns(UserWarning):
        assert vm.speak("hello", callback=lambda: completions.append(1)) is True
        assert _wait_for(lambda: completions == [1])

    assert len(reported) == 1
    assert "could not decode" in reported[0]


@pytest.mark.basic
def test_successful_speech_reports_no_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The visible-failure channel must stay quiet when speech actually plays."""
    gateway = _Gateway()
    gateway.streaming = True
    gateway.stream_events = [
        {"type": "runtime_start", "ok": True},
        {"type": "audio", "audio_b64": base64.b64encode(_wav_bytes()).decode("ascii")},
        {"type": "done", "ok": True},
    ]

    vm, reported = _manager_with_errors(gateway)
    monkeypatch.setattr(vm, "supports_tts", lambda: True)
    monkeypatch.setattr(vm, "_audio_player_available", lambda: True)
    monkeypatch.setattr(vm, "_supports_inprocess_audio_player", lambda: True)
    monkeypatch.setattr(vm, "_begin_stream_playback", lambda: True)
    monkeypatch.setattr(vm, "_ensure_inprocess_audio_player", lambda: object())
    monkeypatch.setattr(
        vm, "_configure_stream_playback_callbacks", lambda player, drained: None
    )
    monkeypatch.setattr(
        vm, "_queue_stream_wav_chunk", lambda audio_bytes, *, playback_drained: 0.01
    )
    monkeypatch.setattr(
        vm,
        "_wait_for_stream_playback_drain",
        lambda player, drained, *, timeout_s: True,
    )

    completions: list[int] = []
    assert vm.speak("hello", callback=lambda: completions.append(1)) is True
    assert _wait_for(lambda: completions == [1])
    assert reported == []


@pytest.mark.basic
def test_user_stop_is_not_reported_as_a_failure() -> None:
    """A stop is an answer, not an error: no banner for a deliberate stop."""
    vm, reported = _manager_with_errors(_Gateway())
    vm._begin_speech_failure_tracking()
    vm._note_speech_failure("the stream ended early")

    ends: list[int] = []
    vm.on_speech_end = lambda: ends.append(1)
    vm._fire_speech_completion(None, cancelled=True)

    assert reported == []
    assert ends == [1]


@pytest.mark.basic
def test_superseded_generation_cannot_raise_a_stale_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Speaking message B must not surface A's teardown as a failure."""
    vm, reported = _manager_with_errors(_Gateway())
    vm._begin_speech_failure_tracking()
    vm._note_speech_failure("first generation was abandoned")

    vm.stop_speaking()  # user clicked another message's speaker
    vm._fire_speech_completion(None)

    assert reported == []

    # …and the next dispatch can still report its own failure.
    vm._begin_speech_failure_tracking()
    vm._note_speech_failure("second generation really failed")
    with pytest.warns(UserWarning):
        vm._fire_speech_completion(None)
    assert reported == ["second generation really failed"]


@pytest.mark.basic
def test_failure_report_fires_at_most_once_per_dispatch() -> None:
    vm, reported = _manager_with_errors(_Gateway())
    vm._begin_speech_failure_tracking()
    with pytest.warns(UserWarning):
        vm._report_speech_failure("first cause")
    vm._report_speech_failure("second cause")
    assert reported == ["first cause"]


@pytest.mark.basic
def test_exception_reason_never_returns_an_empty_string() -> None:
    """`str(TimeoutError())` is "" — the live failure that said nothing."""
    assert GatewayVoiceManager._exception_reason(TimeoutError()) == "TimeoutError"
    assert (
        GatewayVoiceManager._exception_reason(RuntimeError("boom"))
        == "RuntimeError: boom"
    )


# --------------------------------------------------------------------------
# Palette: the failure has to reach the window
# --------------------------------------------------------------------------


@pytest.mark.basic
def test_palette_reports_when_a_reply_has_no_speakable_text() -> None:
    """An image-only/emoji-only reply sanitizes to "" — never a silent no-op."""
    banners: list[tuple[str, str]] = []
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._controller = SimpleNamespace(
        voice_manager=SimpleNamespace(
            pause=lambda: True,
            resume=lambda: True,
            stop_speaking=lambda: None,
            speak=lambda *a, **k: pytest.fail("speak() must not be called"),
            is_paused=lambda: False,
            is_speaking=lambda: False,
        )
    )
    palette._active_spoken_message_key = ""
    palette._active_spoken_message_phase = "idle"
    palette._set_banner = lambda text="", tone="neutral": banners.append((text, tone))
    palette._set_message_voice_card_state = lambda key, state: None

    message = {"id": "m1", "role": "assistant", "content": "![](sandbox:/img.png)"}
    assert speech_plain_text(str(message["content"])) == ""
    AssistantPalette._toggle_message_voice(palette, message)

    assert banners, "an unspeakable reply must explain itself"
    assert "Nothing to read aloud" in banners[-1][0]
    assert banners[-1][1] == "warning"


@pytest.mark.basic
def test_palette_speech_failure_becomes_a_banner_and_frees_the_card() -> None:
    banners: list[tuple[str, str]] = []
    card_states: list[tuple[str, str]] = []
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._active_spoken_message_key = "msg-7"
    palette._active_spoken_message_phase = "synthesizing"
    palette._set_banner = lambda text="", tone="neutral": banners.append((text, tone))
    palette._set_message_voice_card_state = lambda key, state: card_states.append(
        (key, state)
    )
    palette._controller = SimpleNamespace(
        voice_manager=SimpleNamespace(
            is_speaking=lambda: False, is_paused=lambda: False
        )
    )

    AssistantPalette._on_message_speech_failed(
        palette, "the gateway speech request failed (TimeoutError)"
    )

    assert card_states == [("msg-7", "idle")]
    assert palette._active_spoken_message_key == ""
    assert palette._active_spoken_message_phase == "idle"
    assert banners[-1][1] == "warning"
    assert "Voice failed" in banners[-1][0]
    assert "TimeoutError" in banners[-1][0]
    assert palette._voice_failure_seen is True


@pytest.mark.basic
def test_late_failure_report_does_not_reset_a_newer_live_speech() -> None:
    """A superseded run's late report must not idle the card that IS speaking."""
    banners: list[tuple[str, str]] = []
    card_states: list[tuple[str, str]] = []
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._active_spoken_message_key = "msg-new"
    palette._active_spoken_message_phase = "speaking"
    palette._set_banner = lambda text="", tone="neutral": banners.append((text, tone))
    palette._set_message_voice_card_state = lambda key, state: card_states.append(
        (key, state)
    )
    palette._controller = SimpleNamespace(
        voice_manager=SimpleNamespace(is_speaking=lambda: True, is_paused=lambda: False)
    )

    AssistantPalette._on_message_speech_failed(palette, "an older run timed out")

    assert card_states == []
    assert palette._active_spoken_message_key == "msg-new"
    assert palette._active_spoken_message_phase == "speaking"
    assert banners and "an older run timed out" in banners[-1][0]


@pytest.mark.basic
def test_palette_keeps_the_specific_cause_over_the_generic_refusal_banner() -> None:
    """A concrete cause must not be overwritten by the generic fallback text."""
    banners: list[tuple[str, str]] = []
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._active_spoken_message_key = ""
    palette._active_spoken_message_phase = "idle"
    palette._set_banner = lambda text="", tone="neutral": banners.append((text, tone))
    palette._set_message_voice_card_state = lambda key, state: None

    def _speak(text, callback=None):
        # Real managers report synchronously before returning False.
        AssistantPalette._on_message_speech_failed(
            palette, "this machine has no audio output backend for speech"
        )
        return False

    palette._controller = SimpleNamespace(
        voice_manager=SimpleNamespace(
            pause=lambda: True,
            resume=lambda: True,
            stop_speaking=lambda: None,
            speak=_speak,
            is_paused=lambda: False,
            is_speaking=lambda: False,
        )
    )

    AssistantPalette._toggle_message_voice(
        palette, {"id": "m2", "role": "assistant", "content": "Some spoken words."}
    )

    assert "no audio output backend" in banners[-1][0]
    assert "unavailable or still" not in banners[-1][0]


@pytest.mark.basic
def test_palette_generic_banner_survives_for_a_manager_that_reports_nothing() -> None:
    banners: list[tuple[str, str]] = []
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._active_spoken_message_key = ""
    palette._active_spoken_message_phase = "idle"
    palette._set_banner = lambda text="", tone="neutral": banners.append((text, tone))
    palette._set_message_voice_card_state = lambda key, state: None
    palette._controller = SimpleNamespace(
        voice_manager=SimpleNamespace(
            pause=lambda: True,
            resume=lambda: True,
            stop_speaking=lambda: None,
            speak=lambda text, callback=None: False,
            is_paused=lambda: False,
            is_speaking=lambda: False,
        )
    )

    AssistantPalette._toggle_message_voice(
        palette, {"id": "m3", "role": "assistant", "content": "Some spoken words."}
    )

    assert banners[-1][1] == "warning"
    assert "Voice couldn't start" in banners[-1][0]


@pytest.mark.basic
def test_speech_failure_banner_survives_the_completion_callback() -> None:
    """Completion clears only the "Speaking on …" notice, never the error."""
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._active_spoken_message_key = ""
    palette._active_spoken_message_phase = "idle"
    palette._set_message_voice_card_state = lambda key, state: None
    shown = {"text": "Voice failed: the gateway speech request failed."}
    palette._set_banner = lambda text="", tone="neutral": shown.update({"text": text})
    palette.banner_label = SimpleNamespace(text=lambda: shown["text"])

    AssistantPalette._on_message_speech_finished(palette, "msg-7")

    assert shown["text"].startswith("Voice failed")


@pytest.mark.basic
def test_warning_banners_use_a_tone_the_stylesheet_actually_styles() -> None:
    """`tone="warning"` matches no QSS rule; a warning must not look neutral."""
    applied: dict[str, object] = {}

    class _Label:
        def clear(self) -> None:
            applied["cleared"] = True

        def setText(self, text: str) -> None:
            applied["text"] = text

        def setProperty(self, name: str, value: object) -> None:
            applied[name] = value

        def setMinimumHeight(self, value: int) -> None:
            pass

        def setMaximumHeight(self, value: int) -> None:
            pass

        def show(self) -> None:
            pass

        def hide(self) -> None:
            pass

    palette = AssistantPalette.__new__(AssistantPalette)
    palette.banner_label = _Label()
    palette._refresh_widget_style = lambda widget: None
    palette._reflow_shell = lambda *a, **k: None

    AssistantPalette._set_banner(palette, "Voice failed: nope.", tone="warning")

    assert applied["tone"] == "warn"
    assert "QLabel#bannerLabel[tone=\"warn\"]" in _PALETTE_SOURCE


@pytest.mark.basic
def test_speech_text_never_leaks_markdown_for_an_empty_link_label() -> None:
    assert speech_plain_text("[](https://example.com)") == "link"
    assert "[" not in speech_plain_text("See [](https://example.com) please.")


@pytest.mark.basic
def test_real_reply_shapes_that_reduce_to_nothing_are_detectable() -> None:
    """These are real assistant replies, not synthetic edge cases."""
    for markdown in ("![](sandbox:/img.png)", "\U0001f44d", "---", "| --- | --- |"):
        assert speech_plain_text(markdown) == "", markdown
