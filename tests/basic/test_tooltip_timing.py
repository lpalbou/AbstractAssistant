"""Every tooltip path waits, including warm transitions and custom link help."""
import time

import pytest
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QCursor, QKeyEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QLabel, QStyle, QToolTip

from test_palette_smoke import _app
from abstractassistant.ui.tooltips import delayed_tooltip, install_tooltip_timing


@pytest.fixture
def target(monkeypatch):
    app = _app()
    install_tooltip_timing(app)
    widget = QLabel("Tooltip target")
    widget.resize(240, 100)
    widget.show()
    app.processEvents()
    QCursor.setPos(widget.mapToGlobal(QPoint(50, 50)))
    shown = []
    monkeypatch.setattr(QToolTip, "showText", lambda *args: shown.append((time.monotonic(), args[1])))
    yield widget, shown
    widget.close()
    widget.deleteLater()
    app.processEvents()


@pytest.mark.basic
def test_standard_tooltips_never_use_warm_instant_display(target):
    widget, _ = target
    assert widget.style().styleHint(QStyle.SH_ToolTip_WakeUpDelay) >= 200
    assert widget.style().styleHint(QStyle.SH_ToolTip_FallAsleepDelay) == 0


@pytest.mark.basic
def test_links_within_one_widget_each_require_full_dwell(target):
    widget, shown = target
    delayed_tooltip(widget, "First", key="link-a")
    QTest.qWait(120)
    assert not shown
    started = time.monotonic()
    delayed_tooltip(widget, "Second", key="link-b")
    QTest.qWait(120)
    assert not shown
    QTest.qWait(120)
    assert len(shown) == 1 and shown[0][1] == "Second"
    assert shown[0][0] - started >= 0.2


@pytest.mark.basic
@pytest.mark.parametrize("kind", [QEvent.Leave, QEvent.Hide, QEvent.KeyPress])
def test_leaving_hiding_or_escape_cancels_pending_tooltip(target, kind):
    widget, shown = target
    delayed_tooltip(widget, "Never show")
    QTest.qWait(80)
    event = QKeyEvent(kind, Qt.Key_Escape, Qt.NoModifier) if kind == QEvent.KeyPress else QEvent(kind)
    QApplication.sendEvent(widget, event)
    QTest.qWait(200)
    assert not shown


@pytest.mark.basic
def test_stat_detail_focus_also_waits(target, monkeypatch):
    from abstractassistant.ui import stat_detail
    widget, _ = target
    shown = []
    monkeypatch.setattr(stat_detail, "show_stat_detail", lambda chip: shown.append(time.monotonic()))
    monkeypatch.setattr(widget, "hasFocus", lambda: True)
    hover = stat_detail._ChipHover()
    started = time.monotonic()
    hover.eventFilter(widget, QEvent(QEvent.FocusIn))
    QTest.qWait(120)
    assert not shown
    QTest.qWait(180)
    assert len(shown) == 1 and shown[0] - started >= 0.2


@pytest.mark.basic
def test_escape_during_stat_detail_delay_never_reopens_card(target, monkeypatch):
    from abstractassistant.ui import stat_detail
    widget, _ = target
    shown = []
    monkeypatch.setattr(stat_detail, "show_stat_detail", lambda chip: shown.append(chip))
    monkeypatch.setattr(widget, "hasFocus", lambda: True)
    hover = stat_detail._ChipHover()
    hover.eventFilter(widget, QEvent(QEvent.FocusIn))
    QTest.qWait(80)
    hover.eventFilter(widget, QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    QTest.qWait(250)
    assert not shown
