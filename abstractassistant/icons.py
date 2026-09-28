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
from pathlib import Path

from PyQt5.QtCore import QByteArray, QPointF, Qt
from PyQt5.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap

try:  # QtSvg ships with the PyQt5 wheel; guard for minimal test envs.
    from PyQt5.QtSvg import QSvgRenderer
except Exception:  # pragma: no cover - import safety
    QSvgRenderer = None  # type: ignore[assignment]


_ICON_CACHE: dict = {}
_MISSING_WARNED: set = set()

# QIcon.cacheKey() -> the (name, requested colour, size) it was built from.
# A QIcon cannot carry attributes and a widget cannot be asked what glyph it
# holds, so this is how a theme switch finds out what to re-render: look up
# the icon a widget already has, and rebuild it from the same request against
# the new palette. `requested` is the colour the CALL SITE asked for, never
# the translated one, so translations never compound.
_SPEC_BY_ICON: dict = {}


def _remember_spec(icon, name, requested: str, size: int) -> None:
    try:
        _SPEC_BY_ICON[icon.cacheKey()] = (str(name), str(requested), int(size))
    except Exception:
        pass


def icon_image_path(name: str, *, color: str = "", size: int = 10) -> str:
    """A PNG on disk for a glyph, for use in a stylesheet's ``image: url(...)``.

    A spin box's arrows are SUBCONTROLS: there is no widget to call setIcon on,
    and QSS cannot take a QIcon. With no image Qt falls back to the native
    arrow, which is a dark glyph on a dark field — the operator's "the vertical
    + - are not visible on the right". Files are cached per (glyph, colour,
    size), so a theme switch writes a new one and the old stays harmless.
    """
    import hashlib
    import tempfile

    tint = themed_color(color) if color else ""
    key = hashlib.sha1(f"{name}|{tint}|{size}".encode("utf-8")).hexdigest()[:16]
    folder = Path(tempfile.gettempdir()) / "abstractassistant-glyphs"
    target = folder / f"{key}.png"
    if not target.exists():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            icon = symbol_icon(name, color=color, size=size)
            icon.pixmap(int(size), int(size)).save(str(target), "PNG")
        except Exception:
            return ""
    # QSS url() wants forward slashes on every platform.
    return target.as_posix()


def retint_widget_icons(root) -> int:
    """Rebuild every icon under ``root`` against the active palette.

    Icons are baked at widget construction, so without this a theme switch
    left the composer and toolbar glyphs in the OLD palette — near-white on
    near-white after switching to a light theme, i.e. invisible. Returns how
    many were rebuilt.
    """
    from PyQt5.QtWidgets import QWidget

    changed = 0
    widgets = [root] + (root.findChildren(QWidget) if hasattr(root, "findChildren") else [])
    for widget in widgets:
        getter = getattr(widget, "icon", None)
        setter = getattr(widget, "setIcon", None)
        if not callable(getter) or not callable(setter):
            continue
        try:
            current = getter()
            if current is None or current.isNull():
                continue
            spec = _SPEC_BY_ICON.get(current.cacheKey())
        except Exception:
            continue
        if spec is None:
            continue
        name, requested, size = spec
        try:
            setter(symbol_icon(name, color=requested, size=size))
            changed += 1
        except Exception:
            continue
    return changed

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
    "zap": [
        "M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"
    ],
    "archive": [
        "M3 3h18a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z",
        "M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8",
        "M10 12h4",
    ],
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
    # --- settings / activity / approval glyphs (Lucide) ---
    "terminal": ["m4 17 6-6-6-6", "M12 19h8"],
    "globe": [
        "M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0-20 0",
        "M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20",
        "M2 12h20",
    ],
    "folder": [
        "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z",
    ],
    "folder-plus": [
        "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z",
        "M12 10v6",
        "M9 13h6",
    ],
    "shield": [
        "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z",
    ],
    "shield-alert": [
        "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z",
        "M12 8v4",
        "M12 16h.01",
    ],
    "mail": [
        "m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7",
        "M2 4m2 0h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
    ],
    "camera": [
        "M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z",
        "M12 13m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
    ],
    "keyboard": [
        "M2 4m2 0h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
        "M6 8h.01", "M10 8h.01", "M14 8h.01", "M18 8h.01",
        "M8 12h.01", "M12 12h.01", "M16 12h.01", "M7 16h10",
    ],
    "audio-lines": ["M2 10v3", "M6 6v11", "M10 3v18", "M14 8v7", "M18 5v13", "M22 10v3"],
    "headphones": [
        "M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3",
    ],
    "clock": ["M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0-20 0", "M12 6v6l4 2"],
    "circle-check": ["M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0-20 0", "m9 12 2 2 4-4"],
    "circle-x": ["M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0-20 0", "m15 9-6 6", "m9 9 6 6"],
    "circle-alert": ["M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0-20 0", "M12 8v4", "M12 16h.01"],
    "list-tree": [
        "M21 12h-8", "M21 6H8", "M21 18h-8",
        "M3 6v4c0 1.1.9 2 2 2h3", "M3 10v6c0 1.1.9 2 2 2h3",
    ],
    "hand": [
        "M18 11V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2",
        "M14 10V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v2",
        "M10 10.5V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2v8",
        "M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15",
    ],
    "wifi-off": [
        "M12 20h.01",
        "M8.5 16.429a5 5 0 0 1 7 0",
        "M5 12.859a10 10 0 0 1 5.17-2.69",
        "M19 12.859a10 10 0 0 0-2.007-1.523",
        "M2 8.82a15 15 0 0 1 4.177-2.643",
        "M22 8.82a15 15 0 0 0-11.288-3.764",
        "m2 2 20 20",
    ],
    "eye": [
        "M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0",
        "M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
    ],
    "eye-off": [
        "M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49",
        "M14.084 14.158a3 3 0 0 1-4.242-4.242",
        "M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143",
        "m2 2 20 20",
    ],
    "chevron-up": ["m18 15-6-6-6 6"],
    "loader": [
        "M12 2v4", "m16.2 7.8 2.9-2.9", "M18 12h4", "m16.2 16.2 2.9 2.9",
        "M12 18v4", "m4.9 19.1 2.9-2.9", "M2 12h4", "m4.9 4.9 2.9 2.9",
    ],
    "monitor": [
        "M2 3m2 0h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z",
        "M8 21h8", "M12 17v4",
    ],
    "cpu": [
        "M4 4m2 0h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
        "M9 9m0 0h6v6H9z",
        "M15 2v2", "M15 20v2", "M2 15h2", "M2 9h2", "M20 15h2", "M20 9h2", "M9 2v2", "M9 20v2",
    ],
    "link": [
        "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71",
        "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",
    ],
    "message-square": [
        "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
    ],
    "square-pen": [
        "M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7",
        "M18.375 2.625a1 1 0 0 1 3 3l-9.013 9.014a2 2 0 0 1-.853.505l-2.873.84a.5.5 0 0 1-.62-.62l.84-2.873a2 2 0 0 1 .506-.852z",
    ],
}


def _resolve(name: str) -> str:
    n = str(name or "").strip().lower()
    return _ALIASES.get(n, n)


# AbstractUIC kit glyphs drawn verbatim (their own viewBox and stroke), so a
# control reads the same here as in the web clients. `play-circle` is the
# kit's `playCircle` — the shared "Run now" icon — vendored with its hint in
# `assets/automation_controls.json` (a byte-identical copy of the kit's
# canonical file; the AbstractFramework root `scripts/check_identity_sync.py`
# fails on drift).
_KIT_GLYPHS = {"play-circle": "run_now"}


def _kit_glyph_document(name: str, color: str) -> str:
    from .core.automations import AUTOMATION_CONTROLS

    glyph = AUTOMATION_CONTROLS["icons"][_KIT_GLYPHS[name]]
    body = str(glyph["svg"]).replace("currentColor", color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{glyph["view_box"]}" fill="none" '
        f'stroke="{color}" stroke-width="{glyph["stroke_width"]}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def _render_document(document: str, size: int) -> QPixmap:
    pixmap = QPixmap(int(size) * 2, int(size) * 2)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    try:
        QSvgRenderer(QByteArray(document.encode("utf-8"))).render(painter)
    finally:
        painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return pixmap


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


def themed_color(color: str) -> str:
    """A glyph tint expressed in the ACTIVE palette.

    Call sites hand this function colours written against the shipped dark
    palette — tokens like ``THEME.text_secondary`` (already correct) and a
    long tail of hard-coded literals like ``#8ea1b8`` (never correct after a
    switch). Both go through the same translation the stylesheets use, so a
    near-white glyph becomes a near-black one on a light theme instead of
    disappearing into the background.
    """
    from .retint import retint_stylesheet
    from .theme import DEFAULT_THEME, THEME

    text = str(color or "").strip()
    if not text:
        return text
    try:
        return retint_stylesheet(text, source=DEFAULT_THEME, target=THEME)
    except Exception:
        return text


def symbol_icon(name: str, *, color: str = "", size: int = 18) -> QIcon:
    """Return a cached QIcon for a named glyph, tinted and Retina-crisp."""
    # Default to the palette's own text colour: a hard-coded near-white glyph
    # is invisible on a light theme.
    if not color:
        from .theme import THEME

        color = THEME.text_primary

    requested = str(color or "").strip()
    color = themed_color(requested)

    key = (str(name or "").strip().lower(), str(color or "").strip().lower(), int(size))
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        _remember_spec(cached, name, requested, size)
        return cached

    resolved = _resolve(key[0])

    if resolved.startswith("spinner"):
        try:
            frame = int(resolved[7:] or "0")
        except Exception:
            frame = 0
        icon = QIcon(_render_spinner(frame, color, size))
        _ICON_CACHE[key] = icon
        _remember_spec(icon, name, requested, size)
        return icon

    if resolved in _KIT_GLYPHS:
        document = _kit_glyph_document(resolved, color)
        icon = QIcon(_render_document(document, size))
        _ICON_CACHE[key] = icon
        _remember_spec(icon, name, requested, size)
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
        _remember_spec(icon, name, requested, size)
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
    _remember_spec(icon, name, requested, size)
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
