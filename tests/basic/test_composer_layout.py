"""Composer actions remain reachable as text, voice and window size change."""
import pytest
from PyQt5.QtCore import QRect
from test_composer_adversarial import orb_palette, _SMOKE


@pytest.mark.basic
def test_send_visibility_preserves_attachment_only_and_busy_stop(orb_palette):
    window, _ = orb_palette
    assert window.send_button.isHidden()
    window.prompt_edit.setPlainText("draft")
    assert window.send_button.isVisible()
    window.prompt_edit.clear()
    assert window.send_button.isHidden()
    window._attachments = [object()]
    window._refresh_composer_actions()
    assert window.send_button.isVisible()
    window._attachments = []
    window._set_send_button_busy(True)
    assert window.send_button.isVisible()
    assert window.send_button.accessibleName() == "Stop run"
    window._set_send_button_busy(False)
    assert window.send_button.isHidden()


@pytest.mark.basic
@pytest.mark.parametrize("width", [420, 760])
def test_long_draft_grows_without_clipping_orb_and_header(width, orb_palette):
    window, controller = orb_palette
    window._available_screen_geometry = lambda: QRect(0, 0, 1600, 1000)
    controller.update_preferences(window_width=width)
    window._reflow_shell()
    before = window.composer_card.height()
    window.prompt_edit.setPlainText("A long draft line.\n" * 24)
    _SMOKE["_app"]().processEvents()
    assert window.composer_card.height() > before
    assert window.prompt_edit.height() <= 144
    assert window.conversation_button.x() - window.composer_card.geometry().right() >= 12
    assert abs(window.conversation_button.geometry().center().y() - window.composer_card.geometry().center().y()) <= 1
    assert window.rect().contains(window.conversation_button.geometry())
    assert window.header_card.rect().contains(window.session_picker.geometry())
    assert window.header_card.geometry().bottom() < window.history_card.geometry().top()
    window.prompt_edit.clear()
    _SMOKE["_app"]().processEvents()
    assert window.composer_card.height() == before


@pytest.mark.basic
def test_escape_ends_voice_before_hiding_and_speech_labels_follow_player(orb_palette):
    window, controller = orb_palette
    window._start_voice_conversation()
    assert window.prompt_edit.placeholderText() == "Type a message…"
    window._on_voice_state("speaking")
    assert window.voice_strip.status.text() == "Preparing speech…"
    controller.voice_manager.is_paused = lambda: True
    window._on_voice_state("speaking")
    assert window.voice_strip.status.text() == "Speech paused"
    controller.voice_manager.is_paused = lambda: False
    controller.voice_manager.is_speaking = lambda: True
    window._on_voice_state("speaking")
    assert window.voice_strip.status.text().startswith("Speaking")
    window._on_escape()
    assert not controller.voice_manager.listening
    assert not window._voice_conversation_active
    assert window.isVisible()
    assert window.prompt_edit.placeholderText() == "Ask anything…"


@pytest.mark.basic
def test_floating_orb_gap_is_transparent_and_focus_is_keyboard_only(orb_palette):
    from PyQt5.QtCore import QEvent, Qt
    from PyQt5.QtGui import QFocusEvent
    window, _ = orb_palette
    button = window.conversation_button
    button.focusInEvent(QFocusEvent(QEvent.FocusIn, Qt.TabFocusReason))
    assert button.property("keyboardFocus") == "true"
    button.focusInEvent(QFocusEvent(QEvent.FocusIn, Qt.MouseFocusReason))
    assert button.property("keyboardFocus") == "false"
    image = window.grab().toImage()
    ratio = image.devicePixelRatio()
    x = (window.composer_card.geometry().right() + button.x()) // 2
    y = button.geometry().center().y()
    assert image.pixelColor(int(x * ratio), int(y * ratio)).alpha() == 0


@pytest.mark.basic
def test_orb_labels_states_above_centered_body_and_owns_voice_stop(orb_palette):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    window, controller = orb_palette
    button = window.conversation_button
    assert button.caption.isHidden()
    QTest.mouseClick(button, Qt.LeftButton)
    assert controller.voice_manager.listening
    assert window.voice_strip.isHidden()
    assert button.caption.text() == "Listening"
    assert button.caption.geometry().bottom() < button.avatar.y()
    window._voice_conversation._set_state("thinking")
    assert button.caption.text() == "Thinking"
    assert window.voice_strip.isHidden()
    QTest.mouseClick(button, Qt.LeftButton)
    assert not controller.voice_manager.listening
    assert not window._voice_conversation_active
    window._set_status("Ready")
    assert button.caption.isHidden()


@pytest.mark.basic
def test_quiet_microphone_pcm_reaches_avatar_and_stale_level_decays(orb_palette, monkeypatch):
    import numpy as np
    import abstractassistant.app as module
    from abstractvoice.recognition import VoiceRecognizer
    window, _ = orb_palette
    window._start_voice_conversation()
    rec = VoiceRecognizer.__new__(VoiceRecognizer)
    rec._audio_level_ema = 0.0
    rec.audio_level_callback = window.voice_level_received.emit
    for _ in range(8):
        rec._emit_audio_level(np.full((480, 1), 0.002, dtype=np.float32))
    _SMOKE["_app"]().processEvents()
    assert window._avatar_presentation().state == "listening"
    assert window._avatar_presentation().level > 0.15
    timestamp = window._avatar_microphone_level_at
    monkeypatch.setattr(module.time, "monotonic", lambda: timestamp + 1)
    assert window._avatar_presentation().level == 0


@pytest.mark.basic
def test_speaking_orb_uses_output_bands_and_click_stops_read_aloud(orb_palette):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    window, controller = orb_palette
    speaking = [True]
    controller.voice_manager.is_speaking = lambda: speaking[0]
    controller.voice_manager.stop_speaking = lambda: speaking.__setitem__(0, False)
    controller.supports_stt = lambda: False
    window._on_speech_level([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
    frame = window._avatar_presentation()
    assert frame.state == "speaking" and len(frame.bands) == 8
    assert frame.bands[0] < frame.bands[-1]
    assert window.conversation_button.caption.text() == "Speaking"
    assert window.conversation_button.isEnabled()
    assert window.conversation_button.toolTip() == "Stop speaking"
    QTest.mouseClick(window.conversation_button, Qt.LeftButton)
    assert not speaking[0]
    assert not controller.voice_manager.listening
