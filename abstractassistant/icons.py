"""Symbol icons for the assistant UI.

The icons are Lucide glyphs (ISC License, https://lucide.dev) rendered from
inline SVG path data via QSvgRenderer — the same in-memory SVG technique the
mermaid renderer already uses. This replaces ~290 lines of hand-drawn QPainter
glyphs that carried inconsistent stroke weights and content-box sizes.

`symbol_icon(name, color, size)` keeps the previous call contract (name +
tint color + logical size), an internal cache, and 2x/Retina rendering. The
animated loading spinner stays a parametric QPainter draw (`spinner<frame>`).

Lucide is ISC-licensed:
    Copyright (c) 2020, Lucide Contributors
    Permission to use, copy, modify, and/or distribute this software for any
    purpose with or without fee is hereby granted (ISC License).
"""

from __future__ import annotations

import math
import warnings

from PyQt5.QtCore import QByteArray, QPointF, Qt
from PyQt5.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap

try:  # QtSvg ships with the PyQt5 wheel; guard for minimal test envs.
    from PyQt5.QtSvg import QSvgRenderer
except Exception:  # pragma: no cover - import safety
    QSvgRenderer = None  # type: ignore[assignment]


_ICON_CACHE: dict = {}
_MISSING_WARNED: set = set()

# Glyphs drawn as a solid fill (media transport reads better filled at small
# sizes); everything else is a 2px round stroke in the Lucide house style.
_FILLED = {"play", "pause", "stop"}

# Lucide 24x24 path data. Aliases map product names → the Lucide glyph.
_ALIASES = {
    "close": "x",
    "settings": "gear",
    "sliders": "sliders-horizontal",
    "file-document": "file-text",
    "file-data": "file-text",
    "file-audio": "file-music",
    "entity": "flame",
    "agent": "bot",
    "reconnect": "refresh-cw",
    "jump-to-latest": "arrow-down-to-line",
    "info": "info",
}

_ICON_PATHS: dict = {
    "plus": ["M5 12h14", "M12 5v14"],
    "x": ["M18 6 6 18", "m6 6 12 12"],
    "check": ["M20 6 9 17l-5-5"],
    "chevron-down": ["m6 9 6 6 6-6"],
    "chevron-right": ["m9 18 6-6-6-6"],
    "copy": [
        "M8 8m2 0h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z",
        "M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2",
    ],
    "external": [
        "M15 3h6v6",
        "M10 14 21 3",
        "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",
    ],
    "gear": [
        "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z",
        "M12 9m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
    ],
    "wrench": [
        "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z",
    ],
    "sliders-horizontal": [
        "M10 5h11", "M3 5h3", "M14 12h7", "M3 12h7", "M18 19h3", "M3 19h11",
        "M8 3v4", "M12 10v4", "M16 17v4",
    ],
    "paperclip": [
        "m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48",
    ],
    "mic": [
        "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z",
        "M19 10v2a7 7 0 0 1-14 0v-2",
        "M12 19v3",
    ],
    "mic-off": [
        "M2 2 22 22",
        "M18.89 13.23A7.12 7.12 0 0 0 19 12v-2",
        "M5 10v2a7 7 0 0 0 12 5",
        "M15 9.34V5a3 3 0 0 0-5.68-1.33",
        "M9 9v3a3 3 0 0 0 5.12 2.12",
        "M12 19v3",
    ],
    "send": [
        "M14.54 21.69a.5.5 0 0 0 .94-.02l6.5-19a.5.5 0 0 0-.64-.64l-19 6.5a.5.5 0 0 0-.02.94l7.93 3.18a2 2 0 0 1 1.11 1.11z",
        "m21.85 2.15-10.94 10.94",
    ],
    "stop": ["M6 6m2 0h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z"],
    "pause": [
        "M6 4m1 0h2a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z",
        "M14 4m1 0h2a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z",
    ],
    "play": ["M6 4v16l14-8z"],
    "speaker": [
        "M11 4.7a.7.7 0 0 0-1.2-.5L6.4 7.6A1.4 1.4 0 0 1 5.4 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.4a1.4 1.4 0 0 1 1 .4l3.4 3.4a.7.7 0 0 0 1.2-.5z",
        "M16 9a5 5 0 0 1 0 6",
        "M19.36 18.36a9 9 0 0 0 0-12.72",
    ],
    "volume-x": [
        "M11 4.7a.7.7 0 0 0-1.2-.5L6.4 7.6A1.4 1.4 0 0 1 5.4 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.4a1.4 1.4 0 0 1 1 .4l3.4 3.4a.7.7 0 0 0 1.2-.5z",
        "M22 9 16 15",
        "M16 9 22 15",
    ],
    "spark": [
        "M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.14 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z",
        "M20 3v4", "M22 5h-4", "M4 17v2", "M5 18H3",
    ],
    "bot": [
        "M12 8V4H8",
        "M4 8m2 0h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z",
        "M2 14h2", "M20 14h2", "M15 13v2", "M9 13v2",
    ],
    "flame": [
        "M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z",
    ],
    "trash": [
        "M3 6h18",
        "M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6",
        "M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2",
        "M10 11v6", "M14 11v6",
    ],
    "refresh-cw": [
        "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8",
        "M21 3v5h-5",
        "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16",
        "M8 16H3v5",
    ],
    "alert": [
        "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z",
        "M12 9v4", "M12 17h.01",
    ],
    "info": ["M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0-20 0", "M12 16v-4", "M12 8h.01"],
    "arrow-down-to-line": ["M12 17V3", "m6 11 6 6 6-6", "M19 21H5"],
    "file": [
        "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",
        "M14 2v4a2 2 0 0 0 2 2h4",
    ],
    "file-text": [
        "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",
        "M14 2v4a2 2 0 0 0 2 2h4",
        "M16 13H8", "M16 17H8", "M10 9H8",
    ],
    "file-image": [
        "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",
        "M14 2v4a2 2 0 0 0 2 2h4",
        "M10 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0",
        "m20 17-1.3-1.3a2.4 2.4 0 0 0-3.4 0L9 22",
    ],
    "file-music": [
        "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",
        "M14 2v4a2 2 0 0 0 2 2h4",
        "M9 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0",
        "M11 18V9.5a.5.5 0 0 1 .5-.5l4 1",
    ],
    "file-video": [
        "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",
        "M14 2v4a2 2 0 0 0 2 2h4",
        "m10 11 5 3-5 3z",
    ],
    "file-code": [
        "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",
        "M14 2v4a2 2 0 0 0 2 2h4",
        "m9 13-2 2 2 2", "m13 13 2 2-2 2",
    ],
    "file-archive": [
        "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",
        "M14 2v4a2 2 0 0 0 2 2h4",
        "M10 7V6", "M10 12v-1", "M10 18v-2",
        "M10 20m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0",
    ],
}


def _resolve(name: str) -> str:
    n = str(name or "").strip().lower()
    return _ALIASES.get(n, n)


def _svg_document(paths, color: str, filled: bool) -> str:
    if filled:
        body = "".join(f'<path d="{d}"/>' for d in paths)
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="{color}" stroke="none">{body}</svg>'
        )
    body = "".join(f'<path d="{d}"/>' for d in paths)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def _render_spinner(frame: int, color: str, size: int) -> QPixmap:
    pixmap = QPixmap(int(size) * 2, int(size) * 2)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(2.0, 2.0)
    painter.setPen(Qt.NoPen)
    center = QPointF(size * 0.5, size * 0.5)
    radius = size * 0.27
    dot_radius = max(1.4, size * 0.07)
    for idx in range(8):
        angle = ((idx * 45.0) - 90.0) * math.pi / 180.0
        # Head dot reaches full opacity; tail fades round the ring.
        alpha = 40 + ((idx - frame) % 8) * 30
        dot = QColor(color)
        dot.setAlpha(max(40, min(255, alpha)))
        painter.setBrush(QBrush(dot))
        painter.drawEllipse(
            QPointF(center.x() + radius * math.cos(angle), center.y() + radius * math.sin(angle)),
            dot_radius,
            dot_radius,
        )
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return pixmap


def symbol_icon(name: str, *, color: str = "#edf2f8", size: int = 18) -> QIcon:
    """Return a cached QIcon for a named glyph, tinted and Retina-crisp."""
    key = (str(name or "").strip().lower(), str(color or "").strip().lower(), int(size))
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    resolved = _resolve(key[0])

    if resolved.startswith("spinner"):
        try:
            frame = int(resolved[7:] or "0")
        except Exception:
            frame = 0
        icon = QIcon(_render_spinner(frame, color, size))
        _ICON_CACHE[key] = icon
        return icon

    paths = _ICON_PATHS.get(resolved)
    if paths is None and resolved.startswith("file"):
        paths = _ICON_PATHS["file"]
    if paths is None or QSvgRenderer is None:
        if paths is None and resolved not in _MISSING_WARNED:
            _MISSING_WARNED.add(resolved)
            warnings.warn(f"#FALLBACK: unknown icon '{resolved}' (rendering a dot)")
        icon = QIcon(_render_dot(color, size))
        _ICON_CACHE[key] = icon
        return icon

    document = _svg_document(paths, color, resolved in _FILLED)
    pixmap = QPixmap(int(size) * 2, int(size) * 2)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    try:
        renderer = QSvgRenderer(QByteArray(document.encode("utf-8")))
        renderer.render(painter)
    finally:
        painter.end()
    pixmap.setDevicePixelRatio(2.0)
    icon = QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon


def _render_dot(color: str, size: int) -> QPixmap:
    pixmap = QPixmap(int(size) * 2, int(size) * 2)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(2.0, 2.0)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(color)))
    painter.drawEllipse(QPointF(size * 0.5, size * 0.5), size * 0.2, size * 0.2)
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return pixmap
