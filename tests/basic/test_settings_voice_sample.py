"""Settings → Models → Voice output: choosing a voice plays a sample (the kit's picker).

The kit (ui-kit voice_settings.tsx `chooseSample` / `toggleSample`): a choice plays
the voice, a newer choice aborts the older sample, the play/stop toggle stops it,
nothing plays on its own when Settings opens. The desktop does it through its own
TTS path (`voice_manager.speak`), with the voice the route now uses, and never over
a reply that is being read aloud.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abstractassistant.gateway_service import ChoiceItem
from abstractassistant.ui.settings.route_editor import VOICE_SAMPLE_TEXT

import test_settings_pages as tsp


class _Voice:
    """The voice manager's surface the sample uses; records what each speak would say with."""

    def __init__(self, controller) -> None:
        self.controller = controller
        self.calls: list = []
        self.stops = 0
        self.speaking = False

    def speak(self, text, speed=1.0, callback=None, *, on_failure=None, on_notice=None):
        override = self.controller.overrides.get("output.voice") or {}
        self.calls.append({"text": text, "voice": (override.get("options") or {}).get("voice", ""),
                           "callback": callback, "on_failure": on_failure, "on_notice": on_notice})
        return True

    def stop_speaking(self) -> None:
        self.stops += 1
        self.speaking = False

    def is_speaking(self) -> bool:
        return self.speaking

    def is_paused(self) -> bool:
        return False

    def output_device_label(self):
        return "MacBook Pro Speakers"

    def output_volume_state(self):
        return (62, False)


class _Controller(tsp._Controller):
    def __init__(self) -> None:
        super().__init__()
        self.overrides = {"output.voice": {"provider": "abstractvoice", "model": "qwen3-tts"}}
        self.voice_manager = _Voice(self)

    def provider_choices(self, **kwargs):
        return [ChoiceItem(id="lmstudio", label="lmstudio"), ChoiceItem(id="abstractvoice", label="abstractvoice")]

    def model_choices(self, **kwargs):
        if kwargs.get("provider") == "abstractvoice":
            return [ChoiceItem(id="qwen3-tts", label="qwen3-tts")]
        return super().model_choices(**kwargs)

    def voice_choices(self, **kwargs):
        return [ChoiceItem(id="aiden", label="Aiden"), ChoiceItem(id="sisko", label="Sisko")]

    def save_route_override(self, **kwargs):
        self.overrides[kwargs["route_key"]] = {
            "provider": kwargs["provider"], "model": kwargs["model"], "options": dict(kwargs.get("options") or {})
        }


def _open():
    ctl = _Controller()
    dlg, _ = tsp._dialog(ctl)
    dlg.show()
    dlg.show_section("models", "output.voice")
    tsp._app().processEvents()
    editor = dlg.route_editor
    editor.voice_sample._pending.setInterval(0)
    return dlg, editor, ctl.voice_manager


def _choose(editor, voice_id: str) -> None:
    """What a person's pick does: the selection (applies the route), then `activated`."""
    index = editor.voice_combo.findData(voice_id)
    assert index > 0, voice_id
    editor.voice_combo.setCurrentIndex(index)
    editor.voice_combo.activated.emit(index)
    tsp._app().processEvents()


@pytest.mark.basic
def test_opening_settings_and_the_voice_route_plays_nothing() -> None:
    dlg, editor, voice = _open()
    assert editor.sample_button.isVisible()
    assert editor.sample_button.toolTip() == "Play a sample"
    assert voice.calls == []
    dlg.close()


@pytest.mark.basic
def test_choosing_a_voice_synthesizes_one_sample_with_that_voice() -> None:
    dlg, editor, voice = _open()
    _choose(editor, "aiden")
    assert [(c["text"], c["voice"]) for c in voice.calls] == [(VOICE_SAMPLE_TEXT, "aiden")]
    assert editor.voice_sample.state == "loading"
    assert editor.sample_note.isVisible() and editor.sample_note.text() == "Synthesizing a sample…"
    assert editor.sample_button.toolTip() == "Synthesizing… (click to cancel)"
    # The audio starts: playing, the button stops it.
    voice.speaking = True
    editor.voice_sample._tick()
    assert editor.voice_sample.state == "playing" and editor.sample_note.text() == "Playing a sample…"
    assert editor.sample_button.toolTip() == "Stop"
    # It ends: idle, no words left.
    voice.speaking = False
    voice.calls[0]["callback"]()
    tsp._app().processEvents()
    assert editor.voice_sample.state == "idle" and not editor.sample_note.isVisible()
    dlg.close()


@pytest.mark.basic
def test_a_newer_choice_aborts_the_older_sample() -> None:
    dlg, editor, voice = _open()
    _choose(editor, "aiden")
    voice.speaking = True
    editor.voice_sample._tick()
    _choose(editor, "sisko")
    assert voice.stops == 1, "the older sample was not stopped"
    assert [c["voice"] for c in voice.calls] == ["aiden", "sisko"]
    # The older sample's late end is not news: the newer one is still on its way.
    voice.calls[0]["callback"]()
    tsp._app().processEvents()
    assert editor.voice_sample.state == "loading"
    dlg.close()


@pytest.mark.basic
def test_the_toggle_stops_the_sample_then_plays_it_again() -> None:
    dlg, editor, voice = _open()
    _choose(editor, "aiden")
    voice.speaking = True
    editor.voice_sample._tick()
    editor.sample_button.click()
    assert voice.stops == 1 and editor.voice_sample.state == "idle"
    assert editor.sample_button.toolTip() == "Play a sample"
    editor.sample_button.click()
    assert [c["voice"] for c in voice.calls] == ["aiden", "aiden"]
    dlg.close()


@pytest.mark.basic
def test_a_reply_being_read_aloud_is_never_cut_by_a_sample() -> None:
    dlg, editor, voice = _open()
    voice.speaking = True  # a reply
    _choose(editor, "aiden")
    assert voice.calls == [] and voice.stops == 0
    assert "a reply is being read aloud" in editor.sample_note.text()
    dlg.close()


@pytest.mark.basic
def test_a_failed_sample_says_why_in_the_kits_words() -> None:
    dlg, editor, voice = _open()
    _choose(editor, "aiden")
    voice.calls[0]["on_failure"]("the gateway does not currently offer text-to-speech")
    voice.calls[0]["callback"]()
    tsp._app().processEvents()
    assert editor.voice_sample.state == "idle"
    assert editor.sample_note.text() == "The sample did not play: the gateway does not currently offer text-to-speech."
    dlg.close()


@pytest.mark.basic
def test_leaving_the_route_ends_the_sample() -> None:
    dlg, editor, voice = _open()
    _choose(editor, "aiden")
    dlg.show_section("models", "output.text")
    tsp._app().processEvents()
    assert editor.voice_sample.state == "idle" and voice.stops == 1
    assert not editor.sample_button.isVisible()
    dlg.close()
