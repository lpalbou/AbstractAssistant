"""Regressions for the chat-input key handling helpers.

`handle_key_press` is monkey-patched onto the input QTextEdit and evaluates
`_qt_key(...)` as its first expression: if these helpers raise, every keypress
dies before the character is inserted (typing appears completely broken).
"""

from __future__ import annotations

import pytest

from abstractassistant.ui.qt_bubble import QtChatBubble


@pytest.mark.basic
def test_qt_key_resolves_without_instance() -> None:
    # Regression: `_qt_key` was declared @classmethod without a `cls` param,
    # so every call raised TypeError and broke all typing in the bubble.
    for name in ("Key_Up", "Key_Down", "Key_Return", "Key_Escape"):
        key = QtChatBubble._qt_key(name)
        assert key is not None, f"{name} did not resolve"


@pytest.mark.basic
def test_qt_keyboard_modifier_resolves_without_instance() -> None:
    value = QtChatBubble._qt_keyboard_modifier("ShiftModifier")
    assert int(value) != 0


@pytest.mark.basic
def test_prompt_placeholder_matches_send_semantics() -> None:
    # Plain Enter sends; Shift+Enter inserts a newline. The placeholder is the
    # only in-UI hint, so it must not teach the opposite gesture.
    import inspect

    from abstractassistant.ui import qt_bubble

    source = inspect.getsource(qt_bubble)
    assert "Shift+Enter to send" not in source
