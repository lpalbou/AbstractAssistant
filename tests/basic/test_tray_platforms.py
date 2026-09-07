"""The tray must not be the only way in, and must not fight the platform.

Reviewed 2026-09-06 against the shipped Qt backends: modern GNOME dropped both
the XEmbed tray and the StatusNotifier host, so `isSystemTrayAvailable()` is
False there and under Wayland — and the app used to respond by hiding its only
window and running on with no icon and no message.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: E402

import abstractassistant.app as app_module  # noqa: E402
from abstractassistant.app import TrayVisibilityState, _handle_tray_activation  # noqa: E402


_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


@pytest.mark.basic
def test_macos_readiness_survives_a_missing_appkit() -> None:
    """`native_item_count` is -1 when AppKit cannot be asked at all — pyobjc is
    an optional install. Reporting "never ready" for that made a plain pip
    install look permanently broken."""
    unknown = TrayVisibilityState(available=True, qt_visible=True, native_item_count=-1)
    assert unknown.ready is True

    # When AppKit CAN be asked, its answer is the one that counts.
    if sys.platform == "darwin":
        assert (
            TrayVisibilityState(
                available=True, qt_visible=True, native_item_count=0
            ).ready
            is False
        )
        assert (
            TrayVisibilityState(
                available=True,
                qt_visible=True,
                native_item_count=1,
                native_button_size=(24, 24),
                native_image_size=(18, 18),
            ).ready
            is True
        )

    # An unavailable tray is never "ready" anywhere.
    assert TrayVisibilityState(available=False, qt_visible=False).ready is False


@pytest.mark.basic
def test_linux_does_not_get_a_second_context_menu(monkeypatch) -> None:
    """Both Linux paths show the menu themselves — the D-Bus host renders the
    exported dbusmenu, and the XEmbed path pops it before emitting Context — so
    popping our own would show two, at a position Wayland cannot report."""
    _app()
    popped: list = []

    class _Menu(QMenu):
        def popup(self, point):  # noqa: N802 (Qt API)
            popped.append(point)

    menu = _Menu()
    palette = object()

    monkeypatch.setattr(app_module.sys, "platform", "linux")
    _handle_tray_activation(
        palette=palette, menu=menu, reason=QSystemTrayIcon.Context
    )
    assert popped == [], "the platform already showed a menu"

    # Windows needs it: Qt disables native menus for a QApplication, so nothing
    # else will show one.
    monkeypatch.setattr(app_module.sys, "platform", "win32")
    _handle_tray_activation(
        palette=palette, menu=menu, reason=QSystemTrayIcon.Context
    )
    assert len(popped) == 1

    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    _handle_tray_activation(
        palette=palette, menu=menu, reason=QSystemTrayIcon.Context
    )
    assert len(popped) == 2
    menu.deleteLater()


@pytest.mark.basic
def test_the_animation_rate_respects_what_a_frame_costs() -> None:
    """Rendering a frame is ~0.1 ms, but publishing one is not: Windows rebuilds
    an HICON and makes a shell IPC call per frame, and Linux republishes the
    whole pixmap over D-Bus (~9.7 KB)."""
    interval = app_module._TRAY_VOICE_FRAME_INTERVAL_MS
    assert interval > 0
    if sys.platform == "darwin":
        assert interval <= 100, "macOS updates the status item locally"
    else:
        assert interval >= 150, "do not stream frames through the platform bus"


@pytest.mark.basic
def test_an_unavailable_tray_is_announced_not_swallowed() -> None:
    """The single diagnostic that existed only printed inside a frozen macOS
    build, so on Linux the app went quiet in every sense."""
    import inspect

    source = inspect.getsource(app_module._refresh_tray_visibility)
    assert "warnings.warn" in source, "the cause must reach a plain pip install"
    assert "AppIndicator" in source, "name what to do about it"

    # And the launcher must not hide the only window when there is no tray.
    launcher = inspect.getsource(app_module.launch_tray_app)
    assert "tray_state = _refresh_tray_visibility" in launcher, (
        "the startup state was computed and thrown away"
    )
    assert "if not tray_state.available:" in launcher
