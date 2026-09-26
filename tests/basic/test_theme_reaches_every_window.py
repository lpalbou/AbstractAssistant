"""A theme switch must reach every window, including ones already open.

The operator's complaint was not "the theme is wrong" but "it's not even
respecting our theme, even after reselecting another theme" — the failure is
in the *switch*, not the palette. Two things made a window ignore it:

* a stylesheet or colour map built at import/class-definition time, which
  keeps the palette the module was loaded with forever;
* a window with no ``restyle()``, which ``apply_theme``'s sweep skips.

These tests build the windows on the default dark palette, switch to a light
one, and read the colours each window actually declares — background and text
kept apart, because averaging the two just cancels them out.
"""

from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from abstractassistant.retint import parse_color  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def palette(qapp, tmp_path, monkeypatch):
    import abstractassistant.app as app_module
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.theme import BASE_METRICS, DEFAULT_THEME, activate, activate_metrics

    # A real preferences store, in a temp home: these tests CHANGE preferences
    # (theme, text size) and must see the change round-trip, without touching
    # the developer's own file.
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
        window.close()
        # Building a palette applies the USER's saved theme and text size, both
        # of which are process-global; leaving them set changes what every
        # later test sees.
        activate(DEFAULT_THEME)
        activate_metrics(BASE_METRICS.font_body)


def _luma(rgb) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _declared(widget, prop: str):
    """Mean luminance of one property across a widget's own stylesheet.

    Translucent values are skipped: they take their lightness from whatever is
    behind them, so they say nothing about the widget's own palette.
    """
    css = widget.styleSheet() or ""
    pattern = (
        r"background(?:-color)?\s*:\s*([^;\n}]+)"
        if prop == "background"
        else r"(?<![-a-z])color\s*:\s*([^;\n}]+)"
    )
    found = []
    for value in re.findall(pattern, css):
        parsed = parse_color(value.strip())
        if not parsed:
            continue
        rgb, alpha = parsed
        if alpha is not None and alpha < 0.5:
            continue
        found.append(_luma(rgb))
    return (sum(found) / len(found)) if found else None


def _open_windows(palette, module):
    """One of every window the user can have on screen at once."""
    from PyQt5.QtGui import QPixmap

    from abstractassistant.ui.approval import ToolApprovalSheet
    from abstractassistant.ui.dialogs import AskUserDialog
    from abstractassistant.ui.session_switcher import SessionSwitcher
    from abstractassistant.ui.voice_strip import VoiceStrip

    windows = [("AssistantPalette", palette)]

    # `_show_settings`, not `_open_settings`: the latter warms its caches on a
    # thread and builds the dialog from the callback.
    palette._show_settings()
    windows.append(("SettingsDialog", palette._settings_dialog))

    switcher = SessionSwitcher(parent=palette)
    switcher.set_digests([], active_session_id="")
    windows.append(("SessionSwitcher", switcher))

    windows.append(("AskUserDialog", AskUserDialog(prompt="Which branch?", parent=palette)))
    windows.append((
        "ToolApprovalSheet",
        ToolApprovalSheet(
            tool_calls=[{"name": "read_file", "arguments": {"file_path": "/etc/hosts"}}],
            run_id="r1",
            wait_key="w1",
            parent=palette,
        ),
    ))

    message = {"role": "assistant", "content": "hello", "metadata": {}}
    calls = [{"name": "read_file", "arguments": {"file_path": "/etc/hosts"}, "result": "ok"}]
    for name in ("ToolUsageDialog", "FileActivityDialog"):
        windows.append((
            name,
            getattr(module, name)(
                message=message, tool_calls=calls, source="t", run_ids=["r1"], parent=palette
            ),
        ))

    pixmap = QPixmap(80, 60)
    pixmap.fill()
    windows.append((
        "ImagePreviewDialog",
        module.ImagePreviewDialog(pixmap=pixmap, title="shot.png", parent=palette),
    ))

    strip = VoiceStrip(palette)
    strip.set_state("listening")
    windows.append(("VoiceStrip", strip))

    for _, window in windows[1:]:
        window.show()
    return windows


@pytest.mark.basic
def test_a_theme_switch_reaches_windows_that_are_already_open(qapp, palette) -> None:
    import abstractassistant.app as app_module

    windows = _open_windows(palette, app_module)
    qapp.processEvents()

    for theme_id, light in (("catppuccin-latte", True), ("tokyo-night", False)):
        assert palette.apply_theme(theme_id, persist=False)
        qapp.processEvents()
        for name, window in windows:
            background = _declared(window, "background")
            text = _declared(window, "color")
            if background is None and text is None:
                continue  # inherits its parent's sheet; nothing of its own to go stale
            if background is not None:
                if light:
                    assert background > 150, f"{name} kept a dark background on {theme_id}"
                else:
                    assert background < 110, f"{name} kept a light background on {theme_id}"
            if text is not None:
                if light:
                    assert text < 110, f"{name} kept light text on {theme_id}"
                else:
                    assert text > 140, f"{name} kept dark text on {theme_id}"


@pytest.mark.basic
def test_no_window_freezes_a_palette_at_import_time() -> None:
    """A colour read into a module constant or a class attribute is captured
    once, at import, and no restyle can reach it. Both of the app's remaining
    cases (the voice strip's glyph tones, the run log's row tones) were found
    exactly this way.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "abstractassistant"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        source = path.read_text()
        if "THEME." not in source:
            continue
        tree = ast.parse(source)

        def _scan(body, where):
            for node in body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                segment = ast.get_source_segment(source, node) or ""
                if "THEME." in segment or "METRICS." in segment:
                    offenders.append(f"{path.relative_to(root)}:{node.lineno} ({where})")

        _scan(tree.body, "module")
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                _scan(node.body, f"class {node.name}")

    assert not offenders, "palette frozen at import: " + ", ".join(offenders)


@pytest.mark.basic
def test_the_theme_survives_a_relaunch(tmp_path, monkeypatch, qapp) -> None:
    import json

    import abstractassistant.app as app_module
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.theme import DEFAULT_THEME, THEME, activate
    from abstractassistant.ui_themes import build_theme

    home = tmp_path / "home"
    (home / ".abstractassistant").mkdir(parents=True)
    (home / ".abstractassistant" / "preferences.json").write_text(json.dumps({"ui_theme": "gruvbox"}))
    monkeypatch.setenv("HOME", str(home))

    controller = AssistantController(config=Config())
    assert controller.preferences.ui_theme == "gruvbox"

    window = app_module.AssistantPalette(controller=controller)
    try:
        qapp.processEvents()
        wanted = build_theme("gruvbox")
        assert THEME.accent == wanted.accent
        assert THEME.surface_card == wanted.surface_card
    finally:
        window.close()
        # THEME is a process-global mutated in place, so a test that leaves a
        # theme active changes what every later test sees.
        activate(DEFAULT_THEME)


@pytest.mark.basic
def test_icons_follow_a_theme_switch_the_same_as_a_restart(qapp, palette) -> None:
    """An icon is a rendered bitmap, baked with whatever palette was live when
    its widget was built. Restyling a stylesheet never touched them, so after
    switching to a light theme the composer and toolbar glyphs stayed
    near-white on a near-white background — invisible until a restart.
    """
    from PyQt5.QtWidgets import QWidget

    def glyph_luma(widget):
        icon = widget.icon()
        if icon is None or icon.isNull():
            return None
        image = icon.pixmap(24, 24).toImage()
        total = count = 0
        for y in range(image.height()):
            for x in range(image.width()):
                colour = image.pixelColor(x, y)
                if colour.alpha() < 40:
                    continue
                total += _luma((colour.red(), colour.green(), colour.blue())) / 255.0
                count += 1
        return (total / count) if count else None

    watched = ("composerIconButton", "iconButton", "topIconToggleButton", "sendButton")

    def sample(window):
        found = {}
        for widget in window.findChildren(QWidget):
            name = widget.objectName()
            if name in watched and hasattr(widget, "icon"):
                value = glyph_luma(widget)
                if value is not None:
                    found.setdefault(name, value)
        return found

    palette.apply_theme("catppuccin-latte", persist=False)
    qapp.processEvents()
    switched = sample(palette)
    assert switched, "no icon-bearing widgets found to check"

    # A window built while the light theme is already live is what a restart
    # looks like. The two must agree.
    import abstractassistant.app as app_module
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController

    controller = AssistantController(config=Config())
    controller.update_preferences = lambda **kwargs: None
    fresh = app_module.AssistantPalette(controller=controller)
    try:
        qapp.processEvents()
        booted = sample(fresh)
        for name, value in switched.items():
            reference = booted.get(name)
            if reference is None:
                continue
            assert abs(value - reference) < 0.05, (
                f"{name}: {value:.3f} after a switch vs {reference:.3f} after a restart"
            )
    finally:
        fresh.close()


@pytest.mark.basic
def test_a_dialog_is_sized_by_its_own_stylesheet_not_the_chat_window(qapp, palette) -> None:
    """Settings is a CHILD of the palette in Qt's object tree, so the chat
    window's stylesheet cascaded into it and its bare type selectors won:
    footer buttons came out 50px against the 30-36 the dialog asks for, and
    text fields 44px against 28 — the operator's "what the fuck is that
    layout". The palette's sheet is scoped to its own root surface, which no
    dialog is inside.

    The dialog must ALSO be the thing that styles itself: with the leak gone,
    an unstyled dialog renders white native controls, and that is exactly what
    the leak had been hiding.
    """
    from PyQt5.QtWidgets import QLineEdit, QPushButton

    from abstractassistant.theme import METRICS

    palette._show_settings()
    dialog = palette._settings_dialog
    dialog.show()
    for _ in range(4):
        qapp.processEvents()

    buttons = [b for b in dialog.findChildren(QPushButton) if b.objectName() == "primaryButton" and b.isVisible()]
    fields = [w for w in dialog.findChildren(QLineEdit) if w.isVisible()]
    assert buttons and fields

    # The dialog's own control size, plus its own padding and border — never
    # the palette's taller one.
    ceiling = METRICS.control_sm + 12
    assert buttons[0].height() <= ceiling, (
        f"footer button is {buttons[0].height()}px; the dialog asks for ~{METRICS.control_sm}"
    )
    assert fields[0].height() <= ceiling, f"text field is {fields[0].height()}px"

    # And it must actually be PAINTED by the dialog's sheet. An unstyled
    # QLineEdit renders white; the dialog's is a dark surface token.
    image = fields[0].grab().toImage()
    centre = image.pixelColor(image.width() // 2, image.height() // 2)
    assert _luma((centre.red(), centre.green(), centre.blue())) < 140, (
        f"text field rendered unstyled ({centre.name()}) — the dialog's own sheet never applied"
    )


@pytest.mark.basic
def test_the_chat_windows_stylesheet_is_confined_to_the_chat_window(qapp, palette) -> None:
    """Every rule the palette applies must be scoped to its own root surface.

    A bare `QPushButton` rule here reaches every dialog, because a dialog is a
    child of this window. Scoping must be UNIFORM — scoping only the bare
    selectors lifts them above the palette's own `#id` rules and blows up the
    chat window itself (the composer glyphs doubled and the stats chips grew
    boxes), which is why this checks the applied sheet rather than the source.
    """
    import re

    applied = palette.styleSheet()
    assert applied, "the palette has no stylesheet at all"

    unscoped = []
    for match in re.finditer(r"(?m)^[ \t]*([^{}\n][^{}]*?)[ \t]*\{", applied):
        for part in (p.strip() for p in match.group(1).split(",")):
            if not part or part.startswith(("QMainWindow", "QDialog", "QToolTip", "QMenu")):
                continue
            if not part.startswith("QWidget#rootSurface"):
                unscoped.append(part)
    assert not unscoped, "these reach every other window: " + ", ".join(sorted(set(unscoped))[:6])


@pytest.mark.basic
def test_the_text_size_setting_reaches_every_window(qapp, palette, tmp_path, monkeypatch) -> None:
    """Text size is the app's TYPE SCALE, not a transcript setting.

    It used to feed only the markdown the transcript renders, so Settings and
    every dialog kept a fixed scale while the chat changed — the mismatch the
    operator reported. It now drives METRICS, which every window reads, and
    control heights move with it so bigger text does not clip its own control.
    """
    from PyQt5.QtCore import QRect
    from PyQt5.QtWidgets import QLineEdit

    from abstractassistant.theme import METRICS

    # A real Mac screen. Offscreen's own is 800x600, narrower than Settings at
    # text size 17, and since 2026-09-27 a window wider than the screen is
    # shrunk into it (fully visible beats complete) — which would clip here for
    # a reason that has nothing to do with the re-fit this test is about.
    monkeypatch.setattr(palette, "_available_screen_geometry", lambda: QRect(0, 39, 1800, 1082))
    palette._show_settings()
    dialog = palette._settings_dialog
    dialog.show()
    for _ in range(4):
        qapp.processEvents()

    def measure():
        field = [w for w in dialog.findChildren(QLineEdit) if w.isVisible()][0]
        return METRICS.font_body, METRICS.control_sm, field.height()

    seen = {}
    for size in (11, 17):
        assert palette.apply_typography(text_size=size)
        for _ in range(6):
            qapp.processEvents()
        body, control, field_height = measure()
        assert body == size, f"METRICS did not follow text_size={size} (body={body})"
        seen[size] = (control, field_height)

    small_control, small_field = seen[11]
    large_control, large_field = seen[17]
    assert large_control > small_control, "control heights ignored the text size"
    assert large_field > small_field, (
        f"the dialog's own fields did not grow with the text ({small_field} -> {large_field})"
    )

    # Bigger text must not clip: the window re-fits to the new scale.
    for name in dialog.pages:
        dialog.show_section(name)
        for _ in range(3):
            qapp.processEvents()
        page = dialog.stack.currentWidget()
        needed = page.scroll.widget().minimumSizeHint().width()
        assert needed <= page.scroll.viewport().width(), f"{name} clips at text size 17"
