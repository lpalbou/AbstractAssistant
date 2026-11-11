"""`@entity` mention chips as structured objects of a QTextDocument (desktop mirror of
AbstractUIC panel-chat's inline chips, operator rulings 2026-11-08/10/11).

A chip is ONE object-replacement character (U+FFFC) whose char format carries the mention
(`id`, `name`, `kind`, its look `style`/`color`) and the object type ``MENTION_OBJECT_TYPE``.
``MentionChipObject`` draws it: the entity's orb (or the agent's mark) then the name, on a pill
of the accent hue (the kit's `pc-mention-chip`). Because the chip IS a character of the
document, the chips and the words can never drift apart: typing, Backspace over a chip
(deletes it, and with it the mention), undo/redo and cut/paste all act on the same text.
The list of mentions is read OUT of the document (``document_mentions``), never kept beside
it, and the words are never read for "@" (no-heuristics ruling): an "@name" that was not
picked from the list is plain text.

The words a send carries (``document_message``): the text with each chip written "@" + its
name, and the chips in text order as ``{id, name, kind, index, start}`` where ``index`` is the
chip's place among the message's mentions (0, 1, …, the gateway's `mention_index`) and
``start`` is where its "@Name" sits in the text (a Python string index), so
``text[start:start + len(name) + 1] == "@" + name``. Each name once (``mention_key``): a second
chip of a name already in the text is written as words and not sent (the kit's
`mentionsInText`).

The same chip object draws the chips of a sent message (``place_mention_chips``): the bubble's
words keep "@Name" for copy, and each placed mention is drawn exactly as it was in the composer,
without any way to remove it.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PyQt5.QtCore import QObject, QPointF, QRectF, QSizeF, Qt
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextObjectInterface,
)

from ..retint import parse_color
from ..theme import THEME

#: The object type of a mention chip in a QTextDocument (one U+FFFC per chip).
MENTION_OBJECT_TYPE = QTextFormat.UserObject + 11
OBJECT_CHAR = "\ufffc"

_PROP_ID = QTextFormat.UserProperty + 101
_PROP_NAME = QTextFormat.UserProperty + 102
_PROP_KIND = QTextFormat.UserProperty + 103
_PROP_STYLE = QTextFormat.UserProperty + 104
_PROP_COLOR = QTextFormat.UserProperty + 105

#: The clipboard type the kit's composer uses for chips (panel-chat `MENTION_CLIPBOARD_TYPE`):
#: a copy in the desktop composer pastes its chips back in the web one, and the other way round.
MENTION_CLIPBOARD_TYPE = "application/x-abstractframework-mentions+json"

KINDS = ("entity", "agent")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def mention_key(mention: Mapping[str, Any]) -> str:
    """One chip per name and message: `kind:id` (the kit's `mentionKey`)."""
    return f"{_text(mention.get('kind'))}:{_text(mention.get('id'))}"


def mention_text(mention: Mapping[str, Any]) -> str:
    """A chip's words in the message: "@" and its name."""
    return f"@{_text(mention.get('name'))}"


def mention_look(mention: Mapping[str, Any]) -> Optional[Dict[str, Optional[str]]]:
    """The chip's look ({style, color}), or None when it carries neither."""
    look = mention.get("avatar")
    if not isinstance(look, Mapping):
        return None
    style = _text(look.get("style")) or None
    color = _text(look.get("color")) or None
    return {"style": style, "color": color} if (style or color) else None


def usable_candidate(raw: Any) -> Optional[Dict[str, Any]]:
    """A name the composer can hold: an id, a name and a known kind; None otherwise."""
    if not isinstance(raw, Mapping):
        return None
    kind = _text(raw.get("kind")).lower()
    ident = _text(raw.get("id"))
    if kind not in KINDS or not ident:
        return None
    out: Dict[str, Any] = {"id": ident, "name": _text(raw.get("name")) or ident, "kind": kind}
    look = mention_look(raw)
    if look:
        out["avatar"] = look
    hint = _text(raw.get("hint"))
    if hint:
        out["hint"] = hint
    return out


# ---- colours ------------------------------------------------------------------------------


def qcolor(token: str, alpha: Optional[float] = None) -> QColor:
    """A QColor for a theme token (hex or rgba literal), alpha optionally replaced."""
    parsed = parse_color(token)
    if parsed is None:
        color = QColor(str(token or ""))
        if not color.isValid():
            color = QColor(THEME.accent)
    else:
        (r, g, b), a = parsed
        color = QColor(r, g, b)
        if a is not None:
            color.setAlphaF(max(0.0, min(1.0, a)))
    if alpha is not None:
        color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


def mix(a: QColor, b: QColor, amount_a: float) -> QColor:
    """``amount_a`` of ``a`` over ``b`` (CSS color-mix in srgb), opaque."""
    t = max(0.0, min(1.0, float(amount_a)))
    return QColor(
        round(a.red() * t + b.red() * (1 - t)),
        round(a.green() * t + b.green() * (1 - t)),
        round(a.blue() * t + b.blue() * (1 - t)),
    )


def entity_color(look: Optional[Mapping[str, Any]]) -> QColor:
    color = QColor(_text((look or {}).get("color")))
    return color if color.isValid() else qcolor(THEME.text_secondary)


# ---- the mark: an entity's orb, its initial disc, or the agent's mark --------------------

_MARK_CACHE: Dict[Tuple[Any, ...], QPixmap] = {}
_RENDERERS: Dict[int, Any] = {}


def _orb_image(style: str, color: QColor, size_px: int) -> Optional[QImage]:
    """The entity's AbstractAvatar design, still, in its colour (the kit's `ChatAuthorMark`:
    pose "listening", level 0.5, not animated). None when the design cannot be drawn."""
    try:
        renderer = _RENDERERS.get(size_px)
        if renderer is None:
            from abstractavatar import Renderer

            renderer = _RENDERERS[size_px] = Renderer(width=size_px, height=size_px)
        dim = qcolor(THEME.text_muted)
        eye = qcolor(THEME.danger)
        renderer.set_palette(
            warm=(color.red(), color.green(), color.blue()),
            eye=(eye.red(), eye.green(), eye.blue()),
            dim=(dim.red(), dim.green(), dim.blue()),
            ground=(0, 0, 0, 0),
        )
        pixels = renderer.render(style=style, state="listening", level=0.5, time=0.0, gaze=(0.0, 0.0), transparent=True)
        if len(pixels) != size_px * size_px * 4:
            return None
        return QImage(pixels, size_px, size_px, size_px * 4, QImage.Format_RGBA8888).copy()
    except Exception:
        return None


def mention_mark_pixmap(kind: str, name: str, look: Optional[Mapping[str, Any]], size: int, dpr: float = 1.0) -> QPixmap:
    """The small mark of a mention or an author: an entity's orb on a wash of its colour with a
    thin ring of it, its initial on that wash without a design, or the agent's mark. Cached per
    look, size and theme (the wash follows the surface)."""
    size = max(8, int(size))
    dpr = max(1.0, float(dpr or 1.0))
    style = _text((look or {}).get("style"))
    color_text = _text((look or {}).get("color"))
    key = (kind, name[:1].upper(), style, color_text, size, dpr, THEME.surface_raised, THEME.accent, THEME.text_primary)
    cached = _MARK_CACHE.get(key)
    if cached is not None:
        return cached
    px = max(8, round(size * dpr))
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    disc = QRectF(0.5, 0.5, px - 1.0, px - 1.0)
    surface = qcolor(THEME.surface_raised, 1.0)
    if kind == "agent":
        painter.setPen(QPen(qcolor(THEME.accent, 0.30), max(1.0, dpr)))
        painter.setBrush(qcolor(THEME.accent, 0.10))
        painter.drawEllipse(disc)
        from ..icons import symbol_icon

        glyph = max(6, round(size * 0.6))
        icon = symbol_icon("bot", color=THEME.accent, size=glyph).pixmap(round(glyph * dpr), round(glyph * dpr))
        off = (px - icon.width()) / 2
        painter.drawPixmap(QPointF(off, (px - icon.height()) / 2), icon)
    else:
        hue = entity_color(look)
        image = _orb_image(style, hue, px) if style else None
        painter.setPen(QPen(QColor(hue.red(), hue.green(), hue.blue(), round(255 * 0.55)), max(1.0, dpr)))
        painter.setBrush(mix(hue, surface, 0.20 if image is not None else 0.30))
        painter.drawEllipse(disc)
        if image is not None:
            clip = QPainterPath()
            clip.addEllipse(disc)
            painter.setClipPath(clip)
            painter.drawImage(QRectF(0, 0, px, px), image)
        else:
            font = QFont()
            font.setPixelSize(max(6, round(px * 0.5)))
            font.setWeight(QFont.DemiBold)
            painter.setFont(font)
            painter.setPen(qcolor(THEME.text_primary, 1.0))
            painter.drawText(QRectF(0, 0, px, px), Qt.AlignCenter, (name[:1] or "?").upper())
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    _MARK_CACHE[key] = pixmap
    return pixmap


# ---- the chip as a character of a document ----------------------------------------------


def chip_format(mention: Mapping[str, Any], base: Optional[QTextCharFormat] = None) -> QTextCharFormat:
    """The char format of one chip: ``base`` (the words' own format, so the chip takes their
    font) with the chip's object type and the mention it stands for."""
    fmt = QTextCharFormat(base) if base is not None else QTextCharFormat()
    fmt.setObjectType(MENTION_OBJECT_TYPE)
    fmt.setVerticalAlignment(QTextCharFormat.AlignBaseline)
    fmt.setProperty(_PROP_ID, _text(mention.get("id")))
    fmt.setProperty(_PROP_NAME, _text(mention.get("name")))
    fmt.setProperty(_PROP_KIND, _text(mention.get("kind")))
    look = mention_look(mention) or {}
    fmt.setProperty(_PROP_STYLE, look.get("style") or "")
    fmt.setProperty(_PROP_COLOR, look.get("color") or "")
    return fmt


def is_chip_format(fmt: QTextFormat) -> bool:
    return fmt.objectType() == MENTION_OBJECT_TYPE


def mention_of_format(fmt: QTextFormat) -> Optional[Dict[str, Any]]:
    """The mention a chip's format carries ({id, name, kind[, avatar]}), None for other text."""
    if not is_chip_format(fmt):
        return None
    out: Dict[str, Any] = {
        "id": str(fmt.property(_PROP_ID) or ""),
        "name": str(fmt.property(_PROP_NAME) or ""),
        "kind": str(fmt.property(_PROP_KIND) or ""),
    }
    style = str(fmt.property(_PROP_STYLE) or "") or None
    color = str(fmt.property(_PROP_COLOR) or "") or None
    if style or color:
        out["avatar"] = {"style": style, "color": color}
    return out


def _plain(text: str) -> str:
    # QTextDocument.toPlainText's own conversions: line/paragraph separators and nbsp.
    return text.replace("\u2028", "\n").replace("\u2029", "\n").replace("\u00a0", " ")


def _document_parts(doc: QTextDocument) -> List[Tuple[str, Optional[Dict[str, Any]], int]]:
    """The document as (words, mention or None, document position) parts in order; a chip is
    its own part with "@Name" as words."""
    parts: List[Tuple[str, Optional[Dict[str, Any]], int]] = []
    block = doc.begin()
    first = True
    while block.isValid():
        if not first:
            parts.append(("\n", None, block.position() - 1))
        first = False
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                mention = mention_of_format(fragment.charFormat())
                if mention is None:
                    parts.append((_plain(fragment.text()), None, fragment.position()))
                else:
                    for offset, char in enumerate(fragment.text()):
                        if char == OBJECT_CHAR:
                            parts.append((mention_text(mention), dict(mention), fragment.position() + offset))
                        else:
                            parts.append((_plain(char), None, fragment.position() + offset))
            it += 1
        block = block.next()
    return parts


def document_text(doc: QTextDocument) -> str:
    """The document's words with each chip written "@Name" (what `toPlainText` would show)."""
    return "".join(part for part, _m, _p in _document_parts(doc))


def document_mentions(doc: QTextDocument) -> List[Dict[str, Any]]:
    """The chips of the document in text order, each name once, with their document position
    (``position``) — the composer's mention list, read from the text itself."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for _words, mention, position in _document_parts(doc):
        if mention is None or mention_key(mention) in seen or not usable_candidate(mention):
            continue
        seen.add(mention_key(mention))
        out.append({**mention, "position": position})
    return out


def document_message(doc: QTextDocument, *, strip: bool = True) -> Tuple[str, List[Dict[str, Any]]]:
    """What a send carries: the words (chips as "@Name", trimmed like every send) and the chips
    in text order as ``{id, name, kind, index, start}`` (plus ``avatar`` for the bubble's chip
    face; the gateway is sent id/name/kind/index only by the worker)."""
    text = ""
    mentions: List[Dict[str, Any]] = []
    seen = set()
    for words, mention, _position in _document_parts(doc):
        if mention is not None and usable_candidate(mention) and mention_key(mention) not in seen:
            seen.add(mention_key(mention))
            entry: Dict[str, Any] = {"id": mention["id"], "name": mention["name"], "kind": mention["kind"], "index": len(mentions), "start": len(text)}
            if mention.get("avatar"):
                entry["avatar"] = dict(mention["avatar"])
            mentions.append(entry)
        text += words
    if strip:
        lead = len(text) - len(text.lstrip())
        text = text.strip()
        kept = []
        for m in mentions:
            start = int(m["start"]) - lead
            if 0 <= start and text[start:start + len(mention_text(m))] == mention_text(m):
                kept.append({**m, "start": start})
        mentions = [{**m, "index": i} for i, m in enumerate(kept)]
    return text, mentions


def mentions_in_text(text: str, mentions: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """The mentions whose "@Name" sits at their ``start`` in ``text``: text order, each name once,
    of two that overlap the earlier one (the kit's `mentionsInText`). Others are not drawn."""
    placed = []
    for raw in mentions or []:
        candidate = usable_candidate(raw)
        if candidate is None:
            continue
        start = raw.get("start")
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            continue
        if text[start:start + len(mention_text(candidate))] != mention_text(candidate):
            continue
        placed.append({**candidate, "start": start, **({"index": raw["index"]} if isinstance(raw.get("index"), int) else {})})
    placed.sort(key=lambda m: m["start"])
    out: List[Dict[str, Any]] = []
    seen = set()
    end = 0
    for m in placed:
        if mention_key(m) in seen or m["start"] < end:
            continue
        seen.add(mention_key(m))
        out.append(m)
        end = m["start"] + len(mention_text(m))
    return out


def utf16_len(text: str) -> int:
    """QTextDocument positions count UTF-16 code units; Python strings count code points."""
    return len(text.encode("utf-16-le")) // 2


def place_mention_chips(doc: QTextDocument, text: str, mentions: Sequence[Mapping[str, Any]]) -> int:
    """Draw ``mentions`` as chips in a document whose words are ``text`` (a sent message's
    bubble, or a message given back to the composer): each mention's "@Name" at its ``start``
    becomes its chip, keeping the words' own format for the font. Returns how many were placed;
    a mention whose "@Name" is not at its ``start`` stays words (never searched for)."""
    placed = 0
    cursor = QTextCursor(doc)
    cursor.beginEditBlock()
    try:
        for m in reversed(mentions_in_text(text, mentions)):
            words = mention_text(m)
            begin = utf16_len(text[: m["start"]])
            end = begin + utf16_len(words)
            cursor.setPosition(begin)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            if _plain(cursor.selectedText()) != words:
                continue
            base = QTextCursor(doc)
            base.setPosition(begin + 1)
            fmt = chip_format(m, base.charFormat())
            cursor.insertText(OBJECT_CHAR, fmt)
            placed += 1
    finally:
        cursor.endEditBlock()
    return placed


def chip_at(doc: QTextDocument, position: int) -> Optional[Dict[str, Any]]:
    """The chip at document ``position`` (the character after it), or None."""
    if position < 0 or position >= doc.characterCount() - 1:
        return None
    if doc.characterAt(position) != OBJECT_CHAR:
        return None
    block = doc.findBlock(position)
    it = block.begin()
    while not it.atEnd():
        fragment = it.fragment()
        if fragment.isValid() and fragment.position() <= position < fragment.position() + fragment.length():
            mention = mention_of_format(fragment.charFormat())
            return {**mention, "position": position} if mention else None
        it += 1
    return None


def chip_rect(doc: QTextDocument, position: int) -> Optional[QRectF]:
    """Where the chip at ``position`` is drawn, in document coordinates."""
    block = doc.findBlock(position)
    layout = block.layout()
    if layout is None:
        return None
    rel = position - block.position()
    line = layout.lineForTextPosition(rel)
    if not line.isValid():
        return None
    origin = doc.documentLayout().blockBoundingRect(block).topLeft()
    x1 = line.cursorToX(rel)[0]
    x2 = line.cursorToX(rel + 1)[0]
    return QRectF(origin.x() + min(x1, x2), origin.y() + line.y(), abs(x2 - x1), line.height())


def chip_under(doc: QTextDocument, point: QPointF) -> Optional[Dict[str, Any]]:
    """The chip drawn under ``point`` (document coordinates), with its ``rect``, or None."""
    hit = doc.documentLayout().hitTest(point, Qt.FuzzyHit)
    if hit < 0:
        return None
    for position in (hit, hit - 1):
        chip = chip_at(doc, position)
        if chip is None:
            continue
        rect = chip_rect(doc, position)
        if rect is not None and rect.contains(point):
            return {**chip, "rect": rect}
    return None


# ---- the clipboard ------------------------------------------------------------------------


def clipboard_payload(doc: QTextDocument, begin: int, end: int) -> Tuple[str, Optional[str]]:
    """A copy of document range [begin, end): its words (chips as "@Name") and, when it holds
    whole chips, the kit's clipboard JSON (`mentionClipboard`: chips with ``start`` relative to
    the copied words)."""
    words = ""
    chips: List[Dict[str, Any]] = []
    for part, mention, position in _document_parts(doc):
        if mention is not None:
            if begin <= position < end:
                entry = {"id": mention["id"], "name": mention["name"], "kind": mention["kind"], "start": len(words)}
                if mention.get("avatar"):
                    entry["avatar"] = dict(mention["avatar"])
                chips.append(entry)
                words += part
            continue
        # A plain part spans [position, position + utf16 length): keep the overlap.
        size = utf16_len(part) if part != "\n" else 1
        lo, hi = max(begin, position), min(end, position + size)
        if lo >= hi:
            continue
        if part == "\n":
            words += "\n"
            continue
        encoded = part.encode("utf-16-le")
        words += encoded[(lo - position) * 2:(hi - position) * 2].decode("utf-16-le", errors="ignore")
    if not chips:
        return words, None
    return words, json.dumps({"v": 1, "text": words, "mentions": chips})


def mentions_from_clipboard(data: Optional[str], plain: str) -> List[Dict[str, Any]]:
    """The chips a paste brings: only those a copy of a composer put on the clipboard, and only
    when the pasted words are exactly what that copy held (the kit's `mentionsFromClipboard`).
    Anything else is words: an "@name" is never read out of them."""
    if not data:
        return []
    try:
        box = json.loads(data)
    except (TypeError, ValueError):
        return []
    if not isinstance(box, dict) or box.get("v") != 1 or box.get("text") != plain or not isinstance(box.get("mentions"), list):
        return []
    return mentions_in_text(plain, box["mentions"])


class MentionChipObject(QObject, QTextObjectInterface):
    """Draws a chip: the mark over the "@" (the kit hides the "@" under it), then the name, on
    a pill of the accent hue. One handler per document layout (``install_chip_handler``)."""

    PAD_X = 4.0
    GAP = 3.0

    def _font(self, doc: QTextDocument, fmt: QTextFormat) -> QFont:
        return fmt.toCharFormat().font().resolve(doc.defaultFont())

    def intrinsicSize(self, doc, position, fmt):  # noqa: N802 - Qt override
        mention = mention_of_format(fmt) or {}
        metrics = QFontMetricsF(self._font(doc, fmt))
        height = metrics.height()
        mark = max(10.0, round(metrics.ascent() * 0.95))
        width = self.PAD_X + mark + self.GAP + metrics.horizontalAdvance(_text(mention.get("name"))) + self.PAD_X
        return QSizeF(width, height)

    def drawObject(self, painter, rect, doc, position, fmt):  # noqa: N802 - Qt override
        mention = mention_of_format(fmt) or {}
        font = self._font(doc, fmt)
        metrics = QFontMetricsF(font)
        hue = qcolor(THEME.accent, 1.0)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        pill = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = max(3.0, font.pixelSize() * 0.45 if font.pixelSize() > 0 else metrics.height() * 0.3)
        painter.setPen(Qt.NoPen)
        fill = QColor(hue)
        fill.setAlphaF(0.20)
        painter.setBrush(fill)
        painter.drawRoundedRect(pill, radius, radius)
        mark = max(10.0, round(metrics.ascent() * 0.95))
        dpr = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
        pixmap = mention_mark_pixmap(_text(mention.get("kind")), _text(mention.get("name")), mention_look(mention), int(mark), dpr)
        top = rect.top() + (rect.height() - mark) / 2
        painter.drawPixmap(QRectF(rect.left() + self.PAD_X, top, mark, mark), pixmap, QRectF(0, 0, pixmap.width(), pixmap.height()))
        painter.setFont(font)
        painter.setPen(mix(hue, qcolor(THEME.text_primary, 1.0), 0.62))
        baseline = rect.top() + metrics.ascent()
        painter.drawText(QPointF(rect.left() + self.PAD_X + mark + self.GAP, baseline), _text(mention.get("name")))
        painter.restore()


def install_chip_handler(doc: QTextDocument, owner: QObject) -> MentionChipObject:
    """Register the chip drawer on ``doc``'s layout (again after a layout swap); the handler is
    parented to ``owner`` so it lives as long as the widget showing the document."""
    handler = getattr(owner, "_mention_chip_handler", None)
    if not isinstance(handler, MentionChipObject):
        handler = MentionChipObject(owner)
        owner._mention_chip_handler = handler
    doc.documentLayout().registerHandler(MENTION_OBJECT_TYPE, handler)
    return handler
