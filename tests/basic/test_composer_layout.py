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
    assert window.conversation_button.geometry().bottom() == window.composer_card.geometry().bottom()
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
    assert "click Talk" in window.prompt_edit.placeholderText()


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
