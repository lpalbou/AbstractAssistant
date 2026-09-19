"""Choosing the speaker spoken replies come out of (2026-09-18).

Operator: "it only output on the MBP but not on other output device (eg xreal one pro or
headphone). it is critical that we can properly select the audio output".

Before this, the Voice settings page only NAMED the system default and linked to macOS
Sound settings; there was no way to choose a device in the app, and playback did not
reliably follow the system default either (see
abstractvoice/tests/test_audio_output_device_selection.py for the engine half).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication

from abstractassistant.preferences import AssistantPreferences
from abstractassistant.ui.settings.pages import VoicePage

_APP = None


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class _Device:
    def __init__(self, name, uid, index=0, default=False):
        self.name, self.uid, self.index, self.is_system_default = name, uid, index, default
        self.channels, self.samplerate = 2, 48000.0

    @property
    def key(self):
        return self.uid or self.name


GLASSES = _Device("XREAL One Pro", "AppleUSBAudioEngine:XREAL:1", 1, default=True)
SPEAKERS = _Device("MacBook Pro Speakers", "BuiltInSpeakerDevice", 4)
HOTPLUGGED = _Device("Sony WH-1000XM5", "BT-SONY-XM5", None)


class _Voice:
    def __init__(self, devices=None):
        self._devices = devices if devices is not None else [GLASSES, SPEAKERS]
        self.spec = ""
        self.tested: list[str] = []
        self.tone_problem = ""

    def available_output_devices(self):
        return list(self._devices)

    def output_device_label(self):
        if not self.spec:
            return "System default (XREAL One Pro)"
        for device in self._devices:
            if device.key == self.spec:
                return device.name
        return f"{self.spec} (not connected)"

    def output_volume_state(self):
        return (62, False)

    def set_output_device(self, spec):
        self.spec = str(spec or "")

    def play_test_tone(self, spec=None):
        self.tested.append("" if spec is None else str(spec))
        return self.tone_problem


class _Controller:
    def __init__(self, voice=None, prefs=None):
        self.preferences = prefs or AssistantPreferences()
        self.voice_manager = voice or _Voice()
        self.saved: list[dict] = []
        # Mirrors the real AssistantController, which applies the stored choice to the
        # player as it starts up — without this the stub would let a broken wiring pass.
        self.voice_manager.set_output_device(self.preferences.audio_output_device)

    def update_preferences(self, **updates):
        payload = self.preferences.to_dict()
        payload.update(updates)
        self.preferences = AssistantPreferences.from_dict(payload)
        self.saved.append(dict(updates))
        try:
            self.voice_manager.set_output_device(self.preferences.audio_output_device)
        except Exception:
            pass
        return True


def _page(controller) -> VoicePage:
    page = VoicePage(controller, None)
    page.refresh()
    return page


# --------------------------------------------------------------------------- preference


def test_the_choice_is_persisted_as_a_uid_not_an_index() -> None:
    """An index is a position in PortAudio's list and means something else after a
    reboot or a reconnection; a UID names the physical device."""
    prefs = AssistantPreferences.from_dict(
        {"audio_output_device": "BuiltInSpeakerDevice", "audio_output_device_name": "MacBook Pro Speakers"}
    )
    assert prefs.audio_output_device == "BuiltInSpeakerDevice"
    round_tripped = AssistantPreferences.from_dict(prefs.to_dict())
    assert round_tripped.audio_output_device == "BuiltInSpeakerDevice"
    assert round_tripped.audio_output_device_name == "MacBook Pro Speakers"
    assert AssistantPreferences().audio_output_device == ""  # default: follow the system


# --------------------------------------------------------------------------- the picker


def test_the_picker_offers_the_system_default_and_every_device() -> None:
    page = _page(_Controller())
    combo = page.output_device_combo
    assert [combo.itemData(i) for i in range(combo.count())] == [
        "",
        "AppleUSBAudioEngine:XREAL:1",
        "BuiltInSpeakerDevice",
    ]
    assert combo.itemText(0) == "System default (XREAL One Pro)"
    assert combo.currentData() == ""  # nothing pinned yet


def test_a_device_connected_after_launch_is_offered_and_labelled() -> None:
    page = _page(_Controller(voice=_Voice([GLASSES, SPEAKERS, HOTPLUGGED])))
    combo = page.output_device_combo
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert "Sony WH-1000XM5 (connected after launch)" in labels


def test_a_pinned_device_that_is_unplugged_stays_selected_and_says_so() -> None:
    """Unplugging headphones must not silently discard the user's choice."""
    prefs = AssistantPreferences.from_dict(
        {"audio_output_device": "BT-SONY-XM5", "audio_output_device_name": "Sony WH-1000XM5"}
    )
    page = _page(_Controller(prefs=prefs))
    combo = page.output_device_combo
    assert combo.currentData() == "BT-SONY-XM5"
    assert combo.currentText() == "Sony WH-1000XM5 (not connected)"


def test_saving_stores_the_key_and_its_display_name_and_applies_it() -> None:
    controller = _Controller()
    page = _page(controller)
    combo = page.output_device_combo
    combo.setCurrentIndex(combo.findData("BuiltInSpeakerDevice"))
    page._save()

    assert controller.preferences.audio_output_device == "BuiltInSpeakerDevice"
    assert controller.preferences.audio_output_device_name == "MacBook Pro Speakers"
    # Applied to the live player, so the next sentence is audible on the new device.
    assert controller.voice_manager.spec == "BuiltInSpeakerDevice"


def test_choosing_the_system_default_clears_the_pin() -> None:
    prefs = AssistantPreferences.from_dict(
        {"audio_output_device": "BuiltInSpeakerDevice", "audio_output_device_name": "MacBook Pro Speakers"}
    )
    controller = _Controller(prefs=prefs)
    page = _page(controller)
    page.output_device_combo.setCurrentIndex(0)
    page._save()
    assert controller.preferences.audio_output_device == ""


def test_saving_the_page_does_not_disturb_the_other_voice_settings() -> None:
    controller = _Controller()
    page = _page(controller)
    page.auto_speak.setChecked(True)
    page.voice_mode_combo.setCurrentIndex(page.voice_mode_combo.findData("full"))
    page._save()
    assert controller.preferences.auto_speak is True
    assert controller.preferences.voice_mode == "full"


# --------------------------------------------------------------------------- the test tone


def test_the_test_button_plays_on_the_SELECTED_device_not_the_saved_one() -> None:
    """The point of Test is to try a device before committing to it."""
    controller = _Controller()
    page = _page(controller)
    combo = page.output_device_combo
    combo.setCurrentIndex(combo.findData("BuiltInSpeakerDevice"))
    page._test_output_device()
    assert controller.voice_manager.tested == ["BuiltInSpeakerDevice"]
    assert controller.preferences.audio_output_device == ""  # not saved by testing


def test_a_failing_test_tone_reports_why() -> None:
    voice = _Voice()
    voice.tone_problem = "The selected audio output (Sony WH-1000XM5) is not available."
    page = _page(_Controller(voice=voice))
    said: list[tuple] = []
    page.say = lambda message, tone="info": said.append((message, tone))
    page._test_output_device()
    assert said and said[0][1] == "error" and "not available" in said[0][0]


def test_a_raising_voice_manager_cannot_take_the_settings_window_down() -> None:
    voice = _Voice()
    voice.play_test_tone = lambda spec=None: (_ for _ in ()).throw(RuntimeError("portaudio exploded"))
    page = _page(_Controller(voice=voice))
    said: list[tuple] = []
    page.say = lambda message, tone="info": said.append((message, tone))
    page._test_output_device()  # must not raise
    assert said and said[0][1] == "error"


# --------------------------------------------------------------------------- the summary


def test_the_summary_names_where_audio_will_actually_play() -> None:
    page = _page(_Controller())
    assert "XREAL One Pro" in page.device_summary.text()

    prefs = AssistantPreferences.from_dict(
        {"audio_output_device": "BuiltInSpeakerDevice", "audio_output_device_name": "MacBook Pro Speakers"}
    )
    page = _page(_Controller(prefs=prefs))
    assert "MacBook Pro Speakers" in page.device_summary.text()


# --------------------------------------------------------------------------- the mic race


def test_the_device_list_is_not_refreshed_while_the_microphone_may_be_open() -> None:
    """Refreshing restarts PortAudio and invalidates every open stream in the process.

    `_listening` alone is not a sufficient gate: `stop_listening()` clears it BEFORE
    `rec.stop()` closes the input stream, so a refresh inside that window kills a live
    microphone (PaErrorCode -9988). Found by the adversarial pass.
    """
    from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager

    vm = GatewayVoiceManager(llm_manager=SimpleNamespace(data_dir="/tmp"))
    assert vm._can_refresh_audio_devices() is True  # idle

    vm._listening = True
    assert vm._can_refresh_audio_devices() is False

    # The exact window stop_listening() passes through: flag already cleared, stream not
    # yet closed.
    vm._listening = False
    vm._recognizer = object()
    assert vm._can_refresh_audio_devices() is False

    vm._recognizer = None
    assert vm._can_refresh_audio_devices() is True


# --------------------------------------------------------------------------- the dropdown


def test_opening_the_dropdown_rebuilds_the_list() -> None:
    """Operator ask: "a simple drop down where i can see the connected devices and select
    the one i want". Devices come and go while Settings is open, so the list is rebuilt on
    every open — that is what removes the need for a Refresh button."""
    voice = _Voice([GLASSES])
    page = _page(_Controller(voice=voice))
    assert page.output_device_combo.count() == 2  # System default + the glasses

    voice._devices = [GLASSES, SPEAKERS, HOTPLUGGED]  # a headset is plugged in
    page.output_device_combo.showPopup()
    page.output_device_combo.hidePopup()

    labels = [page.output_device_combo.itemText(i) for i in range(page.output_device_combo.count())]
    assert "MacBook Pro Speakers" in labels
    assert "Sony WH-1000XM5 (connected after launch)" in labels


def test_reopening_the_dropdown_keeps_the_current_selection() -> None:
    controller = _Controller()
    page = _page(controller)
    combo = page.output_device_combo
    combo.setCurrentIndex(combo.findData("BuiltInSpeakerDevice"))
    page._reload_output_devices(announce=False)  # what opening the popup does
    # Nothing is saved yet, so the rebuild restores the SAVED value, not the browsing one.
    assert combo.currentData() == ""

    page.output_device_combo.setCurrentIndex(combo.findData("BuiltInSpeakerDevice"))
    page._save()
    page._reload_output_devices(announce=False)
    assert combo.currentData() == "BuiltInSpeakerDevice"


def test_the_page_never_sends_the_user_to_macos_sound_settings() -> None:
    """The operator asked for the device list in the app, not a shortcut out of it."""
    from PyQt5.QtWidgets import QPushButton

    page = _page(_Controller())
    labels = [b.text() for b in page.findChildren(QPushButton)]
    assert not any("Sound settings" in label for label in labels), labels
    assert not hasattr(page, "_open_sound_settings")
