"""Optional global hotkey support for the v2 tray shell."""

from __future__ import annotations

from typing import Callable, Optional


def _normalize_sequence(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "<cmd>+<shift>+space"
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
        parts.append(token)
    return "+".join(parts) or "<cmd>+<shift>+space"


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
            trigger = keyboard.HotKey(parsed, lambda: callback())
            self._listener = keyboard.Listener(
                on_press=lambda key: trigger.press(key),
                on_release=lambda key: trigger.release(key),
            )
            self._listener.daemon = True
            self._listener.start()
            self._registered = hotkey
            self._error = ""
            return True
        except Exception as exc:  # pragma: no cover - depends on OS permissions/runtime
            self._listener = None
            self._registered = ""
            self._error = f"#FALLBACK: failed to register global hotkey {hotkey!r} ({exc})"
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
