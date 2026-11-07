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


@pytest.mark.basic
def test_orb_menu_on_off_items_keep_their_feature_label_and_show_state(orb_palette):
    """Operator rule (toggles show state, 2026-09-30): an on/off in the orb's menu is one
    checkable item named for its feature; the check shows the state, the label never swaps."""
    window, _ = orb_palette

    def items():
        menu = window._build_voice_menu()
        return {a.text(): a for a in menu.actions() if not a.isSeparator()}

    window._start_voice_conversation()
    assert window._voice_conversation.state != "paused"
    mic = items()["Microphone"]
    assert mic.isCheckable() and mic.isChecked()
    mic.trigger()
    assert window._voice_conversation.state == "paused"
    mic = items()["Microphone"]
    assert mic.isCheckable() and not mic.isChecked()
    mic.trigger()
    assert window._voice_conversation.state != "paused"
    window._end_voice_conversation()

    assert "Microphone" not in items()
    dictate = items()["Dictate into the message box"]
    assert dictate.isCheckable() and not dictate.isChecked()
    window._listening = True
    dictate = items()["Dictate into the message box"]
    assert dictate.isCheckable() and dictate.isChecked()
    window._listening = False


@pytest.mark.basic
def test_orb_menu_microphone_shows_the_real_microphone_and_acts_only_when_it_can(orb_palette):
    """While the assistant works or speaks the conversation keeps the microphone closed and
    cannot pause it: the item says so (unticked, disabled, with the reason) instead of a tick
    that an untick silently ignores (review 2026-11-07, finding 1)."""
    window, _ = orb_palette

    def microphone():
        menu = window._build_voice_menu()
        assert menu.toolTipsVisible(), "a disabled item's reason must be readable"
        return {a.text(): a for a in menu.actions() if not a.isSeparator()}["Microphone"]

    window._start_voice_conversation()
    conversation = window._voice_conversation
    assert conversation.state == "listening"
    assert microphone().isEnabled() and microphone().isChecked()

    conversation.mark_sent()  # a turn went out: the assistant works, the mic is closed
    assert conversation.state == "thinking"
    mic = microphone()
    assert not mic.isChecked() and not mic.isEnabled()
    assert mic.toolTip() == "The microphone is closed while the assistant works."
    mic.trigger()
    assert conversation.state == "thinking"

    conversation.run_finished(will_speak=True)
    assert conversation.state == "speaking"
    mic = microphone()
    assert not mic.isChecked() and not mic.isEnabled()
    assert mic.toolTip() == "The microphone is closed while the assistant speaks."

    conversation.speech_finished()
    assert conversation.state == "listening"
    assert microphone().isEnabled() and microphone().isChecked()
    window._end_voice_conversation()
