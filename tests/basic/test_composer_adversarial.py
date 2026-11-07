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


@pytest.mark.basic
@pytest.mark.parametrize("has_text,has_file", [(True, False), (False, True), (True, True)])
def test_draft_created_during_voice_debounce_is_never_sent(orb_palette, has_text, has_file):
    window, controller = orb_palette
    window._start_voice_conversation()
    conversation = window._voice_conversation
    conversation.heard("spoken words")
    if has_text:
        window.prompt_edit.setPlainText("Unfinished draft")
    attachments = [object()] if has_file else []
    window._attachments = attachments
    conversation.send_now()
    assert window.prompt_edit.toPlainText() == ("Unfinished draft spoken words" if has_text else "spoken words")
    assert window._attachments is attachments
    assert controller.built == []
    assert not conversation.auto_send
    assert conversation.state == "listening"
    # Said where the user sees it (the strip is hidden since 0.18.1): the words went to the
    # draft and sending on its own is now off for this conversation.
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
    conversation = window._voice_conversation
    assert conversation.auto_send
    window.prompt_edit.setPlainText("Unfinished draft")
    window._on_transcription("spoken words")
    assert window.prompt_edit.toPlainText() == "Unfinished draft spoken words"
    assert not conversation.auto_send and controller.built == []
    assert window.banner_label.isVisible() and "not sent automatically" in window.banner_label.text()
