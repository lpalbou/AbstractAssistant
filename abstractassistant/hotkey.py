"""Optional global hotkey support for the tray shell."""

from __future__ import annotations

import logging
import sys
from typing import Callable, Optional

_LOG = logging.getLogger(__name__)

# Named keys pynput parses only in brackets (`<space>`); a bare `space` makes
# `HotKey.parse` raise ValueError('space'), which is how the default
# `cmd+shift+space` never registered (through 0.7.0).
_NAMED_KEYS = {
    "space", "tab", "enter", "esc", "backspace", "delete", "home", "end",
    "page_up", "page_down", "up", "down", "left", "right",
    *(f"f{n}" for n in range(1, 21)),
}
_KEY_ALIASES = {"return": "enter", "escape": "esc", "pageup": "page_up", "pagedown": "page_down"}


def _macos_input_trusted() -> bool:
    """Can this process observe the keyboard at all? On macOS a listener in an
    untrusted process starts but never receives a key, so it is not started."""
    if sys.platform != "darwin":
        return True
    # pyobjc-framework-ApplicationServices is a declared macOS dependency.
    import HIServices  # type: ignore[import-not-found]

    return bool(HIServices.AXIsProcessTrusted())


def _normalize_sequence(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "<cmd>+<shift>+<space>"
    parts: list[str] = []
    for token in raw.replace(" ", "").split("+"):
        token = token.strip()
        if not token:
            continue
        if token in {"cmd", "command", "meta", "super", "win", "windows"}:
            parts.append("<cmd>")
            continue
        if token in {"ctrl", "control"}:
            parts.append("<ctrl>")
            continue
        if token == "shift":
            parts.append("<shift>")
            continue
        if token in {"alt", "option"}:
            parts.append("<alt>")
            continue
        token = _KEY_ALIASES.get(token, token)
        if token in _NAMED_KEYS:
            parts.append(f"<{token}>")
            continue
        parts.append(token)
    return "+".join(parts) or "<cmd>+<shift>+<space>"


class GlobalHotkeyManager:
    def __init__(self) -> None:
        self._listener = None
        self._registered = ""
        self._error = ""

    @property
    def registered(self) -> str:
        return self._registered

    @property
    def error(self) -> str:
        return self._error

    def start(self, *, sequence: str, callback: Callable[[], None]) -> bool:
        self.stop()
        hotkey = _normalize_sequence(sequence)
        try:
            from pynput import keyboard
        except Exception as exc:  # pragma: no cover - optional dependency
            self._error = f"#FALLBACK: global hotkey unavailable ({exc})"
            return False

        try:
            parsed = keyboard.HotKey.parse(hotkey)
        except ValueError as exc:
            return self._fail(f"#FALLBACK: global hotkey {sequence!r} is not a valid key combination ({exc})")
        if not _macos_input_trusted():
            return self._fail(
                f"#FALLBACK: global hotkey {hotkey!r} not registered: macOS has not allowed this process "
                f"({sys.executable}) to read the keyboard. Grant it in System Settings → Privacy & Security "
                "→ Accessibility (and Input Monitoring), then save the shortcut again."
            )
        try:
            trigger = keyboard.HotKey(parsed, lambda: callback())
            # HotKey compares against parsed keys; the listener reports raw ones
            # (Key.space, Key.cmd_r). `canonical` maps them to the parsed form —
            # without it the combination can never match. (`listener` is read
            # when a key arrives, after the assignment.)
            listener = keyboard.Listener(
                on_press=lambda key: trigger.press(listener.canonical(key)),
                on_release=lambda key: trigger.release(listener.canonical(key)),
            )
            listener.daemon = True
            listener.start()
            self._listener = listener
            self._registered = hotkey
            self._error = ""
            return True
        except Exception as exc:  # pragma: no cover - depends on OS permissions/runtime
            self._listener = None
            return self._fail(f"#FALLBACK: failed to register global hotkey {hotkey!r} ({exc})")

    def _fail(self, message: str) -> bool:
        self._listener = None
        self._registered = ""
        self._error = message
        _LOG.warning("%s", message)
        return False

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        self._registered = ""
        if listener is None:
            return
        try:
            listener.stop()
        except Exception:
            pass
