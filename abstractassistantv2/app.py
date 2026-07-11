"""Qt-only tray shell for AbstractAssistant v2."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
import html as _html
from html.parser import HTMLParser
import mimetypes
import math
import os
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

from PyQt5.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QTextCursor,
)
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
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

try:
    import AppKit
    import objc
    from Foundation import NSObject

    _MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE = sys.platform == "darwin"
except Exception:  # pragma: no cover - macOS-only enhancement
    AppKit = None  # type: ignore[assignment]
    objc = None  # type: ignore[assignment]
    NSObject = object  # type: ignore[misc,assignment]
    _MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE = False

from abstractassistant.config import Config, DEFAULT_GATEWAY_URL
from abstractassistant.core.file_activity import (
    FileOperation,
    distinct_file_count,
    file_operations_from_tool_calls,
)
from abstractassistant.core.tool_display import (
    compact_tool_call_label,
    compact_tool_call_label_html,
)
from abstractassistant.gateway.tool_usage import (
    extract_tool_call_details_from_scratchpad,
)
from abstractassistant.utils.icon_generator import IconGenerator
from abstractassistant.utils.markdown_renderer import (
    MarkdownRenderer,
    split_markdown_mermaid_blocks,
)

from .controller import AssistantV2Controller
from .gateway import ROUTE_SPECS, CapabilityRouteRow
from .hotkey import GlobalHotkeyManager
from .preferences import AssistantPreferences

_HTML_ACTION_FENCE_RE = re.compile(
    r"```(?:html|x-html|xml)[^\n]*\n(.*?)```", flags=re.I | re.S
)
_TRAY_BUSY_FRAME_COUNT = 36
_TRAY_BUSY_FRAME_INTERVAL_MS = 60
_TRAY_FEEDBACK_ICON_SIZE = 44
_TRAY_VISIBILITY_RETRY_DELAYS_MS = (0, 180, 720, 1600)
_ZOOMED_SHELL_GROWTH = 1.4


def _qt_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return int(getattr(value, "value", 0) or 0)


def _qt_key(name: str) -> int:
    key = getattr(Qt, name, None)
    if key is None and hasattr(Qt, "Key"):
        key = getattr(Qt.Key, name)
    return _qt_int(key)


def _qt_keyboard_modifier(name: str) -> int:
    modifier = getattr(Qt, name, None)
    if modifier is None and hasattr(Qt, "KeyboardModifier"):
        modifier = getattr(Qt.KeyboardModifier, name)
    return _qt_int(modifier)


def _text_cursor_move_operation(name: str):
    operation = getattr(QTextCursor, name, None)
    if operation is None and hasattr(QTextCursor, "MoveOperation"):
        operation = getattr(QTextCursor.MoveOperation, name)
    return operation


def _prompt_navigation_modifiers_are_plain(modifiers: Any) -> bool:
    # Some keyboards report arrow keys with KeypadModifier; keep that as plain navigation.
    return (_qt_int(modifiers) & ~_qt_keyboard_modifier("KeypadModifier")) == 0


def _handle_text_edit_edge_navigation(editor: QTextEdit, key: int) -> bool:
    cursor = editor.textCursor()
    if cursor.hasSelection():
        return False

    normalized_key = _qt_int(key)
    viewport_rect = editor.viewport().rect()
    if normalized_key == _qt_key("Key_Up"):
        probe = QTextCursor(cursor)
        if probe.movePosition(_text_cursor_move_operation("Up")):
            if editor.cursorRect(probe).center().y() >= viewport_rect.top():
                return False
        cursor.movePosition(_text_cursor_move_operation("Start"))
        editor.setTextCursor(cursor)
        return True
    if normalized_key == _qt_key("Key_Down"):
        probe = QTextCursor(cursor)
        if probe.movePosition(_text_cursor_move_operation("Down")):
            if editor.cursorRect(probe).center().y() <= viewport_rect.bottom():
                return False
        cursor.movePosition(_text_cursor_move_operation("End"))
        editor.setTextCursor(cursor)
        return True
    return False


@dataclass(frozen=True)
class HistoryScrollRequest:
    mode: str = "preserve"
    message_key: str = ""
    offset: int = 0


@dataclass(frozen=True)
class TrayVisibilityState:
    available: bool = True
    qt_visible: bool = False
    native_item_count: int = -1
    native_button_size: tuple[int, int] = (0, 0)
    native_image_size: tuple[int, int] = (0, 0)
    error: str = ""

    @property
    def ready(self) -> bool:
        if sys.platform == "darwin":
            return (
                self.native_item_count > 0
                and self.native_button_size[0] > 0
                and self.native_button_size[1] > 0
                and self.native_image_size[0] > 0
                and self.native_image_size[1] > 0
            )
        return bool(self.qt_visible)


@dataclass(frozen=True)
class AssistantHtmlAction:
    label: str
    href: str


@dataclass(frozen=True)
class ToolCallSummary:
    name: str
    reason: str
    parameters: List[tuple[str, str]]
    raw_text: str


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


def _tool_call_arguments(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return dict(arguments)
    text = str(arguments or "").strip()
    if not text:
        return {}
    if not text.startswith("{"):
        return {}
    try:
        import json

        parsed = json.loads(text)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _tool_call_value_summary(name: str, value: Any) -> str:
    key = str(name or "").strip().lower()
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        count = len(value)
        label = "entry" if count == 1 else "entries"
        return f"object with {count} {label}"
    if isinstance(value, list):
        count = len(value)
        label = "item" if count == 1 else "items"
        return f"list with {count} {label}"

    text = str(value or "").strip()
    if not text:
        return "empty"

    lowered = text.lower()
    looks_like_html = (
        "<html" in lowered
        or lowered.startswith("<!doctype html")
        or lowered.startswith("<div")
    )
    has_newlines = "\n" in text or "\r" in text
    if (
        key in {"content", "body", "text", "html", "script"}
        or has_newlines
        or len(text) > 120
    ):
        kind = "HTML content" if looks_like_html else "text content"
        return f"{kind}, {len(text):,} chars"
    if len(text) > 96:
        return f"{text[:93]}..."
    return text


def _tool_call_reason(name: str, arguments: Dict[str, Any]) -> str:
    tool = str(name or "").strip()
    normalized = tool.lower()
    path = str(
        arguments.get("file_path")
        or arguments.get("filepath")
        or arguments.get("path")
        or arguments.get("file")
        or arguments.get("target")
        or ""
    ).strip()
    cmd = str(arguments.get("cmd") or arguments.get("command") or "").strip()
    url = str(arguments.get("url") or arguments.get("href") or "").strip()
    query = str(
        arguments.get("q") or arguments.get("query") or arguments.get("prompt") or ""
    ).strip()

    if normalized == "write_file" and path:
        return f"Create or replace `{path}`."
    if normalized in {"read_file", "open_file"} and path:
        return f"Read `{path}`."
    if normalized in {"edit_file", "update_file"} and path:
        return f"Modify `{path}`."
    if normalized == "apply_patch":
        return "Apply a patch to one or more local files."
    if normalized in {"execute_command", "run_command"} and cmd:
        return f"Run `{cmd}`."
    if normalized in {"list_files", "search_files"} and path:
        return f"Inspect files under `{path}`."
    if normalized in {"fetch_url", "open_url", "open_browser"} and url:
        return f"Open or fetch `{url}`."
    if normalized in {"web_search", "search_web"} and query:
        return f"Search the web for `{query}`."
    if normalized.startswith("write"):
        return "Write or create local content."
    if normalized.startswith("read"):
        return "Read local content."
    if normalized.startswith("list") or normalized.startswith("search"):
        return "Inspect available resources."
    if normalized.startswith("execute") or normalized.startswith("run"):
        return "Run a command."
    return f"Call `{tool or '<unknown>'}` with the parameters below."


def _tool_call_summary(call: Any) -> ToolCallSummary:
    if not isinstance(call, dict):
        return ToolCallSummary(
            name="<unknown>",
            reason="The workflow requested a tool call, but the payload was not structured.",
            parameters=[],
            raw_text=str(call or ""),
        )
    name = str(call.get("name") or "<unknown>").strip() or "<unknown>"
    arguments = _tool_call_arguments(call.get("arguments"))
    raw_text = _tool_calls_text([call]).strip()
    parameter_rows: List[tuple[str, str]] = []
    if arguments:
        for key, value in arguments.items():
            label = str(key or "").strip()
            if not label:
                continue
            parameter_rows.append((label, _tool_call_value_summary(label, value)))
    elif call.get("arguments") not in {None, "", {}}:
        parameter_rows.append(
            ("arguments", _tool_call_value_summary("arguments", call.get("arguments")))
        )
    return ToolCallSummary(
        name=name,
        reason=_tool_call_reason(name, arguments),
        parameters=parameter_rows,
        raw_text=raw_text,
    )


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
        color: #edf2f8 !important;
        font-size: 13px !important;
        line-height: 1.45 !important;
    }
    .markdown-content p {
        margin: 0 0 8px 0 !important;
    }
    .markdown-content ul,
    .markdown-content ol {
        margin: 0 0 8px 0 !important;
        padding-left: 18px !important;
    }
    .markdown-content ul ul,
    .markdown-content ul ol,
    .markdown-content ol ul,
    .markdown-content ol ol {
        margin: 3px 0 0 0 !important;
        padding-left: 10px !important;
    }
    .markdown-content ul ul {
        list-style-type: circle !important;
    }
    .markdown-content ul ul ul {
        list-style-type: square !important;
    }
    .markdown-content li {
        margin-bottom: 3px !important;
    }
    .markdown-content li p {
        margin: 0 !important;
    }
    .markdown-content li ul,
    .markdown-content li ol {
        margin-top: 3px !important;
    }
    .markdown-content code {
        background: #232c3a !important;
        color: #eef4fb !important;
        font-size: inherit !important;
        line-height: inherit !important;
        padding: 2px 6px !important;
        border-radius: 5px !important;
    }
    .markdown-content pre,
    .codehilite {
        background: transparent !important;
        color: #edf2f8 !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        font-size: inherit !important;
        line-height: 1.55 !important;
    }
    .markdown-content pre code {
        background: transparent !important;
        color: inherit !important;
        padding: 0 !important;
        border-radius: 0 !important;
        font-size: inherit !important;
        line-height: inherit !important;
    }
    .markdown-content a {
        color: #79c7ff !important;
    }
    .markdown-content img {
        max-width: 100% !important;
        width: auto !important;
        height: auto !important;
        max-height: 168px !important;
        border-radius: 10px !important;
    }
    .markdown-content .mermaid-diagram img {
        width: 100% !important;
        max-width: 100% !important;
        height: auto !important;
        max-height: none !important;
        border-radius: 0 !important;
    }
    .markdown-content table:not(.codepanel) {
        width: 100% !important;
        table-layout: auto !important;
        border-collapse: collapse !important;
        border-spacing: 0 !important;
        margin: 4px 0 2px 0 !important;
        background: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }
    .markdown-content table:not(.codepanel) td,
    .markdown-content table:not(.codepanel) th {
        padding: 6px 10px !important;
        overflow-wrap: anywhere !important;
        word-break: break-word !important;
        white-space: normal !important;
        vertical-align: top !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
    }
    .markdown-content table:not(.codepanel) th {
        font-size: 11px !important;
        font-weight: 700 !important;
        line-height: 1.3 !important;
        background: rgba(255, 255, 255, 0.04) !important;
    }
    .markdown-content table:not(.codepanel) td {
        font-size: 11px !important;
        line-height: 1.3 !important;
    }
    .markdown-content table:not(.codepanel) tr:nth-child(even) td {
        background: rgba(255, 255, 255, 0.02) !important;
    }
    .markdown-content table.codepanel {
        width: 100% !important;
        margin: 8px 0 10px 0 !important;
        border: none !important;
        background: transparent !important;
    }
    .markdown-content table.codepanel td,
    .markdown-content table.codepanel th {
        font-size: 13px !important;
        line-height: 1.45 !important;
        padding: 0 !important;
        border: none !important;
        white-space: normal !important;
        overflow-wrap: anywhere !important;
        word-break: break-word !important;
        vertical-align: top !important;
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


def _user_html(content: str) -> str:
    import html

    escaped = html.escape(content.strip())
    themed_override = (
        "<style>"
        ".user-content {"
        "  color: #ffffff !important;"
        "  font-size: 13px !important;"
        "  line-height: 1.45 !important;"
        "  white-space: pre-wrap !important;"
        "  text-align: left !important;"
        "  margin: 0px !important;"
        "  padding: 0px !important;"
        "}"
        "</style>"
        '<div class="user-content" align="left">'
    )
    return themed_override + escaped + "</div>"


def _assistant_action_href_allowed(href: Any) -> bool:
    text = str(href or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    scheme = str(parsed.scheme or "").strip().lower()
    if scheme in {"javascript", "vbscript"}:
        return False
    return scheme in {"http", "https", "mailto", "data", "file"}


def _session_picker_date_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "--/--/--"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%y/%m/%d")
    except Exception:
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
        if match:
            year, month, day = match.groups()
            return f"{year[-2:]}/{month}/{day}"
    return "--/--/--"


def _session_picker_topic(value: Any, *, limit: int = 58) -> str:
    text = " ".join(
        str(value or "").replace("\r", " ").replace("\n", " ").split()
    ).strip()
    if not text:
        return "New session"
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)].rstrip()}…"


def _session_picker_label(session: Dict[str, Any]) -> str:
    stamp = session.get("created_at") or session.get("updated_at") or ""
    topic = _session_picker_topic(session.get("title"))
    return f"{_session_picker_date_label(stamp)} - {topic}"


def _session_picker_tooltip(session: Dict[str, Any]) -> str:
    title = " ".join(
        str(session.get("title") or "New session")
        .replace("\r", " ")
        .replace("\n", " ")
        .split()
    ).strip()
    title = title or "New session"
    created = str(session.get("created_at") or "").strip()
    updated = str(session.get("updated_at") or "").strip()
    lines = [title]
    if created:
        lines.append(f"Created: {created}")
    if updated and updated != created:
        lines.append(f"Updated: {updated}")
    return "\n".join(lines)


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


def _assistant_content_with_actions(
    content: str,
) -> tuple[str, List[AssistantHtmlAction]]:
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


def _assistant_content_blocks(
    content: str,
) -> tuple[List[Dict[str, str]], List[AssistantHtmlAction]]:
    cleaned, actions = _assistant_content_with_actions(content)
    blocks: List[Dict[str, str]] = []
    for block in split_markdown_mermaid_blocks(cleaned):
        if block.kind == "mermaid" and block.data_uri:
            blocks.append(
                {"kind": "mermaid", "text": block.text, "data_uri": block.data_uri}
            )
            continue
        text = str(block.text or "")
        if text:
            blocks.append({"kind": "markdown", "text": text, "data_uri": ""})
    if not blocks:
        blocks.append({"kind": "markdown", "text": "", "data_uri": ""})
    return blocks, actions


def _open_external_href(href: str) -> bool:
    text = str(href or "").strip()
    if not _assistant_action_href_allowed(text):
        return False
    try:
        return bool(QDesktopServices.openUrl(QUrl.fromEncoded(text.encode("utf-8"))))
    except Exception:
        return False


def _qt_icon() -> QIcon:
    generator = IconGenerator(size=44)
    image = generator.create_app_icon(color_scheme="green", animated=False)
    path = Path.home() / ".abstractassistant" / "v2_tray_icon.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    pixmap = QPixmap(str(path))
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


_ICON_CACHE: Dict[tuple[str, str, int], QIcon] = {}
_TRAY_ICON_CACHE: Dict[tuple[str, int, int], QIcon] = {}


def _zoomed_shell_size(
    *, screen_width: int, screen_height: int, normal_width: int, normal_height: int
) -> tuple[int, int]:
    base_width = min(
        max(int(screen_width * 0.50), max(760, normal_width + 140)),
        int(screen_width * 0.62),
    )
    base_height = min(
        max(int(screen_height * 0.56), max(420, normal_height + 72)),
        int(screen_height * 0.72),
    )
    width = min(
        max(
            int(round(base_width * _ZOOMED_SHELL_GROWTH)), max(960, normal_width + 260)
        ),
        int(screen_width * 0.86),
    )
    height = min(
        max(
            int(round(base_height * _ZOOMED_SHELL_GROWTH)),
            max(588, normal_height + 160),
        ),
        int(screen_height * 0.92),
    )
    return max(420, width), max(320, height)


def _tray_feedback_icon(
    *, state: str = "idle", frame: int = 0, size: int = _TRAY_FEEDBACK_ICON_SIZE
) -> QIcon:
    normalized_state = str(state or "idle").strip().lower() or "idle"
    normalized_frame = int(frame or 0) % _TRAY_BUSY_FRAME_COUNT
    key = (normalized_state, normalized_frame, int(size))
    cached = _TRAY_ICON_CACHE.get(key)
    if cached is not None:
        return cached

    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    center = QPointF(size / 2.0, size / 2.0)

    def _ring(*, radius: float, width: float, color: QColor, alpha: int) -> None:
        pen = QPen(QColor(color.red(), color.green(), color.blue(), alpha))
        pen.setWidthF(width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, radius, radius)

    def _orb(*, radius: float, color: QColor, alpha: int) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), alpha))
        painter.drawEllipse(center, radius, radius)

    def _gradient_disc(
        *,
        radius: float,
        inner: QColor,
        mid: QColor,
        edge: QColor,
        gloss_alpha: int = 130,
        shadow_alpha: int = 44,
    ) -> None:
        fill = QRadialGradient(
            center.x() - (radius * 0.46),
            center.y() - (radius * 0.54),
            radius * 1.8,
            center.x() - (radius * 0.58),
            center.y() - (radius * 0.64),
        )
        fill.setColorAt(0.0, inner)
        fill.setColorAt(0.46, mid)
        fill.setColorAt(1.0, edge)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(fill))
        painter.drawEllipse(center, radius, radius)

        shadow = QLinearGradient(
            center.x(), center.y() - radius, center.x(), center.y() + radius
        )
        shadow.setColorAt(0.0, QColor(0, 0, 0, 0))
        shadow.setColorAt(0.56, QColor(0, 0, 0, 0))
        shadow.setColorAt(1.0, QColor(5, 10, 18, shadow_alpha))
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(center, radius, radius)

        gloss = QRadialGradient(
            center.x() - (radius * 0.58),
            center.y() - (radius * 0.72),
            radius * 1.05,
        )
        gloss.setColorAt(0.0, QColor(255, 255, 255, gloss_alpha))
        gloss.setColorAt(0.34, QColor(255, 255, 255, int(gloss_alpha * 0.42)))
        gloss.setColorAt(0.78, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(gloss))
        painter.drawEllipse(
            QPointF(center.x() - (radius * 0.16), center.y() - (radius * 0.26)),
            radius * 0.60,
            radius * 0.48,
        )

    def _state_disc(
        *,
        inner: QColor,
        mid: QColor,
        edge: QColor,
        ring: QColor,
        ring_alpha: int = 150,
        glow: Optional[QColor] = None,
        glow_alpha: int = 44,
    ) -> None:
        if glow is not None:
            glow_gradient = QRadialGradient(center, size * 0.47)
            glow_gradient.setColorAt(
                0.68, QColor(glow.red(), glow.green(), glow.blue(), 0)
            )
            glow_gradient.setColorAt(
                1.0, QColor(glow.red(), glow.green(), glow.blue(), glow_alpha)
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow_gradient))
            painter.drawEllipse(center, size * 0.47, size * 0.47)
        _gradient_disc(radius=size * 0.39, inner=inner, mid=mid, edge=edge)
        _ring(radius=size * 0.425, width=size * 0.092, color=ring, alpha=ring_alpha)

    def _arc(
        *,
        radius: float,
        width: float,
        color: QColor,
        start_deg: float,
        span_deg: float,
        alpha: int = 235,
        glow_alpha: int = 84,
    ) -> None:
        rect = QRectF(
            center.x() - radius, center.y() - radius, radius * 2.0, radius * 2.0
        )
        for width_scale, stroke_alpha in ((1.45, glow_alpha), (1.0, alpha)):
            pen = QPen(QColor(color.red(), color.green(), color.blue(), stroke_alpha))
            pen.setWidthF(width * width_scale)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(rect, int(-start_deg * 16), int(-span_deg * 16))

    if normalized_state == "busy":
        phase = float(normalized_frame) / float(_TRAY_BUSY_FRAME_COUNT)
        loop = phase * math.tau
        sweep = math.degrees(loop + (0.14 * math.sin(loop * 2.0)))
        pulse = 0.5 + (0.5 * math.sin((loop * 1.45) - 0.55))
        pendulum = 34.0 * math.sin((loop * 1.30) + 0.2)
        recoil = 13.0 * math.sin((loop * 2.9) + 0.85)
        shimmer = 10.0 * math.sin((loop * 4.0) - 0.3)
        _state_disc(
            inner=QColor("#c9f3ff"),
            mid=QColor("#3aa9ff"),
            edge=QColor("#0f5fda"),
            ring=QColor("#b8ecff"),
            ring_alpha=int(118 + (26 * pulse)),
            glow=QColor("#52bbff"),
            glow_alpha=int(28 + (22 * pulse)),
        )
        _ring(
            radius=size * 0.272,
            width=size * 0.050,
            color=QColor("#ddf6ff"),
            alpha=int(24 + (30 * pulse)),
        )
        _arc(
            radius=size * 0.415,
            width=size * 0.084,
            color=QColor("#f2fbff"),
            start_deg=18.0 + sweep + (pendulum * 0.38),
            span_deg=118.0 + (10.0 * pulse),
            alpha=242,
            glow_alpha=96,
        )
        _arc(
            radius=size * 0.308,
            width=size * 0.066,
            color=QColor("#d9f4ff"),
            start_deg=198.0 + pendulum + recoil,
            span_deg=84.0 + (12.0 * (1.0 - pulse)),
            alpha=232,
            glow_alpha=86,
        )
        _arc(
            radius=size * 0.228,
            width=size * 0.054,
            color=QColor("#b8eaff"),
            start_deg=262.0 - (sweep * 0.82) + (recoil * 0.95) + shimmer,
            span_deg=64.0 + (9.0 * math.sin((loop * 2.35) + 0.45)),
            alpha=212,
            glow_alpha=64,
        )
        _orb(
            radius=size * (0.068 + (0.008 * pulse)), color=QColor("#ffffff"), alpha=255
        )
        orbit_theta = math.radians(sweep + (22.0 * math.sin(loop * 2.7)) - 42.0)
        orbit_distance = size * (0.17 + (0.03 * pulse))
        orbit_center = QPointF(
            center.x() + (math.cos(orbit_theta) * orbit_distance),
            center.y() + (math.sin(orbit_theta) * orbit_distance),
        )
        painter.setPen(Qt.NoPen)
        orbit_glow = QRadialGradient(orbit_center, size * 0.11)
        orbit_glow.setColorAt(0.0, QColor(255, 255, 255, 230))
        orbit_glow.setColorAt(0.45, QColor(203, 242, 255, 150))
        orbit_glow.setColorAt(1.0, QColor(144, 214, 255, 0))
        painter.setBrush(QBrush(orbit_glow))
        painter.drawEllipse(orbit_center, size * 0.078, size * 0.078)
        painter.setBrush(QColor("#effcff"))
        painter.drawEllipse(orbit_center, size * 0.047, size * 0.047)
    elif normalized_state == "complete":
        mint = QColor("#2ccf9b")
        gold = QColor("#ffd36c")
        _state_disc(
            inner=QColor("#cffff0"),
            mid=mint,
            edge=QColor("#11856a"),
            ring=QColor("#8bf0c9"),
            ring_alpha=142,
            glow=QColor("#4fdbaf"),
            glow_alpha=30,
        )
        pen = QPen(gold)
        pen.setWidthF(size * 0.074)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        for dx1, dy1, dx2, dy2 in (
            (0.0, -0.18, 0.0, 0.18),
            (-0.18, 0.0, 0.18, 0.0),
            (-0.12, -0.12, 0.12, 0.12),
            (-0.12, 0.12, 0.12, -0.12),
        ):
            painter.drawLine(
                QPointF(center.x() + (dx1 * size), center.y() + (dy1 * size)),
                QPointF(center.x() + (dx2 * size), center.y() + (dy2 * size)),
            )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#fff4cf"))
        painter.drawEllipse(
            QPointF(center.x() + (size * 0.19), center.y() - (size * 0.19)),
            size * 0.050,
            size * 0.050,
        )
    else:
        _state_disc(
            inner=QColor("#c8ffd2"),
            mid=QColor("#46d978"),
            edge=QColor("#177d46"),
            ring=QColor("#c7ffd3"),
            ring_alpha=156,
            glow=QColor("#63ea8f"),
            glow_alpha=28,
        )
        link_pen = QPen(QColor(242, 255, 246, 74))
        link_pen.setWidthF(size * 0.040)
        link_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(link_pen)
        for start_dx, start_dy, end_dx, end_dy in (
            (0.0, 0.0, -0.20, -0.15),
            (0.0, 0.0, 0.20, -0.13),
            (0.0, 0.0, 0.14, 0.20),
        ):
            painter.drawLine(
                QPointF(center.x() + (start_dx * size), center.y() + (start_dy * size)),
                QPointF(center.x() + (end_dx * size), center.y() + (end_dy * size)),
            )
        painter.setPen(Qt.NoPen)
        for dx, dy, radius, color in (
            (0.0, 0.0, 0.078, QColor("#f5fff7")),
            (-0.20, -0.15, 0.050, QColor("#ffffff")),
            (0.20, -0.13, 0.046, QColor("#f8fff9")),
            (0.14, 0.20, 0.048, QColor("#e6fff0")),
        ):
            painter.setBrush(color)
            painter.drawEllipse(
                QPointF(center.x() + (dx * size), center.y() + (dy * size)),
                size * radius,
                size * radius,
            )

    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    icon = QIcon(pixmap)
    _TRAY_ICON_CACHE[key] = icon
    return icon


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
    pen.setWidthF(max(1.5, size * 0.085))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    # Translucent tint color for modern dual-tone fills
    translucent_brush = QBrush(QColor(tint.red(), tint.green(), tint.blue(), 25))

    def _line(x1: float, y1: float, x2: float, y2: float) -> None:
        painter.drawLine(QPointF(x1 * size, y1 * size), QPointF(x2 * size, y2 * size))

    if key[0] == "plus":
        _line(0.50, 0.22, 0.50, 0.78)
        _line(0.22, 0.50, 0.78, 0.50)
    elif key[0] == "sliders":
        for y, knob_x in ((0.28, 0.66), (0.50, 0.34), (0.72, 0.58)):
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            _line(0.18, y, 0.82, y)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(tint))
            painter.drawEllipse(
                QPointF(knob_x * size, y * size), size * 0.08, size * 0.08
            )
    elif key[0] == "paperclip":
        path = QPainterPath()
        path.moveTo(size * 0.48, size * 0.48)
        path.lineTo(size * 0.48, size * 0.34)
        path.arcTo(QRectF(size * 0.38, size * 0.24, size * 0.20, size * 0.20), 0, 180)
        path.lineTo(size * 0.38, size * 0.64)
        path.arcTo(QRectF(size * 0.38, size * 0.54, size * 0.32, size * 0.24), 180, 180)
        path.lineTo(size * 0.70, size * 0.32)
        path.arcTo(QRectF(size * 0.50, size * 0.16, size * 0.20, size * 0.20), 0, 180)
        path.lineTo(size * 0.50, size * 0.52)
        painter.drawPath(path)
    elif key[0] == "mic":
        painter.setBrush(translucent_brush)
        painter.drawRoundedRect(
            QRectF(size * 0.35, size * 0.15, size * 0.30, size * 0.42),
            size * 0.15,
            size * 0.15,
        )
        painter.setBrush(Qt.NoBrush)
        _line(0.50, 0.62, 0.50, 0.82)
        _line(0.34, 0.82, 0.66, 0.82)
        path = QPainterPath()
        path.moveTo(size * 0.22, size * 0.42)
        path.arcTo(QRectF(size * 0.22, size * 0.28, size * 0.56, size * 0.34), 180, 180)
        painter.drawPath(path)
    elif key[0] == "send":
        path = QPainterPath()
        path.moveTo(size * 0.88, size * 0.12)
        path.lineTo(size * 0.16, size * 0.48)
        path.lineTo(size * 0.48, size * 0.52)
        path.lineTo(size * 0.52, size * 0.84)
        path.closeSubpath()
        painter.setBrush(translucent_brush)
        painter.drawPath(path)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        _line(0.48, 0.52, 0.88, 0.12)
    elif key[0] == "gear":
        painter.drawEllipse(QRectF(size * 0.38, size * 0.38, size * 0.24, size * 0.24))
        painter.drawEllipse(QRectF(size * 0.26, size * 0.26, size * 0.48, size * 0.48))
        teeth_pen = QPen(tint)
        teeth_pen.setWidthF(size * 0.11)
        teeth_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(teeth_pen)
        for idx in range(8):
            angle = idx * 45 * 3.14159265 / 180
            x1 = 0.50 + math.cos(angle) * 0.22
            y1 = 0.50 + math.sin(angle) * 0.22
            x2 = 0.50 + math.cos(angle) * 0.35
            y2 = 0.50 + math.sin(angle) * 0.35
            _line(x1, y1, x2, y2)
    elif key[0] == "copy":
        painter.drawRoundedRect(
            QRectF(size * 0.36, size * 0.20, size * 0.42, size * 0.48),
            size * 0.08,
            size * 0.08,
        )
        painter.setBrush(QBrush(QColor(9, 13, 22, 255)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(
            QRectF(size * 0.20, size * 0.32, size * 0.42, size * 0.48),
            size * 0.08,
            size * 0.08,
        )
        painter.setBrush(Qt.NoBrush)
        painter.setPen(pen)
        painter.drawRoundedRect(
            QRectF(size * 0.20, size * 0.32, size * 0.42, size * 0.48),
            size * 0.08,
            size * 0.08,
        )
    elif key[0] == "close":
        _line(0.30, 0.30, 0.70, 0.70)
        _line(0.70, 0.30, 0.30, 0.70)
    elif key[0] == "stop":
        painter.setBrush(translucent_brush)
        painter.drawRoundedRect(
            QRectF(size * 0.28, size * 0.28, size * 0.44, size * 0.44),
            size * 0.08,
            size * 0.08,
        )
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            QRectF(size * 0.28, size * 0.28, size * 0.44, size * 0.44),
            size * 0.08,
            size * 0.08,
        )
    elif key[0] == "external":
        box_path = QPainterPath()
        box_path.moveTo(size * 0.44, size * 0.24)
        box_path.lineTo(size * 0.24, size * 0.24)
        box_path.lineTo(size * 0.24, size * 0.76)
        box_path.lineTo(size * 0.76, size * 0.76)
        box_path.lineTo(size * 0.76, size * 0.56)
        painter.drawPath(box_path)
        _line(0.48, 0.52, 0.76, 0.24)
        _line(0.60, 0.24, 0.76, 0.24)
        _line(0.76, 0.24, 0.76, 0.40)
    elif key[0].startswith("file"):
        kind = "generic"
        if "-" in key[0]:
            kind = key[0].split("-", 1)[1] or "generic"
        page = QPainterPath()
        page.moveTo(size * 0.24, size * 0.16)
        page.lineTo(size * 0.56, size * 0.16)
        page.lineTo(size * 0.76, size * 0.36)
        page.lineTo(size * 0.76, size * 0.84)
        page.lineTo(size * 0.24, size * 0.84)
        page.closeSubpath()
        painter.setBrush(translucent_brush)
        painter.drawPath(page)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(page)
        _line(0.56, 0.16, 0.56, 0.36)
        _line(0.56, 0.36, 0.76, 0.36)

        if kind == "image":
            painter.drawRoundedRect(
                QRectF(size * 0.34, size * 0.46, size * 0.32, size * 0.22),
                size * 0.04,
                size * 0.04,
            )
            painter.drawEllipse(
                QPointF(size * 0.42, size * 0.51), size * 0.03, size * 0.03
            )
            peak = QPainterPath()
            peak.moveTo(size * 0.36, size * 0.66)
            peak.lineTo(size * 0.46, size * 0.54)
            peak.lineTo(size * 0.52, size * 0.60)
            peak.lineTo(size * 0.58, size * 0.50)
            peak.lineTo(size * 0.64, size * 0.66)
            painter.drawPath(peak)
        elif kind == "audio":
            _line(0.44, 0.44, 0.44, 0.66)
            _line(0.44, 0.44, 0.62, 0.40)
            _line(0.62, 0.40, 0.62, 0.62)
            _line(0.44, 0.48, 0.62, 0.44)
            painter.setBrush(QBrush(tint))
            painter.drawEllipse(
                QPointF(size * 0.39, size * 0.66), size * 0.05, size * 0.04
            )
            painter.drawEllipse(
                QPointF(size * 0.57, size * 0.62), size * 0.05, size * 0.04
            )
            painter.setBrush(Qt.NoBrush)
        elif kind == "video":
            painter.drawRoundedRect(
                QRectF(size * 0.34, size * 0.44, size * 0.32, size * 0.22),
                size * 0.04,
                size * 0.04,
            )
            path = QPainterPath()
            path.moveTo(size * 0.46, size * 0.50)
            path.lineTo(size * 0.56, size * 0.55)
            path.lineTo(size * 0.46, size * 0.60)
            path.closeSubpath()
            painter.setBrush(QBrush(tint))
            painter.drawPath(path)
            painter.setBrush(Qt.NoBrush)
        elif kind == "code":
            _line(0.38, 0.54, 0.44, 0.48)
            _line(0.38, 0.54, 0.44, 0.60)
            _line(0.62, 0.54, 0.56, 0.48)
            _line(0.62, 0.54, 0.56, 0.60)
            _line(0.52, 0.44, 0.48, 0.64)
        elif kind == "archive":
            painter.drawRoundedRect(
                QRectF(size * 0.36, size * 0.44, size * 0.28, size * 0.24),
                size * 0.03,
                size * 0.03,
            )
            _line(0.36, 0.50, 0.64, 0.50)
            _line(0.36, 0.56, 0.64, 0.56)
            _line(0.36, 0.62, 0.64, 0.62)
        elif kind == "data":
            painter.drawRoundedRect(
                QRectF(size * 0.34, size * 0.42, size * 0.32, size * 0.12),
                size * 0.06,
                size * 0.06,
            )
            painter.drawRoundedRect(
                QRectF(size * 0.34, size * 0.56, size * 0.32, size * 0.12),
                size * 0.06,
                size * 0.06,
            )
        else:
            _line(0.36, 0.48, 0.64, 0.48)
            _line(0.36, 0.58, 0.64, 0.58)
            _line(0.36, 0.68, 0.54, 0.68)
    elif key[0] == "speaker":
        path = QPainterPath()
        path.moveTo(size * 0.22, size * 0.38)
        path.lineTo(size * 0.36, size * 0.38)
        path.lineTo(size * 0.54, size * 0.22)
        path.lineTo(size * 0.54, size * 0.78)
        path.lineTo(size * 0.36, size * 0.62)
        path.lineTo(size * 0.22, size * 0.62)
        path.closeSubpath()
        painter.setBrush(translucent_brush)
        painter.drawPath(path)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        wave1 = QPainterPath()
        wave1.moveTo(size * 0.64, size * 0.40)
        wave1.quadTo(size * 0.72, size * 0.50, size * 0.64, size * 0.60)
        painter.drawPath(wave1)
        wave2 = QPainterPath()
        wave2.moveTo(size * 0.72, size * 0.30)
        wave2.quadTo(size * 0.84, size * 0.50, size * 0.72, size * 0.70)
        painter.drawPath(wave2)
    elif key[0] == "pause":
        painter.setBrush(QBrush(tint))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(
            QRectF(size * 0.30, size * 0.24, size * 0.12, size * 0.52),
            size * 0.05,
            size * 0.05,
        )
        painter.drawRoundedRect(
            QRectF(size * 0.58, size * 0.24, size * 0.12, size * 0.52),
            size * 0.05,
            size * 0.05,
        )
    elif key[0] == "play":
        path = QPainterPath()
        path.moveTo(size * 0.34, size * 0.24)
        path.lineTo(size * 0.76, size * 0.50)
        path.lineTo(size * 0.34, size * 0.76)
        path.closeSubpath()
        painter.setBrush(QBrush(tint))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)
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
                QPointF(
                    center.x() + radius * math.cos(angle),
                    center.y() + radius * math.sin(angle),
                ),
                dot_radius,
                dot_radius,
            )
    elif key[0] == "spark":
        path = QPainterPath()
        path.moveTo(size * 0.50, size * 0.15)
        path.quadTo(size * 0.50, size * 0.50, size * 0.85, size * 0.50)
        path.quadTo(size * 0.50, size * 0.50, size * 0.50, size * 0.85)
        path.quadTo(size * 0.50, size * 0.50, size * 0.15, size * 0.50)
        path.quadTo(size * 0.50, size * 0.50, size * 0.50, size * 0.15)
        painter.setBrush(translucent_brush)
        painter.drawPath(path)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    elif key[0] == "check":
        _line(0.24, 0.54, 0.44, 0.74)
        _line(0.44, 0.74, 0.78, 0.30)
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
    if (
        parsed["input_tokens"] == 0
        and parsed["output_tokens"] == 0
        and parsed["total_tokens"] == 0
    ):
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
    for key in (
        "duration_ms",
        "elapsed_ms",
        "total_ms",
        "processing_ms",
        "generation_ms",
    ):
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


def _format_metric_count(value: int) -> str:
    try:
        return f"{max(0, int(value or 0)):,}"
    except Exception:
        return "0"


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
        return dt.strftime("%I:%M %p")
    if (now.date() - dt.date()).days == 1:
        return f"Yesterday {dt.strftime('%I:%M %p')}"
    return dt.strftime("%b %d · %I:%M %p")


def _message_bubble_width(viewport_width: int, *, role: str) -> int:
    width = max(0, int(viewport_width or 0))
    # Both assistant and user bubbles set to 80% of the available panel width
    return max(96, int(width * 0.80))


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
    if content_type.startswith("image/") or suffix in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
        ".heic",
        ".heif",
        ".svg",
    }:
        return "image"
    if content_type.startswith("audio/") or suffix in {
        ".wav",
        ".mp3",
        ".m4a",
        ".aac",
        ".ogg",
        ".flac",
        ".aiff",
        ".aif",
        ".opus",
    }:
        return "audio"
    if content_type.startswith("video/") or suffix in {
        ".mp4",
        ".mov",
        ".m4v",
        ".webm",
        ".mkv",
        ".avi",
        ".mpeg",
        ".mpg",
    }:
        return "video"
    if suffix in {
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".kt",
        ".go",
        ".rs",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".rb",
        ".php",
        ".swift",
        ".html",
        ".css",
        ".scss",
        ".sql",
        ".sh",
        ".bash",
        ".zsh",
    }:
        return "code"
    if suffix in {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}:
        return "archive"
    if suffix in {
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".xml",
        ".parquet",
        ".sqlite",
        ".db",
        ".xls",
        ".xlsx",
    }:
        return "data"
    if content_type.startswith("text/") or suffix in {
        ".txt",
        ".md",
        ".pdf",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".rtf",
    }:
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
    artifact_id = str(
        artifact.get("$artifact") or artifact.get("artifact_id") or ""
    ).strip()
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
    filename = (
        str(
            artifact.get("filename")
            or artifact.get("local_path")
            or artifact.get("path")
            or ""
        )
        .strip()
        .lower()
    )

    if (
        content_type.startswith("image/")
        or modality == "image"
        or filename.endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff")
        )
    ):
        return "image"
    if (
        content_type.startswith("video/")
        or modality == "video"
        or filename.endswith((".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"))
    ):
        return "video"
    if (
        content_type.startswith("audio/")
        or modality == "audio"
        or filename.endswith((".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"))
    ):
        return "audio"
    return "other"


def _artifact_label(artifact: Dict[str, Any]) -> str:
    filename = str(artifact.get("filename") or "").strip()
    if filename:
        return filename
    local_path = str(artifact.get("local_path") or artifact.get("path") or "").strip()
    if local_path:
        return Path(local_path).name or local_path
    artifact_id = str(
        artifact.get("$artifact") or artifact.get("artifact_id") or ""
    ).strip()
    return artifact_id or "artifact"


def _message_media_artifacts(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    metadata = (
        message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    )
    if not isinstance(metadata, dict):
        return []

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _push(
        candidate: Any, *, fallback_kind: str = "", fallback_content_type: str = ""
    ) -> None:
        if not isinstance(candidate, dict):
            return
        artifact_id = str(
            candidate.get("$artifact") or candidate.get("artifact_id") or ""
        ).strip()
        local_path = str(
            candidate.get("local_path") or candidate.get("path") or ""
        ).strip()
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
        _push(
            metadata.get(key),
            fallback_kind=fallback_kind,
            fallback_content_type=str(metadata.get("content_type") or ""),
        )

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
                fallback_content_type=str(
                    generated_media.get("content_type")
                    or metadata.get("content_type")
                    or ""
                ),
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


_IMAGE_PREVIEW_HEIGHT = 50
_IMAGE_PREVIEW_MAX_WIDTH = 220


def _image_thumbnail_size(
    size: QSize,
    *,
    height: int = _IMAGE_PREVIEW_HEIGHT,
    max_width: int = _IMAGE_PREVIEW_MAX_WIDTH,
) -> QSize:
    width = max(1, int(size.width() or 0))
    source_height = max(1, int(size.height() or 0))
    bounded_height = max(1, int(height or _IMAGE_PREVIEW_HEIGHT))
    bounded_width = max(1, int(max_width or _IMAGE_PREVIEW_MAX_WIDTH))
    scaled = QSize(width, source_height).scaled(
        bounded_width, bounded_height, Qt.KeepAspectRatio
    )
    return QSize(max(1, scaled.width()), max(1, scaled.height()))


def _message_key(message: Dict[str, Any]) -> str:
    message_id = str(message.get("message_id") or "").strip()
    metadata = (
        message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    )
    if not message_id and isinstance(metadata, dict):
        message_id = str(metadata.get("message_id") or "").strip()
    if message_id:
        return f"id:{message_id}"
    role = str(message.get("role") or "").strip()
    ts = str(message.get("ts") or message.get("timestamp") or "").strip()
    content = str(message.get("content") or "")
    return f"{role}|{ts}|{content}"


def _history_message_key(message: Dict[str, Any], *, fallback_index: int) -> str:
    message_id = str(message.get("message_id") or "").strip()
    metadata = (
        message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    )
    if not message_id and isinstance(metadata, dict):
        message_id = str(metadata.get("message_id") or "").strip()
    if message_id:
        return f"id:{message_id}"
    role = str(message.get("role") or "").strip()
    ts = str(message.get("ts") or message.get("timestamp") or "").strip()
    if ts:
        return f"{role}|{ts}|{max(0, int(fallback_index))}"
    return f"{role}|index:{max(0, int(fallback_index))}"


def _visible_history_messages(
    messages: List[Dict[str, Any]], *, busy: bool
) -> List[Dict[str, Any]]:
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


def _assistant_tool_calls_for_message(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    metadata = (
        message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    )
    candidates: List[Any] = []
    if isinstance(metadata, dict):
        stats_meta = metadata.get("_assistant_stats")
        if isinstance(stats_meta, dict):
            candidates.extend(
                [
                    stats_meta.get("tool_call_details"),
                    stats_meta.get("tool_calls_detail"),
                    stats_meta.get("tool_calls"),
                ]
            )
        repl = metadata.get("_repl")
        if isinstance(repl, dict):
            repl_stats = repl.get("stats")
            if isinstance(repl_stats, dict):
                candidates.extend(
                    [
                        repl_stats.get("tool_call_details"),
                        repl_stats.get("tool_calls_detail"),
                        repl_stats.get("tool_calls"),
                    ]
                )
        candidates.append(metadata.get("tool_calls"))
        scratchpad_calls = extract_tool_call_details_from_scratchpad(
            metadata.get("scratchpad"),
            run_id=str(metadata.get("run_id") or message.get("run_id") or "").strip(),
        )
        if scratchpad_calls:
            candidates.append(scratchpad_calls)

    for candidate in candidates:
        if isinstance(candidate, list):
            calls = [dict(call) for call in candidate if isinstance(call, dict)]
            if calls:
                return calls
    return []


def _tooltip_html(lines: List[str]) -> str:
    """Join lines into a rich-text tooltip (escaped, line-broken, wrappable)."""
    return "<br/>".join(_html.escape(line) for line in lines if str(line or "").strip())


_TOOLTIP_MAX_LINES = 14


def _capped_tooltip_lines(lines: List[str]) -> List[str]:
    if len(lines) <= _TOOLTIP_MAX_LINES:
        return lines
    hidden = len(lines) - (_TOOLTIP_MAX_LINES - 1)
    return lines[: _TOOLTIP_MAX_LINES - 1] + [f"... and {hidden} more"]


def _tokens_in_tooltip(usage: Dict[str, int], llm_calls: Optional[int]) -> str:
    lines = [
        "Input tokens sent to the model for this answer.",
        f"Exact: {_format_metric_count(usage['input_tokens'])} tokens",
    ]
    if llm_calls is not None and llm_calls > 0:
        plural = "s" if int(llm_calls) != 1 else ""
        lines.append(f"LLM calls: {_format_metric_count(llm_calls)} call{plural}")
    return _tooltip_html(lines)


def _tokens_out_tooltip(usage: Dict[str, int]) -> str:
    lines = [
        "Output tokens generated by the model for this answer.",
        f"Exact: {_format_metric_count(usage['output_tokens'])} tokens",
        f"Total (input + output): {_format_metric_count(usage['total_tokens'])} tokens",
    ]
    return _tooltip_html(lines)


def _tools_footer_tooltip(count: int, tool_calls: List[Dict[str, Any]]) -> str:
    if count <= 0:
        return _tooltip_html(["No tools were executed for this answer."])
    if not tool_calls:
        plural = "s" if int(count) != 1 else ""
        return _tooltip_html(
            [
                f"{count} tool call{plural} executed for this answer.",
                "Details are not attached to this message; click to load them from the run ledger.",
            ]
        )
    lines = ["Tools executed for this answer (click for details):"]
    for call in tool_calls:
        name = str(call.get("name") or "<unknown>").strip() or "<unknown>"
        reason = _tool_call_reason(name, _tool_call_arguments(call.get("arguments")))
        failed = call.get("success") is False
        suffix = "  [failed]" if failed else ""
        lines.append(f"\u2022 {name} \u2014 {reason}{suffix}")
    return _tooltip_html(_capped_tooltip_lines(lines))


_FILE_ACTION_LABELS = {
    "created": "Created",
    "modified": "Modified",
    "moved": "Moved",
    "deleted": "Deleted",
}


def _files_footer_tooltip(operations: List[FileOperation]) -> str:
    if not operations:
        return _tooltip_html(["No files were created, modified, moved or deleted."])
    lines = ["Files affected by this answer:"]
    for op in operations:
        action = _FILE_ACTION_LABELS.get(op.action, op.action.title())
        lines.append(f"\u2022 {action} \u2014 {op.label}")
    return _tooltip_html(_capped_tooltip_lines(lines))


def _assistant_footer_metrics(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    metadata = (
        message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    )
    metrics: List[Dict[str, Any]] = []
    usage = None
    duration_ms = None
    llm_calls = None
    tool_calls = None

    if isinstance(metadata, dict):
        usage = _parse_usage_summary(metadata.get("usage"))
        stats_meta = metadata.get("_assistant_stats")
        if isinstance(stats_meta, dict):
            usage = usage or _parse_usage_summary(
                stats_meta.get("usage")
                if isinstance(stats_meta.get("usage"), dict)
                else stats_meta.get("tokens")
            )
            duration_ms = _extract_duration_ms(stats_meta)
            llm_calls = _coerce_int(stats_meta.get("llm_calls"))
            tool_calls = _coerce_int(stats_meta.get("tool_calls"))
        repl = metadata.get("_repl")
        if isinstance(repl, dict):
            repl_stats = repl.get("stats")
            if isinstance(repl_stats, dict):
                usage = usage or _parse_usage_summary(
                    repl_stats.get("usage")
                    if isinstance(repl_stats.get("usage"), dict)
                    else repl_stats.get("tokens")
                )
                duration_ms = (
                    duration_ms
                    if duration_ms is not None
                    else _extract_duration_ms(repl_stats)
                )
                llm_calls = (
                    llm_calls
                    if llm_calls is not None
                    else _coerce_int(repl_stats.get("llm_calls"))
                )
                tool_calls = (
                    tool_calls
                    if tool_calls is not None
                    else _coerce_int(repl_stats.get("tool_calls"))
                )

    tool_call_details = _assistant_tool_calls_for_message(message)
    if tool_calls is None and tool_call_details:
        tool_calls = len(tool_call_details)

    if usage is not None:
        metrics.append(
            {
                "kind": "tokens_in",
                "label": f"input : {_format_metric_count(usage['input_tokens'])} tk",
                "plain": f"input : {_format_metric_count(usage['input_tokens'])} tk",
                "tooltip": _tokens_in_tooltip(usage, llm_calls),
                "clickable": False,
            }
        )
        metrics.append(
            {
                "kind": "tokens_out",
                "label": f"output : {_format_metric_count(usage['output_tokens'])} tk",
                "plain": f"output : {_format_metric_count(usage['output_tokens'])} tk",
                "tooltip": _tokens_out_tooltip(usage),
                "clickable": False,
            }
        )
    if tool_calls is not None:
        tools_label = f"tools : {_format_metric_count(tool_calls)}"
        metrics.append(
            {
                "kind": "tools",
                "label": tools_label,
                "plain": tools_label,
                "tooltip": _tools_footer_tooltip(int(tool_calls), tool_call_details),
                "clickable": bool(tool_calls > 0),
                "tool_calls": tool_call_details,
            }
        )
        # Files can only be reported honestly when the executed tool calls are
        # known: zero tools proves zero file changes, otherwise derive from the
        # attached details and omit the metric when details are unavailable.
        file_ops: Optional[List[FileOperation]] = None
        if int(tool_calls) == 0:
            file_ops = []
        elif tool_call_details:
            file_ops = file_operations_from_tool_calls(tool_call_details)
        if file_ops is not None:
            files_count = distinct_file_count(file_ops)
            files_label = f"files : {_format_metric_count(files_count)}"
            metrics.append(
                {
                    "kind": "files",
                    "label": files_label,
                    "plain": files_label,
                    "tooltip": _files_footer_tooltip(file_ops),
                    "clickable": bool(files_count > 0),
                    "file_operations": list(file_ops),
                }
            )
    if duration_ms is not None:
        duration = _format_duration_short(duration_ms)
        metrics.append(
            {
                "kind": "duration",
                "label": duration,
                "plain": duration,
                "tooltip": "Elapsed runtime for this answer",
                "clickable": False,
            }
        )

    provider = (
        str(metadata.get("provider") or "").strip()
        if isinstance(metadata, dict)
        else ""
    )
    model = (
        str(metadata.get("model") or "").strip() if isinstance(metadata, dict) else ""
    )
    if not metrics and (provider or model):
        label = " / ".join(part for part in (provider, model) if part)
        metrics.append(
            {
                "kind": "model",
                "label": label,
                "plain": label,
                "tooltip": "Model used",
                "clickable": False,
            }
        )
    elif metrics and model:
        metrics.append(
            {
                "kind": "model",
                "label": model,
                "plain": model,
                "tooltip": _tooltip_html(
                    ["Model used", " / ".join(part for part in (provider, model) if part)]
                ),
                "clickable": False,
            }
        )
    return metrics[:6]


def _assistant_footer_items(message: Dict[str, Any]) -> List[str]:
    return [
        str(item.get("plain") or item.get("label") or "").strip()
        for item in _assistant_footer_metrics(message)
    ]


def _assistant_file_operations_for_message(
    message: Dict[str, Any],
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> List[FileOperation]:
    """File mutations proven by a message's tool calls (cached or supplied)."""
    calls = tool_calls if tool_calls is not None else _assistant_tool_calls_for_message(message)
    return file_operations_from_tool_calls(calls)


DIRECT_CHAT_SYSTEM_PROMPT = (
    "You are AbstractAssistant, a concise desktop assistant. "
    "Use the conversation history and any uploaded files. "
    "When media is attached, analyze it directly or through gateway-configured multimodal routes. "
    "If something is unavailable, say so plainly."
)


class AutoSizingTextBrowser(QTextBrowser):
    def __init__(
        self,
        *,
        min_height: int = 34,
        max_height: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._min_height = int(min_height)
        self._max_height = (
            int(max_height) if isinstance(max_height, int) and max_height > 0 else None
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(True)
        self.document().setDocumentMargin(0)
        try:
            self.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
            )
        except Exception:
            pass

    def refresh_height(self, width: Optional[int] = None) -> None:
        if width is None:
            width = max(280, self.width() - 6)
        else:
            width = max(280, width)
        self.document().setTextWidth(width)
        height = int(self.document().size().height()) + 4
        bounded = max(self._min_height, height)
        if self._max_height is not None:
            bounded = min(self._max_height, bounded)
        self.setFixedHeight(bounded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(0, self.refresh_height)


class DampedScrollArea(QScrollArea):
    def __init__(
        self, *, factor: float = 0.7, parent: Optional[QWidget] = None
    ) -> None:
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
            step = (
                (angle_y / 120.0) * float(max(1, bar.singleStep())) * self._wheel_factor
            )
        if step > 0:
            step = max(1.0, step)
        elif step < 0:
            step = min(-1.0, step)
        bar.setValue(int(round(bar.value() - step)))
        event.accept()


class PannableScrollArea(DampedScrollArea):
    def __init__(
        self, *, factor: float = 0.7, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(factor=factor, parent=parent)
        self._drag_origin: Optional[QPoint] = None
        self.setWidgetResizable(False)
        self.viewport().installEventFilter(self)
        self.viewport().setCursor(Qt.ArrowCursor)

    def refresh_pan_state(self) -> None:
        if self._drag_origin is not None:
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        can_pan = (
            self.horizontalScrollBar().maximum() > 0
            or self.verticalScrollBar().maximum() > 0
        )
        self.viewport().setCursor(Qt.OpenHandCursor if can_pan else Qt.ArrowCursor)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.viewport():
            event_type = event.type()
            if event_type == QEvent.Enter:
                self.refresh_pan_state()
            elif (
                event_type == QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton
            ):
                if (
                    self.horizontalScrollBar().maximum() > 0
                    or self.verticalScrollBar().maximum() > 0
                ):
                    self._drag_origin = event.pos()
                    self.viewport().setCursor(Qt.ClosedHandCursor)
                    event.accept()
                    return True
            elif event_type == QEvent.MouseMove and self._drag_origin is not None:
                delta = event.pos() - self._drag_origin
                self.horizontalScrollBar().setValue(
                    self.horizontalScrollBar().value() - delta.x()
                )
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - delta.y()
                )
                self._drag_origin = event.pos()
                event.accept()
                return True
            elif (
                event_type in {QEvent.MouseButtonRelease, QEvent.Leave}
                and self._drag_origin is not None
            ):
                self._drag_origin = None
                self.refresh_pan_state()
                event.accept()
                return True
        return super().eventFilter(watched, event)


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

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = _qt_int(event.key())
        if (
            key in {_qt_key("Key_Up"), _qt_key("Key_Down")}
            and _prompt_navigation_modifiers_are_plain(event.modifiers())
            and _handle_text_edit_edge_navigation(self, key)
        ):
            event.accept()
            return
        super().keyPressEvent(event)

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
        icon = _symbol_icon(
            _attachment_icon_name(self._path),
            color=_attachment_icon_color(self._path),
            size=18,
        )
        icon_label.setPixmap(icon.pixmap(18, 18))
        root.addWidget(icon_label)

        remove_button = QPushButton(self)
        remove_button.setObjectName("attachmentRemoveButton")
        remove_button.setIcon(_symbol_icon("close", color="#f8fbff", size=10))
        remove_button.setIconSize(QSize(10, 10))
        remove_button.setToolTip("Remove attachment")
        remove_button.setFixedSize(16, 16)
        remove_button.clicked.connect(
            lambda _checked=False: self.remove_requested.emit(self._path)
        )
        remove_button.hide()
        self._remove_button = remove_button

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._remove_button.move(
            max(0, self.width() - self._remove_button.width() - 1), 1
        )

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


class ConnectionStatusOrb(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state = "unknown"
        self.setFixedSize(18, 18)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_state(self, state: str) -> None:
        normalized = str(state or "").strip().lower() or "unknown"
        if normalized == self._state:
            return
        self._state = normalized
        self.update()

    def _palette_colors(self) -> tuple[QColor, QColor, QColor, QColor]:
        if self._state == "connected":
            return (
                QColor("#32d47d"),
                QColor("#a9ffcf"),
                QColor("#0f6f3e"),
                QColor(114, 255, 183, 94),
            )
        if self._state == "disconnected":
            return (
                QColor("#ff6669"),
                QColor("#ffd5d7"),
                QColor("#8e2329"),
                QColor(255, 138, 141, 92),
            )
        return (
            QColor("#7a8aa0"),
            QColor("#e7eef9"),
            QColor("#354255"),
            QColor(178, 197, 224, 74),
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        base, highlight, shadow, ring = self._palette_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        halo_rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        halo = QRadialGradient(halo_rect.center(), halo_rect.width() * 0.5)
        halo.setColorAt(
            0.0,
            QColor(ring.red(), ring.green(), ring.blue(), min(255, ring.alpha() + 18)),
        )
        halo.setColorAt(0.62, ring)
        halo.setColorAt(1.0, QColor(ring.red(), ring.green(), ring.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(halo_rect)

        sphere_rect = QRectF(2.0, 2.0, self.width() - 4.0, self.height() - 4.0)
        fill = QRadialGradient(
            sphere_rect.center().x() - sphere_rect.width() * 0.18,
            sphere_rect.top() + sphere_rect.height() * 0.22,
            sphere_rect.width() * 0.82,
        )
        fill.setColorAt(0.0, highlight)
        fill.setColorAt(0.28, QColor(base).lighter(122))
        fill.setColorAt(0.72, base)
        fill.setColorAt(1.0, shadow)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(QColor(255, 255, 255, 54), 0.9))
        painter.drawEllipse(sphere_rect)

        lower_sheen = QLinearGradient(
            sphere_rect.left(),
            sphere_rect.top(),
            sphere_rect.left(),
            sphere_rect.bottom(),
        )
        lower_sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
        lower_sheen.setColorAt(0.68, QColor(255, 255, 255, 0))
        lower_sheen.setColorAt(1.0, QColor(0, 0, 0, 56))
        painter.setBrush(QBrush(lower_sheen))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(sphere_rect.adjusted(0.0, 0.5, 0.0, 0.0))

        painter.setBrush(QColor(255, 255, 255, 148))
        painter.drawEllipse(
            QRectF(
                sphere_rect.left() + sphere_rect.width() * 0.18,
                sphere_rect.top() + sphere_rect.height() * 0.14,
                sphere_rect.width() * 0.38,
                sphere_rect.height() * 0.28,
            )
        )
        painter.setBrush(QColor(255, 255, 255, 74))
        painter.drawEllipse(
            QRectF(
                sphere_rect.left() + sphere_rect.width() * 0.58,
                sphere_rect.top() + sphere_rect.height() * 0.28,
                sphere_rect.width() * 0.12,
                sphere_rect.height() * 0.12,
            )
        )
        painter.end()


if _MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE:

    class _MacTrafficLightTarget(NSObject):
        def initWithCallbacks_(self, callbacks):  # type: ignore[no-untyped-def]
            self = objc.super(_MacTrafficLightTarget, self).init()
            if self is None:
                return None
            self._callbacks = dict(callbacks or {})
            return self

        def onClose_(self, _sender) -> None:
            callback = self._callbacks.get("close")
            if callable(callback):
                callback()

        def onMinimize_(self, _sender) -> None:
            callback = self._callbacks.get("minimize")
            if callable(callback):
                callback()

        def onZoom_(self, _sender) -> None:
            callback = self._callbacks.get("zoom")
            if callable(callback):
                callback()

else:
    _MacTrafficLightTarget = None  # type: ignore[assignment]


class MacTrafficLightButtonsBridge:
    def __init__(
        self,
        *,
        owner: QWidget,
        anchor: QWidget,
        on_close: Callable[[], None],
        on_minimize: Callable[[], None],
        on_zoom: Callable[[], None],
    ) -> None:
        self._owner = owner
        self._anchor = anchor
        self._callbacks = {
            "close": on_close,
            "minimize": on_minimize,
            "zoom": on_zoom,
        }
        self._buttons: List[Any] = []
        self._host_view = None
        self._source_window = None
        self._target = None

    def available(self) -> bool:
        return bool(
            _MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE
            and AppKit is not None
            and objc is not None
        )

    def sync_geometry(self) -> bool:
        if not self.available():
            return False
        if not self._anchor.isVisible():
            return False
        if not self._ensure_attached():
            return False
        if self._host_view is None or not self._buttons:
            return False

        central = self._owner.centralWidget() or self._owner
        top_left = self._anchor.mapTo(central, QPoint(0, 0))
        host_height = float(self._host_view.frame().size.height)
        host_flipped = bool(self._host_view.isFlipped())
        current_x = float(top_left.x())
        spacing = 6.0
        anchor_height = max(1, self._anchor.height())

        for button in self._buttons:
            frame = button.frame()
            button_height = float(frame.size.height)
            qt_y = float(
                top_left.y() + max(0, int(round((anchor_height - button_height) / 2.0)))
            )
            frame.origin.x = current_x
            if host_flipped:
                frame.origin.y = max(0.0, qt_y)
            else:
                frame.origin.y = max(0.0, host_height - qt_y - button_height)
            button.setFrame_(frame)
            button.setHidden_(False)
            current_x += float(frame.size.width) + spacing
        return True

    def _ensure_attached(self) -> bool:
        if not self.available():
            return False
        try:
            host_view = objc.objc_object(c_void_p=int(self._owner.winId()))
        except Exception:
            return False
        if host_view is None:
            return False
        if not self._buttons and not self._create_buttons():
            return False
        for button in self._buttons:
            try:
                button.removeFromSuperview()
            except Exception:
                pass
            try:
                host_view.addSubview_(button)
            except Exception:
                return False
        self._host_view = host_view
        return True

    def _create_buttons(self) -> bool:
        if not self.available() or AppKit is None or _MacTrafficLightTarget is None:
            return False
        try:
            _app = AppKit.NSApp() or AppKit.NSApplication.sharedApplication()
            del _app
            titled = int(getattr(AppKit, "NSWindowStyleMaskTitled", 1 << 0))
            closable = int(getattr(AppKit, "NSWindowStyleMaskClosable", 1 << 1))
            minimizable = int(
                getattr(AppKit, "NSWindowStyleMaskMiniaturizable", 1 << 2)
            )
            resizable = int(getattr(AppKit, "NSWindowStyleMaskResizable", 1 << 3))
            style_mask = titled | closable | minimizable | resizable
            source_window = (
                AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                    AppKit.NSMakeRect(0, 0, 120, 64),
                    style_mask,
                    AppKit.NSBackingStoreBuffered,
                    False,
                )
            )
            source_window.setReleasedWhenClosed_(False)
            target = _MacTrafficLightTarget.alloc().initWithCallbacks_(self._callbacks)
            buttons = [
                source_window.standardWindowButton_(AppKit.NSWindowCloseButton),
                source_window.standardWindowButton_(AppKit.NSWindowMiniaturizeButton),
                source_window.standardWindowButton_(AppKit.NSWindowZoomButton),
            ]
            selectors = (b"onClose:", b"onMinimize:", b"onZoom:")
            for button, selector in zip(buttons, selectors):
                if button is None:
                    return False
                button.setTarget_(target)
                button.setAction_(selector)
            self._source_window = source_window
            self._target = target
            self._buttons = list(buttons)
            return True
        except Exception:
            self._source_window = None
            self._target = None
            self._buttons = []
            return False


class AssistantHtmlActionBar(QFrame):
    def __init__(
        self, *, actions: List[AssistantHtmlAction], parent: Optional[QWidget] = None
    ) -> None:
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
            button.clicked.connect(
                lambda _checked=False, href=action.href: _open_external_href(href)
            )
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
        on_show_tools=None,
        on_show_files=None,
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
        self._spinner_icons = [
            _symbol_icon(f"spinner{idx}", color="#f0c979", size=15) for idx in range(8)
        ]
        self._spinner_frame = 0
        self._copy_button = None
        self._voice_button = None
        self._voice_spinner = None
        self._content = str(message.get("content") or "")
        self._content_blocks, self._html_actions = _assistant_content_blocks(
            self._content
        )
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
        bubble_layout.setContentsMargins(12, 10, 12, 10)
        # User bubbles stay tight (timestamp hugs the text; the copy header has
        # its own internal padding), assistant bubbles keep block breathing room.
        bubble_layout.setSpacing(0 if is_user else 4)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        bubble_layout.addLayout(header_row)
        header_row.addStretch(1)

        if not is_user and callable(on_toggle_voice):
            voice_button = QPushButton()
            voice_button.setObjectName("messageActionButton")
            voice_button.setCheckable(True)
            try:
                voice_button.setFocusPolicy(Qt.NoFocus)
            except Exception:
                pass
            voice_button.setIconSize(QSize(15, 15))
            voice_button.setFixedSize(24, 24)
            voice_button.setToolTip("Listen to this response / Toggle voice output")
            voice_button.clicked.connect(
                lambda _checked=False, m=message: on_toggle_voice(m)
            )
            header_row.addWidget(voice_button)
            self._voice_button = voice_button
            self._apply_voice_button_state(str(voice_state or "").strip())

        copy_button = QPushButton()
        copy_button.setObjectName("messageActionButton")
        try:
            copy_button.setFocusPolicy(Qt.NoFocus)
        except Exception:
            pass
        copy_button.setIcon(self._copy_icon)
        copy_button.setIconSize(QSize(15, 15))
        copy_button.setFixedSize(24, 24)
        copy_button.setToolTip("Copy message")
        copy_button.clicked.connect(self._copy_message)
        header_row.addWidget(copy_button)
        self._copy_button = copy_button

        if is_user:
            browser = AutoSizingTextBrowser(min_height=20, max_height=None)
            browser.setObjectName("userMessageText")
            browser.setStyleSheet(
                "background: transparent; border: none; color: #ffffff; padding: 0px; margin: 0px;"
            )
            browser.setHtml(_user_html(self._content))
            browser.refresh_height()
            bubble_layout.addWidget(browser)
        else:
            for block in self._content_blocks:
                kind = str(block.get("kind") or "").strip().lower()
                if kind == "mermaid":
                    preview = MermaidPreviewCard(
                        source=str(block.get("text") or ""),
                        data_uri=str(block.get("data_uri") or ""),
                        bubble_width=max(180, int(bubble_width or 0) - 24),
                        parent=bubble,
                    )
                    bubble_layout.addWidget(preview, 0, Qt.AlignLeft)
                    continue
                rendered_text = str(block.get("text") or "")
                if not rendered_text.strip():
                    continue
                browser = AutoSizingTextBrowser(min_height=28, max_height=None)
                browser.setObjectName("assistantMessageText")
                browser.setStyleSheet(
                    "background: transparent; border: none; color: #e8edf4; padding: 0px; margin: 0px;"
                )
                browser.setHtml(_assistant_html(renderer, rendered_text))
                browser.refresh_height()
                bubble_layout.addWidget(browser)

        if self._html_actions:
            bubble_layout.addWidget(
                AssistantHtmlActionBar(actions=self._html_actions, parent=bubble)
            )

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
                open_button.clicked.connect(
                    lambda _checked=False, art=dict(artifact): on_open_artifact(
                        art, message
                    )
                )
                artifact_row.addWidget(open_button, 0, Qt.AlignLeft)
                artifact_row.addStretch(1)
                bubble_layout.addLayout(artifact_row)

        if not is_user:
            footer_metrics = _assistant_footer_metrics(message)
            if footer_metrics:
                footer_row = QHBoxLayout()
                footer_row.setContentsMargins(0, 2, 0, 0)
                footer_row.setSpacing(5)
                first_segment = True
                for metric in footer_metrics:
                    label = str(metric.get("label") or "").strip()
                    if not label:
                        continue
                    if not first_segment:
                        separator = QLabel("|")
                        separator.setObjectName("metricSeparator")
                        footer_row.addWidget(separator)
                    first_segment = False
                    kind = str(metric.get("kind") or "")
                    handler = None
                    if bool(metric.get("clickable")):
                        if kind == "tools" and callable(on_show_tools):
                            handler = on_show_tools
                        elif kind == "files" and callable(on_show_files):
                            handler = on_show_files
                    if handler is not None:
                        chip = QPushButton(label)
                        chip.setCursor(QCursor(Qt.PointingHandCursor))
                        chip.clicked.connect(
                            lambda _checked=False, m=message, h=handler: h(m)
                        )
                        try:
                            chip.setFocusPolicy(Qt.NoFocus)
                        except Exception:
                            pass
                    else:
                        chip = QLabel(label)
                    chip.setObjectName("metricChip")
                    chip.setProperty(
                        "kind", str(metric.get("kind") or "metric").strip() or "metric"
                    )
                    chip.setToolTip(str(metric.get("tooltip") or label))
                    footer_row.addWidget(chip)
                footer_row.addStretch(1)
                bubble_layout.addLayout(footer_row)

        ts_val = message.get("ts") or message.get("timestamp")
        if not ts_val:
            import datetime as dt_module

            ts_val = dt_module.datetime.now(dt_module.timezone.utc).isoformat()
        timestamp = _format_message_timestamp(ts_val)
        if timestamp:
            stamp_row = QHBoxLayout()
            stamp_row.setContentsMargins(0, 0 if is_user else 2, 2, 0)
            stamp_row.setSpacing(0)
            stamp_row.addStretch(1)
            stamp = QLabel(timestamp)
            stamp.setObjectName("messageTimestamp")
            stamp_row.addWidget(stamp)
            bubble_layout.addLayout(stamp_row)

        if is_user:
            bubble_row.addStretch(1)
            bubble_row.addWidget(bubble)
        else:
            bubble_row.addWidget(bubble)
            bubble_row.addStretch(1)

    def set_bubble_width(self, bubble_width: int) -> None:
        bubble = getattr(self, "_bubble", None)
        if bubble is None:
            return
        width_val = max(96, int(bubble_width or 0))
        bubble.setFixedWidth(width_val)
        for browser in self.findChildren(AutoSizingTextBrowser):
            browser.refresh_height(width_val - 24)
        for preview in self.findChildren(MermaidPreviewCard):
            preview.set_bubble_width(width_val - 24)

    def sync_to_viewport_width(self, viewport_width: int) -> None:
        self.set_bubble_width(_message_bubble_width(viewport_width, role=self._role))

    def set_voice_state(self, state: str) -> None:
        self._apply_voice_button_state(str(state or "").strip())

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
            button.setIcon(
                self._spinner_icons[self._spinner_frame % len(self._spinner_icons)]
            )
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
    if (
        candidate
        and len(candidate) >= 24
        and re.fullmatch(r"[A-Fa-f0-9_-]{24,}", candidate)
    ):
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


def _subprocess_audio_player_command(
    path: Path, *, offset_ms: int = 0
) -> Optional[List[str]]:
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
    def __init__(
        self, *, kind: str, path: Path, title: str, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._kind = str(kind or "").strip().lower()
        self._path = Path(path)
        self._title = _media_display_title(
            title=title, kind=self._kind, path=self._path
        )
        self._duration_ms = (
            _probe_media_duration_ms(self._path)
            if self._kind in {"audio", "video"}
            else 0
        )
        self._seeking = False
        self._position_ms = 0
        self._process = None
        self._process_paused = False
        self._process_offset_ms = 0
        self._process_started_at = 0.0
        self._process_backend = (
            self._kind == "audio"
            and _subprocess_audio_player_command(self._path, offset_ms=0) is not None
        )
        self._play_icon = _symbol_icon("play", color="#f4f8fc", size=14)
        self._pause_icon = _symbol_icon("pause", color="#f4f8fc", size=14)
        self._open_icon = _symbol_icon("external", color="#a9bbcf", size=13)
        self._kind_icon = _symbol_icon(
            "file-audio" if self._kind == "audio" else "file-video",
            color="#77d1a8" if self._kind == "audio" else "#f0c979",
            size=14,
        )
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

        if (
            not self._process_backend
            and QT_MULTIMEDIA_AVAILABLE
            and QMediaPlayer is not None
            and QMediaContent is not None
        ):
            try:
                self._player = QMediaPlayer(self)
                self._player.setMedia(
                    QMediaContent(QUrl.fromLocalFile(str(self._path)))
                )
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
        self._play_button.setToolTip("Play/Pause audio or video playback")
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
            process = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
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

    def _stop_process_playback(
        self, *, reset: bool, keep_position: Optional[int] = None
    ) -> None:
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
        elapsed_ms = int(
            (time.monotonic() - float(self._process_started_at or time.monotonic()))
            * 1000.0
        )
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
            if (
                self._process is not None
                and self._process.poll() is None
                and not self._process_paused
            ):
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
        total = (
            _format_media_time(self._duration_ms) if self._duration_ms > 0 else "--:--"
        )
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


_MERMAID_PREVIEW_MAX_WIDTH = 860
_MERMAID_INLINE_MIN_HEIGHT = 140
_MERMAID_INLINE_MAX_HEIGHT = 420
_MERMAID_INLINE_MIN_ZOOM = 0.25
_MERMAID_INLINE_MAX_ZOOM = 4.0
_MERMAID_INLINE_MIN_RENDER_SCALE = 0.02
_MERMAID_INLINE_MAX_RENDER_SCALE = 8.0
_MERMAID_ZOOM_STEP = 1.18


def _pixmap_from_data_uri(data_uri: str) -> QPixmap:
    text = str(data_uri or "").strip()
    if not text.startswith("data:image/"):
        return QPixmap()
    _, _, payload = text.partition(",")
    if not payload:
        return QPixmap()
    try:
        raw = base64.b64decode(payload)
    except Exception:
        return QPixmap()
    pixmap = QPixmap()
    if not pixmap.loadFromData(raw):
        return QPixmap()
    return pixmap


class MermaidPreviewCard(QFrame):
    def __init__(
        self,
        *,
        source: str,
        data_uri: str,
        bubble_width: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._source = str(source or "")
        self._pixmap = _pixmap_from_data_uri(data_uri)
        self._bubble_width = max(220, int(bubble_width or 0))
        self._zoom_multiplier = 1.0
        self.setObjectName("mediaPreviewCard")
        try:
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
        except Exception:
            pass

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        icon_label = QLabel()
        icon_label.setObjectName("mediaTitleIcon")
        icon_label.setPixmap(
            _symbol_icon("file-image", color="#79c7ff", size=14).pixmap(14, 14)
        )
        icon_label.setFixedSize(16, 16)
        header.addWidget(icon_label, 0, Qt.AlignVCenter)

        title_label = QLabel("Diagram")
        title_label.setObjectName("mediaPreviewTitle")
        title_label.setToolTip("Rendered Mermaid diagram")
        header.addWidget(title_label, 1)

        self._zoom_out_button = QPushButton("-")
        self._zoom_out_button.setObjectName("mediaIconButton")
        self._zoom_out_button.setToolTip("Zoom out")
        self._zoom_out_button.clicked.connect(
            lambda: self._set_zoom_multiplier(
                self._zoom_multiplier / _MERMAID_ZOOM_STEP
            )
        )
        header.addWidget(self._zoom_out_button, 0)

        self._zoom_in_button = QPushButton("+")
        self._zoom_in_button.setObjectName("mediaIconButton")
        self._zoom_in_button.setToolTip("Zoom in")
        self._zoom_in_button.clicked.connect(
            lambda: self._set_zoom_multiplier(
                self._zoom_multiplier * _MERMAID_ZOOM_STEP
            )
        )
        header.addWidget(self._zoom_in_button, 0)
        root.addLayout(header)

        self._scroll = PannableScrollArea(factor=0.8, parent=self)
        self._scroll.setObjectName("mermaidPreviewScroll")
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        root.addWidget(self._scroll, 0, Qt.AlignLeft)

        self._image_label = QLabel()
        self._image_label.setObjectName("mermaidPreviewImage")
        self._image_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._scroll.setWidget(self._image_label)

        QShortcut(
            Qt.Key_Plus,
            self,
            activated=lambda: self._set_zoom_multiplier(
                self._zoom_multiplier * _MERMAID_ZOOM_STEP
            ),
        )
        QShortcut(
            Qt.Key_Minus,
            self,
            activated=lambda: self._set_zoom_multiplier(
                self._zoom_multiplier / _MERMAID_ZOOM_STEP
            ),
        )
        self.set_bubble_width(self._bubble_width)

    def set_bubble_width(self, bubble_width: int) -> None:
        self._bubble_width = max(220, int(bubble_width or 0))
        self._render_preview()

    def _set_zoom_multiplier(self, value: float) -> None:
        bounded = max(
            _MERMAID_INLINE_MIN_ZOOM, min(_MERMAID_INLINE_MAX_ZOOM, float(value or 1.0))
        )
        if math.isclose(self._zoom_multiplier, bounded, rel_tol=0.0, abs_tol=0.001):
            self._sync_scroll_state()
            return
        self._zoom_multiplier = bounded
        self._render_preview(preserve_anchor=True)

    def _render_preview(self, *, preserve_anchor: bool = False) -> None:
        if self._pixmap.isNull():
            self._image_label.setText("Diagram preview unavailable.")
            return
        anchor_x = 0.0
        anchor_y = 0.0
        if preserve_anchor:
            anchor_x, anchor_y = self._scroll_anchor()

        frame_width = min(max(220, self._bubble_width), _MERMAID_PREVIEW_MAX_WIDTH)
        source_width = max(1, int(self._pixmap.width() or 1))
        source_height = max(1, int(self._pixmap.height() or 1))
        fit_width_scale = float(frame_width) / float(source_width)
        fit_height_scale = float(_MERMAID_INLINE_MAX_HEIGHT) / float(source_height)
        base_scale = min(fit_width_scale, fit_height_scale)
        scale = base_scale * self._zoom_multiplier
        scale = max(
            _MERMAID_INLINE_MIN_RENDER_SCALE,
            min(_MERMAID_INLINE_MAX_RENDER_SCALE, scale),
        )

        width = max(1, int(round(source_width * scale)))
        height = max(1, int(round(source_height * scale)))
        scaled = self._pixmap.scaled(
            width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        self.setFixedWidth(frame_width)
        self._scroll.setFixedWidth(frame_width)
        self._image_label.setPixmap(scaled)
        self._image_label.setFixedSize(scaled.size())
        viewport_height = min(
            _MERMAID_INLINE_MAX_HEIGHT, max(_MERMAID_INLINE_MIN_HEIGHT, scaled.height())
        )
        self._scroll.setFixedHeight(viewport_height + 18)
        QTimer.singleShot(
            0, lambda: self._after_render(anchor_x, anchor_y, preserve_anchor)
        )

    def _after_render(
        self, anchor_x: float, anchor_y: float, preserve_anchor: bool
    ) -> None:
        if preserve_anchor:
            self._restore_scroll_anchor(anchor_x, anchor_y)
        else:
            self._scroll.horizontalScrollBar().setValue(0)
            self._scroll.verticalScrollBar().setValue(0)
        self._sync_scroll_state()

    def _scroll_anchor(self) -> tuple[float, float]:
        width = max(1, int(self._image_label.width() or 1))
        height = max(1, int(self._image_label.height() or 1))
        viewport = self._scroll.viewport().size()
        center_x = (
            float(self._scroll.horizontalScrollBar().value())
            + float(max(1, viewport.width())) / 2.0
        )
        center_y = (
            float(self._scroll.verticalScrollBar().value())
            + float(max(1, viewport.height())) / 2.0
        )
        return center_x / float(width), center_y / float(height)

    def _restore_scroll_anchor(self, anchor_x: float, anchor_y: float) -> None:
        width = max(1, int(self._image_label.width() or 1))
        height = max(1, int(self._image_label.height() or 1))
        viewport = self._scroll.viewport().size()
        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        target_x = int(
            round(
                float(anchor_x) * float(width) - float(max(1, viewport.width())) / 2.0
            )
        )
        target_y = int(
            round(
                float(anchor_y) * float(height) - float(max(1, viewport.height())) / 2.0
            )
        )
        hbar.setValue(max(0, min(hbar.maximum(), target_x)))
        vbar.setValue(max(0, min(vbar.maximum(), target_y)))

    def _sync_scroll_state(self) -> None:
        self._scroll.refresh_pan_state()
        self._zoom_out_button.setEnabled(
            self._zoom_multiplier > (_MERMAID_INLINE_MIN_ZOOM + 0.01)
        )
        self._zoom_in_button.setEnabled(
            self._zoom_multiplier < (_MERMAID_INLINE_MAX_ZOOM - 0.01)
        )


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
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            scaled_size = _image_thumbnail_size(pixmap.size())
            scaled = pixmap.scaled(
                scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            button.setFixedSize(scaled.size())
            button.setIcon(QIcon(scaled))
            button.setIconSize(scaled.size())
            self._content_layout.addWidget(button, 0, Qt.AlignLeft)
            return

        if self._media_kind in {"audio", "video"}:
            player = InlineMediaPlayer(
                kind=self._media_kind, path=path, title=self._title, parent=self
            )
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


class ThinkingDotsWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(40, 18)
        self._tick = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_tick)
        self._timer.start(16)  # ~60 FPS

    def _update_tick(self) -> None:
        self._tick += 0.14
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        dot_radius = 3.0
        spacing = 9.0
        center_x = self.width() / 2.0
        center_y = self.height() / 2.0

        for i in range(3):
            # Sequence phase delay to create the wave-like motion
            phase = i * 0.95
            offset = math.sin(self._tick - phase)

            # Snap shape: bounce up snappily during positive phase, rest at bottom during negative phase
            if offset > 0:
                y_shift = -offset * 4.5
                dot_color = QColor(99, 102, 241, 235)  # Vibrant Indigo when rising
            else:
                y_shift = 0.0
                dot_color = QColor(156, 163, 175, 140)  # Muted grey at rest

            painter.setBrush(QBrush(dot_color))
            x = center_x + (i - 1) * spacing
            y = center_y + y_shift
            painter.drawEllipse(QPointF(x, y), dot_radius, dot_radius)


class ThinkingIndicatorCard(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("thinkingIndicator")
        self.setFrameShape(QFrame.NoFrame)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bubble = QFrame()
        bubble.setObjectName("thinkingBubble")
        bubble.setFixedSize(60, 28)

        bubble_layout = QHBoxLayout(bubble)
        bubble_layout.setContentsMargins(10, 5, 10, 5)
        bubble_layout.setSpacing(0)
        bubble_layout.setAlignment(Qt.AlignCenter)

        self._dots = ThinkingDotsWidget(bubble)
        bubble_layout.addWidget(self._dots)

        root.addWidget(bubble)
        root.addStretch(1)


def _usage_chip(text: str, tone: str, parent: Optional[QWidget] = None) -> QLabel:
    """Small colored status/action chip used by usage cards."""
    chip = QLabel(str(text or "").upper(), parent)
    chip.setObjectName("usageStatusChip")
    chip.setProperty("tone", str(tone or "neutral"))
    chip.setAlignment(Qt.AlignCenter)
    return chip


def _details_grid(rows: List[tuple], parent: Optional[QWidget] = None) -> QFrame:
    """Key/value details panel shared by tool and file cards."""
    frame = QFrame(parent)
    frame.setObjectName("toolApprovalParams")
    layout = QGridLayout(frame)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setHorizontalSpacing(12)
    layout.setVerticalSpacing(6)
    layout.setColumnStretch(1, 1)
    for row, (key, value) in enumerate(rows):
        key_label = QLabel(str(key))
        key_label.setObjectName("toolApprovalParamKey")
        key_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(key_label, row, 0)

        value_label = QLabel(str(value))
        value_label.setObjectName("toolApprovalParamValue")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(value_label, row, 1)
    return frame


class ToolApprovalCallCard(QFrame):
    def __init__(
        self, *, call: Any, index: int, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        summary = _tool_call_summary(call)
        self.setObjectName("toolApprovalCallCard")

        success: Optional[bool] = None
        error_text = ""
        if isinstance(call, dict):
            if isinstance(call.get("success"), bool):
                success = bool(call.get("success"))
            error_text = str(call.get("error") or "").strip()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        root.addLayout(header)

        icon_color = "#8fd0ff" if success is not False else "#f0968f"
        icon = QLabel()
        icon.setObjectName("toolApprovalIcon")
        icon.setPixmap(_symbol_icon("spark", color=icon_color, size=16).pixmap(16, 16))
        header.addWidget(icon, 0, Qt.AlignTop)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 0, 0)
        title_wrap.setSpacing(2)
        header.addLayout(title_wrap, 1)

        title = QLabel(summary.name)
        title.setObjectName("toolApprovalName")
        title_wrap.addWidget(title)

        reason = QLabel(summary.reason)
        reason.setObjectName("toolApprovalReason")
        reason.setWordWrap(True)
        title_wrap.addWidget(reason)

        badges = QVBoxLayout()
        badges.setContentsMargins(0, 0, 0, 0)
        badges.setSpacing(4)
        header.addLayout(badges)
        order = QLabel(f"#{index + 1}")
        order.setObjectName("usageCardIndex")
        order.setAlignment(Qt.AlignRight | Qt.AlignTop)
        badges.addWidget(order, 0, Qt.AlignRight)
        if success is True:
            badges.addWidget(_usage_chip("completed", "ok", self), 0, Qt.AlignRight)
        elif success is False:
            badges.addWidget(_usage_chip("failed", "failed", self), 0, Qt.AlignRight)
        badges.addStretch(1)

        if summary.parameters:
            root.addWidget(_details_grid(list(summary.parameters), self))

        if error_text:
            error_label = QLabel(error_text)
            error_label.setObjectName("usageCardError")
            error_label.setWordWrap(True)
            error_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            root.addWidget(error_label)

        raw_toggle = QPushButton("Show full tool call")
        raw_toggle.setObjectName("toolApprovalRawToggle")
        raw_toggle.setCheckable(True)
        root.addWidget(raw_toggle, 0, Qt.AlignLeft)

        raw_panel = QPlainTextEdit()
        raw_panel.setObjectName("toolApprovalRawPanel")
        raw_panel.setReadOnly(True)
        raw_panel.setPlainText(
            summary.raw_text or "No raw tool call payload was provided."
        )
        raw_panel.setMinimumHeight(132)
        raw_panel.setMaximumHeight(220)
        raw_panel.hide()
        root.addWidget(raw_panel)

        def _toggle_raw(checked: bool) -> None:
            raw_panel.setVisible(bool(checked))
            raw_toggle.setText(
                "Hide full tool call" if checked else "Show full tool call"
            )

        raw_toggle.toggled.connect(_toggle_raw)


_FILE_ACTION_TONES = {
    "created": "created",
    "modified": "modified",
    "moved": "moved",
    "deleted": "deleted",
}

_FILE_ACTION_ICON_COLORS = {
    "created": "#5ed2a1",
    "modified": "#7fb7f7",
    "moved": "#f0c979",
    "deleted": "#f0968f",
}

_FILE_ACTION_SENTENCES = {
    "created": "Created (or fully replaced) by",
    "modified": "Modified in place by",
    "moved": "Moved / renamed by",
    "deleted": "Deleted by",
}


class FileOperationCard(QFrame):
    """One card per file mutation (created / modified / moved / deleted)."""

    def __init__(
        self, *, operation: FileOperation, index: int, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("toolApprovalCallCard")
        action = str(operation.action or "").strip().lower()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        root.addLayout(header)

        icon = QLabel()
        icon.setObjectName("toolApprovalIcon")
        icon.setPixmap(
            _symbol_icon(
                "file", color=_FILE_ACTION_ICON_COLORS.get(action, "#8fd0ff"), size=16
            ).pixmap(16, 16)
        )
        header.addWidget(icon, 0, Qt.AlignTop)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 0, 0)
        title_wrap.setSpacing(2)
        header.addLayout(title_wrap, 1)

        display_path = operation.detail if (action == "moved" and operation.detail) else operation.path
        name = Path(str(display_path or "")).name or str(display_path or "")
        title = QLabel(name)
        title.setObjectName("toolApprovalName")
        title_wrap.addWidget(title)

        verb = _FILE_ACTION_SENTENCES.get(action, "Touched by")
        via = str(operation.via or "").strip() or "an executed tool"
        subtitle = QLabel(f"{verb} `{via}`.")
        subtitle.setObjectName("toolApprovalReason")
        subtitle.setWordWrap(True)
        title_wrap.addWidget(subtitle)

        badges = QVBoxLayout()
        badges.setContentsMargins(0, 0, 0, 0)
        badges.setSpacing(4)
        header.addLayout(badges)
        order = QLabel(f"#{index + 1}")
        order.setObjectName("usageCardIndex")
        order.setAlignment(Qt.AlignRight | Qt.AlignTop)
        badges.addWidget(order, 0, Qt.AlignRight)
        badges.addWidget(
            _usage_chip(action or "file", _FILE_ACTION_TONES.get(action, "neutral"), self),
            0,
            Qt.AlignRight,
        )
        badges.addStretch(1)

        rows: List[tuple] = []
        if action == "moved" and operation.detail:
            rows.append(("from", operation.path))
            rows.append(("to", operation.detail))
        else:
            rows.append(("path", operation.path))
        if str(operation.via or "").strip():
            rows.append(("tool", operation.via))
        root.addWidget(_details_grid(rows, self))


_USAGE_CARD_EXTRA_STYLE = """
    QLabel#usageStatusChip {
        padding: 2px 8px;
        border-radius: 8px;
        font-size: 9px;
        font-weight: 800;
        letter-spacing: 0.08em;
        color: #cbd5e1;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.10);
    }
    QLabel#usageStatusChip[tone="ok"], QLabel#usageStatusChip[tone="created"] {
        color: #baf3d0;
        background: rgba(31, 167, 112, 0.18);
        border: 1px solid rgba(89, 221, 160, 0.30);
    }
    QLabel#usageStatusChip[tone="modified"] {
        color: #bcd8fb;
        background: rgba(78, 138, 224, 0.18);
        border: 1px solid rgba(127, 183, 247, 0.32);
    }
    QLabel#usageStatusChip[tone="moved"] {
        color: #f7e0ae;
        background: rgba(224, 168, 62, 0.16);
        border: 1px solid rgba(240, 201, 121, 0.32);
    }
    QLabel#usageStatusChip[tone="failed"], QLabel#usageStatusChip[tone="deleted"] {
        color: #ffd2cd;
        background: rgba(220, 76, 60, 0.18);
        border: 1px solid rgba(240, 150, 143, 0.34);
    }
    QLabel#usageCardIndex {
        color: rgba(150, 168, 192, 0.55);
        font-size: 10px;
        font-weight: 700;
        background: transparent;
        border: none;
    }
    QLabel#usageCardError {
        color: #ffb4ab;
        font-size: 11px;
        background: rgba(220, 76, 60, 0.10);
        border: 1px solid rgba(220, 76, 60, 0.22);
        border-radius: 8px;
        padding: 8px 10px;
    }
"""


_USAGE_DIALOG_STYLE = (
    """
    QDialog {
        background: #090d16;
        color: #f3f4f6;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial;
    }
    QLabel#dialogTitle {
        color: #ffffff;
        font-size: 20px;
        font-weight: 700;
    }
    QLabel#toolApprovalHint {
        color: #9ca3af;
        font-size: 13px;
    }
    QScrollArea {
        border: none;
        background: transparent;
    }
    QScrollArea > QWidget > QWidget {
        background: transparent;
    }
    QFrame#toolApprovalCallCard {
        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #161c26, stop: 1 #10141b);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 14px;
    }
    QFrame#toolApprovalCallCard:hover {
        border-color: rgba(99, 102, 241, 0.35);
        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #1a212c, stop: 1 #12171f);
    }
    QLabel#toolApprovalName {
        color: #ffffff;
        font-size: 14px;
        font-weight: 700;
    }
    QLabel#toolApprovalReason {
        color: #d1d5db;
        font-size: 12px;
    }
    QFrame#toolApprovalParams {
        background: rgba(0, 0, 0, 0.25);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 10px;
    }
    QLabel#toolApprovalParamKey {
        color: #a5b4fc;
        font-size: 11px;
        font-weight: 700;
    }
    QLabel#toolApprovalParamValue {
        color: #f3f4f6;
        font-size: 11px;
    }
    QPushButton#toolApprovalRawToggle, QPushButton#toolApprovalSecondaryButton {
        min-height: 32px;
        border-radius: 10px;
        padding: 0 14px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        background: rgba(255, 255, 255, 0.04);
        color: #f3f4f6;
        font-weight: 600;
        font-size: 12px;
    }
    QPushButton#toolApprovalRawToggle:hover, QPushButton#toolApprovalSecondaryButton:hover {
        background: rgba(255, 255, 255, 0.09);
        border-color: rgba(255, 255, 255, 0.15);
    }
    QPlainTextEdit#toolApprovalRawPanel {
        background: #0b0f17;
        color: #f3f4f6;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 8px;
        font-family: Menlo, Monaco, Consolas;
        font-size: 11px;
    }
    QScrollBar:vertical {
        width: 6px;
        background: transparent;
        margin: 4px 0 4px 0;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.12);
        border-radius: 3px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background: rgba(255, 255, 255, 0.2);
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: transparent;
        border: none;
        height: 0px;
    }
    QScrollBar:horizontal {
        height: 0px;
        background: transparent;
    }
"""
    + _USAGE_CARD_EXTRA_STYLE
)


class ToolApprovalDialog(QDialog):
    def __init__(self, *, tool_calls: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.approval_scope = "once"
        self.setWindowTitle("Approve tools")
        self.resize(680, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        headline = QLabel("The assistant wants to run tools for this request.")
        headline.setWordWrap(True)
        headline.setObjectName("dialogTitle")
        root.addWidget(headline)

        hint = QLabel(
            "Review this batch. Use “Allow once” for this request, or allow all enabled tools for this chat to stop prompting while you stay in this chat."
        )
        hint.setWordWrap(True)
        hint.setObjectName("toolApprovalHint")
        root.addWidget(hint)

        calls = (
            [call for call in list(tool_calls or []) if isinstance(call, dict)]
            if isinstance(tool_calls, list)
            else []
        )
        batch_note = QLabel(
            f"{len(calls)} tool request{'s' if len(calls) != 1 else ''} in this approval batch."
            if calls
            else "The workflow did not provide structured tool details for this batch."
        )
        batch_note.setObjectName("toolApprovalBatchNote")
        batch_note.setWordWrap(True)
        root.addWidget(batch_note)

        # Add horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.08); max-height: 1px; border: none; margin: 4px 0;"
        )
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        host = QWidget()
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(10)
        scroll.setWidget(host)

        if calls:
            for index, call in enumerate(calls):
                card = ToolApprovalCallCard(call=call, index=index, parent=host)
                # Apply premium drop shadow to tool approval cards
                shadow = QGraphicsDropShadowEffect(card)
                shadow.setBlurRadius(12)
                shadow.setColor(QColor(0, 0, 0, 80))
                shadow.setOffset(0, 3)
                card.setGraphicsEffect(shadow)
                host_layout.addWidget(card)
        else:
            fallback = QPlainTextEdit()
            fallback.setObjectName("toolApprovalRawPanel")
            fallback.setReadOnly(True)
            fallback.setPlainText(_tool_calls_text(tool_calls))
            host_layout.addWidget(fallback)
        host_layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        deny = QPushButton("Deny")
        deny.setObjectName("toolApprovalSecondaryButton")
        deny.clicked.connect(self.reject)
        buttons.addWidget(deny)

        allow = QPushButton("Allow once")
        allow.setObjectName("toolApprovalSecondaryButton")
        allow.clicked.connect(self._accept_once)
        buttons.addWidget(allow)

        allow_session = QPushButton("Allow all enabled tools in this chat")
        allow_session.setObjectName("toolApprovalPrimaryButton")
        allow_session.setToolTip(
            "Auto-approve future tool requests only for enabled tools in this chat."
        )
        allow_session.clicked.connect(self._accept_for_session)
        buttons.addWidget(allow_session)
        root.addLayout(buttons)

        self.setStyleSheet("""
            QDialog {
                background: #090d16;
                color: #f3f4f6;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial;
            }
            QLabel#dialogTitle {
                color: #ffffff;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#toolApprovalHint {
                color: #9ca3af;
                font-size: 13px;
            }
            QLabel#toolApprovalBatchNote {
                color: #818cf8;
                font-size: 12px;
                font-weight: 600;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QFrame#toolApprovalCallCard {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgba(22, 28, 38, 0.6), stop: 1 rgba(14, 18, 24, 0.7));
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 14px;
            }
            QFrame#toolApprovalCallCard:hover {
                border-color: rgba(99, 102, 241, 0.35);
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgba(26, 33, 44, 0.7), stop: 1 rgba(18, 23, 31, 0.8));
            }
            QLabel#toolApprovalName {
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#toolApprovalReason {
                color: #d1d5db;
                font-size: 12px;
            }
            QFrame#toolApprovalParams {
                background: rgba(0, 0, 0, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 10px;
            }
            QLabel#toolApprovalParamKey {
                color: #a5b4fc;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#toolApprovalParamValue {
                color: #f3f4f6;
                font-size: 11px;
            }
            QPushButton#toolApprovalRawToggle, QPushButton#toolApprovalSecondaryButton, QPushButton#toolApprovalPrimaryButton {
                min-height: 36px;
                border-radius: 10px;
                padding: 0 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton#toolApprovalRawToggle, QPushButton#toolApprovalSecondaryButton {
                border: 1px solid rgba(255, 255, 255, 0.08);
                background: rgba(255, 255, 255, 0.04);
                color: #f3f4f6;
            }
            QPushButton#toolApprovalRawToggle:hover, QPushButton#toolApprovalSecondaryButton:hover {
                background: rgba(255, 255, 255, 0.09);
                border-color: rgba(255, 255, 255, 0.15);
            }
            QPushButton#toolApprovalRawToggle:pressed, QPushButton#toolApprovalSecondaryButton:pressed {
                background: rgba(255, 255, 255, 0.02);
            }
            QPushButton#toolApprovalPrimaryButton {
                border: 1px solid rgba(16, 185, 129, 0.25);
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #10b981, stop: 1 #059669);
                color: #ffffff;
            }
            QPushButton#toolApprovalPrimaryButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #34d399, stop: 1 #10b981);
                border-color: rgba(52, 211, 153, 0.4);
            }
            QPushButton#toolApprovalPrimaryButton:pressed {
                background: #047857;
            }
            QPlainTextEdit#toolApprovalRawPanel {
                background: #0b0f17;
                color: #f3f4f6;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 8px;
                font-family: "SF Mono", Menlo, Monaco, Consolas;
                font-size: 11px;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 4px 0 4px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.12);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
                height: 0px;
            }
            """ + _USAGE_CARD_EXTRA_STYLE)

    def _accept_once(self) -> None:
        self.approval_scope = "once"
        self.accept()

    def _accept_for_session(self) -> None:
        self.approval_scope = "session"
        self.accept()


class ToolUsageLookupWorker(QThread):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        controller: AssistantV2Controller,
        message: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._message = dict(message or {})

    def run(self) -> None:
        try:
            result = self._controller.tool_call_details_for_message(self._message)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.loaded.emit(result if isinstance(result, dict) else {})


class ToolUsageDialog(QDialog):
    def __init__(
        self,
        *,
        message: Dict[str, Any],
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        source: str = "",
        run_ids: Optional[List[str]] = None,
        error: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tools used")
        self.resize(680, 520)
        self._message = dict(message or {})

        ledger_calls = [
            dict(call) for call in (tool_calls or []) if isinstance(call, dict)
        ]
        cached_calls = _assistant_tool_calls_for_message(message)
        calls = ledger_calls or cached_calls
        source_s = str(source or "").strip()
        run_ids_s = [
            str(rid or "").strip() for rid in (run_ids or []) if str(rid or "").strip()
        ]
        error_s = str(error or "").strip()
        metrics = _assistant_footer_metrics(message)
        tool_metric = next(
            (metric for metric in metrics if str(metric.get("kind") or "") == "tools"),
            {},
        )
        count_label = str(
            tool_metric.get("plain") or tool_metric.get("label") or "tool calls"
        ).strip()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        headline = QLabel("Tools used in this answer")
        headline.setWordWrap(True)
        headline.setObjectName("dialogTitle")
        root.addWidget(headline)

        self._hint_label = QLabel("")
        self._hint_label.setWordWrap(True)
        self._hint_label.setObjectName("toolApprovalHint")
        root.addWidget(self._hint_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.08); max-height: 1px; border: none; margin: 4px 0;"
        )
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        host = QWidget()
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(10)
        scroll.setWidget(host)
        self._host = host
        self._host_layout = host_layout
        self._count_label = count_label

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("toolApprovalSecondaryButton")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self.setStyleSheet(_USAGE_DIALOG_STYLE)
        self.update_tool_usage(
            tool_calls=calls, source=source_s, run_ids=run_ids_s, error=error_s
        )

    def set_loading(self) -> None:
        if _assistant_tool_calls_for_message(self._message):
            self._hint_label.setText(
                "Refreshing tool details from the runtime ledger..."
            )
            return
        self._populate_empty(
            "Loading tool details from the runtime ledger...",
            "The dialog is replaying the run ledger via Gateway.",
        )

    def update_tool_usage(
        self,
        *,
        tool_calls: List[Dict[str, Any]],
        source: str = "",
        run_ids: Optional[List[str]] = None,
        error: str = "",
    ) -> None:
        calls = [dict(call) for call in (tool_calls or []) if isinstance(call, dict)]
        source_s = str(source or "").strip()
        run_ids_s = [
            str(rid or "").strip() for rid in (run_ids or []) if str(rid or "").strip()
        ]
        error_s = str(error or "").strip()
        if calls:
            if source_s == "ledger":
                run_hint = f" from run {run_ids_s[0]}" if run_ids_s else ""
                hint_text = f"{len(calls)} tools loaded{run_hint} by replaying the runtime ledger."
            elif source_s == "scratchpad":
                run_hint = f" for run {run_ids_s[0]}" if run_ids_s else ""
                hint_text = f"{len(calls)} tools loaded{run_hint} from the persisted agent scratchpad because the Gateway ledger was unavailable."
            else:
                hint_text = f"{len(calls)} tools loaded from cached assistant metadata."
            self._clear_tool_host()
            self._hint_label.setText(hint_text)
            for index, call in enumerate(calls):
                self._host_layout.addWidget(
                    ToolApprovalCallCard(call=call, index=index, parent=self._host)
                )
            self._host_layout.addStretch(1)
            return
        if error_s:
            self._populate_empty(
                f"Could not load tool details from the runtime ledger: {error_s}",
                f"Ledger lookup failed.\n\n{error_s}",
            )
        elif source_s == "missing_run_id":
            self._populate_empty(
                "This message has a tool count but no run_id, so the runtime ledger cannot be replayed for it.",
                "No run_id is attached to this assistant message. Future messages now persist the run_id so this ledger replay can work.",
            )
        else:
            self._populate_empty(
                f"{self._count_label} recorded, but no completed tool_calls records were found in the runtime ledger.",
                "The Gateway ledger returned no completed tool_calls records for this run.",
            )

    def _populate_empty(self, hint: str, detail: str) -> None:
        self._clear_tool_host()
        self._hint_label.setText(str(hint or ""))
        fallback = QPlainTextEdit()
        fallback.setObjectName("toolApprovalRawPanel")
        fallback.setReadOnly(True)
        fallback.setPlainText(str(detail or ""))
        self._host_layout.addWidget(fallback)
        self._host_layout.addStretch(1)

    def _clear_tool_host(self) -> None:
        while self._host_layout.count():
            item = self._host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class FileActivityDialog(QDialog):
    """Per-answer file activity: one scrollable card per file mutation."""

    def __init__(
        self,
        *,
        message: Dict[str, Any],
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        source: str = "",
        run_ids: Optional[List[str]] = None,
        error: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Files affected")
        self.resize(680, 520)
        self._message = dict(message or {})

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        headline = QLabel("Files affected in this answer")
        headline.setWordWrap(True)
        headline.setObjectName("dialogTitle")
        root.addWidget(headline)

        self._hint_label = QLabel("")
        self._hint_label.setWordWrap(True)
        self._hint_label.setObjectName("toolApprovalHint")
        root.addWidget(self._hint_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.08); max-height: 1px; border: none; margin: 4px 0;"
        )
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        host = QWidget()
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(10)
        scroll.setWidget(host)
        self._host = host
        self._host_layout = host_layout

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("toolApprovalSecondaryButton")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self.setStyleSheet(_USAGE_DIALOG_STYLE)
        self.update_file_activity(
            tool_calls=tool_calls, source=source, run_ids=run_ids, error=error
        )

    def set_loading(self) -> None:
        if _assistant_file_operations_for_message(self._message):
            self._hint_label.setText(
                "Refreshing file activity from the runtime ledger..."
            )
            return
        self._populate_empty(
            "Loading file activity from the runtime ledger...",
            "The dialog is replaying the run ledger via Gateway to derive file operations.",
        )

    def update_file_activity(
        self,
        *,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        source: str = "",
        run_ids: Optional[List[str]] = None,
        error: str = "",
    ) -> None:
        operations = _assistant_file_operations_for_message(
            self._message,
            tool_calls if isinstance(tool_calls, list) and tool_calls else None,
        )
        source_s = str(source or "").strip()
        run_ids_s = [
            str(rid or "").strip() for rid in (run_ids or []) if str(rid or "").strip()
        ]
        error_s = str(error or "").strip()

        if operations:
            counts: Dict[str, int] = {}
            for op in operations:
                counts[op.action] = counts.get(op.action, 0) + 1
            parts = [
                f"{counts[action]} {action}"
                for action in ("created", "modified", "moved", "deleted")
                if counts.get(action)
            ]
            distinct = distinct_file_count(operations)
            origin = (
                f" Derived by replaying run {run_ids_s[0]}." if source_s == "ledger" and run_ids_s else ""
            )
            plural = "s" if distinct != 1 else ""
            self._hint_label.setText(
                f"{distinct} file{plural} affected \u2014 {', '.join(parts)}. "
                f"Only mutations proven by the executed tool calls are listed.{origin}"
            )
            self._clear_host()
            for index, operation in enumerate(operations):
                self._host_layout.addWidget(
                    FileOperationCard(operation=operation, index=index, parent=self._host)
                )
            self._host_layout.addStretch(1)
            return

        if error_s:
            self._populate_empty(
                f"Could not load file activity from the runtime ledger: {error_s}",
                f"Ledger lookup failed.\n\n{error_s}",
            )
        else:
            self._populate_empty(
                "No files were created, modified, moved or deleted by this answer.",
                "None of the executed tool calls performed a provable file mutation.\n"
                "Read-only tools (searches, reads, fetches) never count as file activity,\n"
                "and ambiguous shell commands (globs, substitutions) are deliberately not guessed.",
            )

    def _populate_empty(self, hint: str, detail: str) -> None:
        self._clear_host()
        self._hint_label.setText(str(hint or ""))
        fallback = QPlainTextEdit()
        fallback.setObjectName("toolApprovalRawPanel")
        fallback.setReadOnly(True)
        fallback.setPlainText(str(detail or ""))
        self._host_layout.addWidget(fallback)
        self._host_layout.addStretch(1)

    def _clear_host(self) -> None:
        while self._host_layout.count():
            item = self._host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class ToolSettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    def __init__(
        self, *, controller: AssistantV2Controller, parent: Optional[QWidget] = None
    ) -> None:
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

        # Add horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.08); max-height: 1px; border: none; margin: 4px 0;"
        )
        root.addWidget(sep)

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
        self.setStyleSheet("""
            QDialog {
                background: #090d16;
                color: #f3f4f6;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial;
            }
            QLabel#dialogTitle {
                color: #ffffff;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#dialogSubtitle {
                color: #9ca3af;
                font-size: 13px;
            }
            QLabel#statusNote {
                color: #e0e7ff;
                background: rgba(99, 102, 241, 0.08);
                border: 1px solid rgba(99, 102, 241, 0.18);
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 12px;
                line-height: 1.4;
            }
            QLabel#feedbackNote {
                color: #34d399;
                font-size: 12px;
                font-weight: 600;
            }
            QLineEdit, QComboBox {
                min-height: 36px;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                background: rgba(255, 255, 255, 0.03);
                color: #f3f4f6;
                padding: 6px 12px;
                font-size: 13px;
            }
            QLineEdit:hover, QComboBox:hover {
                border-color: rgba(99, 102, 241, 0.3);
                background: rgba(255, 255, 255, 0.05);
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #6366f1;
                background: rgba(255, 255, 255, 0.06);
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background: #1e293b;
                color: #f3f4f6;
                border: 1px solid rgba(255, 255, 255, 0.1);
                selection-background-color: #312e81;
                selection-color: #ffffff;
                border-radius: 8px;
                padding: 4px;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QFrame#toolRow {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgba(22, 28, 38, 0.5), stop: 1 rgba(14, 18, 24, 0.6));
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 12px;
            }
            QFrame#toolRow:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgba(26, 33, 44, 0.7), stop: 1 rgba(18, 23, 31, 0.8));
                border-color: rgba(99, 102, 241, 0.35);
            }
            QLabel#toolIcon {
                min-width: 28px;
                color: #818cf8;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#toolName {
                color: #ffffff;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#toolMeta {
                color: #9ca3af;
                font-size: 11px;
            }
            QPushButton {
                min-height: 38px;
                border-radius: 10px;
                padding: 7px 16px;
                border: 1px solid rgba(16, 185, 129, 0.25);
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #10b981, stop: 1 #059669);
                color: #ffffff;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #34d399, stop: 1 #10b981);
                border-color: rgba(52, 211, 153, 0.4);
            }
            QPushButton:pressed {
                background: #047857;
            }
            QPushButton#secondaryButton {
                background: rgba(255, 255, 255, 0.04);
                color: #f3f4f6;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            QPushButton#secondaryButton:hover {
                background: rgba(255, 255, 255, 0.09);
                border-color: rgba(255, 255, 255, 0.15);
            }
            QPushButton#secondaryButton:pressed {
                background: rgba(255, 255, 255, 0.02);
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 4px 0 4px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.12);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
                height: 0px;
            }
            """)

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
        self.mode_note.setText(
            self._tool_mode_text(str((inventory or {}).get("tool_mode") or ""))
        )
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

            desc_parts = [
                str(item.get("description") or "").strip(),
                str(item.get("when_to_use") or "").strip(),
            ]
            desc = (
                " ".join(part for part in desc_parts if part).strip()
                or "No description available."
            )
            meta = QLabel(desc)
            meta.setObjectName("toolMeta")
            meta.setWordWrap(True)
            text_col.addWidget(meta)

            policy_default = str(item.get("policy_default") or "ask").strip().lower()
            default_hint = QLabel(
                f"Default: {'Approve' if policy_default == 'approve' else 'Ask'}"
            )
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
            self._rows[name] = {
                "row": row,
                "combo": combo,
                "default_mode": str(item.get("default_mode") or "ask"),
                "search": searchable,
            }

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

    def __init__(
        self,
        *,
        controller: AssistantV2Controller,
        apply_hotkey,
        parent: Optional[QWidget] = None,
    ) -> None:
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

        subtitle = QLabel(
            "Gateway defaults stay on the gateway. Device preferences stay on this Mac."
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # Add horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.08); max-height: 1px; border: none; margin: 4px 0;"
        )
        root.addWidget(sep)

        self.settings_tabs = QTabWidget()
        self.settings_tabs.setObjectName("settingsTabs")
        root.addWidget(self.settings_tabs, 1)

        connection_tab = QWidget()
        connection_root = QVBoxLayout(connection_tab)
        connection_root.setContentsMargins(0, 0, 0, 0)
        connection_root.setSpacing(12)
        self.settings_tabs.addTab(connection_tab, "Connection")

        connection_intro = QLabel(
            "Choose how this desktop app signs into the gateway. These settings stay on this device."
        )
        connection_intro.setObjectName("sectionHelp")
        connection_intro.setWordWrap(True)
        connection_root.addWidget(connection_intro)

        self.connection_card = QFrame()
        self.connection_card.setObjectName("settingsCard")
        connection_stack = QVBoxLayout(self.connection_card)
        connection_stack.setContentsMargins(18, 18, 18, 18)
        connection_stack.setSpacing(14)
        connection_root.addWidget(self.connection_card)

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
        self.auth_mode_combo.currentIndexChanged.connect(
            self._refresh_connection_fields
        )
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

        self.remember_session = QCheckBox(
            "Keep the gateway session after this app closes"
        )
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
        self.voice_shortcut_button.clicked.connect(
            lambda: self._focus_route("output.voice")
        )
        voice_shortcut_layout.addWidget(self.voice_shortcut_button, 0, Qt.AlignTop)
        routes_root.addWidget(self.voice_shortcut_card)

        self.route_card = QFrame()
        self.route_card.setObjectName("settingsCard")
        route_stack = QVBoxLayout(self.route_card)
        route_stack.setContentsMargins(18, 18, 18, 18)
        route_stack.setSpacing(14)
        routes_root.addWidget(self.route_card, 1)

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
        self.provider_combo.currentIndexChanged.connect(
            self._refresh_models_for_provider
        )
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

        self.prefs_card = QFrame()
        self.prefs_card.setObjectName("settingsCard")
        prefs_stack = QVBoxLayout(self.prefs_card)
        prefs_stack.setContentsMargins(18, 18, 18, 18)
        prefs_stack.setSpacing(14)
        prefs_root.addWidget(self.prefs_card)

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

        # Add drop shadows to settings cards
        for card in (
            self.connection_card,
            self.voice_shortcut_card,
            self.route_card,
            self.prefs_card,
        ):
            shadow = QGraphicsDropShadowEffect(card)
            shadow.setBlurRadius(16)
            shadow.setColor(QColor(0, 0, 0, 100))
            shadow.setOffset(0, 4)
            card.setGraphicsEffect(shadow)

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
            self.route_help.setText(
                "Connect to a gateway account that can read capability defaults."
            )
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
        self.setStyleSheet("""
            QDialog {
                background: #090d16;
                color: #f3f4f6;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial;
            }
            QLabel#dialogTitle {
                font-size: 20px;
                font-weight: 700;
                color: #ffffff;
            }
            QLabel#dialogSubtitle, QLabel#sectionHelp, QLabel#routeHelp {
                color: #9ca3af;
                font-size: 13px;
            }
            QFrame#settingsCard {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgba(22, 28, 38, 0.5), stop: 1 rgba(14, 18, 24, 0.6));
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 18px;
            }
            QFrame#settingsCard:hover {
                border-color: rgba(99, 102, 241, 0.2);
            }
            QTabWidget::pane {
                border: none;
                margin-top: 10px;
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 0.03);
                color: #9ca3af;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 10px;
                padding: 8px 16px;
                margin-right: 8px;
                min-width: 110px;
                font-weight: 600;
            }
            QTabBar::tab:hover {
                background: rgba(255, 255, 255, 0.08);
                color: #ffffff;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 rgba(99, 102, 241, 0.25), stop: 1 rgba(79, 70, 229, 0.3));
                color: #ffffff;
                border: 1px solid rgba(99, 102, 241, 0.5);
            }
            QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QSpinBox {
                background: rgba(255, 255, 255, 0.03);
                color: #f3f4f6;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit, QComboBox, QSpinBox {
                min-height: 38px;
            }
            QPlainTextEdit {
                padding: 10px 12px;
            }
            QLineEdit:hover, QComboBox:hover, QPlainTextEdit:hover, QListWidget:hover, QSpinBox:hover {
                border-color: rgba(99, 102, 241, 0.35);
                background: rgba(255, 255, 255, 0.05);
            }
            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QListWidget:focus, QSpinBox:focus {
                border-color: #6366f1;
                background: rgba(255, 255, 255, 0.07);
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background: #1e293b;
                color: #f3f4f6;
                border: 1px solid rgba(255, 255, 255, 0.1);
                selection-background-color: #312e81;
                selection-color: #ffffff;
                border-radius: 8px;
                padding: 4px;
            }
            QPushButton {
                min-height: 38px;
                border-radius: 10px;
                padding: 7px 16px;
                border: 1px solid rgba(16, 185, 129, 0.25);
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #10b981, stop: 1 #059669);
                color: #ffffff;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #34d399, stop: 1 #10b981);
                border-color: rgba(52, 211, 153, 0.4);
            }
            QPushButton:pressed {
                background: #047857;
            }
            QPushButton#secondaryButton {
                background: rgba(255, 255, 255, 0.04);
                color: #f3f4f6;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            QPushButton#secondaryButton:hover {
                background: rgba(255, 255, 255, 0.09);
                border-color: rgba(255, 255, 255, 0.15);
            }
            QPushButton#secondaryButton:pressed {
                background: rgba(255, 255, 255, 0.02);
            }
            QListWidget {
                padding: 8px;
            }
            QListWidget::item {
                background: rgba(255, 255, 255, 0.01);
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 8px;
                padding: 8px 12px;
                margin-bottom: 6px;
                color: #d1d5db;
            }
            QListWidget::item:hover {
                background: rgba(255, 255, 255, 0.05);
                border-color: rgba(99, 102, 241, 0.2);
                color: #ffffff;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 rgba(99, 102, 241, 0.25), stop: 1 rgba(79, 70, 229, 0.3));
                border-color: rgba(99, 102, 241, 0.5);
                color: #ffffff;
            }
            QLabel#routeLabel {
                font-size: 20px;
                font-weight: 700;
                color: #ffffff;
            }
            QLabel#statusNote {
                color: #e0e7ff;
                background: rgba(99, 102, 241, 0.08);
                border: 1px solid rgba(99, 102, 241, 0.18);
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 12px;
                line-height: 1.4;
            }
            QLabel#feedbackNote {
                color: #34d399;
                font-size: 12px;
                font-weight: 600;
            }
            QCheckBox {
                spacing: 8px;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 4px 0 4px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.12);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
                height: 0px;
            }
            """)

    def _load_connection_preferences(self) -> None:
        connection = self._controller.current_connection()
        self.gateway_url_edit.setText(str(connection.base_url or DEFAULT_GATEWAY_URL))
        self._set_combo_value(
            self.auth_mode_combo, str(connection.auth_mode or "bearer")
        )
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
            detail = (
                str(payload.get("detail") or "Not connected yet.").strip()
                if isinstance(payload, dict)
                else "Not connected yet."
            )
            self.connection_status.setText(f"Status: {detail}")
            return
        principal = (
            payload.get("principal")
            if isinstance(payload.get("principal"), dict)
            else {}
        )
        auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else {}
        routing = (
            payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
        )
        user_id = str(principal.get("user_id") or "unknown").strip()
        tenant_id = str(principal.get("tenant_id") or "").strip()
        mode = str(auth.get("mode") or "").strip() or "unknown"
        suffix = f" in tenant {tenant_id}" if tenant_id else ""
        routing_mode = str(routing.get("mode") or "").strip()
        routing_note = f" Routing: {routing_mode}." if routing_mode else ""
        self.connection_status.setText(
            f"Status: connected as {user_id}{suffix} via {mode}.{routing_note}"
        )

    def _save_connection(self) -> None:
        base_url = self.gateway_url_edit.text().strip() or DEFAULT_GATEWAY_URL
        auth_mode = str(self.auth_mode_combo.currentData() or "bearer")
        try:
            if auth_mode == "bearer":
                self._controller.save_bearer_connection(
                    base_url=base_url, auth_token=self.bearer_token_edit.text()
                )
                self.connection_feedback.setText(
                    "Saved bearer-token connection on this device."
                )
            else:
                self._controller.login_gateway_session(
                    base_url=base_url,
                    user_id=self.gateway_user_edit.text().strip(),
                    token=self.gateway_user_token_edit.text(),
                    remember=bool(self.remember_session.isChecked()),
                )
                self.gateway_user_token_edit.clear()
                self.connection_feedback.setText(
                    "Saved gateway session on this device."
                )
        except Exception as exc:
            QMessageBox.critical(self, "Connection failed", str(exc))
            return
        self.settings_saved.emit()
        self.refresh()

    def _clear_connection(self) -> None:
        connection = self._controller.current_connection()
        base_url = self.gateway_url_edit.text().strip() or DEFAULT_GATEWAY_URL
        try:
            if (
                str(connection.auth_mode or "").strip() == "session"
                and str(connection.session_id or "").strip()
            ):
                self._controller.logout_gateway_session()
            else:
                self._controller.save_bearer_connection(
                    base_url=base_url, auth_token=""
                )
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
        row = next(
            (item for item in self._route_rows if item.key == "output.voice"), None
        )
        if row is None:
            self.voice_shortcut_summary.setText(
                "Configure provider, model, and voice/profile used when the assistant speaks replies aloud."
            )
            return
        provider = str(row.provider or "").strip() or "No provider"
        model = str(row.model or "").strip() or "No model"
        voice = (
            str(
                (row.options or {}).get("voice")
                or (row.options or {}).get("profile")
                or ""
            ).strip()
            or "Default voice"
        )
        self.voice_shortcut_summary.setText(f"{provider} / {model} · {voice}")

    def _route_key_label(self, key: str) -> str:
        spec = ROUTE_SPECS.get(str(key or "").strip())
        return spec.label if spec is not None else str(key or "").strip()

    def _route_state_text(self, row: CapabilityRouteRow) -> str:
        parts = [
            (
                "Saved on the connected gateway."
                if row.configured
                else "No saved override on this route yet."
            ),
        ]
        if row.covered_by:
            parts.append(
                f"This route is covered by {self._route_key_label(row.covered_by)}."
            )
        if row.derived_from:
            parts.append(
                f"This route inherits from {self._route_key_label(row.derived_from)}."
            )
        if row.source:
            parts.append(f"Gateway source: {row.source}.")
        return " ".join(parts)

    def _populate_providers(self, *, row: CapabilityRouteRow) -> None:
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        try:
            choices = self._controller.provider_choices(
                route_key=row.key, base_url=self.base_url_edit.text().strip()
            )
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
        provider = (
            self.provider_combo.currentData() or self.provider_combo.currentText()
        )
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
        current_provider = str(
            self.provider_combo.currentData() or self.provider_combo.currentText() or ""
        ).strip()
        current_model = str(
            self.model_combo.currentData() or self.model_combo.currentText() or ""
        ).strip()
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
        provider = str(
            self.provider_combo.currentData() or self.provider_combo.currentText() or ""
        ).strip()
        model = str(
            self.model_combo.currentData() or self.model_combo.currentText() or ""
        ).strip()
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
            voice_value = str(
                options.get("voice") or options.get("profile") or ""
            ).strip()
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
            voice = str(
                self.voice_combo.currentData() or self.voice_combo.currentText() or ""
            ).strip()
            if voice:
                options["voice"] = voice
            else:
                options.pop("voice", None)
                options.pop("profile", None)
        if row.key == "output.image.image_upscale":
            resolution = str(
                self.resolution_combo.currentData()
                or self.resolution_combo.currentText()
                or ""
            ).strip()
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
            provider = str(
                self.provider_combo.currentData()
                or self.provider_combo.currentText()
                or ""
            ).strip()
            model = str(
                self.model_combo.currentData() or self.model_combo.currentText() or ""
            ).strip()
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
        self.route_feedback.setText(
            "This route now uses the gateway-wide default again."
        )
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
    connection_status_updated = pyqtSignal(object)
    # Voice recognition callbacks arrive on a background recognizer thread;
    # these signals marshal them onto the Qt main thread before touching widgets.
    transcription_received = pyqtSignal(str)
    listening_stopped = pyqtSignal()

    # Run-teardown state (2026-07-10). Class-level defaults on purpose:
    # `getattr(self, ..., default)` on a missing attribute raises RuntimeError
    # (not AttributeError) on a QObject whose __init__ was skipped (tests build
    # palettes via __new__), while class attributes resolve through normal MRO.
    _cancel_requested = False
    _pending_submit = False

    def __init__(
        self, *, controller: AssistantV2Controller, debug: bool = False
    ) -> None:
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
        self._deferred_history_scroll_on_show = HistoryScrollRequest()
        # Ask-user wait deferred by the user (Cancel + "keep waiting").
        self._deferred_ask_payload: Optional[Dict[str, Any]] = None
        self._history_cards_by_key: Dict[str, QWidget] = {}
        self._history_refreshing = False
        self._status_text = "Ready"
        self._status_tone = "neutral"
        self._run_busy = False
        self._run_has_final_output = False
        self._active_tool_history_status: Optional[Dict[str, Any]] = None
        self._tray_animation_frame = 0
        self._tray_completion_unread = False
        self._connection_status_state = "unknown"
        self._connection_status_detail = "Checking gateway connection."
        self._hotkey_tooltip_note = ""
        self._connection_status_request_inflight = False
        self._tray_feedback_timer = QTimer(self)
        self._tray_feedback_timer.setInterval(_TRAY_BUSY_FRAME_INTERVAL_MS)
        self._tray_feedback_timer.timeout.connect(self._advance_tray_feedback)
        self._connection_status_timer = QTimer(self)
        self._connection_status_timer.setInterval(15000)
        self._connection_status_timer.timeout.connect(
            self._request_connection_status_refresh
        )
        self._history_settle_timer = QTimer(self)
        self._history_settle_timer.setSingleShot(True)
        self._history_settle_timer.timeout.connect(self._apply_pending_history_scroll)
        self.hotkey_activated.connect(self.toggle_palette)
        self.message_speech_started.connect(self._on_message_speech_started)
        self.message_speech_finished.connect(self._on_message_speech_finished)
        self.connection_status_updated.connect(self._apply_connection_status)
        self.transcription_received.connect(self._on_transcription)
        self.listening_stopped.connect(self._on_listen_stop)
        self._controller.voice_manager.on_speech_start = (
            self._emit_message_speech_started
        )

        self.setWindowTitle("AbstractAssistant")
        self.setWindowIcon(_qt_icon())
        self.setObjectName("assistantPalette")
        self.setMinimumSize(420, 260)
        self.resize(
            self._controller.preferences.window_width,
            self._controller.preferences.window_height,
        )
        self.setAcceptDrops(False)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
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
        header_shell.setContentsMargins(14, 4, 4, 4)
        header_shell.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        header_shell.addLayout(title_row)

        traffic_host = QWidget()
        traffic_host.setObjectName("trafficHost")
        traffic_host.setFixedSize(62, 14)
        title_row.addWidget(traffic_host, 0, Qt.AlignVCenter)
        self._traffic_host = traffic_host
        self._native_traffic_lights = None

        if _MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE:
            traffic_host.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._native_traffic_lights = MacTrafficLightButtonsBridge(
                owner=self,
                anchor=traffic_host,
                on_close=self._quit_application,
                on_minimize=self.hide,
                on_zoom=self._toggle_zoom,
            )
        else:
            traffic_group = QHBoxLayout(traffic_host)
            traffic_group.setContentsMargins(0, 0, 0, 0)
            traffic_group.setSpacing(5)

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
        title_row.addStretch(1)

        self.session_picker = QComboBox()
        self.session_picker.setObjectName("sessionPicker")
        self.session_picker.setFixedHeight(28)
        self.session_picker.setMinimumWidth(172)
        self.session_picker.setMaximumWidth(248)
        self.session_picker.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.session_picker.setMinimumContentsLength(18)
        self.session_picker.setToolTip("Jump to a recent session")
        self.session_picker.currentIndexChanged.connect(self._on_session_picker_changed)
        title_row.addWidget(self.session_picker, 1, Qt.AlignVCenter)

        header_actions = QHBoxLayout()
        header_actions.setContentsMargins(0, 0, 0, 0)
        header_actions.setSpacing(4)
        title_row.addLayout(header_actions, 0)

        new_session = QPushButton()
        new_session.setObjectName("iconButton")
        new_session.setIcon(_symbol_icon("plus"))
        new_session.setIconSize(QSize(14, 14))
        new_session.setFixedSize(24, 24)
        new_session.setToolTip("Start a fresh conversation / Clear history")
        new_session.clicked.connect(self._create_session)
        header_actions.addWidget(new_session)

        tools = QPushButton()
        tools.setObjectName("iconButton")
        tools.setIcon(_symbol_icon("spark"))
        tools.setIconSize(QSize(14, 14))
        tools.setFixedSize(24, 24)
        tools.setToolTip("Configure active agent capabilities & tool permissions")
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
        self.auto_speak.setToolTip("Toggle automatic voice output (Text-to-Speech)")
        header_actions.addWidget(self.auto_speak)

        settings = QPushButton()
        settings.setObjectName("iconButton")
        settings.setIcon(_symbol_icon("gear"))
        settings.setIconSize(QSize(14, 14))
        settings.setFixedSize(24, 24)
        settings.setToolTip("Open assistant preferences & gateway connection settings")
        settings.clicked.connect(self._open_settings)
        header_actions.addWidget(settings)

        self.connection_orb = ConnectionStatusOrb()
        self.connection_orb.setToolTip("Checking gateway connection")
        title_row.addWidget(self.connection_orb, 0, Qt.AlignVCenter)

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
        self.chat_status_label.setWordWrap(True)
        self.chat_status_label.setTextFormat(Qt.PlainText)
        self.chat_status_label.hide()
        history_wrap.addWidget(self.banner_label)
        history_wrap.addWidget(self.chat_status_label)
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
        self.attach_button.setToolTip(
            "Attach files, photos, or documents (Drag & Drop supported)"
        )
        self.attach_button.clicked.connect(self._pick_attachments)
        composer.addWidget(self.attach_button)

        self.mic_button = QPushButton()
        self.mic_button.setObjectName("composerIconButton")
        self.mic_button.setIcon(_symbol_icon("mic"))
        self.mic_button.setIconSize(QSize(16, 16))
        self.mic_button.setFixedSize(36, 36)
        self.mic_button.setToolTip("Use voice input / Speak your query")
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
        self.send_button.setToolTip("Send message")
        self.send_button.clicked.connect(self._on_send_button_clicked)
        # During a run the button is also the control surface: right-click
        # offers pause/resume/stop (click alone stops; typed text steers).
        self.send_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.send_button.customContextMenuRequested.connect(self._show_run_control_menu)
        composer.addWidget(self.send_button)

        QShortcut(Qt.Key_Escape, self, activated=self.hide)

        self._apply_styles()
        self._refresh_workflows()
        self.refresh_history()
        self._refresh_capability_state()
        self._refresh_submission_state()
        self._render_attachments()
        self._apply_hotkey()
        self._request_connection_status_refresh()
        self._connection_status_timer.start()
        QTimer.singleShot(0, self._reflow_shell)
        QTimer.singleShot(0, self._sync_native_traffic_lights)

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

    def _compose_connection_tooltip(self, detail: str) -> str:
        text = str(detail or "").strip() or "Checking gateway connection."
        note = str(getattr(self, "_hotkey_tooltip_note", "") or "").strip()
        if note:
            return f"{text}\n({note})"
        return text

    def _set_connection_indicator(self, state: str, detail: str) -> None:
        orb = getattr(self, "connection_orb", None)
        if orb is None:
            return
        self._connection_status_state = str(state or "").strip().lower() or "unknown"
        self._connection_status_detail = (
            str(detail or "").strip() or "Checking gateway connection."
        )
        orb.set_state(self._connection_status_state)
        orb.setToolTip(self._compose_connection_tooltip(self._connection_status_detail))
        orb.update()

    def _request_connection_status_refresh(self) -> None:
        if bool(getattr(self, "_connection_status_request_inflight", False)):
            return
        self._connection_status_request_inflight = True

        def _run() -> None:
            try:
                payload = self._controller.connection_status()
            except Exception as exc:
                payload = {
                    "ok": False,
                    "detail": str(exc or "Gateway unavailable.").strip(),
                }
            self.connection_status_updated.emit(payload)

        threading.Thread(target=_run, daemon=True).start()

    def _apply_connection_status(self, payload: Any) -> None:
        self._connection_status_request_inflight = False
        if not isinstance(payload, dict) or payload.get("ok") is False:
            detail = (
                str(payload.get("detail") or "Gateway unavailable.").strip()
                if isinstance(payload, dict)
                else "Gateway unavailable."
            )
            self._set_connection_indicator("disconnected", detail)
            return

        principal = (
            payload.get("principal")
            if isinstance(payload.get("principal"), dict)
            else {}
        )
        auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else {}
        routing = (
            payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
        )
        user_id = str(principal.get("user_id") or "unknown").strip()
        tenant_id = str(principal.get("tenant_id") or "").strip()
        mode = str(auth.get("mode") or "").strip() or "unknown"
        routing_mode = str(routing.get("mode") or "").strip()
        detail = f"Connected to gateway as {user_id}"
        if tenant_id:
            detail = f"{detail} in tenant {tenant_id}"
        detail = f"{detail} via {mode}"
        if routing_mode:
            detail = f"{detail} • routing: {routing_mode}"
        self._set_connection_indicator("connected", detail)

    def _active_session_id(self) -> str:
        return str(getattr(self._controller, "active_session_id", "") or "").strip()

    def _refresh_session_picker(
        self, *, select_session_id: Optional[str] = None
    ) -> None:
        combo = getattr(self, "session_picker", None)
        if combo is None:
            return
        try:
            sessions = list(self._controller.list_sessions() or [])
        except Exception:
            sessions = []

        active = str(select_session_id or self._active_session_id() or "").strip()
        selected_index = 0

        combo.blockSignals(True)
        try:
            combo.clear()
            for session in sessions:
                if not isinstance(session, dict):
                    continue
                session_id = str(session.get("session_id") or "").strip()
                if not session_id:
                    continue
                combo.addItem(_session_picker_label(session), session_id)
                item_index = combo.count() - 1
                combo.setItemData(
                    item_index, _session_picker_tooltip(session), Qt.ToolTipRole
                )
                if active and session_id == active:
                    selected_index = item_index
            if combo.count() <= 0:
                combo.addItem("No sessions yet")
                combo.setEnabled(False)
            else:
                combo.setEnabled(True)
                combo.setCurrentIndex(min(selected_index, combo.count() - 1))
        finally:
            combo.blockSignals(False)

    def _on_session_picker_changed(self, index: int) -> None:
        combo = getattr(self, "session_picker", None)
        if combo is None:
            return
        session_id = str(combo.itemData(int(index)) or "").strip()
        if not session_id:
            return
        current = self._active_session_id()
        if session_id == current:
            return
        if self._worker is not None:
            QMessageBox.information(
                self,
                "Session switch",
                "Please wait for the current response to finish.",
            )
            self._refresh_session_picker(select_session_id=current or None)
            return
        try:
            self._controller.switch_session(session_id)
        except Exception as exc:
            QMessageBox.warning(
                self, "Session switch", f"Failed to switch session:\n{exc}"
            )
            self._refresh_session_picker(select_session_id=current or None)
            return
        self._tray_completion_unread = False
        self._refresh_tray_feedback()
        self._set_history_status()
        self._set_status("Ready")
        self.refresh_history(request=self._history_scroll_request(mode="bottom"))

    def _set_status(self, text: str, tone: str = "neutral") -> None:
        self._status_text = str(text or "").strip() or "Ready"
        self._status_tone = str(tone or "neutral").strip() or "neutral"

    def _set_history_status(
        self,
        text: str = "",
        *,
        tone: str = "neutral",
        rich: bool = False,
        tooltip: Optional[str] = None,
    ) -> None:
        message = str(text or "").strip()
        if not message:
            self._active_tool_history_status = None
            self.chat_status_label.clear()
            self.chat_status_label.hide()
            return
        if rich:
            display = message
            self.chat_status_label.setTextFormat(Qt.RichText)
            self.chat_status_label.setWordWrap(False)
        else:
            self._active_tool_history_status = None
            display = message if len(message) <= 160 else f"{message[:157].rstrip()}..."
            self.chat_status_label.setTextFormat(Qt.PlainText)
            self.chat_status_label.setWordWrap(True)
        self.chat_status_label.setText(display)
        self.chat_status_label.setProperty(
            "tone", str(tone or "neutral").strip() or "neutral"
        )
        self.chat_status_label.setToolTip(str(tooltip or message))
        self._refresh_widget_style(self.chat_status_label)
        self.chat_status_label.show()

    def _tool_history_label_max_chars(self, *, prefix: str = "") -> int:
        """Approximate the longest single-line tool label that fits the current palette width."""

        fallback = 120
        try:
            label = getattr(self, "chat_status_label", None)
            width = (
                int(label.width())
                if label is not None and int(label.width()) > 80
                else 0
            )
            if width <= 80:
                card = getattr(self, "history_card", None)
                width = (
                    int(card.width()) - 34
                    if card is not None and int(card.width()) > 120
                    else 0
                )
            if width <= 80:
                width = int(self.width()) - 72 if int(self.width()) > 120 else 0
            if width <= 80:
                return fallback

            font = label.font() if label is not None else self.font()
            metrics = QFontMetrics(font)
            sample = "abcdefghijklmnopqrstuvwxyz0123456789_-./:=?&"
            avg_px = max(5.5, metrics.horizontalAdvance(sample) / max(1, len(sample)))
            prefix_px = metrics.horizontalAdvance(str(prefix or ""))
            usable_px = max(120, width - 18 - prefix_px)
            estimated = int(usable_px / avg_px)

            if bool(self.isMaximized()) or width >= 980:
                upper = 280
            elif width >= 720:
                upper = 210
            elif width >= 520:
                upper = 150
            else:
                upper = 96
            return max(64, min(upper, estimated))
        except Exception:
            return fallback

    def _tool_message_parts(self, message: Any) -> tuple[str, Any]:
        if not isinstance(message, dict):
            return "tool", None
        metadata = message.get("metadata")
        meta = metadata if isinstance(metadata, dict) else {}
        name = str(meta.get("name") or "").strip()
        if not name:
            content = str(message.get("content") or "")
            match = re.match(r"\s*\[([^\]]+)\]:", content)
            if match:
                name = str(match.group(1) or "").strip()
        arguments = meta.get("arguments")
        if arguments is None:
            arguments = meta.get("args")
        return name or "tool", arguments

    def _set_tool_history_status(
        self,
        *,
        name: str,
        arguments: Any,
        prefix: str = "",
        tone: str = "busy",
        remember: bool = True,
    ) -> None:
        budget = self._tool_history_label_max_chars(prefix=prefix)
        label = compact_tool_call_label(name, arguments, max_chars=budget)
        label_html = compact_tool_call_label_html(name, arguments, max_chars=budget)
        prefix_html = ""
        if prefix:
            prefix_html = f'<span style="color:#ffc963; font-weight:600;">{_html.escape(prefix)}</span>'
        self._set_history_status(
            f"{prefix_html}{label_html}",
            tone=tone,
            rich=True,
            tooltip=f"{prefix}{label}",
        )
        if remember:
            self._active_tool_history_status = {
                "name": str(name or "tool"),
                "arguments": arguments,
                "prefix": str(prefix or ""),
                "tone": str(tone or "busy"),
            }

    def _refresh_active_tool_history_status_for_width(self) -> None:
        payload = getattr(self, "_active_tool_history_status", None)
        if not isinstance(payload, dict):
            return
        self._set_tool_history_status(
            name=str(payload.get("name") or "tool"),
            arguments=payload.get("arguments"),
            prefix=str(payload.get("prefix") or ""),
            tone=str(payload.get("tone") or "busy"),
            remember=False,
        )

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
        self._refresh_tray_feedback()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.hide()
        event.ignore()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_native_traffic_lights)
        QTimer.singleShot(0, self._restore_deferred_history_scroll_on_show)
        self._request_connection_status_refresh()
        # Re-prompt an ask-user wait the user deferred with Cancel.
        deferred = getattr(self, "_deferred_ask_payload", None)
        if isinstance(deferred, dict):
            self._deferred_ask_payload = None
            if getattr(self, "_worker", None) is not None:
                QTimer.singleShot(
                    250, lambda payload=dict(deferred): self._on_worker_event(payload)
                )

    def resizeEvent(self, event) -> None:  # noqa: N802
        preserve_request = None
        if not bool(getattr(self, "_history_refreshing", False)):
            preserve_request = self._capture_history_scroll_request()
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_visible_history_cards)
        QTimer.singleShot(0, self._sync_native_traffic_lights)
        QTimer.singleShot(0, self._refresh_active_tool_history_status_for_width)
        if preserve_request is not None:
            self._commit_history_scroll_request(preserve_request)

    def _sync_native_traffic_lights(self) -> None:
        bridge = getattr(self, "_native_traffic_lights", None)
        if bridge is None:
            return
        bridge.sync_geometry()

    def _quit_application(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def shutdown(self) -> None:
        """Best-effort cleanup before the process exits.

        Wired to ``QApplication.aboutToQuit`` so quitting mid-run does not tear
        down a live ``GatewayWorker`` thread (Qt aborts with "QThread:
        Destroyed while thread is still running"). The run stays durable
        server-side; we only stop the local follower.
        """
        worker = getattr(self, "_worker", None)
        if worker is not None:
            try:
                worker.requestInterruption()
            except Exception:
                pass
            try:
                worker.wait(2000)
            except Exception:
                pass
        try:
            hotkey = getattr(self, "_hotkey", None)
            if hotkey is not None:
                hotkey.stop()
        except Exception:
            pass
        try:
            voice = getattr(self._controller, "voice_manager", None)
            if voice is not None and hasattr(voice, "cleanup"):
                voice.cleanup()
        except Exception:
            pass

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
            if key in {Qt.Key_Return, Qt.Key_Enter} and not (
                modifiers & int(Qt.ShiftModifier)
            ):
                self._submit()
                return True
        history_host = state.get("history_host")
        if obj is history_host and event is not None:
            if event.type() in {QEvent.LayoutRequest, QEvent.Resize, QEvent.Show}:
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
        if (
            self._settings_dialog is not None
            and self._settings_dialog.isVisible()
            and self._settings_dialog.isActiveWindow()
        ):
            return
        if (
            self._tool_settings_dialog is not None
            and self._tool_settings_dialog.isVisible()
            and self._tool_settings_dialog.isActiveWindow()
        ):
            return
        self.hide()

    def _available_screen_geometry(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return None
        return screen.availableGeometry()

    def _clamp_window_to_screen(
        self, *, x: int, y: int, width: int, height: int, screen_geom
    ):
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
        normal_width = min(
            max(int(prefs.window_width), 420), min(612, int(screen_geom.width() * 0.38))
        )
        normal_height = min(
            max(int(prefs.window_height), 320),
            min(392, int(screen_geom.height() * 0.46)),
        )
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
        composer_height = int(
            self.composer_card.height() or self.composer_card.sizeHint().height() or 80
        )
        side_gap = 8
        card_gap = 4
        top_gap = 4
        bottom_gap = 4
        if self._zoomed:
            width, target_height = _zoomed_shell_size(
                screen_width=int(screen_geom.width()),
                screen_height=int(screen_geom.height()),
                normal_width=normal_width,
                normal_height=normal_height,
            )
            card_width = max(420 - (side_gap * 2), width - (side_gap * 2))
            history_height = max(
                132,
                int(
                    target_height
                    - top_gap
                    - bottom_gap
                    - header_height
                    - composer_height
                    - (card_gap * 2)
                ),
            )
            self.history_card.setMinimumHeight(history_height)
            self.history_card.setMaximumHeight(history_height)
            self.header_card.setGeometry(side_gap, top_gap, card_width, header_height)
            history_y = top_gap + header_height + card_gap
            self.history_card.setGeometry(
                side_gap, history_y, card_width, history_height
            )
            composer_y = history_y + history_height + card_gap
            self.composer_card.setGeometry(
                side_gap, composer_y, card_width, composer_height
            )
            x = int(screen_geom.x() + max(0, (screen_geom.width() - width) / 2))
            y = int(
                screen_geom.y() + max(0, (screen_geom.height() - target_height) / 2)
            )
            self.setGeometry(x, y, width, target_height)
            QTimer.singleShot(0, self._sync_native_traffic_lights)
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
        self.composer_card.setGeometry(
            side_gap, composer_y, card_width, composer_height
        )
        target_height = int(composer_y + composer_height + bottom_gap)
        self.resize(width, target_height)
        self.position_near_tray()
        QTimer.singleShot(0, self._sync_native_traffic_lights)

    def _toggle_zoom(self) -> None:
        self._zoomed = not bool(self._zoomed)
        self._reflow_shell()

    def show_palette(self) -> None:
        self._tray_completion_unread = False
        self._refresh_tray_feedback()
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
        scroll_request = (
            request
            if isinstance(request, HistoryScrollRequest)
            else self._default_history_refresh_request()
        )
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
                message_key = _history_message_key(
                    message, fallback_index=visible_index
                )
                bubble_width = _message_bubble_width(viewport_width, role=role)
                card = MessageCard(
                    message=message,
                    message_key=message_key,
                    renderer=self._renderer,
                    on_open_artifact=self._open_artifact_from_message,
                    build_media_preview=self._build_media_preview,
                    bubble_width=bubble_width,
                    on_toggle_voice=None if is_user else self._toggle_message_voice,
                    on_show_tools=None if is_user else self._show_message_tools,
                    on_show_files=None if is_user else self._show_message_files,
                    voice_state=(
                        "idle" if is_user else self._message_voice_state(message)
                    ),
                )
                self._history_cards_by_key[message_key] = card
                self.history_layout.addWidget(card)
            if self._show_thinking_indicator():
                self.history_layout.addWidget(ThinkingIndicatorCard())
            self._sync_history_viewport()
            self._refresh_session_picker(
                select_session_id=self._active_session_id() or None
            )
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

    def _default_history_refresh_request(self) -> HistoryScrollRequest:
        cards_by_key = getattr(self, "__dict__", {}).get("_history_cards_by_key", {})
        if isinstance(cards_by_key, dict) and cards_by_key:
            return self._capture_history_scroll_request()
        if self._latest_visible_message_key():
            return self._history_scroll_request(mode="bottom")
        return self._history_scroll_request()

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

    def _commit_history_scroll_request(
        self, request: Optional[HistoryScrollRequest]
    ) -> None:
        if not isinstance(request, HistoryScrollRequest):
            request = self._history_scroll_request()
        state = getattr(self, "__dict__", {})
        timer = state.get("_history_settle_timer")
        if timer is not None:
            timer.stop()
        self._pending_history_scroll = request
        if not self.isVisible():
            if request.mode in {"bottom", "message_top"}:
                self._deferred_history_scroll_on_show = request
            elif getattr(self, "_deferred_history_scroll_on_show", None) is None:
                self._deferred_history_scroll_on_show = self._history_scroll_request(
                    mode="bottom"
                )
            return
        self._deferred_history_scroll_on_show = self._history_scroll_request()
        self._schedule_history_scroll_apply()

    def _restore_deferred_history_scroll_on_show(self) -> None:
        request = getattr(self, "_deferred_history_scroll_on_show", None)
        if request is None or request.mode not in {"bottom", "message_top"}:
            request = self._history_scroll_request(mode="bottom")
        self._deferred_history_scroll_on_show = self._history_scroll_request()
        self._commit_history_scroll_request(request)

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
        request = getattr(self, "__dict__", {}).get(
            "_pending_history_scroll", HistoryScrollRequest()
        )
        self._sync_history_viewport()
        self._pending_history_scroll = self._history_scroll_request()
        self._apply_history_scroll_request(request)

    def _apply_history_scroll_request(self, request: HistoryScrollRequest) -> None:
        scroll = getattr(self, "__dict__", {}).get("history_scroll")
        if scroll is None:
            return
        bar = scroll.verticalScrollBar()
        if bar is None:
            return
        normalized = (
            str(getattr(request, "mode", "preserve") or "preserve").strip().lower()
        )
        if normalized == "bottom":
            bar.setValue(bar.maximum())
            # Asynchronous text browser reflow safety timers
            QTimer.singleShot(50, lambda: bar.setValue(bar.maximum()))
            QTimer.singleShot(150, lambda: bar.setValue(bar.maximum()))
            return
        target_key = str(getattr(request, "message_key", "") or "").strip()
        if normalized == "message_top" and not target_key:
            target_key = self._latest_visible_message_key(role="assistant")
        if not target_key:
            return
        cards_by_key = getattr(self, "__dict__", {}).get("_history_cards_by_key", {})
        target_widget = (
            cards_by_key.get(target_key) if isinstance(cards_by_key, dict) else None
        )
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
        next_items = [
            item
            for item in self._attachments
            if _normalize_attachment_path(item) != target
        ]
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
                self.attachments_layout.addWidget(
                    chip, 0, Qt.AlignLeft | Qt.AlignVCenter
                )
            self.attachments_layout.addStretch(1)
        else:
            hint = QLabel("Drop files to attach")
            hint.setObjectName("attachmentsDropHint")
            self.attachments_layout.addWidget(hint, 0, Qt.AlignLeft | Qt.AlignVCenter)
            self.attachments_layout.addStretch(1)
        self.attachments_tray.show()
        self.composer_card.setFixedHeight(96)
        self._reflow_shell()

    def _on_send_button_clicked(self) -> None:
        """The composer button sends when idle and stops the run when busy."""
        if self._worker is not None:
            self._cancel_active_run()
            return
        self._submit()

    def _set_send_button_busy(self, busy: bool) -> None:
        """Morph the composer button between Send and Stop."""
        try:
            button = getattr(self, "send_button", None)
        except Exception:
            # QObject attribute access raises when __init__ was skipped (tests).
            button = None
        if button is None:
            return
        if busy:
            button.setIcon(_symbol_icon("stop", color="#f8fffc"))
            button.setToolTip(
                "Stop this run — typed text steers it instead (right-click: pause/resume)"
            )
            button.setEnabled(True)
        else:
            button.setIcon(_symbol_icon("send", color="#f8fffc"))
            button.setToolTip("Send message")

    def _cancel_active_run(self) -> None:
        """Stop the in-flight run: cancel server-side and interrupt the follower."""
        worker = getattr(self, "_worker", None)
        run_id = str(self._controller.last_run_id() or "").strip()
        if run_id:
            self._controller.cancel_run(run_id)
        if worker is not None:
            try:
                worker.requestInterruption()
            except Exception:
                pass
        # The follower honors the interruption only at its next SSE line/idle
        # window, so the worker can linger for seconds. Mark the teardown so
        # typed text is never steered into the cancelled run, and hand the
        # Send button back immediately — the user stopped this run on purpose
        # and expects to relaunch (a send during teardown is queued, see
        # _submit / _on_worker_finished).
        self._cancel_requested = True
        self._set_send_button_busy(False)
        self._set_status("Stopping…", tone="busy")
        self._set_history_status("Stopping the current run…", tone="busy")

    def _steer_active_run(self) -> bool:
        """Send the composer text as steering to the run in progress.

        The guidance lands in the run's durable inbox (gateway inject_guidance)
        and folds into the agent's next reasoning cycle — no cancel/restart,
        the run keeps its context. Returns True when the text was consumed.
        """
        guidance = self.prompt_edit.toPlainText().strip()
        if not guidance:
            return False
        run_id = str(self._controller.last_run_id() or "").strip()
        if not run_id or not self._controller.inject_guidance(run_id, guidance):
            return False
        self.prompt_edit.clear()
        # Show the interjection in the transcript so the thread reads truthfully.
        try:
            self._controller.append_user_message(
                guidance, metadata={"kind": "operator_guidance"}
            )
            self.refresh_history(request=self._history_scroll_request(mode="bottom"))
        except Exception:
            pass
        preview = guidance if len(guidance) <= 80 else f"{guidance[:77]}..."
        self._set_status("Steering the run…", tone="busy")
        self._set_history_status(f"Steering: {preview}", tone="busy")
        return True

    def _pause_active_run(self) -> None:
        run_id = str(self._controller.last_run_id() or "").strip()
        if run_id and self._controller.pause_run(run_id):
            self._set_status("Pausing…", tone="busy")
            self._set_history_status(
                "Pausing — takes effect at the next step boundary", tone="busy"
            )

    def _resume_active_run(self) -> None:
        run_id = str(self._controller.last_run_id() or "").strip()
        if run_id and self._controller.resume_run(run_id):
            self._set_status("Resumed", tone="busy")
            self._set_history_status("Resumed", tone="busy")

    def _show_run_control_menu(self, pos) -> None:
        if self._worker is None:
            return
        menu = QMenu(self.send_button)
        act_pause = menu.addAction("Pause run")
        act_resume = menu.addAction("Resume run")
        menu.addSeparator()
        act_stop = menu.addAction("Stop run")
        chosen = menu.exec_(self.send_button.mapToGlobal(pos))
        if chosen == act_pause:
            self._pause_active_run()
        elif chosen == act_resume:
            self._resume_active_run()
        elif chosen == act_stop:
            self._cancel_active_run()

    def _submit(self) -> None:
        worker = self._worker
        if worker is not None:
            try:
                alive = bool(worker.isRunning())
            except Exception:
                alive = False
            if alive and not bool(self._cancel_requested):
                # A run is in progress: typed text becomes steering (2026-07-10),
                # so the user can redirect the agent without losing its context.
                self._steer_active_run()
                return
            if alive:
                # Stop was requested but the follower is still winding down. A
                # live QThread must never be rebound (Qt aborts), and steering a
                # cancelled run would silently swallow the message — queue it
                # instead; _on_worker_finished sends it the moment the old
                # worker closes. The composer keeps the text meanwhile.
                if self.prompt_edit.toPlainText().strip():
                    self._pending_submit = True
                    self._set_history_status(
                        "Finishing the stopped run — your message will send in a moment.",
                        tone="info",
                    )
                return
            # Stale reference: the thread already finished (finished-signal
            # race) — clear it and proceed with a fresh send.
            self._worker = None
        self._pending_submit = False
        self._cancel_requested = False
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt and not self._attachments:
            return
        plan = self._controller.submission_plan(
            prompt=prompt, attachments=self._attachments
        )
        if not bool(plan.get("ready", True)):
            detail = str(
                plan.get("detail") or "This request cannot run right now."
            ).strip()
            QMessageBox.critical(self, "Assistant unavailable", detail)
            return

        attachments = list(self._attachments)
        append_user_now = bool(prompt or attachments)

        # Clear text input, clear attachments queue, and reflow layout first
        self.prompt_edit.clear()
        self._attachments = []
        self._render_attachments()

        if append_user_now:
            metadata = None
            preview_items = _local_attachment_preview_items(attachments)
            if preview_items:
                metadata = {
                    "attachments": preview_items,
                    "media": preview_items,
                }
        self._controller.append_user_message(prompt, metadata=metadata)

        self._run_busy = True
        self._run_has_final_output = False
        self._tray_completion_unread = False
        self._set_status("Running assistant workflow...", tone="busy")
        self._set_history_status("Running assistant workflow...", tone="busy")
        self._refresh_tray_feedback()
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
        self._set_send_button_busy(True)

        # Refresh history and scroll to bottom at the very end
        self.refresh_history(request=self._history_scroll_request(mode="bottom"))

    def _on_worker_event(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        typ = str(payload.get("type") or "").strip()
        if typ == "status":
            status_text = str(payload.get("status") or "Working").strip() or "Working"
            status_lower = status_text.lower()
            inactive_statuses = {
                "completed",
                "complete",
                "ready",
                "idle",
                "offline",
                "error",
                "failed",
                "cancelled",
            }
            self._run_busy = (
                status_lower not in inactive_statuses and not self._run_has_final_output
            )
            self._set_status(status_text, tone="busy" if self._run_busy else "neutral")
            if self._run_busy:
                if not str(self.chat_status_label.text() or "").strip():
                    self._set_history_status(status_text, tone="busy")
            elif status_lower in {"offline", "error", "failed", "cancelled"}:
                tone = "error" if status_lower in {"error", "failed"} else "info"
                self._set_history_status(status_text, tone=tone)
            self._refresh_tray_feedback()
            return
        if typ == "run_activity":
            summary = str(payload.get("summary") or "").strip()
            if summary:
                self._set_history_status(summary, tone="busy")
            return
        if typ == "cycle":
            # Agent reasoning cycle starting (adapter counts llm_call starts on
            # the reason node): live "the agent is thinking, Nth pass" signal.
            n = payload.get("iteration")
            self._set_history_status(f"Thinking — cycle {n}", tone="busy")
            return
        if typ == "tool_started":
            # Tool launch with args, emitted BEFORE execution (STARTED ledger
            # record) — previously only tool results were visible.
            tools = [t for t in (payload.get("tools") or []) if isinstance(t, dict)]
            names = ", ".join(str(t.get("name") or "") for t in tools if t.get("name"))
            label = f"Tool: {names}" if names else "Running tools"
            if len(tools) == 1:
                preview = str(tools[0].get("arguments_preview") or "").strip()
                if preview:
                    label = f"{label} {preview}"
            self._set_history_status(label, tone="busy")
            return
        if typ == "replay_degraded":
            message = str(payload.get("message") or "Gateway replay is degraded.").strip()
            self._run_busy = False
            self._run_has_final_output = True
            self._set_status("Replay degraded", tone="error")
            self._set_history_status(message, tone="error")
            self._refresh_tray_feedback()
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
            metadata = (
                payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            )
            fallback_completion = (
                str(metadata.get("kind") or "").strip().lower() == "fallback_completion"
            )
            self._set_status("Ready")
            if is_final and fallback_completion:
                self._set_history_status(
                    str(payload.get("content") or "").strip(), tone="info"
                )
            elif is_final:
                self._set_history_status()
            if self.auto_speak.isChecked() and is_final:
                self._controller.voice_manager.speak(str(payload.get("content") or ""))
            if is_final:
                content = str(payload.get("content") or "").strip()
                hidden = not self.isVisible()
                self._tray_completion_unread = hidden
                self._refresh_tray_feedback()
                if hidden:
                    self._notify_completion_ready(content)
            return
        if typ == "tool_request":
            tool_calls = (
                payload.get("tool_calls")
                if isinstance(payload.get("tool_calls"), list)
                else []
            )
            # Answer the wait by identity: a second approval request can arrive
            # while the dialog is open and would otherwise steal the answer.
            wait_run_id = str(payload.get("run_id") or "").strip()
            wait_key = str(payload.get("wait_key") or "").strip()

            def _answer_tool_approval(approved_flag: bool) -> None:
                worker = getattr(self, "_worker", None)
                if worker is None:
                    return
                if wait_run_id and wait_key:
                    worker.provide_tool_approval(
                        approved_flag, run_id=wait_run_id, wait_key=wait_key
                    )
                else:
                    worker.provide_tool_approval(approved_flag)

            if tool_calls:
                summary = _tool_call_summary(tool_calls[0])
                self._set_tool_history_status(
                    name=summary.name,
                    arguments=tool_calls[0].get("arguments"),
                    prefix="Waiting for approval: ",
                )
            else:
                self._set_history_status("Waiting for tool approval", tone="busy")
            if self._controller.should_auto_approve_tool_batch(tool_calls):
                if tool_calls:
                    summary = _tool_call_summary(tool_calls[0])
                    self._set_tool_history_status(
                        name=summary.name,
                        arguments=tool_calls[0].get("arguments"),
                        prefix="Auto-approved in this chat: ",
                    )
                else:
                    self._set_history_status(
                        "Auto-approved tools in this chat", tone="busy"
                    )
                _answer_tool_approval(True)
                return
            dialog = ToolApprovalDialog(
                tool_calls=payload.get("tool_calls"), parent=self
            )
            approved = dialog.exec_() == QDialog.Accepted
            if (
                approved
                and str(getattr(dialog, "approval_scope", "once") or "once")
                == "session"
            ):
                self._controller.grant_session_tool_auto_approval()
                self._set_banner(
                    "Trusting enabled tools in this chat. Disabled tools stay disabled; gateway limits still apply.",
                    tone="info",
                )
            _answer_tool_approval(approved)
            return
        if typ == "ask_user":
            prompt = str(payload.get("prompt") or "Input required").strip()
            wait_run_id = str(payload.get("run_id") or "").strip()
            wait_key = str(payload.get("wait_key") or "").strip()
            short_prompt = (
                prompt if len(prompt) <= 120 else f"{prompt[:117].rstrip()}..."
            )
            self._set_history_status(
                f"Waiting for your input: {short_prompt}", tone="busy"
            )
            response, ok = QInputDialog.getText(self, "Input required", prompt)
            if not ok:
                # Cancel used to silently resume the run with an empty answer.
                choice = QMessageBox.question(
                    self,
                    "Run is waiting for your answer",
                    "Send an empty response so the run can continue?\n\n"
                    "Choosing No keeps the run waiting; showing this window "
                    "again will ask the question again.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if choice != QMessageBox.Yes:
                    self._deferred_ask_payload = dict(payload)
                    self._set_history_status(
                        f"Waiting for your input (dismissed): {short_prompt}",
                        tone="busy",
                    )
                    return
                response = ""
            self._deferred_ask_payload = None
            worker = getattr(self, "_worker", None)
            if worker is not None:
                if wait_run_id and wait_key:
                    worker.provide_user_response(
                        str(response or ""), run_id=wait_run_id, wait_key=wait_key
                    )
                else:
                    worker.provide_user_response(str(response or ""))
            return
        if typ == "history_seeded":
            if not bool(payload.get("changed", True)):
                return
            assistant_key = self._latest_visible_message_key(role="assistant")
            if assistant_key:
                self.refresh_history(
                    request=self._history_scroll_request(
                        mode="message_top", message_key=assistant_key
                    )
                )
            elif self._latest_visible_message_key():
                self.refresh_history(
                    request=self._history_scroll_request(mode="bottom")
                )
            else:
                self.refresh_history()
            return
        if typ == "tool":
            message = (
                payload.get("message")
                if isinstance(payload.get("message"), dict)
                else {}
            )
            name, arguments = self._tool_message_parts(message)
            self._set_tool_history_status(name=name, arguments=arguments)
            return

    def _on_worker_error(self, error: str) -> None:
        self._run_busy = False
        self._run_has_final_output = True
        self._tray_completion_unread = False
        self._worker = None
        self._set_send_button_busy(False)
        self._set_status("Error", tone="error")
        self._set_history_status(str(error or "Unknown error"), tone="error")
        self._refresh_tray_feedback()
        self._notify("Assistant error", str(error or "Unknown error"))
        QMessageBox.critical(self, "Assistant error", str(error or "Unknown error"))

    def _on_worker_finished(self) -> None:
        had_indicator = self._show_thinking_indicator()
        was_stopped = bool(self._cancel_requested)
        self._worker = None
        self._run_busy = False
        self._cancel_requested = False
        self._set_send_button_busy(False)
        if not self._run_has_final_output:
            # A user-stopped run legitimately has no final answer — say so
            # instead of the misleading "completed but returned no written reply".
            fallback = (
                "Run stopped."
                if was_stopped
                else "The workflow completed, but it returned no written reply."
            )
            self._run_has_final_output = True
            self._set_history_status(fallback, tone="info")
        self._refresh_tray_feedback()
        if had_indicator != self._show_thinking_indicator():
            self.refresh_history()
        self._set_status("Ready")
        # A send queued during teardown (stop clicked, user typed the next
        # message before the follower closed) fires now.
        if self._pending_submit:
            self._pending_submit = False
            prompt_edit = getattr(self, "prompt_edit", None)
            if prompt_edit is not None and prompt_edit.toPlainText().strip():
                QTimer.singleShot(0, self._submit)

    def _on_user_message_appended(self, _content: str = "") -> None:
        self.refresh_history(request=self._history_scroll_request(mode="bottom"))

    def _open_artifact_from_message(
        self, artifact: Dict[str, Any], message: Dict[str, Any]
    ) -> None:
        metadata = (
            message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        )
        run_id = str(
            metadata.get("artifact_run_id")
            or metadata.get("run_id")
            or message.get("run_id")
            or self._controller.last_run_id()
            or self._controller.session_run_id()
            or ""
        ).strip()
        self._open_artifact(artifact, run_id=run_id)

    def _build_media_preview(
        self, artifact: Dict[str, Any], message: Dict[str, Any]
    ) -> Optional[QWidget]:
        if not isinstance(artifact, dict):
            return None
        if _artifact_media_kind(artifact) not in {"image", "audio", "video"}:
            return None

        metadata = (
            message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        )
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

        return ArtifactPreviewCard(
            artifact=artifact, resolve_path=_resolve, parent=self
        )

    def _open_artifact(self, artifact: Dict[str, Any], *, run_id: str) -> None:
        try:
            path = self._controller.download_artifact(run_id=run_id, artifact=artifact)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _show_message_tools(self, message: Dict[str, Any]) -> None:
        dialog = ToolUsageDialog(
            message=message,
            tool_calls=_assistant_tool_calls_for_message(message),
            source="metadata",
            parent=self,
        )
        self._run_usage_lookup(
            message=message, dialog=dialog, apply=dialog.update_tool_usage
        )

    def _show_message_files(self, message: Dict[str, Any]) -> None:
        dialog = FileActivityDialog(
            message=message,
            tool_calls=_assistant_tool_calls_for_message(message),
            source="metadata",
            parent=self,
        )
        self._run_usage_lookup(
            message=message, dialog=dialog, apply=dialog.update_file_activity
        )

    def _run_usage_lookup(self, *, message: Dict[str, Any], dialog, apply) -> None:
        """Open a usage dialog and refresh it from the run ledger in background.

        ``apply`` is the dialog's update method; the ledger lookup returns the
        executed tool calls, from which each dialog derives its own view
        (tool cards or file-operation cards).
        """
        worker = ToolUsageLookupWorker(
            controller=self._controller, message=message, parent=dialog
        )
        try:
            state = self.__dict__
        except Exception:
            state = {}
        workers = state.get("_tool_usage_workers")
        if not isinstance(workers, list):
            workers = []
            state["_tool_usage_workers"] = workers
        workers.append(worker)

        def _loaded(result: Any) -> None:
            payload = result if isinstance(result, dict) else {}
            apply(
                tool_calls=(
                    payload.get("tool_calls")
                    if isinstance(payload.get("tool_calls"), list)
                    else []
                ),
                source=str(payload.get("source") or ""),
                run_ids=(
                    payload.get("run_ids")
                    if isinstance(payload.get("run_ids"), list)
                    else []
                ),
                error=str(payload.get("error") or ""),
            )

        def _failed(error: str) -> None:
            apply(tool_calls=[], source="error", run_ids=[], error=str(error or ""))

        def _cleanup() -> None:
            try:
                workers.remove(worker)
            except ValueError:
                pass
            worker.deleteLater()

        worker.loaded.connect(_loaded)
        worker.failed.connect(_failed)
        worker.finished.connect(_cleanup)
        dialog.set_loading()
        worker.start()
        dialog.exec_()

    def _message_voice_state(self, message: Dict[str, Any]) -> str:
        key = _message_key(message)
        if key != str(self._active_spoken_message_key or ""):
            return "idle"
        if str(self._active_spoken_message_phase or "") == "synthesizing":
            return "synthesizing"
        if str(self._active_spoken_message_phase or "") == "paused":
            return "paused"
        if str(self._active_spoken_message_phase or "") == "speaking":
            return "speaking"
        if self._controller.voice_manager.is_paused():
            return "paused"
        if self._controller.voice_manager.is_speaking():
            return "speaking"
        self._active_spoken_message_key = ""
        self._active_spoken_message_phase = "idle"
        return "idle"

    def _set_message_voice_card_state(self, key: str, state: str) -> None:
        cards_by_key = getattr(self, "__dict__", {}).get("_history_cards_by_key", {})
        card = (
            cards_by_key.get(str(key or "").strip())
            if isinstance(cards_by_key, dict)
            else None
        )
        if card is None:
            return
        setter = getattr(card, "set_voice_state", None)
        if callable(setter):
            setter(str(state or "").strip())

    def _toggle_message_voice(self, message: Dict[str, Any]) -> None:
        key = _message_key(message)
        state = self._message_voice_state(message)
        voice = self._controller.voice_manager
        if state == "synthesizing":
            voice.pause()
            self._active_spoken_message_phase = "paused"
            self._set_message_voice_card_state(key, "paused")
            return
        if state == "speaking":
            voice.pause()
            self._active_spoken_message_phase = "paused"
            self._set_message_voice_card_state(key, "paused")
            return
        if state == "paused":
            voice.resume()
            self._active_spoken_message_phase = "speaking"
            self._set_message_voice_card_state(key, "speaking")
            return
        previous_key = str(self._active_spoken_message_key or "").strip()
        voice.stop_speaking()
        if previous_key and previous_key != key:
            self._set_message_voice_card_state(previous_key, "idle")
        content = str(message.get("content") or "").strip()
        if not content:
            return
        self._active_spoken_message_key = key
        self._active_spoken_message_phase = "synthesizing"
        self._set_message_voice_card_state(key, "synthesizing")
        started = voice.speak(
            content, callback=lambda key=key: self.message_speech_finished.emit(key)
        )
        if started:
            self._active_spoken_message_key = key
        else:
            self._active_spoken_message_key = ""
            self._active_spoken_message_phase = "idle"
            self._set_message_voice_card_state(key, "idle")

    def _on_message_speech_finished(self, key: str) -> None:
        if str(self._active_spoken_message_key or "") == str(key or ""):
            self._active_spoken_message_key = ""
            self._active_spoken_message_phase = "idle"
        self._set_message_voice_card_state(str(key or ""), "idle")

    def _emit_message_speech_started(self) -> None:
        key = str(self._active_spoken_message_key or "").strip()
        if key:
            self.message_speech_started.emit(key)

    def _on_message_speech_started(self, key: str) -> None:
        if str(self._active_spoken_message_key or "") != str(key or ""):
            return
        self._active_spoken_message_phase = "speaking"
        self._set_message_voice_card_state(str(key or ""), "speaking")

    def _toggle_listening(self) -> None:
        if self._listening:
            self._controller.voice_manager.stop_listening()
            self._listening = False
            self.mic_button.setChecked(False)
            self.mic_button.setToolTip("Speak your question")
            self._set_status("Ready")
            return
        try:
            # Emit through signals: these callbacks fire on the recognizer's
            # background thread, and the slots mutate Qt widgets.
            self._controller.voice_manager.listen(
                on_transcription=lambda text: self.transcription_received.emit(str(text or "")),
                on_stop=lambda: self.listening_stopped.emit(),
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
            dialog = SettingsDialog(
                controller=self._controller,
                apply_hotkey=self._apply_hotkey,
                parent=self,
            )
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
                x = int(
                    screen_geom.x() + screen_geom.width() - dialog_geom.width() - x_gap
                )
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
        self._request_connection_status_refresh()
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
            self._hotkey_tooltip_note = ""
            self._hotkey.stop()
            self._set_connection_indicator(
                self._connection_status_state, self._connection_status_detail
            )
            return
        ok = self._hotkey.start(
            sequence=prefs.hotkey_sequence, callback=self.hotkey_activated.emit
        )
        msg = (
            "Summon shortcut unavailable. Use the tray icon or reinstall hotkey support."
            if (not ok and self._hotkey.error)
            else ""
        )
        self._hotkey_tooltip_note = msg
        if self._tray is not None:
            self._tray.setToolTip(
                f"AbstractAssistant\n({msg})" if msg else "AbstractAssistant"
            )
        self._set_connection_indicator(
            self._connection_status_state, self._connection_status_detail
        )
        self.history_card.setToolTip("")
        if self._status_tone not in {"error", "busy"}:
            self._set_status("Ready")

    def _refresh_capability_state(self) -> None:
        tts_available = self._controller.supports_tts()
        stt_available = self._controller.supports_stt()
        self.auto_speak.setEnabled(tts_available)
        self.auto_speak.setToolTip(
            "" if tts_available else "Gateway voice output is not configured."
        )
        self.mic_button.setEnabled(stt_available)
        self.mic_button.setToolTip(
            "" if stt_available else "Gateway speech input is not configured."
        )
        self._update_prompt_placeholder()
        self._refresh_submission_state()

    def _update_prompt_placeholder(self) -> None:
        self.prompt_edit.setPlaceholderText(
            "Ask anything or drop files here. The assistant will choose the right tools or media on the gateway."
        )

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

    def _tray_feedback_state(self) -> str:
        if self._show_thinking_indicator():
            return "busy"
        if self._tray_completion_unread:
            return "complete"
        return "idle"

    def _refresh_tray_feedback(self) -> None:
        tray = self._tray
        if tray is None:
            return
        state = self._tray_feedback_state()
        if state == "busy":
            if not self._tray_feedback_timer.isActive():
                self._tray_feedback_timer.start()
        else:
            self._tray_feedback_timer.stop()
            self._tray_animation_frame = 0
        try:
            tray.setIcon(
                _tray_feedback_icon(state=state, frame=self._tray_animation_frame)
            )
        except Exception:
            pass
        tooltip = "AbstractAssistant"
        if state == "busy":
            tooltip = "AbstractAssistant • Thinking..."
        elif state == "complete":
            tooltip = "AbstractAssistant • Reply ready"
        try:
            tray.setToolTip(tooltip)
        except Exception:
            pass

    def _advance_tray_feedback(self) -> None:
        if self._tray_feedback_state() != "busy":
            self._tray_feedback_timer.stop()
            return
        self._tray_animation_frame = (
            self._tray_animation_frame + 1
        ) % _TRAY_BUSY_FRAME_COUNT
        self._refresh_tray_feedback()

    def _notify(
        self,
        title: str,
        message: str,
        *,
        icon: Optional[QIcon] = None,
        duration_ms: int = 5000,
    ) -> None:
        tray = self._tray
        if tray is None:
            return
        text = str(message or "").strip()
        if not text:
            return
        try:
            if icon is not None:
                tray.showMessage(title, text[:220], icon, duration_ms)
            else:
                tray.showMessage(
                    title, text[:220], QSystemTrayIcon.Information, duration_ms
                )
        except Exception:
            try:
                tray.showMessage(
                    title, text[:220], QSystemTrayIcon.Information, duration_ms
                )
            except Exception:
                pass

    def _notify_completion_ready(self, message: str) -> None:
        text = re.sub(r"\s+", " ", str(message or "").strip())
        excerpt = text[:140].rstrip()
        if len(text) > len(excerpt):
            excerpt = f"{excerpt}..."
        body = "Your reply is waiting in the menu bar."
        if excerpt:
            body = (
                f"Fresh reply ready.\n{excerpt}\nClick the shimmering orbit to open it."
            )
        self._notify(
            "Fresh Reply Ready",
            body,
            icon=_tray_feedback_icon(state="complete"),
            duration_ms=7000,
        )

    def _scroll_history_to_latest(self) -> None:
        self._apply_history_scroll_request(self._history_scroll_request(mode="bottom"))

    def _apply_styles(self) -> None:
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#0c1016"))
        palette.setColor(QPalette.Base, QColor("#161b23"))
        palette.setColor(QPalette.Text, QColor("#e8edf4"))
        self.setPalette(palette)
        self.setStyleSheet("""
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
            QComboBox#sessionPicker {
                min-height: 28px;
                max-height: 28px;
                padding: 0px 30px 0px 12px;
                border-radius: 14px;
                border: 1px solid rgba(130, 150, 178, 0.28);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(42, 52, 67, 0.98),
                    stop:1 rgba(23, 29, 39, 0.98));
                color: #eef4fb;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox#sessionPicker:hover {
                border-color: rgba(121, 199, 255, 0.42);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(47, 59, 76, 0.99),
                    stop:1 rgba(25, 32, 43, 0.99));
            }
            QComboBox#sessionPicker:disabled {
                color: #8390a2;
                border-color: rgba(130, 150, 178, 0.16);
                background: rgba(24, 30, 39, 0.88);
            }
            QComboBox#sessionPicker::drop-down {
                border: none;
                width: 26px;
            }
            QComboBox#sessionPicker QAbstractItemView {
                background: rgba(21, 27, 37, 0.99);
                color: #eef4fb;
                border: 1px solid rgba(130, 150, 178, 0.20);
                selection-background-color: #243447;
                border-radius: 12px;
                padding: 6px;
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
                border: 1px solid rgba(255, 255, 255, 0.08);
                background: rgba(22, 28, 38, 0.65);
            }
            QFrame#userBubble {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 rgba(99, 102, 241, 0.2), stop: 1 rgba(79, 70, 229, 0.3));
                border-color: rgba(99, 102, 241, 0.4);
            }
            QFrame#thinkingIndicator {
                border: none;
                background: transparent;
            }
            QFrame#thinkingBubble {
                border-radius: 14px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                background: rgba(22, 28, 38, 0.65);
            }
            QFrame#userBubble QLabel#messageRole,
            QFrame#userBubble QLabel#userMessageText {
                color: #ffffff;
            }
            QLabel#messageRole {
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.08em;
                color: #9bb0c6;
            }
            QLabel#messageTimestamp {
                color: rgba(255, 255, 255, 0.42);
                font-size: 10px;
                margin-top: 2px;
            }
            QLabel#thinkingDots {
                color: #9bb0c6;
                font-size: 16px;
                font-weight: 700;
                letter-spacing: 0.18em;
            }
            QWidget#trafficHost {
                background: transparent;
                border: none;
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
            QLabel#metricChip, QPushButton#metricChip {
                padding: 0px;
                border: none;
                background: transparent;
                color: #7c8fa6;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton#metricChip {
                text-align: left;
            }
            QPushButton#metricChip[kind="tools"], QPushButton#metricChip[kind="files"] {
                color: #8fa9c8;
            }
            QPushButton#metricChip[kind="tools"]:hover, QPushButton#metricChip[kind="files"]:hover {
                color: #d3e5fa;
                text-decoration: underline;
            }
            QLabel#metricSeparator {
                padding: 0px;
                border: none;
                background: transparent;
                color: rgba(140, 160, 186, 0.32);
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
            QScrollArea#mermaidPreviewScroll {
                background: rgba(16, 22, 31, 0.92);
                border: 1px solid rgba(166, 187, 214, 0.10);
                border-radius: 10px;
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
            QLabel#mermaidPreviewImage {
                background: transparent;
            }
            QLabel#mediaTransportMeta {
                color: #9fb0c4;
                font-size: 10px;
                font-weight: 600;
                min-width: 66px;
            }
            QPushButton#mediaImageButton {
                padding: 0px;
                border-radius: 8px;
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
            """)


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


def _env_truthy(name: str) -> bool:
    value = str(os.getenv(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _tray_diagnostics_enabled() -> bool:
    return _env_truthy("ABSTRACTASSISTANT_TRAY_DIAGNOSTICS") or bool(
        getattr(sys, "frozen", False)
    )


def _tray_diagnostics_log_path() -> Optional[Path]:
    raw = str(os.getenv("ABSTRACTASSISTANT_TRAY_LOG_PATH") or "").strip()
    if raw:
        try:
            return Path(raw).expanduser()
        except Exception:
            return None
    if not _tray_diagnostics_enabled():
        return None
    return (
        Path.home()
        / "Library"
        / "Logs"
        / "Assistant"
        / "abstractassistant-launcher.log"
    )


def _bundle_tray_log(message: str) -> None:
    if not _tray_diagnostics_enabled():
        return
    text = f"[assistant-tray] {message}"
    try:
        print(text, flush=True)
    except Exception:
        pass
    path = _tray_diagnostics_log_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{text}\n")
    except Exception:
        pass


def _native_tray_capture_path() -> Optional[Path]:
    raw = str(os.getenv("ABSTRACTASSISTANT_TRAY_CAPTURE_PATH") or "").strip()
    if not raw:
        if not _tray_diagnostics_enabled():
            return None
        return (
            Path.home()
            / "Library"
            / "Logs"
            / "Assistant"
            / "abstractassistant-status-item.png"
        )
    try:
        return Path(raw).expanduser()
    except Exception:
        return None


def _capture_native_status_item_button_png(*, reason: str = "") -> bool:
    capture_path = _native_tray_capture_path()
    if capture_path is None or sys.platform != "darwin" or AppKit is None:
        return False
    try:
        items = AppKit.NSStatusBar.systemStatusBar().valueForKey_("statusItems")
        if items is None or int(items.count()) <= 0:
            return False
        objects = items.allObjects()
        if not objects:
            return False
        item = objects[0]
        button = item.button() if item is not None else None
        if button is None:
            return False
        bounds = button.bounds()
        if int(round(bounds.size.width)) <= 0 or int(round(bounds.size.height)) <= 0:
            return False
        bitmap = button.bitmapImageRepForCachingDisplayInRect_(bounds)
        if bitmap is None:
            return False
        button.cacheDisplayInRect_toBitmapImageRep_(bounds, bitmap)
        data = bitmap.representationUsingType_properties_(AppKit.NSPNGFileType, None)
        if data is None:
            return False
        capture_path.parent.mkdir(parents=True, exist_ok=True)
        capture_path.write_bytes(bytes(data))
        _bundle_tray_log(
            f"{reason or 'capture'}: wrote native tray button render to {capture_path}"
        )
        return True
    except Exception as exc:
        _bundle_tray_log(
            f"{reason or 'capture'}: native tray button capture failed: {exc}"
        )
        return False


def _native_status_item_metrics() -> tuple[int, tuple[int, int], tuple[int, int]]:
    if sys.platform != "darwin" or AppKit is None:
        return -1, (0, 0), (0, 0)
    try:
        items = AppKit.NSStatusBar.systemStatusBar().valueForKey_("statusItems")
        if items is None:
            return 0, (0, 0), (0, 0)
        count = int(items.count())
        button_size = (0, 0)
        image_size = (0, 0)
        objects = items.allObjects()
        if count > 0 and objects:
            item = objects[0]
            button = item.button() if item is not None else None
            if button is not None:
                frame = button.frame()
                button_size = (
                    int(round(frame.size.width)),
                    int(round(frame.size.height)),
                )
                image = button.image()
                if image is not None:
                    size = image.size()
                    image_size = (int(round(size.width)), int(round(size.height)))
        return count, button_size, image_size
    except Exception:
        return -1, (0, 0), (0, 0)


def _refresh_tray_visibility(
    *, tray: QSystemTrayIcon, palette, reason: str = ""
) -> TrayVisibilityState:
    try:
        available = bool(QSystemTrayIcon.isSystemTrayAvailable())
    except Exception:
        available = True
    if not available:
        _bundle_tray_log(f"{reason or 'refresh'}: system tray unavailable")
        native_item_count, native_button_size, native_image_size = (
            _native_status_item_metrics()
        )
        return TrayVisibilityState(
            available=False,
            qt_visible=False,
            native_item_count=native_item_count,
            native_button_size=native_button_size,
            native_image_size=native_image_size,
        )
    try:
        tray.show()
    except Exception as exc:
        _bundle_tray_log(f"{reason or 'refresh'}: tray.show failed: {exc}")
    try:
        tray.setVisible(True)
    except Exception:
        pass
    try:
        palette.attach_tray(tray)
    except Exception as exc:
        _bundle_tray_log(f"{reason or 'refresh'}: attach_tray failed: {exc}")
    try:
        palette._refresh_tray_feedback()
    except Exception as exc:
        _bundle_tray_log(f"{reason or 'refresh'}: tray feedback refresh failed: {exc}")
    try:
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
    except Exception:
        pass
    try:
        visible = bool(tray.isVisible())
    except Exception:
        visible = True
    native_item_count, native_button_size, native_image_size = (
        _native_status_item_metrics()
    )
    state = TrayVisibilityState(
        available=True,
        qt_visible=visible,
        native_item_count=native_item_count,
        native_button_size=native_button_size,
        native_image_size=native_image_size,
    )
    _bundle_tray_log(
        f"{reason or 'refresh'}: tray visible={state.qt_visible} "
        f"native_items={state.native_item_count} "
        f"button={state.native_button_size[0]}x{state.native_button_size[1]} "
        f"image={state.native_image_size[0]}x{state.native_image_size[1]} "
        f"ready={state.ready}"
    )
    if state.ready:
        _capture_native_status_item_button_png(reason=reason or "refresh")
    return state


def _schedule_tray_visibility_refresh(
    *,
    tray: QSystemTrayIcon,
    palette,
    delays_ms: tuple[int, ...] = _TRAY_VISIBILITY_RETRY_DELAYS_MS,
) -> None:
    for delay in tuple(delays_ms or ()):
        QTimer.singleShot(
            max(0, int(delay)),
            lambda d=int(delay): _refresh_tray_visibility(
                tray=tray, palette=palette, reason=f"retry@{d}ms"
            ),
        )


def _macos_tray_context_fallback(*, host_menu: QMenu, palette) -> None:
    try:
        host_menu.hide()
    except Exception:
        pass
    now = time.monotonic()
    last_activation = float(getattr(palette, "_tray_last_activation_ts", 0.0) or 0.0)
    if last_activation > 0.0 and (now - last_activation) <= 0.20:
        return
    try:
        palette.show_palette()
    except Exception:
        pass


def _configure_tray_host(*, tray: QSystemTrayIcon, palette, menu: QMenu) -> None:
    if sys.platform != "darwin":
        try:
            tray.setContextMenu(menu)
        except Exception:
            pass
        return
    host_menu = QMenu()
    try:
        host_menu.aboutToShow.connect(
            lambda: _macos_tray_context_fallback(host_menu=host_menu, palette=palette)
        )
    except Exception:
        pass
    try:
        tray.setContextMenu(host_menu)
    except Exception:
        pass
    try:
        palette._tray_host_menu = host_menu
    except Exception:
        pass


def _schedule_initial_palette_show(
    *,
    tray: QSystemTrayIcon,
    palette,
    delays_ms: tuple[int, ...] = _TRAY_VISIBILITY_RETRY_DELAYS_MS,
) -> None:
    shown = {"done": False}
    delays = tuple(delays_ms or ())

    def _maybe_show(*, reason: str) -> None:
        if shown["done"]:
            return
        state = _refresh_tray_visibility(tray=tray, palette=palette, reason=reason)
        if not state.ready:
            return
        shown["done"] = True
        palette.show_palette()

    for delay in delays:
        QTimer.singleShot(
            max(0, int(delay)),
            lambda d=int(delay): _maybe_show(reason=f"visible-launch@{d}ms"),
        )

    fallback_delay = max(delays or (0,)) + 500

    def _fallback_show() -> None:
        if shown["done"]:
            return
        shown["done"] = True
        try:
            palette._set_banner(
                "Menu bar icon is still initializing. Keep this window open while the app finishes attaching.",
                tone="warn",
            )
        except Exception:
            pass
        palette.show_palette()

    QTimer.singleShot(max(0, int(fallback_delay)), _fallback_show)


def launch_tray_app(
    *,
    config: Optional[Config] = None,
    debug: bool = False,
    data_dir: Optional[Path] = None,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("AbstractAssistant")
    app.setWindowIcon(_qt_icon())
    show_on_launch = _env_truthy("ABSTRACTASSISTANT_SHOW_ON_LAUNCH")

    controller = AssistantV2Controller(config=config, data_dir=data_dir, debug=debug)
    palette = AssistantPalette(controller=controller, debug=debug)
    # Clean up the worker/hotkey/voice on quit so quitting mid-run cannot tear
    # down a live QThread (crash-on-exit class).
    try:
        app.aboutToQuit.connect(palette.shutdown)
    except Exception:
        pass

    tray = QSystemTrayIcon(_qt_icon(), app)
    app._assistant_tray = tray  # type: ignore[attr-defined]
    tray.setToolTip("AbstractAssistant")
    menu = QMenu()
    menu.addAction("Show", palette.show_palette)
    menu.addAction("Hide", palette.hide)
    menu.addAction("New Session", palette._create_session)
    menu.addAction("Settings", palette._open_settings)
    menu.addSeparator()
    menu.addAction("Quit", app.quit)
    palette._tray_menu = menu
    _configure_tray_host(tray=tray, palette=palette, menu=menu)

    def _on_tray_activated(reason) -> None:
        try:
            palette._tray_last_activation_ts = time.monotonic()
        except Exception:
            pass
        _handle_tray_activation(palette=palette, menu=menu, reason=reason)

    tray.activated.connect(_on_tray_activated)
    _refresh_tray_visibility(tray=tray, palette=palette, reason="startup")
    _schedule_tray_visibility_refresh(tray=tray, palette=palette)
    if show_on_launch:
        try:
            app.applicationStateChanged.connect(  # type: ignore[attr-defined]
                lambda state: (
                    _refresh_tray_visibility(
                        tray=tray, palette=palette, reason="app-active"
                    )
                    if state == Qt.ApplicationActive
                    else None
                )
            )
        except Exception:
            pass
    if show_on_launch:
        _schedule_initial_palette_show(tray=tray, palette=palette)
    else:
        palette.hide()
    return app.exec_()
