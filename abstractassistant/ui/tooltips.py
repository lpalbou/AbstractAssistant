"""One minimum dwell time for standard Qt and application-owned tooltips."""
from __future__ import annotations

from PyQt5.QtCore import QEvent, QObject, Qt, QTimer
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication, QProxyStyle, QStyle, QToolTip

MIN_TOOLTIP_DELAY_MS = 200


class TooltipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802
        if hint == QStyle.SH_ToolTip_WakeUpDelay:
            # Qt owns this timer; allow margin for its coarse-timer scheduling.
            return 250
        if hint == QStyle.SH_ToolTip_FallAsleepDelay:
            # Never use the instant-tooltip shortcut when moving between items.
            return 0
        return super().styleHint(hint, option, widget, returnData)


def install_tooltip_timing(app: QApplication) -> None:
    if getattr(app, "_assistant_tooltip_style", None) is None:
        style = TooltipStyle(app.style())
        app._assistant_tooltip_style = style
        app.setStyle(style)


class _DelayedTooltip(QObject):
    def __init__(self, widget):
        super().__init__(widget)
        self.widget = widget
        self.key = None
        self.text = ""
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.show_pending)
        widget.installEventFilter(self)

    def request(self, text, key=None):
        identity = text if key is None else key
        if identity == self.key:
            return
        self.cancel()
        self.key, self.text = identity, text
        self.timer.start(MIN_TOOLTIP_DELAY_MS)

    def cancel(self):
        self.timer.stop()
        self.key, self.text = None, ""
        QToolTip.hideText()

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() in (QEvent.Leave, QEvent.Hide, QEvent.MouseButtonPress) or (
            event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape
        ):
            self.cancel()
        return False

    def show_pending(self):
        if self.text and self.widget.isVisible() and self.widget.rect().contains(self.widget.mapFromGlobal(QCursor.pos())):
            QToolTip.showText(QCursor.pos(), self.text, self.widget)


def delayed_tooltip(widget, text: str, *, key=None) -> None:
    tooltip = getattr(widget, "_assistant_delayed_tooltip", None)
    if tooltip is None:
        tooltip = widget._assistant_delayed_tooltip = _DelayedTooltip(widget)
    if text:
        tooltip.request(text, key)
    else:
        tooltip.cancel()
