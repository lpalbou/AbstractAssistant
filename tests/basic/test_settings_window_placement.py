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
