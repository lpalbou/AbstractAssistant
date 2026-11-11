"""The desktop composer's `@` mentions (operator rulings 2026-11-08/10/11, "following the same
logic as other apps": AbstractUIC panel-chat 0.9.13 inline chips, AbstractAssistant web).

``MentionTextEdit`` is the QTextEdit the palette's composer is built on. Typing `@` (at the start
or after a space) opens the list of names (``MentionPicker``) fed by the roster the palette
caches (``set_mention_names``); picking one puts a CHIP into the sentence where the `@query` was
(the entity's orb + name, no ×), followed by one space. The chip is one character of the
document (``mention_chip``), so deleting it in the text removes the mention, and undo, redo,
cut, copy and paste carry it. Nothing is read out of the words: an "@name" typed or pasted from
elsewhere stays words.

``message_payload()`` is what a send carries: the words, each chip as "@Name", and the chips as
``{id, name, kind, index, start}`` in text order (``mention_chip.document_message``).
``toPlainText()`` returns the same words, so every existing caller of the composer's text sees
"@Castor", never the chip's placeholder character.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QMimeData, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QTextCharFormat, QTextCursor, QTextFormat
from PyQt5.QtWidgets import QTextEdit, QWidget

from ..core.mentions import EntityRoster, Mention, MentionCandidate
from .mention_card import CardFor, watch_chips
from .mention_chip import (
    MENTION_CLIPBOARD_TYPE,
    OBJECT_CHAR,
    chip_format,
    clipboard_payload,
    document_mentions,
    document_message,
    document_text,
    install_chip_handler,
    mention_key,
    mention_text,
    mentions_from_clipboard,
    mentions_in_text,
    place_mention_chips,
    usable_candidate,
    utf16_len,
)
from .mention_picker import ALREADY, LOAD_FAILED, LOADING, NOBODY, MentionPicker, mention_trigger_at, no_match

_SPACE_AFTER = {" ", "\t", "\u00a0", "\u2028", "\u2029", "\n", "\r"}


def candidate_dict(candidate: MentionCandidate) -> Dict[str, Any]:
    """A roster name as the chip holds it ({id, name, kind[, avatar]})."""
    out: Dict[str, Any] = {"id": candidate.id, "name": candidate.name, "kind": candidate.kind}
    if candidate.avatar is not None:
        out["avatar"] = candidate.avatar.to_dict()
    return out


def as_mentions(chips: Sequence[Mapping[str, Any]]) -> List[Mention]:
    """The composer's chips as the worker takes them (``core.mentions.Mention``, text order)."""
    return [Mention(id=str(c["id"]), name=str(c["name"]), kind=str(c["kind"]), index=int(c["index"]), start=c.get("start")) for c in chips]


def plain_format(fmt: QTextCharFormat) -> QTextCharFormat:
    """``fmt`` as words: no object type (text typed after a chip inherits its format)."""
    out = QTextCharFormat(fmt)
    out.clearProperty(QTextFormat.ObjectType)
    out.clearProperty(QTextFormat.ObjectIndex)
    return out


class MentionTextEdit(QTextEdit):
    """A QTextEdit whose `@` opens the mention list and whose chips are part of the text."""

    #: The list opened and no roster is held (never read in this chat, or read again after a
    #: refusal): the host reads `GET /entities` off the GUI thread and answers with
    #: ``set_mention_names``. Never per keystroke.
    mention_names_wanted = pyqtSignal()

    # Class defaults: Qt delivers events (``event``) while ``__init__`` is still running.
    _picker: Optional[MentionPicker] = None
    _trigger: Optional[Tuple[int, str]] = None

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        install_chip_handler(self.document(), self)
        self._mentions_on = False
        self._unavailable = ""
        self._roster: Optional[EntityRoster] = None
        self._roster_status = "idle"  # idle | loading | ready | error
        self._trigger: Optional[Tuple[int, str]] = None
        self._dismissed_at: Optional[int] = None
        self._picker: Optional[MentionPicker] = None
        self._anchor: Optional[QWidget] = None
        self._place_pending = False
        self.textChanged.connect(self._sync_list)
        self.cursorPositionChanged.connect(self._sync_list)

    # -- host API --------------------------------------------------------------------------

    def set_mentions_enabled(self, on: bool) -> None:
        """Mentions are offered only where a send can carry them (a session chat)."""
        self._mentions_on = bool(on)
        self._sync_list()

    def mentions_enabled(self) -> bool:
        return self._mentions_on

    def set_mentions_unavailable(self, sentence: str) -> None:
        """An older gateway: the list says so (one visible sentence) and offers no name."""
        self._unavailable = str(sentence or "").strip()
        self._sync_list()

    def set_mention_names(self, roster: Optional[EntityRoster], *, status: str = "ready") -> None:
        """The roster the list filters (``core.mentions.EntityRoster``, agent first): ``status``
        "ready" with it, "loading" while it is read, "error" when it could not be, "idle" to read
        it again at the next `@` (a new chat, a refusal)."""
        if status == "ready":
            if not isinstance(roster, EntityRoster):
                raise TypeError(f"The mention names are a core.mentions.EntityRoster, not {type(roster).__name__}.")
            self._roster = roster
        elif status == "idle":
            self._roster = None
        self._roster_status = status
        self._sync_list()

    def mention_roster(self) -> Optional[EntityRoster]:
        return self._roster

    def set_card_provider(self, card_for: CardFor) -> None:
        """The card a chip shows after a 150 ms rest (``mention_card``)."""
        watch_chips(self, card_for)

    def set_list_anchor(self, widget: QWidget) -> None:
        """The box the list floats above (the composer card), default this field."""
        self._anchor = widget

    def mentions(self) -> List[Dict[str, Any]]:
        """The chips in the text, in order, each name once (with their document ``position``)."""
        return document_mentions(self.document())

    def message_payload(self) -> Tuple[str, List[Dict[str, Any]]]:
        """(words, mentions) of a send: trimmed words with chips as "@Name", and the chips as
        {id, name, kind, index, start[, avatar]}."""
        return document_message(self.document())

    def draft_payload(self) -> Tuple[str, List[Dict[str, Any]]]:
        """(words, chips) of the field as it stands, untrimmed (a draft kept aside)."""
        return document_message(self.document(), strip=False)

    def toPlainText(self) -> str:  # noqa: N802 - the words as the person reads them
        return document_text(self.document())

    def set_message(self, text: str, mentions: Sequence[Mapping[str, Any]] = ()) -> None:
        """Put words back in the field with their chips (a message given back after a send
        could not go): each mention whose "@Name" sits at its ``start`` becomes its chip."""
        self.setPlainText(str(text or ""))
        doc = self.document()
        doc.setUndoRedoEnabled(False)
        try:
            place_mention_chips(doc, str(text or ""), mentions)
        finally:
            doc.setUndoRedoEnabled(True)
        self.moveCursor(QTextCursor.End)

    def picker(self) -> Optional[MentionPicker]:
        return self._picker

    def mention_list_open(self) -> bool:
        picker = self._picker
        return picker is not None and not sip.isdeleted(picker) and picker.isVisible()

    def mention_list_takes_enter(self) -> bool:
        """Enter picks the highlighted name; while the names load it waits (it would send the
        typed `@…` as words). With nothing to pick, Enter sends as always."""
        if not self.mention_list_open():
            return False
        picker = self._picker
        return picker.active_index >= 0 or (picker.status == "loading" and not self._unavailable)

    def insert_mention(self, candidate: Mapping[str, Any]) -> bool:
        """Pick ``candidate`` for the `@` being typed: its chip replaces the `@query`, then one
        space unless one follows; the caret goes after it. One undo step."""
        chosen = usable_candidate(candidate)
        trigger = self._trigger
        if chosen is None or trigger is None:
            return False
        start, _query = trigger
        doc = self.document()
        caret = self.textCursor().position()
        base_cursor = QTextCursor(doc)
        base_cursor.setPosition(start + 1)
        base = plain_format(base_cursor.charFormat())
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.setPosition(caret, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(OBJECT_CHAR, chip_format(chosen, base))
        at_end = cursor.position() >= doc.characterCount() - 1
        if at_end or doc.characterAt(cursor.position()) not in _SPACE_AFTER:
            cursor.insertText(" ", base)
        else:
            cursor.movePosition(QTextCursor.NextCharacter)
        cursor.endEditBlock()
        self._trigger = None
        self.setTextCursor(cursor)
        self._sync_list()
        return True

    # -- the list --------------------------------------------------------------------------

    def _current_trigger(self) -> Optional[Tuple[int, str]]:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return None
        caret = cursor.position()
        probe = QTextCursor(cursor)
        probe.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        before = probe.selectedText()
        found = mention_trigger_at(before)
        if found is None:
            return None
        index, query = found
        return caret - utf16_len(before[index:]), query

    def _ensure_picker(self) -> Optional[MentionPicker]:
        window = self.window()
        if window is None or window is self:
            return None
        if self._picker is None or sip.isdeleted(self._picker) or self._picker.parentWidget() is not window:
            self._picker = MentionPicker(window)
            self._picker.picked.connect(self.insert_mention)
        return self._picker

    def _close_list(self) -> None:
        if self.mention_list_open():
            self._picker.hide()

    def _sync_list(self) -> None:
        trigger = self._current_trigger() if self._mentions_on and self.isEnabled() and not self.isReadOnly() else None
        if trigger is None or trigger[0] != self._dismissed_at:
            self._dismissed_at = None
        self._trigger = trigger
        if trigger is None or trigger[0] == self._dismissed_at:
            self._close_list()
            return
        picker = self._ensure_picker()
        if picker is None:
            return
        opening = not picker.isVisible()
        query = trigger[1]
        if self._unavailable:
            picker.set_names([], message=self._unavailable, status="unavailable")
        else:
            if opening and self._roster_status in {"idle", "error"}:
                self._roster_status = "loading"
                self.mention_names_wanted.emit()
            found = [candidate_dict(c) for c in self._roster.match(query)] if self._roster is not None else []
            picked = {mention_key(m) for m in self.mentions()}
            shown = [c for c in found if mention_key(c) not in picked]
            if self._roster is None and self._roster_status == "loading":
                picker.set_names([], message=LOADING, status="loading")
            elif self._roster is None:
                picker.set_names([], message=LOAD_FAILED, status="error")
            else:
                message = "" if shown else (ALREADY if found else (no_match(query) if query else NOBODY))
                picker.set_names(shown, message=message, status="ready")
        picker.show()
        self._schedule_place()

    def _schedule_place(self) -> None:
        self._place_list()
        if not self._place_pending:
            # Once more after the layout settled (the composer grows as the text does).
            self._place_pending = True
            QTimer.singleShot(0, self._place_later)

    def _place_later(self) -> None:
        self._place_pending = False
        self._place_list()

    def _place_list(self) -> None:
        if sip.isdeleted(self) or not self.mention_list_open():
            return
        picker = self._picker
        anchor = self._anchor if self._anchor is not None else self
        window = picker.parentWidget()
        try:
            top_left = anchor.mapTo(window, QPoint(0, 0))
        except RuntimeError:
            return
        picker.place_above(QRect(top_left, anchor.size()))

    def _list_key(self, event) -> bool:
        key = event.key()
        modifiers = event.modifiers()
        picker = self._picker
        if picker is None:
            return False
        if key in (Qt.Key_Up, Qt.Key_Down) and picker.items:
            picker.move(1 if key == Qt.Key_Down else -1)
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab) and not (modifiers & Qt.ShiftModifier):
            candidate = picker.active_candidate()
            if candidate is not None:
                self.insert_mention(candidate)
                return True
            if key != Qt.Key_Tab and picker.status == "loading" and not self._unavailable:
                return True
            return False
        if key == Qt.Key_Escape:
            self._dismissed_at = self._trigger[0] if self._trigger else None
            self._close_list()
            return True
        return False

    def event(self, event) -> bool:  # noqa: A003 - Qt override
        kind = event.type()
        if self.mention_list_open():
            if kind == QEvent.ShortcutOverride and event.key() in (Qt.Key_Escape, Qt.Key_Up, Qt.Key_Down, Qt.Key_Tab, Qt.Key_Return, Qt.Key_Enter):
                event.accept()
                return True
            if kind == QEvent.KeyPress and self._list_key(event):
                event.accept()
                return True
        return super().event(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._close_list()
        super().focusOutEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._close_list()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._place_list()

    # -- the clipboard ---------------------------------------------------------------------

    def createMimeDataFromSelection(self) -> QMimeData:  # noqa: N802 - Qt override
        cursor = self.textCursor()
        words, data = clipboard_payload(self.document(), cursor.selectionStart(), cursor.selectionEnd())
        if data is None:
            return super().createMimeDataFromSelection()
        mime = QMimeData()
        mime.setText(words)
        mime.setData(MENTION_CLIPBOARD_TYPE, data.encode("utf-8"))
        return mime

    def insertFromMimeData(self, source) -> None:  # noqa: N802 - Qt override
        if source is not None and source.hasFormat(MENTION_CLIPBOARD_TYPE) and source.hasText():
            plain = source.text()
            raw = bytes(source.data(MENTION_CLIPBOARD_TYPE)).decode("utf-8", errors="replace")
            chips = mentions_from_clipboard(raw, plain)
            if chips:
                self._paste_with_chips(plain, chips)
                return
        super().insertFromMimeData(source)

    def _paste_with_chips(self, plain: str, chips: Sequence[Mapping[str, Any]]) -> None:
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        self._insert_words(cursor, plain, chips)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def _insert_words(self, cursor: QTextCursor, plain: str, chips: Sequence[Mapping[str, Any]]) -> None:
        """Type ``plain`` at ``cursor`` with ``chips`` (placed at their ``start`` in it). A name
        already in the text stays words (one chip per name and message)."""
        base = plain_format(cursor.charFormat())
        present = {mention_key(m) for m in self.mentions()}
        at = 0
        for chip in mentions_in_text(plain, chips):
            start = int(chip["start"])
            if start > at:
                cursor.insertText(plain[at:start], base)
            if mention_key(chip) in present:
                cursor.insertText(mention_text(chip), base)
            else:
                present.add(mention_key(chip))
                cursor.insertText(OBJECT_CHAR, chip_format(chip, base))
            at = start + len(mention_text(chip))
        if at < len(plain):
            cursor.insertText(plain[at:], base)

    # -- words from elsewhere (a failed send, dictation) -----------------------------------

    def insert_message_at_start(self, text: str, mentions: Sequence[Mapping[str, Any]] = ()) -> None:
        """A message given back (its send did not go): its words and chips go in front of what
        was typed meanwhile, on their own line; with nothing typed they are the whole field."""
        words = str(text or "")
        if not words:
            return
        if not self.toPlainText().strip():
            self.set_message(words, mentions)
            return
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.Start)
        self._insert_words(cursor, words + "\n", mentions)
        cursor.endEditBlock()
        self.moveCursor(QTextCursor.End)

    def append_words(self, text: str) -> None:
        """Words added at the end of the draft (dictation), after one space; the draft's chips
        stay chips. The draft's trailing spaces go, as the plain-text append did."""
        words = str(text or "")
        if not self.toPlainText().strip():
            self.setPlainText(words)
            self.moveCursor(QTextCursor.End)
            return
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.End)
        while cursor.position() > 0 and doc.characterAt(cursor.position() - 1) in _SPACE_AFTER:
            cursor.deletePreviousChar()
        if words.strip():
            cursor.insertText(" " + words, plain_format(cursor.charFormat()))
        cursor.endEditBlock()
        self.setTextCursor(cursor)
