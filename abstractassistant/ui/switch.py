"""AfSwitch — the one control for a persistent on/off setting in the Assistant.

Operator rule (2026-09-30, shared with every AbstractFramework client; the web
clients use the ui-kit's ``AfSwitch``): an on/off setting is a SWITCH labelled
by the FEATURE ("Speak replies automatically", "Active", "Email me the
result"), clearly highlighted when on and plain when off. It never carries a
verb label ("Turn on", "Enable X", a Pause/Resume swap): a label naming what a
click would do reads as the current state half the time. One-shot actions
(Test, Run now, Archive) stay ordinary buttons.

ON is shown three ways, so it survives colour blindness and every theme: the
thumb slides right and carries a check mark (position + shape), the track
fills with the accent and glows (colour + light), the label turns bold
(weight).

UNAVAILABLE is not ``setEnabled(False)``: a disabled widget cannot take focus,
so keyboard users would never reach the reason. The switch stays focusable,
ignores clicks and keys, is drawn dimmed with a dashed track, and names the
reason in its tooltip and accessible description; with ``reason_inline`` the
short reason is also painted after the label ("Active — Archived"), the same
shape as the terminal marker ``[-] Feature — reason``.

It is a ``QCheckBox`` underneath, so ``isChecked`` / ``setChecked`` /
``toggled`` / ``clicked`` keep their meaning for the code that reads it.
"""

from __future__ import annotations

import re
from typing import Optional

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QCheckBox, QWidget

from ..theme import METRICS, THEME

TRACK_W = 34
TRACK_H = 20
GAP = 8
# The glow around an ON track needs a margin so it is not clipped.
GLOW = 3

_RGBA = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)")


def qcolor(value: str, alpha: Optional[float] = None) -> QColor:
    """A QColor from a theme token (``#rrggbb`` or ``rgba(r, g, b, a)``)."""
    text = str(value or "").strip()
    match = _RGBA.fullmatch(text)
    if match:
        r, g, b, a = match.groups()
        color = QColor(int(r), int(g), int(b))
        color.setAlphaF(float(a) if a is not None else 1.0)
    else:
        color = QColor(text)
    if alpha is not None:
        color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


class AfSwitch(QCheckBox):
    """A feature-labelled switch (see the module docstring)."""

    def __init__(self, label: str = "", parent: Optional[QWidget] = None, *, reason_inline: bool = False) -> None:
        super().__init__(label, parent)
        self.setObjectName("afSwitch")
        # Body size by default (a stylesheet's font-size, where one applies, wins).
        font = QFont(self.font())
        font.setPixelSize(int(METRICS.font_ui))
        self.setFont(font)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._reason = ""
        self._short_reason = ""
        self._hint = ""
        self._busy = False
        self.reason_inline = bool(reason_inline)
        # A state change repaints (and re-measures: the label turns bold).
        self.toggled.connect(lambda _checked: self._restyle())

    # ------------------------------------------------------------ state

    @property
    def unavailable_reason(self) -> str:
        return self._reason

    @property
    def busy(self) -> bool:
        return self._busy

    def is_actionable(self) -> bool:
        return not self._reason and not self._busy

    def set_hint(self, hint: str) -> None:
        """What the setting does (tooltip when available)."""
        self._hint = str(hint or "").strip()
        self._sync_tooltip()

    def set_unavailable(self, reason: Optional[str], *, short: Optional[str] = None) -> None:
        """A non-empty reason makes the switch unavailable (still focusable,
        clicks ignored, reason in the tooltip and the accessible description;
        ``short`` is what ``reason_inline`` paints after the label)."""
        self._reason = str(reason or "").strip()
        self._short_reason = str(short or "").strip() or self._reason
        self.setCursor(Qt.ForbiddenCursor if self._reason else Qt.PointingHandCursor)
        self._sync_tooltip()
        self._restyle()

    def set_busy(self, busy: bool) -> None:
        """A save is in flight: the state stays as it is and clicks are ignored."""
        self._busy = bool(busy)
        self.setCursor(Qt.BusyCursor if self._busy else (Qt.ForbiddenCursor if self._reason else Qt.PointingHandCursor))
        self._restyle()

    def _sync_tooltip(self) -> None:
        if self._reason:
            self.setToolTip(f"{self._reason}\n{self._hint}" if self._hint else self._reason)
            self.setAccessibleDescription(self._reason)
        else:
            self.setToolTip(self._hint)
            self.setAccessibleDescription(self._hint)

    def _restyle(self) -> None:
        self.updateGeometry()
        self.update()

    # ------------------------------------------------------ interaction

    def nextCheckState(self) -> None:  # noqa: N802 (Qt API)
        # The one place a click or Space changes the state: ignored while
        # unavailable or busy (Qt then emits neither toggled nor a change).
        if self.is_actionable():
            super().nextCheckState()

    def checkStateSet(self) -> None:  # noqa: N802 (Qt API)
        super().checkStateSet()
        self.update()

    def hitButton(self, pos) -> bool:  # noqa: N802 (Qt API)
        # The whole switch (track and label) is the target, as on the web.
        return self.rect().contains(pos)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        # Enter switches too (Space is QCheckBox's own).
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.is_actionable():
                self.click()
            event.accept()
            return
        super().keyPressEvent(event)

    # ----------------------------------------------------------- layout

    def _label_font(self) -> QFont:
        font = QFont(self.font())
        # Bold when on (weight 600 = DemiBold), body weight otherwise.
        font.setWeight(QFont.DemiBold if self.isChecked() else QFont.Medium)
        return font

    def _inline_reason(self) -> str:
        return f" — {self._short_reason}" if (self.reason_inline and self._reason) else ""

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        label_w = QFontMetrics(self._label_font()).horizontalAdvance(self.text())
        # Measure bold always, so the switch does not change width when switched.
        bold = QFont(self.font())
        bold.setWeight(QFont.DemiBold)
        label_w = max(label_w, QFontMetrics(bold).horizontalAdvance(self.text()))
        reason_w = QFontMetrics(self.font()).horizontalAdvance(self._inline_reason())
        text_w = label_w + reason_w
        width = GLOW + TRACK_W + (GAP + text_w if text_w else 0) + GLOW
        height = max(TRACK_H + 2 * GLOW, QFontMetrics(bold).height() + 4)
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        return QSize(GLOW * 2 + TRACK_W, TRACK_H + 2 * GLOW)

    # ------------------------------------------------------------ paint

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        on = self.isChecked()
        unavailable = bool(self._reason)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        top = (self.height() - TRACK_H) / 2.0
        track = QRectF(GLOW, top, TRACK_W, TRACK_H)
        radius = TRACK_H / 2.0
        accent = qcolor(THEME.accent)
        dim = 0.45 if unavailable else 1.0

        if on and not unavailable:
            # The glow: a soft accent halo around the filled track.
            glow = QColor(accent)
            glow.setAlphaF(0.28)
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawRoundedRect(track.adjusted(-GLOW, -GLOW, GLOW, GLOW), radius + GLOW, radius + GLOW)

        if on:
            fill = QColor(accent)
            fill.setAlphaF(fill.alphaF() * dim)
            painter.setBrush(fill)
            painter.setPen(QPen(fill, 1))
        else:
            painter.setBrush(qcolor(THEME.overlay_faint))
            pen = QPen(qcolor(THEME.border_strong), 1.2)
            if unavailable:
                pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
        painter.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # The thumb: right + check mark when on, left and plain when off.
        d = TRACK_H - 6
        x = track.right() - 3 - d if on else track.left() + 3
        thumb = QRectF(x, top + 3, d, d)
        if on:
            thumb_color = qcolor(THEME.primary_text)
        else:
            thumb_color = qcolor(THEME.text_secondary)
        thumb_color.setAlphaF(thumb_color.alphaF() * (0.55 if unavailable else 1.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(thumb_color)
        painter.drawEllipse(thumb)
        if on:
            mark = QPainterPath()
            c = thumb.center()
            mark.moveTo(QPointF(c.x() - d * 0.24, c.y() + 0.2))
            mark.lineTo(QPointF(c.x() - d * 0.06, c.y() + d * 0.18))
            mark.lineTo(QPointF(c.x() + d * 0.26, c.y() - d * 0.18))
            check = QColor(accent)
            check.setAlphaF(check.alphaF() * dim)
            painter.setPen(QPen(check, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(mark)
        if self._busy:
            painter.setPen(QPen(qcolor(THEME.text_faint), 1.2, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(thumb.adjusted(-1.5, -1.5, 1.5, 1.5))

        if self.hasFocus():
            ring = QColor(accent)
            ring.setAlphaF(0.85)
            painter.setPen(QPen(ring, 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(track.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)

        # The label: the feature name; bold when on, muted when unavailable.
        text = self.text()
        left = int(track.right() + GAP)
        if text:
            font = self._label_font()
            painter.setFont(font)
            painter.setPen(qcolor(THEME.text_faint if unavailable else THEME.text_primary))
            metrics = QFontMetrics(font)
            reason = self._inline_reason()
            reason_w = QFontMetrics(self.font()).horizontalAdvance(reason)
            room = max(0, self.width() - left - GLOW - reason_w)
            shown = metrics.elidedText(text, Qt.ElideRight, room)
            rect = QRectF(left, 0, room, self.height())
            painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, shown)
            if reason:
                painter.setFont(self.font())
                painter.setPen(qcolor(THEME.text_faint))
                x = left + metrics.horizontalAdvance(shown)
                room = max(0, self.width() - x - GLOW)
                painter.drawText(
                    QRectF(x, 0, room, self.height()),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    QFontMetrics(self.font()).elidedText(reason, Qt.ElideRight, room),
                )
        painter.end()
