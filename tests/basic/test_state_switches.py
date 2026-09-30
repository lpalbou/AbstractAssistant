"""On/off settings are switches labelled by the feature (operator rule 2026-09-30).

The web clients use the ui-kit's ``AfSwitch``; the Assistant has the same
control as ``abstractassistant.ui.switch.AfSwitch``. These tests fail when a
setting goes back to a plain checkbox, a verb label, a Save button, or an
"unavailable" that is really a dead (disabled) control.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, Qt  # noqa: E402
from PyQt5.QtGui import QKeyEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QCheckBox, QLabel, QRadioButton  # noqa: E402

from abstractassistant.ui.switch import AfSwitch  # noqa: E402

_APP = None
PACKAGE = Path(__file__).resolve().parents[2] / "abstractassistant"


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _dialog():
    from test_settings_pages import _dialog as make

    return make()


def _center_pixel(sw: AfSwitch, x: int):
    image = sw.grab().toImage()
    return image.pixelColor(x * image.width() // max(1, sw.width()), image.height() // 2)


# ------------------------------------------------------------------ widget


@pytest.mark.basic
def test_the_switch_shows_on_and_off_differently_and_the_label_is_the_feature() -> None:
    _app()
    sw = AfSwitch("Speak replies automatically")
    from abstractassistant.theme import THEME
    from abstractassistant.ui.switch import qcolor

    accent = qcolor(THEME.accent)

    def near_accent(color) -> bool:
        return abs(color.red() - accent.red()) + abs(color.green() - accent.green()) + abs(color.blue() - accent.blue()) < 40

    sw.resize(sw.sizeHint())
    # x=5: inside the track's left end, left of the OFF thumb (never covered by a thumb).
    off_track = _center_pixel(sw, 5)
    off_weight = sw._label_font().weight()
    sw.setChecked(True)
    on_track = _center_pixel(sw, 5)
    # ON: the track fills with the accent (colour), the label turns bold (weight).
    assert near_accent(on_track) and not near_accent(off_track), (on_track.name(), off_track.name(), accent.name())
    assert sw._label_font().weight() > off_weight
    # The width does not jump when switched (measured bold both ways).
    assert AfSwitch("Speak replies automatically").sizeHint() == sw.sizeHint()
    # Body size and at most weight 600 (Qt's CSS weight = QFont weight * 8).
    assert sw._label_font().weight() * 8 <= 600
    sw.deleteLater()


@pytest.mark.basic
def test_unavailable_is_focusable_ignores_clicks_and_says_why() -> None:
    _app()
    sw = AfSwitch("Email me the result")
    sw.set_hint("Sends the result by email.")
    sw.set_unavailable("Connect a mailbox first.")
    assert sw.isEnabled() and sw.focusPolicy() == Qt.StrongFocus
    sw.click()
    sw.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert sw.isChecked() is False
    assert sw.toolTip() == "Connect a mailbox first.\nSends the result by email."
    assert sw.accessibleDescription() == "Connect a mailbox first."
    sw.set_unavailable(None)
    sw.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert sw.isChecked() is True, "Enter switches (Space is QCheckBox's own)"
    sw.set_busy(True)
    sw.click()
    assert sw.isChecked() is True, "busy: the state stays as it is"
    sw.deleteLater()


@pytest.mark.basic
def test_the_inline_reason_is_the_terminal_marker_shape() -> None:
    _app()
    sw = AfSwitch("Active", reason_inline=True)
    plain = sw.sizeHint().width()
    sw.set_unavailable("Archived: history is kept, nothing runs.", short="Archived")
    assert sw._inline_reason() == " — Archived"
    assert sw.sizeHint().width() > plain
    sw.deleteLater()


# ---------------------------------------------------------------- settings


@pytest.mark.basic
def test_every_on_off_setting_in_settings_and_the_schedule_sheet_is_a_switch() -> None:
    """A plain QCheckBox may only be the route editor's "Advanced" disclosure
    (it shows fields, it is not a setting)."""
    _app()
    from abstractassistant.ui.automations import ScheduleSheet

    dlg, _ctl = _dialog()
    sheet = ScheduleSheet(target=None, target_label="Assistant", prompt="p")
    allowed = {id(dlg.page_models.route_editor.show_advanced)}
    plain = [b.text() for root in (dlg, sheet) for b in root.findChildren(QCheckBox) if not isinstance(b, AfSwitch) and id(b) not in allowed]
    assert plain == []
    switches = {b.text() for root in (dlg, sheet) for b in root.findChildren(AfSwitch)}
    assert switches >= {
        "Keep the session after this app closes",
        "Speak replies automatically",
        "Send what you say automatically",
        "Ask for short, spoken-style replies",
        "Summon the assistant from anywhere",
        "Email me the result",
    }
    verbs = re.compile(r"^(turn (on|off)|enable|disable|pause|resume)\b|\b(on|off)$", re.I)
    assert [t for t in switches if verbs.search(t)] == []
    sheet.deleteLater()
    dlg.deleteLater()


@pytest.mark.basic
def test_voice_switches_apply_at_once_and_the_page_has_no_save() -> None:
    _app()
    dlg, ctl = _dialog()
    page = dlg.page_voice
    assert page.actions() == [], "no Save-per-section: switches and choices apply as they change"
    assert ctl.preferences.auto_speak is False
    page.auto_speak.click()
    assert ctl.preferences.auto_speak is True
    assert page.feedback.text() == "Replies are spoken automatically."
    page.voice_auto_send.click()
    assert ctl.preferences.voice_auto_send is False
    assert page.feedback.text() == "What you say lands in the message box; Return sends it."
    # A choice applies on the user's pick too (activated, not a refresh).
    page.voice_mode_combo.setCurrentIndex(page.voice_mode_combo.findData("full"))
    page.voice_mode_combo.activated.emit(page.voice_mode_combo.currentIndex())
    assert ctl.preferences.voice_mode == "full"
    # A refresh never saves.
    saved = ctl.preferences
    page.refresh()
    assert ctl.preferences is saved
    dlg.deleteLater()


@pytest.mark.basic
def test_a_failed_save_flips_the_switch_back_and_says_so() -> None:
    _app()
    dlg, ctl = _dialog()

    def refuse(**_updates):
        raise OSError("read-only")

    ctl.update_preferences = refuse
    page = dlg.page_voice
    page.voice_spoken_replies.click()
    assert page.voice_spoken_replies.isChecked() is True  # back to the stored value (default on)
    assert page.feedback.text() == "Could not save the voice settings." and page.feedback.property("tone") == "error"
    dlg.deleteLater()


@pytest.mark.basic
def test_the_global_shortcut_switch_applies_at_once() -> None:
    _app()
    from abstractassistant.ui.settings import SettingsDialog
    from test_settings_pages import _Controller

    applied: list = []
    ctl = _Controller()
    dlg = SettingsDialog(controller=ctl, apply_hotkey=lambda: applied.append(ctl.preferences.hotkey_enabled), parent=None)
    page = dlg.page_window
    page.refresh()
    assert page.hotkey_enabled.isChecked() is False
    page.hotkey_enabled.click()
    assert ctl.preferences.hotkey_enabled is True and applied == [True]
    assert page.feedback.text() == "The global shortcut is on."
    dlg.deleteLater()


@pytest.mark.basic
def test_dialog_labels_stay_on_the_type_scale() -> None:
    """No label, switch or option in the Settings dialog or the Schedule sheet
    above 15 px or weight 600 (headings and pills are not labels)."""
    _app()
    from PyQt5.QtGui import QFontInfo

    from abstractassistant.ui.automations import ScheduleSheet

    dlg, _ctl = _dialog()
    sheet = ScheduleSheet(target=None, target_label="Assistant", prompt="p")
    dlg.show()
    sheet.show()
    _APP.processEvents()
    headings = {"sectionTitle", "dialogTitle", "cardTitle", "routeLabel", "autoViewTitle", "chip"}
    offenders = []
    for root in (dlg, sheet):
        for w in root.findChildren(QLabel) + root.findChildren(QCheckBox) + root.findChildren(QRadioButton):
            if w.objectName() in headings or type(w).__name__ == "Chip":
                continue
            font = w._label_font() if isinstance(w, AfSwitch) else w.font()
            px = QFontInfo(font).pixelSize()
            if px > 15 or font.weight() * 8 > 600:
                offenders.append((w.objectName(), w.text()[:30], px, font.weight() * 8))
    assert offenders == []
    sheet.close()
    dlg.close()


# ------------------------------------------------------------ source guard

_VERBS = r"(?:Turn on|Turn off|Enable|Disable|Pause|Resume)\b[^\"]*|[^\"]* (?:on|off)"
_SWAP = re.compile(rf'"({_VERBS})"\s+if\s+[^"\n]+\s+else\s+"({_VERBS})"')


def find_verb_toggle_labels(source: str) -> list:
    """The kit's ``findVerbToggleLabels`` for Python: a conditional that swaps
    two on/off verb labels (``"Pause" if paused else "Resume"``). A genuine
    one-shot action on a live thing (pausing a running run or the
    microphone) opts out on its line with ``state-toggle-lint: allow``."""
    hits = []
    for number, line in enumerate(source.splitlines(), 1):
        if "state-toggle-lint: allow" in line:
            continue
        if _SWAP.search(line):
            hits.append((number, line.strip()))
    return hits


@pytest.mark.basic
def test_the_guard_flags_a_verb_swap() -> None:
    assert find_verb_toggle_labels('label = "Resume" if paused else "Pause"')
    assert find_verb_toggle_labels('text = "Email off" if on else "Email on"')
    assert not find_verb_toggle_labels('self.say("The global shortcut is on." if checked else "The global shortcut is off.")')


@pytest.mark.basic
def test_no_source_swaps_an_on_off_verb_label() -> None:
    files = sorted(PACKAGE.rglob("*.py"))
    assert len(files) > 40
    hits = [f"{path.relative_to(PACKAGE)}:{n}: {text}" for path in files for n, text in find_verb_toggle_labels(path.read_text(encoding="utf-8"))]
    assert hits == []
