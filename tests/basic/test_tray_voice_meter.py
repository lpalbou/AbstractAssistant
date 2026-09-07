"""The tray icon shows the assistant's voice while it speaks.

Restored from 0.4.10, where a live meter drove the tray icon and the icon went
back to its normal state when speech ended. The gateway-native rewrite kept the
meter (the voice manager still emits output levels) but nothing drew it.

The load-bearing behaviour is the RETURN. Speech ends in more ways than it
starts, and two of those endings fire no completion callback at all, so the
icon is driven by asking the player rather than by a flag someone has to
remember to clear.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSize  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import abstractassistant.app as app_module  # noqa: E402
from abstractassistant.app import AssistantPalette, _tray_feedback_icon, _tray_voice_bars  # noqa: E402


_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class _Tray:
    def __init__(self) -> None:
        self.icons: list = []
        self.tooltips: list[str] = []

    def setIcon(self, icon) -> None:  # noqa: N802 (Qt API)
        self.icons.append(icon)

    def setToolTip(self, text) -> None:  # noqa: N802 (Qt API)
        self.tooltips.append(str(text))


class _Timer:
    def __init__(self) -> None:
        self.active = False
        self._interval = 0
        self.intervals: list[int] = []

    def isActive(self) -> bool:  # noqa: N802 (Qt API)
        return self.active

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False

    def interval(self) -> int:
        return self._interval

    def setInterval(self, value) -> None:  # noqa: N802 (Qt API)
        self._interval = int(value)
        self.intervals.append(int(value))


class _Voice:
    """A player the tray can ask, the way the real one is asked."""

    def __init__(self, *, speaking: bool = False, paused: bool = False) -> None:
        self.speaking = speaking
        self.paused = paused

    def is_speaking(self) -> bool:
        return bool(self.speaking)

    def is_paused(self) -> bool:
        return bool(self.paused)


def _palette(*, speaking: bool = False) -> AssistantPalette:
    _app()
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._tray = _Tray()
    palette._tray_feedback_timer = _Timer()
    palette._tray_animation_frame = 0
    palette._tray_completion_unread = False
    palette._speech_meter = 0.0
    palette._speech_meter_ts = 0.0
    palette._show_thinking_indicator = lambda: False
    palette._controller = type("C", (), {"voice_manager": _Voice(speaking=speaking)})()
    return palette


@pytest.mark.basic
def test_meter_normalizes_scalars_bands_and_junk() -> None:
    count = app_module._TRAY_VOICE_BAR_COUNT

    # Per-band levels are resampled to the icon's bar count, in range.
    bars = _tray_voice_bars([0.1, 0.9, 0.4, 0.6, 0.2, 0.8, 0.3])
    assert len(bars) == count and all(0.0 <= b <= 1.0 for b in bars)

    # A single level becomes a symmetric burst, peaking at the reading.
    burst = _tray_voice_bars(0.8)
    assert len(burst) == count
    assert max(burst) == pytest.approx(0.8)
    assert burst[0] < burst[count // 2] and burst[-1] < burst[count // 2]

    # Nothing, and nonsense, are silence — never a crash.
    assert _tray_voice_bars(None) == [0.0] * count
    assert _tray_voice_bars([]) == [0.0] * count
    assert _tray_voice_bars(["x", None]) == [0.0] * count
    # Out-of-range readings are clamped, not drawn off the icon.
    assert all(0.0 <= b <= 1.0 for b in _tray_voice_bars([-3.0, 12.0]))


@pytest.mark.basic
def test_speaking_icon_tracks_the_level_and_is_never_cached() -> None:
    _app()
    # The cache is a process-global: whether "idle" is already in it depends on
    # what ran before, and the last assertion here needs a COLD one.
    app_module._TRAY_ICON_CACHE.clear()
    before = len(app_module._TRAY_ICON_CACHE)
    quiet = _tray_feedback_icon(state="speaking", levels=[0.0] * 5)
    loud = _tray_feedback_icon(state="speaking", levels=[1.0] * 5)

    assert not quiet.isNull() and not loud.isNull()
    # A live meter is a new picture every frame: caching it would grow forever.
    assert len(app_module._TRAY_ICON_CACHE) == before
    # Loud and quiet are actually different pictures.
    assert (
        quiet.pixmap(QSize(44, 44)).toImage()
        != loud.pixmap(QSize(44, 44)).toImage()
    )
    # The other states still cache.
    _tray_feedback_icon(state="idle")
    assert len(app_module._TRAY_ICON_CACHE) > before


@pytest.mark.basic
def test_speaking_wins_the_tray_and_drives_a_faster_timer() -> None:
    palette = _palette(speaking=True)
    palette._show_thinking_indicator = lambda: True  # a run is going too

    AssistantPalette._refresh_tray_feedback(palette)
    assert AssistantPalette._tray_feedback_state(palette) == "speaking"
    assert palette._tray_feedback_timer.isActive()
    assert palette._tray_feedback_timer.interval() == app_module._TRAY_VOICE_FRAME_INTERVAL_MS
    assert palette._tray.tooltips[-1].endswith("Speaking")

    # Speech over: the run underneath it takes the icon back.
    palette._controller.voice_manager.speaking = False
    AssistantPalette._refresh_tray_feedback(palette)
    assert AssistantPalette._tray_feedback_state(palette) == "busy"
    assert palette._tray_feedback_timer.interval() == app_module._TRAY_BUSY_FRAME_INTERVAL_MS
    assert "Thinking" in palette._tray.tooltips[-1]


@pytest.mark.basic
def test_the_meter_decays_instead_of_freezing() -> None:
    """Levels arrive per audio chunk and stop when playback stalls or ends."""
    import time

    palette = _palette()
    now = time.monotonic()
    palette._speech_meter = [1.0, 1.0, 1.0]
    palette._speech_meter_ts = now

    fresh = AssistantPalette._decayed_speech_meter(palette, now=now)
    assert max(fresh) == pytest.approx(1.0)

    half = AssistantPalette._decayed_speech_meter(
        palette, now=now + (app_module._TRAY_VOICE_DECAY_S / 2.0)
    )
    assert 0.4 < max(half) < 0.6

    stale = AssistantPalette._decayed_speech_meter(
        palette, now=now + app_module._TRAY_VOICE_DECAY_S + 1.0
    )
    assert stale == 0.0
    # Never fed at all: silence, not an exception.
    palette._speech_meter_ts = 0.0
    assert AssistantPalette._decayed_speech_meter(palette) == 0.0


@pytest.mark.basic
def test_the_icon_follows_the_player_however_speech_ends() -> None:
    """The operator's requirement: 'whether finished or interrupted by the
    user, it resumes the normal icon state'.

    Speech ends in more ways than it starts — finished, stopped, superseded,
    paused, failed, quit — and a flag would have to be cleared in every one of
    them. Two of those endings fire no completion callback at all (a deliberate
    stop, and a pause, which never ends). So the icon asks the player instead,
    and every ending reduces to one property.
    """
    for ending, speaking, paused in (
        ("finished", False, False),
        ("stopped by the user", False, False),
        ("paused by the user", False, True),
        ("superseded, the new one still playing", True, False),
    ):
        palette = _palette(speaking=True)
        assert AssistantPalette._tray_feedback_state(palette) == "speaking"
        palette._controller.voice_manager.speaking = speaking
        palette._controller.voice_manager.paused = paused
        state = AssistantPalette._tray_feedback_state(palette)
        expected = "speaking" if speaking else "idle"
        assert state == expected, f"{ending}: got {state!r}"

    # A player that cannot be asked is not a speaking player.
    palette = _palette(speaking=True)
    palette._controller = type("C", (), {"voice_manager": None})()
    assert AssistantPalette._tray_feedback_state(palette) == "idle"
    palette._controller = type(
        "C",
        (),
        {"voice_manager": type("V", (), {"is_speaking": lambda self: 1 / 0})()},
    )()
    assert AssistantPalette._tray_feedback_state(palette) == "idle"


@pytest.mark.basic
def test_auto_speak_and_conversations_reach_the_tray_too() -> None:
    """Neither sets a message key, so a key-driven icon never showed for them —
    the two paths where the tray matters most."""
    palette = _palette(speaking=True)
    palette._active_spoken_message_key = ""      # auto-speak sets no key
    palette.message_speech_started = type("S", (), {"emit": staticmethod(lambda *a: None)})()
    emitted: list = []
    palette.speech_activity_changed = type(
        "S", (), {"emit": staticmethod(lambda: emitted.append(True))}
    )()

    AssistantPalette._on_voice_speech_activity(palette)
    assert emitted == [True], "the keyless hook must fire without a message key"
    assert AssistantPalette._tray_feedback_state(palette) == "speaking"


@pytest.mark.basic
def test_levels_feed_the_tray_and_not_the_microphone_strip() -> None:
    palette = _palette(speaking=True)
    strip: list = []
    palette._on_voice_level = lambda level: strip.append(level)

    AssistantPalette._on_speech_level(palette, [0.2, 0.9, 0.4])
    assert palette._speech_meter == [0.2, 0.9, 0.4]
    assert palette._speech_meter_ts > 0.0
    # The composer's strip is the MIC meter; these are output levels, and
    # the band floor would peg it at 40% for every reply.
    assert strip == []
    # The first reading of a speech nobody announced still starts the animation.
    assert palette._tray_feedback_timer.isActive()


@pytest.mark.basic
def test_the_output_meter_actually_emits_levels() -> None:
    """It never had: `_compute_band_levels` was called with 3 of its 4 required
    arguments and every call raised into a bare `except`, so anything drawing
    this meter was frozen. 193 chunks, 193 exceptions, 0 readings."""
    numpy = pytest.importorskip("numpy")
    from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager

    manager = GatewayVoiceManager.__new__(GatewayVoiceManager)
    manager._audio_meter_warned = False
    readings: list = []
    manager._audio_meter_callback = readings.append

    sample_rate = 48000
    t = numpy.arange(int(sample_rate * 0.1)) / sample_rate
    tone = (numpy.sin(2 * numpy.pi * 440 * t) * 0.5 * 32767).astype(numpy.int16)
    GatewayVoiceManager._emit_audio_meter_from_chunk(manager, tone, sample_rate)

    assert len(readings) == 1
    bands = readings[0]
    assert isinstance(bands, list) and bands
    assert max(bands) > 0.0, "a 440 Hz tone must not read as silence"
    assert all(0.0 <= b <= 1.0 for b in bands)
