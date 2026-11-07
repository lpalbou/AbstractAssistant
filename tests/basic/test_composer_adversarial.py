"""Independent interaction regressions for the desktop voice orb."""

import os
import runpy
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest

from abstractassistant.ui.avatar import AvatarPresentation, AvatarVoiceButton

_SMOKE = runpy.run_path(str(Path(__file__).with_name("test_palette_smoke.py")))


@pytest.fixture
def orb_palette():
    app = _SMOKE["_app"]()
    controller = _SMOKE["_Controller"]()
    window = _SMOKE["AssistantPalette"](controller=controller)
    _SMOKE["_wait_for_bootstrap"](window)
    window._hide_if_inactive = lambda: None
    window.show()
    app.processEvents()
    yield window, controller
    window.shutdown()
    window.hide()
    window.deleteLater()
    app.processEvents()


def _speak_a_turn(window, controller, words):
    """One voice turn up to its transcript: speech, the silence, the gateway's words."""
    controller.voice_manager.heard = True
    turn = window._voice_conversation
    window.voice_turn_ended.emit(turn, "silence")
    _SMOKE["_app"]().processEvents()
    window.voice_turn_transcribed.emit(turn, words)
    _SMOKE["_app"]().processEvents()


@pytest.mark.basic
@pytest.mark.parametrize("has_text,has_file", [(True, False), (False, True), (True, True)])
def test_draft_created_during_a_voice_turn_is_never_sent(orb_palette, has_text, has_file):
    window, controller = orb_palette
    window._start_voice_conversation()
    if has_text:
        window.prompt_edit.setPlainText("Unfinished draft")
    attachments = [object()] if has_file else []
    window._attachments = attachments
    _speak_a_turn(window, controller, "spoken words")
    assert window.prompt_edit.toPlainText() == ("Unfinished draft spoken words" if has_text else "spoken words")
    assert window._attachments is attachments
    assert controller.built == []
    # The turn is over: the microphone is closed and nothing listens again.
    assert window._voice_conversation is None
    assert not controller.voice_manager.listening
    # Said where the user sees it (the strip is hidden since 0.18.1): the words went to the
    # draft and were not sent on their own.
    assert window.banner_label.isVisible()
    assert "not sent automatically" in window.banner_label.text()
    assert "Return" in window.banner_label.text()


@pytest.mark.basic
def test_keyboard_orb_ends_capture_even_after_capabilities_disconnect(orb_palette):
    window, controller = orb_palette
    QTest.keyClick(window.conversation_button, Qt.Key_Space)
    assert controller.voice_manager.listening
    assert window.prompt_edit.placeholderText() == "Type a message…"
    controller.current_workflow = lambda: None
    controller.supports_stt = lambda: False
    controller.supports_tts = lambda: False
    window._refresh_capability_state()
    assert window.conversation_button.isEnabled()
    QTest.keyClick(window.conversation_button, Qt.Key_Space)
    assert not controller.voice_manager.listening
    assert not window._voice_conversation_active
    assert not window.conversation_button.isChecked()


@pytest.mark.basic
def test_animation_failure_switches_to_usable_voice_control_without_other_ui_events():
    app = _SMOKE["_app"]()

    class Renderer:
        fail = False

        def __init__(self, *, width, height):
            self.size = width * height * 4

        def set_palette(self, **kwargs):
            pass

        def render(self, **kwargs):
            if self.fail:
                raise RuntimeError("rendering failed after startup")
            return bytes(self.size)

        def close(self):
            pass

    button = AvatarVoiceButton(lambda: AvatarPresentation())
    button.avatar._factory = Renderer
    button.show()
    button.avatar.configure(enabled=True, style="watch-hover", animated=True)
    button.update_presentation()
    app.processEvents()
    try:
        assert button.avatar.isVisible()
        button.avatar._renderer.fail = True
        button.avatar._on_frame()
        app.processEvents()
        assert button.fallback.isVisible()
        assert button.avatar.isHidden()
        assert button.isEnabled()
        assert button.accessibleName() == "Voice"
    finally:
        button.hide()
        button.deleteLater()
        app.processEvents()


@pytest.mark.basic
def test_words_heard_beside_a_draft_go_into_it_and_the_notice_says_so(orb_palette):
    window, controller = orb_palette
    window._start_voice_conversation()
    window.prompt_edit.setPlainText("Unfinished draft")
    _speak_a_turn(window, controller, "spoken words")
    assert window.prompt_edit.toPlainText() == "Unfinished draft spoken words"
    assert controller.built == []
    assert window.banner_label.isVisible() and "not sent automatically" in window.banner_label.text()


# ------------------------------------------------------------ one voice turn per press (0.18.2)


@pytest.mark.basic
def test_a_press_on_the_listening_orb_sends_what_was_said(orb_palette):
    window, controller = orb_palette
    voice = controller.voice_manager
    QTest.mouseClick(window.conversation_button, Qt.LeftButton)
    assert voice.listening and window._voice_conversation.state == "listening"
    voice.heard = True
    QTest.mouseClick(window.conversation_button, Qt.LeftButton)  # done talking
    assert not voice.listening
    assert window._voice_conversation.state == "transcribing"
    assert callable(voice.transcribe_kwargs.get("on_transcription"))
    window.voice_turn_transcribed.emit(window._voice_conversation, "call mum")
    _SMOKE["_app"]().processEvents()
    assert controller.built and controller.built[-1]["prompt"] == "call mum"


@pytest.mark.basic
def test_a_press_on_the_listening_orb_with_nothing_said_cancels(orb_palette):
    window, controller = orb_palette
    voice = controller.voice_manager
    QTest.mouseClick(window.conversation_button, Qt.LeftButton)
    voice.transcribe_kwargs = {}
    QTest.mouseClick(window.conversation_button, Qt.LeftButton)
    assert not voice.listening
    assert voice.transcribe_kwargs == {}  # nothing went to the gateway
    assert not window._voice_conversation_active
    assert not window.conversation_button.isChecked()
    assert window.title_label.text() == "I didn't hear anything"
    assert controller.built == []


@pytest.mark.basic
def test_escape_cancels_a_turn_even_after_speech(orb_palette):
    window, controller = orb_palette
    voice = controller.voice_manager
    window._start_voice_conversation()
    voice.heard = True
    voice.transcribe_kwargs = {}
    window._on_escape()
    assert not voice.listening and voice.transcribe_kwargs == {}
    assert not window._voice_conversation_active
    assert controller.built == []


@pytest.mark.basic
def test_the_turn_ends_after_the_reply_and_nothing_listens_again(orb_palette):
    """The operator's report: in a quiet room the loop kept listening after each reply
    and sent "Thank you." and "Cough, cough." One turn, then the orb is idle."""
    window, controller = orb_palette
    voice = controller.voice_manager
    opened: list = []
    original = voice.begin_hold
    voice.begin_hold = lambda **kw: (opened.append(1), original(**kw))[1]
    window._start_voice_conversation()
    conversation = window._voice_conversation
    voice.heard = True
    window.voice_turn_ended.emit(conversation, "silence")
    _SMOKE["_app"]().processEvents()
    # The run itself is the smoke controller's (it refuses to start); drive the
    # reply's lifecycle directly: it is spoken, then it finishes.
    conversation.state = "thinking"
    conversation.run_finished(will_speak=True)
    window._on_voice_speech_finished()
    _SMOKE["_app"]().processEvents()
    assert not window._voice_conversation_active
    assert not voice.listening
    # A late transcript or an endpoint from the finished turn changes nothing.
    window.voice_turn_transcribed.emit(conversation, "Thank you.")
    window.voice_turn_ended.emit(conversation, "silence")
    _SMOKE["_app"]().processEvents()
    assert opened == [1]
    assert controller.built == []
    assert not window.conversation_button.isChecked()


@pytest.mark.basic
def test_a_cancelled_turns_late_transcript_never_lands_in_the_next_turn(orb_palette):
    window, controller = orb_palette
    voice = controller.voice_manager
    window._start_voice_conversation()
    first = window._voice_conversation
    voice.heard = True
    window.voice_turn_ended.emit(first, "silence")
    _SMOKE["_app"]().processEvents()
    window._on_escape()  # cancelled while the gateway transcribes
    window._start_voice_conversation()
    second = window._voice_conversation
    window.voice_turn_ended.emit(second, "silence")
    _SMOKE["_app"]().processEvents()
    assert second.state == "transcribing"
    window.voice_turn_transcribed.emit(first, "the cancelled question")
    _SMOKE["_app"]().processEvents()
    assert controller.built == [] and second.state == "transcribing"
    window.voice_turn_transcribed.emit(second, "the real question")
    _SMOKE["_app"]().processEvents()
    assert controller.built and controller.built[-1]["prompt"] == "the real question"


@pytest.mark.basic
@pytest.mark.parametrize("press", ["shortcut", "menu"])
def test_cmd_shift_v_and_the_menu_item_are_the_same_press_as_the_orb(orb_palette, press):
    """Review A2: pressed while the orb listens, ⌘⇧V and the menu item send what was said,
    and cancel when nothing was said — exactly like a click on the orb."""
    window, controller = orb_palette
    voice = controller.voice_manager

    def do_press():
        if press == "shortcut":
            QTest.keyClick(window, Qt.Key_V, Qt.ControlModifier | Qt.ShiftModifier)
        else:
            menu = window._build_voice_menu()
            {a.text(): a for a in menu.actions() if not a.isSeparator()}["Voice conversation (⌘⇧V)"].trigger()
        _SMOKE["_app"]().processEvents()

    do_press()
    assert window._voice_conversation.state == "listening"
    voice.heard = True
    do_press()  # done talking
    assert window._voice_conversation.state == "transcribing"
    assert callable(voice.transcribe_kwargs.get("on_transcription"))
    window._end_voice_conversation()

    voice.heard = False
    voice.transcribe_kwargs = {}
    do_press()
    do_press()  # nothing said yet: cancelled
    assert voice.transcribe_kwargs == {}
    assert not window._voice_conversation_active and not voice.listening
