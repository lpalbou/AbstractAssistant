"""Settings opens fully on screen, and follows the palette off it.

Two operator reports (2026-09-21):

* "the settings window opens far too much to the right, so it appears
  truncated" — `_show_aux_dialog` anchored the window's RIGHT edge to the
  screen's, using a frame read in the same turn as `show()`. Settings sizes
  itself in `_fit_to_content` (it lays each page out before measuring), so
  that read could still be the pre-layout one; anchoring off a too-narrow
  width pushes x too far right and the rest hangs off the screen. Clamping
  could not rescue it — it was handed the same wrong width.
* "whenever the abstractassistant window hides, the settings window should
  hide too" — it had no relationship to the palette's visibility at all.

The second one has a hard boundary: a run PARKED ON THE USER must not be
hidden. An approval sheet that nobody could see is how a run sat 15m52s in
silence (2026-09-07), so only the configuration windows follow.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication, QDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def palette(qapp, tmp_path, monkeypatch):
    import abstractassistant.app as app_module
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.theme import BASE_METRICS, DEFAULT_THEME, activate, activate_metrics

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    # The native traffic-light bridge aborts under the offscreen platform.
    app_module._MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE = False
    controller = AssistantController(config=Config())
    window = app_module.AssistantPalette(controller=controller)
    window.resize(560, 700)
    qapp.processEvents()
    try:
        yield window
    finally:
        # Tear the child windows down explicitly. A Settings dialog left
        # parented to a closed palette aborts the offscreen plugin when the
        # NEXT test builds one — an intermittent `Fatal Python error: Aborted`
        # inside `_show_settings`, not a failure in the code under test.
        for attr in ("_settings_dialog", "_tool_settings_dialog", "_approval_sheet", "_activity_dialog"):
            child = getattr(window, attr, None)
            if child is not None:
                try:
                    child.close()
                    child.setParent(None)
                    child.deleteLater()
                except RuntimeError:
                    pass
                setattr(window, attr, None)
        window.close()
        window.deleteLater()
        qapp.processEvents()
        activate(DEFAULT_THEME)
        activate_metrics(BASE_METRICS.font_body)


def _open_settings(palette, qapp):
    palette.show()
    palette._show_settings("")
    qapp.processEvents()
    qapp.processEvents()  # the deferred placement pass
    dialog = palette._settings_dialog
    assert dialog is not None
    return dialog


@pytest.mark.basic
def test_settings_opens_as_far_into_the_screen_as_it_can(palette, qapp) -> None:
    """Placement never leaves visible width on the table.

    A window WIDER than the screen cannot be contained (Settings has a fixed
    width because its pages have no horizontal scrollbar), so the guarantee is
    the honest one: it starts at the screen's left edge and overflows by no
    more than its own excess. A window that FITS is fully inside.
    """
    dialog = _open_settings(palette, qapp)
    screen = palette._available_screen_geometry()
    assert screen is not None

    frame = dialog.frameGeometry()
    assert frame.top() >= screen.top()
    assert frame.left() >= screen.left(), "settings opened off the left edge"

    excess = max(0, frame.width() - screen.width())
    overflow = max(0, frame.right() - screen.right())
    assert overflow <= excess, (
        f"settings overflows the right edge by {overflow}px but is only "
        f"{excess}px too wide — {overflow - excess}px of it were thrown away "
        "by placement. That is the truncation the operator saw."
    )


@pytest.mark.basic
def test_a_dialog_that_grows_after_show_is_still_placed_inside(palette, qapp) -> None:
    """The exact failure mode: the size Qt reports at show() is not the final one.

    A resizable dialog (Settings is fixed-size, so it cannot play this role) is
    shown small, grown, and re-placed — which is what the deferred pass does
    once the window manager has laid the real frame out.
    """
    palette.show()
    screen = palette._available_screen_geometry()
    dialog = QDialog(palette)
    dialog.resize(200, 200)
    palette._show_aux_dialog(dialog)
    qapp.processEvents()

    # Grown after placement, exactly as Settings grows after `show()`.
    dialog.resize(int(screen.width() * 0.9), dialog.height())
    qapp.processEvents()
    palette._place_aux_dialog(dialog)
    qapp.processEvents()

    frame = dialog.frameGeometry()
    assert frame.right() <= screen.right(), (
        "a dialog that grew after show was left hanging off the right edge"
    )
    assert frame.left() >= screen.left()
    dialog.close()


@pytest.mark.basic
def test_hiding_the_palette_hides_settings(palette, qapp, monkeypatch) -> None:
    # The offscreen platform reports no window as active, so the palette's
    # focus rule fires spuriously and would hide the dialog before the
    # assertion. The subject here is "the palette hid — does Settings
    # follow?", not Qt's focus emulation, so drive the hide directly.
    monkeypatch.setattr(type(palette), "_hide_if_inactive", lambda self: None)
    dialog = _open_settings(palette, qapp)
    assert dialog.isVisible()

    # Focus has left Settings — the real shape of "the user clicked another
    # app". A Settings window still holding focus is deliberately NOT hidden.
    monkeypatch.setattr(type(dialog), "isActiveWindow", lambda self: False)
    palette.hide()
    qapp.processEvents()

    assert not dialog.isVisible(), "settings was left floating over another app"


@pytest.mark.basic
def test_a_run_parked_on_the_user_is_never_hidden_with_the_palette(palette, qapp) -> None:
    """An approval sheet is a question, not configuration. It stays."""
    palette.show()
    sheet = QDialog(palette)
    sheet.show()
    qapp.processEvents()
    palette._approval_sheet = sheet

    palette.hide()
    qapp.processEvents()

    assert sheet.isVisible(), (
        "the approval sheet was hidden with the palette — that is the 15m52s "
        "silent-park incident"
    )
    sheet.close()


@pytest.mark.basic
def test_only_configuration_windows_follow_the_palette(palette) -> None:
    followers = palette._settings_family_dialogs()
    assert all(d is not None for d in followers)
    # Structural guard: the wait surfaces must never join this list.
    palette._approval_sheet = QDialog(palette)
    palette._activity_dialog = QDialog(palette)
    followers = palette._settings_family_dialogs()
    assert palette._approval_sheet not in followers
    assert palette._activity_dialog not in followers


@pytest.mark.basic
def test_settings_with_focus_is_not_yanked_away(palette, qapp, monkeypatch) -> None:
    """The counterpart guard: hiding a window the user is typing in would be
    worse than the orphan window this feature exists to avoid."""
    monkeypatch.setattr(type(palette), "_hide_if_inactive", lambda self: None)
    dialog = _open_settings(palette, qapp)
    monkeypatch.setattr(type(dialog), "isActiveWindow", lambda self: True)

    palette.hide()
    qapp.processEvents()

    assert dialog.isVisible()


# --------------------------------------------------------------------------
# 2026-09-27: "the Settings window opens too far to the right, partially off
# screen (the Connect button is cut by the screen edge)". Settings re-measures
# itself AFTER it is placed — `_register_aux_dialog` re-applies its stylesheet
# a turn after show, `restyle()` defers `_refit`, and `_fit_to_content` sets a
# new fixed size — and a window grows from its top-left corner, so a wider fit
# pushed its right side past the screen edge. Every placement now goes through
# `_fit_window_rect`, and a re-fit re-clamps.


class _Area:
    def __init__(self, x, y, w, h):
        self._g = (x, y, w, h)

    def x(self):
        return self._g[0]

    def y(self):
        return self._g[1]

    def width(self):
        return self._g[2]

    def height(self):
        return self._g[3]


_MAC = _Area(0, 39, 1800, 1082)  # menu bar above, Dock hidden


@pytest.mark.basic
def test_fit_rect_pulls_a_right_edge_overflow_back_inside_the_gap() -> None:
    from abstractassistant.app import _fit_window_rect

    x, y, w, h = _fit_window_rect(x=964, y=51, width=917, height=608, area=_MAC, gap=12)
    assert (w, h) == (917, 608)
    assert x + w == 1800 - 12
    assert y == 51


@pytest.mark.basic
def test_fit_rect_pulls_a_bottom_overflow_back_inside_the_gap() -> None:
    from abstractassistant.app import _fit_window_rect

    x, y, w, h = _fit_window_rect(x=100, y=900, width=820, height=608, area=_MAC, gap=12)
    assert (x, w, h) == (100, 820, 608)
    assert y + h == 39 + 1082 - 12


@pytest.mark.basic
def test_fit_rect_keeps_the_gap_from_the_left_and_top_edges_too() -> None:
    from abstractassistant.app import _fit_window_rect

    assert _fit_window_rect(x=-50, y=0, width=820, height=608, area=_MAC, gap=12)[:2] == (12, 51)


@pytest.mark.basic
def test_fit_rect_shrinks_a_window_larger_than_the_screen() -> None:
    from abstractassistant.app import _fit_window_rect

    area = _Area(0, 25, 800, 575)
    x, y, w, h = _fit_window_rect(x=300, y=25, width=1000, height=900, area=area, gap=12)
    assert (x, y, w, h) == (12, 37, 776, 551)


@pytest.mark.basic
def test_fit_rect_leaves_a_window_that_fits_where_it_is() -> None:
    from abstractassistant.app import _fit_window_rect

    assert _fit_window_rect(x=400, y=200, width=820, height=608, area=_MAC, gap=12) == (400, 200, 820, 608)


def _inside(frame, area, gap: int) -> bool:
    return (
        frame.left() >= area.left() + gap
        and frame.top() >= area.top() + gap
        and frame.right() <= area.right() - gap
        and frame.bottom() <= area.bottom() - gap
    )


@pytest.fixture
def mac_screen(palette, monkeypatch):
    """A 1800x1082 available area (offscreen's own screen is 800x600, too
    small for Settings to ever FIT, which is the case the operator hit)."""
    from PyQt5.QtCore import QRect

    area = QRect(0, 39, 1800, 1082)
    monkeypatch.setattr(palette, "_available_screen_geometry", lambda: area)
    # Offscreen reports no active window, so the palette's focus rule would
    # hide it (and Settings with it) mid-test.
    monkeypatch.setattr(type(palette), "_hide_if_inactive", lambda self: None)
    return area


@pytest.mark.basic
def test_settings_opened_from_a_palette_at_the_right_edge_is_inside_the_screen(
    palette, qapp, mac_screen
) -> None:
    """Headless end to end: a larger type scale makes the post-show re-fit
    WIDER than the first fit (820 -> ~917 px), exactly the late growth that
    left the right side past the screen edge."""
    palette.apply_typography(text_size=22)
    palette.show()
    palette.position_near_tray()
    qapp.processEvents()
    assert palette.frameGeometry().right() >= mac_screen.right() - 40  # palette hugs the right edge

    dialog = _open_settings(palette, qapp)
    for _ in range(5):
        qapp.processEvents()  # the re-applied stylesheet, then the deferred re-fit
    gap = palette._screen_edge_gap(mac_screen)
    frame = dialog.frameGeometry()
    assert frame.width() > 820, "the late re-fit did not grow the window; the test lost its bite"
    assert _inside(frame, mac_screen, gap), f"settings {frame} is not inside {mac_screen} minus {gap}px"

    # Re-show: same guarantee.
    dialog.hide()
    qapp.processEvents()
    palette._show_settings("connection")
    for _ in range(5):
        qapp.processEvents()
    assert _inside(dialog.frameGeometry(), mac_screen, gap)


@pytest.mark.basic
def test_settings_that_grows_while_open_stays_inside_the_screen(palette, qapp, mac_screen) -> None:
    dialog = _open_settings(palette, qapp)
    for _ in range(3):
        qapp.processEvents()
    palette.apply_typography(text_size=22)  # text size changed from Appearance
    for _ in range(5):
        qapp.processEvents()
    assert _inside(dialog.frameGeometry(), mac_screen, palette._screen_edge_gap(mac_screen))


@pytest.mark.basic
def test_settings_larger_than_the_screen_is_shrunk_to_fit(palette, qapp, monkeypatch) -> None:
    from PyQt5.QtCore import QRect

    area = QRect(0, 25, 760, 520)
    monkeypatch.setattr(palette, "_available_screen_geometry", lambda: area)
    monkeypatch.setattr(type(palette), "_hide_if_inactive", lambda self: None)
    dialog = _open_settings(palette, qapp)
    for _ in range(5):
        qapp.processEvents()
    assert _inside(dialog.frameGeometry(), area, palette._screen_edge_gap(area))
