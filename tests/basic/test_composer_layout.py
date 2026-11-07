"""Composer actions remain reachable as text, voice and window size change."""
import pytest
from PyQt5.QtCore import QRect
from test_composer_adversarial import orb_palette, _SMOKE
from abstractassistant.app import ORB_TOOLTIP


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
    # The header title is what the user sees (the voice strip is hidden since 0.18.1).
    window._on_voice_state("speaking")
    assert window.title_label.text() == "Preparing speech…"
    controller.voice_manager.is_paused = lambda: True
    window._on_voice_state("speaking")
    assert window.title_label.text() == "Speech paused"
    controller.voice_manager.is_paused = lambda: False
    controller.voice_manager.is_speaking = lambda: True
    window._on_voice_state("speaking")
    assert window.title_label.text().startswith("Speaking")
    window._on_voice_state("transcribing")
    assert window.title_label.text() == "Sending what you said…"
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
    controller.voice_manager.listening = False  # the turn's words went out: the mic is closed
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
    import abstractassistant.app as module
    from abstractvoice.audio.levels import VoiceLevelNormalizer
    window, controller = orb_palette
    window._start_voice_conversation()
    # The voice turn's recording reports levels the way `begin_hold` does: the
    # adaptive normalizer, fed a quiet microphone (rms 0.002) while speech is heard.
    level = controller.voice_manager.capture_kwargs["on_audio_level"]
    normalizer = VoiceLevelNormalizer()
    for _ in range(8):
        level(normalizer.push(0.002, peak=0.004, seconds=0.03, speech=True))
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
    assert window.conversation_button.toolTip() == ORB_TOOLTIP
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

    dictate = items()["Dictate into the message box"]
    assert dictate.isCheckable() and not dictate.isChecked()
    window._listening = True
    dictate = items()["Dictate into the message box"]
    assert dictate.isCheckable() and dictate.isChecked()
    window._listening = False


@pytest.mark.basic
def test_voice_turn_menu_item_is_ticked_exactly_while_the_turn_runs(orb_palette):
    """A voice turn is one utterance (0.18.2): there is no microphone to pause between
    turns, so no "Microphone" item; "Voice conversation" is ticked from the press until
    the reply has been spoken, then unticks by itself."""
    window, controller = orb_palette

    def items():
        menu = window._build_voice_menu()
        return {a.text(): a for a in menu.actions() if not a.isSeparator()}

    window._start_voice_conversation()
    conversation = window._voice_conversation
    for state in ("listening",):
        assert conversation.state == state
        assert items()["Voice conversation (⌘⇧V)"].isChecked()
        assert "Microphone" not in items()
    controller.voice_manager.heard = True
    window.voice_turn_ended.emit(conversation, "silence")
    _SMOKE["_app"]().processEvents()
    assert conversation.state == "transcribing"
    assert items()["Voice conversation (⌘⇧V)"].isChecked()
    conversation.state = "thinking"  # the send itself is covered by the smoke tests
    conversation.run_finished(will_speak=True)
    assert conversation.state == "speaking"
    assert items()["Voice conversation (⌘⇧V)"].isChecked()
    conversation.speech_finished()
    _SMOKE["_app"]().processEvents()
    item = items()["Voice conversation (⌘⇧V)"]
    assert item.isCheckable() and not item.isChecked()
    assert not window._voice_conversation_active
    assert not window.conversation_button.isChecked()
    assert not controller.voice_manager.listening  # nothing reopened the microphone


@pytest.mark.basic
def test_voice_conversation_is_one_checkable_item_and_the_orb_keeps_one_name(orb_palette):
    """Operator rule (toggles show state): the voice conversation is an on/off, so the menu
    has one checkable "Voice conversation" item whose label never swaps, and the orb keeps
    one accessible name and one tooltip that are true in every state (review finding 2)."""
    window, controller = orb_palette

    def menu_labels():
        menu = window._build_voice_menu()
        return {a.text(): a for a in menu.actions() if not a.isSeparator()}

    def orb():
        window._refresh_avatar()
        button = window.conversation_button
        return button.accessibleName(), button.toolTip()

    idle = menu_labels()
    item = idle["Voice conversation (⌘⇧V)"]
    assert item.isCheckable() and not item.isChecked()
    assert orb() == ("Voice", ORB_TOOLTIP)

    window._start_voice_conversation()
    active = menu_labels()
    item = active["Voice conversation (⌘⇧V)"]
    assert item.isCheckable() and item.isChecked()
    assert set(idle) == set(active)  # the labels never change with the state
    assert orb() == ("Voice", ORB_TOOLTIP)
    item.trigger()
    assert not window._voice_conversation_active

    window._listening = True  # dictating: a click on the orb stops dictation
    assert orb() == ("Voice", ORB_TOOLTIP)
    window._listening = False
    controller.voice_manager.is_speaking = lambda: True  # reading a reply aloud
    assert orb() == ("Voice", ORB_TOOLTIP)


@pytest.mark.basic
@pytest.mark.parametrize("theme_id", ["dark", "light", "observer-night", "solarized-light"])
def test_the_floating_orb_has_its_own_translucent_backdrop_in_every_theme(orb_palette, theme_id):
    """Operator 2026-11-07: the orb and its "Listening" label sat straight on whatever was
    behind the window (a white web page made them unreadable). The orb's own rect gets the
    theme's card surface, more transparent than the composer; the gap stays transparent."""
    from abstractassistant.retint import parse_color
    from abstractassistant.theme import THEME

    from abstractassistant.theme import DEFAULT_THEME, activate

    window, _ = orb_palette
    window.apply_theme(theme_id, persist=False)
    _SMOKE["_app"]().processEvents()
    button = window.conversation_button
    try:
        image = window.grab().toImage()
        _rgb, _alpha = parse_color(THEME.surface_card)
        wanted = button.backdrop_color()
        r, g, b = wanted.red(), wanted.green(), wanted.blue()
    finally:
        activate(DEFAULT_THEME)  # the palette is process-global; leave it as found
    ratio = image.devicePixelRatio()
    # Below the orb's face, inside the button: the backdrop, and nothing else.
    x, y = button.x() + button.width() // 2, button.y() + button.height() - 8
    pixel = image.pixelColor(int(x * ratio), int(y * ratio))
    assert 0.7 * 255 <= pixel.alpha() <= 0.9 * 255, pixel.alpha()
    composer_alpha = (_alpha if _alpha is not None else 1.0) * 255
    assert pixel.alpha() < composer_alpha  # more transparent than the panel beside it
    assert max(abs(pixel.red() - r), abs(pixel.green() - g), abs(pixel.blue() - b)) <= 3
    # The desktop gap between the composer and the orb is untouched.
    gap_x = (window.composer_card.geometry().right() + button.x()) // 2
    assert image.pixelColor(int(gap_x * ratio), int(button.geometry().center().y() * ratio)).alpha() == 0


@pytest.mark.basic
def test_a_disabled_voice_conversation_item_says_why(orb_palette):
    """Operator rule (a disabled item says why): with no gateway connection the greyed-out
    item's tooltip is the reason, not the description of what it would do (review A1)."""
    window, controller = orb_palette
    connected = controller.current_workflow
    controller.current_workflow = lambda: None
    menu = window._build_voice_menu()
    assert menu.toolTipsVisible()
    item = {a.text(): a for a in menu.actions() if not a.isSeparator()}["Voice conversation (⌘⇧V)"]
    assert not item.isEnabled()
    assert item.toolTip() == "Connect to the gateway before starting a voice conversation."
    controller.current_workflow = connected
    item = {a.text(): a for a in window._build_voice_menu().actions() if not a.isSeparator()}["Voice conversation (⌘⇧V)"]
    assert item.isEnabled() and item.toolTip().startswith("One question per press")


@pytest.mark.basic
def test_the_orb_tooltip_describes_one_question_per_press():
    """Review A3: a click while the orb listens SENDS (it no longer "stops" a conversation)."""
    assert "one question" in ORB_TOOLTIP and "send it now" in ORB_TOOLTIP
    assert "start or stop" not in ORB_TOOLTIP


def _luminance(rgb):
    def channel(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a, b):
    low, high = sorted((_luminance(a), _luminance(b)))
    return (high + 0.05) / (low + 0.05)


def _over(color, background):
    alpha = color.alphaF()
    return tuple(round(alpha * c + (1 - alpha) * bg)
                 for c, bg in zip((color.red(), color.green(), color.blue()), background))


@pytest.mark.basic
def test_the_orb_backdrop_stands_out_over_white_and_black_in_every_theme():
    """Review A8: in the light themes the card surface is itself near white, so a backdrop
    in that colour vanished over a white page. In EVERY theme, over a white page and over a
    black desktop, the panel's tone differs from the page and its edge is clearly visible."""
    from abstractassistant import ui_themes
    from abstractassistant.theme import DEFAULT_THEME, activate
    from abstractassistant.ui.avatar import AvatarPresentation, AvatarVoiceButton

    _SMOKE["_app"]()
    button = AvatarVoiceButton(lambda: AvatarPresentation())
    try:
        for theme_id in ["abstract-glass", *ui_themes.THEME_SPECS]:
            activate(ui_themes.build_theme(theme_id) or DEFAULT_THEME)
            for page in ((255, 255, 255), (0, 0, 0)):
                fill = _over(button.backdrop_color(), page)
                edge = _over(button.backdrop_edge_color(), fill)
                assert _contrast(fill, page) >= 1.2, (theme_id, page, fill)
                assert _contrast(edge, page) >= 1.8, (theme_id, page, edge)
    finally:
        activate(DEFAULT_THEME)
        button.deleteLater()
