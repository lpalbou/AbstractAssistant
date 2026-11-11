"""Who answers, in the transcript (operator rulings 2026-11-08 and round 6, 2026-11-11).

- ``AuthorBadge``: the head of an answer an entity wrote — its orb and its name, where today's
  "✦ Assistant" sits (``core.mentions.bubble_author``; an agent's answer keeps today's header).
- ``PendingMentionCard``: an entity's answer on its way — a bubble at the answer's place with the
  entity's orb and name and three animated dots (the kit's `pc-working-dots`), one per mentioned
  entity, replaced by the answer when it lands and removed at once when the entity refused. It is
  an indicator, never a control: nothing in it can be clicked.
"""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional

from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..theme import THEME
from .mention_chip import mention_look, mention_mark_pixmap, qcolor

_CYCLE_S = 0.74
_DELAYS_S = (0.0, 0.11, 0.22)
_LIFT_PX = 4.5


def dot_phase(elapsed_s: float, delay_s: float) -> tuple:
    """(lift in px, lit) of one dot ``elapsed_s`` into the animation (the kit's keyframes: up and
    back down in the first half of the cycle, lit; resting and dim in the second half)."""
    t = ((elapsed_s - delay_s) / _CYCLE_S) % 1.0
    if t < 0.25:
        return _LIFT_PX * (t / 0.25), True
    if t < 0.5:
        return _LIFT_PX * (1.0 - (t - 0.25) / 0.25), True
    return 0.0, False


class WorkingDots(QWidget):
    """Three dots that hop in turn while an answer is on its way. Clocked only while shown."""

    FRAME_MS = 33

    def __init__(self, label: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("mentionWorkingDots")
        self.setFixedSize(40, 18)
        self.setAccessibleName(label)
        self.setToolTip("")
        self._started = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self.update)

    @property
    def animating(self) -> bool:
        return self._timer.isActive()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        elapsed = time.monotonic() - self._started
        size, gap = 6.0, 3.0
        left = (self.width() - (3 * size + 2 * gap)) / 2
        base = (self.height() + size) / 2 + 1.5
        for i, delay in enumerate(_DELAYS_S):
            lift, lit = dot_phase(elapsed, delay)
            painter.setBrush(qcolor(THEME.accent, 0.92) if lit else qcolor(THEME.text_muted, 0.55))
            painter.drawEllipse(QRectF(left + i * (size + gap), base - size - lift, size, size))
        painter.end()


class AuthorBadge(QWidget):
    """An author's orb and name in a bubble's header (an indicator, not a button)."""

    MARK = 16

    def __init__(self, author: Mapping[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("messageAuthor")
        kind = str(author.get("kind") or "entity")
        name = str(author.get("name") or "") or {"entity": "Entity", "person": "Someone"}.get(kind, "Agent")
        self.author_name = name
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.mark = QLabel(self)
        self.mark.setObjectName("messageAuthorMark")
        self.mark.setFixedSize(self.MARK, self.MARK)
        mark_kind = "agent" if kind == "agent" else "entity"
        self.mark.setPixmap(mention_mark_pixmap(mark_kind, name, mention_look(author), self.MARK, self.devicePixelRatioF()))
        row.addWidget(self.mark, 0, Qt.AlignVCenter)
        self.name_label = QLabel(name, self)
        self.name_label.setObjectName("messageRole")
        self.name_label.setTextFormat(Qt.PlainText)
        row.addWidget(self.name_label, 0, Qt.AlignVCenter)
        self.setAccessibleName(name)


class PendingMentionCard(QFrame):
    """An entity's answer on its way: its orb and name, and the dots, in an answer's bubble."""

    def __init__(self, *, key: str, author: Mapping[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.key = str(key)
        self.setObjectName("messageContainer")
        self.setProperty("pendingMention", "true")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        root.addLayout(row)
        bubble = QFrame(self)
        bubble.setObjectName("assistantBubble")
        bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
        self.bubble = bubble
        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(12, 10, 14, 10)
        inner.setSpacing(6)
        self.badge = AuthorBadge(author, bubble)
        inner.addWidget(self.badge)
        self.dots = WorkingDots(f"{self.badge.author_name} is answering", bubble)
        inner.addWidget(self.dots, 0, Qt.AlignLeft)
        row.addWidget(bubble)
        row.addStretch(1)
        self.setAccessibleName(f"{self.badge.author_name} is answering")

    @property
    def author_name(self) -> str:
        return self.badge.author_name

    def sync_to_viewport_width(self, viewport_width: int) -> None:
        """The bubble hugs its head and dots (no width to follow)."""
        del viewport_width
