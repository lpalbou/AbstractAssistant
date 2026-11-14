"""The card on a mention chip (the kit's `renderMentionCard`, panel-chat 0.9.13; AbstractAssistant
web ui/MentionCard.tsx): resting the pointer ~150 ms on "@Castor" — in the composer or in a sent
message — or reaching a sent message's chip with the keyboard (Tab: the chip is an anchor) shows a small card with the entity's orb, its name and one sentence of its state, read
from the roster the `@` list loaded. The agent's chip, or a name the roster does not hold, has no
card. It goes when the pointer leaves the chip, on a click, a scroll, a key, or when the widget
hides. The card floats inside the palette window, below the chip (above when there is no room).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QSize, Qt, QTimer
from PyQt5.QtWidgets import QAbstractScrollArea, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..theme import METRICS, THEME
from .mention_chip import chip_at, chip_rect, chip_under, mention_look, mention_mark_pixmap

#: How long the pointer rests on a chip before its card shows (the kit's MENTION_CARD_REST_MS).
MENTION_CARD_REST_MS = 150
_GAP = 6
_MARGIN = 8

CardFor = Callable[[Mapping[str, Any]], Optional[Mapping[str, Any]]]


def card_qss() -> str:
    t = THEME
    return f"""
    QFrame#mentionCard {{
        background: {t.surface_raised};
        border: 1px solid {t.border_strong};
        border-radius: 10px;
    }}
    QLabel#mentionCardName {{ color: {t.text_strong}; font-size: {METRICS.font_body}px; font-weight: 700; background: transparent; }}
    QLabel#mentionCardState {{ color: {t.text_secondary}; font-size: {METRICS.font_ui}px; background: transparent; }}
    """


class MentionCard(QFrame):
    """The card itself: orb, name, state sentence. One per window (``for_window``)."""

    MAX_WIDTH = 320  # 20rem

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("mentionCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        self.mark = QLabel(self)
        self.mark.setFixedSize(28, 28)
        row.addWidget(self.mark, 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.name_label = QLabel(self)
        self.name_label.setObjectName("mentionCardName")
        self.name_label.setTextFormat(Qt.PlainText)
        text.addWidget(self.name_label)
        self.state_label = QLabel(self)
        self.state_label.setObjectName("mentionCardState")
        self.state_label.setTextFormat(Qt.PlainText)
        self.state_label.setWordWrap(True)
        text.addWidget(self.state_label)
        row.addLayout(text, 1)
        self.shown_for = ""
        self.hide()

    @classmethod
    def for_window(cls, window: QWidget) -> "MentionCard":
        card = window.findChild(MentionCard, "mentionCard", Qt.FindDirectChildrenOnly)
        return card if card is not None else cls(window)

    def show_card(self, card: Mapping[str, Any], anchor: QRect, key: str = "") -> None:
        """Show ``card`` ({name, avatar, sentence}) for a chip at ``anchor`` (parent coords)."""
        parent = self.parentWidget()
        self.setStyleSheet(card_qss())
        name = str(card.get("name") or "")
        self.mark.setPixmap(mention_mark_pixmap("entity", name, mention_look(card), 28, self.devicePixelRatioF()))
        self.name_label.setText(name)
        sentence = str(card.get("sentence") or "")
        self.state_label.setText(sentence)
        self.state_label.setVisible(bool(sentence))
        width = min(self.MAX_WIDTH, max(160, (parent.width() if parent else self.MAX_WIDTH) - 2 * _MARGIN))
        self.setFixedWidth(width)
        self.adjustSize()
        size = QSize(width, self.sizeHint().height())
        height_room = parent.height() if parent else size.height() + anchor.bottom() + 2 * _MARGIN
        width_room = parent.width() if parent else width + 2 * _MARGIN
        below = anchor.bottom() + _GAP
        above = anchor.top() - _GAP - size.height()
        fits_below = below + size.height() <= height_room - _MARGIN
        if not fits_below and above >= _MARGIN:
            top = above
        else:
            top = max(_MARGIN, min(below, height_room - _MARGIN - size.height()))
        left = max(_MARGIN, min(anchor.left(), width_room - _MARGIN - size.width()))
        self.setGeometry(QRect(QPoint(left, top), size))
        self.shown_for = key
        self.show()
        self.raise_()

    def dismiss(self) -> None:
        self.shown_for = ""
        self.hide()


class ChipHoverWatcher(QObject):
    """Follows the pointer over a text widget's chips and shows the card of the one it rests on.

    Installed on the widget's viewport (``watch_chips``). Hit-tests the chip's own drawn box,
    so the card never shows for the words around it."""

    def __init__(self, editor: QAbstractScrollArea, card_for: CardFor) -> None:
        super().__init__(editor)
        self.editor = editor
        self.card_for = card_for
        self._chip: Optional[Dict[str, Any]] = None
        self._shown: Optional[MentionCard] = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._show)
        self._viewport = editor.viewport()
        self._viewport.setMouseTracking(True)
        self._viewport.installEventFilter(self)
        editor.installEventFilter(self)
        # The keyboard: in a read-only message, Tab selects a chip's anchor (the chip itself).
        # Qt moves that selection without a signal, so it is read once the key (or the focus)
        # has been handled.
        editor.selectionChanged.connect(self._on_selection)
        self._after_key = QTimer(self)
        self._after_key.setSingleShot(True)
        self._after_key.setInterval(0)
        self._after_key.timeout.connect(self._on_selection)

    def _doc_point(self, pos: QPoint) -> QPointF:
        h = self.editor.horizontalScrollBar()
        v = self.editor.verticalScrollBar()
        return QPointF(pos.x() + (h.value() if h else 0), pos.y() + (v.value() if v else 0))

    def chip_at_point(self, pos: QPoint) -> Optional[Dict[str, Any]]:
        """The chip under viewport point ``pos``, with its ``rect`` in document coordinates."""
        return chip_under(self.editor.document(), self._doc_point(pos))

    def _window_card(self) -> Optional[MentionCard]:
        """The window's card, made on first use (only when a card is about to show)."""
        window = self.editor.window()
        if window is None or window is self.editor:
            return None
        return MentionCard.for_window(window)

    def _key(self, chip: Mapping[str, Any]) -> str:
        return f"{id(self.editor)}:{chip.get('position')}:{chip.get('kind')}:{chip.get('id')}"

    def hover(self, pos: QPoint) -> None:
        chip = self.chip_at_point(pos)
        if chip is None:
            self.leave()
            return
        if self._chip is not None and self._key(chip) == self._key(self._chip):
            return
        self.leave()
        self._chip = chip
        self._timer.start(MENTION_CARD_REST_MS)

    def _on_selection(self) -> None:
        """A chip reached by the keyboard (its one character selected in a read-only message)
        shows its card after the same rest; anything else selected hides it."""
        if sip.isdeleted(self.editor) or not self.editor.isReadOnly():
            return
        cursor = self.editor.textCursor()
        begin, end = cursor.selectionStart(), cursor.selectionEnd()
        chip = chip_at(self.editor.document(), begin) if end - begin == 1 else None
        rect = chip_rect(self.editor.document(), begin) if chip is not None else None
        if chip is None or rect is None:
            self.leave()
            return
        chip = {**chip, "rect": rect}
        if self._chip is not None and self._key(chip) == self._key(self._chip):
            return
        self.leave()
        self._chip = chip
        self._timer.start(MENTION_CARD_REST_MS)

    def leave(self) -> None:
        self._timer.stop()
        self._chip = None
        card, self._shown = self._shown, None
        # Only the card this watcher showed, never a lookup (this runs while windows close).
        if card is not None and not sip.isdeleted(card) and card.shown_for.startswith(f"{id(self.editor)}:"):
            card.dismiss()

    def _show(self) -> None:
        chip = self._chip
        if chip is None or sip.isdeleted(self.editor) or not self.editor.isVisible():
            return
        data = self.card_for(chip) if callable(self.card_for) else None
        if not data:
            return
        card = self._window_card()
        if card is None:
            return
        rect = chip["rect"]
        h = self.editor.horizontalScrollBar()
        v = self.editor.verticalScrollBar()
        top_left = QPoint(int(rect.left() - (h.value() if h else 0)), int(rect.top() - (v.value() if v else 0)))
        viewport = self.editor.viewport()
        origin = viewport.mapTo(card.parentWidget(), top_left)
        anchor = QRect(origin, QSize(int(rect.width()), int(rect.height())))
        card.show_card(data, anchor, self._key(chip))
        self._shown = card

    def eventFilter(self, obj, event):  # noqa: N802 - Qt override
        if sip.isdeleted(self.editor) or sip.isdeleted(self._viewport):
            return False  # torn down: events still arrive while Qt deletes the widgets
        kind = event.type()
        if obj is self._viewport and kind == QEvent.MouseMove:
            self.hover(event.pos())
        elif kind in (QEvent.Leave, QEvent.Hide, QEvent.MouseButtonPress, QEvent.Wheel, QEvent.KeyPress, QEvent.FocusOut):
            self.leave()
            if kind == QEvent.KeyPress and obj is self.editor and self.editor.isReadOnly():
                self._after_key.start()
        elif kind == QEvent.FocusIn and obj is self.editor and self.editor.isReadOnly():
            self._after_key.start()
        return False


def watch_chips(editor: QAbstractScrollArea, card_for: CardFor) -> ChipHoverWatcher:
    """Show a chip's card when the pointer rests on it in ``editor`` (once per widget)."""
    watcher = getattr(editor, "_mention_hover_watcher", None)
    if isinstance(watcher, ChipHoverWatcher):
        watcher.card_for = card_for
        return watcher
    watcher = ChipHoverWatcher(editor, card_for)
    editor._mention_hover_watcher = watcher
    return watcher
