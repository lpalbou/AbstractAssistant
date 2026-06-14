"""Qt-only tray shell for AbstractAssistant v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import mimetypes
import math
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
try:
    from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
    from PyQt5.QtMultimediaWidgets import QVideoWidget
    QT_MULTIMEDIA_AVAILABLE = True
except Exception:  # pragma: no cover - multimedia is optional at runtime
    QMediaContent = None  # type: ignore[assignment]
    QMediaPlayer = None  # type: ignore[assignment]
    QVideoWidget = None  # type: ignore[assignment]
    QT_MULTIMEDIA_AVAILABLE = False

try:
    import soundfile as _soundfile
except Exception:  # pragma: no cover - optional at runtime
    _soundfile = None

from abstractassistant.config import Config, DEFAULT_GATEWAY_URL
from abstractassistant.utils.icon_generator import IconGenerator
from abstractassistant.utils.markdown_renderer import MarkdownRenderer

from .controller import AssistantV2Controller
from .gateway import ROUTE_SPECS, CapabilityRouteRow
from .hotkey import GlobalHotkeyManager
from .preferences import AssistantPreferences

_MARKDOWNISH_RE = re.compile(r"(^\s*[-*]\s+|^\s*\d+\.\s+|```|`[^`]+`|\[[^\]]+\]\([^)]+\)|\|.+\||^#)", flags=re.M)
_HTML_ACTION_FENCE_RE = re.compile(r"```(?:html|x-html|xml)[^\n]*\n(.*?)```", flags=re.I | re.S)


@dataclass(frozen=True)
class HistoryScrollRequest:
    mode: str = "preserve"
    message_key: str = ""
    offset: int = 0


@dataclass(frozen=True)
class AssistantHtmlAction:
    label: str
    href: str


def _tool_calls_text(tool_calls: Any) -> str:
    if not isinstance(tool_calls, list) or not tool_calls:
        return "No tool details were provided by the workflow."
    blocks: List[str] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "<unknown>").strip() or "<unknown>"
        arguments = call.get("arguments")
        if isinstance(arguments, dict):
            rendered = json_dumps(arguments)
        else:
            rendered = str(arguments or "")
        blocks.append(f"{name}\n{rendered}".strip())
    return "\n\n".join(blocks) or "No tool details were provided by the workflow."


def _assistant_html(renderer: MarkdownRenderer, content: str) -> str:
    base = renderer.render(content)
    themed_override = """
    <style>
    .markdown-content,
    .markdown-content p,
    .markdown-content li,
    .markdown-content strong,
    .markdown-content em,
    .markdown-content h1,
    .markdown-content h2,
    .markdown-content h3,
    .markdown-content h4,
    .markdown-content h5,
    .markdown-content h6,
    .markdown-content blockquote,
    .markdown-content td,
    .markdown-content th {
        color: #e8edf4 !important;
        font-size: 12px !important;
        line-height: 1.34 !important;
    }
    .markdown-content code {
        background: #20262f !important;
        color: #c9f0e1 !important;
    }
    .markdown-content pre,
    .highlight {
        background: #161b23 !important;
        color: #e8edf4 !important;
        border-color: rgba(232, 237, 244, 0.12) !important;
    }
    .markdown-content a {
        color: #79c7ff !important;
    }
    .markdown-content table {
        width: 100% !important;
        table-layout: fixed !important;
        border-collapse: collapse !important;
        border-spacing: 0 !important;
        margin: 4px 0 2px 0 !important;
        background: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(166, 187, 214, 0.14) !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }
    .markdown-content td,
    .markdown-content th {
        padding: 3px 5px !important;
        overflow-wrap: anywhere !important;
        word-break: break-word !important;
        white-space: normal !important;
        vertical-align: top !important;
        border: 1px solid rgba(166, 187, 214, 0.12) !important;
    }
    .markdown-content th {
        font-size: 10px !important;
        font-weight: 700 !important;
        line-height: 1.18 !important;
        background: rgba(121, 136, 164, 0.18) !important;
    }
    .markdown-content td {
        font-size: 10px !important;
        line-height: 1.2 !important;
    }
    .markdown-content tr:nth-child(even) td {
        background: rgba(255, 255, 255, 0.02) !important;
    }
    .markdown-content pre,
    .markdown-content code {
        white-space: pre-wrap !important;
        overflow-wrap: anywhere !important;
        word-break: break-word !important;
    }
    .markdown-content blockquote {
        border-left: 3px solid rgba(121, 199, 255, 0.42) !important;
        color: #b7c3d4 !important;
    }
    </style>
    """
    return themed_override + base


def _render_assistant_as_plain_label(content: str) -> bool:
    text = str(content or "")
    if not text.strip():
        return True
    if _MARKDOWNISH_RE.search(text):
        return False
    if "\n\n" in text:
        return False
    return True


def _assistant_action_href_allowed(href: Any) -> bool:
    text = str(href or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    scheme = str(parsed.scheme or "").strip().lower()
    if scheme in {"javascript", "vbscript"}:
        return False
    return scheme in {"http", "https", "mailto", "data", "file"}


class _AssistantHtmlActionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.actions: List[AssistantHtmlAction] = []
        self._active_href = ""
        self._active_label_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        if str(tag or "").strip().lower() != "a":
            return
        href = ""
        for key, value in attrs:
            if str(key or "").strip().lower() == "href":
                href = str(value or "").strip()
                break
        if not _assistant_action_href_allowed(href):
            return
        self._active_href = href
        self._active_label_parts = []

    def handle_data(self, data: str) -> None:
        if not self._active_href:
            return
        text = str(data or "")
        if text:
            self._active_label_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if str(tag or "").strip().lower() != "a" or not self._active_href:
            return
        label = " ".join("".join(self._active_label_parts).split()) or self._active_href
        self.actions.append(AssistantHtmlAction(label=label, href=self._active_href))
        self._active_href = ""
        self._active_label_parts = []


def _assistant_html_actions_from_snippet(snippet: str) -> List[AssistantHtmlAction]:
    text = str(snippet or "").strip()
    if not text:
        return []
    parser = _AssistantHtmlActionParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return []
    deduped: List[AssistantHtmlAction] = []
    seen: set[tuple[str, str]] = set()
    for action in parser.actions:
        key = (str(action.label or "").strip(), str(action.href or "").strip())
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped


def _assistant_content_with_actions(content: str) -> tuple[str, List[AssistantHtmlAction]]:
    text = str(content or "")
    actions: List[AssistantHtmlAction] = []

    def _replace(match: re.Match[str]) -> str:
        snippet = str(match.group(1) or "").strip()
        snippet_actions = _assistant_html_actions_from_snippet(snippet)
        if not snippet_actions:
            return match.group(0)
        actions.extend(snippet_actions)
        return ""

    cleaned = _HTML_ACTION_FENCE_RE.sub(_replace, text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, actions


def _open_external_href(href: str) -> bool:
    text = str(href or "").strip()
    if not _assistant_action_href_allowed(text):
        return False
    try:
        return bool(QDesktopServices.openUrl(QUrl.fromEncoded(text.encode("utf-8"))))
    except Exception:
        return False


def _qt_icon() -> QIcon:
    generator = IconGenerator(size=96)
    image = generator.create_app_icon(color_scheme="green", animated=False)
    path = Path.home() / ".abstractassistant" / "v2_tray_icon.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return QIcon(str(path))


_ICON_CACHE: Dict[tuple[str, str, int], QIcon] = {}


def _symbol_icon(name: str, *, color: str = "#dfe7f1", size: int = 18) -> QIcon:
    key = (str(name or "").strip().lower(), str(color or "").strip().lower(), int(size))
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    tint = QColor(color)
    pen = QPen(tint)
    pen.setWidthF(max(1.6, size * 0.10))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    def _line(x1: float, y1: float, x2: float, y2: float) -> None:
        painter.drawLine(QPointF(x1 * size, y1 * size), QPointF(x2 * size, y2 * size))

    if key[0] == "plus":
        _line(0.50, 0.18, 0.50, 0.82)
        _line(0.18, 0.50, 0.82, 0.50)
    elif key[0] == "sliders":
        for y, knob_x in ((0.25, 0.70), (0.50, 0.34), (0.75, 0.58)):
            _line(0.18, y, 0.82, y)
            painter.setBrush(QBrush(tint))
            painter.drawEllipse(QPointF(knob_x * size, y * size), size * 0.08, size * 0.08)
            painter.setBrush(Qt.NoBrush)
    elif key[0] == "paperclip":
        path = QPainterPath(QPointF(size * 0.63, size * 0.30))
        path.cubicTo(size * 0.80, size * 0.45, size * 0.77, size * 0.78, size * 0.50, size * 0.78)
        path.cubicTo(size * 0.29, size * 0.78, size * 0.24, size * 0.55, size * 0.37, size * 0.44)
        path.lineTo(size * 0.58, size * 0.23)
        path.cubicTo(size * 0.66, size * 0.16, size * 0.77, size * 0.18, size * 0.82, size * 0.26)
        path.cubicTo(size * 0.88, size * 0.34, size * 0.86, size * 0.46, size * 0.78, size * 0.52)
        path.lineTo(size * 0.49, size * 0.81)
        painter.drawPath(path)
    elif key[0] == "mic":
        painter.drawRoundedRect(QRectF(size * 0.34, size * 0.16, size * 0.32, size * 0.40), size * 0.12, size * 0.12)
        _line(0.50, 0.56, 0.50, 0.77)
        _line(0.34, 0.80, 0.66, 0.80)
        path = QPainterPath()
        path.moveTo(size * 0.24, size * 0.48)
        path.cubicTo(size * 0.24, size * 0.68, size * 0.36, size * 0.76, size * 0.50, size * 0.76)
        path.cubicTo(size * 0.64, size * 0.76, size * 0.76, size * 0.68, size * 0.76, size * 0.48)
        painter.drawPath(path)
    elif key[0] == "send":
        painter.setBrush(Qt.NoBrush)
        trail_tint = QColor(tint)
        trail_tint.setAlpha(150)
        trail_pen = QPen(trail_tint)
        trail_pen.setWidthF(max(1.4, size * 0.09))
        trail_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(trail_pen)
        _line(0.16, 0.50, 0.37, 0.50)
        _line(0.20, 0.35, 0.40, 0.35)
        _line(0.20, 0.65, 0.40, 0.65)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(tint))
        dart = QPainterPath()
        dart.moveTo(size * 0.38, size * 0.34)
        dart.lineTo(size * 0.38, size * 0.45)
        dart.lineTo(size * 0.64, size * 0.45)
        dart.lineTo(size * 0.64, size * 0.24)
        dart.lineTo(size * 0.88, size * 0.50)
        dart.lineTo(size * 0.64, size * 0.76)
        dart.lineTo(size * 0.64, size * 0.55)
        dart.lineTo(size * 0.38, size * 0.55)
        dart.lineTo(size * 0.38, size * 0.66)
        dart.lineTo(size * 0.16, size * 0.50)
        dart.closeSubpath()
        painter.drawPath(dart)
    elif key[0] == "gear":
        outer = QRectF(size * 0.22, size * 0.22, size * 0.56, size * 0.56)
        painter.drawEllipse(outer)
        painter.drawEllipse(QRectF(size * 0.40, size * 0.40, size * 0.20, size * 0.20))
        for x1, y1, x2, y2 in (
            (0.50, 0.08, 0.50, 0.20),
            (0.50, 0.80, 0.50, 0.92),
            (0.08, 0.50, 0.20, 0.50),
            (0.80, 0.50, 0.92, 0.50),
            (0.21, 0.21, 0.30, 0.30),
            (0.70, 0.70, 0.79, 0.79),
            (0.21, 0.79, 0.30, 0.70),
            (0.70, 0.30, 0.79, 0.21),
        ):
            _line(x1, y1, x2, y2)
    elif key[0] == "copy":
        painter.drawRoundedRect(QRectF(size * 0.22, size * 0.30, size * 0.40, size * 0.42), size * 0.08, size * 0.08)
        painter.drawRoundedRect(QRectF(size * 0.38, size * 0.16, size * 0.40, size * 0.42), size * 0.08, size * 0.08)
    elif key[0] == "close":
        _line(0.28, 0.28, 0.72, 0.72)
        _line(0.72, 0.28, 0.28, 0.72)
    elif key[0] == "external":
        painter.drawRoundedRect(QRectF(size * 0.20, size * 0.28, size * 0.42, size * 0.42), size * 0.07, size * 0.07)
        _line(0.46, 0.24, 0.78, 0.24)
        _line(0.78, 0.24, 0.78, 0.56)
        _line(0.44, 0.58, 0.78, 0.24)
    elif key[0].startswith("file"):
        kind = "generic"
        if "-" in key[0]:
            kind = key[0].split("-", 1)[1] or "generic"
        page = QPainterPath()
        page.moveTo(size * 0.28, size * 0.16)
        page.lineTo(size * 0.58, size * 0.16)
        page.lineTo(size * 0.74, size * 0.32)
        page.lineTo(size * 0.74, size * 0.82)
        page.lineTo(size * 0.28, size * 0.82)
        page.closeSubpath()
        painter.drawPath(page)
        _line(0.58, 0.16, 0.58, 0.32)
        _line(0.58, 0.32, 0.74, 0.32)
        if kind == "image":
            painter.drawRoundedRect(QRectF(size * 0.34, size * 0.42, size * 0.34, size * 0.20), size * 0.04, size * 0.04)
            painter.drawEllipse(QPointF(size * 0.40, size * 0.47), size * 0.025, size * 0.025)
            _line(0.37, 0.58, 0.46, 0.49)
            _line(0.46, 0.49, 0.56, 0.58)
            _line(0.49, 0.58, 0.58, 0.52)
        elif kind == "audio":
            _line(0.42, 0.42, 0.42, 0.62)
            _line(0.42, 0.42, 0.58, 0.38)
            painter.drawEllipse(QPointF(size * 0.39, size * 0.66), size * 0.05, size * 0.05)
            painter.drawEllipse(QPointF(size * 0.57, size * 0.62), size * 0.05, size * 0.05)
            _line(0.58, 0.38, 0.58, 0.58)
        elif kind == "video":
            painter.drawRoundedRect(QRectF(size * 0.34, size * 0.43, size * 0.34, size * 0.20), size * 0.04, size * 0.04)
            painter.setBrush(QBrush(tint))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(size * 0.46, size * 0.47),
                        QPointF(size * 0.56, size * 0.53),
                        QPointF(size * 0.46, size * 0.59),
                    ]
                )
            )
            painter.setBrush(Qt.NoBrush)
            painter.setPen(pen)
        elif kind == "code":
            _line(0.38, 0.54, 0.46, 0.46)
            _line(0.38, 0.54, 0.46, 0.62)
            _line(0.64, 0.54, 0.56, 0.46)
            _line(0.64, 0.54, 0.56, 0.62)
            _line(0.52, 0.44, 0.48, 0.64)
        elif kind == "archive":
            painter.drawRoundedRect(QRectF(size * 0.36, size * 0.42, size * 0.28, size * 0.24), size * 0.03, size * 0.03)
            _line(0.50, 0.44, 0.50, 0.64)
            _line(0.44, 0.50, 0.56, 0.50)
        elif kind == "data":
            painter.drawRoundedRect(QRectF(size * 0.35, size * 0.42, size * 0.30, size * 0.22), size * 0.03, size * 0.03)
            _line(0.35, 0.49, 0.65, 0.49)
            _line(0.35, 0.56, 0.65, 0.56)
            _line(0.45, 0.42, 0.45, 0.64)
            _line(0.55, 0.42, 0.55, 0.64)
        else:
            _line(0.36, 0.46, 0.64, 0.46)
            _line(0.36, 0.54, 0.64, 0.54)
            _line(0.36, 0.62, 0.56, 0.62)
    elif key[0] == "speaker":
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(size * 0.18, size * 0.42),
                    QPointF(size * 0.34, size * 0.42),
                    QPointF(size * 0.50, size * 0.30),
                    QPointF(size * 0.50, size * 0.70),
                    QPointF(size * 0.34, size * 0.58),
                    QPointF(size * 0.18, size * 0.58),
                ]
            )
        )
        outer = QPainterPath()
        outer.moveTo(size * 0.60, size * 0.34)
        outer.quadTo(size * 0.82, size * 0.50, size * 0.60, size * 0.66)
        inner = QPainterPath()
        inner.moveTo(size * 0.56, size * 0.42)
        inner.quadTo(size * 0.68, size * 0.50, size * 0.56, size * 0.58)
        painter.drawPath(inner)
        painter.drawPath(outer)
    elif key[0] == "pause":
        painter.setBrush(QBrush(tint))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(size * 0.28, size * 0.20, size * 0.14, size * 0.60), size * 0.04, size * 0.04)
        painter.drawRoundedRect(QRectF(size * 0.58, size * 0.20, size * 0.14, size * 0.60), size * 0.04, size * 0.04)
    elif key[0] == "play":
        painter.setBrush(QBrush(tint))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(size * 0.34, size * 0.24),
                    QPointF(size * 0.72, size * 0.50),
                    QPointF(size * 0.34, size * 0.76),
                ]
            )
        )
    elif key[0].startswith("spinner"):
        try:
            frame = int(key[0][7:] or "0")
        except Exception:
            frame = 0
        painter.setPen(Qt.NoPen)
        center = QPointF(size * 0.50, size * 0.50)
        radius = size * 0.27
        dot_radius = max(1.4, size * 0.065)
        for idx in range(8):
            angle = ((idx * 45.0) - 90.0) * 3.141592653589793 / 180.0
            alpha = 55 + ((idx - frame) % 8) * 24
            dot = QColor(tint)
            dot.setAlpha(max(45, min(255, alpha)))
            painter.setBrush(QBrush(dot))
            painter.drawEllipse(
                QPointF(center.x() + radius * math.cos(angle), center.y() + radius * math.sin(angle)),
                dot_radius,
                dot_radius,
            )
    elif key[0] == "spark":
        _line(0.50, 0.12, 0.50, 0.40)
        _line(0.50, 0.60, 0.50, 0.88)
        _line(0.12, 0.50, 0.40, 0.50)
        _line(0.60, 0.50, 0.88, 0.50)
        _line(0.24, 0.24, 0.38, 0.38)
        _line(0.62, 0.62, 0.76, 0.76)
        _line(0.24, 0.76, 0.38, 0.62)
        _line(0.62, 0.38, 0.76, 0.24)
    elif key[0] == "check":
        _line(0.20, 0.55, 0.42, 0.76)
        _line(0.42, 0.76, 0.82, 0.24)
    else:
        painter.setBrush(QBrush(tint))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(size * 0.30, size * 0.30, size * 0.40, size * 0.40))

    painter.end()
    icon = QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon


def _copy_to_clipboard(text: str) -> bool:
    clipboard = QApplication.clipboard()
    if clipboard is None:
        return False
    clipboard.setText(str(text or ""))
    return True


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _parse_usage_summary(value: Any) -> Optional[Dict[str, int]]:
    if not isinstance(value, dict):
        return None
    in_tok = _coerce_int(value.get("input_tokens"))
    if in_tok is None:
        in_tok = _coerce_int(value.get("prompt_tokens"))
    if in_tok is None:
        in_tok = _coerce_int(value.get("prompt"))
    if in_tok is None:
        in_tok = _coerce_int(value.get("input"))
    if in_tok is None:
        in_tok = _coerce_int(value.get("in"))

    out_tok = _coerce_int(value.get("output_tokens"))
    if out_tok is None:
        out_tok = _coerce_int(value.get("completion_tokens"))
    if out_tok is None:
        out_tok = _coerce_int(value.get("completion"))
    if out_tok is None:
        out_tok = _coerce_int(value.get("output"))
    if out_tok is None:
        out_tok = _coerce_int(value.get("out"))

    total_tok = _coerce_int(value.get("total_tokens"))
    if total_tok is None:
        total_tok = _coerce_int(value.get("total"))
    if total_tok is None and (in_tok is not None or out_tok is not None):
        total_tok = max(0, int(in_tok or 0) + int(out_tok or 0))

    parsed = {
        "input_tokens": max(0, int(in_tok or 0)),
        "output_tokens": max(0, int(out_tok or 0)),
        "total_tokens": max(0, int(total_tok or 0)),
    }
    if parsed["input_tokens"] == 0 and parsed["output_tokens"] == 0 and parsed["total_tokens"] == 0:
        return None
    return parsed


def _parse_iso_ms(raw: Any) -> Optional[int]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    return int(dt.timestamp() * 1000)


def _extract_duration_ms(value: Any) -> Optional[int]:
    if not isinstance(value, dict):
        return None
    for key in ("duration_ms", "elapsed_ms", "total_ms", "processing_ms", "generation_ms"):
        numeric = _coerce_float(value.get(key))
        if numeric is not None and numeric >= 0:
            return int(numeric)
    for key in ("duration_s", "elapsed_s", "total_s", "processing_s", "generation_s"):
        numeric = _coerce_float(value.get(key))
        if numeric is not None and numeric >= 0:
            return int(numeric * 1000.0)
    started = _parse_iso_ms(value.get("started_at"))
    ended = _parse_iso_ms(value.get("ended_at"))
    if started is not None and ended is not None:
        return max(0, ended - started)
    return None


def _format_duration_short(duration_ms: int) -> str:
    ms = max(0, int(duration_ms or 0))
    if ms < 1000:
        return f"{ms} ms"
    seconds = ms / 1000.0
    if seconds < 10:
        return f"{seconds:.1f}s"
    return f"{int(round(seconds))}s"


def _format_message_timestamp(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone()
    except Exception:
        return text
    now = datetime.now(dt.tzinfo)
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if (now.date() - dt.date()).days == 1:
        return f"Yesterday {dt.strftime('%H:%M')}"
    return dt.strftime("%b %d · %H:%M")


def _message_bubble_width(viewport_width: int, *, role: str) -> int:
    width = max(0, int(viewport_width or 0))
    normalized_role = str(role or "").strip().lower()
    ratio = 0.40 if normalized_role == "user" else 0.70
    return max(96, int(width * ratio))


def _normalize_attachment_path(raw_path: Any) -> str:
    text = str(raw_path or "").strip()
    if not text:
        return ""
    return str(Path(text).expanduser())


def _attachment_kind(raw_path: Any) -> str:
    path = _normalize_attachment_path(raw_path)
    name = Path(path).name.lower()
    suffix = Path(name).suffix.lower()
    content_type, _encoding = mimetypes.guess_type(name)
    content_type = str(content_type or "").strip().lower()
    if content_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".svg"}:
        return "image"
    if content_type.startswith("audio/") or suffix in {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".aiff", ".aif", ".opus"}:
        return "audio"
    if content_type.startswith("video/") or suffix in {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpeg", ".mpg"}:
        return "video"
    if suffix in {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".html", ".css", ".scss", ".sql", ".sh", ".bash", ".zsh"}:
        return "code"
    if suffix in {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}:
        return "archive"
    if suffix in {".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".xml", ".parquet", ".sqlite", ".db", ".xls", ".xlsx"}:
        return "data"
    if content_type.startswith("text/") or suffix in {".txt", ".md", ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".rtf"}:
        return "document"
    return "generic"


def _attachment_icon_name(raw_path: Any) -> str:
    return {
        "image": "file-image",
        "audio": "file-audio",
        "video": "file-video",
        "code": "file-code",
        "archive": "file-archive",
        "data": "file-data",
        "document": "file-document",
    }.get(_attachment_kind(raw_path), "file")


def _attachment_icon_color(raw_path: Any) -> str:
    return {
        "image": "#7fc4ff",
        "audio": "#77d1a8",
        "video": "#f0c979",
        "code": "#ffb286",
        "archive": "#d0b7ff",
        "data": "#9fd0ff",
        "document": "#dfe7f1",
    }.get(_attachment_kind(raw_path), "#dfe7f1")


def _merge_attachment_paths(existing: List[str], incoming: List[str]) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for raw_path in list(existing or []) + list(incoming or []):
        normalized = _normalize_attachment_path(raw_path)
        if not normalized:
            continue
        candidate = Path(normalized)
        if not candidate.exists() or not candidate.is_file():
            continue
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        merged.append(key)
    return merged


def _local_file_paths_from_mime(mime: Any) -> List[str]:
    if mime is None or not hasattr(mime, "hasUrls") or not mime.hasUrls():
        return []
    paths: List[str] = []
    for url in mime.urls():
        try:
            is_local = bool(url.isLocalFile())
        except Exception:
            is_local = False
        if not is_local:
            continue
        try:
            local_path = url.toLocalFile()
        except Exception:
            local_path = ""
        normalized = _normalize_attachment_path(local_path)
        if normalized:
            paths.append(normalized)
    return _merge_attachment_paths([], paths)


def _artifact_key(artifact: Dict[str, Any]) -> str:
    artifact_id = str(artifact.get("$artifact") or artifact.get("artifact_id") or "").strip()
    local_path = str(artifact.get("local_path") or artifact.get("path") or "").strip()
    filename = str(artifact.get("filename") or "").strip()
    if artifact_id:
        return f"artifact:{artifact_id}"
    if local_path:
        return f"local:{local_path}"
    if filename:
        return f"file:{filename}"
    return f"raw:{repr(sorted(artifact.items()))}"


def _artifact_media_kind(artifact: Dict[str, Any]) -> str:
    content_type = str(artifact.get("content_type") or "").strip().lower()
    modality = str(artifact.get("modality") or "").strip().lower()
    filename = str(artifact.get("filename") or artifact.get("local_path") or artifact.get("path") or "").strip().lower()

    if content_type.startswith("image/") or modality == "image" or filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff")):
        return "image"
    if content_type.startswith("video/") or modality == "video" or filename.endswith((".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")):
        return "video"
    if content_type.startswith("audio/") or modality == "audio" or filename.endswith((".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac")):
        return "audio"
    return "other"


def _artifact_label(artifact: Dict[str, Any]) -> str:
    filename = str(artifact.get("filename") or "").strip()
    if filename:
        return filename
    local_path = str(artifact.get("local_path") or artifact.get("path") or "").strip()
    if local_path:
        return Path(local_path).name or local_path
    artifact_id = str(artifact.get("$artifact") or artifact.get("artifact_id") or "").strip()
    return artifact_id or "artifact"


def _message_media_artifacts(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    if not isinstance(metadata, dict):
        return []

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _push(candidate: Any, *, fallback_kind: str = "", fallback_content_type: str = "") -> None:
        if not isinstance(candidate, dict):
            return
        artifact_id = str(candidate.get("$artifact") or candidate.get("artifact_id") or "").strip()
        local_path = str(candidate.get("local_path") or candidate.get("path") or "").strip()
        if not artifact_id and not local_path:
            return
        item = dict(candidate)
        if fallback_kind and not str(item.get("modality") or "").strip():
            item["modality"] = fallback_kind
        if fallback_content_type and not str(item.get("content_type") or "").strip():
            item["content_type"] = fallback_content_type
        key = _artifact_key(item)
        if key in seen:
            return
        seen.add(key)
        out.append(item)

    for key, fallback_kind in (
        ("image_artifact", "image"),
        ("video_artifact", "video"),
        ("audio_artifact", "audio"),
        ("music_artifact", "audio"),
        ("artifact", ""),
        ("media_artifact", ""),
        ("artifact_ref", ""),
    ):
        _push(metadata.get(key), fallback_kind=fallback_kind, fallback_content_type=str(metadata.get("content_type") or ""))

    generated_media = metadata.get("generated_media")
    if isinstance(generated_media, dict):
        for key, fallback_kind in (
            ("image_artifact", "image"),
            ("video_artifact", "video"),
            ("audio_artifact", "audio"),
            ("music_artifact", "audio"),
            ("artifact", ""),
            ("artifact_ref", ""),
        ):
            _push(
                generated_media.get(key),
                fallback_kind=fallback_kind,
                fallback_content_type=str(generated_media.get("content_type") or metadata.get("content_type") or ""),
            )

    for list_key in ("attachments", "media"):
        values = metadata.get(list_key)
        if not isinstance(values, list):
            continue
        for item in values:
            _push(item)

    return out


def _local_attachment_preview_items(paths: List[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw_path in paths or []:
        path = Path(str(raw_path or "")).expanduser()
        if not str(path):
            continue
        item: Dict[str, Any] = {
            "local_path": str(path),
            "filename": path.name,
        }
        kind = _artifact_media_kind(item)
        if kind == "image":
            item["modality"] = "image"
        elif kind == "video":
            item["modality"] = "video"
        elif kind == "audio":
            item["modality"] = "audio"
        items.append(item)
    return items


def _message_key(message: Dict[str, Any]) -> str:
    role = str(message.get("role") or "").strip()
    ts = str(message.get("ts") or message.get("timestamp") or "").strip()
    content = str(message.get("content") or "")
    return f"{role}|{ts}|{content}"


def _history_message_key(message: Dict[str, Any], *, fallback_index: int) -> str:
    message_id = str(message.get("message_id") or "").strip()
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    if not message_id and isinstance(metadata, dict):
        message_id = str(metadata.get("message_id") or "").strip()
    if message_id:
        return f"id:{message_id}"
    role = str(message.get("role") or "").strip()
    ts = str(message.get("ts") or message.get("timestamp") or "").strip()
    if ts:
        return f"{role}|{ts}|{max(0, int(fallback_index))}"
    return f"{role}|index:{max(0, int(fallback_index))}"


def _visible_history_messages(messages: List[Dict[str, Any]], *, busy: bool) -> List[Dict[str, Any]]:
    del busy
    return [
        message
        for message in messages
        if isinstance(message, dict)
        and str(message.get("role") or "").strip() in {"user", "assistant"}
        and (
            str(message.get("content") or "").strip()
            or bool(_message_media_artifacts(message))
        )
    ]


def _assistant_footer_items(message: Dict[str, Any]) -> List[str]:
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    items: List[str] = []
    usage = None
    duration_ms = None
    llm_calls = None
    tool_calls = None

    if isinstance(metadata, dict):
        usage = _parse_usage_summary(metadata.get("usage"))
        stats_meta = metadata.get("_assistant_stats")
        if isinstance(stats_meta, dict):
            usage = usage or _parse_usage_summary(stats_meta.get("usage") if isinstance(stats_meta.get("usage"), dict) else stats_meta.get("tokens"))
            duration_ms = _extract_duration_ms(stats_meta)
            llm_calls = _coerce_int(stats_meta.get("llm_calls"))
            tool_calls = _coerce_int(stats_meta.get("tool_calls"))
        repl = metadata.get("_repl")
        if isinstance(repl, dict):
            repl_stats = repl.get("stats")
            if isinstance(repl_stats, dict):
                usage = usage or _parse_usage_summary(repl_stats.get("usage") if isinstance(repl_stats.get("usage"), dict) else repl_stats.get("tokens"))
                duration_ms = duration_ms if duration_ms is not None else _extract_duration_ms(repl_stats)
                llm_calls = llm_calls if llm_calls is not None else _coerce_int(repl_stats.get("llm_calls"))
                tool_calls = tool_calls if tool_calls is not None else _coerce_int(repl_stats.get("tool_calls"))

    if usage is not None:
        items.append(f"{usage['input_tokens']} in")
        items.append(f"{usage['output_tokens']} out")
    if duration_ms is not None:
        items.append(_format_duration_short(duration_ms))
    if llm_calls is not None and llm_calls > 1:
        items.append(f"{llm_calls} calls")
    if tool_calls is not None and tool_calls > 0:
        items.append(f"{tool_calls} tools")

    provider = str(metadata.get("provider") or "").strip() if isinstance(metadata, dict) else ""
    model = str(metadata.get("model") or "").strip() if isinstance(metadata, dict) else ""
    if not items and (provider or model):
        items.append(" / ".join(part for part in (provider, model) if part))
    elif len(items) < 4 and model:
        items.append(model)
    return items[:4]


DIRECT_CHAT_SYSTEM_PROMPT = (
    "You are AbstractAssistant, a concise desktop assistant. "
    "Use the conversation history and any uploaded files. "
    "When media is attached, analyze it directly or through gateway-configured multimodal routes. "
    "If something is unavailable, say so plainly."
)


class AutoSizingTextBrowser(QTextBrowser):
    def __init__(self, *, min_height: int = 34, max_height: Optional[int] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._min_height = int(min_height)
        self._max_height = int(max_height) if isinstance(max_height, int) and max_height > 0 else None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(True)
        self.document().setDocumentMargin(0)
        try:
            self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        except Exception:
            pass

    def refresh_height(self) -> None:
        width = max(280, self.viewport().width() - 6)
        self.document().setTextWidth(width)
        self.document().adjustSize()
        height = int(self.document().size().height()) + 12
        bounded = max(self._min_height, height)
        if self._max_height is not None:
            bounded = min(self._max_height, bounded)
        self.setFixedHeight(bounded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(0, self.refresh_height)


class DampedScrollArea(QScrollArea):
    def __init__(self, *, factor: float = 0.7, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._wheel_factor = max(0.1, float(factor or 0.7))

    def wheelEvent(self, event) -> None:  # noqa: N802
        bar = self.verticalScrollBar()
        if bar is None:
            super().wheelEvent(event)
            return
        try:
            pixel_delta = event.pixelDelta()
        except Exception:
            pixel_delta = None
        pixel_y = int(pixel_delta.y()) if pixel_delta is not None else 0
        if pixel_y:
            step = pixel_y * self._wheel_factor
        else:
            try:
                angle_delta = event.angleDelta()
            except Exception:
                angle_delta = None
            angle_y = int(angle_delta.y()) if angle_delta is not None else 0
            if not angle_y:
                super().wheelEvent(event)
                return
            step = (angle_y / 120.0) * float(max(1, bar.singleStep())) * self._wheel_factor
        if step > 0:
            step = max(1.0, step)
        elif step < 0:
            step = min(-1.0, step)
        bar.setValue(int(round(bar.value() - step)))
        event.accept()


class AttachmentDropFrame(QFrame):
    files_dropped = pyqtSignal(object)
    drop_active_changed = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        paths = _local_file_paths_from_mime(event.mimeData())
        if paths:
            self.drop_active_changed.emit(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        paths = _local_file_paths_from_mime(event.mimeData())
        if paths:
            self.drop_active_changed.emit(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.drop_active_changed.emit(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = _local_file_paths_from_mime(event.mimeData())
        self.drop_active_changed.emit(False)
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        event.ignore()


class AttachmentTextEdit(QTextEdit):
    files_dropped = pyqtSignal(object)
    drop_active_changed = pyqtSignal(bool)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        paths = _local_file_paths_from_mime(event.mimeData())
        if paths:
            self.drop_active_changed.emit(True)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        paths = _local_file_paths_from_mime(event.mimeData())
        if paths:
            self.drop_active_changed.emit(True)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.drop_active_changed.emit(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = _local_file_paths_from_mime(event.mimeData())
        self.drop_active_changed.emit(False)
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class AttachmentIconChip(QFrame):
    remove_requested = pyqtSignal(str)

    def __init__(self, *, path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._path = _normalize_attachment_path(path)
        self.setObjectName("attachmentIconChip")
        self.setToolTip(Path(self._path).name or self._path)
        self.setFixedSize(36, 36)
        self.setProperty("hovered", "false")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        icon_label = QLabel()
        icon_label.setObjectName("attachmentIconGlyph")
        icon_label.setAlignment(Qt.AlignCenter)
        icon = _symbol_icon(_attachment_icon_name(self._path), color=_attachment_icon_color(self._path), size=18)
        icon_label.setPixmap(icon.pixmap(18, 18))
        root.addWidget(icon_label)

        remove_button = QPushButton(self)
        remove_button.setObjectName("attachmentRemoveButton")
        remove_button.setIcon(_symbol_icon("close", color="#f8fbff", size=10))
        remove_button.setIconSize(QSize(10, 10))
        remove_button.setToolTip("Remove attachment")
        remove_button.setFixedSize(16, 16)
        remove_button.clicked.connect(lambda _checked=False: self.remove_requested.emit(self._path))
        remove_button.hide()
        self._remove_button = remove_button

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._remove_button.move(max(0, self.width() - self._remove_button.width() - 1), 1)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hovered", "true")
        self._remove_button.show()
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hovered", "false")
        self._remove_button.hide()
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()
        super().leaveEvent(event)


class AssistantHtmlActionBar(QFrame):
    def __init__(self, *, actions: List[AssistantHtmlAction], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("assistantHtmlActionBar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for action in actions:
            button = QPushButton(str(action.label or "").strip() or "Open")
            button.setObjectName("assistantHtmlActionButton")
            button.setIcon(_symbol_icon("external", color="#f6fbff", size=14))
            button.setIconSize(QSize(14, 14))
            button.setToolTip(str(action.href or "").strip())
            button.clicked.connect(lambda _checked=False, href=action.href: _open_external_href(href))
            layout.addWidget(button, 0, Qt.AlignLeft)


class MessageCard(QFrame):
    def __init__(
        self,
        *,
        message: Dict[str, Any],
        message_key: str,
        renderer: MarkdownRenderer,
        on_open_artifact,
        build_media_preview=None,
        bubble_width: int,
        on_toggle_voice=None,
        voice_state: str = "idle",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        role = str(message.get("role") or "").strip()
        is_user = role == "user"
        copy_tint = "#dfeffb" if is_user else "#8ea1b8"
        self._copy_icon = _symbol_icon("copy", color=copy_tint, size=15)
        self._copied_icon = _symbol_icon("check", color="#5ed2a1", size=15)
        self._voice_icon = _symbol_icon("speaker", color="#8ea1b8", size=15)
        self._pause_icon = _symbol_icon("pause", color="#5ed2a1", size=15)
        self._play_icon = _symbol_icon("play", color="#5ed2a1", size=15)
        self._spinner_icons = [_symbol_icon(f"spinner{idx}", color="#f0c979", size=15) for idx in range(8)]
        self._spinner_frame = 0
        self._copy_button = None
        self._voice_button = None
        self._voice_spinner = None
        self._content = str(message.get("content") or "")
        self._rendered_content, self._html_actions = _assistant_content_with_actions(self._content)
        self._role = role
        self._history_message_key = str(message_key or "").strip()
        self._media_artifacts = _message_media_artifacts(message)

        self.setObjectName("messageContainer")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)

        bubble_row = QHBoxLayout()
        bubble_row.setContentsMargins(0, 0, 0, 0)
        bubble_row.setSpacing(0)
        root.addLayout(bubble_row)

        bubble = QFrame()
        bubble.setObjectName("userBubble" if is_user else "assistantBubble")
        self._bubble = bubble
        self.set_bubble_width(bubble_width)
        try:
            bubble.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        except Exception:
            pass
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(10, 7, 10, 7)
        bubble_layout.setSpacing(4)

        if not is_user:
            header_row = QHBoxLayout()
            header_row.setContentsMargins(0, 0, 0, 0)
            header_row.setSpacing(6)
            bubble_layout.addLayout(header_row)
            header_row.addStretch(1)

            if callable(on_toggle_voice):
                voice_button = QPushButton()
                voice_button.setObjectName("messageActionButton")
                voice_button.setCheckable(True)
                voice_button.setIconSize(QSize(15, 15))
                voice_button.setFixedSize(24, 24)
                voice_button.clicked.connect(lambda: on_toggle_voice(message))
                header_row.addWidget(voice_button)
                self._voice_button = voice_button
                self._apply_voice_button_state(str(voice_state or "").strip())

            copy_button = QPushButton()
            copy_button.setObjectName("messageActionButton")
            copy_button.setIcon(self._copy_icon)
            copy_button.setIconSize(QSize(15, 15))
            copy_button.setFixedSize(24, 24)
            copy_button.setToolTip("Copy message")
            copy_button.clicked.connect(self._copy_message)
            header_row.addWidget(copy_button)
            self._copy_button = copy_button

        if self._rendered_content.strip():
            if is_user:
                label = QLabel(self._rendered_content)
                label.setObjectName("userMessageText")
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                bubble_layout.addWidget(label)
            else:
                if _render_assistant_as_plain_label(self._rendered_content):
                    label = QLabel(self._rendered_content)
                    label.setObjectName("assistantMessageTextLabel")
                    label.setWordWrap(True)
                    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    bubble_layout.addWidget(label)
                else:
                    browser = AutoSizingTextBrowser(min_height=28, max_height=None)
                    browser.setObjectName("assistantMessageText")
                    browser.setStyleSheet("background: transparent; border: none; color: #e8edf4;")
                    browser.setHtml(_assistant_html(renderer, self._rendered_content))
                    browser.refresh_height()
                    bubble_layout.addWidget(browser)

        if self._html_actions:
            bubble_layout.addWidget(AssistantHtmlActionBar(actions=self._html_actions, parent=bubble))

        preview_count = 0
        if callable(build_media_preview):
            for artifact in self._media_artifacts:
                preview_widget = build_media_preview(artifact, message)
                if preview_widget is None:
                    continue
                bubble_layout.addWidget(preview_widget)
                preview_count += 1

        if preview_count == 0:
            for artifact in self._media_artifacts:
                artifact_row = QHBoxLayout()
                artifact_row.setContentsMargins(0, 0, 0, 0)
                artifact_row.setSpacing(6)
                open_button = QPushButton(_artifact_label(artifact))
                open_button.setObjectName("artifactChip")
                open_button.setToolTip("Open media")
                open_button.clicked.connect(lambda _checked=False, art=dict(artifact): on_open_artifact(art, message))
                artifact_row.addWidget(open_button, 0, Qt.AlignLeft)
                artifact_row.addStretch(1)
                bubble_layout.addLayout(artifact_row)

        if not is_user:
            footer_items = _assistant_footer_items(message)
            if footer_items:
                footer_row = QHBoxLayout()
                footer_row.setContentsMargins(0, 0, 0, 0)
                footer_row.setSpacing(6)
                for item in footer_items:
                    chip = QLabel(item)
                    chip.setObjectName("metricChip")
                    footer_row.addWidget(chip)
                footer_row.addStretch(1)
                bubble_layout.addLayout(footer_row)

        if is_user:
            bubble_row.addStretch(1)
            bubble_row.addWidget(bubble)
        else:
            bubble_row.addWidget(bubble)
            bubble_row.addStretch(1)

        timestamp = _format_message_timestamp(message.get("ts") or message.get("timestamp"))
        if timestamp and not is_user:
            stamp_row = QHBoxLayout()
            stamp_row.setContentsMargins(4, 0, 4, 0)
            stamp_row.setSpacing(0)
            stamp = QLabel(timestamp)
            stamp.setObjectName("messageTimestamp")
            stamp_row.addWidget(stamp)
            stamp_row.addStretch(1)
            root.addLayout(stamp_row)

    def set_bubble_width(self, bubble_width: int) -> None:
        bubble = getattr(self, "_bubble", None)
        if bubble is None:
            return
        bubble.setFixedWidth(max(96, int(bubble_width or 0)))

    def sync_to_viewport_width(self, viewport_width: int) -> None:
        self.set_bubble_width(_message_bubble_width(viewport_width, role=self._role))

    def _copy_message(self) -> None:
        if self._copy_button is None:
            return
        if not _copy_to_clipboard(self._content):
            return
        self._copy_button.setIcon(self._copied_icon)
        QTimer.singleShot(900, lambda: self._copy_button.setIcon(self._copy_icon))

    def _apply_voice_button_state(self, state: str) -> None:
        button = self._voice_button
        if button is None:
            return
        normalized = str(state or "").strip().lower()
        if self._voice_spinner is not None and normalized != "synthesizing":
            self._voice_spinner.stop()
            self._voice_spinner.deleteLater()
            self._voice_spinner = None
        if normalized == "synthesizing":
            button.setChecked(False)
            button.setEnabled(False)
            button.setIcon(self._spinner_icons[self._spinner_frame % len(self._spinner_icons)])
            button.setToolTip("Synthesizing reply audio")
            if self._voice_spinner is None:
                self._voice_spinner = QTimer(self)
                self._voice_spinner.timeout.connect(self._advance_voice_spinner)
                self._voice_spinner.start(90)
            return
        button.setEnabled(True)
        if normalized == "speaking":
            button.setChecked(True)
            button.setIcon(self._pause_icon)
            button.setToolTip("Pause reply audio")
            return
        if normalized == "paused":
            button.setChecked(True)
            button.setIcon(self._play_icon)
            button.setToolTip("Resume reply audio")
            return
        button.setChecked(False)
        button.setIcon(self._voice_icon)
        button.setToolTip("Speak this reply")

    def _advance_voice_spinner(self) -> None:
        if self._voice_button is None or not self._spinner_icons:
            return
        self._spinner_frame = (self._spinner_frame + 1) % len(self._spinner_icons)
        self._voice_button.setIcon(self._spinner_icons[self._spinner_frame])


def _format_media_time(ms: int) -> str:
    total_seconds = max(0, int(ms or 0) // 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _media_display_title(*, title: str, kind: str, path: Path) -> str:
    raw = str(title or "").strip()
    candidate = raw or path.name or path.stem
    if candidate and len(candidate) >= 24 and re.fullmatch(r"[A-Fa-f0-9_-]{24,}", candidate):
        candidate = ""
    if candidate:
        return candidate
    return {
        "audio": "Audio",
        "video": "Video",
        "image": "Image",
    }.get(str(kind or "").strip().lower(), path.name or "Media")


def _probe_media_duration_ms(path: Path) -> int:
    candidate = Path(path)
    if not candidate.exists():
        return 0
    if _soundfile is not None:
        try:
            info = _soundfile.info(str(candidate))
            frames = int(getattr(info, "frames", 0) or 0)
            samplerate = int(getattr(info, "samplerate", 0) or 0)
            if frames > 0 and samplerate > 0:
                return int((frames / float(samplerate)) * 1000.0)
        except Exception:
            pass
    try:
        with wave.open(str(candidate), "rb") as handle:
            frames = int(handle.getnframes() or 0)
            rate = int(handle.getframerate() or 0)
            if frames > 0 and rate > 0:
                return int((frames / float(rate)) * 1000.0)
    except Exception:
        pass
    if shutil.which("ffprobe"):
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(candidate),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            value = str(result.stdout or "").strip()
            if value:
                seconds = float(value)
                if seconds > 0:
                    return int(seconds * 1000.0)
        except Exception:
            pass
    return 0


def _subprocess_audio_player_command(path: Path, *, offset_ms: int = 0) -> Optional[List[str]]:
    candidate = Path(path)
    offset_ms_i = max(0, int(offset_ms or 0))
    offset_s = offset_ms_i / 1000.0
    ffplay = shutil.which("ffplay")
    if ffplay:
        cmd = [ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet"]
        if offset_s > 0:
            cmd.extend(["-ss", f"{offset_s:.3f}"])
        cmd.append(str(candidate))
        return cmd
    if sys.platform == "darwin":
        afplay = shutil.which("afplay")
        if afplay and offset_ms_i <= 0:
            return [afplay, str(candidate)]
        return None
    if shutil.which("paplay") and offset_ms_i <= 0:
        return [shutil.which("paplay") or "paplay", str(candidate)]
    if shutil.which("aplay") and offset_ms_i <= 0:
        return [shutil.which("aplay") or "aplay", str(candidate)]
    if shutil.which("mpg123") and offset_ms_i <= 0:
        return [shutil.which("mpg123") or "mpg123", str(candidate)]
    return None


class InlineMediaPlayer(QFrame):
    def __init__(self, *, kind: str, path: Path, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._kind = str(kind or "").strip().lower()
        self._path = Path(path)
        self._title = _media_display_title(title=title, kind=self._kind, path=self._path)
        self._duration_ms = _probe_media_duration_ms(self._path) if self._kind in {"audio", "video"} else 0
        self._seeking = False
        self._position_ms = 0
        self._process = None
        self._process_paused = False
        self._process_offset_ms = 0
        self._process_started_at = 0.0
        self._process_backend = self._kind == "audio" and _subprocess_audio_player_command(self._path, offset_ms=0) is not None
        self._play_icon = _symbol_icon("play", color="#f4f8fc", size=14)
        self._pause_icon = _symbol_icon("pause", color="#f4f8fc", size=14)
        self._open_icon = _symbol_icon("external", color="#a9bbcf", size=13)
        self._kind_icon = _symbol_icon("file-audio" if self._kind == "audio" else "file-video", color="#77d1a8" if self._kind == "audio" else "#f0c979", size=14)
        self.setObjectName("inlineMediaPlayer")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        kind_label = QLabel()
        kind_label.setObjectName("mediaTitleIcon")
        kind_label.setPixmap(self._kind_icon.pixmap(14, 14))
        kind_label.setFixedSize(16, 16)
        title_row.addWidget(kind_label, 0, Qt.AlignVCenter)
        title_label = QLabel(self._title)
        title_label.setObjectName("mediaPreviewTitle")
        title_label.setToolTip(self._path.name or self._title)
        title_row.addWidget(title_label, 1)
        open_button = QPushButton()
        open_button.setObjectName("mediaIconButton")
        open_button.setIcon(self._open_icon)
        open_button.setIconSize(QSize(13, 13))
        open_button.setFixedSize(26, 26)
        open_button.setToolTip("Open externally")
        open_button.clicked.connect(self._open_external)
        self._open_button = open_button
        title_row.addWidget(open_button, 0)
        root.addLayout(title_row)

        self._player = None
        self._video_widget = None
        self._position_timer = QTimer(self)
        self._position_timer.timeout.connect(self._poll_process_playback)
        self.destroyed.connect(self._cleanup_playback)

        if not self._process_backend and QT_MULTIMEDIA_AVAILABLE and QMediaPlayer is not None and QMediaContent is not None:
            try:
                self._player = QMediaPlayer(self)
                self._player.setMedia(QMediaContent(QUrl.fromLocalFile(str(self._path))))
            except Exception:
                self._player = None

        if self._kind == "video":
            if self._player is not None and QVideoWidget is not None:
                video = QVideoWidget(self)
                video.setObjectName("mediaVideoPreview")
                video.setMinimumHeight(136)
                video.setMaximumHeight(176)
                root.addWidget(video)
                try:
                    self._player.setVideoOutput(video)
                except Exception:
                    pass
                self._video_widget = video
            else:
                fallback = QLabel("Video preview unavailable on this system.")
                fallback.setObjectName("mediaPreviewStatus")
                root.addWidget(fallback)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(5)

        self._play_button = QPushButton()
        self._play_button.setObjectName("mediaTransportButton")
        self._play_button.setIconSize(QSize(14, 14))
        self._play_button.setFixedSize(28, 28)
        self._play_button.clicked.connect(self._toggle_playback)
        controls.addWidget(self._play_button, 0)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setObjectName("mediaPlayerSlider")
        self._slider.setRange(0, max(0, self._duration_ms))
        self._slider.sliderPressed.connect(self._on_seek_started)
        self._slider.sliderReleased.connect(self._on_seek_finished)
        self._slider.valueChanged.connect(self._on_slider_value_changed)
        controls.addWidget(self._slider, 1)

        self._time_label = QLabel("")
        self._time_label.setObjectName("mediaTransportMeta")
        controls.addWidget(self._time_label, 0)
        root.addLayout(controls)

        if self._player is not None:
            try:
                self._player.durationChanged.connect(self._on_duration_changed)
                self._player.positionChanged.connect(self._on_position_changed)
                self._player.stateChanged.connect(self._on_state_changed)
                status_changed = getattr(self._player, "mediaStatusChanged", None)
                if status_changed is not None:
                    status_changed.connect(self._on_media_status_changed)
            except Exception:
                pass
        self._slider.setEnabled(self._duration_ms > 0)
        self._apply_transport_button_state()
        self._update_time_label(0)

    def _open_external(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._path)))

    def _toggle_playback(self) -> None:
        if self._process_backend:
            self._toggle_process_playback()
            return
        player = self._player
        if player is None:
            self._open_external()
            return
        try:
            if player.state() == QMediaPlayer.PlayingState:
                player.pause()
            else:
                player.play()
        except Exception:
            self._open_external()

    def _on_seek_started(self) -> None:
        self._seeking = True

    def _on_seek_finished(self) -> None:
        self._seeking = False
        target = max(0, int(self._slider.value()))
        if self._process_backend:
            was_playing = self._process is not None and not self._process_paused
            self._stop_process_playback(reset=False, keep_position=target)
            self._position_ms = target
            self._slider.setValue(target)
            self._update_time_label(target)
            self._apply_transport_button_state()
            if was_playing:
                self._start_process_playback(offset_ms=target)
            return
        player = self._player
        if player is None:
            return
        try:
            player.setPosition(target)
        except Exception:
            return

    def _on_slider_value_changed(self, value: int) -> None:
        if self._seeking:
            self._update_time_label(int(value))

    def _on_duration_changed(self, duration: int) -> None:
        incoming = max(0, int(duration or 0))
        if incoming > 0:
            self._duration_ms = incoming
        self._slider.setRange(0, self._duration_ms)
        self._slider.setEnabled(self._duration_ms > 0)
        self._update_time_label(int(self._slider.value()))

    def _on_position_changed(self, position: int) -> None:
        position_ms = max(0, int(position or 0))
        self._position_ms = position_ms
        if not self._seeking:
            self._slider.setValue(position_ms)
        self._update_time_label(position_ms)

    def _on_state_changed(self, _state: int) -> None:
        self._apply_transport_button_state()

    def _on_media_status_changed(self, _status: int) -> None:
        player = self._player
        if player is None:
            return
        status_fn = getattr(player, "mediaStatus", None)
        if not callable(status_fn):
            return
        try:
            status = player.mediaStatus()
        except Exception:
            return
        invalid_status = getattr(QMediaPlayer, "InvalidMedia", None)
        if invalid_status is not None and status == invalid_status:
            self._play_button.setEnabled(False)
            self._time_label.setText("Unsupported")
            return
        self._apply_transport_button_state()

    def _toggle_process_playback(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            if self._process_paused:
                self._resume_process_playback()
            else:
                self._pause_process_playback()
            return
        start_at = self._position_ms
        if self._duration_ms > 0 and start_at >= max(0, self._duration_ms - 200):
            start_at = 0
        self._start_process_playback(offset_ms=start_at)

    def _start_process_playback(self, *, offset_ms: int) -> None:
        command = _subprocess_audio_player_command(self._path, offset_ms=offset_ms)
        if not command:
            self._open_external()
            return
        self._stop_process_playback(reset=False, keep_position=offset_ms)
        try:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            self._open_external()
            return
        self._process = process
        self._process_paused = False
        self._process_offset_ms = max(0, int(offset_ms or 0))
        self._process_started_at = time.monotonic()
        self._position_ms = self._process_offset_ms
        self._position_timer.start(120)
        self._apply_transport_button_state()
        self._update_time_label(self._position_ms)

    def _pause_process_playback(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            self._position_ms = self._current_process_position_ms()
            process.send_signal(signal.SIGSTOP)
            self._process_paused = True
        except Exception:
            self._stop_process_playback(reset=False)
            return
        self._apply_transport_button_state()
        self._update_time_label(self._position_ms)

    def _resume_process_playback(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            self._start_process_playback(offset_ms=self._position_ms)
            return
        try:
            process.send_signal(signal.SIGCONT)
            self._process_paused = False
            self._process_offset_ms = self._position_ms
            self._process_started_at = time.monotonic()
        except Exception:
            self._start_process_playback(offset_ms=self._position_ms)
            return
        self._apply_transport_button_state()

    def _stop_process_playback(self, *, reset: bool, keep_position: Optional[int] = None) -> None:
        process = self._process
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=0.2)
                    except Exception:
                        process.kill()
            except Exception:
                pass
        self._process = None
        self._position_timer.stop()
        self._process_paused = False
        self._process_started_at = 0.0
        self._process_offset_ms = 0
        if keep_position is not None:
            self._position_ms = max(0, int(keep_position))
        elif reset:
            self._position_ms = 0
        self._apply_transport_button_state()

    def _current_process_position_ms(self) -> int:
        if self._process is None:
            return max(0, int(self._position_ms or 0))
        if self._process_paused:
            return max(0, int(self._position_ms or 0))
        elapsed_ms = int((time.monotonic() - float(self._process_started_at or time.monotonic())) * 1000.0)
        position = max(0, int(self._process_offset_ms or 0) + elapsed_ms)
        if self._duration_ms > 0:
            position = min(position, self._duration_ms)
        return position

    def _poll_process_playback(self) -> None:
        process = self._process
        if process is None:
            self._position_timer.stop()
            return
        if process.poll() is not None:
            self._stop_process_playback(reset=True)
            self._slider.setValue(0)
            self._update_time_label(0)
            return
        if self._process_paused:
            return
        position = self._current_process_position_ms()
        self._position_ms = position
        if not self._seeking:
            self._slider.setValue(position)
        self._update_time_label(position)

    def _apply_transport_button_state(self) -> None:
        if self._process_backend:
            self._play_button.setEnabled(True)
            if self._process is not None and self._process.poll() is None and not self._process_paused:
                self._play_button.setIcon(self._pause_icon)
                self._play_button.setToolTip("Pause audio")
            else:
                self._play_button.setIcon(self._play_icon)
                self._play_button.setToolTip("Play audio")
            return
        player = self._player
        if player is None:
            self._play_button.setEnabled(False)
            self._play_button.setIcon(self._play_icon)
            self._play_button.setToolTip("Playback unavailable")
            return
        try:
            is_playing = player.state() == QMediaPlayer.PlayingState
        except Exception:
            is_playing = False
        self._play_button.setEnabled(True)
        self._play_button.setIcon(self._pause_icon if is_playing else self._play_icon)
        self._play_button.setToolTip("Pause audio" if is_playing else "Play audio")

    def _update_time_label(self, position_ms: int) -> None:
        total = _format_media_time(self._duration_ms) if self._duration_ms > 0 else "--:--"
        self._time_label.setText(f"{_format_media_time(position_ms)} / {total}")

    def _cleanup_playback(self, *_args) -> None:
        try:
            self._position_timer.stop()
        except Exception:
            pass
        process = self._process
        self._process = None
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=0.2)
                    except Exception:
                        process.kill()
            except Exception:
                pass
        player = self._player
        if player is not None:
            try:
                player.stop()
            except Exception:
                pass


class ArtifactPreviewCard(QFrame):
    path_ready = pyqtSignal(str)
    preview_failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        artifact: Dict[str, Any],
        resolve_path: Callable[[], Path],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._artifact = dict(artifact)
        self._resolve_path = resolve_path
        self._media_kind = _artifact_media_kind(self._artifact)
        self._title = _artifact_label(self._artifact)
        self._local_path: Optional[Path] = None

        self.setObjectName("mediaPreviewCard")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)
        root.addLayout(self._content_layout)

        self._status_label = QLabel("Loading preview…")
        self._status_label.setObjectName("mediaPreviewStatus")
        self._content_layout.addWidget(self._status_label)

        self.path_ready.connect(self._on_path_ready)
        self.preview_failed.connect(self._on_preview_failed)
        threading.Thread(target=self._load_preview_path, daemon=True).start()

    def _load_preview_path(self) -> None:
        try:
            path = self._resolve_path()
        except Exception as exc:
            try:
                self.preview_failed.emit(str(exc))
            except Exception:
                pass
            return
        try:
            self.path_ready.emit(str(path))
        except Exception:
            pass

    def _clear_content(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_path_ready(self, raw_path: str) -> None:
        path = Path(str(raw_path or "")).expanduser()
        self._local_path = path
        self._clear_content()

        if self._media_kind == "image":
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                self._on_preview_failed("Image preview unavailable.")
                return
            button = QPushButton()
            button.setObjectName("mediaImageButton")
            button.setToolTip(str(path))
            button.clicked.connect(self._open_external)
            button.setMinimumHeight(112)
            button.setMaximumHeight(156)
            scaled = pixmap.scaled(256, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            button.setIcon(QIcon(scaled))
            button.setIconSize(scaled.size())
            self._content_layout.addWidget(button)
            return

        if self._media_kind in {"audio", "video"}:
            player = InlineMediaPlayer(kind=self._media_kind, path=path, title=self._title, parent=self)
            self._content_layout.addWidget(player)
            return

        self._on_preview_failed("Preview unavailable. Open the file instead.")

    def _on_preview_failed(self, message: str) -> None:
        self._clear_content()
        label = QLabel(str(message or "Preview unavailable."))
        label.setObjectName("mediaPreviewStatus")
        self._content_layout.addWidget(label)
        open_button = QPushButton("Open")
        open_button.setObjectName("mediaOpenButton")
        open_button.clicked.connect(self._open_external)
        self._content_layout.addWidget(open_button, 0, Qt.AlignLeft)

    def _open_external(self) -> None:
        if self._local_path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._local_path)))


class ThinkingIndicatorCard(QFrame):
    def __init__(self, *, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("thinkingIndicator")
        self._frames = ("● ○ ○", "○ ● ○", "○ ○ ●")
        self._frame_index = 0

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bubble = QFrame()
        bubble.setObjectName("assistantBubble")
        bubble.setMaximumWidth(96)
        bubble.setMinimumWidth(72)
        bubble.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 10, 14, 10)
        bubble_layout.setSpacing(0)

        self._label = QLabel(self._frames[0])
        self._label.setObjectName("thinkingDots")
        self._label.setAlignment(Qt.AlignCenter)
        bubble_layout.addWidget(self._label)

        root.addWidget(bubble)
        root.addStretch(1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(240)

    def _advance(self) -> None:
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self._label.setText(self._frames[self._frame_index])


class ToolApprovalDialog(QDialog):
    def __init__(self, *, tool_calls: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Approve tools")
        self.resize(620, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        headline = QLabel("The assistant wants to run tools for this request.")
        headline.setWordWrap(True)
        headline.setObjectName("dialogTitle")
        root.addWidget(headline)

        hint = QLabel("Review this batch. Allow or deny applies only to the current request.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(_tool_calls_text(tool_calls))
        root.addWidget(details, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        deny = QPushButton("Deny")
        deny.clicked.connect(self.reject)
        buttons.addWidget(deny)
        allow = QPushButton("Allow")
        allow.clicked.connect(self.accept)
        buttons.addWidget(allow)
        root.addLayout(buttons)


class ToolSettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    def __init__(self, *, controller: AssistantV2Controller, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._rows: Dict[str, Dict[str, Any]] = {}
        self.setWindowTitle("Tools")
        self.resize(720, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Tools")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Choose how this Mac pre-approves or blocks tool requests before they reach the gateway. "
            "These settings can only narrow behavior on this device; they cannot grant more than the gateway allows."
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.mode_note = QLabel("")
        self.mode_note.setObjectName("statusNote")
        self.mode_note.setWordWrap(True)
        root.addWidget(self.mode_note)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter tools")
        self.search_edit.textChanged.connect(self._apply_filter)
        root.addWidget(self.search_edit)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(self.scroll, 1)

        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.scroll.setWidget(self.list_host)

        self.feedback = QLabel("")
        self.feedback.setObjectName("feedbackNote")
        self.feedback.setWordWrap(True)
        root.addWidget(self.feedback)

        buttons = QHBoxLayout()
        self.reset_button = QPushButton("Use Safe Defaults")
        self.reset_button.setObjectName("secondaryButton")
        self.reset_button.clicked.connect(self._reset_defaults)
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        cancel = QPushButton("Close")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self._apply_styles()
        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #0f141b;
                color: #e8edf4;
                font-family: "SF Pro Text", "Helvetica Neue", Arial;
            }
            QLabel#dialogTitle {
                color: #f6f8fb;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#dialogSubtitle {
                color: #9aabbf;
                font-size: 13px;
            }
            QLabel#statusNote {
                color: #b8c9dc;
                background: rgba(121, 199, 255, 0.08);
                border: 1px solid rgba(121, 199, 255, 0.18);
                border-radius: 10px;
                padding: 8px 10px;
            }
            QLabel#feedbackNote {
                color: #8bd8b1;
                font-size: 12px;
                font-weight: 600;
            }
            QLineEdit, QComboBox {
                min-height: 34px;
                border-radius: 10px;
                border: 1px solid rgba(166, 187, 214, 0.18);
                background: #171d25;
                color: #e8edf4;
                padding: 6px 10px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: rgba(121, 199, 255, 0.45);
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QFrame#toolRow {
                background: #151b23;
                border: 1px solid rgba(166, 187, 214, 0.14);
                border-radius: 12px;
            }
            QLabel#toolIcon {
                min-width: 28px;
                color: #7ec6ff;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#toolName {
                color: #edf2f8;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#toolMeta {
                color: #89a0b8;
                font-size: 11px;
            }
            QPushButton {
                min-height: 34px;
                border-radius: 10px;
                padding: 7px 13px;
                border: 1px solid rgba(166, 187, 214, 0.18);
                background: #1c2430;
                color: #f3f7fb;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #243041;
            }
            QPushButton#secondaryButton {
                background: #171d25;
                color: #dfe8f3;
                border-color: rgba(166, 187, 214, 0.16);
            }
            """
        )

    def _toolset_icon(self, toolset: str) -> str:
        mapping = {
            "files": "⌘",
            "web": "◎",
            "system": "›",
            "comms": "✉",
            "smartnote": "✦",
        }
        return mapping.get(str(toolset or "").strip().lower(), "•")

    def _tool_mode_text(self, mode: str) -> str:
        mode_s = str(mode or "approval").strip().lower()
        if mode_s in {"approval", "local_approval", "local-approval"}:
            return "Gateway tool mode: approval. The gateway may auto-run safe tools and pause risky tools. This Mac can further restrict or pre-approve requests."
        if mode_s in {"local", "local_all", "local-all"}:
            return "Gateway tool mode: local. This deployment can execute tools directly, and this Mac can still block or pre-approve before submission."
        if mode_s in {"passthrough"}:
            return "Gateway tool mode: passthrough. The gateway forwards tool requests downstream after this Mac's local gating step."
        if mode_s in {"delegated", "delegate", "job"}:
            return "Gateway tool mode: delegated. Tool calls wait for external executors after this Mac's local gating step."
        return "Gateway tool mode was not reported. This Mac can still restrict tools, but unavailable gateway policy will fail closed."

    def refresh(self) -> None:
        inventory = self._controller.tool_inventory()
        items = inventory.get("items") if isinstance(inventory, dict) else []
        self.mode_note.setText(self._tool_mode_text(str((inventory or {}).get("tool_mode") or "")))
        self.feedback.clear()

        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._rows = {}
        for item in items or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            row = QFrame()
            row.setObjectName("toolRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(10)

            icon = QLabel(self._toolset_icon(str(item.get("toolset") or "")))
            icon.setObjectName("toolIcon")
            icon.setAlignment(Qt.AlignTop)
            layout.addWidget(icon)

            text_col = QVBoxLayout()
            text_col.setSpacing(3)
            layout.addLayout(text_col, 1)

            title = QLabel(name)
            title.setObjectName("toolName")
            text_col.addWidget(title)

            desc_parts = [str(item.get("description") or "").strip(), str(item.get("when_to_use") or "").strip()]
            desc = " ".join(part for part in desc_parts if part).strip() or "No description available."
            meta = QLabel(desc)
            meta.setObjectName("toolMeta")
            meta.setWordWrap(True)
            text_col.addWidget(meta)

            policy_default = str(item.get("policy_default") or "ask").strip().lower()
            default_hint = QLabel(f"Default: {'Approve' if policy_default == 'approve' else 'Ask'}")
            default_hint.setObjectName("toolMeta")
            text_col.addWidget(default_hint)

            combo = QComboBox()
            combo.addItem("Disabled", "disabled")
            combo.addItem("Approve", "approve")
            combo.addItem("Ask", "ask")
            current_mode = str(item.get("selected_mode") or "ask").strip().lower()
            index = combo.findData(current_mode)
            combo.setCurrentIndex(index if index >= 0 else 2)
            layout.addWidget(combo)

            self.list_layout.addWidget(row)
            searchable = f"{name}\n{desc}\n{item.get('toolset') or ''}".lower()
            self._rows[name] = {"row": row, "combo": combo, "default_mode": str(item.get("default_mode") or "ask"), "search": searchable}

        self.list_layout.addStretch(1)
        self._apply_filter()
        note = str((inventory or {}).get("note") or "").strip()
        if note:
            self.feedback.setText(note)

    def _apply_filter(self) -> None:
        query = str(self.search_edit.text() or "").strip().lower()
        for info in self._rows.values():
            hay = str(info.get("search") or "")
            info["row"].setVisible(not query or query in hay)

    def _reset_defaults(self) -> None:
        for info in self._rows.values():
            combo = info.get("combo")
            default_mode = str(info.get("default_mode") or "ask").strip().lower()
            if combo is None:
                continue
            idx = combo.findData(default_mode)
            combo.setCurrentIndex(idx if idx >= 0 else 2)
        self.feedback.setText("Restored safe defaults in this window.")

    def _save(self) -> None:
        statuses: Dict[str, str] = {}
        for name, info in self._rows.items():
            combo = info.get("combo")
            if combo is None:
                continue
            statuses[name] = str(combo.currentData() or "ask").strip().lower()
        self._controller.save_tool_preferences(statuses)
        self.feedback.setText("Saved tool defaults on this device.")
        self.settings_saved.emit()


class SettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    def __init__(self, *, controller: AssistantV2Controller, apply_hotkey, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._apply_hotkey = apply_hotkey
        self._route_rows: List[CapabilityRouteRow] = []
        self.setWindowTitle("Assistant Settings")
        self.resize(860, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title = QLabel("Assistant Settings")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        subtitle = QLabel("Gateway defaults stay on the gateway. Device preferences stay on this Mac.")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.settings_tabs = QTabWidget()
        self.settings_tabs.setObjectName("settingsTabs")
        root.addWidget(self.settings_tabs, 1)

        connection_tab = QWidget()
        connection_root = QVBoxLayout(connection_tab)
        connection_root.setContentsMargins(0, 0, 0, 0)
        connection_root.setSpacing(12)
        self.settings_tabs.addTab(connection_tab, "Connection")

        connection_intro = QLabel("Choose how this desktop app signs into the gateway. These settings stay on this device.")
        connection_intro.setObjectName("sectionHelp")
        connection_intro.setWordWrap(True)
        connection_root.addWidget(connection_intro)

        connection_card = QFrame()
        connection_card.setObjectName("settingsCard")
        connection_stack = QVBoxLayout(connection_card)
        connection_stack.setContentsMargins(18, 18, 18, 18)
        connection_stack.setSpacing(14)
        connection_root.addWidget(connection_card)

        connection_form = QGridLayout()
        connection_form.setHorizontalSpacing(12)
        connection_form.setVerticalSpacing(10)
        connection_form.setColumnStretch(1, 1)
        connection_stack.addLayout(connection_form)

        connection_form.addWidget(QLabel("Gateway URL"), 0, 0)
        self.gateway_url_edit = QLineEdit()
        self.gateway_url_edit.setPlaceholderText(DEFAULT_GATEWAY_URL)
        connection_form.addWidget(self.gateway_url_edit, 0, 1)

        connection_form.addWidget(QLabel("Sign-in mode"), 1, 0)
        self.auth_mode_combo = QComboBox()
        self.auth_mode_combo.addItem("Bearer token", "bearer")
        self.auth_mode_combo.addItem("Gateway session", "session")
        self.auth_mode_combo.currentIndexChanged.connect(self._refresh_connection_fields)
        connection_form.addWidget(self.auth_mode_combo, 1, 1)

        self.bearer_token_label = QLabel("Bearer token")
        connection_form.addWidget(self.bearer_token_label, 2, 0)
        self.bearer_token_edit = QLineEdit()
        self.bearer_token_edit.setEchoMode(QLineEdit.Password)
        self.bearer_token_edit.setPlaceholderText("Shared gateway token")
        connection_form.addWidget(self.bearer_token_edit, 2, 1)

        self.gateway_user_label = QLabel("Gateway user")
        connection_form.addWidget(self.gateway_user_label, 3, 0)
        self.gateway_user_edit = QLineEdit()
        self.gateway_user_edit.setPlaceholderText("admin")
        connection_form.addWidget(self.gateway_user_edit, 3, 1)

        self.gateway_user_token_label = QLabel("Gateway user token")
        connection_form.addWidget(self.gateway_user_token_label, 4, 0)
        self.gateway_user_token_edit = QLineEdit()
        self.gateway_user_token_edit.setEchoMode(QLineEdit.Password)
        self.gateway_user_token_edit.setPlaceholderText("Paste the gateway user token")
        connection_form.addWidget(self.gateway_user_token_edit, 4, 1)

        self.remember_session = QCheckBox("Keep the gateway session after this app closes")
        connection_form.addWidget(self.remember_session, 5, 0, 1, 2)

        self.connection_status = QLabel("")
        self.connection_status.setWordWrap(True)
        self.connection_status.setObjectName("statusNote")
        connection_stack.addWidget(self.connection_status)

        self.connection_feedback = QLabel("")
        self.connection_feedback.setWordWrap(True)
        self.connection_feedback.setObjectName("feedbackNote")
        connection_stack.addWidget(self.connection_feedback)

        connection_buttons = QHBoxLayout()
        self.connection_refresh_button = QPushButton("Reload status")
        self.connection_refresh_button.setObjectName("secondaryButton")
        self.connection_refresh_button.clicked.connect(self._refresh_connection_status)
        connection_buttons.addWidget(self.connection_refresh_button)
        self.connection_save_button = QPushButton("Connect")
        self.connection_save_button.clicked.connect(self._save_connection)
        connection_buttons.addWidget(self.connection_save_button)
        self.connection_logout_button = QPushButton("Sign out")
        self.connection_logout_button.setObjectName("secondaryButton")
        self.connection_logout_button.clicked.connect(self._clear_connection)
        connection_buttons.addWidget(self.connection_logout_button)
        connection_buttons.addStretch(1)
        connection_stack.addLayout(connection_buttons)
        connection_root.addStretch(1)

        routes_tab = QWidget()
        self._routes_tab = routes_tab
        routes_root = QVBoxLayout(routes_tab)
        routes_root.setContentsMargins(0, 0, 0, 0)
        routes_root.setSpacing(12)
        self.settings_tabs.addTab(routes_tab, "Gateway Defaults")

        capability_help = QLabel(
            "These defaults are saved on the connected gateway and affect this assistant and any other thin client using the same gateway account."
        )
        capability_help.setObjectName("sectionHelp")
        capability_help.setWordWrap(True)
        routes_root.addWidget(capability_help)

        self.voice_shortcut_card = QFrame()
        self.voice_shortcut_card.setObjectName("settingsCard")
        voice_shortcut_layout = QHBoxLayout(self.voice_shortcut_card)
        voice_shortcut_layout.setContentsMargins(18, 16, 18, 16)
        voice_shortcut_layout.setSpacing(14)
        voice_shortcut_text = QVBoxLayout()
        voice_shortcut_text.setSpacing(4)
        voice_shortcut_layout.addLayout(voice_shortcut_text, 1)
        voice_shortcut_title = QLabel("Voice Output")
        voice_shortcut_title.setObjectName("routeLabel")
        voice_shortcut_text.addWidget(voice_shortcut_title)
        self.voice_shortcut_summary = QLabel("")
        self.voice_shortcut_summary.setObjectName("routeHelp")
        self.voice_shortcut_summary.setWordWrap(True)
        voice_shortcut_text.addWidget(self.voice_shortcut_summary)
        self.voice_shortcut_button = QPushButton("Open Voice Output")
        self.voice_shortcut_button.setObjectName("secondaryButton")
        self.voice_shortcut_button.clicked.connect(lambda: self._focus_route("output.voice"))
        voice_shortcut_layout.addWidget(self.voice_shortcut_button, 0, Qt.AlignTop)
        routes_root.addWidget(self.voice_shortcut_card)

        route_card = QFrame()
        route_card.setObjectName("settingsCard")
        route_stack = QVBoxLayout(route_card)
        route_stack.setContentsMargins(18, 18, 18, 18)
        route_stack.setSpacing(14)
        routes_root.addWidget(route_card, 1)

        panel = QHBoxLayout()
        panel.setSpacing(16)
        route_stack.addLayout(panel, 1)

        self.route_list = QListWidget()
        self.route_list.setMinimumWidth(230)
        self.route_list.currentRowChanged.connect(self._load_selected_route)
        panel.addWidget(self.route_list, 1)

        right = QVBoxLayout()
        right.setSpacing(10)
        panel.addLayout(right, 2)

        self.route_label = QLabel("")
        self.route_label.setObjectName("routeLabel")
        right.addWidget(self.route_label)

        self.route_help = QLabel("")
        self.route_help.setWordWrap(True)
        self.route_help.setObjectName("routeHelp")
        right.addWidget(self.route_help)

        self.show_advanced = QCheckBox("Show advanced route fields")
        self.show_advanced.stateChanged.connect(self._apply_advanced_visibility)
        right.addWidget(self.show_advanced)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.setColumnStretch(1, 1)
        right.addLayout(form)

        form.addWidget(QLabel("Provider"), 0, 0)
        self.provider_combo = QComboBox()
        self.provider_combo.setMinimumWidth(260)
        self.provider_combo.currentIndexChanged.connect(self._refresh_models_for_provider)
        form.addWidget(self.provider_combo, 0, 1)

        form.addWidget(QLabel("Model"), 1, 0)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(260)
        form.addWidget(self.model_combo, 1, 1)

        self.base_url_label = QLabel("Provider base URL")
        form.addWidget(self.base_url_label, 2, 0)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("Optional provider-specific override")
        self.base_url_edit.editingFinished.connect(self._reload_catalogs_for_base_url)
        form.addWidget(self.base_url_edit, 2, 1)

        self.options_label = QLabel("Advanced options JSON")
        form.addWidget(self.options_label, 3, 0)
        self.options_edit = QPlainTextEdit()
        self.options_edit.setPlaceholderText('{"key":"value"}')
        self.options_edit.setFixedHeight(90)
        form.addWidget(self.options_edit, 3, 1)

        self.voice_label = QLabel("Voice / Profile")
        form.addWidget(self.voice_label, 4, 0)
        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        self.voice_combo.setMinimumWidth(260)
        form.addWidget(self.voice_combo, 4, 1)

        self.resolution_label = QLabel("Upscale resolution")
        form.addWidget(self.resolution_label, 5, 0)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("2x", "2x")
        self.resolution_combo.addItem("4x", "4x")
        self.resolution_combo.addItem("auto", "auto")
        form.addWidget(self.resolution_combo, 5, 1)

        self.route_state = QLabel("")
        self.route_state.setWordWrap(True)
        self.route_state.setObjectName("statusNote")
        right.addWidget(self.route_state)

        self.route_feedback = QLabel("")
        self.route_feedback.setWordWrap(True)
        self.route_feedback.setObjectName("feedbackNote")
        right.addWidget(self.route_feedback)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Reload From Gateway")
        self.refresh_button.setObjectName("secondaryButton")
        self.refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_button)
        self.reset_button = QPushButton("Use Gateway Default")
        self.reset_button.setObjectName("secondaryButton")
        self.reset_button.clicked.connect(self._clear_route)
        buttons.addWidget(self.reset_button)
        self.save_button = QPushButton("Save On Gateway")
        self.save_button.clicked.connect(self._save_route)
        buttons.addWidget(self.save_button)
        buttons.addStretch(1)
        right.addLayout(buttons)
        routes_root.addStretch(1)

        prefs_tab = QWidget()
        prefs_root = QVBoxLayout(prefs_tab)
        prefs_root.setContentsMargins(0, 0, 0, 0)
        prefs_root.setSpacing(12)
        self.settings_tabs.addTab(prefs_tab, "This Device")

        prefs_help = QLabel("These controls affect only this tray app on this device.")
        prefs_help.setObjectName("sectionHelp")
        prefs_help.setWordWrap(True)
        prefs_root.addWidget(prefs_help)

        prefs_card = QFrame()
        prefs_card.setObjectName("settingsCard")
        prefs_stack = QVBoxLayout(prefs_card)
        prefs_stack.setContentsMargins(18, 18, 18, 18)
        prefs_stack.setSpacing(14)
        prefs_root.addWidget(prefs_card)

        prefs_layout = QGridLayout()
        prefs_layout.setHorizontalSpacing(12)
        prefs_layout.setVerticalSpacing(10)
        prefs_layout.setColumnStretch(1, 1)
        prefs_stack.addLayout(prefs_layout)

        self.hotkey_enabled = QCheckBox("Enable global summon shortcut")
        prefs_layout.addWidget(self.hotkey_enabled, 0, 0, 1, 2)
        prefs_layout.addWidget(QLabel("Shortcut"), 1, 0)
        self.hotkey_edit = QLineEdit()
        prefs_layout.addWidget(self.hotkey_edit, 1, 1)

        self.auto_speak = QCheckBox("Speak replies automatically")
        prefs_layout.addWidget(self.auto_speak, 2, 0, 1, 2)

        prefs_layout.addWidget(QLabel("Popover width"), 3, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(420, 760)
        prefs_layout.addWidget(self.width_spin, 3, 1)

        prefs_layout.addWidget(QLabel("Expanded height"), 4, 0)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(240, 520)
        prefs_layout.addWidget(self.height_spin, 4, 1)

        prefs_layout.addWidget(QLabel("Screen edge gap"), 5, 0)
        self.bottom_offset_spin = QSpinBox()
        self.bottom_offset_spin.setRange(0, 80)
        prefs_layout.addWidget(self.bottom_offset_spin, 5, 1)

        self.prefs_feedback = QLabel("")
        self.prefs_feedback.setWordWrap(True)
        self.prefs_feedback.setObjectName("feedbackNote")
        prefs_stack.addWidget(self.prefs_feedback)

        bottom = QHBoxLayout()
        prefs_stack.addLayout(bottom)
        bottom.addStretch(1)
        prefs_save = QPushButton("Save On This Device")
        prefs_save.clicked.connect(self._save_preferences)
        bottom.addWidget(prefs_save)

        prefs_root.addStretch(1)

        self._apply_styles()
        self.refresh()

    def refresh(self) -> None:
        selected_key = ""
        row = self._active_row()
        if row is not None:
            selected_key = row.key
        self._load_connection_preferences()
        self._refresh_connection_status()
        try:
            self._route_rows = self._controller.route_rows()
        except Exception as exc:
            self._route_rows = []
            self.route_feedback.setText(str(exc))
        self.route_list.clear()
        for row in self._route_rows:
            item = QListWidgetItem(row.label)
            self.route_list.addItem(item)
        if self._route_rows:
            selected_index = 0
            if selected_key:
                for idx, item in enumerate(self._route_rows):
                    if item.key == selected_key:
                        selected_index = idx
                        break
            self.route_list.setCurrentRow(selected_index)
        else:
            self.route_label.setText("No gateway routes available")
            self.route_help.setText("Connect to a gateway account that can read capability defaults.")
            self.route_state.setText("")
            self._set_route_editor_enabled(False)
        self._refresh_voice_shortcut_summary()
        prefs = self._controller.preferences
        self.hotkey_enabled.setChecked(bool(prefs.hotkey_enabled))
        self.hotkey_edit.setText(str(prefs.hotkey_sequence or "cmd+shift+space"))
        self.auto_speak.setChecked(bool(prefs.auto_speak))
        self.width_spin.setValue(int(prefs.window_width))
        self.height_spin.setValue(int(prefs.window_height))
        self.bottom_offset_spin.setValue(int(prefs.bottom_offset))

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #0f141c;
                color: #e8edf4;
                font-family: "SF Pro Text", "Helvetica Neue", Arial;
            }
            QLabel#dialogTitle {
                font-size: 24px;
                font-weight: 700;
                color: #f6f8fb;
            }
            QLabel#dialogSubtitle, QLabel#sectionHelp, QLabel#routeHelp {
                color: #9aa8bb;
                font-size: 13px;
            }
            QFrame#settingsCard {
                background: #161c25;
                border: 1px solid rgba(166, 187, 214, 0.14);
                border-radius: 18px;
            }
            QTabWidget::pane {
                border: none;
                margin-top: 10px;
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 0.05);
                color: #9aa8bb;
                border: 1px solid transparent;
                border-radius: 12px;
                padding: 9px 14px;
                margin-right: 8px;
                min-width: 120px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #1d2632;
                color: #f6f8fb;
                border-color: rgba(166, 187, 214, 0.18);
            }
            QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QSpinBox {
                background: #111821;
                color: #e8edf4;
                border: 1px solid rgba(166, 187, 214, 0.18);
                border-radius: 12px;
                padding: 8px 10px;
            }
            QLineEdit, QComboBox, QSpinBox {
                min-height: 38px;
            }
            QPlainTextEdit {
                padding: 10px 12px;
            }
            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QListWidget:focus, QSpinBox:focus {
                border-color: rgba(83, 198, 145, 0.52);
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView, QListWidget {
                background: #111821;
                selection-background-color: #243041;
                selection-color: #f6f8fb;
            }
            QPushButton {
                min-height: 38px;
                border-radius: 12px;
                padding: 7px 14px;
                border: 1px solid rgba(83, 198, 145, 0.28);
                background: #2e8b63;
                color: #f9fffc;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #37a272;
            }
            QPushButton:pressed {
                background: #236749;
            }
            QPushButton#secondaryButton {
                background: #141b24;
                color: #dfe7f2;
                border-color: rgba(166, 187, 214, 0.16);
            }
            QPushButton#secondaryButton:hover {
                background: #1d2632;
            }
            QPushButton#secondaryButton:pressed {
                background: #121922;
            }
            QListWidget {
                padding: 8px;
            }
            QLabel#routeLabel {
                font-size: 22px;
                font-weight: 700;
                color: #f6f8fb;
            }
            QLabel#statusNote {
                color: #9aa8bb;
                font-size: 12px;
            }
            QLabel#feedbackNote {
                color: #73d3a8;
                font-size: 12px;
                font-weight: 600;
            }
            QCheckBox {
                spacing: 8px;
            }
            """
        )

    def _load_connection_preferences(self) -> None:
        connection = self._controller.current_connection()
        self.gateway_url_edit.setText(str(connection.base_url or DEFAULT_GATEWAY_URL))
        self._set_combo_value(self.auth_mode_combo, str(connection.auth_mode or "bearer"))
        self.bearer_token_edit.setText(str(connection.auth_token or ""))
        self.gateway_user_edit.setText(str(connection.user_id or ""))
        self.remember_session.setChecked(bool(connection.remember_session))
        self.gateway_user_token_edit.clear()
        self._refresh_connection_fields()

    def _refresh_connection_fields(self) -> None:
        auth_mode = str(self.auth_mode_combo.currentData() or "bearer")
        is_bearer = auth_mode == "bearer"
        self.bearer_token_label.setVisible(is_bearer)
        self.bearer_token_edit.setVisible(is_bearer)
        self.gateway_user_label.setVisible(not is_bearer)
        self.gateway_user_edit.setVisible(not is_bearer)
        self.gateway_user_token_label.setVisible(not is_bearer)
        self.gateway_user_token_edit.setVisible(not is_bearer)
        self.remember_session.setVisible(not is_bearer)

    def _refresh_connection_status(self) -> None:
        payload = self._controller.connection_status()
        if not isinstance(payload, dict) or payload.get("ok") is False:
            detail = str(payload.get("detail") or "Not connected yet.").strip() if isinstance(payload, dict) else "Not connected yet."
            self.connection_status.setText(f"Status: {detail}")
            return
        principal = payload.get("principal") if isinstance(payload.get("principal"), dict) else {}
        auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else {}
        routing = payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
        user_id = str(principal.get("user_id") or "unknown").strip()
        tenant_id = str(principal.get("tenant_id") or "").strip()
        mode = str(auth.get("mode") or "").strip() or "unknown"
        suffix = f" in tenant {tenant_id}" if tenant_id else ""
        routing_mode = str(routing.get("mode") or "").strip()
        routing_note = f" Routing: {routing_mode}." if routing_mode else ""
        self.connection_status.setText(f"Status: connected as {user_id}{suffix} via {mode}.{routing_note}")

    def _save_connection(self) -> None:
        base_url = self.gateway_url_edit.text().strip() or DEFAULT_GATEWAY_URL
        auth_mode = str(self.auth_mode_combo.currentData() or "bearer")
        try:
            if auth_mode == "bearer":
                self._controller.save_bearer_connection(base_url=base_url, auth_token=self.bearer_token_edit.text())
                self.connection_feedback.setText("Saved bearer-token connection on this device.")
            else:
                self._controller.login_gateway_session(
                    base_url=base_url,
                    user_id=self.gateway_user_edit.text().strip(),
                    token=self.gateway_user_token_edit.text(),
                    remember=bool(self.remember_session.isChecked()),
                )
                self.gateway_user_token_edit.clear()
                self.connection_feedback.setText("Saved gateway session on this device.")
        except Exception as exc:
            QMessageBox.critical(self, "Connection failed", str(exc))
            return
        self.settings_saved.emit()
        self.refresh()

    def _clear_connection(self) -> None:
        connection = self._controller.current_connection()
        base_url = self.gateway_url_edit.text().strip() or DEFAULT_GATEWAY_URL
        try:
            if str(connection.auth_mode or "").strip() == "session" and str(connection.session_id or "").strip():
                self._controller.logout_gateway_session()
            else:
                self._controller.save_bearer_connection(base_url=base_url, auth_token="")
        except Exception as exc:
            QMessageBox.critical(self, "Sign-out failed", str(exc))
            return
        self.connection_feedback.setText("Cleared local gateway sign-in state.")
        self.settings_saved.emit()
        self.refresh()

    def _active_row(self) -> Optional[CapabilityRouteRow]:
        idx = int(self.route_list.currentRow())
        if idx < 0 or idx >= len(self._route_rows):
            return None
        return self._route_rows[idx]

    def _load_selected_route(self, _index: int) -> None:
        row = self._active_row()
        if row is None:
            self._set_route_editor_enabled(False)
            return
        self.route_label.setText(row.label)
        self.route_help.setText(row.description or row.package_hint or "")
        self.route_state.setText(self._route_state_text(row))
        self.base_url_edit.setText(row.base_url)
        self.options_edit.setPlainText(json_dumps(row.options))
        self.show_advanced.setChecked(bool(row.base_url or row.options))
        self._populate_providers(row=row)
        self._set_combo_value(self.provider_combo, row.provider)
        self._refresh_models_for_provider()
        self._set_combo_value(self.model_combo, row.model)
        self._apply_route_specific_state(row)
        self._apply_advanced_visibility()
        read_only = bool(row.read_only and not row.overrideable)
        self.provider_combo.setEnabled(not read_only)
        self.model_combo.setEnabled(not read_only)
        self.base_url_edit.setEnabled(not read_only)
        self.options_edit.setEnabled(not read_only)
        self.voice_combo.setEnabled(not read_only)
        self.resolution_combo.setEnabled(not read_only)
        self.save_button.setEnabled(not read_only)
        self.reset_button.setEnabled(not read_only)

    def _set_route_editor_enabled(self, enabled: bool) -> None:
        self.provider_combo.setEnabled(enabled)
        self.model_combo.setEnabled(enabled)
        self.base_url_edit.setEnabled(enabled)
        self.options_edit.setEnabled(enabled)
        self.voice_combo.setEnabled(enabled)
        self.resolution_combo.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)

    def _focus_route(self, route_key: str) -> None:
        target = str(route_key or "").strip()
        if not target:
            return
        gateway_defaults_index = self.settings_tabs.indexOf(self._routes_tab)
        if gateway_defaults_index >= 0:
            self.settings_tabs.setCurrentIndex(gateway_defaults_index)
        for idx, row in enumerate(self._route_rows):
            if row.key == target:
                self.route_list.setCurrentRow(idx)
                break

    def _refresh_voice_shortcut_summary(self) -> None:
        row = next((item for item in self._route_rows if item.key == "output.voice"), None)
        if row is None:
            self.voice_shortcut_summary.setText("Configure provider, model, and voice/profile used when the assistant speaks replies aloud.")
            return
        provider = str(row.provider or "").strip() or "No provider"
        model = str(row.model or "").strip() or "No model"
        voice = str((row.options or {}).get("voice") or (row.options or {}).get("profile") or "").strip() or "Default voice"
        self.voice_shortcut_summary.setText(f"{provider} / {model} · {voice}")

    def _route_key_label(self, key: str) -> str:
        spec = ROUTE_SPECS.get(str(key or "").strip())
        return spec.label if spec is not None else str(key or "").strip()

    def _route_state_text(self, row: CapabilityRouteRow) -> str:
        parts = [
            "Saved on the connected gateway." if row.configured else "No saved override on this route yet.",
        ]
        if row.covered_by:
            parts.append(f"This route is covered by {self._route_key_label(row.covered_by)}.")
        if row.derived_from:
            parts.append(f"This route inherits from {self._route_key_label(row.derived_from)}.")
        if row.source:
            parts.append(f"Gateway source: {row.source}.")
        return " ".join(parts)

    def _populate_providers(self, *, row: CapabilityRouteRow) -> None:
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        try:
            choices = self._controller.provider_choices(route_key=row.key, base_url=self.base_url_edit.text().strip())
        except Exception as exc:
            self.route_feedback.setText(str(exc))
            choices = []
        for choice in choices:
            self.provider_combo.addItem(choice.label, choice.id)
        if self.provider_combo.count() == 0 and row.provider:
            self.provider_combo.addItem(row.provider, row.provider)
        self.provider_combo.blockSignals(False)

    def _refresh_models_for_provider(self) -> None:
        row = self._active_row()
        if row is None:
            return
        provider = self.provider_combo.currentData() or self.provider_combo.currentText()
        self.model_combo.clear()
        try:
            choices = self._controller.model_choices(
                route_key=row.key,
                provider=str(provider or ""),
                base_url=self.base_url_edit.text().strip(),
            )
        except Exception as exc:
            self.route_feedback.setText(str(exc))
            choices = []
        for choice in choices:
            self.model_combo.addItem(choice.label, choice.id)
        if row.model and self.model_combo.findText(row.model) < 0:
            self.model_combo.addItem(row.model, row.model)
        self._refresh_voice_choices()

    def _reload_catalogs_for_base_url(self) -> None:
        row = self._active_row()
        if row is None:
            return
        current_provider = str(self.provider_combo.currentData() or self.provider_combo.currentText() or "").strip()
        current_model = str(self.model_combo.currentData() or self.model_combo.currentText() or "").strip()
        self._populate_providers(row=row)
        if current_provider:
            if self.provider_combo.findText(current_provider) < 0:
                self.provider_combo.addItem(current_provider, current_provider)
            self._set_combo_value(self.provider_combo, current_provider)
        self._refresh_models_for_provider()
        if current_model:
            if self.model_combo.findText(current_model) < 0:
                self.model_combo.addItem(current_model, current_model)
            self._set_combo_value(self.model_combo, current_model)

    def _refresh_voice_choices(self) -> None:
        row = self._active_row()
        self.voice_combo.clear()
        if row is None or row.key != "output.voice":
            return
        provider = str(self.provider_combo.currentData() or self.provider_combo.currentText() or "").strip()
        model = str(self.model_combo.currentData() or self.model_combo.currentText() or "").strip()
        try:
            choices = self._controller.voice_choices(
                provider=provider,
                model=model,
                base_url=self.base_url_edit.text().strip(),
            )
        except Exception as exc:
            self.route_feedback.setText(str(exc))
            choices = []
        for choice in choices:
            self.voice_combo.addItem(choice.label, choice.id)

    def _apply_route_specific_state(self, row: CapabilityRouteRow) -> None:
        options = dict(row.options)
        is_voice = row.key == "output.voice"
        self.voice_label.setVisible(is_voice)
        self.voice_combo.setVisible(is_voice)
        if is_voice:
            self._refresh_voice_choices()
            voice_value = str(options.get("voice") or options.get("profile") or "").strip()
            if voice_value:
                if self.voice_combo.findText(voice_value) < 0:
                    self.voice_combo.addItem(voice_value, voice_value)
                self._set_combo_value(self.voice_combo, voice_value)

        is_upscale = row.key == "output.image.image_upscale"
        self.resolution_label.setVisible(is_upscale)
        self.resolution_combo.setVisible(is_upscale)
        if is_upscale:
            resolution = str(options.get("resolution") or "2x").strip() or "2x"
            self._set_combo_value(self.resolution_combo, resolution)

    def _apply_advanced_visibility(self) -> None:
        visible = bool(self.show_advanced.isChecked())
        self.base_url_label.setVisible(visible)
        self.base_url_edit.setVisible(visible)
        self.options_label.setVisible(visible)
        self.options_edit.setVisible(visible)

    def _merged_options(self) -> Dict[str, Any]:
        row = self._active_row()
        if row is None:
            return {}
        options = self._controller.parse_options(self.options_edit.toPlainText())
        if row.key == "output.voice":
            voice = str(self.voice_combo.currentData() or self.voice_combo.currentText() or "").strip()
            if voice:
                options["voice"] = voice
            else:
                options.pop("voice", None)
                options.pop("profile", None)
        if row.key == "output.image.image_upscale":
            resolution = str(self.resolution_combo.currentData() or self.resolution_combo.currentText() or "").strip()
            if resolution:
                options["resolution"] = resolution
            else:
                options.pop("resolution", None)
        return options

    def _save_route(self) -> None:
        row = self._active_row()
        if row is None:
            return
        try:
            provider = str(self.provider_combo.currentData() or self.provider_combo.currentText() or "").strip()
            model = str(self.model_combo.currentData() or self.model_combo.currentText() or "").strip()
            self._controller.save_route_default(
                route_key=row.key,
                provider=provider,
                model=model,
                base_url=self.base_url_edit.text().strip(),
                options=self._merged_options(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.route_feedback.setText("Saved on the connected gateway.")
        self.settings_saved.emit()
        self.refresh()

    def _clear_route(self) -> None:
        row = self._active_row()
        if row is None:
            return
        try:
            self._controller.clear_route_default(route_key=row.key)
        except Exception as exc:
            QMessageBox.critical(self, "Reset failed", str(exc))
            return
        self.route_feedback.setText("This route now uses the gateway-wide default again.")
        self.settings_saved.emit()
        self.refresh()

    def _save_preferences(self) -> None:
        prefs = AssistantPreferences(
            hotkey_enabled=bool(self.hotkey_enabled.isChecked()),
            hotkey_sequence=self.hotkey_edit.text().strip() or "cmd+shift+space",
            auto_speak=bool(self.auto_speak.isChecked()),
            window_width=int(self.width_spin.value()),
            window_height=int(self.height_spin.value()),
            bottom_offset=int(self.bottom_offset_spin.value()),
            tool_preferences=dict(self._controller.preferences.tool_preferences or {}),
        )
        self._controller.save_preferences(prefs)
        self._apply_hotkey()
        self.prefs_feedback.setText("Saved on this device.")
        self.settings_saved.emit()

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        target = str(value or "").strip()
        if not target:
            return
        idx = combo.findData(target)
        if idx < 0:
            idx = combo.findText(target)
        if idx >= 0:
            combo.setCurrentIndex(idx)


class AssistantPalette(QMainWindow):
    hotkey_activated = pyqtSignal()
    message_speech_started = pyqtSignal(str)
    message_speech_finished = pyqtSignal(str)

    def __init__(self, *, controller: AssistantV2Controller, debug: bool = False) -> None:
        super().__init__()
        self._controller = controller
        self._debug = bool(debug)
        self._renderer = MarkdownRenderer(theme="friendly_grayscale")
        self._tray = None
        self._tray_menu = None
        self._settings_dialog = None
        self._tool_settings_dialog = None
        self._worker = None
        self._hotkey = GlobalHotkeyManager()
        self._attachments: List[str] = []
        self._listening = False
        self._transient_modal_open = False
        self._active_spoken_message_key = ""
        self._active_spoken_message_phase = "idle"
        self._zoomed = False
        self._composer_drop_active = False
        self._pending_history_scroll = HistoryScrollRequest()
        self._history_cards_by_key: Dict[str, QWidget] = {}
        self._history_refreshing = False
        self._status_text = "Ready"
        self._status_tone = "neutral"
        self._run_busy = False
        self._run_has_final_output = False
        self._history_settle_timer = QTimer(self)
        self._history_settle_timer.setSingleShot(True)
        self._history_settle_timer.timeout.connect(self._apply_pending_history_scroll)
        self.hotkey_activated.connect(self.toggle_palette)
        self.message_speech_started.connect(self._on_message_speech_started)
        self.message_speech_finished.connect(self._on_message_speech_finished)
        self._controller.voice_manager.on_speech_start = self._emit_message_speech_started

        self.setWindowTitle("AbstractAssistant")
        self.setWindowIcon(_qt_icon())
        self.setObjectName("assistantPalette")
        self.setMinimumSize(420, 260)
        self.resize(self._controller.preferences.window_width, self._controller.preferences.window_height)
        self.setAcceptDrops(False)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        central = QWidget()
        central.setObjectName("rootSurface")
        self.setCentralWidget(central)
        self._surface = central

        header_card = QFrame(central)
        header_card.setObjectName("topBarCard")
        header_card.setMinimumHeight(42)
        header_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header_card = header_card
        header_shell = QVBoxLayout(header_card)
        header_shell.setContentsMargins(4, 4, 4, 4)
        header_shell.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        header_shell.addLayout(title_row)

        traffic_group = QHBoxLayout()
        traffic_group.setContentsMargins(0, 0, 0, 0)
        traffic_group.setSpacing(5)
        title_row.addLayout(traffic_group, 0)

        close_button = QPushButton()
        close_button.setObjectName("trafficButton")
        close_button.setProperty("tone", "close")
        close_button.setFixedSize(12, 12)
        close_button.setToolTip("Quit AbstractAssistant")
        close_button.clicked.connect(self._quit_application)
        traffic_group.addWidget(close_button, 0, Qt.AlignVCenter)

        minimize_button = QPushButton()
        minimize_button.setObjectName("trafficButton")
        minimize_button.setProperty("tone", "minimize")
        minimize_button.setFixedSize(12, 12)
        minimize_button.setToolTip("Hide assistant")
        minimize_button.clicked.connect(self.hide)
        traffic_group.addWidget(minimize_button, 0, Qt.AlignVCenter)

        zoom_button = QPushButton()
        zoom_button.setObjectName("trafficButton")
        zoom_button.setProperty("tone", "zoom")
        zoom_button.setFixedSize(12, 12)
        zoom_button.setToolTip("Maximize chat")
        zoom_button.clicked.connect(self._toggle_zoom)
        traffic_group.addWidget(zoom_button, 0, Qt.AlignVCenter)

        title = QLabel("AbstractAssistant")
        title.setObjectName("windowTitle")
        title_row.addWidget(title, 0, Qt.AlignVCenter)

        self.connection_led = QFrame()
        self.connection_led.setObjectName("connectionLed")
        self.connection_led.setFixedSize(8, 8)
        self.connection_led.setToolTip("Checking gateway connection")
        self.connection_led.setProperty("state", "unknown")
        title_row.addWidget(self.connection_led, 0, Qt.AlignVCenter)
        title_row.addStretch(1)

        header_actions = QHBoxLayout()
        header_actions.setContentsMargins(0, 0, 0, 0)
        header_actions.setSpacing(4)
        title_row.addLayout(header_actions, 0)

        new_session = QPushButton()
        new_session.setObjectName("iconButton")
        new_session.setIcon(_symbol_icon("plus"))
        new_session.setIconSize(QSize(14, 14))
        new_session.setFixedSize(24, 24)
        new_session.setToolTip("Start a fresh conversation")
        new_session.clicked.connect(self._create_session)
        header_actions.addWidget(new_session)

        tools = QPushButton()
        tools.setObjectName("iconButton")
        tools.setIcon(_symbol_icon("spark"))
        tools.setIconSize(QSize(14, 14))
        tools.setFixedSize(24, 24)
        tools.setToolTip("Choose which tools the workflow-backed assistant may use")
        tools.clicked.connect(self._open_tool_settings)
        header_actions.addWidget(tools)

        self.auto_speak = QPushButton()
        self.auto_speak.setObjectName("topIconToggleButton")
        self.auto_speak.setCheckable(True)
        self.auto_speak.setIcon(_symbol_icon("speaker"))
        self.auto_speak.setIconSize(QSize(14, 14))
        self.auto_speak.setFixedSize(24, 24)
        self.auto_speak.setChecked(bool(self._controller.preferences.auto_speak))
        self.auto_speak.clicked.connect(self._persist_auto_speak)
        self.auto_speak.setToolTip("Speak replies automatically")
        header_actions.addWidget(self.auto_speak)

        settings = QPushButton()
        settings.setObjectName("iconButton")
        settings.setIcon(_symbol_icon("gear"))
        settings.setIconSize(QSize(14, 14))
        settings.setFixedSize(24, 24)
        settings.setToolTip("Preferences")
        settings.clicked.connect(self._open_settings)
        header_actions.addWidget(settings)

        self.banner_label = QLabel("")
        self.banner_label.setObjectName("bannerLabel")
        self.banner_label.setWordWrap(True)
        self.banner_label.setMinimumHeight(0)
        self.banner_label.setMaximumHeight(0)
        self.banner_label.hide()

        self.history_card = QFrame(central)
        self.history_card.setObjectName("historyCard")
        self.history_scroll = DampedScrollArea(factor=0.7)
        self.history_scroll.setObjectName("historyScroll")
        self.history_scroll.setWidgetResizable(True)
        self.history_host = QWidget()
        self.history_host.setObjectName("historyHost")
        self.history_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.history_host.installEventFilter(self)
        self.history_layout = QVBoxLayout(self.history_host)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(8)
        self.history_layout.setAlignment(Qt.AlignTop)
        self.history_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.history_scroll.setWidget(self.history_host)
        history_wrap = QVBoxLayout(self.history_card)
        history_wrap.setContentsMargins(6, 6, 6, 6)
        history_wrap.setSpacing(4)
        self.chat_status_label = QLabel("Ready")
        self.chat_status_label.setObjectName("historyStatusLabel")
        self.chat_status_label.hide()
        history_wrap.addWidget(self.banner_label)
        history_wrap.addWidget(self.history_scroll, 1)

        self.composer_card = AttachmentDropFrame(central)
        self.composer_card.setObjectName("composerCard")
        self.composer_card.setFixedHeight(56)
        self.composer_card.files_dropped.connect(self._handle_dropped_files)
        self.composer_card.drop_active_changed.connect(self._set_composer_drop_active)
        composer_outer = QVBoxLayout(self.composer_card)
        composer_outer.setContentsMargins(0, 0, 0, 0)
        composer_outer.setSpacing(0)

        self.attachments_tray = QScrollArea()
        self.attachments_tray.setObjectName("attachmentsTray")
        self.attachments_tray.setWidgetResizable(True)
        self.attachments_tray.setFrameShape(QFrame.NoFrame)
        self.attachments_tray.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.attachments_tray.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.attachments_tray.setFixedHeight(42)
        self.attachments_tray.hide()
        self.attachments_host = QWidget()
        self.attachments_host.setObjectName("attachmentsTrayHost")
        self.attachments_layout = QHBoxLayout(self.attachments_host)
        self.attachments_layout.setContentsMargins(8, 6, 8, 2)
        self.attachments_layout.setSpacing(6)
        self.attachments_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.attachments_tray.setWidget(self.attachments_host)
        composer_outer.addWidget(self.attachments_tray)

        composer = QHBoxLayout()
        composer.setContentsMargins(4, 4, 4, 4)
        composer.setSpacing(4)
        composer_outer.addLayout(composer)

        self.attach_button = QPushButton()
        self.attach_button.setObjectName("composerIconButton")
        self.attach_button.setIcon(_symbol_icon("paperclip"))
        self.attach_button.setIconSize(QSize(16, 16))
        self.attach_button.setFixedSize(36, 36)
        self.attach_button.setToolTip("Attach files")
        self.attach_button.clicked.connect(self._pick_attachments)
        composer.addWidget(self.attach_button)

        self.mic_button = QPushButton()
        self.mic_button.setObjectName("composerIconButton")
        self.mic_button.setIcon(_symbol_icon("mic"))
        self.mic_button.setIconSize(QSize(16, 16))
        self.mic_button.setFixedSize(36, 36)
        self.mic_button.setToolTip("Speak your question")
        self.mic_button.clicked.connect(self._toggle_listening)
        composer.addWidget(self.mic_button)

        self.prompt_edit = AttachmentTextEdit()
        self.prompt_edit.setObjectName("promptEdit")
        self.prompt_edit.setFixedHeight(38)
        self.prompt_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.prompt_edit.document().setDocumentMargin(1)
        self.prompt_edit.setPlaceholderText("Ask anything or drop files here.")
        self.prompt_edit.installEventFilter(self)
        self.prompt_edit.files_dropped.connect(self._handle_dropped_files)
        self.prompt_edit.drop_active_changed.connect(self._set_composer_drop_active)
        composer.addWidget(self.prompt_edit, 1)

        self.send_button = QPushButton()
        self.send_button.setObjectName("sendButton")
        self.send_button.setIcon(_symbol_icon("send", color="#f8fffc"))
        self.send_button.setIconSize(QSize(18, 18))
        self.send_button.setFixedSize(38, 38)
        self.send_button.setToolTip("Send")
        self.send_button.clicked.connect(self._submit)
        composer.addWidget(self.send_button)

        QShortcut(Qt.Key_Escape, self, activated=self.hide)

        self._apply_styles()
        self._refresh_workflows()
        self.refresh_history()
        self._refresh_capability_state()
        self._refresh_submission_state()
        self._render_attachments()
        self._apply_hotkey()
        QTimer.singleShot(0, self._reflow_shell)

    def _labeled_control(self, title: str, control: QWidget) -> QWidget:
        host = QFrame()
        host.setObjectName("controlBlock")
        host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(title)
        label.setObjectName("controlLabel")
        layout.addWidget(label)
        control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if hasattr(control, "setMaximumHeight"):
            control.setMaximumHeight(40)
        layout.addWidget(control)
        return host

    def _refresh_widget_style(self, widget: QWidget) -> None:
        style = widget.style()
        if style is None:
            return
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _set_status(self, text: str, tone: str = "neutral") -> None:
        self._status_text = str(text or "").strip() or "Ready"
        self._status_tone = str(tone or "neutral").strip() or "neutral"

    def _set_banner(self, text: str = "", tone: str = "info") -> None:
        message = str(text or "").strip()
        if not message:
            self.banner_label.clear()
            self.banner_label.setMinimumHeight(0)
            self.banner_label.setMaximumHeight(0)
            self.banner_label.hide()
            return
        self.banner_label.setText(message)
        self.banner_label.setProperty("tone", tone)
        self.banner_label.setMinimumHeight(0)
        self.banner_label.setMaximumHeight(16777215)
        self._refresh_widget_style(self.banner_label)
        self.banner_label.show()

    def attach_tray(self, tray: QSystemTrayIcon) -> None:
        self._tray = tray

    def closeEvent(self, event) -> None:  # noqa: N802
        self.hide()
        event.ignore()

    def resizeEvent(self, event) -> None:  # noqa: N802
        preserve_request = None
        if not bool(getattr(self, "_history_refreshing", False)):
            preserve_request = self._capture_history_scroll_request()
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_visible_history_cards)
        if preserve_request is not None:
            self._commit_history_scroll_request(preserve_request)

    def _quit_application(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def event(self, event) -> bool:  # noqa: A003
        if event is not None and event.type() == QEvent.WindowDeactivate:
            QTimer.singleShot(0, self._hide_if_inactive)
        return super().event(event)

    def eventFilter(self, obj, event):  # noqa: N802
        state = getattr(self, "__dict__", {})
        prompt_edit = state.get("prompt_edit")
        if obj is prompt_edit and event is not None and event.type() == QEvent.KeyPress:
            key = int(event.key())
            modifiers = int(event.modifiers())
            if key in {Qt.Key_Return, Qt.Key_Enter} and not (modifiers & int(Qt.ShiftModifier)):
                self._submit()
                return True
        history_host = state.get("history_host")
        if obj is history_host and event is not None:
            if event.type() in {QEvent.LayoutRequest, QEvent.Resize, QEvent.Show}:
                self._sync_history_viewport()
                self._schedule_history_scroll_apply()
        return False

    def _hide_if_inactive(self) -> None:
        if not self.isVisible() or self.isActiveWindow():
            return
        if self._transient_modal_open:
            return
        active_modal = QApplication.activeModalWidget()
        if active_modal is not None and active_modal.isVisible():
            return
        if self._settings_dialog is not None and self._settings_dialog.isVisible() and self._settings_dialog.isActiveWindow():
            return
        if self._tool_settings_dialog is not None and self._tool_settings_dialog.isVisible() and self._tool_settings_dialog.isActiveWindow():
            return
        self.hide()

    def _available_screen_geometry(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return None
        return screen.availableGeometry()

    def _clamp_window_to_screen(self, *, x: int, y: int, width: int, height: int, screen_geom):
        min_x = int(screen_geom.x())
        min_y = int(screen_geom.y())
        max_x = int(screen_geom.x() + max(0, int(screen_geom.width()) - int(width)))
        max_y = int(screen_geom.y() + max(0, int(screen_geom.height()) - int(height)))
        return max(min_x, min(int(x), max_x)), max(min_y, min(int(y), max_y))

    def position_near_tray(self) -> None:
        screen_geom = self._available_screen_geometry()
        if screen_geom is None:
            return
        pref_gap = max(0, int(self._controller.preferences.bottom_offset))
        right_gap = 4 if pref_gap == 0 else min(pref_gap, 8)
        top_gap = 3 if pref_gap == 0 else min(pref_gap, 8)
        width = int(self.width())
        height = int(self.height())
        x = int(screen_geom.x() + screen_geom.width() - width - right_gap)
        y = int(screen_geom.y() + top_gap)
        x, y = self._clamp_window_to_screen(
            x=x,
            y=y,
            width=width,
            height=height,
            screen_geom=screen_geom,
        )
        self.move(x, y)

    def _reflow_shell(self) -> None:
        screen_geom = self._available_screen_geometry()
        if screen_geom is None:
            return
        prefs = self._controller.preferences
        normal_width = min(max(int(prefs.window_width), 420), min(612, int(screen_geom.width() * 0.38)))
        normal_height = min(max(int(prefs.window_height), 320), min(392, int(screen_geom.height() * 0.46)))
        show_history = True
        show_banner = bool(getattr(self.banner_label, "text", lambda: "")().strip())
        if hasattr(self, "history_card") and self.history_card is not None:
            self.history_card.setVisible(show_history)
        if hasattr(self, "banner_label") and self.banner_label is not None:
            if show_banner:
                self.banner_label.setMinimumHeight(0)
                self.banner_label.setMaximumHeight(16777215)
            else:
                self.banner_label.setMinimumHeight(0)
                self.banner_label.setMaximumHeight(0)
            self.banner_label.setVisible(show_banner)
        header_height = max(42, int(self.header_card.sizeHint().height()))
        composer_height = int(self.composer_card.height() or self.composer_card.sizeHint().height() or 80)
        side_gap = 8
        card_gap = 4
        top_gap = 4
        bottom_gap = 4
        if self._zoomed:
            width = min(
                max(int(screen_geom.width() * 0.50), max(760, normal_width + 140)),
                int(screen_geom.width() * 0.62),
            )
            target_height = min(
                max(int(screen_geom.height() * 0.56), max(420, normal_height + 72)),
                int(screen_geom.height() * 0.72),
            )
            card_width = max(420 - (side_gap * 2), width - (side_gap * 2))
            history_height = max(
                132,
                int(target_height - top_gap - bottom_gap - header_height - composer_height - (card_gap * 2)),
            )
            self.history_card.setMinimumHeight(history_height)
            self.history_card.setMaximumHeight(history_height)
            self.header_card.setGeometry(side_gap, top_gap, card_width, header_height)
            history_y = top_gap + header_height + card_gap
            self.history_card.setGeometry(side_gap, history_y, card_width, history_height)
            composer_y = history_y + history_height + card_gap
            self.composer_card.setGeometry(side_gap, composer_y, card_width, composer_height)
            x = int(screen_geom.x() + max(0, (screen_geom.width() - width) / 2))
            y = int(screen_geom.y() + max(0, (screen_geom.height() - target_height) / 2))
            self.setGeometry(x, y, width, target_height)
            return
        width = normal_width
        expanded_height = normal_height
        history_height = max(132, min(164, int(expanded_height * 0.42)))
        self.history_card.setMinimumHeight(history_height)
        self.history_card.setMaximumHeight(history_height)
        card_width = max(420 - (side_gap * 2), width - (side_gap * 2))
        self.header_card.setGeometry(side_gap, top_gap, card_width, header_height)
        history_y = top_gap + header_height + card_gap
        self.history_card.setGeometry(side_gap, history_y, card_width, history_height)
        composer_y = history_y + history_height + card_gap
        self.composer_card.setGeometry(side_gap, composer_y, card_width, composer_height)
        target_height = int(composer_y + composer_height + bottom_gap)
        self.resize(width, target_height)
        self.position_near_tray()

    def _toggle_zoom(self) -> None:
        self._zoomed = not bool(self._zoomed)
        self._reflow_shell()

    def show_palette(self) -> None:
        self._reflow_shell()
        self.show()
        self.raise_()
        self.activateWindow()
        self.prompt_edit.setFocus()

    def toggle_palette(self) -> None:
        self.show_palette()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        event.ignore()

    def refresh_history(self, request: Optional[HistoryScrollRequest] = None) -> None:
        scroll_request = request if isinstance(request, HistoryScrollRequest) else self._capture_history_scroll_request()
        state = getattr(self, "__dict__", {})
        timer = state.get("_history_settle_timer")
        if timer is not None:
            timer.stop()
        self._history_refreshing = True
        try:
            while self.history_layout.count():
                item = self.history_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            self._history_cards_by_key = {}
            visible_messages = _visible_history_messages(
                self._controller.session_messages(),
                busy=self._show_thinking_indicator(),
            )
            viewport_width = int(self.history_scroll.viewport().width() or self.width())
            for visible_index, message in enumerate(visible_messages):
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role") or "").strip()
                is_user = role == "user"
                message_key = _history_message_key(message, fallback_index=visible_index)
                bubble_width = _message_bubble_width(viewport_width, role=role)
                card = MessageCard(
                    message=message,
                    message_key=message_key,
                    renderer=self._renderer,
                    on_open_artifact=self._open_artifact_from_message,
                    build_media_preview=self._build_media_preview,
                    bubble_width=bubble_width,
                    on_toggle_voice=None if is_user else self._toggle_message_voice,
                    voice_state="idle" if is_user else self._message_voice_state(message),
                )
                self._history_cards_by_key[message_key] = card
                self.history_layout.addWidget(card)
            if self._show_thinking_indicator():
                self.history_layout.addWidget(ThinkingIndicatorCard())
            self._sync_history_viewport()
            self._reflow_shell()
        finally:
            self._history_refreshing = False
        self._commit_history_scroll_request(scroll_request)

    def _resize_visible_history_cards(self) -> None:
        viewport_width = int(self.history_scroll.viewport().width() or self.width())
        for index in range(self.history_layout.count()):
            item = self.history_layout.itemAt(index)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None and hasattr(widget, "sync_to_viewport_width"):
                widget.sync_to_viewport_width(viewport_width)
        self._sync_history_viewport()
        self._schedule_history_scroll_apply()

    def _sync_history_viewport(self) -> None:
        state = getattr(self, "__dict__", {})
        host = state.get("history_host")
        layout = state.get("history_layout")
        if host is None or layout is None:
            return
        try:
            layout.invalidate()
            layout.activate()
            host.updateGeometry()
            host.adjustSize()
        except Exception:
            return

    def _history_scroll_request(
        self,
        *,
        mode: str = "preserve",
        message_key: str = "",
        offset: int = 0,
    ) -> HistoryScrollRequest:
        normalized = str(mode or "").strip().lower()
        if normalized not in {"preserve", "bottom", "message_top"}:
            normalized = "preserve"
        return HistoryScrollRequest(
            mode=normalized,
            message_key=str(message_key or "").strip(),
            offset=max(0, int(offset or 0)),
        )

    def _capture_history_scroll_request(self) -> HistoryScrollRequest:
        state = getattr(self, "__dict__", {})
        scroll = state.get("history_scroll")
        layout = state.get("history_layout")
        if scroll is None or layout is None:
            return self._history_scroll_request()
        bar = scroll.verticalScrollBar()
        if bar is None:
            return self._history_scroll_request()
        top = max(0, int(bar.value()))
        for index in range(max(0, int(layout.count()))):
            item = layout.itemAt(index)
            if item is None:
                continue
            widget = item.widget()
            if widget is None:
                continue
            key = str(getattr(widget, "_history_message_key", "") or "").strip()
            if not key:
                continue
            try:
                widget_top = max(0, int(widget.y()))
                widget_bottom = widget_top + max(1, int(widget.height()))
            except Exception:
                continue
            if widget_bottom <= top:
                continue
            return self._history_scroll_request(
                mode="preserve",
                message_key=key,
                offset=max(0, top - widget_top),
            )
        return self._history_scroll_request()

    def _latest_visible_message_key(self, *, role: str = "") -> str:
        target_role = str(role or "").strip().lower()
        visible_messages = _visible_history_messages(
            self._controller.session_messages(),
            busy=self._show_thinking_indicator(),
        )
        for visible_index in range(len(visible_messages) - 1, -1, -1):
            message = visible_messages[visible_index]
            if not isinstance(message, dict):
                continue
            message_role = str(message.get("role") or "").strip().lower()
            if target_role and message_role != target_role:
                continue
            return _history_message_key(message, fallback_index=visible_index)
        return ""

    def _commit_history_scroll_request(self, request: Optional[HistoryScrollRequest]) -> None:
        if not isinstance(request, HistoryScrollRequest):
            request = self._history_scroll_request()
        state = getattr(self, "__dict__", {})
        timer = state.get("_history_settle_timer")
        if timer is not None:
            timer.stop()
        self._pending_history_scroll = request
        self._schedule_history_scroll_apply()

    def _schedule_history_scroll_apply(self) -> None:
        state = getattr(self, "__dict__", {})
        request = state.get("_pending_history_scroll", HistoryScrollRequest())
        if not isinstance(request, HistoryScrollRequest):
            request = self._history_scroll_request()
            self._pending_history_scroll = request
        if request.mode == "preserve" and not request.message_key:
            return
        timer = state.get("_history_settle_timer")
        if timer is None:
            return
        timer.start(16)

    def _apply_pending_history_scroll(self) -> None:
        request = getattr(self, "__dict__", {}).get("_pending_history_scroll", HistoryScrollRequest())
        self._pending_history_scroll = self._history_scroll_request()
        self._apply_history_scroll_request(request)

    def _apply_history_scroll_request(self, request: HistoryScrollRequest) -> None:
        scroll = getattr(self, "__dict__", {}).get("history_scroll")
        if scroll is None:
            return
        bar = scroll.verticalScrollBar()
        if bar is None:
            return
        normalized = str(getattr(request, "mode", "preserve") or "preserve").strip().lower()
        if normalized == "bottom":
            bar.setValue(bar.maximum())
            return
        target_key = str(getattr(request, "message_key", "") or "").strip()
        if normalized == "message_top" and not target_key:
            target_key = self._latest_visible_message_key(role="assistant")
        if not target_key:
            return
        cards_by_key = getattr(self, "__dict__", {}).get("_history_cards_by_key", {})
        target_widget = cards_by_key.get(target_key) if isinstance(cards_by_key, dict) else None
        if target_widget is None:
            return
        try:
            target_y = max(0, int(target_widget.geometry().top()))
        except Exception:
            return
        if normalized == "preserve":
            target_y += max(0, int(getattr(request, "offset", 0) or 0))
        bar.setValue(min(bar.maximum(), target_y))

    def _show_thinking_indicator(self) -> bool:
        return bool(self._run_busy and not self._run_has_final_output)

    def _set_composer_drop_active(self, active: bool) -> None:
        normalized = bool(active)
        if self._composer_drop_active == normalized:
            return
        self._composer_drop_active = normalized
        self.composer_card.setProperty("dropActive", "true" if normalized else "false")
        self.prompt_edit.setProperty("dropActive", "true" if normalized else "false")
        self._refresh_widget_style(self.composer_card)
        self._refresh_widget_style(self.prompt_edit)
        self._render_attachments()

    def _handle_dropped_files(self, paths: Any) -> None:
        self._append_attachments(list(paths or []), announce=True)

    def _append_attachments(self, paths: List[str], *, announce: bool = False) -> None:
        validated = _merge_attachment_paths([], list(paths or []))
        if not validated:
            if announce and paths:
                self._set_status("Only local files can be attached", tone="warn")
            return
        merged = _merge_attachment_paths(self._attachments, validated)
        if merged == self._attachments:
            if announce and paths:
                self._set_status("Files already attached", tone="info")
            return
        self._attachments = merged
        self._render_attachments()
        if announce:
            count = len(self._attachments)
            label = "attachment" if count == 1 else "attachments"
            self._set_status(f"{count} {label} ready", tone="info")

    def _remove_attachment(self, path: str) -> None:
        target = _normalize_attachment_path(path)
        next_items = [item for item in self._attachments if _normalize_attachment_path(item) != target]
        if next_items == self._attachments:
            return
        self._attachments = next_items
        self._render_attachments()
        count = len(self._attachments)
        if count:
            label = "attachment" if count == 1 else "attachments"
            self._set_status(f"{count} {label} ready", tone="info")
        else:
            self._set_status("Attachments cleared", tone="neutral")

    def _pick_attachments(self) -> None:
        self._transient_modal_open = True
        try:
            paths, _ = QFileDialog.getOpenFileNames(self, "Select attachments")
        finally:
            self._transient_modal_open = False
        if not paths:
            return
        self._append_attachments([str(Path(path)) for path in paths], announce=True)

    def _render_attachments(self) -> None:
        while self.attachments_layout.count():
            item = self.attachments_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self._attachments and not self._composer_drop_active:
            self.attachments_tray.hide()
            self.composer_card.setFixedHeight(56)
            self._reflow_shell()
            return
        if self._attachments:
            for path in self._attachments:
                chip = AttachmentIconChip(path=path, parent=self.attachments_host)
                chip.remove_requested.connect(self._remove_attachment)
                self.attachments_layout.addWidget(chip, 0, Qt.AlignLeft | Qt.AlignVCenter)
            self.attachments_layout.addStretch(1)
        else:
            hint = QLabel("Drop files to attach")
            hint.setObjectName("attachmentsDropHint")
            self.attachments_layout.addWidget(hint, 0, Qt.AlignLeft | Qt.AlignVCenter)
            self.attachments_layout.addStretch(1)
        self.attachments_tray.show()
        self.composer_card.setFixedHeight(96)
        self._reflow_shell()

    def _submit(self) -> None:
        if self._worker is not None:
            return
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt and not self._attachments:
            return
        plan = self._controller.submission_plan(prompt=prompt, attachments=self._attachments)
        if not bool(plan.get("ready", True)):
            detail = str(plan.get("detail") or "This request cannot run right now.").strip()
            QMessageBox.critical(self, "Assistant unavailable", detail)
            return

        attachments = list(self._attachments)
        append_user_now = bool(prompt or attachments)
        if append_user_now:
            metadata = None
            preview_items = _local_attachment_preview_items(attachments)
            if preview_items:
                metadata = {
                    "attachments": preview_items,
                    "media": preview_items,
                }
            self._controller.append_user_message(prompt, metadata=metadata)
            self.refresh_history(request=self._history_scroll_request(mode="bottom"))
        self._run_busy = True
        self._run_has_final_output = False
        self._set_status("Running assistant workflow...", tone="busy")
        try:
            worker = self._controller.build_chat_worker(
                prompt=prompt,
                attachments=attachments,
                system_prompt_extra=str(plan.get("system_prompt_extra") or ""),
                append_user_message=not append_user_now,
            )
        except Exception as exc:
            self._on_worker_error(str(exc))
            return
        self._worker = worker
        worker.event_emitted.connect(self._on_worker_event)
        worker.error_occurred.connect(self._on_worker_error)
        worker.finished.connect(self._on_worker_finished)
        worker.start()
        self.refresh_history(request=self._history_scroll_request(mode="bottom"))
        self.prompt_edit.clear()
        self._attachments = []
        self._render_attachments()

    def _on_worker_event(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        typ = str(payload.get("type") or "").strip()
        if typ == "status":
            status_text = str(payload.get("status") or "Working").strip() or "Working"
            status_lower = status_text.lower()
            inactive_statuses = {"completed", "complete", "ready", "idle", "offline", "error", "failed", "cancelled"}
            self._run_busy = status_lower not in inactive_statuses and not self._run_has_final_output
            self._set_status(status_text, tone="busy" if self._run_busy else "neutral")
            return
        if typ == "user_message_appended":
            self._on_user_message_appended(str(payload.get("content") or ""))
            return
        if typ == "assistant":
            is_final = bool(payload.get("final"))
            if is_final:
                self._run_has_final_output = True
                self._run_busy = False
            if bool(payload.get("history_changed", True)):
                self.refresh_history(
                    request=self._history_scroll_request(
                        mode="message_top",
                        message_key=self._latest_visible_message_key(role="assistant"),
                    )
                )
            self._set_status("Ready")
            if self.auto_speak.isChecked() and is_final:
                self._controller.voice_manager.speak(str(payload.get("content") or ""))
            if is_final:
                self._notify("Assistant reply", str(payload.get("content") or "").strip())
            return
        if typ == "tool_request":
            dialog = ToolApprovalDialog(tool_calls=payload.get("tool_calls"), parent=self)
            approved = dialog.exec_() == QDialog.Accepted
            self._worker.provide_tool_approval(approved)
            return
        if typ == "ask_user":
            prompt = str(payload.get("prompt") or "Input required").strip()
            response, ok = QInputDialog.getText(self, "Input required", prompt)
            text = response if ok else ""
            self._worker.provide_user_response(text)
            return
        if typ == "history_seeded":
            if not bool(payload.get("changed", True)):
                return
            assistant_key = self._latest_visible_message_key(role="assistant")
            if assistant_key:
                self.refresh_history(request=self._history_scroll_request(mode="message_top", message_key=assistant_key))
            elif self._latest_visible_message_key():
                self.refresh_history(request=self._history_scroll_request(mode="bottom"))
            else:
                self.refresh_history()
            return
        if typ == "tool":
            return

    def _on_worker_error(self, error: str) -> None:
        self._run_busy = False
        self._run_has_final_output = True
        self._set_status("Error", tone="error")
        self._notify("Assistant error", str(error or "Unknown error"))
        QMessageBox.critical(self, "Assistant error", str(error or "Unknown error"))

    def _on_worker_finished(self) -> None:
        had_indicator = self._show_thinking_indicator()
        self._worker = None
        self._run_busy = False
        if had_indicator != self._show_thinking_indicator():
            self.refresh_history()
        self._set_status("Ready")

    def _on_user_message_appended(self, _content: str = "") -> None:
        self.refresh_history(request=self._history_scroll_request(mode="bottom"))

    def _open_artifact_from_message(self, artifact: Dict[str, Any], message: Dict[str, Any]) -> None:
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        run_id = str(
            metadata.get("artifact_run_id")
            or metadata.get("run_id")
            or message.get("run_id")
            or self._controller.last_run_id()
            or self._controller.session_run_id()
            or ""
        ).strip()
        self._open_artifact(artifact, run_id=run_id)

    def _build_media_preview(self, artifact: Dict[str, Any], message: Dict[str, Any]) -> Optional[QWidget]:
        if not isinstance(artifact, dict):
            return None
        if _artifact_media_kind(artifact) not in {"image", "audio", "video"}:
            return None

        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        run_id = str(
            (metadata or {}).get("artifact_run_id")
            or (metadata or {}).get("run_id")
            or message.get("run_id")
            or self._controller.last_run_id()
            or self._controller.session_run_id()
            or ""
        ).strip()

        def _resolve() -> Path:
            return self._controller.download_artifact(run_id=run_id, artifact=artifact)

        return ArtifactPreviewCard(artifact=artifact, resolve_path=_resolve, parent=self)

    def _open_artifact(self, artifact: Dict[str, Any], *, run_id: str) -> None:
        try:
            path = self._controller.download_artifact(run_id=run_id, artifact=artifact)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _message_voice_state(self, message: Dict[str, Any]) -> str:
        key = _message_key(message)
        if key != str(self._active_spoken_message_key or ""):
            return "idle"
        if str(self._active_spoken_message_phase or "") == "synthesizing":
            return "synthesizing"
        if self._controller.voice_manager.is_paused():
            return "paused"
        if self._controller.voice_manager.is_speaking():
            return "speaking"
        self._active_spoken_message_key = ""
        self._active_spoken_message_phase = "idle"
        return "idle"

    def _toggle_message_voice(self, message: Dict[str, Any]) -> None:
        key = _message_key(message)
        state = self._message_voice_state(message)
        voice = self._controller.voice_manager
        if state == "synthesizing":
            return
        if state == "speaking":
            voice.pause()
            self.refresh_history()
            return
        if state == "paused":
            voice.resume()
            self.refresh_history()
            return
        voice.stop_speaking()
        content = str(message.get("content") or "").strip()
        if not content:
            return
        self._active_spoken_message_key = key
        self._active_spoken_message_phase = "synthesizing"
        self.refresh_history()
        started = voice.speak(content, callback=lambda key=key: self.message_speech_finished.emit(key))
        if started:
            self._active_spoken_message_key = key
        else:
            self._active_spoken_message_key = ""
            self._active_spoken_message_phase = "idle"
            self.refresh_history()

    def _on_message_speech_finished(self, key: str) -> None:
        if str(self._active_spoken_message_key or "") == str(key or ""):
            self._active_spoken_message_key = ""
            self._active_spoken_message_phase = "idle"
        self.refresh_history()

    def _emit_message_speech_started(self) -> None:
        key = str(self._active_spoken_message_key or "").strip()
        if key:
            self.message_speech_started.emit(key)

    def _on_message_speech_started(self, key: str) -> None:
        if str(self._active_spoken_message_key or "") != str(key or ""):
            return
        self._active_spoken_message_phase = "speaking"
        self.refresh_history()

    def _toggle_listening(self) -> None:
        if self._listening:
            self._controller.voice_manager.stop_listening()
            self._listening = False
            self.mic_button.setChecked(False)
            self.mic_button.setToolTip("Speak your question")
            self._set_status("Ready")
            return
        try:
            self._controller.voice_manager.listen(
                on_transcription=self._on_transcription,
                on_stop=self._on_listen_stop,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Microphone unavailable", str(exc))
            return
        self._listening = True
        self.mic_button.setChecked(True)
        self.mic_button.setToolTip("Stop listening")
        self._set_status("Listening...", tone="busy")

    def _on_transcription(self, text: str) -> None:
        current = self.prompt_edit.toPlainText().strip()
        combined = f"{current} {text}".strip() if current else text
        self.prompt_edit.setPlainText(combined)
        self.prompt_edit.moveCursor(self.prompt_edit.textCursor().End)

    def _on_listen_stop(self) -> None:
        self._listening = False
        self.mic_button.setChecked(False)
        self.mic_button.setToolTip("Speak your question")
        self._set_status("Ready")

    def _refresh_workflows(self) -> None:
        options = self._controller.workflow_options()
        status = self._controller.workflow_status()
        current = options[0] if options else None
        if current is not None:
            workflow_name = str(current.label or current.bundle_id or "assistant").strip()
            version = str(current.bundle_version or "").strip()
            detail = f"Connected to {workflow_name}"
            if version:
                detail = f"{detail} ({version})"
            self._set_connection_led("connected", detail)
        else:
            detail = str(status.error or "Gateway assistant workflow unavailable.").strip()
            self._set_connection_led("disconnected", detail)
        if status.error and not options:
            detail = str(status.error or "").strip()
            message = detail
            detail_lower = detail.lower()
            if "workflow" in detail_lower or "catalog" in detail_lower:
                message = "Assistant unavailable right now. Open Settings to review the gateway connection."
            self._set_banner(message, tone="error")
            self._set_status("Gateway attention required", tone="error")
        else:
            self._set_banner()
        self._refresh_submission_state()
        self._reflow_shell()

    def _set_connection_led(self, state: str, detail: str) -> None:
        led = getattr(self, "connection_led", None)
        if led is None:
            return
        normalized = str(state or "").strip().lower() or "unknown"
        led.setProperty("state", normalized)
        tooltip = str(detail or "").strip()
        if normalized == "connected":
            tooltip = tooltip or "Connected to the published gateway assistant."
        elif normalized == "disconnected":
            tooltip = tooltip or "The published gateway assistant is unavailable."
        else:
            tooltip = tooltip or "Checking gateway connection."
        led.setToolTip(tooltip)
        led.style().unpolish(led)
        led.style().polish(led)
        led.update()

    def _create_session(self) -> None:
        self._controller.create_session()
        self._refresh_workflows()
        self.refresh_history()

    def _open_tool_settings(self) -> None:
        if self._tool_settings_dialog is None:
            dialog = ToolSettingsDialog(controller=self._controller, parent=self)
            dialog.settings_saved.connect(self._on_tool_settings_saved)
            self._tool_settings_dialog = dialog
        self._tool_settings_dialog.refresh()
        self._show_aux_dialog(self._tool_settings_dialog)

    def _open_settings(self) -> None:
        if self._settings_dialog is None:
            dialog = SettingsDialog(controller=self._controller, apply_hotkey=self._apply_hotkey, parent=self)
            dialog.settings_saved.connect(self._on_settings_saved)
            self._settings_dialog = dialog
        self._settings_dialog.refresh()
        self._show_aux_dialog(self._settings_dialog)

    def _show_aux_dialog(self, dialog: QDialog) -> None:
        try:
            dialog.adjustSize()
        except Exception:
            pass
        dialog.show()
        try:
            dialog_geom = dialog.frameGeometry()
            screen_geom = self._available_screen_geometry()
            if screen_geom is not None:
                pref_gap = max(0, int(self._controller.preferences.bottom_offset))
                x_gap = 8 if pref_gap == 0 else min(pref_gap, 10)
                y_gap = 8 if pref_gap == 0 else min(pref_gap, 12)
                x = int(screen_geom.x() + screen_geom.width() - dialog_geom.width() - x_gap)
                y = int(screen_geom.y() + y_gap)
                x, y = self._clamp_window_to_screen(
                    x=x,
                    y=y,
                    width=dialog_geom.width(),
                    height=dialog_geom.height(),
                    screen_geom=screen_geom,
                )
                dialog.move(x, y)
        except Exception:
            pass
        dialog.raise_()
        dialog.activateWindow()

    def _on_settings_saved(self) -> None:
        self.auto_speak.setChecked(bool(self._controller.preferences.auto_speak))
        self._refresh_capability_state()
        self._refresh_workflows()
        self._refresh_submission_state()
        self._reflow_shell()

    def _on_tool_settings_saved(self) -> None:
        self._set_status("Tool defaults updated", tone="info")

    def _persist_auto_speak(self) -> None:
        prefs = self._controller.preferences
        updated = AssistantPreferences(
            hotkey_enabled=prefs.hotkey_enabled,
            hotkey_sequence=prefs.hotkey_sequence,
            auto_speak=bool(self.auto_speak.isChecked()),
            window_width=prefs.window_width,
            window_height=prefs.window_height,
            bottom_offset=prefs.bottom_offset,
            tool_preferences=dict(prefs.tool_preferences or {}),
        )
        self._controller.save_preferences(updated)

    def _apply_hotkey(self) -> None:
        prefs = self._controller.preferences_store.load()
        self._controller.preferences = prefs
        if not prefs.hotkey_enabled:
            self._hotkey.stop()
            return
        ok = self._hotkey.start(sequence=prefs.hotkey_sequence, callback=self.hotkey_activated.emit)
        if not ok and self._hotkey.error:
            self.history_card.setToolTip("Summon shortcut unavailable. Use the tray icon or reinstall hotkey support.")
            if self._status_tone not in {"error", "busy"}:
                self._set_status("Ready")
        elif self._status_tone not in {"error", "busy"}:
            self.history_card.setToolTip("")
            self._set_status("Ready")

    def _refresh_capability_state(self) -> None:
        tts_available = self._controller.supports_tts()
        stt_available = self._controller.supports_stt()
        self.auto_speak.setEnabled(tts_available)
        self.auto_speak.setToolTip("" if tts_available else "Gateway voice output is not configured.")
        self.mic_button.setEnabled(stt_available)
        self.mic_button.setToolTip("" if stt_available else "Gateway speech input is not configured.")
        self._update_prompt_placeholder()
        self._refresh_submission_state()

    def _update_prompt_placeholder(self) -> None:
        self.prompt_edit.setPlaceholderText("Ask anything or drop files here. The assistant will choose the right tools or media on the gateway.")

    def _refresh_submission_state(self) -> None:
        ready = self._controller.current_workflow() is not None
        tooltip = ""
        if not ready:
            tooltip = str(
                self._controller.workflow_status().error
                or "Configure the gateway connection so the published assistant workflow is available."
            ).strip()

        self.prompt_edit.setEnabled(ready)
        self.send_button.setEnabled(ready)
        self.attach_button.setEnabled(ready)
        if ready:
            self.prompt_edit.setToolTip("")
            self.send_button.setToolTip("")
        else:
            self.prompt_edit.setToolTip(tooltip)
            self.send_button.setToolTip(tooltip)

    def _notify(self, title: str, message: str) -> None:
        tray = self._tray
        if tray is None:
            return
        text = str(message or "").strip()
        if not text:
            return
        try:
            tray.showMessage(title, text[:180], QSystemTrayIcon.Information, 5000)
        except Exception:
            pass

    def _scroll_history_to_latest(self) -> None:
        self._apply_history_scroll_request(self._history_scroll_request(mode="bottom"))

    def _apply_styles(self) -> None:
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#0c1016"))
        palette.setColor(QPalette.Base, QColor("#161b23"))
        palette.setColor(QPalette.Text, QColor("#e8edf4"))
        self.setPalette(palette)
        self.setStyleSheet(
            """
            QMainWindow#assistantPalette, QWidget#rootSurface {
                background: transparent;
                color: #e8edf4;
                font-family: "SF Pro Text", "Helvetica Neue", Arial;
            }
            QFrame#topBarCard, QFrame#historyCard, QFrame#composerCard {
                background: rgba(16, 22, 31, 0.98);
                border: 1px solid rgba(166, 187, 214, 0.14);
                border-radius: 16px;
            }
            QFrame#composerCard[dropActive="true"] {
                background: rgba(19, 31, 28, 0.98);
                border-color: rgba(95, 211, 155, 0.52);
            }
            QFrame#controlBlock {
                background: transparent;
                border: none;
            }
            QLabel#windowTitle {
                color: #f6f8fb;
                font-size: 15px;
                font-weight: 700;
            }
            QFrame#connectionLed {
                border-radius: 4px;
                background: #6a7788;
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
            QFrame#connectionLed[state="connected"] {
                background: #38bf76;
                border-color: rgba(112, 224, 164, 0.56);
            }
            QFrame#connectionLed[state="disconnected"] {
                background: #d05252;
                border-color: rgba(255, 183, 183, 0.46);
            }
            QLabel#controlLabel {
                color: #71839a;
                font-size: 10px;
            }
            QLabel#bannerLabel {
                border-radius: 11px;
                padding: 7px 9px;
                border: 1px solid rgba(121, 199, 255, 0.24);
                background: rgba(67, 129, 185, 0.10);
                color: #b9dcff;
                font-size: 11px;
            }
            QLabel#bannerLabel[tone="warn"] {
                border-color: rgba(236, 195, 96, 0.26);
                background: rgba(181, 123, 22, 0.12);
                color: #f7d590;
            }
            QLabel#bannerLabel[tone="error"] {
                border-color: rgba(255, 121, 121, 0.24);
                background: rgba(145, 39, 39, 0.14);
                color: #ffb4b4;
            }
            QFrame#assistantBubble, QFrame#userBubble {
                border-radius: 16px;
                border: 1px solid rgba(166, 187, 214, 0.14);
                background: #1b2430;
            }
            QFrame#userBubble {
                background: #245f8f;
                border-color: rgba(151, 214, 255, 0.34);
            }
            QFrame#userBubble QLabel#messageRole,
            QFrame#userBubble QLabel#userMessageText {
                color: #f6fbff;
            }
            QLabel#messageRole {
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.08em;
                color: #9bb0c6;
            }
            QLabel#messageTimestamp {
                color: rgba(183, 196, 210, 0.72);
                font-size: 10px;
            }
            QLabel#thinkingDots {
                color: #9bb0c6;
                font-size: 16px;
                font-weight: 700;
                letter-spacing: 0.18em;
            }
            QTextBrowser#assistantMessageText, QLabel#assistantMessageTextLabel, QLabel#userMessageText {
                color: #edf2f8;
                font-size: 13px;
                line-height: 1.45;
            }
            QLabel#assistantMessageTextLabel {
                color: #edf2f8;
            }
            QLabel#userMessageText {
                color: #f6fbff;
            }
            QPushButton#messageActionButton {
                min-height: 24px;
                max-height: 24px;
                min-width: 24px;
                max-width: 24px;
                padding: 0px;
                border-radius: 12px;
                border: none;
                background: rgba(255, 255, 255, 0.05);
            }
            QPushButton#messageActionButton:hover {
                background: rgba(255, 255, 255, 0.12);
            }
            QPushButton#messageActionButton:checked {
                background: rgba(83, 198, 145, 0.18);
                border: 1px solid rgba(83, 198, 145, 0.28);
            }
            QLabel#metricChip {
                padding: 2px 7px;
                border-radius: 9px;
                background: rgba(255, 255, 255, 0.06);
                color: #a8bad0;
                font-size: 10px;
                font-weight: 600;
            }
            QFrame#assistantHtmlActionBar {
                background: transparent;
                border: none;
            }
            QPushButton#assistantHtmlActionButton {
                min-height: 30px;
                padding: 0 12px;
                border-radius: 10px;
                border: 1px solid rgba(114, 196, 255, 0.24);
                background: rgba(39, 98, 142, 0.30);
                color: #f6fbff;
                font-size: 11px;
                font-weight: 700;
                text-align: left;
            }
            QPushButton#assistantHtmlActionButton:hover {
                background: rgba(51, 116, 166, 0.42);
                border-color: rgba(132, 210, 255, 0.40);
            }
            QPushButton#assistantHtmlActionButton:pressed {
                background: rgba(33, 82, 119, 0.52);
            }
            QFrame#mediaPreviewCard, QFrame#inlineMediaPlayer {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(166, 187, 214, 0.12);
                border-radius: 12px;
                padding: 6px;
            }
            QLabel#mediaPreviewTitle {
                color: #eaf1f8;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#mediaTitleIcon {
                background: transparent;
                border: none;
            }
            QLabel#mediaPreviewStatus {
                color: #9fb0c4;
                font-size: 10px;
            }
            QLabel#mediaTransportMeta {
                color: #9fb0c4;
                font-size: 10px;
                font-weight: 600;
                min-width: 66px;
            }
            QPushButton#mediaImageButton {
                min-height: 112px;
                max-height: 156px;
                padding: 0px;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(166, 187, 214, 0.10);
            }
            QPushButton#mediaImageButton:hover {
                background: rgba(255, 255, 255, 0.06);
                border-color: rgba(121, 199, 255, 0.30);
            }
            QWidget#mediaVideoPreview {
                background: #0d1117;
                border-radius: 10px;
            }
            QPushButton#mediaTransportButton, QPushButton#mediaIconButton, QPushButton#mediaOpenButton {
                min-height: 28px;
                max-height: 28px;
                min-width: 28px;
                max-width: 28px;
                border-radius: 14px;
                padding: 0px;
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(166, 187, 214, 0.12);
                color: #eef4fb;
            }
            QPushButton#mediaOpenButton {
                min-width: 56px;
                max-width: 90px;
                border-radius: 9px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#mediaTransportButton:hover, QPushButton#mediaIconButton:hover, QPushButton#mediaOpenButton:hover {
                background: rgba(255, 255, 255, 0.12);
                border-color: rgba(121, 199, 255, 0.28);
            }
            QPushButton#mediaTransportButton:disabled {
                background: rgba(255, 255, 255, 0.03);
                border-color: rgba(166, 187, 214, 0.08);
            }
            QSlider#mediaPlayerSlider::groove:horizontal {
                height: 4px;
                background: rgba(255, 255, 255, 0.12);
                border-radius: 2px;
            }
            QSlider#mediaPlayerSlider::sub-page:horizontal {
                background: #79c7ff;
                border-radius: 2px;
            }
            QSlider#mediaPlayerSlider::handle:horizontal {
                width: 10px;
                margin: -4px 0;
                border-radius: 5px;
                background: #eef6ff;
            }
            QPushButton#artifactChip {
                min-height: 24px;
                border-radius: 10px;
                padding: 2px 8px;
                background: rgba(121, 199, 255, 0.10);
                border-color: rgba(121, 199, 255, 0.18);
                color: #c8e7ff;
                font-size: 11px;
                font-weight: 600;
            }
            QScrollArea#attachmentsTray, QWidget#attachmentsTrayHost {
                background: transparent;
                border: none;
            }
            QLabel#attachmentsDropHint {
                color: #9dd6bc;
                font-size: 11px;
                font-weight: 600;
                padding-top: 2px;
            }
            QFrame#attachmentIconChip {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(166, 187, 214, 0.14);
                border-radius: 11px;
            }
            QFrame#attachmentIconChip[hovered="true"] {
                background: rgba(255, 255, 255, 0.10);
                border-color: rgba(121, 199, 255, 0.34);
            }
            QLabel#attachmentIconGlyph {
                background: transparent;
                border: none;
            }
            QPushButton#attachmentRemoveButton {
                min-height: 16px;
                max-height: 16px;
                min-width: 16px;
                max-width: 16px;
                padding: 0px;
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.14);
                background: rgba(219, 88, 88, 0.92);
            }
            QPushButton#attachmentRemoveButton:hover {
                background: rgba(236, 108, 108, 0.98);
            }
            #dialogTitle, #routeLabel {
                font-weight: 700;
                font-size: 15px;
                color: #f4f7fb;
            }
            #routeHelp { color: #96a3b6; }
            QPushButton {
                min-height: 34px;
                border-radius: 11px;
                padding: 7px 13px;
                border: 1px solid rgba(166, 187, 214, 0.20);
                background: #1c2430;
                color: #f3f7fb;
                font-weight: 700;
            }
            QPushButton:hover { background: #243041; }
            QPushButton:pressed { background: #131922; }
            QPushButton#secondaryButton {
                background: #171d25;
                color: #dfe8f3;
                border-color: rgba(166, 187, 214, 0.16);
            }
            QPushButton#secondaryButton:hover { background: #202833; }
            QPushButton#secondaryButton:pressed { background: #141a22; }
            QPushButton#trafficButton {
                min-height: 12px;
                max-height: 12px;
                min-width: 12px;
                max-width: 12px;
                padding: 0px;
                border-radius: 6px;
                border: 1px solid rgba(0, 0, 0, 0.16);
                background: #7d8795;
            }
            QPushButton#trafficButton[tone="close"] {
                background: #ff5f57;
                border-color: #e0443e;
            }
            QPushButton#trafficButton[tone="minimize"] {
                background: #febc2e;
                border-color: #dea123;
            }
            QPushButton#trafficButton[tone="zoom"] {
                background: #28c840;
                border-color: #1fa332;
            }
            QPushButton#trafficButton:hover {
                border-color: rgba(0, 0, 0, 0.24);
            }
            QPushButton#trafficButton:pressed {
                background: rgba(255, 255, 255, 0.22);
            }
            QPushButton#iconButton, QPushButton#composerIconButton {
                min-height: 24px;
                max-height: 24px;
                min-width: 24px;
                max-width: 24px;
                padding: 0px;
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.04);
                border-color: rgba(166, 187, 214, 0.12);
                color: #dde6f0;
            }
            QPushButton#iconButton:hover, QPushButton#composerIconButton:hover {
                background: rgba(255, 255, 255, 0.09);
            }
            QPushButton#iconButton:pressed, QPushButton#composerIconButton:pressed {
                background: rgba(255, 255, 255, 0.05);
            }
            QPushButton#composerIconButton:checked {
                background: rgba(83, 198, 145, 0.18);
                border-color: rgba(83, 198, 145, 0.32);
            }
            QPushButton#sendButton {
                min-height: 38px;
                max-height: 38px;
                min-width: 38px;
                max-width: 38px;
                padding: 0px;
                border-radius: 12px;
                background: #2e8b63;
                color: #f9fffc;
                border-color: #2e8b63;
            }
            QPushButton#sendButton:hover { background: #37a272; }
            QPushButton#sendButton:pressed { background: #236749; }
            QPushButton#topToggleButton {
                min-height: 28px;
                max-height: 28px;
                border-radius: 14px;
                padding: 4px 11px;
                background: rgba(255, 255, 255, 0.04);
                border-color: rgba(166, 187, 214, 0.12);
                color: #dfe7f2;
                font-weight: 600;
            }
            QPushButton#topToggleButton:hover {
                background: rgba(255, 255, 255, 0.09);
            }
            QPushButton#topToggleButton:pressed {
                background: rgba(255, 255, 255, 0.05);
            }
            QPushButton#topToggleButton:checked {
                background: rgba(83, 198, 145, 0.18);
                border-color: rgba(83, 198, 145, 0.30);
                color: #e9fff4;
            }
            QPushButton#topIconToggleButton {
                min-height: 24px;
                max-height: 24px;
                min-width: 24px;
                max-width: 24px;
                padding: 0px;
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.04);
                border-color: rgba(166, 187, 214, 0.12);
                color: #dfe7f2;
            }
            QPushButton#topIconToggleButton:hover {
                background: rgba(255, 255, 255, 0.09);
            }
            QPushButton#topIconToggleButton:pressed {
                background: rgba(255, 255, 255, 0.05);
            }
            QPushButton#topIconToggleButton:checked {
                background: rgba(83, 198, 145, 0.18);
                border-color: rgba(83, 198, 145, 0.30);
            }
            QComboBox, QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QSpinBox {
                border-radius: 10px;
                border: 1px solid rgba(166, 187, 214, 0.16);
                background: #181e27;
                color: #e8edf4;
                padding: 6px 9px;
            }
            QComboBox:disabled, QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QListWidget:disabled, QSpinBox:disabled {
                color: #6f7b8d;
                background: #141920;
            }
            QComboBox, QLineEdit, QSpinBox {
                min-height: 30px;
                max-height: 30px;
            }
            QComboBox:hover, QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QListWidget:hover, QSpinBox:hover {
                border-color: rgba(121, 199, 255, 0.36);
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background: #181e27;
                color: #e8edf4;
                border: 1px solid rgba(166, 187, 214, 0.18);
                selection-background-color: #243041;
                border-radius: 10px;
                padding: 6px;
            }
            QTextEdit#promptEdit {
                font-size: 12px;
                line-height: 1.2;
                padding: 1px 4px;
            }
            QTextEdit#promptEdit[dropActive="true"] {
                background: rgba(23, 44, 38, 0.94);
                border-color: rgba(95, 211, 155, 0.50);
            }
            QScrollArea#historyScroll {
                border: none;
                background: transparent;
            }
            QWidget#historyHost {
                background: transparent;
            }
            QScrollBar:vertical {
                width: 10px;
                background: transparent;
                margin: 6px 0 6px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.14);
                border-radius: 5px;
                min-height: 28px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
                height: 0px;
            }
            QLabel#historyStatusLabel {
                color: #b9c7d7;
                font-weight: 600;
                font-size: 11px;
                padding: 2px 7px;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.04);
            }
            QLabel#historyStatusLabel[tone="busy"] {
                color: #f0c979;
                background: rgba(181, 123, 22, 0.12);
            }
            QLabel#historyStatusLabel[tone="error"] {
                color: #ffb7b7;
                background: rgba(145, 39, 39, 0.14);
            }
            QLabel#historyStatusLabel[tone="info"] {
                color: #8bd8b1;
                background: rgba(83, 198, 145, 0.12);
            }
            """
        )


def json_dumps(value: Dict[str, Any]) -> str:
    if not value:
        return ""
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


def _handle_tray_activation(*, palette, menu: Optional[QMenu], reason) -> None:
    if reason == QSystemTrayIcon.Context:
        if menu is not None:
            try:
                menu.popup(QCursor.pos())
            except Exception:
                pass
        return
    if reason in {QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick}:
        try:
            palette.show_palette()
        except Exception:
            pass


def launch_tray_app(*, config: Optional[Config] = None, debug: bool = False, data_dir: Optional[Path] = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("AbstractAssistant")
    app.setWindowIcon(_qt_icon())

    controller = AssistantV2Controller(config=config, data_dir=data_dir, debug=debug)
    palette = AssistantPalette(controller=controller, debug=debug)

    tray = QSystemTrayIcon(_qt_icon(), app)
    tray.setToolTip("AbstractAssistant")
    menu = QMenu()
    menu.addAction("Show", palette.show_palette)
    menu.addAction("Hide", palette.hide)
    menu.addAction("New Session", palette._create_session)
    menu.addAction("Settings", palette._open_settings)
    menu.addSeparator()
    menu.addAction("Quit", app.quit)
    palette._tray_menu = menu
    tray.activated.connect(lambda reason: _handle_tray_activation(palette=palette, menu=menu, reason=reason))
    tray.show()
    palette.attach_tray(tray)
    palette.hide()
    return app.exec_()
