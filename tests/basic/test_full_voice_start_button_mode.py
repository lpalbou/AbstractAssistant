"""
Full voice start-button behavior tests.
"""

from abstractassistant.ui.qt_bubble import QtChatBubble


def test_full_voice_button_starts_when_inactive() -> None:
    bubble = QtChatBubble.__new__(QtChatBubble)
    calls = {"start": 0, "hide": 0}
    bubble.debug = False
    bubble._is_full_voice_running = lambda: False  # type: ignore[method-assign]
    bubble.start_full_voice_mode = lambda: calls.__setitem__("start", calls["start"] + 1)  # type: ignore[method-assign]
    bubble.hide = lambda: calls.__setitem__("hide", calls["hide"] + 1)  # type: ignore[method-assign]

    bubble._handle_full_voice_click_main_thread()

    assert calls["start"] == 1
    assert calls["hide"] == 0


def test_full_voice_button_hides_when_already_running() -> None:
    bubble = QtChatBubble.__new__(QtChatBubble)
    calls = {"start": 0, "hide": 0}
    bubble.debug = False
    bubble._is_full_voice_running = lambda: True  # type: ignore[method-assign]
    bubble.start_full_voice_mode = lambda: calls.__setitem__("start", calls["start"] + 1)  # type: ignore[method-assign]
    bubble.hide = lambda: calls.__setitem__("hide", calls["hide"] + 1)  # type: ignore[method-assign]

    bubble._handle_full_voice_click_main_thread()

    assert calls["start"] == 0
    assert calls["hide"] == 1


def test_voice_ui_mode_does_not_resize_window() -> None:
    class _DummyContainer:
        def __init__(self) -> None:
            self.visible = True

        def hide(self) -> None:
            self.visible = False

        def show(self) -> None:
            self.visible = True

    class _DummyInputRow:
        def __init__(self) -> None:
            self.voice_mode = None

        def set_voice_mode(self, enabled: bool) -> None:
            self.voice_mode = bool(enabled)

    class _DummyButton:
        def __init__(self) -> None:
            self.visible = True
            self.enabled = True

        def setVisible(self, enabled: bool) -> None:
            self.visible = bool(enabled)

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = bool(enabled)

    class _DummyInput:
        def __init__(self) -> None:
            self.enabled = True

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = bool(enabled)

    bubble = QtChatBubble.__new__(QtChatBubble)
    bubble.input_container = _DummyContainer()
    bubble._input_row = _DummyInputRow()
    bubble.send_button = _DummyButton()
    bubble.input_text = _DummyInput()
    calls = {"resize": 0, "clamp": 0}
    bubble.setFixedSize = lambda *a, **k: calls.__setitem__("resize", calls["resize"] + 1)  # type: ignore[method-assign]
    bubble._ensure_window_within_screen = lambda *_a, **_k: calls.__setitem__("clamp", calls["clamp"] + 1)  # type: ignore[method-assign]

    bubble._set_voice_ui_mode(True)
    bubble._set_voice_ui_mode(False)

    assert calls["resize"] == 0
    assert calls["clamp"] >= 1
