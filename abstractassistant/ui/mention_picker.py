"""The `@` list of the desktop composer (the kit's `pc-mention-popover`, panel-chat 0.9.13).

Typing `@` at the start of the text or after a space opens a list of the names the person may
mention: the conversation's agent (`@agent`) and the entities `GET /entities` returned for this
account, read from a roster the palette cached (no gateway call per keystroke). The list follows
what is typed after the `@` (a name or id that STARTS with it, any case); a name already in the
message is not offered again. Up/Down move, Enter or Tab pick, Escape closes the list for this
`@` (a new `@` opens it again), a click picks. The list floats above the composer, inside the
palette window (a separate window would take the focus and hide the palette).

Qt-free rules (``mention_trigger_at``, ``move_active``) mirror the kit's `mentionTriggerAt` and
`moveMentionActive`; the filter is ``core.mentions.EntityRoster.match`` (the web's
`matchCandidates`).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PyQt5.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..theme import METRICS, THEME
from .mention_chip import mention_key, mention_look, mention_mark_pixmap

#: The longest query the list follows; past it the `@` is just text (the kit's MENTION_QUERY_MAX).
MENTION_QUERY_MAX = 48
_SPACES = {" ", "\n", "\t", "\r", "\u00a0", "\u2028", "\u2029"}

#: The list's sentences when it has no name to show (the kit's own words).
LOADING = "Looking for names…"
LOAD_FAILED = "The names could not be loaded."
ALREADY = "Already mentioned."
NOBODY = "No one to mention here."


def no_match(query: str) -> str:
    return f"No name matches “{query}”."


def mention_trigger_at(before_caret: str) -> Optional[Tuple[int, str]]:
    """The `@` being typed at the caret: (its index in ``before_caret``, what follows it), or
    None. It opens the list when it starts the text or follows a space, and only non-space
    characters sit between it and the caret ("me@host" and "@ " do not open it)."""
    value = str(before_caret or "")
    end = len(value)
    i = end - 1
    while i >= 0 and end - i - 1 <= MENTION_QUERY_MAX:
        ch = value[i]
        if ch in _SPACES:
            return None
        if ch == "@":
            if i > 0 and value[i - 1] not in _SPACES:
                return None
            return i, value[i + 1:end]
        i -= 1
    return None


def move_active(active: int, count: int, delta: int) -> int:
    if count <= 0:
        return -1
    if active < 0:
        return count - 1 if delta < 0 else 0
    return ((active + delta) % count + count) % count


def picker_qss() -> str:
    t = THEME
    return f"""
    QFrame#mentionPicker {{
        background: {t.surface_raised};
        border: 1px solid {t.border_strong};
        border-radius: 10px;
    }}
    QScrollArea#mentionPickerScroll, QWidget#mentionPickerRows {{ background: transparent; border: none; }}
    QFrame#mentionOption {{ background: transparent; border: none; border-radius: 6px; }}
    QFrame#mentionOption[active="true"] {{
        background: {t.overlay_hover};
        border-left: 3px solid {t.accent};
    }}
    QLabel#mentionOptionName {{ color: {t.text_primary}; font-size: {METRICS.font_body}px; font-weight: 600; background: transparent; }}
    QLabel#mentionOptionHint {{ color: {t.text_muted}; font-size: {METRICS.font_caption}px; background: transparent; }}
    QLabel#mentionOptionKind {{ color: {t.text_muted}; font-size: {max(9, METRICS.font_caption - 1)}px; background: transparent; }}
    QLabel#mentionPickerEmpty {{ color: {t.text_secondary}; font-size: {METRICS.font_ui}px; padding: 8px 10px; background: transparent; }}
    """


class _Option(QFrame):
    """One name in the list: its mark, its name (and hint), its kind. Not a button: the whole
    row is the choice, as in the kit."""

    hovered = pyqtSignal(int)
    chosen = pyqtSignal(int)

    def __init__(self, index: int, candidate: Mapping[str, Any], parent: QWidget) -> None:
        super().__init__(parent)
        self.index = index
        self.candidate = dict(candidate)
        self.setObjectName("mentionOption")
        self.setProperty("active", "false")
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)
        self.setAccessibleName(f"{candidate['name']}, {candidate['kind']}")
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(10)
        mark = QLabel(self)
        mark.setObjectName("mentionOptionMark")
        mark.setFixedSize(22, 22)
        mark.setPixmap(mention_mark_pixmap(candidate["kind"], candidate["name"], mention_look(candidate), 22, self.devicePixelRatioF()))
        row.addWidget(mark, 0, Qt.AlignVCenter)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(0)
        self.name_label = QLabel(candidate["name"], self)
        self.name_label.setObjectName("mentionOptionName")
        self.name_label.setTextFormat(Qt.PlainText)
        text.addWidget(self.name_label)
        if candidate.get("hint"):
            hint = QLabel(str(candidate["hint"]), self)
            hint.setObjectName("mentionOptionHint")
            hint.setTextFormat(Qt.PlainText)
            text.addWidget(hint)
        row.addLayout(text, 1)
        kind = QLabel(candidate["kind"], self)
        kind.setObjectName("mentionOptionKind")
        row.addWidget(kind, 0, Qt.AlignVCenter)

    def set_active(self, active: bool) -> None:
        value = "true" if active else "false"
        if self.property("active") == value:
            return
        self.setProperty("active", value)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.hovered.emit(self.index)
        super().enterEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton:
            self.chosen.emit(self.index)
            event.accept()
            return
        super().mousePressEvent(event)


class MentionPicker(QFrame):
    """The list itself: a child of the palette window, floated above the composer by the
    composer (``place_above``). Never takes the focus: the caret stays in the message."""

    picked = pyqtSignal(dict)

    MAX_WIDTH = 352  # 22rem
    MAX_HEIGHT = 280

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("mentionPicker")
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAccessibleName("Mention someone")
        self._items: List[Dict[str, Any]] = []
        self._options: List[_Option] = []
        self._active = -1
        self.status = "ready"
        self.message = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("mentionPickerScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFocusPolicy(Qt.NoFocus)
        self._rows = QWidget(self._scroll)
        self._rows.setObjectName("mentionPickerRows")
        self._rows_layout = QVBoxLayout(self._rows)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._scroll.setWidget(self._rows)
        root.addWidget(self._scroll)
        self.empty_label = QLabel(self)
        self.empty_label.setObjectName("mentionPickerEmpty")
        self.empty_label.setWordWrap(True)
        self.empty_label.setTextFormat(Qt.PlainText)
        root.addWidget(self.empty_label)
        self.hide()

    # -- state -------------------------------------------------------------------------------

    @property
    def items(self) -> List[Dict[str, Any]]:
        return list(self._items)

    @property
    def active_index(self) -> int:
        return self._active

    def active_candidate(self) -> Optional[Dict[str, Any]]:
        return dict(self._items[self._active]) if 0 <= self._active < len(self._items) else None

    def set_names(self, items: Sequence[Mapping[str, Any]], *, message: str = "", status: str = "ready") -> None:
        """Show ``items`` (or, with none, ``message``: why the list is empty)."""
        keys = [mention_key(i) for i in items]
        same = keys == [mention_key(i) for i in self._items]
        self.status = status
        self.message = message
        self.setStyleSheet(picker_qss())
        if not same:
            for option in self._options:
                option.hide()
                option.setParent(None)
                option.deleteLater()
            self._options = []
            self._items = [dict(i) for i in items]
            for index, candidate in enumerate(self._items):
                option = _Option(index, candidate, self._rows)
                option.hovered.connect(self.set_active)
                option.chosen.connect(self._choose)
                self._rows_layout.addWidget(option)
                self._options.append(option)
            self._active = 0 if self._items else -1
        elif self._active >= len(self._items):
            self._active = len(self._items) - 1
        self._scroll.setVisible(bool(self._items))
        self.empty_label.setVisible(not self._items)
        self.empty_label.setText("" if self._items else message)
        self._paint_active()

    def set_active(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self._active = index
            self._paint_active()

    def move(self, delta: int) -> None:  # noqa: A003 - list movement, not QWidget.move
        self.set_active(move_active(self._active, len(self._items), delta))

    def _paint_active(self) -> None:
        for option in self._options:
            option.set_active(option.index == self._active)
        if 0 <= self._active < len(self._options):
            self._scroll.ensureWidgetVisible(self._options[self._active], 0, 0)

    def _choose(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self.picked.emit(dict(self._items[index]))

    # -- placement ---------------------------------------------------------------------------

    def place_above(self, anchor: QRect) -> None:
        """Float the list above ``anchor`` (the composer's text box, in the parent's
        coordinates), left edges aligned, 6 px gap, kept 8 px inside the window."""
        parent = self.parentWidget()
        if parent is None:
            return
        width = max(160, min(self.MAX_WIDTH, anchor.width(), parent.width() - 16))
        # Measured once the rows carry their style (an unpolished row reports a smaller height).
        self.ensurePolished()
        for option in self._options:
            option.ensurePolished()
            for child in option.findChildren(QWidget):
                child.ensurePolished()
        self._rows_layout.activate()
        rows_height = self._rows.sizeHint().height() + 2 * self._scroll.frameWidth() + 2 * self.frameWidth()
        content = rows_height if self._items else self.empty_label.heightForWidth(width - 8) or self.empty_label.sizeHint().height()
        room = max(48, anchor.top() - 6 - 8)
        height = min(self.MAX_HEIGHT, int(parent.height() * 0.4) if parent.height() > 300 else self.MAX_HEIGHT, content + 8, room)
        left = max(8, min(anchor.left(), parent.width() - 8 - width))
        top = max(8, anchor.top() - 6 - height)
        self.setGeometry(QRect(QPoint(left, top), QSize(width, max(40, height))))
        self.raise_()
