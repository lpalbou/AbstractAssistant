"""The ONE rich tooltip of the message footer's stat chips (Qt).

Renders a `core.stat_detail.StatDetail` as a titled card — the desktop
mirror of AbstractUIC panel-chat ``StatDetailPanel`` / ``StatChip``: it opens
on hover (after a short delay) or keyboard focus, closes on mouse-out, blur,
click or Escape, sits above the chip (below when there is no room), clamped to
the screen. Every chip uses it (`attach_stat_detail`); a chip carries no plain
``toolTip`` of its own any more. Colours are THEME tokens only.
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..core.stat_detail import NOT_REPORTED, StatDetail, stat_detail_text
from ..theme import METRICS, THEME
from .styles import alpha

_GAP = 8
_OPEN_DELAY_MS = 250
_CLOSE_DELAY_MS = 150


def stat_detail_qss() -> str:
    return f"""
    QFrame#statDetail {{
        background: {THEME.surface_raised};
        border: 1px solid {THEME.border_strong};
        border-radius: 10px;
    }}
    QLabel#statDetailTitle {{ color: {THEME.text_strong}; font-size: {METRICS.font_ui}px; font-weight: 700; }}
    QLabel#statDetailHeadline {{ color: {THEME.text_secondary}; font-size: {METRICS.font_ui}px; font-weight: 600; }}
    QLabel#statDetailHeading {{
        color: {THEME.text_muted}; font-size: {max(9, METRICS.font_caption - 1)}px; font-weight: 700;
        letter-spacing: 0.06em; padding-top: 4px;
    }}
    QLabel#statDetailLabel {{ color: {THEME.text_muted}; font-size: {METRICS.font_caption}px; }}
    QLabel#statDetailValue {{ color: {THEME.text_primary}; font-size: {METRICS.font_caption}px; font-weight: 600; }}
    QLabel#statDetailValue[absent="true"] {{ color: {THEME.text_faint}; font-style: italic; font-weight: 400; }}
    QLabel#statDetailHint {{ color: {THEME.text_faint}; font-size: {METRICS.font_caption}px; }}
    QLabel#statDetailNote {{ color: {THEME.text_faint}; font-size: {METRICS.font_caption}px; }}
    QFrame#statDetailRule {{ background: {alpha(THEME.text_faint, 0.25)}; border: none; }}
    QLabel#statDetailFoot {{ color: {THEME.text_faint}; font-size: {METRICS.font_caption}px; }}
    """


def _label(text: str, name: str, parent: QWidget, *, wrap: bool = False) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName(name)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(wrap)
    return label


class StatDetailCard(QFrame):
    """The card itself (also used on its own, e.g. for a screenshot)."""

    MAX_WIDTH = 340

    def __init__(self, detail: StatDetail, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.detail = detail
        self.setObjectName("statDetail")
        self.setProperty("kind", detail.kind)
        self.setStyleSheet(stat_detail_qss())
        self.setMaximumWidth(self.MAX_WIDTH)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.title_label = _label(detail.title, "statDetailTitle", self)
        self.headline_label = _label(detail.headline, "statDetailHeadline", self)
        head.addWidget(self.title_label, 0)
        head.addStretch(1)
        head.addWidget(self.headline_label, 0)
        root.addLayout(head)
        self.headings = []
        for section in detail.sections:
            heading = _label(section.heading.upper(), "statDetailHeading", self)
            self.headings.append(heading)
            root.addWidget(heading)
            if section.rows:
                grid = QGridLayout()
                grid.setContentsMargins(0, 0, 0, 0)
                grid.setHorizontalSpacing(12)
                grid.setVerticalSpacing(2)
                for r, row in enumerate(section.rows):
                    grid.addWidget(_label(row.label, "statDetailLabel", self), r, 0, Qt.AlignLeft | Qt.AlignTop)
                    value = _label(row.value, "statDetailValue", self, wrap=True)
                    value.setProperty("absent", "true" if row.value == NOT_REPORTED else "false")
                    cell = QHBoxLayout()
                    cell.setSpacing(6)
                    cell.addWidget(value, 1)
                    if row.hint:
                        cell.addWidget(_label(row.hint, "statDetailHint", self), 0)
                    grid.addLayout(cell, r, 1)
                grid.setColumnStretch(1, 1)
                root.addLayout(grid)
            if section.note:
                root.addWidget(_label(section.note, "statDetailNote", self, wrap=True))
        if detail.footer:
            rule = QFrame(self)
            rule.setObjectName("statDetailRule")
            rule.setFixedHeight(1)
            root.addSpacing(4)
            root.addWidget(rule)
            for line in detail.footer:
                root.addWidget(_label(line, "statDetailFoot", self, wrap=True))
        self.setAccessibleName(f"{detail.title} details")
        self.setAccessibleDescription(stat_detail_text(detail))


class StatDetailPopup(QFrame):
    """A frameless tooltip window holding one `StatDetailCard` at a time."""

    def __init__(self) -> None:
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setObjectName("statDetailPopup")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.card: Optional[StatDetailCard] = None
        self.anchor: Optional[QWidget] = None

    def show_for(self, chip: QWidget, detail: StatDetail) -> None:
        if self.card is not None:
            self.layout().removeWidget(self.card)
            self.card.deleteLater()
        self.card = StatDetailCard(detail, self)
        self.layout().addWidget(self.card)
        self.anchor = chip
        self.adjustSize()
        self.move(self._position(chip))
        self.show()
        self.raise_()

    def _position(self, chip: QWidget) -> QPoint:
        size = self.sizeHint()
        top_left = chip.mapToGlobal(QPoint(0, 0))
        screen = QApplication.screenAt(top_left) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else QRect(0, 0, 1600, 1200)
        above = top_left.y() - _GAP - size.height()
        below = top_left.y() + chip.height() + _GAP
        if above >= area.top() + _GAP:
            y = above
        elif below + size.height() <= area.bottom() - _GAP:
            y = below
        else:
            y = max(area.top() + _GAP, area.bottom() - _GAP - size.height())
        x = min(max(area.left() + _GAP, top_left.x()), max(area.left() + _GAP, area.right() - _GAP - size.width()))
        return QPoint(int(x), int(y))

    def dismiss(self) -> None:
        self.hide()
        self.anchor = None


_POPUP: Optional[StatDetailPopup] = None


def stat_detail_popup() -> StatDetailPopup:
    global _POPUP
    try:
        if _POPUP is not None:
            _POPUP.isVisible()  # raises once the C++ object is gone
            return _POPUP
    except RuntimeError:
        pass
    _POPUP = StatDetailPopup()
    return _POPUP


class _ChipHover(QObject):
    """Hover / focus / Escape behaviour for every detail chip (one instance)."""

    def __init__(self) -> None:
        super().__init__()
        self._open = QTimer(self)
        self._open.setSingleShot(True)
        self._open.timeout.connect(self._show_pending)
        self._close = QTimer(self)
        self._close.setSingleShot(True)
        self._close.timeout.connect(self._close_if_away)
        self._pending: Optional[QWidget] = None

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        kind = event.type()
        if kind == QEvent.Enter:
            self._close.stop()
            self._pending = obj
            self._open.start(_OPEN_DELAY_MS)
        elif kind == QEvent.Leave:
            self._open.stop()
            self._close.start(_CLOSE_DELAY_MS)
        elif kind == QEvent.FocusIn:
            show_stat_detail(obj)
        elif kind in (QEvent.FocusOut, QEvent.MouseButtonPress, QEvent.Hide):
            self._open.stop()
            _dismiss_for(obj)
        elif kind == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            _dismiss_for(obj)
        elif kind == QEvent.ToolTip:
            return True  # the card is the tooltip
        return False

    def _show_pending(self) -> None:
        chip = self._pending
        self._pending = None
        if chip is None:
            return
        try:
            if chip.underMouse():
                show_stat_detail(chip)
        except RuntimeError:
            return

    def _close_if_away(self) -> None:
        popup = stat_detail_popup()
        if not popup.isVisible():
            return
        if popup.geometry().contains(QCursor.pos()):
            self._close.start(_CLOSE_DELAY_MS)
            return
        anchor = popup.anchor
        try:
            if anchor is not None and anchor.underMouse():
                return
        except RuntimeError:
            pass
        popup.dismiss()


_HOVER: Optional[_ChipHover] = None


def _hover() -> _ChipHover:
    global _HOVER
    if _HOVER is None:
        _HOVER = _ChipHover()
    return _HOVER


def _dismiss_for(chip: QWidget) -> None:
    popup = stat_detail_popup()
    if popup.anchor is chip:
        popup.dismiss()


def attach_stat_detail(chip: QWidget, detail: StatDetail) -> None:
    """Give ``chip`` the structured detail card (hover / focus / Escape)."""
    chip.stat_detail = detail
    chip.setToolTip("")
    chip.setAccessibleDescription(stat_detail_text(detail))
    chip.setAttribute(Qt.WA_Hover, True)
    if chip.focusPolicy() == Qt.NoFocus:
        # Reachable from the keyboard like the kit's chip (tabIndex 0): focus
        # opens the card, Escape or leaving closes it.
        chip.setFocusPolicy(Qt.TabFocus)
    chip.installEventFilter(_hover())


def show_stat_detail(chip: QWidget) -> Optional[StatDetailPopup]:
    detail = getattr(chip, "stat_detail", None)
    if not isinstance(detail, StatDetail):
        return None
    popup = stat_detail_popup()
    popup.show_for(chip, detail)
    return popup


__all__ = ["StatDetailCard", "StatDetailPopup", "attach_stat_detail", "show_stat_detail", "stat_detail_popup", "stat_detail_qss"]
