"""Window defaults: 650 px wide, 12 px from the screen edges (2026-09-25; gap 28 -> 12 on 2026-09-27).

The gap preference used to be capped in code (``min(pref_gap, 8)`` for the
palette, 10/12 for Settings), so any value above 8 did nothing; a saved 0 was
turned back into 18 by ``or 18``. Layout version 2 moves users who still have
the OLD defaults to the new ones exactly once and keeps anything they chose.
"""

from __future__ import annotations

import os

import pytest

from abstractassistant.preferences import (
    DEFAULT_SCREEN_EDGE_GAP,
    DEFAULT_WINDOW_WIDTH,
    LAYOUT_VERSION,
    AssistantPreferences,
    PreferencesStore,
)


@pytest.mark.basic
def test_new_defaults() -> None:
    prefs = AssistantPreferences()
    assert (prefs.window_width, prefs.bottom_offset) == (650, 12)
    assert AssistantPreferences.from_dict({}).window_width == 650
    assert AssistantPreferences.from_dict({}).bottom_offset == 12
    assert LAYOUT_VERSION == 2


@pytest.mark.basic
@pytest.mark.parametrize(
    ("saved", "expected"),
    [
        # v1 files holding the OLD defaults move to the new ones...
        ({"layout_version": 1, "window_width": 500, "bottom_offset": 18}, (650, 12)),
        ({"window_width": 500, "bottom_offset": 18}, (650, 12)),
        # ...and a 0.6.0 file holding its 28 keeps it (a saved gap is respected)...
        ({"layout_version": 2, "window_width": 650, "bottom_offset": 28}, (650, 28)),
        # ...a value the user changed is kept...
        ({"layout_version": 1, "window_width": 720, "bottom_offset": 40}, (720, 40)),
        ({"layout_version": 1, "window_width": 500, "bottom_offset": 6}, (650, 6)),
        # ...a saved 0 gap is a choice, not "unset"...
        ({"layout_version": 1, "window_width": 800, "bottom_offset": 0}, (800, 0)),
        # ...and once stamped v2, 500/18 are deliberate and stay.
        ({"layout_version": 2, "window_width": 500, "bottom_offset": 18}, (500, 18)),
    ],
)
def test_layout_v2_migration_rule(saved: dict, expected: tuple) -> None:
    prefs = AssistantPreferences.from_dict(saved)
    assert (prefs.window_width, prefs.bottom_offset) == expected


@pytest.mark.basic
def test_migration_happens_once_and_zero_survives_a_round_trip(tmp_path) -> None:
    store = PreferencesStore(tmp_path / "preferences.json")
    store._write({"layout_version": 1, "window_width": 500, "bottom_offset": 18, "window_height": 400})
    migrated = store.load()
    assert (migrated.window_width, migrated.bottom_offset) == (650, 12)
    # The v1 height migration (x0.85) must not run a second time for a v1 file.
    assert migrated.window_height == 400
    store.save(migrated)
    store.save(AssistantPreferences.from_dict({**migrated.to_dict(), "bottom_offset": 0}))
    assert store.load().bottom_offset == 0


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Screen:
    def __init__(self, x=0, y=25, w=1440, h=875):
        self._g = (x, y, w, h)

    def x(self):
        return self._g[0]

    def y(self):
        return self._g[1]

    def width(self):
        return self._g[2]

    def height(self):
        return self._g[3]


@pytest.mark.basic
@pytest.mark.parametrize("gap", [0, 8, 28, 60])
def test_the_gap_preference_is_honoured_not_capped(gap: int) -> None:
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtWidgets import QApplication

    import abstractassistant.app as app_module

    _app = QApplication.instance() or QApplication([])  # noqa: F841
    palette = app_module.AssistantPalette.__new__(app_module.AssistantPalette)
    palette._controller = type("C", (), {"preferences": AssistantPreferences(bottom_offset=gap)})()
    assert app_module.AssistantPalette._screen_edge_gap(palette, _Screen()) == gap
    # Clamped only so a window still fits on a tiny screen.
    assert app_module.AssistantPalette._screen_edge_gap(palette, _Screen(w=100, h=100)) == min(gap, 25)


@pytest.mark.basic
@pytest.mark.parametrize("gap", [0, 28, 44])
def test_settings_page_shows_the_saved_gap_even_zero(gap: int) -> None:
    pytest.importorskip("PyQt5.QtWidgets")
    from test_settings_pages import _dialog

    dlg, ctl = _dialog()
    ctl.preferences = AssistantPreferences(hotkey_enabled=False, bottom_offset=gap)
    dlg.show_section("window")
    dlg.page_window.refresh()
    assert dlg.page_window.bottom_offset_spin.value() == gap
    assert dlg.page_window.width_spin.value() == DEFAULT_WINDOW_WIDTH
    dlg.page_window._save_preferences()
    assert ctl.preferences.bottom_offset == gap
    assert DEFAULT_SCREEN_EDGE_GAP == 12


@pytest.mark.basic
def test_no_hidden_caps_below_the_settings_ranges() -> None:
    # A saved gap of 150 / width 1800 survive loading (the old loader cut the gap to 80).
    prefs = AssistantPreferences.from_dict({"layout_version": 2, "bottom_offset": 150, "window_width": 1800})
    assert (prefs.bottom_offset, prefs.window_width) == (150, 1800)
    assert AssistantPreferences.from_dict({"layout_version": 2, "bottom_offset": 999}).bottom_offset == 200


@pytest.mark.basic
def test_settings_spinners_reach_the_new_ranges() -> None:
    pytest.importorskip("PyQt5.QtWidgets")
    from test_settings_pages import _dialog

    dlg, _ctl = _dialog()
    page = dlg.page_window
    assert (page.bottom_offset_spin.minimum(), page.bottom_offset_spin.maximum()) == (0, 200)
    assert (page.width_spin.minimum(), page.width_spin.maximum()) == (420, 2000)


@pytest.mark.basic
def test_the_window_width_is_limited_only_by_the_screen(tmp_path, monkeypatch) -> None:
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtCore import QRect
    from PyQt5.QtWidgets import QApplication

    import abstractassistant.app as app_module
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.theme import BASE_METRICS, DEFAULT_THEME, activate, activate_metrics

    app = QApplication.instance() or QApplication([])
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    app_module._MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE = False
    controller = AssistantController(config=Config(), data_dir=tmp_path / "data")
    controller.update_preferences(hotkey_enabled=False, window_width=1500)
    window = app_module.AssistantPalette(controller=controller)
    try:
        monkeypatch.setattr(window, "_available_screen_geometry", lambda: QRect(0, 0, 3000, 1600))
        window._reflow_shell()
        app.processEvents()
        assert window.width() == 1500  # was capped at 960
        monkeypatch.setattr(window, "_available_screen_geometry", lambda: QRect(0, 0, 1440, 900))
        window._reflow_shell()
        assert window.width() == int(1440 * 0.62)
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
        activate(DEFAULT_THEME)
        activate_metrics(BASE_METRICS.font_body)
