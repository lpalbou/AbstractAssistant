"""Qt tray shell for AbstractAssistant (gateway-native palette)."""

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
    QByteArray,
    QEvent,
    QPoint,
    QPointF,
    QRect,
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
    QImageReader,
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
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
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
    QRadioButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QToolTip,
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
from abstractassistant.core.speech_text import speech_plain_text
from abstractassistant.core.file_activity import (
    FileOperation,
    distinct_file_count,
    file_operations_from_tool_calls,
)
from abstractassistant.core.tool_display import (
    compact_tool_call_label,
    compact_tool_call_label_html,
)
from abstractassistant.gateway.run_stats import parse_iso_ms, parse_usage_summary
from abstractassistant.icons import retint_widget_icons, symbol_icon as _symbol_icon
from abstractassistant.gateway.tool_usage import (
    extract_tool_call_details_from_scratchpad,
)
from abstractassistant.utils.icon_generator import IconGenerator
from abstractassistant.utils.markdown_renderer import (
    MarkdownRenderer,
    split_markdown_mermaid_blocks,
)

from .controller import AssistantController
from .gateway_service import ROUTE_SPECS, CapabilityRouteRow
from .hotkey import GlobalHotkeyManager
from .preferences import AssistantPreferences, normalize_ui_theme
from .core.voice_conversation import (
    VOICE_CONVERSATION_SYSTEM_PROMPT,
    VoiceConversation,
)
from .core import tool_presenter as _presenter
from .core.link_targets import (
    click_action,
    describe_link,
    file_href,
    local_path_from_href,
    mentioned_local_files,
    path_kind,
)
from .ui.activity import RunActivityCard, RunActivityModel, build_activity_qss
from .gateway.live_deltas import (
    ASSISTANT_DELTA,
    ASSISTANT_DELTA_END,
    ASSISTANT_DELTA_RESET,
    subagent_caption,
    TRUNCATED_NOTE as LIVE_TRUNCATED_NOTE,
    LiveReply,
    end_reason_text,
)
from .ui.session_switcher import SessionSwitcher
from .core.automations import NotificationLedger, discussion_banner, target_from_workflow
from .ui.automations import (
    AUTOMATIONS_POLL_HIDDEN_MS,
    AUTOMATIONS_POLL_VISIBLE_MS,
    AutomationsHub,
    AutomationView,
    ScheduleSheet,
)
from .theme import DEFAULT_THEME, THEME, activate_metrics
from .retint import parse_color, retint_stylesheet
from .ui.approval import (
    build_approval_qss,
    ToolApprovalCallCard as _ToolApprovalCallCard,
    ToolApprovalSheet,
    ToolCallCard,
)
from .ui.dialogs import AskUserDialog
from .ui.settings import SettingsDialog, ToolSettingsDialog
from .ui.styles import chat_stylesheet, dialog_stylesheet, scope_stylesheet
from .ui.voice_strip import VOICE_STRIP_HEIGHT, VoiceStrip

_HTML_ACTION_FENCE_RE = re.compile(
    r"```(?:html|x-html|xml)[^\n]*\n(.*?)```", flags=re.I | re.S
)
_TRAY_BUSY_FRAME_COUNT = 36
_TRAY_BUSY_FRAME_INTERVAL_MS = 60
_TRAY_FEEDBACK_ICON_SIZE = 44
# Live voice meter in the tray while the assistant speaks.
_TRAY_VOICE_BAR_COUNT = 5
# ~15 fps on macOS, where updating the status item is a local call. Elsewhere
# every frame costs a platform round trip — an HICON rebuild plus a shell IPC
# call on Windows, a D-Bus republish of the whole pixmap on Linux — so the
# animation is slowed rather than shipped as a background load.
_TRAY_VOICE_FRAME_INTERVAL_MS = 66 if sys.platform == "darwin" else 200
_TRAY_VOICE_DECAY_S = 0.35
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
        # `native_item_count < 0` means AppKit could not be asked at all (pyobjc
        # missing). Falling back to Qt's own answer keeps a pip install usable
        # instead of reporting "never ready" forever.
        if sys.platform == "darwin" and self.native_item_count >= 0:
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


# Tool-call presentation helpers live in core/tool_presenter.py (shared with
# the approval sheet); the private names stay as aliases for callers/tests.
ToolCallSummary = _presenter.ToolCallSummary
_tool_calls_text = _presenter.tool_calls_text
_tool_call_arguments = _presenter.tool_call_arguments
_tool_call_value_summary = _presenter.tool_call_value_summary
_tool_call_reason = _presenter.tool_call_reason
_tool_call_summary = _presenter.tool_call_summary


def _assistant_html(renderer: MarkdownRenderer, content: str) -> str:
    base = renderer.render(content)
    # `!important` beats the renderer's own stylesheet, so this block decides
    # the reply's colours — it has to be translated to the active theme too, or
    # a light theme renders light text on a light card.
    themed_override = _typographic(_themed("""
    <style>
    .markdown-content,
    .markdown-content p,
    .markdown-content li,
    .markdown-content strong,
    .markdown-content em,
    .markdown-content blockquote,
    .markdown-content td,
    .markdown-content th {
        color: #edf2f8 !important;
        font-size: @@SIZE@@px !important;
        line-height: @@LINE@@ !important;
    }
    /* Compressed heading scale for a chat column: headings differ from body
       by weight AND a modest size step, instead of all collapsing to 13px. */
    .markdown-content h1 { color: #f8fafc !important; font-size: @@H1@@px !important; font-weight: 700 !important; margin: 12px 0 6px 0 !important; line-height: 1.3 !important; border: none !important; }
    .markdown-content h2 { color: #f8fafc !important; font-size: @@H2@@px !important; font-weight: 700 !important; margin: 12px 0 6px 0 !important; line-height: 1.3 !important; border: none !important; }
    .markdown-content h3 { color: #edf2f8 !important; font-size: @@H3@@px !important; font-weight: 600 !important; margin: 10px 0 4px 0 !important; line-height: 1.3 !important; }
    .markdown-content h4,
    .markdown-content h5,
    .markdown-content h6 { color: #edf2f8 !important; font-size: @@SIZE@@px !important; font-weight: 600 !important; margin: 8px 0 4px 0 !important; line-height: 1.3 !important; }
    .markdown-content p {
        margin: 0 0 @@PARA@@px 0 !important;
    }
    .markdown-content ul,
    .markdown-content ol {
        margin: 0 0 @@PARA@@px 0 !important;
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
        margin-bottom: @@BULLET@@px !important;
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
    """))
    # A deliverable path is a link, not a code sample. Removing only this
    # renderer-owned wrapper avoids a long highlighted slab across the reply;
    # the complete selectable path and the link target remain intact.
    base = re.sub(r'<code>(<a class="aa-file"\s[^>]*>[^<]*</a>)</code>', r'\1', base)
    return themed_override + base


def _user_html(content: str) -> str:
    import html

    escaped = html.escape(content.strip())
    # The user bubble is a tinted surface, so its text follows the palette's
    # strongest text colour — hard-coding white made it unreadable the moment
    # the tint was light.
    themed_override = (
        "<style>"
        ".user-content {"
        f"  color: {THEME.text_strong} !important;"
        f"  font-size: {TYPOGRAPHY.size}px !important;"
        f"  line-height: {TYPOGRAPHY.line} !important;"
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


def _session_button_text(title: Any, *, limit: int = 26) -> str:
    """The header control's label: the SESSION's topic, short enough for the bar.

    The control names the session you are in, so it falls back to "Untitled
    session" and never to "New …" — every session on disk is stored with the
    placeholder title "New session", which made the header claim every one of
    them was new.
    """
    text = " ".join(str(title or "").replace("\r", " ").replace("\n", " ").split()).strip()
    if not text or text.lower() in {"new session", "new chat"}:
        return "Untitled session"
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)].rstrip()}…"


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


def _reveal_in_file_manager(path: str) -> bool:
    """Select `path` in Finder (macOS) or open its folder elsewhere. Never runs it."""
    target = str(path or "").strip()
    if not target:
        return False
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["/usr/bin/open", "-R", target])
            return True
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", f"/select,{target}"])
            return True
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(target) or target)))
    except Exception:
        return False


def activate_message_link(href: str, *, force_reveal: bool = False) -> str:
    """Act on a link the user clicked in a message. Returns "" or why nothing opened.

    The link text was written by a model, so this is the ONE place that decides
    what a click may do (policy: `core/link_targets.py`). Web links go to the
    browser. A local path is resolved through its symlinks first — `clip.mp4`
    pointing at an app bundle must be judged as the app — then opened only when
    its kind is inert to open; anything else is shown in Finder instead of run.
    """
    text = str(href or "").strip()
    if not text:
        return "Empty link."
    if text.startswith(("/", "~/")):
        # `[clip](/Users/…)` — markdown emits the path as a scheme-less href.
        text = file_href(text) or text
    scheme = str(urlparse(text).scheme or "").strip().lower()
    if scheme in {"http", "https", "mailto"}:
        try:
            opened = bool(QDesktopServices.openUrl(QUrl.fromEncoded(text.encode("utf-8"))))
        except Exception:
            opened = False
        return "" if opened else "Could not open this link."
    if scheme != "file":
        return f"“{scheme or 'This'}” links are not opened from a message."

    local = local_path_from_href(text)
    if local is None:
        return "This link points at another computer, so it was not opened."
    try:
        real = os.path.realpath(local)
        if not os.path.exists(real):
            return f"Not found: {local}"
        is_dir = os.path.isdir(real)
    except (OSError, ValueError) as exc:
        # ValueError: an embedded NUL. Nothing may escape this function — it runs
        # inside a Qt slot, where an uncaught exception aborts the whole app.
        return f"Could not reach {local}: {exc}"

    # A folder WITH an extension is a bundle (.app, .workflow, .pkg…): opening it
    # launches it. Plain folders open in Finder; bundles are only ever revealed.
    is_plain_folder = is_dir and not os.path.splitext(os.path.basename(real))[1]
    may_open = is_plain_folder or (not is_dir and click_action(real) == "open")
    if force_reveal or not may_open:
        return "" if _reveal_in_file_manager(real) else f"Could not show {local} in Finder."
    if not is_dir and path_kind(real) == "text" and sys.platform == "darwin":
        # Text and SOURCE files go to the text editor, never to their default app:
        # where python.org's Python Launcher is installed, "opening" a .py RUNS it.
        try:
            subprocess.Popen(["/usr/bin/open", "-t", real])
            return ""
        except Exception:
            return f"Could not open {local}."
    try:
        opened = bool(QDesktopServices.openUrl(QUrl.fromLocalFile(real)))
    except Exception:
        opened = False
    return "" if opened else f"Could not open {local}."


def _open_external_href(href: str) -> bool:
    text = str(href or "").strip()
    if not _assistant_action_href_allowed(text):
        return False
    scheme = str(urlparse(text).scheme or "").strip().lower()
    if scheme in {"http", "https", "mailto", "file"}:
        # Same policy as an inline link: an action button must not be a way to
        # run something an inline link would only have revealed.
        return activate_message_link(text) == ""
    try:
        return bool(QDesktopServices.openUrl(QUrl.fromEncoded(text.encode("utf-8"))))
    except Exception:
        return False


def _asset_path(name: str) -> Optional[Path]:
    """Resolve a bundled asset both in-repo (editable) and frozen (PyInstaller)."""
    frozen_base = getattr(sys, "_MEIPASS", None)
    candidates = []
    if frozen_base:
        candidates.append(Path(frozen_base) / "abstractassistant" / "assets" / name)
    candidates.append(Path(__file__).resolve().parent / "assets" / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None




@dataclass(frozen=True)
class Typography:
    """How the transcript reads: size, line height, and the gaps between blocks."""

    size: int = 13
    line: float = 1.20
    paragraph: int = 3
    bullet: int = 3

    @classmethod
    def from_preferences(cls, prefs: Any) -> "Typography":
        return cls(
            size=int(getattr(prefs, "text_size", 13) or 13),
            line=float(getattr(prefs, "line_spacing", 1.20) or 1.20),
            paragraph=int(getattr(prefs, "paragraph_spacing", 3)),
            bullet=int(getattr(prefs, "bullet_spacing", 3)),
        )

    @property
    def heading_1(self) -> int:
        return self.size + 4

    @property
    def heading_2(self) -> int:
        return self.size + 2

    @property
    def heading_3(self) -> int:
        return self.size + 1


#: The rhythm the transcript is rendered with. Replaced when the user changes
#: it in Settings, so every message rebuilt afterwards uses the new one.
TYPOGRAPHY = Typography()


def _typographic(css: str) -> str:
    """Fill the reading-rhythm placeholders from the active typography.

    Placeholders rather than an f-string: the block is 150 lines of CSS full of
    braces, and doubling every one of them to make it a format string is a
    large edit with nothing to gain.
    """
    t = TYPOGRAPHY
    for token, value in (
        ("@@SIZE@@", t.size),
        ("@@LINE@@", t.line),
        ("@@PARA@@", t.paragraph),
        ("@@BULLET@@", t.bullet),
        ("@@H1@@", t.heading_1),
        ("@@H2@@", t.heading_2),
        ("@@H3@@", t.heading_3),
    ):
        css = css.replace(token, str(value))
    return css


def _themed(qss: str) -> str:
    """A stylesheet written against the app's own palette, in the active theme.

    Most of the chrome below is colour literals rather than tokens; translating
    them is what lets a theme reach every window without rewriting 22k
    characters of stylesheet by hand. See `ui/retint.py`.
    """
    return retint_stylesheet(qss, source=DEFAULT_THEME, target=THEME)


def _solid(color: str) -> str:
    """A QPalette-safe opaque colour: `QColor` cannot parse an `rgba()` string."""
    parsed = parse_color(color)
    if parsed is None:
        return color
    (r, g, b), _alpha = parsed
    return "#%02x%02x%02x" % (r, g, b)


def _qt_icon() -> QIcon:
    # Prefer the designed app icon (transparent rounded-square art); fall back
    # to the procedural icon only if the asset is missing.
    asset = _asset_path("app_icon.png")
    if asset is not None:
        icon = QIcon(str(asset))
        if not icon.isNull():
            return icon
    generator = IconGenerator(size=44)
    image = generator.create_app_icon(color_scheme="green", animated=False)
    path = Path.home() / ".abstractassistant" / "tray_icon.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    pixmap = QPixmap(str(path))
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


_TRAY_ICON_CACHE: Dict[tuple[str, int, int], QIcon] = {}


def _fit_window_rect(
    *, x: int, y: int, width: int, height: int, area: Any, gap: int
) -> tuple[int, int, int, int]:
    """The window rect (frame, title bar included) moved and, if needed,
    shrunk so it lies inside ``area`` minus ``gap`` on every side.

    ``area`` is a screen's available geometry (menu bar and Dock excluded);
    anything with ``x()/y()/width()/height()`` works. Pure arithmetic, so the
    rule is testable without a screen.
    """
    ax, ay = int(area.x()), int(area.y())
    aw, ah = int(area.width()), int(area.height())
    gap = max(0, min(int(gap), aw // 2, ah // 2))
    width = max(1, min(int(width), aw - 2 * gap))
    height = max(1, min(int(height), ah - 2 * gap))
    x = max(ax + gap, min(int(x), ax + aw - gap - width))
    y = max(ay + gap, min(int(y), ay + ah - gap - height))
    return x, y, width, height


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


def _tray_voice_bars(levels: Any, *, count: int = _TRAY_VOICE_BAR_COUNT) -> List[float]:
    """Normalize a meter — a level, or per-band levels — into ``count`` bars.

    The gateway's meter is whatever the player produced for the chunk being
    heard, so its length varies; the icon needs a fixed number of bars.
    """
    if isinstance(levels, (list, tuple)):
        values = []
        for value in levels:
            try:
                values.append(max(0.0, min(1.0, float(value))))
            except (TypeError, ValueError):
                values.append(0.0)
    else:
        try:
            values = [max(0.0, min(1.0, float(levels or 0.0)))]
        except (TypeError, ValueError):
            values = [0.0]
    if not values:
        return [0.0] * count
    if len(values) == count:
        return values
    if len(values) == 1:
        # One level: shape it into a symmetric burst so the icon reads as a
        # voice rather than a row of identical blocks.
        peak = values[0]
        shape = (0.45, 0.78, 1.0, 0.78, 0.45)
        return [peak * shape[i % len(shape)] for i in range(count)]
    # Resample by averaging each source window into its target bar.
    out: List[float] = []
    for index in range(count):
        start = int(index * len(values) / count)
        end = max(start + 1, int((index + 1) * len(values) / count))
        window = values[start:end] or [values[min(start, len(values) - 1)]]
        out.append(sum(window) / len(window))
    return out


def _tray_feedback_icon(
    *,
    state: str = "idle",
    frame: int = 0,
    size: int = _TRAY_FEEDBACK_ICON_SIZE,
    levels: Any = None,
) -> QIcon:
    normalized_state = str(state or "idle").strip().lower() or "idle"
    normalized_frame = int(frame or 0) % _TRAY_BUSY_FRAME_COUNT
    bars = _tray_voice_bars(levels) if normalized_state == "speaking" else []
    # A live meter is a new picture every frame: caching it would grow without
    # bound and still miss, so the speaking state renders straight through.
    key = (normalized_state, normalized_frame, int(size))
    if normalized_state != "speaking":
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

    if normalized_state == "speaking":
        # The assistant's own voice, live: bar heights are the audio the player
        # is putting on the speakers right now.
        peak = max(bars) if bars else 0.0
        _state_disc(
            inner=QColor("#e6d9ff"),
            mid=QColor("#a074ff"),
            edge=QColor("#5326b8"),
            ring=QColor("#d9c6ff"),
            ring_alpha=int(126 + (40 * peak)),
            glow=QColor("#a97cff"),
            glow_alpha=int(26 + (26 * peak)),
        )
        span = size * 0.50
        bar_width = span / ((len(bars) * 1.8) or 1.0)
        gap = (span - (bar_width * len(bars))) / max(1, len(bars) - 1)
        left = center.x() - (span / 2.0)
        painter.setPen(Qt.NoPen)
        for index, value in enumerate(bars):
            # Every bar keeps a floor so silence still reads as "speaking",
            # never as an empty icon.
            height = size * (0.075 + (0.30 * value))
            rect = QRectF(
                left + (index * (bar_width + gap)),
                center.y() - (height / 2.0),
                bar_width,
                height,
            )
            painter.setBrush(QColor(255, 255, 255, int(206 + (49 * value))))
            painter.drawRoundedRect(rect, bar_width / 2.0, bar_width / 2.0)
    elif normalized_state == "busy":
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
    elif normalized_state == "waiting":
        # Deliberately still: "busy" animates, and a badge that spins reads as
        # progress. This one means the run has STOPPED and needs the user.
        amber = QColor("#e0af68")
        _state_disc(
            inner=QColor("#ffe9c4"),
            mid=amber,
            edge=QColor("#8a5a12"),
            ring=QColor("#ffd79a"),
            ring_alpha=150,
            glow=QColor("#f0bf7a"),
            glow_alpha=34,
        )
        pen = QPen(QColor("#3a2400"))
        pen.setWidthF(size * 0.085)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(
            QPointF(center.x(), center.y() - size * 0.155),
            QPointF(center.x(), center.y() + size * 0.045),
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#3a2400"))
        painter.drawEllipse(QPointF(center.x(), center.y() + size * 0.145), size * 0.049, size * 0.049)
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
    if normalized_state != "speaking":
        _TRAY_ICON_CACHE[key] = icon
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


# Shared with the run-stats fold: identical key preference order and
# zero-usage filtering (previously duplicated here).
_parse_usage_summary = parse_usage_summary
_parse_iso_ms = parse_iso_ms


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
    # Assistant replies get the wider column (long content, stable reflow);
    # user messages are capped narrower and right-aligned so a short prompt
    # doesn't render as a full-width slab.
    fraction = 0.72 if str(role or "").strip().lower() == "user" else 0.86
    return max(96, int(width * fraction))


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


def _human_file_size(size_bytes: int) -> str:
    size = float(max(0, int(size_bytes)))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


def _mentioned_file_caption(path: str) -> str:
    """"Video · 3.4 MB" — what kind of thing the chip is, and how big."""
    from .core.link_targets import path_kind

    noun = {
        "image": "Image",
        "video": "Video",
        "audio": "Audio",
        "document": "Document",
        "text": "Text",
    }.get(path_kind(path), "File")
    try:
        return f"{noun} · {_human_file_size(os.path.getsize(path))}"
    except OSError:
        return noun


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

# What a message the USER sent shows for its files: the picture itself, kept
# small (a 260px gallery tile is right for media the assistant MADE and wrong
# for an input), clickable for the full-size preview. Files with no picture to
# show fall back to a shorter icon + name pill.
_ATTACHMENT_THUMB_HEIGHT = 56
_ATTACHMENT_THUMB_MAX_WIDTH = 132
_ATTACHMENT_CHIP_GLYPH = 20
_ATTACHMENT_CHIP_MAX_TEXT = 168
# A file the ANSWER points at is identified by its name — there is no sentence of
# the user's own to say which file it was — so its chip shows far more of it.
_MENTION_CHIP_MAX_TEXT = 340


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


def _rounded_thumbnail(
    pixmap: QPixmap, *, height: int, max_width: int, radius: int = 6
) -> QPixmap:
    """Small, corner-rounded thumbnail of ``pixmap``, rendered at 2x for retina.

    The aspect ratio is kept — a screenshot has to still look like that
    screenshot at 56px, which a square crop of its middle does not.
    """
    target = _image_thumbnail_size(pixmap.size(), height=height, max_width=max_width)
    span = QSize(target.width() * 2, target.height() * 2)
    canvas = QPixmap(span)
    canvas.fill(QColor(0, 0, 0, 0))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    try:
        clip = QPainterPath()
        clip.addRoundedRect(
            QRectF(0, 0, span.width(), span.height()), radius * 2, radius * 2
        )
        painter.setClipPath(clip)
        painter.drawPixmap(
            QRect(0, 0, span.width(), span.height()),
            pixmap.scaled(span, Qt.KeepAspectRatio, Qt.SmoothTransformation),
        )
    finally:
        painter.end()
    canvas.setDevicePixelRatio(2.0)
    return canvas


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


def _cache_tooltip_lines(cache: Dict[str, Any], llm_calls: Optional[int]) -> List[str]:
    cached = int(cache.get("cached_tokens") or 0)
    new = int(cache.get("new_tokens") or 0)
    measured = int(cache.get("measured_calls") or 0)
    coverage = f"{measured} of {llm_calls}" if llm_calls is not None else str(measured)
    return [
        f"Measured cache usage · {coverage} model calls",
        f"Reused from cache: {_format_metric_count(cached)} tokens",
        f"Newly processed: {_format_metric_count(new)} tokens",
        "Summed across the turn, including ReAct calls. Repeated context counts on each call.",
        "Newly processed includes uncached history and tool results, not just your new message.",
        "Measured counts can differ from the model’s reported input total.",
    ]


def _tokens_in_tooltip(usage: Dict[str, int], llm_calls: Optional[int], cache=None) -> str:
    lines = [
        "Reported input tokens across this turn.",
        f"Total: {_format_metric_count(usage['input_tokens'])} tokens",
    ]
    if llm_calls is not None and llm_calls > 0:
        plural = "s" if int(llm_calls) != 1 else ""
        lines.append(f"LLM calls: {_format_metric_count(llm_calls)} call{plural}")
    if isinstance(cache, dict) and cache.get("measured_calls"):
        lines.extend(_cache_tooltip_lines(cache, llm_calls))
    else:
        lines.append("Cache reuse was not reported; it is not assumed to be zero.")
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
    prompt_cache = None

    if isinstance(metadata, dict):
        usage = _parse_usage_summary(metadata.get("usage"))
        stats_meta = metadata.get("_assistant_stats")
        if isinstance(stats_meta, dict):
            prompt_cache = stats_meta.get("prompt_cache")
            usage = _parse_usage_summary(
                stats_meta.get("usage")
                if isinstance(stats_meta.get("usage"), dict)
                else stats_meta.get("tokens")
            ) or usage
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
        split_known = bool(usage["input_tokens"] or usage["output_tokens"])
        if not split_known and usage["total_tokens"]:
            # The split is genuinely unavailable: some servers report usage in
            # the Responses dialect (`input_tokens`/`output_tokens`) which the
            # provider layer normalizes by reading Chat-Completions names only,
            # so the halves arrive as 0 while the total survives. Printing
            # "input : 0 tk" is a CLAIM, and a false one — show the number we
            # actually have. See docs/backlog/proposed/0011.
            total_label = f"total : {_format_metric_count(usage['total_tokens'])} tk"
            metrics.append(
                {
                    "kind": "tokens_total",
                    "label": total_label,
                    "plain": total_label,
                    "tooltip": (
                        "Total tokens for this answer. This provider did not report "
                        "the input/output split."
                    ),
                    "clickable": False,
                }
            )
        else:
            metrics.append(
                {
                    "kind": "tokens_in",
                    "label": f"input : {_format_metric_count(usage['input_tokens'])} tk",
                    "plain": f"input : {_format_metric_count(usage['input_tokens'])} tk",
                    "tooltip": _tokens_in_tooltip(usage, llm_calls, prompt_cache),
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
    if isinstance(prompt_cache, dict) and prompt_cache.get("measured_calls"):
        cached = int(prompt_cache.get("cached_tokens") or 0)
        processed = cached + int(prompt_cache.get("new_tokens") or 0)
        complete = llm_calls is not None and int(prompt_cache["measured_calls"]) == llm_calls
        label = "Cache: partial"
        if complete:
            label = f"{cached / processed:.0%} reused" if processed else "Cache: no input"
        metrics.insert(1 if usage is not None else 0, {
            "kind": "cache", "label": label, "plain": label,
            "tooltip": _tooltip_html(_cache_tooltip_lines(prompt_cache, llm_calls)),
            "clickable": False,
        })
    return metrics


def _assistant_footer_items(message: Dict[str, Any]) -> List[str]:
    return [
        str(item.get("plain") or item.get("label") or "").strip()
        for item in _assistant_footer_metrics(message)
    ]


def _metric_display_label(metric: Dict[str, Any]) -> str:
    """Human-facing labels; exact counts and explanations stay in tooltips."""
    label = str(metric.get("label") or "").strip()
    kind = metric.get("kind")
    if kind in {"tokens_in", "tokens_out", "tokens_total"}:
        value = label.partition(" : ")[2].removesuffix(" tk")
        return f"{value} { {'tokens_in': 'in', 'tokens_out': 'out', 'tokens_total': 'tokens'}[kind]}"
    if kind in {"tools", "files"}:
        value = label.partition(" : ")[2]
        noun = str(kind)[:-1] if value == "1" else str(kind)
        return f"{value} {noun}"
    if kind == "duration" and re.fullmatch(r"\d+s", label):
        seconds = int(label[:-1])
        if seconds >= 60:
            minutes, seconds = divmod(seconds, 60)
            return f"{minutes}m {seconds:02d}s"
    return label


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
        # Clicks are OURS. `setOpenExternalLinks(True)` hands every href straight
        # to the OS, and for a model-written `file:` link "open" can mean "run"
        # (an .app, a .command, a share on another host). With both switched off
        # QTextBrowser neither navigates nor opens; `anchorClicked` decides.
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor_clicked)
        self.highlighted[QUrl].connect(self._on_anchor_hovered)
        self.document().setDocumentMargin(0)
        try:
            self.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
            )
        except Exception:
            pass

    def _on_anchor_clicked(self, url: QUrl) -> None:
        href = bytes(url.toEncoded()).decode("utf-8", "replace")
        reveal = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)  # ⌘ on macOS
        try:
            problem = activate_message_link(href, force_reveal=reveal)
        except Exception as exc:  # a slot must never raise: Qt aborts the process
            problem = f"Could not open this link: {exc}"
        if problem:
            QToolTip.showText(QCursor.pos(), problem, self)

    def _on_anchor_hovered(self, url: QUrl) -> None:
        href = bytes(url.toEncoded()).decode("utf-8", "replace") if not url.isEmpty() else ""
        if href:
            # Escaped: Qt renders a tooltip that LOOKS like HTML as HTML, and the
            # href is model-written — `<img src=…>` in a path would be fetched.
            QToolTip.showText(QCursor.pos(), _tooltip_html(describe_link(href).split("\n")), self)
        else:
            QToolTip.hideText()

    def loadResource(self, kind: int, url: QUrl):  # noqa: N802
        """Inline `data:` images only (that is all a reply ever embeds — mermaid).

        The default loader reads ANY url a message names, on the GUI thread, while
        the message renders: `<img src="file:///home/…">` or a path on an autofs /
        network mount blocks the whole app for the mount timeout, and a model can
        be made to write one by a page it quotes.
        """
        if str(url.scheme() or "").lower() != "data":
            return None
        return super().loadResource(kind, url)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        href = str(self.anchorAt(event.pos()) or "").strip()
        if not href:
            super().contextMenuEvent(event)
            return
        local = local_path_from_href(href)
        menu = QMenu(self)
        if local is not None:
            open_action = menu.addAction("Open" if click_action(local) == "open" else "Show in Finder")
            reveal_action = menu.addAction("Show in Finder") if click_action(local) == "open" else None
            copy_action = menu.addAction("Copy Path")
            copy_value = local
        else:
            open_action = menu.addAction("Open Link")
            reveal_action = None
            copy_action = menu.addAction("Copy Link")
            copy_value = href
        chosen = menu.exec_(event.globalPos())
        if chosen is None:
            return
        if chosen is copy_action:
            QApplication.clipboard().setText(copy_value)
            return
        problem = activate_message_link(href, force_reveal=chosen is reveal_action)
        if problem:
            QToolTip.showText(event.globalPos(), problem, self)

    def refresh_height(self, width: Optional[int] = None) -> None:
        if width is None:
            width = max(1, self.viewport().width())
        else:
            width = max(1, width)
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


_COMPOSER_BASE_HEIGHT = 56
_ATTACHMENT_CHIP_SIZE = 36
_ATTACHMENT_TRAY_SPACING = 6
_ATTACHMENT_TRAY_MAX_ROWS = 3
_ATTACHMENT_TRAY_VPADDING = 8  # tray contents margins: 6 top + 2 bottom
_ATTACHMENT_TRAY_ROW_HEIGHT = _ATTACHMENT_CHIP_SIZE + _ATTACHMENT_TRAY_VPADDING


def _attachment_tray_height(rows: int) -> int:
    """Pixel height of an attachment tray showing ``rows`` wrapped chip rows."""
    visible = max(1, min(int(rows or 1), _ATTACHMENT_TRAY_MAX_ROWS))
    return (
        visible * _ATTACHMENT_CHIP_SIZE
        + (visible - 1) * _ATTACHMENT_TRAY_SPACING
        + _ATTACHMENT_TRAY_VPADDING
    )


def _refresh_style(widget: QWidget) -> None:
    """Re-apply the stylesheet after an objectName/property change."""
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class FlowLayout(QLayout):
    """Left-to-right layout that wraps onto a new row when the width runs out.

    Qt ships no wrapping layout, so a row of chips in a QHBoxLayout either
    squeezes every chip into illegibility or spills past the right edge where
    it can never be reached. Attachments arrive in unbounded numbers, so both
    the composer tray and the artifact-chip fallback need real wrapping.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        margin: int = 0,
        h_spacing: int = 6,
        v_spacing: int = 6,
    ) -> None:
        super().__init__(parent)
        self._items: List[Any] = []
        self._h_spacing = max(0, int(h_spacing))
        self._v_spacing = max(0, int(v_spacing))
        self.setContentsMargins(margin, margin, margin, margin)

    # -- QLayout plumbing -------------------------------------------------
    def addItem(self, item) -> None:  # noqa: N802 - Qt override
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 - Qt override
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802 - Qt override
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802 - Qt override
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt override
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt override
        return self._do_layout(QRect(0, 0, max(0, int(width)), 0), test_only=True)

    def setGeometry(self, rect) -> None:  # noqa: N802 - Qt override
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt override
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    def rows_for_width(self, width: int) -> int:
        """Number of wrapped rows this layout needs at ``width`` pixels."""
        margins = self.contentsMargins()
        usable = max(1, int(width) - margins.left() - margins.right())
        rows = 0
        x = 0
        for item in self._items:
            item_width = max(1, item.sizeHint().width())
            if x > 0 and x + item_width > usable:
                x = 0
            if x == 0:
                rows += 1
            x += item_width + self._h_spacing
        return max(1, rows) if self._items else 0

    def _do_layout(self, rect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_spacing
            if next_x - self._h_spacing > effective.right() + 1 and line_height > 0:
                x = effective.x()
                y = y + line_height + self._v_spacing
                next_x = x + hint.width() + self._h_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class FlowContainer(QWidget):
    """Widget host for :class:`FlowLayout` that reports its wrapped height.

    A plain QWidget advertises its layout's ``sizeHint`` and ignores
    height-for-width, so a wrapped second row would be clipped. This forwards
    both so parent layouts reserve the real height.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        h_spacing: int = 6,
        v_spacing: int = 6,
    ) -> None:
        super().__init__(parent)
        self._flow = FlowLayout(self, h_spacing=h_spacing, v_spacing=v_spacing)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def flow(self) -> FlowLayout:
        return self._flow

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt override
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt override
        return self._flow.heightForWidth(width)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        width = max(1, self.width())
        return QSize(width, self._flow.heightForWidth(width))


class MediaGallery(QWidget):
    """Grid of media thumbnails inside a message bubble.

    Stacking one full-width card per attachment wasted the whole bubble width
    on a 50px thumbnail and pushed the rest of the conversation off-screen.
    Tiles are square, uniformly sized, and packed into as many columns as the
    bubble affords, so four attachments read as one gallery rather than four
    near-empty rows.
    """

    _SPACING = 6
    _MIN_TILE = 96

    def __init__(self, *, available_width: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("mediaGallery")
        self._available_width = max(120, int(available_width or 0))
        self._cards: List[QWidget] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(self._SPACING)
        self._grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)

    def add_card(self, card: QWidget) -> None:
        self._cards.append(card)
        self._relayout()

    def card_count(self) -> int:
        return len(self._cards)

    def set_available_width(self, width: int) -> None:
        width_val = max(120, int(width or 0))
        if width_val == self._available_width:
            return
        self._available_width = width_val
        self._relayout()

    def tile_size(self) -> int:
        return self._tile_size(len(self._cards), self._available_width)

    @staticmethod
    def _base_tile_size(count: int) -> int:
        """Preferred tile edge for ``count`` items, before width clamping."""
        if count <= 1:
            return 260
        if count == 2:
            return 176
        if count <= 4:
            return 136
        if count <= 9:
            return 112
        return 92

    @classmethod
    def _columns_for(cls, count: int, width: int) -> int:
        if count <= 1:
            return 1
        # How many tiles fit at the smallest tile we are willing to draw…
        fits = max(1, (width + cls._SPACING) // (cls._MIN_TILE + cls._SPACING))
        columns = max(1, min(count, fits))
        # …then even the rows out. Taking the raw maximum leaves ragged tails
        # (four images at 3 columns render as 3 + 1); balancing turns that into
        # a clean 2 x 2.
        rows = math.ceil(count / columns)
        return max(1, math.ceil(count / rows))

    @classmethod
    def _tile_size(cls, count: int, width: int) -> int:
        if count <= 0:
            return cls._base_tile_size(1)
        columns = cls._columns_for(count, width)
        # Fill the row edge to edge, but never past the per-count ceiling: a
        # lone image should not balloon to the full bubble width.
        available = max(48, width - (columns - 1) * cls._SPACING)
        return max(48, min(cls._base_tile_size(count), available // columns))

    def _relayout(self) -> None:
        while self._grid.count():
            self._grid.takeAt(0)
        count = len(self._cards)
        if not count:
            return
        columns = self._columns_for(count, self._available_width)
        tile = self._tile_size(count, self._available_width)
        for index, card in enumerate(self._cards):
            setter = getattr(card, "set_tile_size", None)
            if callable(setter):
                setter(tile)
            self._grid.addWidget(
                card, index // columns, index % columns, Qt.AlignLeft | Qt.AlignTop
            )
        for column in range(self._grid.columnCount()):
            self._grid.setColumnStretch(column, 0)
        self._grid.setColumnStretch(max(columns, 1), 1)


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
            size=21,
        )
        icon_label.setPixmap(icon.pixmap(21, 21))
        root.addWidget(icon_label)

        remove_button = QPushButton(self)
        remove_button.setObjectName("attachmentRemoveButton")
        remove_button.setIcon(_symbol_icon("close", color="#f8fbff", size=12))
        remove_button.setIconSize(QSize(12, 12))
        remove_button.setToolTip("Remove attachment")
        remove_button.setFixedSize(18, 18)
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
        base, _highlight, _shadow, ring = self._palette_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Flat status dot + soft ring, to match the app's flat-glass chrome
        # (the old glossy sphere was the most skeuomorphic element in the UI).
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        dot_r = min(self.width(), self.height()) * 0.28

        ring_color = QColor(base.red(), base.green(), base.blue(), 70)
        painter.setPen(QPen(ring_color, 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), dot_r + 3.0, dot_r + 3.0)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(base))
        painter.drawEllipse(QPointF(cx, cy), dot_r, dot_r)
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
            button.setIcon(_symbol_icon("external", color="#f6fbff", size=16))
            button.setIconSize(QSize(16, 16))
            button.setToolTip(str(action.href or "").strip())
            button.clicked.connect(
                lambda _checked=False, href=action.href: _open_external_href(href)
            )
            layout.addWidget(button, 0, Qt.AlignLeft)


class MessageCard(QFrame):
    # Class-level default: getattr(obj, missing, default) raises RuntimeError
    # on QObjects built via __new__ (see the 2026-07-10 teardown-guard note).
    _media_gallery: Optional["MediaGallery"] = None

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
        markdown_user_body: bool = False,
    ) -> None:
        """``markdown_user_body``: render a user bubble's body as markdown
        (off by default: a person's typed prompt stays literal). On only for
        text the system composed in the user's seat — an automation's task
        turn ("[Trigger …]\n## …")."""
        super().__init__(parent)
        role = str(message.get("role") or "").strip()
        is_user = role == "user"
        copy_tint = THEME.text_secondary
        self._copy_icon = _symbol_icon("copy", color=copy_tint, size=17)
        self._copied_icon = _symbol_icon("check", color=THEME.positive, size=17)
        self._voice_icon = _symbol_icon("speaker", color=THEME.text_secondary, size=17)
        self._pause_icon = _symbol_icon("pause", color=THEME.positive, size=17)
        self._play_icon = _symbol_icon("play", color=THEME.positive, size=17)
        self._spinner_icons = [
            _symbol_icon(f"spinner{idx}", color=THEME.warning, size=17) for idx in range(8)
        ]
        self._spinner_frame = 0
        self._copy_button = None
        self._voice_button = None
        self._voice_spinner = None
        # Hover-revealed actions (operator ask 2026-07-15): the buttons keep
        # their layout slot permanently (opacity 0 <-> 1, never show/hide) so
        # revealing them cannot reflow the card under the cursor.
        self._actions_hovered = False
        self._voice_state = str(voice_state or "").strip().lower() or "idle"
        self._action_buttons: List[QPushButton] = []
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
        bubble_layout.setContentsMargins(12, 10, 12, 12)
        # User bubbles stay tight (timestamp hugs the text; the copy header has
        # its own internal padding), assistant bubbles keep block breathing room.
        bubble_layout.setSpacing(0 if is_user else 8)

        # Header: [assistant identity][stretch][timestamp][voice][copy]. The timestamp lives at
        # the upper right, co-located with the hover actions (operator ask
        # 2026-07-15: the old bottom stamp row cost a line of vertical space
        # per bubble). The stamp is always visible; the buttons fade in.
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        bubble_layout.addLayout(header_row)
        if not is_user:
            identity = QLabel("✦  Assistant")
            identity.setObjectName("messageRole")
            header_row.addWidget(identity, 0, Qt.AlignVCenter)
        if not is_user:
            header_row.addStretch(1)

        ts_val = message.get("ts") or message.get("timestamp")
        if not ts_val:
            import datetime as dt_module

            ts_val = dt_module.datetime.now(dt_module.timezone.utc).isoformat()
        timestamp = _format_message_timestamp(ts_val)
        if timestamp:
            stamp = QLabel(timestamp)
            stamp.setObjectName("messageTimestamp")
            header_row.addWidget(stamp, 0, Qt.AlignVCenter)

        if not is_user and callable(on_toggle_voice):
            voice_button = QPushButton()
            voice_button.setObjectName("messageActionButton")
            voice_button.setCheckable(True)
            try:
                voice_button.setFocusPolicy(Qt.NoFocus)
            except Exception:
                pass
            voice_button.setIconSize(QSize(17, 17))
            voice_button.setFixedSize(28, 28)
            voice_button.setToolTip("Listen to this response / Toggle voice output")
            voice_button.clicked.connect(
                lambda _checked=False, m=message: on_toggle_voice(m)
            )
            header_row.addWidget(voice_button)
            self._voice_button = voice_button
            self._register_action_button(voice_button)
            self._apply_voice_button_state(str(voice_state or "").strip())

        copy_button = QPushButton()
        copy_button.setObjectName("messageActionButton")
        try:
            copy_button.setFocusPolicy(Qt.NoFocus)
        except Exception:
            pass
        copy_button.setIcon(self._copy_icon)
        copy_button.setIconSize(QSize(17, 17))
        copy_button.setFixedSize(28, 28)
        copy_button.setToolTip("Copy message")
        copy_button.clicked.connect(self._copy_message)
        header_row.addWidget(copy_button)
        self._copy_button = copy_button
        self._register_action_button(copy_button)
        self._update_action_visibility()

        if is_user:
            browser = AutoSizingTextBrowser(min_height=20, max_height=None)
            browser.setObjectName("userMessageText")
            browser.setStyleSheet(
                f"background: transparent; border: none; color: {THEME.text_strong}; padding: 0px; margin: 0px;"
            )
            browser.setHtml(
                _assistant_html(renderer, self._content) if markdown_user_body else _user_html(self._content)
            )
            browser.refresh_height()
            # Short prompts share a row with their time/actions instead of
            # reserving an empty 28px header above a single line of text.
            browser.setMinimumWidth(0)
            header_row.insertWidget(0, browser, 1, Qt.AlignVCenter)
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
                    f"background: transparent; border: none; color: {THEME.text_primary}; padding: 0px; margin: 0px;"
                )
                browser.setHtml(_assistant_html(renderer, rendered_text))
                browser.refresh_height()
                bubble_layout.addWidget(browser)

        if self._html_actions:
            bubble_layout.addWidget(
                AssistantHtmlActionBar(actions=self._html_actions, parent=bubble)
            )

        # Files the ANSWER points at ("saved at /Users/…/clip.mp4") get the same
        # compact chip a user attachment gets: a thumbnail for a picture, icon +
        # name otherwise, one click to open. The inline link stays too — the chip
        # is the deliverable made visible, not a replacement for the sentence.
        # Only inert kinds that exist right now earn one (`mentioned_local_files`).
        if not is_user and callable(build_media_preview):
            attached = {
                str(artifact.get(key) or "").strip()
                for artifact in self._media_artifacts
                for key in ("local_path", "path", "filename")
            }
            mention_strip: Optional[FlowContainer] = None
            for item in _local_attachment_preview_items(
                mentioned_local_files(self._content)
            ):
                if item["local_path"] in attached or item["filename"] in attached:
                    continue  # already shown as generated media
                item["mentioned"] = True
                item["caption"] = _mentioned_file_caption(item["local_path"])
                # Glyph, caption, paddings and the bubble's own margins take ~200px;
                # the name gets what is left, so a narrow window elides instead of
                # clipping the chip against the bubble's edge.
                item["chip_max_text"] = max(
                    80, min(_MENTION_CHIP_MAX_TEXT, int(bubble_width or 0) - 200)
                )
                chip = build_media_preview(item, message, tile_size=0, compact=True)
                if chip is None:
                    continue
                if mention_strip is None:
                    mention_strip = FlowContainer(bubble)
                    mention_strip.setObjectName("attachmentChipStrip")
                    bubble_layout.addWidget(mention_strip)
                mention_strip.flow().addWidget(chip)

        # Images become a wrapped square-tile gallery; audio/video keep their
        # own full-width transport rows because a tile cannot host a scrubber.
        gallery_width = max(120, int(bubble_width or 0) - 24)
        gallery: Optional[MediaGallery] = None
        chip_strip: Optional[FlowContainer] = None
        # Anything that could not be previewed (PDFs, spreadsheets, unknown
        # types) still needs a chip. The old code only fell back when NOTHING
        # previewed, so a message mixing images with documents dropped the
        # documents from the bubble entirely.
        unpreviewed: List[Dict[str, Any]] = []
        if callable(build_media_preview) and is_user:
            # Files the USER attached are inputs they already know they sent:
            # they get one line of compact chips, not a 260px gallery tile that
            # pushes the conversation off-screen (operator ask 2026-09-06).
            # The picture is one click away, in ImagePreviewDialog.
            for artifact in self._media_artifacts:
                preview_widget = build_media_preview(
                    artifact, message, tile_size=0, compact=True
                )
                if preview_widget is None:
                    unpreviewed.append(artifact)
                    continue
                if chip_strip is None:
                    chip_strip = FlowContainer(bubble)
                    chip_strip.setObjectName("attachmentChipStrip")
                    bubble_layout.addWidget(chip_strip)
                chip_strip.flow().addWidget(preview_widget)
        elif callable(build_media_preview):
            image_artifacts = [
                artifact
                for artifact in self._media_artifacts
                if _artifact_media_kind(artifact) == "image"
            ]
            tile_size = (
                MediaGallery._tile_size(len(image_artifacts), gallery_width)
                if image_artifacts
                else 0
            )
            for artifact in self._media_artifacts:
                is_image = _artifact_media_kind(artifact) == "image"
                preview_widget = build_media_preview(
                    artifact, message, tile_size=tile_size if is_image else 0
                )
                if preview_widget is None:
                    unpreviewed.append(artifact)
                    continue
                if is_image:
                    if gallery is None:
                        gallery = MediaGallery(
                            available_width=gallery_width, parent=bubble
                        )
                        bubble_layout.addWidget(gallery, 0, Qt.AlignLeft)
                    preview_widget.setParent(gallery)
                    gallery.add_card(preview_widget)
                else:
                    bubble_layout.addWidget(preview_widget)
        else:
            unpreviewed = list(self._media_artifacts)
        self._media_gallery = gallery

        if unpreviewed:
            # Fallback chips wrap instead of claiming one full row each.
            chip_host = FlowContainer(bubble)
            chip_host.setObjectName("artifactChipTray")
            for artifact in unpreviewed:
                open_button = QPushButton(_artifact_label(artifact))
                open_button.setObjectName("artifactChip")
                open_button.setToolTip("Open media")
                open_button.setCursor(QCursor(Qt.PointingHandCursor))
                open_button.clicked.connect(
                    lambda _checked=False, art=dict(artifact): on_open_artifact(
                        art, message
                    )
                )
                chip_host.flow().addWidget(open_button)
            bubble_layout.addWidget(chip_host)

        if not is_user:
            footer_metrics = _assistant_footer_metrics(message)
            if footer_metrics:
                footer = FlowContainer(bubble, h_spacing=6, v_spacing=6)
                footer.setObjectName("messageMetrics")
                footer_row = footer.flow()
                footer_row.setContentsMargins(0, 4, 0, 0)
                for metric in footer_metrics:
                    label = _metric_display_label(metric)
                    if not label:
                        continue
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
                            chip.setFocusPolicy(Qt.StrongFocus)
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
                bubble_layout.addWidget(footer)

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
        for gallery in self.findChildren(MediaGallery):
            gallery.set_available_width(width_val - 24)

    def sync_to_viewport_width(self, viewport_width: int) -> None:
        self.set_bubble_width(_message_bubble_width(viewport_width, role=self._role))

    def set_voice_state(self, state: str) -> None:
        self._apply_voice_button_state(str(state or "").strip())

    def _register_action_button(self, button: QPushButton) -> None:
        """Park an action button in its hover-revealed rest state.

        The button keeps its layout slot (opacity animates, never show/hide)
        so hover cannot reflow the card; a hidden button is also disabled so
        an invisible target cannot be clicked.
        """
        effect = QGraphicsOpacityEffect(button)
        effect.setOpacity(0.0)
        button.setGraphicsEffect(effect)
        button.setEnabled(False)
        self._action_buttons.append(button)

    def _actions_should_show(self) -> bool:
        # An active voice button (spinner/pause/play) is a playback state
        # indicator, not just an affordance: it stays pinned while the mouse
        # is elsewhere.
        return self._actions_hovered or self._voice_state in {
            "synthesizing",
            "speaking",
            "paused",
        }

    def _update_action_visibility(self) -> None:
        visible = self._actions_should_show()
        for button in self._action_buttons:
            effect = button.graphicsEffect()
            if effect is not None:
                effect.setOpacity(1.0 if visible else 0.0)
        if self._copy_button is not None:
            self._copy_button.setEnabled(visible)
        if self._voice_button is not None:
            # While synthesizing the voice button shows a spinner and must not
            # accept clicks even though it is visible.
            self._voice_button.setEnabled(
                visible and self._voice_state != "synthesizing"
            )

    def enterEvent(self, event) -> None:  # noqa: N802
        self._actions_hovered = True
        self._update_action_visibility()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._actions_hovered = False
        self._update_action_visibility()
        super().leaveEvent(event)

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
        normalized = str(state or "").strip().lower() or "idle"
        self._voice_state = normalized
        if self._voice_spinner is not None and normalized != "synthesizing":
            self._voice_spinner.stop()
            self._voice_spinner.deleteLater()
            self._voice_spinner = None
        if normalized == "synthesizing":
            button.setChecked(False)
            button.setIcon(
                self._spinner_icons[self._spinner_frame % len(self._spinner_icons)]
            )
            button.setToolTip("Synthesizing reply audio")
            if self._voice_spinner is None:
                self._voice_spinner = QTimer(self)
                self._voice_spinner.timeout.connect(self._advance_voice_spinner)
                self._voice_spinner.start(90)
            self._update_action_visibility()
            return
        if normalized == "speaking":
            button.setChecked(True)
            button.setIcon(self._pause_icon)
            button.setToolTip("Pause reply audio")
        elif normalized == "paused":
            button.setChecked(True)
            button.setIcon(self._play_icon)
            button.setToolTip("Resume reply audio")
        else:
            button.setChecked(False)
            button.setIcon(self._voice_icon)
            button.setToolTip("Speak this reply")
        self._update_action_visibility()

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


class LiveMessageCard(MessageCard):
    """The reply while the model is still writing it (contract S).

    One card per streamed LLM call (``call_id``). The content channel is the
    reply text, rendered like any assistant message; the reasoning channel
    goes to a collapsed "Thinking" area and is never mixed into the reply.
    The durable assistant message REPLACES this card when it is appended —
    the live text is only a preview. Updated in place by the palette's
    throttled flush (``set_live_text``); never rebuilt per delta.
    """

    def __init__(
        self,
        *,
        call_id: str,
        run_id: str,
        renderer: MarkdownRenderer,
        bubble_width: int,
        caption: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        # An empty message key: a live card is never a scroll anchor (it is
        # about to be replaced) and never collides with a durable message.
        super().__init__(
            message={"role": "assistant", "content": ""},
            message_key="",
            renderer=renderer,
            on_open_artifact=lambda *_args: None,
            bubble_width=bubble_width,
            parent=parent,
        )
        self.setObjectName("liveMessageContainer")
        self.call_id = str(call_id or "")
        self.run_id = str(run_id or "")
        self._renderer = renderer
        self._reasoning = ""
        self._truncated = False
        self._thinking_open = False
        self._caption = str(caption or "").strip()
        layout = self._bubble.layout()

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        self.live_label = QLabel(self._label_text("Writing…"))
        self.live_label.setObjectName("messageTimestamp")
        top.addWidget(self.live_label, 0, Qt.AlignVCenter)
        top.addStretch(1)
        self.thinking_toggle = QPushButton("Thinking ▸")
        self.thinking_toggle.setObjectName("liveThinkingToggle")
        self.thinking_toggle.setCursor(QCursor(Qt.PointingHandCursor))
        self.thinking_toggle.setFlat(True)
        self.thinking_toggle.clicked.connect(self._toggle_thinking)
        self.thinking_toggle.hide()
        top.addWidget(self.thinking_toggle, 0, Qt.AlignVCenter)
        layout.addLayout(top)

        self.reasoning_view = AutoSizingTextBrowser(min_height=20, max_height=180)
        self.reasoning_view.setObjectName("liveReasoningText")
        self.reasoning_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.reasoning_view.hide()
        layout.addWidget(self.reasoning_view)

        self.truncated_note = QLabel(LIVE_TRUNCATED_NOTE)
        self.truncated_note.setObjectName("liveTruncatedNote")
        self.truncated_note.setWordWrap(True)
        self.truncated_note.hide()
        layout.addWidget(self.truncated_note)

        self.content_view = AutoSizingTextBrowser(min_height=20, max_height=None)
        self.content_view.setObjectName("assistantMessageText")
        self.content_view.setStyleSheet(
            f"background: transparent; border: none; color: {THEME.text_primary}; padding: 0px; margin: 0px;"
        )
        self.content_view.hide()
        layout.addWidget(self.content_view)

    def _label_text(self, state: str) -> str:
        return f"{self._caption} — {state}" if self._caption else state

    @property
    def caption(self) -> str:
        return self._caption

    @property
    def content_text(self) -> str:
        return self._content

    @property
    def reasoning_text(self) -> str:
        return self._reasoning

    @property
    def thinking_open(self) -> bool:
        return self._thinking_open

    def _toggle_thinking(self) -> None:
        self._thinking_open = not self._thinking_open
        self._sync_thinking()

    def _sync_thinking(self) -> None:
        has = bool(self._reasoning)
        self.thinking_toggle.setVisible(has)
        self.thinking_toggle.setText("Thinking ▾" if self._thinking_open else "Thinking ▸")
        self.reasoning_view.setVisible(has and self._thinking_open)

    def set_live_text(self, *, content: str, reasoning: str, truncated: bool) -> None:
        width = max(1, int(self._bubble.width() or 0) - 24)
        if content != self._content:
            self._content = content  # the copy button copies what is shown
            self.content_view.setHtml(_assistant_html(self._renderer, content) if content else "")
            self.content_view.setVisible(bool(content))
            self.content_view.refresh_height(width)
        if reasoning != self._reasoning:
            self._reasoning = reasoning
            bar = self.reasoning_view.verticalScrollBar()
            follow = bar is None or bar.value() >= bar.maximum() - 4
            self.reasoning_view.setPlainText(reasoning)
            self.reasoning_view.refresh_height(width)
            if follow and bar is not None:
                bar.setValue(bar.maximum())
        self._sync_thinking()
        self._truncated = bool(truncated)
        self.truncated_note.setVisible(self._truncated)

    def set_ended(self, reason: str) -> None:
        """The model call finished writing; the card waits for the durable
        message that replaces it."""
        if reason == "completed":
            self.live_label.setText(self._label_text("Finishing…"))


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
        self._play_icon = _symbol_icon("play", color="#f4f8fc", size=16)
        self._pause_icon = _symbol_icon("pause", color="#f4f8fc", size=16)
        self._open_icon = _symbol_icon("external", color="#a9bbcf", size=15)
        self._kind_icon = _symbol_icon(
            "file-audio" if self._kind == "audio" else "file-video",
            color="#77d1a8" if self._kind == "audio" else "#f0c979",
            size=16,
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
        kind_label.setPixmap(self._kind_icon.pixmap(16, 16))
        kind_label.setFixedSize(18, 18)
        title_row.addWidget(kind_label, 0, Qt.AlignVCenter)
        title_label = QLabel(self._title)
        title_label.setObjectName("mediaPreviewTitle")
        title_label.setToolTip(self._path.name or self._title)
        title_row.addWidget(title_label, 1)
        open_button = QPushButton()
        open_button.setObjectName("mediaIconButton")
        open_button.setIcon(self._open_icon)
        open_button.setIconSize(QSize(15, 15))
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
        self._play_button.setIconSize(QSize(16, 16))
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
            _symbol_icon("file-image", color="#79c7ff", size=16).pixmap(16, 16)
        )
        icon_label.setFixedSize(18, 18)
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
        tile_size: Optional[int] = None,
        compact: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._artifact = dict(artifact)
        self._resolve_path = resolve_path
        self._media_kind = _artifact_media_kind(self._artifact)
        self._title = _artifact_label(self._artifact)
        self._local_path: Optional[Path] = None
        # Compact cards are small attachment thumbnails: no square tile, no card
        # chrome, full size one click away.
        self._compact = bool(compact)
        # Tiled cards live in a MediaGallery grid: they drop the card chrome
        # (the grid supplies the rhythm) and scale into a square tile.
        self._tile_size = None if self._compact else (max(0, int(tile_size or 0)) or None)
        self._source_pixmap: Optional[QPixmap] = None
        self._image_button: Optional[QPushButton] = None
        self._thumb_label: Optional[QLabel] = None
        self._preview_dialog: Optional["ImagePreviewDialog"] = None
        self._content_layout: Optional[QVBoxLayout] = None
        self._compact_layout: Optional[QHBoxLayout] = None
        self._failure_reason: str = ""

        if self._compact:
            self.setObjectName("mediaPreviewChip")
            self._build_compact_chip()
        else:
            self.setObjectName(
                "mediaPreviewTile" if self._tile_size else "mediaPreviewCard"
            )
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
        self._start_resolve()

    def _start_resolve(self) -> None:
        """Resolve the file, on a thread only when that can actually block.

        A file the user attached from disk needs no download: resolving it is
        one stat call, so it happens inline and the card is painted once, with
        its picture. Threading it instead cost one OS thread per attachment per
        history refresh (18 for one real message here) and made every card
        flash its placeholder first.
        """
        local_path = str(
            self._artifact.get("local_path") or self._artifact.get("path") or ""
        ).strip()
        try:
            if local_path and Path(local_path).expanduser().exists():
                self._on_path_ready(local_path)
                return
        except OSError:
            pass  # unreadable parent directory: let the resolver report it
        threading.Thread(target=self._load_preview_path, daemon=True).start()

    def _build_compact_chip(self) -> None:
        """Icon + name pill, the placeholder every compact card starts as.

        An image replaces it with its own thumbnail as soon as the file
        resolves (`_apply_compact_thumbnail`); anything else — a PDF, or an
        image whose file is gone — keeps the pill, which is what an attachment
        looks like when there is no picture to show.
        """
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setProperty("hovered", "false")
        self.setToolTip(self._title)

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 10, 4)
        row.setSpacing(7)
        self._compact_layout = row

        glyph = QLabel(self)
        glyph.setObjectName("mediaPreviewChipThumb")
        glyph.setFixedSize(_ATTACHMENT_CHIP_GLYPH, _ATTACHMENT_CHIP_GLYPH)
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setPixmap(
            _symbol_icon(
                _attachment_icon_name(self._title),
                color=_attachment_icon_color(self._title),
                size=_ATTACHMENT_CHIP_GLYPH,
            ).pixmap(_ATTACHMENT_CHIP_GLYPH, _ATTACHMENT_CHIP_GLYPH)
        )
        row.addWidget(glyph, 0, Qt.AlignVCenter)

        mentioned = bool(self._artifact.get("mentioned"))
        name = QLabel(self)
        name.setObjectName("mediaPreviewChipName")
        name.setText(
            QFontMetrics(name.font()).elidedText(
                self._title,
                Qt.ElideMiddle,
                int(self._artifact.get("chip_max_text") or 0)
                or (_MENTION_CHIP_MAX_TEXT if mentioned else _ATTACHMENT_CHIP_MAX_TEXT),
            )
        )
        row.addWidget(name, 0, Qt.AlignVCenter)

        caption = str(self._artifact.get("caption") or "").strip()
        if caption:
            meta = QLabel(caption, self)
            meta.setObjectName("mediaPreviewChipMeta")
            row.addWidget(meta, 0, Qt.AlignVCenter)

    def _apply_compact_thumbnail(self, path: Path) -> None:
        """Swap the placeholder pill for the picture itself."""
        if self._media_kind == "image" and self._artifact.get("mentioned"):
            # A file the MODEL named: read the header first. A few KB of PNG can
            # declare 30000x30000 pixels, and this runs on the GUI thread every time
            # the transcript is rebuilt (each run event).
            declared = QImageReader(str(path)).size()
            if not declared.isValid() or declared.width() * declared.height() > 40_000_000:
                self.setToolTip(f"{self._title} — click to open")
                return
        pixmap = QPixmap(str(path)) if self._media_kind == "image" else QPixmap()
        if pixmap.isNull():
            self.setToolTip(f"{self._title} — click to open")
            return
        self._source_pixmap = pixmap
        thumbnail = _rounded_thumbnail(
            pixmap,
            height=_ATTACHMENT_THUMB_HEIGHT,
            max_width=_ATTACHMENT_THUMB_MAX_WIDTH,
        )

        while self._compact_layout.count():
            item = self._compact_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Unparent before deleteLater: a merely scheduled deletion keeps
                # painting the pill over the picture until the next event loop.
                widget.setParent(None)
                widget.deleteLater()
        self._compact_layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(self)
        label.setObjectName("mediaPreviewChipImage")
        label.setPixmap(thumbnail)
        self._thumb_label = label
        self._compact_layout.addWidget(label)

        if self._artifact.get("mentioned"):
            # Deliverables retain a filename and dimensions beside the preview.
            # User inputs remain compact thumbnails.
            self.setProperty("deliverable", "true")
            self._compact_layout.setContentsMargins(6, 6, 10, 6)
            details = QWidget(self)
            text_layout = QVBoxLayout(details)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(4)
            name = QLabel(self)
            name.setObjectName("mediaPreviewChipName")
            name.setTextFormat(Qt.PlainText)
            name.setText(QFontMetrics(name.font()).elidedText(
                self._title, Qt.ElideMiddle,
                int(self._artifact.get("chip_max_text") or _MENTION_CHIP_MAX_TEXT),
            ))
            text_layout.addWidget(name)
            meta = QLabel(f"{path.suffix.lstrip('.').upper()} · {pixmap.width()} × {pixmap.height()}\nClick to preview")
            meta.setObjectName("mediaPreviewChipMeta")
            text_layout.addWidget(meta)
            self._compact_layout.addWidget(details)

        # The picture carries its own frame, so the pill chrome goes away.
        self.setObjectName("mediaPreviewThumb")
        _refresh_style(self)
        self.setToolTip(
            f"{self._title} — {pixmap.width()}x{pixmap.height()} — click to preview"
        )

    def is_compact(self) -> bool:
        return bool(self._compact)

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
        if self._content_layout is None:
            return
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Hide + unparent before deleteLater: a merely scheduled
                # deletion keeps painting over its replacement until the next
                # event-loop turn.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _on_path_ready(self, raw_path: str) -> None:
        path = Path(str(raw_path or "")).expanduser()
        self._local_path = path

        if self._compact:
            self._apply_compact_thumbnail(path)
            return

        self._clear_content()

        if self._media_kind == "image":
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                self._on_preview_failed("Image preview unavailable.")
                return
            self._source_pixmap = pixmap
            button = QPushButton()
            button.setObjectName("mediaImageButton")
            button.setToolTip(str(path))
            button.clicked.connect(self._open_external)
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self._image_button = button
            self._apply_image_scale()
            self._content_layout.addWidget(button, 0, Qt.AlignLeft)
            return

        if self._media_kind in {"audio", "video"}:
            player = InlineMediaPlayer(
                kind=self._media_kind, path=path, title=self._title, parent=self
            )
            self._content_layout.addWidget(player)
            return

        self._on_preview_failed("Preview unavailable. Open the file instead.")

    def _apply_image_scale(self) -> None:
        button = self._image_button
        pixmap = self._source_pixmap
        if button is None or pixmap is None or pixmap.isNull():
            return
        if self._tile_size:
            tile = QSize(self._tile_size, self._tile_size)
            scaled = pixmap.scaled(tile, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            # The button keeps the square tile so the grid stays aligned; the
            # icon keeps the source aspect ratio and centres inside it.
            button.setFixedSize(tile)
            button.setIcon(QIcon(scaled))
            button.setIconSize(scaled.size())
            self.setFixedSize(tile)
            return
        scaled_size = _image_thumbnail_size(pixmap.size())
        scaled = pixmap.scaled(scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        button.setFixedSize(scaled.size())
        button.setIcon(QIcon(scaled))
        button.setIconSize(scaled.size())

    def _activate_compact(self) -> None:
        """Click: preview images in-app, hand anything else to the OS."""
        if self._local_path is None:
            QMessageBox.warning(
                self.window(),
                "Open failed",
                self._failure_reason or f"{self._title} is not available.",
            )
            return
        pixmap = self._source_pixmap
        if self._media_kind == "image" and pixmap is not None and not pixmap.isNull():
            dialog = ImagePreviewDialog(
                pixmap=pixmap,
                path=self._local_path,
                title=self._title,
                parent=self.window(),
            )
            # Held so the modeless dialog is not garbage collected the moment
            # this method returns.
            self._preview_dialog = dialog
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return
        if self._artifact.get("mentioned"):
            # A file the ANSWER named, not one the user attached: same rules as the
            # inline link it sits under (editor for text, reveal for anything live).
            problem = activate_message_link(file_href(str(self._local_path)))
            if problem:
                QMessageBox.warning(self.window(), "Open failed", problem)
            return
        self._open_external()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._compact and event.button() == Qt.LeftButton:
            self._activate_compact()
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._compact:
            self.setProperty("hovered", "true")
            _refresh_style(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._compact:
            self.setProperty("hovered", "false")
            _refresh_style(self)
        super().leaveEvent(event)

    def set_tile_size(self, tile_size: int) -> None:
        """Re-scale into a square tile of ``tile_size`` px (gallery resize)."""
        if self._compact:
            return
        value = max(0, int(tile_size or 0)) or None
        if value == self._tile_size:
            return
        self._tile_size = value
        self.setObjectName("mediaPreviewTile" if value else "mediaPreviewCard")
        _refresh_style(self)
        if value:
            self.setFixedSize(QSize(value, value))
        self._apply_image_scale()

    def _on_preview_failed(self, message: str) -> None:
        if self._compact:
            # A chip has no room for prose: the reason goes in the tooltip, and
            # is repeated on click. Clicking a dead chip must never be a silent
            # no-op — that reads as a broken app.
            reason = str(message or "Preview unavailable.")
            self._failure_reason = reason
            self.setToolTip(
                reason if self._title in reason else f"{self._title} — {reason}"
            )
            return
        self._clear_content()
        if self._tile_size:
            # A tile has no room for prose: keep the grid square and put the
            # reason in the tooltip.
            button = QPushButton()
            button.setObjectName("mediaOpenTile")
            button.setIcon(_symbol_icon("file", color="#9fb0c4", size=22))
            button.setIconSize(QSize(22, 22))
            button.setToolTip(f"{self._title} — {message or 'Preview unavailable.'}")
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.setFixedSize(QSize(self._tile_size, self._tile_size))
            button.clicked.connect(self._open_external)
            self._content_layout.addWidget(button, 0, Qt.AlignLeft)
            return
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


def _image_preview_style() -> str:
    """Rebuilt on demand so the preview follows the theme."""
    return _themed("""
    QDialog#imagePreviewDialog {
        background: #0f151d;
        color: #e8edf4;
    }
    QLabel#imagePreviewImage {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(166, 187, 214, 0.12);
        border-radius: 10px;
    }
    QLabel#imagePreviewMeta {
        color: #9fb0c4;
        font-size: 11px;
        font-weight: 600;
    }
    QPushButton#imagePreviewButton {
        min-height: 26px;
        border-radius: 9px;
        padding: 4px 14px;
        border: 1px solid rgba(166, 187, 214, 0.20);
        background: #1c2430;
        color: #f3f7fb;
        font-size: 11px;
        font-weight: 700;
    }
    QPushButton#imagePreviewButton:hover {
        background: #232d3b;
        border-color: rgba(121, 199, 255, 0.30);
    }
    """)


class ImagePreviewDialog(QDialog):
    """Full-size look at an image the transcript only shows as a chip.

    Modeless (the app's rule since the 2026-09-05 round-2 pass): the preview
    must never block the conversation behind it. Esc closes it.
    """

    def __init__(
        self,
        *,
        pixmap: QPixmap,
        path: Optional[Path] = None,
        title: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._path = Path(path) if path is not None else None
        label_title = str(title or "").strip() or (
            self._path.name if self._path is not None else "Preview"
        )
        self.setObjectName("imagePreviewDialog")
        self.setWindowTitle(label_title)
        self.setModal(False)
        self.restyle()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(8)

        image = QLabel(self)
        image.setObjectName("imagePreviewImage")
        image.setAlignment(Qt.AlignCenter)
        image.setPixmap(
            pixmap.scaled(
                self.fit_size(pixmap.size()),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )
        root.addWidget(image, 1, Qt.AlignCenter)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(8)
        meta = QLabel(
            f"{label_title} · {max(0, pixmap.width())}x{max(0, pixmap.height())}", self
        )
        meta.setObjectName("imagePreviewMeta")
        footer.addWidget(meta, 0, Qt.AlignVCenter)
        footer.addStretch(1)
        if self._path is not None:
            open_button = QPushButton("Open", self)
            open_button.setObjectName("imagePreviewButton")
            open_button.setToolTip(str(self._path))
            open_button.clicked.connect(self._open_external)
            footer.addWidget(open_button)
        close_button = QPushButton("Close", self)
        close_button.setObjectName("imagePreviewButton")
        close_button.clicked.connect(self.close)
        footer.addWidget(close_button)
        root.addLayout(footer)
        # Size to the picture up front: a dialog that opens at its default
        # geometry and only then settles reads as a flicker.
        self.resize(self.sizeHint())

    def restyle(self) -> None:
        """Re-read the palette (the theme changed, or first paint)."""
        self.setStyleSheet(_image_preview_style())

    @staticmethod
    def fit_size(size: QSize) -> QSize:
        """Bound an image to most of the screen, never upscaling a small one."""
        width = max(1, int(size.width() or 0))
        height = max(1, int(size.height() or 0))
        bound_width, bound_height = 1100, 780
        try:
            screen = QApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                bound_width = max(320, int(available.width() * 0.82))
                bound_height = max(240, int(available.height() * 0.82))
        except Exception:
            pass
        if width <= bound_width and height <= bound_height:
            return QSize(width, height)
        scaled = QSize(width, height).scaled(
            bound_width, bound_height, Qt.KeepAspectRatio
        )
        return QSize(max(1, scaled.width()), max(1, scaled.height()))

    def _open_external(self) -> None:
        if self._path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._path)))


# The live-run indicator is ui/activity.py's RunActivityCard; the old names
# stay importable for callers and tests.
from .ui.activity import ThinkingDotsWidget  # noqa: E402

ThinkingIndicatorCard = RunActivityCard


class RunActivityDialog(QDialog):
    """Live view of the current run's activity: per-cycle model output
    (its actual intermediate thinking), tool calls with arguments, tool
    results, and waits — appended in real time while the run progresses.

    Opened by clicking the thinking badge (laurent's ask, 2026-07-17); the
    abstractcode unfold pattern, as a modeless dialog. Model text renders
    through the SHARED markdown renderer (tables, code, lists — same as the
    transcript), never as raw pipe-text (laurent's 18:11 correction).
    """

    @staticmethod
    def _tone_colors() -> Dict[str, str]:
        """Read per row, not frozen on the class: as a class attribute these
        kept the palette the module was imported with, so the run log stayed
        on the old theme's colours after a switch."""
        return {
            "cycle": THEME.accent,
            "thinking": THEME.accent_text,
            "tool": THEME.warning,
            "result": THEME.positive,
            "waiting": THEME.attention,
            "status": THEME.text_muted,
        }

    def __init__(
        self,
        renderer: Optional[MarkdownRenderer] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._renderer = renderer or MarkdownRenderer(theme="friendly_grayscale")
        self.setWindowTitle("Run Activity")
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setModal(False)
        # A working surface, not a toast: the transcript-sized default and the
        # floor keep _show_aux_dialog's adjustSize from collapsing it.
        # Sized to sit beside the palette instead of dwarfing it.
        self.setMinimumSize(560, 420)
        self.resize(720, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._host.setObjectName("activityHost")
        self._layout = QVBoxLayout(self._host)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll, 1)

        # Persistent placeholder toggled by visibility — deleting/recreating
        # it left a deleted-later ghost painting over the entries.
        self._empty = QLabel("No run activity yet — send a message to watch it live.")
        self._empty.setObjectName("activityEmpty")
        self._empty.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self._empty)

        self.setStyleSheet(
            dialog_stylesheet()
            + """
            QWidget#activityHost {{ background: transparent; }}
            QLabel#activityEmpty {{ color: {THEME.text_faint}; padding: 24px; }}
            QFrame#activityEntry {{
                background: {THEME.overlay_faint};
                border: 1px solid {THEME.border_subtle};
                border-radius: 8px;
            }}
            QLabel#activityHeader {{ font-weight: 700; font-size: 12px; }}
            QLabel#activityBody {{ color: {THEME.text_secondary}; font-size: 12px; }}
            """.format(THEME=THEME)
        )


    def restyle(self) -> None:
        """Re-read the palette (the theme changed, or first paint)."""
        self.setStyleSheet(dialog_stylesheet() + build_activity_qss())
    def set_entries(self, entries: List[Dict[str, Any]]) -> None:
        # Remove every entry widget, keeping the persistent placeholder.
        for index in reversed(range(self._layout.count())):
            item = self._layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None and widget is not self._empty:
                self._layout.takeAt(index)
                widget.setParent(None)
                widget.deleteLater()
        self._empty.setVisible(not entries)
        for entry in entries:
            self.append_entry(entry, scroll=False)
        self._scroll_to_bottom()

    def append_entry(self, entry: Dict[str, Any], *, scroll: bool = True) -> None:
        if not isinstance(entry, dict):
            return
        widget = self._build_entry_widget(entry)
        if widget is not None:
            self._empty.setVisible(False)
            self._layout.addWidget(widget)
            if scroll:
                self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        def _apply() -> None:
            try:
                bar = self._scroll.verticalScrollBar()
                bar.setValue(bar.maximum())
            except Exception:
                pass

        QTimer.singleShot(0, _apply)

    def _build_entry_widget(self, entry: Dict[str, Any]) -> Optional[QWidget]:
        kind = str(entry.get("kind") or "").strip()
        frame = QFrame()
        frame.setObjectName("activityEntry")
        col = QVBoxLayout(frame)
        col.setContentsMargins(10, 8, 10, 8)
        col.setSpacing(4)

        def _header(text: str, tone: str) -> None:
            label = QLabel(text)
            label.setObjectName("activityHeader")
            color = self._tone_colors().get(tone, THEME.text_muted)
            label.setStyleSheet(f"color: {color};")
            col.addWidget(label)

        def _body(text: str, *, mono: bool = False) -> None:
            content = str(text or "").strip()
            if not content:
                return
            label = QLabel(content)
            label.setObjectName("activityMono" if mono else "activityBody")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            col.addWidget(label)

        def _markdown_body(text: str) -> None:
            """Model prose renders through the shared markdown pipeline —
            tables/code/lists look like the transcript, not raw pipe-text."""
            content = str(text or "").strip()
            if not content:
                return
            browser = AutoSizingTextBrowser(min_height=24, max_height=None)
            browser.setObjectName("activityMarkdown")
            browser.setStyleSheet(
                f"background: transparent; border: none; color: {THEME.text_primary}; padding: 0px; margin: 0px;"
            )
            browser.setHtml(_assistant_html(self._renderer, content))
            browser.refresh_height()
            col.addWidget(browser)

        ts = str(entry.get("ts") or "").strip()
        ts_suffix = f" — {_format_message_timestamp(ts)}" if ts else ""

        if kind == "cycle":
            _header(f"Cycle {entry.get('n')}{ts_suffix}", "cycle")
        elif kind == "thinking":
            _header(f"Model — cycle {entry.get('n')}{ts_suffix}", "thinking")
            reasoning = str(entry.get("reasoning") or "").strip()
            content = str(entry.get("content") or "").strip()
            if reasoning:
                _markdown_body(reasoning)
            if content and content != reasoning:
                _markdown_body(content)
        elif kind == "tools":
            _header(f"Tool calls{ts_suffix}", "tool")
            for tool in entry.get("tools") or []:
                if not isinstance(tool, dict):
                    continue
                name = str(tool.get("name") or "tool")
                _body(name)
                args = str(
                    tool.get("arguments_text") or tool.get("arguments_preview") or ""
                ).strip()
                if args:
                    _body(args, mono=True)
        elif kind == "tool_result":
            _header(f"Result — {entry.get('name') or 'tool'}{ts_suffix}", "result")
            _body(str(entry.get("preview") or ""), mono=True)
        elif kind == "waiting":
            _header(f"Waiting{ts_suffix}", "waiting")
            _body(str(entry.get("text") or ""))
        elif kind == "status":
            _header(f"Status{ts_suffix}", "status")
            _body(str(entry.get("text") or ""))
        else:
            return None
        return frame


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


ToolApprovalCallCard = _ToolApprovalCallCard


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
                "file", color=_FILE_ACTION_ICON_COLORS.get(action, "#8fd0ff"), size=18
            ).pixmap(18, 18)
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


# Post-hoc tool/file dialogs share the application stylesheet plus the
# approval card rules (usageStatusChip / usageCardError live there now).
def _usage_dialog_style() -> str:
    """Rebuilt on demand: frozen at import, these dialogs stayed dark inside a
    light app."""
    return dialog_stylesheet() + build_approval_qss()
ToolApprovalDialog = ToolApprovalSheet


class ToolUsageLookupWorker(QThread):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        controller: AssistantController,
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

        self.restyle()
        self.update_tool_usage(
            tool_calls=calls, source=source_s, run_ids=run_ids_s, error=error_s
        )


    def restyle(self) -> None:
        """Re-read the palette (the theme changed, or first paint)."""
        self.setStyleSheet(_usage_dialog_style())
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
                hint_text = f"{len(calls)} tools loaded from this answer's saved details."
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

        self.restyle()
        self.update_file_activity(
            tool_calls=tool_calls, source=source, run_ids=run_ids, error=error
        )


    def restyle(self) -> None:
        """Re-read the palette (the theme changed, or first paint)."""
        self.setStyleSheet(_usage_dialog_style())
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


class AssistantPalette(QMainWindow):
    hotkey_activated = pyqtSignal()
    message_speech_started = pyqtSignal(str)
    message_speech_finished = pyqtSignal(str)
    # Speech failures arrive on the TTS worker thread; this marshals them onto
    # the GUI thread so a refusal/abort becomes a banner instead of a
    # `warnings.warn` nobody can see (2026-08-02).
    message_speech_failed = pyqtSignal(str)
    connection_status_updated = pyqtSignal(object)
    # Startup work that touches the gateway runs off the GUI thread and lands
    # via these signals (bootstrap warms caches; reattach probes the last run).
    bootstrap_ready = pyqtSignal()
    reattach_candidate = pyqtSignal(object)
    # Voice recognition callbacks arrive on a background recognizer thread;
    # these signals marshal them onto the Qt main thread before touching widgets.
    transcription_received = pyqtSignal(str)
    listening_stopped = pyqtSignal()
    # Hands-free conversation: microphone/playback level (recognizer thread)
    # and the spoken reply's completion (playback thread) hop to the GUI thread.
    voice_level_received = pyqtSignal(float)
    voice_speech_finished = pyqtSignal()
    settings_ready = pyqtSignal(str)
    session_attachments_restored = pyqtSignal(int)
    # The session list came back from the gateway (payload: the refresh result).
    sessions_refreshed = pyqtSignal(object)
    # The active session's cached copy was unreadable and could not be rebuilt.
    session_sync_failed = pyqtSignal(str)
    # A sync ended after the user had switched to another session: sync that one.
    session_sync_again = pyqtSignal()
    # Meter readings arrive on the audio thread; this hops them to the GUI.
    speech_level_received = pyqtSignal(object)
    # The player started or stopped: no message key, so auto-speak and the
    # voice conversation reach the tray too.
    speech_activity_changed = pyqtSignal()

    # Run-teardown state (2026-07-10). Class-level defaults on purpose:
    # `getattr(self, ..., default)` on a missing attribute raises RuntimeError
    # (not AttributeError) on a QObject whose __init__ was skipped (tests build
    # palettes via __new__), while class attributes resolve through normal MRO.
    _cancel_requested = False
    _pending_submit = False
    # wait_key -> {"kind": "approval"|"ask", "label": str}. A run parked on the
    # user is invisible once its dialog is closed or missed: one sat 16 minutes
    # in silence. While this is non-empty the palette keeps a notice and the
    # tray keeps a badge, whatever else happens.
    _pending_user_waits: Optional[Dict[str, Dict[str, Any]]] = None
    # How the run the palette is following ENDED, per the run itself.
    # `_cancel_requested` only knows about a stop this process issued.
    _last_run_status = ""
    # Set when the voice manager surfaced a concrete failure for the current
    # speak attempt, so the generic "couldn't start" banner never overwrites a
    # specific cause.
    _voice_failure_seen = False
    # Live run-observability status routed into the transcript-tail thinking
    # badge (dots + text, one pill) instead of a banner above the transcript.
    _thinking_card = None
    _thinking_status_text = ""
    _thinking_status_tooltip = ""
    _thinking_status_tone = "thinking"
    _activity_dialog = None
    # None (not []) as the class default: a shared mutable class-level list
    # would leak activity across instances; _append_run_activity lazily
    # creates the per-instance list.
    _run_activity_log = None
    # The current history status regardless of where it renders (top label or
    # thinking badge) — generic worker statuses only fill in when this is empty.
    _history_status_text = ""
    # Live replies (contract S): call_id -> LiveReply / LiveMessageCard, the
    # calls changed since the last repaint, and the repaint throttle.
    _live_replies = None
    _live_cards = None
    _live_dirty = None
    _live_flush_timer = None
    _live_closed_calls = None
    _stream_unsupported_noted = None
    LIVE_FLUSH_MIN_MS = 40
    # True from construction until the startup bootstrap thread warms the
    # gateway caches; sends are refused meanwhile so an early send cannot
    # block the GUI thread on a cold catalog fetch or race the catalog
    # reconcile (which could publish a duplicate managed workflow).
    _bootstrapping = True

    def __init__(
        self, *, controller: AssistantController, debug: bool = False
    ) -> None:
        super().__init__()
        self._controller = controller
        # The saved theme must be live before ANY widget is built:
        # a widget that reads THEME in its constructor (the voice strip did)
        # otherwise keeps the default palette for the life of the process, not applied
        # after a flash of the default palette.
        try:
            from . import ui_themes
            from .theme import activate as _activate

            saved = ui_themes.build_theme(
                normalize_ui_theme(getattr(self._controller.preferences, "ui_theme", ""))
            )
            if saved is not None:
                _activate(saved)
        except Exception:
            pass
        try:
            global TYPOGRAPHY

            TYPOGRAPHY = Typography.from_preferences(controller.preferences)
            activate_metrics(TYPOGRAPHY.size)
        except Exception:
            pass
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
        # Live output meter for the tray while the assistant speaks.
        self._speech_meter: Any = 0.0
        self._speech_meter_ts = 0.0
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
        self.message_speech_failed.connect(self._on_message_speech_failed)
        self.connection_status_updated.connect(self._apply_connection_status)
        self.bootstrap_ready.connect(self._on_bootstrap_ready)
        self.reattach_candidate.connect(self._on_reattach_candidate)
        self.transcription_received.connect(self._on_transcription)
        self.listening_stopped.connect(self._on_listen_stop)
        self.voice_level_received.connect(self._on_voice_level)
        self.voice_speech_finished.connect(self._on_voice_speech_finished)
        self.session_attachments_restored.connect(self._on_session_attachments_restored)
        self.sessions_refreshed.connect(self._on_sessions_refreshed)
        self.session_sync_failed.connect(self._on_session_sync_failed)
        self.session_sync_again.connect(self._sync_session_from_gateway)
        # Automations (contract F): the hub does every call off the GUI thread.
        self._automations = AutomationsHub(
            client_factory=self._controller.automations_client,
            available=self._controller.automations_available,
            notify=self._notify_automation,
            ledger=NotificationLedger(self._controller.automation_notification_ledger_path()),
            parent=self,
        )
        self._automations.summaries_changed.connect(self._on_automations_changed)
        self._automations_timer = QTimer(self)
        self._automations_timer.setInterval(AUTOMATIONS_POLL_HIDDEN_MS)
        self._automations_timer.timeout.connect(self._poll_automations)
        self._automations_timer.start()
        self._automations_menu_action = None
        self._automation_view_id = ""
        self._schedule_sheet = None
        self.speech_level_received.connect(self._on_speech_level)
        self.speech_activity_changed.connect(self._refresh_tray_feedback)
        self._voice_conversation: Optional[VoiceConversation] = None
        self._voice_conversation_active = False
        self._voice_level_last_emit = 0.0
        self._auto_speak_before_voice: Optional[bool] = None
        self._workspace_root_label = ""
        self._controller.voice_manager.on_speech_start = self._on_voice_speech_activity
        self._controller.voice_manager.on_speech_end = self._on_voice_speech_activity
        self._controller.voice_manager.on_speech_error = (
            self.message_speech_failed.emit
        )
        self._install_speech_meter()
        # Settings reaches the theme switch through the controller rather than
        # walking the widget tree.
        try:
            self._controller.apply_theme = self.apply_theme
            self._controller.apply_typography = self.apply_typography
        except Exception:
            pass

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
            zoom_button.setToolTip("Maximize window")
            zoom_button.clicked.connect(self._toggle_zoom)
            traffic_group.addWidget(zoom_button, 0, Qt.AlignVCenter)

        # The title label doubles as the status readout: idle it names the
        # app; during a run / voice activity it says what is happening (the
        # header has no spare width for a separate status chip).
        title = QLabel("AbstractAssistant")
        title.setObjectName("windowTitle")
        title.setProperty("tone", "idle")
        title.setMinimumWidth(120)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.title_label = title
        title_row.addWidget(title, 2, Qt.AlignVCenter)

        # The chat control opens the switcher (search, metrics, rename,
        # delete) — a dropdown of truncated first questions could not say
        # which chat holds the work.
        self.session_picker = QPushButton("Untitled session")
        self.session_picker.setObjectName("sessionPicker")
        self.session_picker.setFixedHeight(28)
        self.session_picker.setMinimumWidth(136)
        self.session_picker.setMaximumWidth(248)
        self.session_picker.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.session_picker.setCursor(Qt.PointingHandCursor)
        self.session_picker.setIcon(_symbol_icon("chevron-down", color=THEME.text_muted, size=12))
        self.session_picker.setIconSize(QSize(12, 12))
        self.session_picker.setLayoutDirection(Qt.RightToLeft)  # chevron on the right
        self.session_picker.setToolTip("Switch session")
        self.session_picker.clicked.connect(self._open_session_switcher)
        title_row.addWidget(self.session_picker, 1, Qt.AlignVCenter)

        header_actions = QHBoxLayout()
        header_actions.setContentsMargins(0, 0, 0, 0)
        header_actions.setSpacing(4)
        title_row.addLayout(header_actions, 0)

        new_session = QPushButton()
        new_session.setObjectName("iconButton")
        new_session.setIcon(_symbol_icon("plus", size=16))
        new_session.setIconSize(QSize(16, 16))
        new_session.setFixedSize(28, 28)
        new_session.setToolTip("New session (⌘N)")
        new_session.clicked.connect(self._create_session)
        header_actions.addWidget(new_session)

        tools = QPushButton()
        tools.setObjectName("iconButton")
        tools.setIcon(_symbol_icon("shield", size=16))
        tools.setIconSize(QSize(16, 16))
        tools.setFixedSize(28, 28)
        tools.setToolTip("Tools & permissions")
        tools.clicked.connect(self._open_tool_settings)
        header_actions.addWidget(tools)

        schedule = QPushButton()
        schedule.setObjectName("iconButton")
        schedule.setIcon(_symbol_icon("clock", size=16))
        schedule.setIconSize(QSize(16, 16))
        schedule.setFixedSize(28, 28)
        schedule.setToolTip("Schedule this conversation…")
        schedule.clicked.connect(self._open_schedule_sheet)
        header_actions.addWidget(schedule)
        self.schedule_button = schedule
        # Shown once a poll confirms the gateway offers automations.
        schedule.hide()

        self.auto_speak = QPushButton()
        self.auto_speak.setObjectName("topIconToggleButton")
        self.auto_speak.setCheckable(True)
        self.auto_speak.setIcon(_symbol_icon("speaker", size=16))
        self.auto_speak.setIconSize(QSize(16, 16))
        self.auto_speak.setFixedSize(28, 28)
        self.auto_speak.setChecked(bool(self._controller.preferences.auto_speak))
        self.auto_speak.clicked.connect(self._persist_auto_speak)
        self.auto_speak.setToolTip("Speak replies aloud")
        header_actions.addWidget(self.auto_speak)

        settings = QPushButton()
        settings.setObjectName("iconButton")
        settings.setIcon(_symbol_icon("gear", size=16))
        settings.setIconSize(QSize(16, 16))
        settings.setFixedSize(28, 28)
        settings.setToolTip("Settings (⌘,)")
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
        # An automation opened from the switcher replaces the transcript in
        # place (its occurrences read as a chat); "← Chat" brings it back.
        self.automation_view = AutomationView(
            render_turn=self._automation_turn_card,
            bubble_width=_message_bubble_width,
            parent=self.history_card,
        )
        self.automation_view.hide()
        self.automation_view.back_requested.connect(self._close_automation_view)
        self.automation_view.control_requested.connect(self._on_automation_control)
        self.automation_view.revise_requested.connect(self._on_automation_revise)
        self.automation_view.discuss_requested.connect(self._on_automation_discuss)
        self.automation_view.wait_answered.connect(self._on_automation_wait_answer)
        self.automation_view.load_more_requested.connect(self._on_automation_load_more)
        self.automation_view.retry_requested.connect(self._automations.retry)
        history_wrap.addWidget(self.automation_view, 1)

        self.composer_card = AttachmentDropFrame(central)
        self.composer_card.setObjectName("composerCard")
        self.composer_card.setFixedHeight(56)
        self.composer_card.files_dropped.connect(self._handle_dropped_files)
        self.composer_card.drop_active_changed.connect(self._set_composer_drop_active)
        composer_outer = QVBoxLayout(self.composer_card)
        composer_outer.setContentsMargins(0, 0, 0, 0)
        composer_outer.setSpacing(0)

        # The tray wraps: a single non-scrolling row silently clipped every
        # chip past the composer width, so attaching many files hid most of
        # them. It grows to _ATTACHMENT_TRAY_MAX_ROWS, then scrolls.
        self.attachments_tray = QScrollArea()
        self.attachments_tray.setObjectName("attachmentsTray")
        self.attachments_tray.setWidgetResizable(True)
        self.attachments_tray.setFrameShape(QFrame.NoFrame)
        self.attachments_tray.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.attachments_tray.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.attachments_tray.setFixedHeight(_ATTACHMENT_TRAY_ROW_HEIGHT)
        self.attachments_tray.hide()
        self.attachments_host = FlowContainer(h_spacing=6, v_spacing=6)
        self.attachments_host.setObjectName("attachmentsTrayHost")
        self.attachments_layout = self.attachments_host.flow()
        self.attachments_layout.setContentsMargins(8, 6, 8, 2)
        self.attachments_tray.setWidget(self.attachments_host)
        composer_outer.addWidget(self.attachments_tray)

        # Hands-free conversation status (hidden until a conversation starts).
        self.voice_strip = VoiceStrip(self.composer_card)
        self.voice_strip.hide()
        self.voice_strip.pause_toggled.connect(self._voice_pause_toggled)
        self.voice_strip.stop_speech_requested.connect(self._voice_stop_speaking)
        self.voice_strip.interrupt_requested.connect(self._cancel_active_run)
        self.voice_strip.end_requested.connect(self._end_voice_conversation)
        composer_outer.addWidget(self.voice_strip)

        composer = QHBoxLayout()
        composer.setContentsMargins(4, 4, 4, 4)
        composer.setSpacing(4)
        composer_outer.addLayout(composer)

        self.attach_button = QPushButton()
        self.attach_button.setObjectName("composerIconButton")
        self.attach_button.setIcon(_symbol_icon("paperclip", size=18))
        self.attach_button.setIconSize(QSize(18, 18))
        self.attach_button.setFixedSize(36, 36)
        self.attach_button.setToolTip(
            "Attach files, photos, or documents (Drag & Drop supported)"
        )
        self.attach_button.clicked.connect(self._pick_attachments)
        composer.addWidget(self.attach_button)

        self.mic_button = QPushButton()
        self.mic_button.setObjectName("composerIconButton")
        self.mic_button.setIcon(_symbol_icon("mic", size=18))
        self.mic_button.setIconSize(QSize(18, 18))
        self.mic_button.setFixedSize(36, 36)
        self.mic_button.setToolTip("Dictate into the message")
        self.mic_button.clicked.connect(self._toggle_listening)
        composer.addWidget(self.mic_button)

        self.conversation_button = QPushButton()
        self.conversation_button.setObjectName("composerIconButton")
        self.conversation_button.setCheckable(True)
        self.conversation_button.setIcon(_symbol_icon("audio-lines", size=18))
        self.conversation_button.setIconSize(QSize(18, 18))
        self.conversation_button.setFixedSize(36, 36)
        self.conversation_button.setToolTip("Start a voice conversation (⌘⇧V)")
        self.conversation_button.clicked.connect(self._toggle_voice_conversation)
        composer.addWidget(self.conversation_button)

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
        self.send_button.setIcon(_symbol_icon("send", color="#f8fffc", size=21))
        self.send_button.setIconSize(QSize(21, 21))
        self.send_button.setFixedSize(38, 38)
        self.send_button.setToolTip("Send message")
        self.send_button.clicked.connect(self._on_send_button_clicked)
        # During a run the button is also the control surface: right-click
        # offers pause/resume/stop (click alone stops; typed text steers).
        self.send_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.send_button.customContextMenuRequested.connect(self._show_run_control_menu)
        composer.addWidget(self.send_button)

        QShortcut(Qt.Key_Escape, self, activated=self._on_escape)
        QShortcut(Qt.CTRL | Qt.Key_N, self, activated=self._create_session)
        QShortcut(Qt.CTRL | Qt.Key_Comma, self, activated=self._open_settings)
        QShortcut(Qt.CTRL | Qt.Key_Period, self, activated=self._cancel_active_run)
        QShortcut(Qt.CTRL | Qt.SHIFT | Qt.Key_V, self, activated=self._toggle_voice_conversation)

        self._apply_styles()
        self.refresh_history()
        self._render_attachments()
        self._apply_hotkey()
        self._request_connection_status_refresh()
        self._connection_status_timer.start()
        # Warm the workflow/tool/capabilities caches off the GUI thread instead
        # of blocking the first paint on ~6 sequential 30s round trips; the
        # cache-backed refreshes then run instantly when bootstrap lands.
        self._set_history_status("Connecting to gateway…", tone="busy")
        self._start_bootstrap()
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

    def _start_bootstrap(self) -> None:
        """Warm gateway caches off-thread, then apply UI state + probe reattach."""

        def _run() -> None:
            try:
                self._controller.prefetch()
            except Exception:
                pass
            try:
                self.bootstrap_ready.emit()
            except RuntimeError:
                # Palette was destroyed mid-launch (quit during bootstrap).
                return
            try:
                candidate = self._controller.probe_reattach_candidate()
            except Exception:
                candidate = None
            if candidate:
                try:
                    self.reattach_candidate.emit(candidate)
                except RuntimeError:
                    return

        threading.Thread(target=_run, name="assistant-bootstrap", daemon=True).start()

    def _on_bootstrap_ready(self) -> None:
        self._bootstrapping = False
        # Cache-backed refreshes are instant now that prefetch warmed them.
        connecting = False
        try:
            connecting = "Connecting to gateway" in str(self.chat_status_label.text() or "")
        except Exception:
            connecting = False
        self._refresh_workflows()
        self._refresh_capability_state()
        self._refresh_submission_state()
        # The gateway is reachable now: the session list and the transcript on
        # screen come from it (the local copies are only a cache).
        self._refresh_sessions_from_gateway()
        self._sync_session_from_gateway()
        # Clear the transient "Connecting…" banner unless a refresh replaced it
        # with something more specific (e.g. a gateway-unavailable message).
        try:
            if connecting and "Connecting to gateway" in str(self.chat_status_label.text() or ""):
                self._set_history_status()
        except Exception:
            pass

    def _on_reattach_candidate(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            return
        # If the user already started sending, don't hijack their run.
        if self._worker is not None:
            return
        # The probe ran on a background thread; if the active session's last
        # run changed since (a quick turn finished while probing), the
        # candidate is stale — reattaching would rewrite last_run_id to the
        # older run and misdirect steer/pause/cancel.
        if str(self._controller.last_run_id() or "").strip() != run_id:
            return
        try:
            worker = self._controller.build_attach_worker(run_id)
        except Exception:
            return
        # A run that has already ended is RECOVERED, not followed: it gets no
        # Stop button, no pause control and no "in progress" copy. The probe
        # reattaches to a terminal run to pull back an answer written while
        # the app was closed, and presenting that as a live run showed run
        # controls for something that had finished half an hour earlier.
        ended = str(payload.get("status") or "").strip().lower()
        recovering = ended in {"completed", "failed", "cancelled"}

        self._worker = worker
        self._cancel_requested = False
        self._last_run_status = ended if recovering else ""
        self._run_busy = not recovering
        self._run_has_final_output = False
        self._discard_live_replies()
        self._live_closed_calls = set()
        self._clear_run_activity()
        self._activity_model = RunActivityModel(run_id=run_id, reattached=True)
        worker.event_emitted.connect(self._on_worker_event)
        worker.error_occurred.connect(self._on_worker_error)
        warning_signal = getattr(worker, "warning_occurred", None)
        if warning_signal is not None:
            warning_signal.connect(self._on_worker_warning)
        worker.finished.connect(self._on_worker_finished)
        self._set_send_button_busy(not recovering)
        message = (
            "Catching up on the last run…"
            if recovering
            else "Reattached to the run in progress…"
        )
        self._set_status(message, tone="busy")
        self._set_history_status(message, tone="busy")
        self._refresh_tray_feedback()
        worker.start()
        # Show the thinking badge (with the reattach status) right away instead
        # of waiting for the first replay event to rebuild the transcript.
        self.refresh_history(request=self._history_scroll_request(mode="bottom"))

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

    def _session_records(self) -> List[Dict[str, Any]]:
        """The session list for the header and the switcher.

        Digests, always — they are the only records that carry `display_title`,
        and without them the header read the stored title, which is the
        placeholder "New session" for practically every session on disk. They
        are a cached local read (42 ms cold, under 2 ms warm), so loading them
        on demand here is cheaper than being wrong.
        """
        digests = self._state("_session_digests")
        if not (isinstance(digests, list) and digests):
            self._warm_session_digests()
            digests = self._state("_session_digests")
        if isinstance(digests, list) and digests:
            return list(digests)
        try:
            return [dict(rec) for rec in (self._controller.list_sessions() or []) if isinstance(rec, dict)]
        except Exception:
            return []

    def _refresh_session_picker(
        self, *, select_session_id: Optional[str] = None
    ) -> None:
        button = self._state("session_picker")
        if button is None:
            return
        active = str(select_session_id or self._active_session_id() or "").strip()
        records = self._session_records()
        title = ""
        for record in records:
            if str(record.get("session_id") or "") == active:
                # `title` is "New session" for almost every chat on disk — the
                # digest's display_title falls back to the opening question, so
                # the header names the chat the way the switcher row does.
                title = str(record.get("display_title") or record.get("title") or "")
                break
        self._session_button_title = _session_button_text(title)
        try:
            button.setEnabled(True)
        except Exception:
            return
        self._elide_session_button()
        self._refresh_workspace_hint()

    def _elide_session_button(self) -> None:
        """Fit the session name to the control, leaving room for the chevron."""
        button = self._state("session_picker")
        if button is None:
            return
        full = str(self._state("_session_button_title", "") or "Untitled session")
        try:
            metrics = QFontMetrics(button.font())
            available = max(40, button.width() - 36)
            button.setText(metrics.elidedText(full, Qt.ElideRight, available))
            button.setToolTip(button.toolTip() or "Switch session")
        except Exception:
            pass

    def _warm_session_digests(self) -> None:
        """Re-read the chat metrics.

        Synchronous on purpose: the digests come from local files behind a cache
        keyed by file identity, measured on the real store at 42 ms for 74 chats
        cold and 1 ms once warm. The background version this replaces landed its
        result seconds AFTER the popup was already open and rebuilt every row
        underneath the user — which squeezed the rows on top of each other and
        cost the palette its activation (the popup then vanished).
        """
        try:
            digests = self._controller.session_digests()
        except Exception:
            digests = []
        self._session_digests = list(digests) if isinstance(digests, list) else []

    def _invalidate_session_digests(self) -> None:
        """The transcript changed: the next read recomputes what is stale.

        `SessionDigestCache` is keyed by file identity, so only the session
        that actually changed is parsed again.
        """
        self._session_digests = []

    def _open_session_switcher(self) -> None:
        """Open the chat switcher under the header control."""
        switcher = self._state("_session_switcher")
        if switcher is None:
            switcher = SessionSwitcher(parent=self)
            switcher.session_chosen.connect(self._switch_to_session)
            switcher.new_chat_requested.connect(self._create_session)
            switcher.rename_requested.connect(self._rename_session)
            switcher.automation_chosen.connect(self._open_automation)
            switcher.automation_open_requested.connect(self._open_automation)
            switcher.automation_edit_requested.connect(self._edit_automation)
            switcher.automation_control_requested.connect(self._on_switcher_automation_control)
            switcher.load_more_requested.connect(self._load_more_sessions)
            switcher.tab_changed.connect(self._on_switcher_tab_changed)
            switcher.new_automation_requested.connect(self._open_new_automation_sheet)
            self._session_switcher = switcher
        self._apply_automations_to_switcher(switcher)
        self._warm_session_digests()
        switcher.set_digests(
            self._session_records(),
            active_session_id=self._active_session_id(),
            more=self._sessions_more(),
        )
        tab = self._state("_switcher_open_tab") or self._controller.switcher_tab()
        self._switcher_open_tab = None
        switcher.set_tab(str(tab))
        self._apply_session_list_status(switcher)
        button = self._state("session_picker")
        try:
            origin = button.mapToGlobal(QPoint(0, button.height() + 6))
        except Exception:
            origin = self.mapToGlobal(QPoint(0, 40))
        switcher.open_at(origin, screen_geometry=self._available_screen_geometry())
        # The rows above are the cache; the gateway's answer replaces them.
        self._refresh_sessions_from_gateway()
        self._poll_automations()

    # ------------------------------------------------------------ automations

    def _poll_automations(self) -> None:
        hub = self._state("_automations")
        if hub is not None:
            hub.poll()

    def _notify_automation(self, title: str, body: str) -> None:
        self._notify(str(title or "Automation"), str(body or title or ""), duration_ms=7000)

    def _automations_status_text(self) -> str:
        hub = self._state("_automations")
        if hub is None:
            return ""
        if hub.error:
            return f"Automations: {hub.error}"
        if hub.available is True and not hub.summaries:
            return "No automation yet. Schedule a conversation with the clock button."
        return ""

    def _apply_automations_to_switcher(self, switcher: Any) -> None:
        hub = self._state("_automations")
        if hub is None:
            return  # a palette built without __init__ (tests)
        if hub.available is not True and not hub.error:
            # Not advertised (or not asked yet): no Automations tab at all.
            switcher.set_automations([], status="", available=False)
            return
        switcher.set_automations(hub.summaries, status=self._automations_status_text(), available=True)

    def _on_automations_changed(self, _summaries: Any) -> None:
        hub = self._automations
        switcher = self._state("_session_switcher")
        if switcher is not None:
            try:
                if switcher.isVisible():
                    self._apply_automations_to_switcher(switcher)
            except RuntimeError:
                self._session_switcher = None
        unread = hub.unread
        button = self._state("schedule_button")
        if button is not None:
            button.setVisible(hub.available is True)
        action = self._state("_automations_menu_action")
        if action is not None:
            try:
                action.setText(f"Automations… ({unread} new)" if unread else "Automations…")
                action.setVisible(hub.available is True)
            except RuntimeError:
                self._automations_menu_action = None
        view_id = self._state("_automation_view_id", "")
        if view_id:
            summary = hub.summary(view_id)
            if summary is not None:
                self.automation_view.set_summary(summary)

    def _automation_turn_card(self, role: str, content: str, ts: str, bubble_width: int) -> QWidget:
        """An occurrence's task or answer, rendered by the conversation's own
        `MessageCard` (same markdown/code/table/JSON rendering as a chat)."""
        message = {"role": role, "content": content, "ts": ts}
        return MessageCard(
            message=message,
            message_key=f"automation:{role}:{ts}:{hash(content)}",
            renderer=self._renderer,
            on_open_artifact=self._open_artifact_from_message,
            build_media_preview=self._build_media_preview,
            bubble_width=bubble_width,
            # The task turn is composed by the automation, never typed.
            markdown_user_body=role == "user",
        )

    def open_automations(self) -> None:
        """Tray "Automations…": show the palette with the switcher open on the
        Automations tab."""
        self.show_palette()
        self._switcher_open_tab = "automations"
        QTimer.singleShot(0, self._open_session_switcher)

    def _on_switcher_tab_changed(self, tab: str) -> None:
        """The last switcher tab is remembered."""
        try:
            self._controller.set_switcher_tab(str(tab))
        except Exception as exc:
            self._set_banner(f"Could not remember the switcher tab: {exc}", tone="warn", key="session")

    def _edit_automation(self, automation_id: str) -> None:
        """"Edit schedule…" in the switcher: the automation view with its edit form open."""
        self._open_automation(automation_id, where="top")
        if self._state("_automation_view_id") == str(automation_id):
            button = self.automation_view.control_buttons["revise"]
            if button.isEnabled():
                button.click()

    def _on_switcher_automation_control(self, automation_id: str, control: str) -> None:
        """An inline control of the Automations tab (pause / resume / run now /
        stop / archive): the same command path as the automation view."""
        switcher = self._state("_session_switcher")

        def done(ok: bool, value: Any) -> None:
            if switcher is not None:
                try:
                    if ok:
                        switcher.set_status("")
                    else:
                        switcher.set_status(self._automations.error_text(value), tone="warn")
                except RuntimeError:
                    return
            self._poll_automations()

        self._automations.command(str(automation_id), str(control), done)

    def _open_automation(self, automation_id: str, where: str = "latest") -> None:
        """Open an automation in the palette; ``where`` = "latest" (scrolled to
        the last run) or "top" (its first run)."""
        aid = str(automation_id or "").strip()
        summary = self._automations.summary(aid)
        if summary is None:
            self._set_banner("That automation is not in the list any more.", tone="info", key="automation")
            return
        self._automation_view_id = aid
        view = self.automation_view
        view.set_error("")
        view.set_notice("Loading runs…")
        view.set_occurrences([], next_cursor=None)
        view.set_summary(summary)
        self.history_scroll.hide()
        self.chat_status_label.hide()
        self.composer_card.hide()
        view.show()
        if summary.get("legacy"):
            # A schedule from before automations: the gateway serves no
            # definition or occurrences for it (GET /automations/{id} → 404).
            view.set_notice(
                "This is an older scheduled run, kept with its own controls. Manage it from the Observer, "
                "or recreate it as an automation."
            )
            return

        def loaded(ok: bool, value: Any) -> None:
            if self._state("_automation_view_id") != aid:
                return
            view.set_notice("")
            if not ok:
                view.set_error(self._automations.error_text(value))
                return
            view.set_occurrences(value.get("items") or [], next_cursor=value.get("next_cursor"))
            if where == "top":
                view.scroll.verticalScrollBar().setValue(0)
            else:
                view.scroll_to_latest()
            # Viewing acknowledges the attention items the view DISPLAYED.
            self._automations.mark_seen(summary)

        self._automations.load_occurrences(aid, loaded)

    def _close_automation_view(self) -> None:
        self._automation_view_id = ""
        self.automation_view.hide()
        self.history_scroll.show()
        self.composer_card.show()
        self.refresh_history()

    def _reload_open_automation(self) -> None:
        aid = self._state("_automation_view_id", "")
        if not aid:
            return
        view = self.automation_view

        def loaded(ok: bool, value: Any) -> None:
            if ok and self._state("_automation_view_id") == aid:
                view.set_occurrences(value.get("items") or [], next_cursor=value.get("next_cursor"))

        self._automations.poll()
        self._automations.load_occurrences(aid, loaded)

    def _automation_call_done(self, success_notice: str) -> Callable[[bool, Any], None]:
        view = self.automation_view

        def done(ok: bool, value: Any) -> None:
            view.set_busy(False)
            if not ok:
                view.set_error(self._automations.error_text(value), retry=self._automations.can_retry)
                return
            view.set_error("")
            receipt = value if isinstance(value, dict) else {}
            if receipt.get("duplicate"):
                # The same command id was already queued: the first one stands.
                view.set_notice(f"{success_notice} (already received)")
            elif receipt.get("accepted") is True:
                view.set_notice(success_notice)
            else:
                view.set_error("The gateway did not accept the request.")
            self._reload_open_automation()

        return done

    def _on_automation_control(self, control: str) -> None:
        aid = self._state("_automation_view_id", "")
        if not aid:
            return
        labels = {
            "pause": "Paused: no scheduled run until you resume.",
            "resume": "Resumed: the next run is on the schedule.",
            "run_now": "Run requested.",
            "stop_current": "Stop requested.",
            "archive": "Archived. Its history is kept.",
        }
        self.automation_view.set_busy(True)
        self._automations.command(aid, control, self._automation_call_done(labels.get(control, "Done.")))

    def _on_automation_revise(self, changes: Any) -> None:
        summary = self._automations.summary(self._state("_automation_view_id", ""))
        if summary is None or not isinstance(changes, dict):
            return
        self.automation_view.set_busy(True)
        self._automations.revise(summary, changes, self._automation_call_done("Saved; applies from the next run."))

    def _on_automation_load_more(self) -> None:
        aid = self._state("_automation_view_id", "")
        view = self.automation_view
        cursor = view.next_cursor
        if not aid or not cursor:
            return

        def loaded(ok: bool, value: Any) -> None:
            if not ok:
                view.set_error(self._automations.error_text(value))
                return
            if self._state("_automation_view_id") == aid:
                view.set_occurrences(value.get("items") or [], next_cursor=value.get("next_cursor"), append=True)

        self._automations.load_occurrences(aid, loaded, cursor=cursor)

    def _on_automation_wait_answer(self, run_id: str, wait_key: str, kind: str, answer: Any) -> None:
        view = self.automation_view
        view.set_busy(True)
        controller = self._controller

        def done(ok: bool, value: Any) -> None:
            view.set_busy(False)
            if not ok:
                view.set_error(f"Your answer did not reach the gateway ({value}). The run is still waiting; try again.")
                return
            view.set_notice(
                ("Approved; the occurrence continues." if answer is True else "Denied; the occurrence continues.")
                if kind == "tool_approval"
                else "Answer sent; the occurrence continues."
            )
            self._reload_open_automation()

        self._automations.run(
            lambda: controller.answer_wait(run_id=run_id, wait_key=wait_key, kind=kind, answer=answer), done
        )

    def _on_automation_discuss(self, index: int, prompt: str) -> None:
        aid = self._state("_automation_view_id", "")
        if not aid:
            return
        if self._state("_worker") is not None:
            self.automation_view.set_error("Wait for the current reply to finish (or stop it) before opening a discussion.")
            return
        view = self.automation_view
        view.set_busy(True)

        def done(ok: bool, value: Any) -> None:
            view.set_busy(False)
            if not ok:
                view.set_error(self._automations.error_text(value), retry=self._automations.can_retry)
                return
            self._open_discussion(value if isinstance(value, dict) else {}, occurrence_index=int(index))

        self._automations.discuss(aid, int(index), str(prompt), done)

    def _open_discussion(self, result: Dict[str, Any], *, occurrence_index: int) -> None:
        """Discuss answered: its session is an ordinary gateway session —
        switch to it and follow its first run like any reattach."""
        session_id = str(result.get("session_id") or "").strip()
        run_id = str(result.get("run_id") or "").strip()
        if not session_id or not run_id:
            self.automation_view.set_error("The gateway did not return the discussion's session.")
            return
        try:
            self._controller.open_gateway_session(session_id, run_id=run_id)
        except Exception as exc:
            self.automation_view.set_error(f"Could not open the discussion: {exc}")
            return
        self._close_automation_view()
        self._tray_completion_unread = False
        self._set_history_status()
        self._set_banner(*discussion_banner(result, occurrence_index=occurrence_index), key="session")
        self._invalidate_session_digests()
        self._refresh_session_picker(select_session_id=session_id)
        self._on_reattach_candidate({"run_id": run_id, "status": "running", "waiting": None})
        self._refresh_sessions_from_gateway()

    def _open_new_automation_sheet(self) -> None:
        """"+ New automation" in the switcher: the same sheet, standalone —
        an empty task, the default schedule, the configured workflow."""
        self._open_schedule_sheet(standalone=True)

    def _open_schedule_sheet(self, standalone: bool = False) -> None:
        """"Schedule this conversation…": the conversation's workflow and its
        last prompt prefill the sheet (the workflow is resolved off the GUI
        thread; the catalog may need a round trip). ``standalone``: the
        switcher's "+ New automation" (no prompt; the new row is selected in
        the Automations tab after creation)."""
        if self._automations.available is not True:
            # No automation route before a poll confirmed the gateway offers them.
            self._set_banner("This gateway does not offer automations.", tone="info", key="automation")
            return
        controller = self._controller
        prompt = "" if standalone else controller.last_user_prompt()

        def resolved(ok: bool, value: Any) -> None:
            selection = value if ok else None
            label = str(getattr(selection, "label", "") or getattr(selection, "bundle_id", "") or "")
            if getattr(selection, "is_gateway_default", False):
                label = f"gateway default ({label})" if label else "gateway default"
            sheet = ScheduleSheet(target=target_from_workflow(selection), target_label=label, prompt=prompt, parent=self)
            sheet.standalone = bool(standalone)
            if standalone:
                sheet.setWindowTitle("New automation")
            sheet.submitted.connect(lambda body, s=sheet: self._submit_schedule(s, body))
            self._schedule_sheet = sheet
            # Typing in the sheet must not hide the palette (focus rule).
            self._register_aux_dialog(sheet)
            self._automations.trigger_sources(
                lambda ok2, sources: sheet.set_trigger_sources(sources.get("items") or [])
                if ok2 and isinstance(sources, dict)
                else sheet.set_error(self._automations.error_text(sources))
            )
            sheet.show()
            sheet.raise_()

        self._automations.run(controller.current_workflow, resolved)

    def _submit_schedule(self, sheet: Any, body: Dict[str, Any]) -> None:
        def done(ok: bool, value: Any) -> None:
            if not ok:
                sheet.submit_failed(
                    self._automations.error_text(value), reuse_id=self._automations.no_gateway_answer(value)
                )
                return
            sheet.close()
            summary = value.get("summary") if isinstance(value, dict) else None
            if isinstance(summary, dict) and summary.get("automation_id"):
                hub = self._automations
                hub.summaries = [s for s in hub.summaries if s.get("automation_id") != summary["automation_id"]] + [summary]
                if getattr(sheet, "standalone", False):
                    # "+ New automation": back to the Automations tab, the new row selected.
                    self._switcher_open_tab = "automations"
                    self._open_session_switcher()
                    switcher = self._state("_session_switcher")
                    if switcher is not None:
                        switcher.select_automation(str(summary["automation_id"]))
                else:
                    self._open_automation(str(summary["automation_id"]))
            self._poll_automations()

        self._automations.create(body, done)

    def _refresh_open_session_switcher(self) -> None:
        """Re-render the popup's rows (rename, or the gateway answered)."""
        switcher = self._state("_session_switcher")
        if switcher is None:
            return
        try:
            if switcher.isVisible():
                switcher.set_digests(
                    self._session_records(),
                    active_session_id=self._active_session_id(),
                    more=self._sessions_more(),
                )
                self._apply_session_list_status(switcher)
        except RuntimeError:
            self._session_switcher = None

    def _active_session_listed_on_gateway(self) -> bool:
        """Whether the cached list already has a gateway row for the session
        on screen (True when there is no controller to ask)."""
        if self._state("_controller") is None:
            return True
        try:
            active = self._active_session_id()
            for record in self._session_records():
                if str(record.get("session_id") or "") == active:
                    return bool(record.get("on_gateway", True))
        except Exception:
            return True
        return False

    def _apply_session_list_status(self, switcher: Any) -> None:
        """The switcher's header line: where the rows come from."""
        setter = getattr(switcher, "set_status", None)
        if not callable(setter):
            return
        controller = self._controller
        try:
            state = dict(controller.session_list_state() or {})
        except Exception:
            return
        lines: List[str] = []
        tone = ""
        tooltip = ""
        if state.get("error"):
            lines.append("Cached — gateway unreachable")
            tone = "warn"
            tooltip = str(state.get("error"))
        elif state.get("refreshing") and not state.get("fetched_at"):
            lines.append("Loading sessions from the gateway…")
        setter("\n".join(lines), tone=tone, tooltip=tooltip)

    def _switch_to_session(self, session_id: str) -> None:
        target = str(session_id or "").strip()
        if not target:
            return
        current = self._active_session_id()
        if target == current:
            return
        if self._state("_worker") is not None:
            self._set_banner(
                "Wait for the current reply to finish (or stop it) before switching sessions.",
                tone="info",
            )
            return
        try:
            self._controller.switch_session(target)
        except Exception as exc:
            self._set_banner(f"Could not switch session: {exc}", tone="error")
            self._refresh_session_picker(select_session_id=current or None)
            return
        self._tray_completion_unread = False
        self._refresh_tray_feedback()
        self._set_history_status()
        self._set_status("Ready")
        self.refresh_history(request=self._history_scroll_request(mode="bottom"))
        self._sync_session_from_gateway()

    def _sessions_more(self) -> bool:
        """The gateway has more sessions than the list shows ("Load more")."""
        try:
            return bool(dict(self._controller.session_list_state() or {}).get("more"))
        except Exception:
            return False

    def _sync_session_from_gateway(self) -> None:
        """Replace the session on screen with the gateway's history.

        The cached transcript is painted first (instant, and all there is
        offline); this asks the gateway off the GUI thread and redraws only if
        the history differs. One at a time. Offline it changes nothing and
        says nothing — unless the cached copy was unreadable, which is shown.
        (The `_attachment_backfill_*` names predate this: the sync replaced the
        attachment backfill and keeps its same-session redraw guard.)
        """
        if bool(self._state("_attachment_backfill_running", False)):
            # Switching sessions with an unreachable gateway must not leave a
            # thread per switch waiting on a socket.
            return
        self._attachment_backfill_running = True
        # The redraw it may trigger belongs to THIS session: a switch while the
        # call was in flight must not rebuild (or re-render) the new one.
        started_for = self._active_session_id()
        self._attachment_backfill_session = started_for
        controller = self._controller

        def _work() -> None:
            result: Dict[str, Any] = {}
            try:
                before = str(controller.last_run_id() or "").strip()
                result = dict(controller.sync_session_from_gateway() or {})
                after = str(controller.last_run_id() or "").strip()
            except Exception:
                before = after = ""
            finally:
                self._attachment_backfill_running = False
            try:
                if result.get("error"):
                    self.session_sync_failed.emit(str(result["error"]))
                if result.get("changed"):
                    self.session_attachments_restored.emit(1)
                    if after and after != before:
                        # The cache did not know this session's latest run (it
                        # was rebuilt from the gateway): a run still waiting on
                        # the user must be reattached like at launch.
                        candidate = controller.probe_reattach_candidate()
                        if candidate:
                            self.reattach_candidate.emit(candidate)
                now = str(getattr(controller, "active_session_id", "") or "").strip()
                if now and now != started_for:
                    # The user switched while this ran, and that switch's own
                    # sync was skipped (one at a time): sync the session on
                    # screen now.
                    self.session_sync_again.emit()
            except Exception:
                return  # the palette was destroyed meanwhile

        try:
            threading.Thread(
                target=_work, name="session-sync", daemon=True
            ).start()
        except Exception:
            self._attachment_backfill_running = False

    def _on_session_sync_failed(self, message: str) -> None:
        if str(message or "").strip():
            self._set_banner(str(message), tone="error", key="session")

    def _load_more_sessions(self) -> None:
        """The switcher's "Load more sessions" row."""
        self._refresh_sessions_from_gateway(more=True)

    def _refresh_sessions_from_gateway(self, more: bool = False) -> None:
        """Fetch the session list from the gateway, off the GUI thread
        (``more``: one more page of sessions)."""
        if bool(self._state("_sessions_refresh_running", False)):
            return
        self._sessions_refresh_running = True
        controller = self._controller

        def _work() -> None:
            result: Dict[str, Any] = {}
            try:
                result = dict((controller.load_more_sessions() if more else controller.refresh_sessions()) or {})
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            finally:
                self._sessions_refresh_running = False
            try:
                self.sessions_refreshed.emit(result)
            except Exception:
                return  # the palette is gone (quit mid-refresh)

        try:
            threading.Thread(target=_work, name="session-list", daemon=True).start()
        except Exception:
            self._sessions_refresh_running = False

    def _on_sessions_refreshed(self, _result: Any) -> None:
        self._invalidate_session_digests()
        self._refresh_session_picker()
        self._refresh_open_session_switcher()

    def _on_session_attachments_restored(self, _count: int) -> None:
        started_for = str(self._state("_attachment_backfill_session", "") or "")
        if started_for and started_for != self._active_session_id():
            return
        self.refresh_history()

    def _rename_session(self, session_id: str, title: str) -> None:
        try:
            self._controller.rename_session(session_id, title)
        except Exception as exc:
            self._set_banner(f"Could not rename the session: {exc}", tone="error")
            return
        self._session_digests = []
        self._warm_session_digests()
        self._refresh_session_picker()
        self._refresh_open_session_switcher()

    def _state(self, name: str, default: Any = None) -> Any:
        """Instance state that tolerates a palette built via ``__new__`` (tests):
        ``getattr`` with a default raises on such QObjects."""
        return getattr(self, "__dict__", {}).get(name, default)

    def _set_status(self, text: str, tone: str = "neutral") -> None:
        """Header status: the title label shows what the app is doing.

        Idle ("Ready") restores the app name; anything else replaces it with the
        status text, toned busy / info / warn / error / voice. Kept as state too
        for callers and tests that read `_status_text` / `_status_tone`.
        """
        self._status_text = str(text or "").strip() or "Ready"
        self._status_tone = str(tone or "neutral").strip() or "neutral"
        label = getattr(self, "__dict__", {}).get("title_label")
        if label is None:
            return
        idle = self._status_text.lower() in {"ready", ""}
        try:
            text = "AbstractAssistant" if idle else self._status_text
            try:
                metrics = QFontMetrics(label.font())
                budget = int(label.width()) - 2 if int(label.width()) > 40 else 160
                if idle and metrics.horizontalAdvance(text) > budget:
                    # Never show a chopped brand: fall back to the short name.
                    text = "Assistant"
                text = metrics.elidedText(text, Qt.ElideRight, max(40, budget))
            except Exception:
                pass
            label.setText(text)
            label.setToolTip("" if idle else self._status_text)
            label.setProperty("tone", "idle" if idle else self._status_tone)
            self._refresh_widget_style(label)
        except RuntimeError:
            pass

    def _on_escape(self) -> None:
        """Esc: stop speech if the assistant is talking, otherwise hide."""
        try:
            voice = self._controller.voice_manager
            if voice.is_speaking() or voice.is_paused():
                voice.stop_speaking()
                self._voice_after_stop_speaking()
                return
        except Exception:
            pass
        self.hide()

    def _set_history_status(
        self,
        text: str = "",
        *,
        tone: str = "neutral",
        rich: bool = False,
        tooltip: Optional[str] = None,
        badge_tone: str = "",
    ) -> None:
        message = str(text or "").strip()
        if not message:
            self._active_tool_history_status = None
            self._history_status_text = ""
            self._set_thinking_status("")
            self.chat_status_label.clear()
            self.chat_status_label.hide()
            return
        self._history_status_text = message
        if tone == "busy" and self._show_thinking_indicator():
            # Run observability lives in the thinking badge at the transcript
            # tail — plain text only, activity-toned (thinking/tool/waiting).
            # Rich tool statuses carry their plain form in the tooltip.
            if not rich:
                self._active_tool_history_status = None
            plain = str(tooltip or "").strip() if rich else message
            resolved_tone = badge_tone or "thinking"
            # When the run has an activity model, its header copy wins: it
            # names the current step the same way the step rows do
            # ("Running read_file(path=…)", "Needs your approval · …").
            model = self._state("_activity_model")
            if model is not None and hasattr(model, "header_text"):
                try:
                    header = str(model.header_text() or "").strip()
                    if header and header != "Running…":
                        plain = header
                        resolved_tone = str(model.header_tone() or resolved_tone)
                except Exception:
                    pass
            self._set_thinking_status(
                plain or message,
                tooltip=str(tooltip or plain or message),
                tone=resolved_tone,
            )
            self.chat_status_label.clear()
            self.chat_status_label.hide()
            return
        self._set_thinking_status("")
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

    def _history_status_showing(self) -> bool:
        return bool(str(self._history_status_text or "").strip())

    def _set_thinking_status(self, text: str, tooltip: str = "", tone: str = "") -> None:
        display = str(text or "").strip()
        self._thinking_status_text = display
        self._thinking_status_tooltip = str(tooltip or display)
        if tone:
            self._thinking_status_tone = str(tone)
        card = self._thinking_card
        if card is not None:
            try:
                card.set_status(
                    display,
                    tooltip=self._thinking_status_tooltip,
                    tone=self._thinking_status_tone,
                )
            except RuntimeError:
                # The card was torn down by a history rebuild mid-update.
                self._thinking_card = None

    def _feed_activity(self, payload: Dict[str, Any]) -> None:
        """Fold a worker event into the run's activity model and refresh the
        in-transcript card (step rows, elapsed) — the legacy status strings
        keep flowing through `_set_history_status` for the header line."""
        model = self._state("_activity_model")
        if model is None:
            return
        try:
            if not getattr(model, "run_id", "") and str(payload.get("run_id") or "").strip():
                model.run_id = str(payload.get("run_id") or "").strip()
            changed = model.apply_event(payload)
        except Exception:
            return
        card = self._state("_thinking_card")
        if card is None:
            return
        try:
            card.refresh(changed)
        except RuntimeError:
            self._thinking_card = None
        except Exception:
            pass
        dialog = self._state("_activity_dialog")
        if dialog is not None and changed:
            try:
                if dialog.isVisible() and hasattr(model, "to_log_entries"):
                    dialog.set_entries(model.to_log_entries())
            except RuntimeError:
                self._activity_dialog = None

    def _note_activity(self, kind: str, text: str = "", **kwargs: Any) -> None:
        model = self._state("_activity_model")
        if model is None:
            return
        try:
            model.note_local(kind, text, **kwargs)
        except Exception:
            return
        card = self._state("_thinking_card")
        if card is not None:
            try:
                card.refresh()
            except Exception:
                pass

    def _finish_activity(self, status: str) -> None:
        model = self._state("_activity_model")
        if model is None:
            return
        try:
            model.finish(status)
        except Exception:
            pass
        history = self._state("_activity_by_run")
        if history is None:
            history = {}
            self._activity_by_run = history
        key = str(getattr(model, "run_id", "") or f"run-{len(history) + 1}")
        history[key] = model
        while len(history) > 20:
            history.pop(next(iter(history)))

    def _append_run_activity(self, entry: Dict[str, Any]) -> None:
        """Record a live run-activity entry and stream it into the open view."""
        if not isinstance(entry, dict):
            return
        log = self._run_activity_log
        if log is None:
            log = []
            self._run_activity_log = log
        entry = dict(entry)
        entry.setdefault("ts", "")
        log.append(entry)
        if len(log) > 500:
            del log[: len(log) - 500]
        dialog = self._activity_dialog
        # While a run has an activity model the dialog is fed from the model
        # (`_feed_activity` → `to_log_entries`); appending here too would
        # show every line twice.
        if dialog is not None and dialog.isVisible() and self._state("_activity_model") is None:
            try:
                dialog.append_entry(entry)
            except RuntimeError:
                self._activity_dialog = None

    def _clear_run_activity(self) -> None:
        self._run_activity_log = []
        dialog = self._activity_dialog
        if dialog is not None and dialog.isVisible():
            try:
                dialog.set_entries([])
            except RuntimeError:
                self._activity_dialog = None

    def _open_run_activity(self) -> None:
        dialog = self._activity_dialog
        if dialog is None:
            dialog = RunActivityDialog(renderer=self._renderer, parent=self)
            self._activity_dialog = dialog
        model = self._state("_activity_model")
        entries: List[Dict[str, Any]] = []
        if model is not None and hasattr(model, "to_log_entries"):
            try:
                entries = list(model.to_log_entries())
            except Exception:
                entries = []
        dialog.set_entries(entries or list(self._run_activity_log or []))
        self._show_aux_dialog(dialog)

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
        badge_tone: str = "tool",
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
            badge_tone=badge_tone,
        )
        if remember:
            self._active_tool_history_status = {
                "name": str(name or "tool"),
                "arguments": arguments,
                "prefix": str(prefix or ""),
                "tone": str(tone or "busy"),
                "badge_tone": str(badge_tone or "tool"),
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
            badge_tone=str(payload.get("badge_tone") or "tool"),
            remember=False,
        )

    # The banner stylesheet styles tone="warn"; callers have long passed
    # "warning" (the voice/mute/volume warnings all do), which matches NO rule
    # and rendered every warning as an ordinary blue notice. Normalize here so
    # a warning LOOKS like one wherever it is raised.
    _BANNER_TONE_ALIASES = {"warning": "warn", "caution": "warn", "err": "error"}

    def _set_banner(self, text: str = "", tone: str = "info", *, key: str = "") -> None:
        """Show one notice above the transcript.

        ``key`` names the notice's source ("workflow", "speech", …) so a source
        can clear ITS OWN notice with ``_clear_banner(key)`` without wiping a
        notice another source just raised (the bootstrap used to clear an
        error banner the instant it finished).
        """
        message = str(text or "").strip()
        if not message:
            self._banner_key = ""
            self.banner_label.clear()
            self.banner_label.setMinimumHeight(0)
            self.banner_label.setMaximumHeight(0)
            self.banner_label.hide()
            return
        resolved = str(tone or "info").strip().lower()
        resolved = self._BANNER_TONE_ALIASES.get(resolved, resolved)
        self._banner_key = str(key or "")
        self.banner_label.setText(message)
        self.banner_label.setProperty("tone", resolved)
        self.banner_label.setMinimumHeight(0)
        self.banner_label.setMaximumHeight(16777215)
        self._refresh_widget_style(self.banner_label)
        self.banner_label.show()

    def _note_user_wait(self, *, wait_key: str, kind: str, label: str) -> None:
        """Record that a run is parked on the user until they answer."""
        key = str(wait_key or "").strip()
        if not key:
            return
        waits = self._state("_pending_user_waits") or {}
        waits = dict(waits)
        waits[key] = {"kind": str(kind or "approval"), "label": str(label or "")}
        self._pending_user_waits = waits
        self._refresh_wait_notice()

    def _clear_user_wait(self, wait_key: str = "") -> None:
        """Answered (or the run ended): drop the wait, or all of them."""
        waits = dict(self._state("_pending_user_waits") or {})
        if not waits:
            return
        key = str(wait_key or "").strip()
        if key:
            waits.pop(key, None)
        else:
            waits.clear()
        self._pending_user_waits = waits
        self._refresh_wait_notice()

    def _refresh_wait_notice(self) -> None:
        """Raise or clear the "needs you" notice, and repaint the tray."""
        waits = self._state("_pending_user_waits") or {}
        if waits:
            first = next(iter(waits.values()))
            label = str(first.get("label") or "").strip()
            what = (
                "waiting for your input"
                if str(first.get("kind")) == "ask"
                else "waiting for you to approve a tool"
            )
            extra = f" ({len(waits)} pending)" if len(waits) > 1 else ""
            detail = f" — {label}" if label else ""
            self._set_banner(
                f"The assistant is {what}{detail}{extra}.", tone="attention", key="wait"
            )
        else:
            self._clear_banner("wait")
        self._refresh_tray_feedback()

    def _clear_banner(self, key: str) -> None:
        """Clear the banner only if ``key`` raised it."""
        if str(self._state("_banner_key", "") or "") == str(key or ""):
            self._set_banner("")
            # A transient notice (a speech device, a warning) may sit on top of
            # the "needs you" one; when it goes, the wait is still true, so say
            # it again rather than leaving the run silently parked.
            if str(key or "") != "wait" and self._state("_pending_user_waits"):
                self._refresh_wait_notice()

    def attach_tray(self, tray: QSystemTrayIcon) -> None:
        self._tray = tray
        self._refresh_tray_feedback()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.hide()
        event.ignore()

    def _settings_family_dialogs(self) -> List[QDialog]:
        """The secondary windows that follow the palette off screen.

        Settings and the tool editor are CONFIGURATION: they belong to the
        palette and are meaningless floating alone over another app. The rest
        of `_aux_dialogs()` deliberately does NOT follow — an approval sheet or
        an ask dialog is a run PARKED ON THE USER, and hiding one is how a run
        sat 15m52s in silence (2026-09-07). Those stay until they are answered.
        """
        state = getattr(self, "__dict__", {})
        out: List[QDialog] = []
        for key in ("_settings_dialog", "_tool_settings_dialog"):
            dialog = state.get(key)
            if dialog is not None and dialog not in out:
                out.append(dialog)
        return out

    def hideEvent(self, event) -> None:  # noqa: N802
        # Every path that hides the palette hides these with it — the focus
        # rule in `_hide_if_inactive`, the tray toggle, Esc, closeEvent —
        # rather than one of them, so Settings cannot be left behind.
        super().hideEvent(event)
        timer = self._state("_automations_timer")
        if timer is not None:
            timer.setInterval(AUTOMATIONS_POLL_HIDDEN_MS)
        for dialog in self._settings_family_dialogs():
            try:
                # A Settings window the user is TYPING IN keeps itself alive:
                # `_hide_if_inactive` already declines to hide the palette
                # while an aux dialog is active, so reaching here with an
                # active Settings means some other path hid the palette out
                # from under it. Vanishing mid-edit would be worse than the
                # orphan window this follows the palette to avoid.
                if dialog.isVisible() and not dialog.isActiveWindow():
                    dialog.hide()
            except RuntimeError:
                continue  # Dialog already destroyed.

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        timer = self._state("_automations_timer")
        if timer is not None:
            timer.setInterval(AUTOMATIONS_POLL_VISIBLE_MS)
            QTimer.singleShot(0, self._poll_automations)
        QTimer.singleShot(0, self._sync_native_traffic_lights)
        QTimer.singleShot(0, self._restore_deferred_history_scroll_on_show)
        self._request_connection_status_refresh()
        # Reopening the window must show a run that is still parked on the
        # user, whatever notice happened to be on screen when it was hidden.
        if self._state("_pending_user_waits"):
            QTimer.singleShot(0, self._refresh_wait_notice)
        # Re-prompt a wait the user deferred (ask-user "Keep waiting", or the
        # approval sheet's "Decide later").
        deferred = self._state("_deferred_ask_payload")
        if isinstance(deferred, dict):
            self._deferred_ask_payload = None
            if self._state("_worker") is not None:
                QTimer.singleShot(
                    250, lambda payload=dict(deferred): self._open_ask_dialog(payload, reraise=True)
                )
        deferred_tools = self._state("_deferred_tool_request")
        if isinstance(deferred_tools, dict) and self._state("_worker") is not None:
            self._deferred_tool_request = None
            QTimer.singleShot(
                250,
                lambda request=dict(deferred_tools): self._open_approval_sheet(
                    tool_calls=list(request.get("tool_calls") or []),
                    run_id=str(request.get("run_id") or ""),
                    wait_key=str(request.get("wait_key") or ""),
                ),
            )

    def resizeEvent(self, event) -> None:  # noqa: N802
        preserve_request = None
        if not bool(getattr(self, "_history_refreshing", False)):
            preserve_request = self._capture_history_scroll_request()
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_visible_history_cards)
        QTimer.singleShot(0, self._sync_native_traffic_lights)
        QTimer.singleShot(0, self._refresh_active_tool_history_status_for_width)
        # Re-elide the header status and the chat name to their new widths.
        QTimer.singleShot(0, lambda: self._set_status(self._status_text, self._status_tone))
        QTimer.singleShot(0, self._elide_session_button)
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
        # Hand back the meter callback: it holds a bound signal of this window,
        # and the audio thread must not emit into a deleted QObject.
        manager = getattr(self._state("_controller"), "voice_manager", None)
        setter = getattr(manager, "set_audio_meter_callback", None)
        if callable(setter):
            try:
                setter(None)
            except Exception:
                pass
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

    def _aux_dialogs(self) -> List[QDialog]:
        """Every secondary window the palette owns (settings, tools, run log,
        tool/file details, approval sheet…). Activating one must not hide the
        palette — and with it, the child window the user just clicked."""
        state = getattr(self, "__dict__", {})
        seen: List[QDialog] = []
        for key in ("_settings_dialog", "_tool_settings_dialog", "_activity_dialog", "_approval_sheet"):
            dialog = state.get(key)
            if dialog is not None and dialog not in seen:
                seen.append(dialog)
        for dialog in list(state.get("_aux_dialog_registry") or []):
            if dialog is not None and dialog not in seen:
                seen.append(dialog)
        return seen

    def _hide_if_inactive(self) -> None:
        if not self.isVisible() or self.isActiveWindow():
            return
        if self._transient_modal_open:
            return
        active_modal = QApplication.activeModalWidget()
        if active_modal is not None and active_modal.isVisible():
            return
        if bool(self._state("_voice_conversation_active", False)):
            # A hands-free conversation is a control surface; keep it on screen.
            return
        for dialog in self._aux_dialogs():
            try:
                if dialog.isVisible() and dialog.isActiveWindow():
                    return
            except RuntimeError:
                continue
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

    def _screen_edge_gap(self, screen_geom) -> int:
        """The saved screen-edge gap, clamped only so a window still fits:
        never more than a quarter of the screen's smaller side."""
        try:
            pref_gap = max(0, int(self._controller.preferences.bottom_offset))
        except Exception:
            pref_gap = 0
        limit = max(0, min(int(screen_geom.width()), int(screen_geom.height())) // 4)
        return min(pref_gap, limit)

    def position_near_tray(self) -> None:
        screen_geom = self._available_screen_geometry()
        if screen_geom is None:
            return
        # The "Screen edge gap" preference, honoured as saved (0 = flush);
        # the clamp below keeps the window on screen whatever it is.
        gap = self._screen_edge_gap(screen_geom)
        right_gap = gap
        top_gap = gap
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

    def _reflow_shell(self, *, reposition: bool = False) -> None:
        """Lay the three cards out for the current size.

        ``reposition`` moves the window back to its tray anchor; every other
        caller (history refreshes, composer growth) re-sizes in place so the
        palette does not jump while the user is reading.
        """
        screen_geom = self._available_screen_geometry()
        if screen_geom is None:
            return
        prefs = self._controller.preferences
        # The preferred size is honored up to a screen fraction: the transcript
        # is the point of the window, so it gets whatever height is left after
        # the header and composer instead of a fixed 132–164 px band.
        # The only limit on the saved width is the screen (62% of it).
        normal_width = min(
            max(int(prefs.window_width), 420), max(420, int(screen_geom.width() * 0.62))
        )
        normal_height = min(
            max(int(prefs.window_height), 320),
            max(320, min(880, int(screen_geom.height() * 0.82))),
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
        # Chips re-wrap when the shell width changes, so the tray height must be
        # recomputed before the composer height is read into the layout maths.
        if self.attachments_tray.isVisible():
            self._sync_attachment_tray_height()
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
        history_height = max(
            132,
            int(
                expanded_height
                - top_gap
                - bottom_gap
                - header_height
                - composer_height
                - (card_gap * 2)
            ),
        )
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
        previous = self.geometry()
        self.resize(width, target_height)
        if reposition or not bool(self._state("_shell_positioned", False)):
            self.position_near_tray()
            self._shell_positioned = True
        else:
            # Grow/shrink in place, anchored to the top-right corner so a
            # taller composer never pushes the window off the screen edge.
            try:
                right = previous.x() + previous.width()
                x, y = self._clamp_window_to_screen(
                    x=right - width,
                    y=previous.y(),
                    width=width,
                    height=target_height,
                    screen_geom=screen_geom,
                )
                self.move(x, y)
            except Exception:
                pass
        QTimer.singleShot(0, self._sync_native_traffic_lights)

    def _toggle_zoom(self) -> None:
        self._zoomed = not bool(self._zoomed)
        self._reflow_shell(reposition=True)

    def show_palette(self) -> None:
        self._tray_completion_unread = False
        self._refresh_tray_feedback()
        self._reflow_shell(reposition=True)
        self.show()
        self.raise_()
        self.activateWindow()
        self.prompt_edit.setFocus()

    def _surface_for_prompt(self, *, title: str, message: str) -> None:
        """Bring the palette to the front + tray-notify before opening a modal.

        A run can reach a tool-approval or ask-user wait while the palette is
        hidden or behind other windows; without this the modal opens unfocused
        and the user never sees the run is blocked on them.
        """
        try:
            visible = bool(self.isVisible()) and not bool(self.isMinimized())
            active = bool(self.isActiveWindow())
        except Exception:
            visible = False
            active = False
        # Already frontmost: don't steal focus or fire a notification for a
        # prompt the user is looking at.
        if visible and active:
            return
        if not visible:
            try:
                self.show_palette()
            except Exception:
                pass
        else:
            try:
                self.raise_()
                self.activateWindow()
            except Exception:
                pass
        # macOS: pull the whole app forward so the modal is not stuck behind
        # another space/app.
        try:
            import AppKit  # type: ignore

            app = AppKit.NSApp() or AppKit.NSApplication.sharedApplication()
            if app is not None:
                app.activateIgnoringOtherApps_(True)
        except Exception:
            pass
        self._notify(title, message)

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
        # One repaint for the whole rebuild, not one per card: on the
        # translucent frameless window a half-built transcript (old cards still
        # scheduled for deletion, new ones already added) is what showed two
        # sessions drawn over each other after a switch.
        scroll = state.get("history_scroll")
        if scroll is not None:
            scroll.setUpdatesEnabled(False)
        try:
            while self.history_layout.count():
                item = self.history_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    # Hide + unparent BEFORE deleteLater: a card that is only
                    # scheduled for deletion is still a visible child of
                    # history_host and keeps painting under the new transcript
                    # until the event loop gets round to deleting it.
                    widget.hide()
                    widget.setParent(None)
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
            self._live_cards = {}
            for reply in list((self._state("_live_replies") or {}).values()):
                if reply.content or reply.reasoning:
                    self.history_layout.addWidget(
                        self._build_live_card(reply, viewport_width)
                    )
            has_live = bool(self._live_cards)
            if not visible_messages and not has_live and not self._show_thinking_indicator():
                self.history_layout.addWidget(self._build_history_empty_state())
            self._thinking_card = None
            if self._show_thinking_indicator():
                thinking_card = ThinkingIndicatorCard(
                    status_text=self._thinking_status_text,
                    tooltip=self._thinking_status_tooltip,
                    tone=self._thinking_status_tone,
                )
                thinking_card.sync_to_viewport_width(viewport_width)
                thinking_card.activated.connect(self._open_run_activity)
                self._wire_activity_card(thinking_card)
                self._thinking_card = thinking_card
                self.history_layout.addWidget(thinking_card)
            else:
                self._thinking_status_text = ""
                self._thinking_status_tooltip = ""
                self._thinking_status_tone = "thinking"
            self._sync_history_viewport()
            self._refresh_session_picker(
                select_session_id=self._active_session_id() or None
            )
            self._reflow_shell()
        finally:
            self._history_refreshing = False
            if scroll is not None:
                scroll.setUpdatesEnabled(True)
        self._commit_history_scroll_request(scroll_request)

    def _wire_activity_card(self, card: QWidget) -> None:
        """Connect the live activity card's controls and feed it the model."""
        model = self._state("_activity_model")
        try:
            if hasattr(card, "set_model"):
                card.set_model(model)
            for signal_name, handler in (
                ("pause_requested", self._pause_active_run),
                ("resume_requested", self._resume_active_run),
                ("stop_requested", self._cancel_active_run),
                ("log_requested", self._open_run_activity),
                ("review_requested", self._review_wait_step),
            ):
                signal = getattr(card, signal_name, None)
                if signal is not None:
                    signal.connect(handler)
            if hasattr(card, "set_expanded"):
                card.set_expanded(bool(self._state("_zoomed", False)))
            if hasattr(card, "set_paused"):
                card.set_paused(bool(self._state("_run_paused", False)))
        except Exception:
            pass

    def _build_history_empty_state(self) -> QWidget:
        """A centered placeholder shown for a fresh, message-less session.

        Kept compact on purpose: the collapsed palette gives the history
        viewport ~110px, so oversized margins clip the subtitle.
        """
        holder = QWidget()
        holder.setObjectName("historyEmptyState")
        col = QVBoxLayout(holder)
        col.setContentsMargins(16, 12, 16, 12)
        col.setSpacing(5)
        col.addStretch(1)
        icon = QLabel()
        icon.setPixmap(_symbol_icon("spark", color="#8fa1b5", size=22).pixmap(22, 22))
        icon.setAlignment(Qt.AlignCenter)
        col.addWidget(icon, 0, Qt.AlignCenter)
        title = QLabel("Ask anything")
        title.setObjectName("historyEmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        col.addWidget(title, 0, Qt.AlignCenter)
        sub = QLabel("Type, drop files, or use the mic to dictate · ⌘⇧V talks")
        sub.setObjectName("historyEmptySubtitle")
        sub.setAlignment(Qt.AlignCenter)
        # No word wrap: Qt's wrap heuristic folds this line even with room to
        # spare, and the folded second line is what got clipped in short
        # viewports. One line fits every supported palette width (>= 420px).
        sub.setWordWrap(False)
        col.addWidget(sub, 0, Qt.AlignCenter)
        col.addStretch(1)
        return holder

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
            # Asynchronous text browser reflow safety timers. Guarded: a bare
            # lambda over `bar` raised into Qt (which aborts the process) when
            # the palette was torn down within the 150 ms.
            QTimer.singleShot(50, self._pin_history_bottom)
            QTimer.singleShot(150, self._pin_history_bottom)
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
            self.composer_card.setFixedHeight(_COMPOSER_BASE_HEIGHT + self._composer_extra_height())
            self._reflow_shell()
            return
        if self._attachments:
            for path in self._attachments:
                chip = AttachmentIconChip(path=path, parent=self.attachments_host)
                chip.remove_requested.connect(self._remove_attachment)
                self.attachments_layout.addWidget(chip)
        else:
            hint = QLabel("Drop files to attach")
            hint.setObjectName("attachmentsDropHint")
            self.attachments_layout.addWidget(hint)
        self.attachments_tray.show()
        self._sync_attachment_tray_height()
        self._reflow_shell()

    def _attachment_tray_width(self) -> int:
        """Usable chip width in the tray, tolerating a not-yet-laid-out view.

        Sources are probed lazily and defensively: during the first render the
        viewport has no width yet, and each fallback may itself be unbuilt.
        """
        sources = (
            lambda: self.attachments_tray.viewport().width(),
            lambda: self.attachments_tray.width(),
            lambda: self.composer_card.width(),
            lambda: self.width(),
        )
        for source in sources:
            try:
                candidate = int(source() or 0)
            except Exception:
                continue
            if candidate > 40:
                return candidate
        return 360

    def _composer_extra_height(self) -> int:
        """Height of the optional composer rows (voice strip) above the prompt."""
        strip = getattr(self, "__dict__", {}).get("voice_strip")
        try:
            return VOICE_STRIP_HEIGHT if strip is not None and strip.isVisible() else 0
        except RuntimeError:
            return 0

    def _sync_attachment_tray_height(self) -> None:
        """Grow the tray (and composer) to fit wrapped chip rows, then scroll."""
        rows = self.attachments_layout.rows_for_width(self._attachment_tray_width())
        height = _attachment_tray_height(rows)
        self.attachments_tray.setFixedHeight(height)
        self.composer_card.setFixedHeight(_COMPOSER_BASE_HEIGHT + height + self._composer_extra_height())

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
            button.setIcon(_symbol_icon("stop", color="#fff1f1", size=19))
            button.setToolTip(
                "Stop this run (⌘.) — typed text steers it instead (right-click: pause/resume)"
            )
            button.setEnabled(True)
        else:
            button.setIcon(_symbol_icon("send", color="#f8fffc", size=21))
            button.setToolTip("Send message")
        # Stop is a danger-toned button so it never reads as "go".
        button.setProperty("busy", "true" if busy else "false")
        self._refresh_widget_style(button)

    def _cancel_active_run(self) -> None:
        """Stop the in-flight run: cancel server-side and interrupt the follower."""
        worker = self._state("_worker")
        if worker is None:
            # Nothing is running (⌘. on an idle palette): never cancel the
            # previous run or flash "Stopping…".
            return
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
        # The step row lands first so the header copy derived from the model
        # ("Stopping…") never lags behind the row.
        self._note_activity("stop", "")
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
        self._note_activity("steer", guidance)
        self._set_status("Steering the run…", tone="busy")
        self._set_history_status(f"Steering: {preview}", tone="busy")
        return True

    def _pause_active_run(self) -> None:
        run_id = str(self._controller.last_run_id() or "").strip()
        if run_id and self._controller.pause_run(run_id):
            self._run_paused = True
            self._note_activity("pause", "")
            self._set_status("Pausing…", tone="busy")
            self._set_history_status(
                "Pause requested — takes effect at the next step boundary", tone="busy", badge_tone="paused"
            )
            card = self._state("_thinking_card")
            if card is not None and hasattr(card, "set_paused"):
                card.set_paused(True)
        elif run_id:
            self._note_activity("pause", "Pause was not accepted by the gateway", tone="danger", status="failed")
            self._set_banner("The gateway did not accept the pause command.", tone="warn")

    def _resume_active_run(self) -> None:
        run_id = str(self._controller.last_run_id() or "").strip()
        if run_id and self._controller.resume_run(run_id):
            self._run_paused = False
            self._note_activity("resume", "")
            self._set_status("Resumed", tone="busy")
            self._set_history_status("Resumed", tone="busy", badge_tone="thinking")
            card = self._state("_thinking_card")
            if card is not None and hasattr(card, "set_paused"):
                card.set_paused(False)

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
        if self.prompt_edit.toPlainText().strip() or self._attachments:
            # Applies to fresh sends, steering and queued sends alike, and
            # cancels synthesis as well as audible/paused playback.
            try:
                self._controller.voice_manager.stop_speaking()
            except Exception:
                pass
            key = str(self._state("_active_spoken_message_key", "") or "")
            self._on_message_speech_finished(key)
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
        self._last_run_status = ""
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt and not self._attachments:
            return
        if bool(getattr(self, "_bootstrapping", False)):
            # Still warming the gateway caches — refuse rather than block the
            # GUI thread on a cold catalog fetch (or race the reconcile).
            self._set_history_status("Connecting to gateway — one moment…", tone="busy")
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
        # Remember the turn so a run that never starts can be withdrawn and
        # the composer refilled (see `run_start_failed`).
        self._pending_user_message_id = str(
            self._controller.append_user_message(prompt, metadata=metadata) or ""
        )
        # This turn may be what finally names the session in the header.
        self._invalidate_session_digests()
        self._pending_submission = {"prompt": prompt, "attachments": list(attachments)}
        self._run_start_failed = False
        conversation = self._state("_voice_conversation")
        if (
            conversation is not None
            and bool(self._state("_voice_conversation_active", False))
            and conversation.state in {"heard", "listening", "speaking", "paused"}
        ):
            # Manual voice mode: the user pressed Return on the transcript.
            # Account for the turn (mic pauses) without sending it twice.
            conversation.mark_sent()

        self._run_busy = True
        self._run_has_final_output = False
        self._tray_completion_unread = False
        self._discard_live_replies()
        self._live_closed_calls = set()
        self._clear_run_activity()
        self._activity_model = RunActivityModel(run_id="", reattached=False)
        self._set_status("Running assistant workflow...", tone="busy")
        self._set_history_status("Running assistant workflow...", tone="busy")
        self._refresh_tray_feedback()
        addenda = [
            str(plan.get("system_prompt_extra") or "").strip(),
            self._voice_system_prompt().strip(),
        ]
        try:
            worker = self._controller.build_chat_worker(
                prompt=prompt,
                attachments=attachments,
                system_prompt_extra="\n\n".join(part for part in addenda if part),
                append_user_message=not append_user_now,
            )
        except Exception as exc:
            self._on_worker_error(str(exc))
            return
        self._worker = worker
        worker.event_emitted.connect(self._on_worker_event)
        worker.error_occurred.connect(self._on_worker_error)
        warning_signal = getattr(worker, "warning_occurred", None)
        if warning_signal is not None:
            warning_signal.connect(self._on_worker_warning)
        worker.finished.connect(self._on_worker_finished)
        worker.start()
        self._set_send_button_busy(True)
        self._note_stream_unsupported_once()

        # Refresh history and scroll to bottom at the very end
        self.refresh_history(request=self._history_scroll_request(mode="bottom"))

    def _on_worker_event(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        typ = str(payload.get("type") or "").strip()
        if typ == ASSISTANT_DELTA:
            self._on_live_delta(payload)
            return
        if typ == ASSISTANT_DELTA_END:
            self._on_live_delta_end(payload)
            return
        if typ == ASSISTANT_DELTA_RESET:
            self._on_live_reset()
            return
        self._feed_activity(payload)
        if typ == "run_start_failed":
            # The gateway refused to start the run (workspace grant out of
            # policy, missing workflow…): withdraw the phantom user turn, put
            # the text back in the composer, and show the gateway's reason.
            detail = str(payload.get("error") or "The gateway did not start the run.").strip()
            pending_id = str(self._state("_pending_user_message_id", "") or "")
            if pending_id:
                try:
                    self._controller.remove_message(pending_id)
                except Exception:
                    pass
                self._pending_user_message_id = ""
            submission = self._state("_pending_submission")
            if isinstance(submission, dict):
                prompt_edit = getattr(self, "prompt_edit", None)
                failed_text = str(submission.get("prompt") or "")
                if prompt_edit is not None and failed_text:
                    typed = prompt_edit.toPlainText()
                    # Never drop what the user typed meanwhile: the failed
                    # turn goes back in front of it.
                    prompt_edit.setPlainText(f"{failed_text}\n{typed}" if typed.strip() else failed_text)
                    prompt_edit.moveCursor(prompt_edit.textCursor().End)
                restored = [str(p) for p in (submission.get("attachments") or []) if str(p)]
                if restored and not self._attachments:
                    self._attachments = restored
                    self._render_attachments()
                self._pending_submission = None
            self._run_busy = False
            self._run_has_final_output = True
            self._run_start_failed = True
            model = self._state("_activity_model")
            if model is not None:
                try:
                    model.apply_event({"type": "error", "error": detail})
                except Exception:
                    pass
            self._finish_activity("failed")
            self._set_send_button_busy(False)
            self._set_status("Not sent", tone="error")
            self._set_history_status()
            self._set_banner(f"Not sent — {detail}", tone="error")
            self._refresh_tray_feedback()
            conversation = self._state("_voice_conversation")
            if conversation is not None:
                conversation.run_failed(detail)
            self.refresh_history(request=self._history_scroll_request(mode="bottom"))
            return
        if typ == "connection":
            state = str(payload.get("state") or "").strip().lower()
            if state == "offline":
                reason = str(payload.get("reason") or "").strip()
                self._set_status("Reconnecting…", tone="warn")
                self._set_history_status(
                    "Gateway unreachable — retrying" + (f" ({reason})" if reason else ""),
                    tone="busy",
                    badge_tone="offline",
                )
            elif state == "online":
                self._set_status("Running…", tone="busy")
                self._set_history_status("Reconnected", tone="busy", badge_tone="thinking")
            return
        if typ == "workspace":
            root = str(payload.get("root") or "").strip()
            if root:
                self._workspace_root_label = root
                self._refresh_workspace_hint()
            return
        if typ == "status":
            status_text = str(payload.get("status") or "Working").strip() or "Working"
            status_lower = status_text.lower()
            if status_lower == "offline":
                # Rendered by the `connection` event; the run is still busy.
                return
            inactive_statuses = {
                "completed",
                "complete",
                "ready",
                "idle",
                "error",
                "failed",
                "cancelled",
            }
            self._run_busy = (
                status_lower not in inactive_statuses and not self._run_has_final_output
            )
            if status_lower in {"cancelled", "failed", "completed"}:
                self._discard_live_replies()
                # What the RUN said it ended as. `_cancel_requested` only
                # knows about a stop THIS process issued, so a run cancelled
                # before a relaunch came back described as "completed".
                self._last_run_status = status_lower
            # Raw gateway status words become header copy ("thinking" → "Thinking…").
            header_copy = {
                "thinking": "Thinking…",
                "running": "Running…",
                "executing": "Running…",
                "waiting": "Waiting for you",
                "completed": "Ready",
                "complete": "Ready",
                "cancelled": "Run stopped",
                "failed": "Failed",
                "error": "Failed",
            }.get(status_lower, status_text)
            self._set_status(header_copy, tone="busy" if self._run_busy else "neutral")
            if self._run_busy:
                if not self._history_status_showing():
                    self._set_history_status(status_text, tone="busy")
            elif status_lower in {"error", "failed", "cancelled"}:
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
            self._set_history_status(
                f"Thinking — cycle {n}", tone="busy", badge_tone="thinking"
            )
            self._append_run_activity({"kind": "cycle", "n": n})
            return
        if typ == "cycle_result":
            # The model's ACTUAL output for the cycle (real thinking, not the
            # prompt echo) — feeds the clickable run-activity view only.
            self._append_run_activity(
                {
                    "kind": "thinking",
                    "n": payload.get("iteration"),
                    "content": str(payload.get("content") or ""),
                    "reasoning": str(payload.get("reasoning") or ""),
                    "ts": str(payload.get("ts") or ""),
                }
            )
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
            self._set_history_status(label, tone="busy", badge_tone="tool")
            self._append_run_activity({"kind": "tools", "tools": tools})
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
        if typ == "attachments_uploaded":
            self._on_attachments_uploaded(payload.get("attachments"))
            return
        if typ == "assistant":
            # The durable message replaces the live text: drop every live
            # card BEFORE the transcript redraws, so the reply never shows
            # twice (the answer may come from the root run while the text
            # streamed from its agent subrun, so run ids do not pair up).
            self._discard_live_replies(close=True)
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
            conversation = self._state("_voice_conversation")
            in_conversation = conversation is not None and bool(
                self._state("_voice_conversation_active", False)
            )
            if is_final and in_conversation:
                spoken = speech_plain_text(str(payload.get("content") or ""))
                will_speak = bool(spoken) and self._controller.supports_tts()
                # Nothing to speak: `_on_worker_finished` reopens the mic once
                # the follower has really closed (no early listening window
                # that would steer the closing run).
                if will_speak:
                    conversation.run_finished(will_speak=True)
                    started = self._controller.voice_manager.speak(
                        spoken, callback=lambda: self.voice_speech_finished.emit()
                    )
                    if not started:
                        conversation.speech_finished()
            elif self.auto_speak.isChecked() and is_final:
                self._controller.voice_manager.speak(
                    speech_plain_text(str(payload.get("content") or ""))
                )
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
                    badge_tone="waiting",
                )
            else:
                self._set_history_status(
                    "Waiting for tool approval", tone="busy", badge_tone="waiting"
                )
            self._append_run_activity(
                {
                    "kind": "waiting",
                    "text": "Tool approval requested"
                    + (
                        f": {_tool_call_summary(tool_calls[0]).name}"
                        if tool_calls
                        else ""
                    ),
                }
            )
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
                model = self._state("_activity_model")
                if model is not None and hasattr(model, "resolve_wait"):
                    try:
                        model.resolve_wait(wait_key, "auto_approved")
                    except Exception:
                        pass
                self._clear_user_wait(wait_key)
                _answer_tool_approval(True)
                return
            self._surface_for_prompt(
                title="Tool approval needed",
                message="The assistant is waiting for you to approve a tool.",
            )
            self._open_approval_sheet(
                tool_calls=tool_calls, run_id=wait_run_id, wait_key=wait_key
            )
            return
        if typ == "ask_user":
            self._open_ask_dialog(payload)
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
            self._set_tool_history_status(
                name=name, arguments=arguments, badge_tone="tool"
            )
            preview = str(message.get("content") or "").strip()
            if len(preview) > 800:
                #[WARNING:TRUNCATION] bounded result preview for the activity view
                preview = preview[:799] + "…"
            self._append_run_activity(
                {
                    "kind": "tool_result",
                    "name": name,
                    "preview": preview,
                    "ts": str(message.get("ts") or ""),
                }
            )
            return

    def _on_worker_error(self, error: str) -> None:
        """Fatal follower error: say why where the user is looking (banner +
        run status), notify only when the palette is hidden, no modal."""
        text = str(error or "Unknown error").strip() or "Unknown error"
        self._discard_live_replies()
        self._run_busy = False
        self._run_has_final_output = True
        self._tray_completion_unread = False
        # Keep the worker reference: the QThread is still winding down and
        # `_submit` must queue (never rebind) until `_on_worker_finished`
        # clears it; marking the run cancelled sends typed text to that queue
        # instead of steering a dead run.
        self._cancel_requested = True
        self._set_send_button_busy(False)
        model = self._state("_activity_model")
        if model is not None:
            try:
                model.apply_event({"type": "error", "error": text})
            except Exception:
                pass
        self._finish_activity("failed")
        self._set_status("Failed", tone="error")
        self._set_history_status(text, tone="error")
        self._set_banner(f"The run failed: {text}", tone="error")
        self._refresh_tray_feedback()
        conversation = self._state("_voice_conversation")
        if conversation is not None:
            conversation.run_failed(text)
        try:
            hidden = not self.isVisible()
        except Exception:
            hidden = False
        if hidden:
            self._notify("Assistant error", text)

    def _on_worker_warning(self, message: str) -> None:
        """Non-fatal follower notice (an answer that did not reach the
        gateway): the run keeps going, the user gets told."""
        text = str(message or "").strip()
        if text:
            self._set_banner(text, tone="warn")

    def _on_worker_finished(self) -> None:
        # A stale `finished` from a worker that was already replaced must not
        # tear down the run that superseded it.
        try:
            sender = self.sender()
        except Exception:
            sender = None
        current = getattr(self, "__dict__", {}).get("_worker")
        if sender is not None and current is not None and current is not sender:
            return
        self._discard_live_replies()
        had_indicator = self._show_thinking_indicator()
        was_stopped = bool(self._cancel_requested)
        start_failed = bool(self._state("_run_start_failed", False))
        self._run_start_failed = False
        self._worker = None
        # The run added turns, tools and tokens: the session's metrics moved.
        self._invalidate_session_digests()
        if not self._active_session_listed_on_gateway():
            # Its first run just made this session a gateway session: fetch
            # the list so the row survives switching away.
            self._refresh_sessions_from_gateway()
        self._run_busy = False
        self._cancel_requested = False
        self._run_paused = False
        self._set_send_button_busy(False)
        self._clear_user_wait()
        if not start_failed:
            # (A model already finished as failed/stopped keeps that status.)
            self._finish_activity("stopped" if was_stopped else "completed")
        conversation = self._state("_voice_conversation")
        if conversation is not None and conversation.state == "thinking":
            # No spoken reply is coming (stopped, or nothing to say): listen again.
            conversation.run_finished(will_speak=False)
        if not self._run_has_final_output:
            # A stopped run legitimately has no final answer — say so instead
            # of the misleading "completed but returned no written reply".
            # The run's OWN terminal status counts too: reattaching after a
            # relaunch to a run that was cancelled in the previous process
            # reported it as completed, because only this process's stop flag
            # was consulted.
            ended_as = str(self._state("_last_run_status", "") or "")
            if was_stopped or ended_as == "cancelled":
                fallback = "Run stopped."
            elif ended_as == "failed":
                fallback = "The run failed before it wrote a reply."
            else:
                fallback = "The workflow completed, but it returned no written reply."
            self._run_has_final_output = True
            self._set_history_status(fallback, tone="info")
        self._refresh_tray_feedback()
        if had_indicator != self._show_thinking_indicator():
            self.refresh_history()
        if not (start_failed or self._state("_status_tone", "") == "error"):
            # "Not sent" / "Failed" stay until the next run replaces them.
            self._set_status("Ready")
        # A send queued during teardown (stop clicked, user typed the next
        # message before the follower closed) fires now.
        if self._pending_submit:
            self._pending_submit = False
            prompt_edit = getattr(self, "prompt_edit", None)
            if prompt_edit is not None and prompt_edit.toPlainText().strip():
                QTimer.singleShot(0, self._submit)

    # ------------------------------------------------------------ live replies

    STREAM_UNSUPPORTED_NOTE = (
        "Stream replies is On, but this gateway does not offer live replies: "
        "answers appear when they are finished."
    )

    def _note_stream_unsupported_once(self) -> None:
        """Once per chat session: say that "On" could not be honoured."""
        try:
            unsupported = bool(self._controller.stream_on_but_unsupported())
        except Exception:
            return
        if not unsupported:
            return
        noted = self._state("_stream_unsupported_noted")
        if noted is None:
            noted = set()
            self._stream_unsupported_noted = noted
        session_id = str(self._active_session_id() or "")
        if session_id in noted:
            return
        noted.add(session_id)
        self._set_banner(self.STREAM_UNSUPPORTED_NOTE, tone="info", key="stream")

    def _on_live_delta(self, payload: Dict[str, Any]) -> None:
        """Fold one live delta into its call's text; repaint on the throttle.

        Every delta updates the model at once (nothing is dropped); only the
        repaint is batched, so a fast stream costs one render per interval.
        """
        call_id = str(payload.get("call_id") or "").strip()
        if not call_id:
            return
        # Never bring live text back once the answer is on screen, nor for a
        # call whose card a durable message already replaced (S-2.2).
        if bool(self._state("_run_has_final_output", False)):
            return
        if call_id in (self._state("_live_closed_calls") or set()):
            return
        replies = self._state("_live_replies")
        if replies is None:
            replies = {}
            self._live_replies = replies
        reply = replies.get(call_id)
        if reply is None:
            # A new model call: the previous call's finished text was an
            # intermediate step (its tools follow in the activity card) and
            # a durable message will carry whatever of it is the answer.
            for other_id, other in list(replies.items()):
                if other.ended:
                    self._drop_live_reply(other_id)
            reply = LiveReply(
                run_id=str(payload.get("run_id") or ""),
                call_id=call_id,
                node_id=str(payload.get("node_id") or ""),
                subagent=bool(payload.get("subagent")),
            )
            replies[call_id] = reply
        if reply.apply_delta(payload):
            self._mark_live_dirty(call_id)

    def _on_live_delta_end(self, payload: Dict[str, Any]) -> None:
        call_id = str(payload.get("call_id") or "").strip()
        reason = str(payload.get("reason") or "failed")
        if reason == "unavailable":
            # The call ran without streaming; say why in one line (S-2.7).
            self._drop_live_reply(call_id)
            self._set_history_status(
                end_reason_text(reason, str(payload.get("detail") or "")), tone="info"
            )
            return
        reply = (self._state("_live_replies") or {}).get(call_id)
        if reply is None:
            # One delta_end arrives per call attempt, streamed or not: an
            # unknown call is normal and has nothing on screen.
            return
        reply.ended = reason
        if reason == "completed":
            self._mark_live_dirty(call_id)
            return
        # Failed/cancelled: the text is not a reply. Remove it and say why.
        # A "reinvoked" cancel is a restart: the re-run streams under a new
        # call id and gets its own card.
        detail = str(payload.get("detail") or "")
        had_card = call_id in (self._state("_live_cards") or {})
        self._drop_live_reply(call_id)
        if had_card or reply.content or reply.reasoning:
            self._set_history_status(end_reason_text(reason, detail), tone="info")

    def _on_live_reset(self) -> None:
        """The run stream (re)connected: drop every live text (S-2.3).

        The models are cleared at once; the cards go on the next flush, so a
        reply whose snapshot arrives within the flush interval keeps its card
        (updated in place) instead of flickering out and back.
        """
        replies = self._state("_live_replies")
        if replies:
            replies.clear()
        for call_id in list((self._state("_live_cards") or {}).keys()):
            self._mark_live_dirty(call_id)

    def _mark_live_dirty(self, call_id: str) -> None:
        dirty = self._state("_live_dirty")
        if dirty is None:
            dirty = set()
            self._live_dirty = dirty
        dirty.add(call_id)
        timer = self._state("_live_flush_timer")
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._flush_live_replies)
            self._live_flush_timer = timer
            self._live_flush_interval_ms = self.LIVE_FLUSH_MIN_MS
        if not timer.isActive():
            timer.start(int(self._state("_live_flush_interval_ms", self.LIVE_FLUSH_MIN_MS)))

    def _history_at_bottom(self) -> bool:
        scroll = self._state("history_scroll")
        bar = scroll.verticalScrollBar() if scroll is not None else None
        if bar is None:
            return True
        return int(bar.value()) >= int(bar.maximum()) - 24

    def _build_live_card(self, reply: LiveReply, viewport_width: int) -> "LiveMessageCard":
        card = LiveMessageCard(
            call_id=reply.call_id,
            run_id=reply.run_id,
            renderer=self._renderer,
            bubble_width=_message_bubble_width(viewport_width, role="assistant"),
            caption=subagent_caption(reply.node_id) if reply.subagent else "",
        )
        card.set_live_text(content=reply.content, reasoning=reply.reasoning, truncated=reply.truncated)
        if reply.ended:
            card.set_ended(reply.ended)
        cards = self._state("_live_cards")
        if cards is None:
            cards = {}
            self._live_cards = cards
        cards[reply.call_id] = card
        return card

    def _flush_live_replies(self) -> None:
        """Repaint the live cards changed since the last flush.

        The interval adapts to the render cost (3x the last flush, 40 ms
        minimum) so a long reply re-rendered as markdown cannot starve the
        event loop; the text itself is never cut.
        """
        dirty = self._state("_live_dirty") or set()
        self._live_dirty = set()
        replies = self._state("_live_replies") or {}
        for call_id in [c for c in dirty if c not in replies]:
            # Dropped by a reconnect and not re-sent: that reply has ended.
            self._drop_live_reply(call_id)
        if not dirty or not replies:
            return
        follow = self._history_at_bottom()
        started = time.monotonic()
        cards = self._state("_live_cards")
        if cards is None:
            cards = {}
            self._live_cards = cards
        viewport_width = int(self.history_scroll.viewport().width() or self.width())
        changed = False
        for call_id in list(dirty):
            reply = replies.get(call_id)
            if reply is None or not (reply.content or reply.reasoning):
                continue
            card = cards.get(call_id)
            try:
                if card is None:
                    card = self._build_live_card(reply, viewport_width)
                    anchor = self._state("_thinking_card")
                    index = self.history_layout.indexOf(anchor) if anchor is not None else -1
                    if index >= 0:
                        self.history_layout.insertWidget(index, card)
                    else:
                        self.history_layout.addWidget(card)
                    self._remove_history_empty_state()
                else:
                    card.set_live_text(
                        content=reply.content, reasoning=reply.reasoning, truncated=reply.truncated
                    )
                    if reply.ended:
                        card.set_ended(reply.ended)
                changed = True
            except RuntimeError:
                # The card was deleted under us by a history rebuild; the
                # rebuild re-created it from the same state.
                cards.pop(call_id, None)
        if changed:
            self._sync_history_viewport()
            if follow:
                # Pin now and once more after the text browser reflows. Not
                # `_apply_history_scroll_request`: its timers capture the
                # scrollbar and would fire into a deleted widget if the window
                # goes away mid-stream (a slot that raises aborts Qt).
                self._pin_history_bottom()
                QTimer.singleShot(60, self._pin_history_bottom)
        elapsed_ms = (time.monotonic() - started) * 1000.0
        self._live_flush_interval_ms = max(self.LIVE_FLUSH_MIN_MS, min(1000, int(elapsed_ms * 3)))

    def _pin_history_bottom(self) -> None:
        try:
            bar = self.history_scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
        except (RuntimeError, AttributeError):
            return  # the palette was torn down

    def _remove_history_empty_state(self) -> None:
        for index in range(self.history_layout.count() - 1, -1, -1):
            item = self.history_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None and widget.objectName() == "historyEmptyState":
                self.history_layout.takeAt(index)
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _drop_live_reply(self, call_id: str) -> None:
        replies = self._state("_live_replies")
        if replies is not None:
            replies.pop(call_id, None)
        dirty = self._state("_live_dirty")
        if dirty is not None:
            dirty.discard(call_id)
        cards = self._state("_live_cards")
        card = cards.pop(call_id, None) if cards is not None else None
        if card is None:
            return
        try:
            self.history_layout.removeWidget(card)
            card.hide()
            card.setParent(None)
            card.deleteLater()
        except RuntimeError:
            return
        self._sync_history_viewport()

    def _discard_live_replies(self, *, close: bool = False) -> None:
        """Drop every live card (a durable message replaced them, or the run
        ended). ``close`` also remembers the calls so a late delta for one of
        them cannot recreate its card."""
        if close:
            closed = self._state("_live_closed_calls")
            if closed is None:
                closed = set()
                self._live_closed_calls = closed
            closed.update((self._state("_live_replies") or {}).keys())
            closed.update((self._state("_live_cards") or {}).keys())
        for call_id in list((self._state("_live_replies") or {}).keys()):
            self._drop_live_reply(call_id)
        for call_id in list((self._state("_live_cards") or {}).keys()):
            self._drop_live_reply(call_id)

    def _on_user_message_appended(self, _content: str = "") -> None:
        self.refresh_history(request=self._history_scroll_request(mode="bottom"))

    def _on_attachments_uploaded(self, attachments: Any) -> None:
        """Record the gateway's durable ids on the turn already on screen.

        The message is written the instant the user sends (so the transcript
        never lags), which is before the upload has returned an artifact id.
        Storing the id now is what lets the preview outlive the local file —
        macOS deletes screenshots dragged out of its screenshot UI.
        """
        items = [item for item in (attachments or []) if isinstance(item, dict)]
        message_id = str(self._state("_pending_user_message_id", "") or "")
        if not items or not message_id:
            return
        if self._controller.merge_message_metadata(
            message_id, {"attachments": items, "media": items}
        ):
            self.refresh_history()

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
        self,
        artifact: Dict[str, Any],
        message: Dict[str, Any],
        *,
        tile_size: int = 0,
        compact: bool = False,
    ) -> Optional[QWidget]:
        if not isinstance(artifact, dict):
            return None
        # A compact chip carries its own type glyph, so every attachment gets
        # one — a PDF next to a screenshot reads as the same kind of thing.
        if not compact and _artifact_media_kind(artifact) not in {
            "image",
            "audio",
            "video",
        }:
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
            artifact=artifact,
            resolve_path=_resolve,
            tile_size=tile_size,
            compact=compact,
            parent=self,
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
        # Speak prose, not markup: raw markdown reads as noise ("hash hash…")
        # and its heading/list blocks defeat streaming segmentation — the
        # first audio segment swallowed a whole header block live (2026-07-28).
        raw_content = str(message.get("content") or "")
        content = speech_plain_text(raw_content)
        if not content:
            # A reply can be all image/code/emoji: the sanitizer legitimately
            # reduces it to nothing. Returning here used to make the speaker
            # button a no-op with no explanation whatsoever.
            self._set_message_voice_card_state(key, "idle")
            self._set_banner(
                "Nothing to read aloud: this reply has no spoken text once "
                "images, code and links are removed.",
                tone="warning",
            )
            return
        self._active_spoken_message_key = key
        self._active_spoken_message_phase = "synthesizing"
        self._set_message_voice_card_state(key, "synthesizing")
        # The voice manager reports concrete refusals through on_speech_error;
        # the generic banner below is only for a manager that never did.
        self._voice_failure_seen = False
        started = voice.speak(
            content, callback=lambda key=key: self.message_speech_finished.emit(key)
        )
        if started:
            self._active_spoken_message_key = key
        else:
            self._active_spoken_message_key = ""
            self._active_spoken_message_phase = "idle"
            self._set_message_voice_card_state(key, "idle")
            # A silent no-op looked like "voice is broken" with no clue why
            # (2026-07-28). Refusals must say so where the user is looking.
            if not self._voice_failure_seen:
                self._set_banner(
                    "Voice couldn't start: gateway speech is unavailable or still "
                    "reconnecting. Try again in a few seconds, or check Settings.",
                    tone="warning",
                )

    def _on_message_speech_failed(self, reason: str) -> None:
        """Show WHY speech did not play, where the user is looking.

        Before this, every failure after speak() returned True was reported
        only via `warnings.warn`: the live 2026-08-02 reproduction of the
        operator's "Garden in the Log" click spent four minutes on rejected
        pins and two 120 s timeouts, emitted three such warnings, and the only
        thing the UI did was flip the card back to idle."""
        text = str(reason or "").strip()
        self._voice_failure_seen = True
        # The failing message's card must not stay stuck on "synthesizing" —
        # unless a NEWER speak is already live (a late report from the run the
        # newer one superseded must not reset the newer card).
        live = False
        try:
            voice = self._controller.voice_manager
            live = bool(voice.is_speaking() or voice.is_paused())
        except Exception:
            live = False
        if not live:
            key = str(self._active_spoken_message_key or "").strip()
            if key:
                self._set_message_voice_card_state(key, "idle")
            self._active_spoken_message_key = ""
            self._active_spoken_message_phase = "idle"
        self._set_banner(
            f"Voice failed: {text}." if text else "Voice failed for an unknown reason.",
            tone="warning",
        )
        # A failed reply must never wedge the hands-free loop: listen again.
        conversation = self._state("_voice_conversation")
        if conversation is not None and conversation.state == "speaking":
            conversation.speech_finished()

    def _on_message_speech_finished(self, key: str) -> None:
        if str(self._state("_active_spoken_message_key", "") or "") == str(key or ""):
            self._active_spoken_message_key = ""
            self._active_spoken_message_phase = "idle"
        self._set_message_voice_card_state(str(key or ""), "idle")
        # Clear the "Speaking on …" banner (and only that banner — another
        # notice shown meanwhile must survive).
        try:
            self._clear_banner("speech")
        except Exception:
            pass

    def _emit_message_speech_started(self) -> None:
        key = str(self._active_spoken_message_key or "").strip()
        if key:
            self.message_speech_started.emit(key)

    def _on_voice_speech_activity(self) -> None:
        """The player started or stopped. Runs on the audio thread."""
        self._emit_message_speech_started()
        self.speech_activity_changed.emit()

    def _on_message_speech_started(self, key: str) -> None:
        if str(self._active_spoken_message_key or "") != str(key or ""):
            return
        self._active_spoken_message_phase = "speaking"
        self._set_message_voice_card_state(str(key or ""), "speaking")
        # Say WHERE the audio is going and HOW LOUD the system output is:
        # playback follows the system default output, so a headset/AR-glasses
        # sink or a near-zero output volume makes correct playback
        # indistinguishable from a hang (2026-07-28: three-way audit cleared
        # every software layer; the machine's output volume was 6/100).
        device = ""
        volume = None
        muted = None
        try:
            device = str(self._controller.voice_manager.output_device_label() or "").strip()
            volume, muted = self._controller.voice_manager.output_volume_state()
        except Exception:
            device = ""
        if not device:
            return
        text = f"Speaking on \u201c{device}\u201d"
        tone = "info"
        if muted is True:
            text += " — the system output is MUTED; unmute to hear it."
            tone = "warning"
        elif isinstance(volume, int) and volume < 15:
            text += f" — the system output volume is {volume}%; raise it to hear anything."
            tone = "warning"
        elif isinstance(volume, int):
            text += f" (volume {volume}%)."
        else:
            text += " — if you can't hear it, check the Mac's sound output."
        self._set_banner(text, tone=tone, key="speech")

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
        conversation = self._state("_voice_conversation")
        if conversation is not None and bool(self._state("_voice_conversation_active", False)):
            conversation.heard(text)
            if not conversation.auto_send:
                self._append_prompt_text(text)
                self.voice_strip.set_state("listening", "Added to your message — press Return to send")
            return
        self._append_prompt_text(text)

    def _append_prompt_text(self, text: str) -> None:
        current = self.prompt_edit.toPlainText().strip()
        combined = f"{current} {text}".strip() if current else text
        self.prompt_edit.setPlainText(combined)
        self.prompt_edit.moveCursor(self.prompt_edit.textCursor().End)

    # ------------------------------------------------------------ voice conversation

    def _voice_conversation_unavailable_reason(self) -> str:
        controller = self._controller
        try:
            if not controller.supports_stt():
                return "Voice conversation needs gateway speech-to-text and a microphone (pip install \"abstractassistant[voice]\")."
            if not controller.supports_tts():
                return "Voice conversation needs gateway text-to-speech and a local audio output."
        except Exception as exc:
            return f"Voice conversation is unavailable: {exc}"
        return ""

    def _toggle_voice_conversation(self) -> None:
        if bool(self._state("_voice_conversation_active", False)):
            self._end_voice_conversation()
        else:
            self._start_voice_conversation()

    def _start_voice_conversation(self) -> None:
        reason = self._voice_conversation_unavailable_reason()
        if reason:
            self.conversation_button.setChecked(False)
            self._set_banner(reason, tone="warn")
            return
        if self._listening:
            # Push-to-dictate and the conversation share the microphone.
            self._toggle_listening()
        prefs = self._controller.preferences
        conversation = VoiceConversation(
            voice_manager=self._controller.voice_manager,
            on_send=self._voice_send,
            on_state=self._on_voice_state,
            on_level=self.speech_level_received.emit,
            schedule=lambda delay, fn: QTimer.singleShot(int(delay * 1000), fn),
            auto_send=bool(getattr(prefs, "voice_auto_send", True)),
            voice_mode=str(getattr(prefs, "voice_mode", "wait") or "wait"),
        )
        self._voice_conversation = conversation
        self._voice_conversation_active = True
        self._auto_speak_before_voice = bool(self.auto_speak.isChecked())
        self.conversation_button.setChecked(True)
        self.conversation_button.setToolTip("End the voice conversation (⌘⇧V)")
        self.mic_button.setEnabled(False)
        self.mic_button.setToolTip("Dictation is off during a voice conversation")
        self.voice_strip.show()
        self._sync_composer_height()
        started = conversation.start(
            listen_kwargs={
                "on_transcription": lambda text: self.transcription_received.emit(str(text or "")),
                "on_stop": lambda: self.listening_stopped.emit(),
                "on_audio_level": lambda level: self.voice_level_received.emit(float(level or 0.0)),
            }
        )
        if not started:
            detail = conversation.error or "the microphone did not start"
            self._set_banner(
                f"Microphone unavailable: {detail}. macOS: System Settings → Privacy & Security → Microphone.",
                tone="error",
            )
            self._end_voice_conversation(keep_error=True)

    def _end_voice_conversation(self, *, keep_error: bool = False) -> None:
        conversation = self._state("_voice_conversation")
        self._voice_conversation_active = False
        self._voice_conversation = None
        if conversation is not None:
            # Always close the microphone and any speech, error or not — the
            # loop is detached first so its final state change cannot
            # re-enter this teardown.
            error_text = str(getattr(conversation, "error", "") or "") if conversation.state == "error" else ""
            try:
                conversation.detach()
            except Exception:
                pass
            try:
                conversation.stop(reason=error_text if keep_error else "")
            except Exception:
                pass
        restore = self._state("_auto_speak_before_voice")
        if restore is not None:
            self.auto_speak.setChecked(bool(restore))
            self._auto_speak_before_voice = None
        self.conversation_button.setChecked(False)
        self.conversation_button.setToolTip("Start a voice conversation (⌘⇧V)")
        self.voice_strip.set_state("off")
        self.voice_strip.hide()
        self._sync_composer_height()
        # `conversation.stop()` drops the voice manager's meter callback; take
        # it back so the tray still shows later speech.
        self._install_speech_meter()
        self._refresh_capability_state()
        if self._status_tone not in {"error", "busy"}:
            self._set_status("Ready")

    def _sync_composer_height(self) -> None:
        if self.attachments_tray.isVisible():
            self._sync_attachment_tray_height()
        else:
            self.composer_card.setFixedHeight(_COMPOSER_BASE_HEIGHT + self._composer_extra_height())
        self._reflow_shell()

    def _voice_send(self, text: str) -> None:
        """The conversation decided an utterance is a turn: send it like typed text."""
        conversation = self._state("_voice_conversation")
        worker = self._state("_worker")
        alive = False
        if worker is not None:
            try:
                alive = bool(worker.isRunning())
            except Exception:
                alive = False
        if alive:
            # The previous run is still closing: hold the turn for the next
            # listening window instead of steering a finished run with it.
            if conversation is not None:
                conversation.requeue(text)
            return
        self.prompt_edit.setPlainText(str(text or ""))
        self._submit()
        if conversation is not None and self._state("_worker") is None:
            # The send was refused (still connecting, nothing runnable…):
            # listen again rather than sit in "thinking" forever.
            conversation.run_failed("send refused")

    def _on_voice_state(self, state: str) -> None:
        conversation = self._state("_voice_conversation")
        strip = getattr(self, "__dict__", {}).get("voice_strip")
        if strip is None:
            return
        text = ""
        if state == "heard" and conversation is not None:
            preview = conversation.last_transcript
            text = f"Heard: “{preview[:60]}{'…' if len(preview) > 60 else ''}”"
        elif state == "speaking" and conversation is not None and conversation.voice_mode == "full":
            text = "Speaking… say “stop” or press Esc"
        elif state == "error" and conversation is not None and conversation.error:
            text = f"Voice conversation stopped: {conversation.error}"
        strip.set_state(state, text)
        status_map = {
            "starting": ("Starting microphone…", "busy"),
            "listening": ("Listening", "voice"),
            "heard": ("Heard you", "voice"),
            "thinking": ("Thinking…", "busy"),
            "speaking": ("Speaking", "voice"),
            "paused": ("Microphone paused", "info"),
            "error": ("Voice stopped", "error"),
        }
        if state in status_map:
            self._set_status(*status_map[state])
        elif state == "off":
            self._set_status("Ready")
        if state == "error" and conversation is not None:
            self._set_banner(f"Voice conversation stopped: {conversation.error}", tone="error")
            self._end_voice_conversation(keep_error=True)

    def _on_voice_level(self, level: float) -> None:
        strip = getattr(self, "__dict__", {}).get("voice_strip")
        if strip is None or not strip.isVisible():
            return
        now = time.monotonic()
        if now - float(self._state("_voice_level_last_emit", 0.0) or 0.0) < 0.04:
            return
        self._voice_level_last_emit = now
        strip.set_level(level)

    def _voice_pause_toggled(self) -> None:
        conversation = self._state("_voice_conversation")
        if conversation is None:
            return
        if conversation.state == "paused":
            conversation.resume()
        else:
            conversation.pause()

    def _voice_stop_speaking(self) -> None:
        try:
            self._controller.voice_manager.stop_speaking()
        except Exception:
            pass
        self._voice_after_stop_speaking()

    def _voice_after_stop_speaking(self) -> None:
        """A deliberate stop skips the speak callback: move the loop on now."""
        conversation = self._state("_voice_conversation")
        if (
            conversation is not None
            and bool(self._state("_voice_conversation_active", False))
            and conversation.state == "speaking"
        ):
            conversation.speech_finished()

    def _on_voice_speech_finished(self) -> None:
        conversation = self._state("_voice_conversation")
        if conversation is not None and bool(self._state("_voice_conversation_active", False)):
            conversation.speech_finished()

    def _voice_system_prompt(self) -> str:
        """Spoken-style guidance while a conversation runs (a run-time addendum,
        never persisted; the controller re-attaches the workflow persona)."""
        if not bool(self._state("_voice_conversation_active", False)):
            return ""
        prefs = self._controller.preferences
        if not bool(getattr(prefs, "voice_spoken_replies", True)):
            return ""
        return VOICE_CONVERSATION_SYSTEM_PROMPT

    def _refresh_workspace_hint(self) -> None:
        """Say where the run's files go (session picker tooltip)."""
        picker = getattr(self, "__dict__", {}).get("session_picker")
        if picker is None:
            return
        try:
            status = self._controller.workspace_root_status()
        except Exception:
            status = {"root": str(self._state("_workspace_root_label", "") or ""), "source": "session"}
        root = str(status.get("root") or "").strip()
        source = str(status.get("source") or "gateway")
        if not root:
            hint = "Switch chat\nFiles: the gateway picks a fresh folder for each run (choose one in Settings → Workspace)."
        elif source == "local":
            hint = f"Switch chat\nFiles go to your folder: {root}"
        else:
            hint = f"Switch chat\nFiles for this chat live in the gateway folder: {root}"
        picker.setToolTip(hint)

    def _on_listen_stop(self) -> None:
        """The recognizer heard the spoken "stop" phrase.

        The recognizer itself keeps capturing after its stop callback, so the
        mic must be closed here — otherwise the indicator shows "off" while the
        microphone is still recording and uploading to the gateway.
        """
        conversation = self._state("_voice_conversation")
        if conversation is not None and bool(self._state("_voice_conversation_active", False)):
            # In a conversation the spoken "stop" only interrupts the reply
            # (the voice manager already stopped playback); keep listening.
            conversation.speech_finished()
            return
        try:
            self._controller.voice_manager.stop_listening()
        except Exception:
            pass
        self._listening = False
        self.mic_button.setChecked(False)
        self.mic_button.setToolTip("Dictate into the message")
        self._set_status("Ready")

    def _refresh_workflows(self) -> None:
        options = self._controller.workflow_options()
        current = self._controller.current_workflow() if options else None
        status = self._controller.workflow_status()
        if options and current is None and status.error:
            # The workflow chosen in Settings left the catalog: say so, and
            # where to fix it, rather than a disabled Send with no reason.
            self._set_banner(str(status.error), tone="error", key="workflow")
            self._set_status("Pick a workflow in Settings", tone="error")
        elif status.error and not options:
            detail = str(status.error or "").strip()
            message = detail
            detail_lower = detail.lower()
            if "workflow" in detail_lower or "catalog" in detail_lower:
                message = "Assistant unavailable right now. Open Settings to review the gateway connection."
            # A failed console sign-in explains the missing catalog better
            # than the generic message; keep it until the user acts.
            if str(self._state("_banner_key", "") or "") != "handover":
                self._set_banner(message, tone="error", key="workflow")
            self._set_status("Gateway attention required", tone="error")
        else:
            self._clear_banner("workflow")
        self._refresh_submission_state()
        self._reflow_shell()

    def _create_session(self) -> None:
        if self._state("_worker") is not None:
            self._set_banner(
                "A run is still in progress — stop it (⌘.) or wait for it before starting a new chat.",
                tone="warn",
            )
            return
        self._controller.create_session()
        self._refresh_workflows()
        self.refresh_history()

    def _open_tool_settings(self) -> None:
        """Tools & permissions is a page of Settings now."""
        self._open_settings(section="tools")

    def _open_settings(self, section: str = "") -> None:
        controller = self._controller
        warm = getattr(controller, "settings_caches_warm", None)
        warmer = getattr(controller, "warm_settings_caches", None)
        if callable(warm) and callable(warmer) and not bool(self._state("_settings_warming", False)):
            try:
                ready = bool(warm())
            except Exception:
                ready = True
            if not ready:
                # First open (or stale caches): fetch the workspace policy,
                # tool inventory, routes and model card on a thread, then
                # build the pages — never HTTP on the GUI thread.
                self._settings_warming = True
                try:
                    if not bool(self._state("_settings_ready_wired", False)):
                        self.settings_ready.connect(self._show_settings)
                        self._settings_ready_wired = True
                except Exception:
                    self._settings_warming = False
                    self._show_settings(section)
                    return
                self._set_status("Opening settings…", tone="busy")

                def _warm() -> None:
                    try:
                        warmer()
                    finally:
                        self.settings_ready.emit(str(section or ""))

                threading.Thread(target=_warm, name="settings-warmup", daemon=True).start()
                return
        self._show_settings(section)

    def _show_settings(self, section: str = "") -> None:
        self._settings_warming = False
        if self._state("_status_text", "") == "Opening settings…":
            self._set_status("Ready")
        if self._settings_dialog is None:
            dialog = SettingsDialog(
                controller=self._controller,
                apply_hotkey=self._apply_hotkey,
                parent=self,
            )
            dialog.settings_saved.connect(self._on_settings_saved)
            # Settings re-measures itself AFTER it is placed (its stylesheet is
            # re-applied a turn after show, then `_refit` sets a new fixed
            # size), and a window grows from its top-left corner — a wider fit
            # pushed its right side past the screen edge. Pull it back inside.
            dialog.fitted.connect(lambda d=dialog: self._place_aux_dialog(d, anchor=False))
            self._settings_dialog = dialog
        else:
            self._settings_dialog.refresh()
        if section:
            self._settings_dialog.show_section(section)
        self._show_aux_dialog(self._settings_dialog)

    def _register_aux_dialog(self, dialog: QDialog) -> None:
        registry = self._state("_aux_dialog_registry")
        if registry is None:
            registry = []
            self._aux_dialog_registry = registry
        registry[:] = [d for d in registry if d is not None and d is not dialog]
        registry.append(dialog)
        # Re-apply the window's own stylesheet once it is on screen. A dialog
        # parented to the palette resolves its style against the ancestor
        # chain, and Qt caches that resolution before the dialog's own sheet
        # is in play: the sheet is set, the string is correct, and every child
        # still renders UNSTYLED (a white QLineEdit on a dark dialog) until it
        # is applied a second time. This was invisible while the palette's
        # stylesheet leaked in and styled those widgets instead.
        restyle = getattr(dialog, "restyle", None)
        if callable(restyle):
            QTimer.singleShot(0, restyle)

    # ------------------------------------------------------------ waits (modeless)

    def _pause_voice_for_dialog(self) -> None:
        """A question or approval is on screen: stop transcribing side talk."""
        conversation = self._state("_voice_conversation")
        if conversation is not None and conversation.state in {"listening", "heard"}:
            if conversation.pause():
                self._voice_paused_for_dialog = True

    def _resume_voice_after_dialog(self) -> None:
        conversation = self._state("_voice_conversation")
        if conversation is not None and bool(self._state("_voice_paused_for_dialog", False)):
            self._voice_paused_for_dialog = False
            conversation.resume()

    def _open_approval_sheet(self, *, tool_calls: List[Dict[str, Any]], run_id: str, wait_key: str) -> None:
        """Show (or queue into) the modeless approval sheet for one wait."""
        risks: Dict[str, Dict[str, Any]] = {}
        try:
            risks = self._controller.tool_inventory_by_name()
        except Exception:
            risks = {}
        sheet = self._state("_approval_sheet")
        try:
            alive = sheet is not None and sheet.isVisible()
        except RuntimeError:
            alive = False
        label = _tool_call_summary(tool_calls[0]).name if tool_calls else ""
        self._note_user_wait(wait_key=wait_key, kind="approval", label=label)
        if alive and hasattr(sheet, "enqueue"):
            sheet.enqueue(list(tool_calls or []), run_id=run_id, wait_key=wait_key, risks=risks)
            return
        sheet = ToolApprovalDialog(
            tool_calls=list(tool_calls or []),
            risks=risks,
            run_id=run_id,
            wait_key=wait_key,
            parent=self,
        )
        self._approval_sheet = sheet
        self._register_aux_dialog(sheet)
        sheet.decided.connect(self._on_tool_decision)
        stop_signal = getattr(sheet, "stop_requested", None)
        if stop_signal is not None:
            stop_signal.connect(self._cancel_active_run)
        self._pause_voice_for_dialog()
        self._place_sheet(sheet)
        sheet.show()
        sheet.raise_()
        sheet.activateWindow()

    def _place_sheet(self, sheet: QDialog) -> None:
        """Center a sheet over the palette when visible, else near the tray."""
        try:
            if self.isVisible():
                geom = self.frameGeometry()
                size = sheet.size()
                if not size.isValid() or size.width() < 200 or size.height() < 120:
                    size = sheet.sizeHint()
                x = geom.x() + max(0, (geom.width() - size.width()) // 2)
                y = geom.y() + max(0, (geom.height() - size.height()) // 3)
                screen_geom = self._available_screen_geometry()
                if screen_geom is not None:
                    x, y = self._clamp_window_to_screen(
                        x=x, y=y, width=size.width(), height=size.height(), screen_geom=screen_geom
                    )
                sheet.move(x, y)
                return
        except Exception:
            pass
        try:
            self._show_aux_dialog(sheet)
        except Exception:
            pass

    def _on_tool_decision(self, decision: str, info: Any) -> None:
        details = dict(info) if isinstance(info, dict) else {}
        run_id = str(details.get("run_id") or "").strip()
        wait_key = str(details.get("wait_key") or "").strip()
        tool_calls = details.get("tool_calls") if isinstance(details.get("tool_calls"), list) else []
        for name in details.get("remember") or []:
            try:
                self._controller.save_tool_preference(str(name), "approve")
            except Exception:
                pass
        model = self._state("_activity_model")
        first = _tool_call_summary(tool_calls[0]).name if tool_calls else "tool"
        if decision == "defer":
            # The run stays parked; the question comes back when the palette is
            # shown again or from the activity card's Review link.
            self._deferred_tool_request = {
                "type": "tool_request",
                "tool_calls": tool_calls,
                "run_id": run_id,
                "wait_key": wait_key,
            }
            if model is not None:
                model.resolve_wait(wait_key, "deferred")
            self._set_history_status(
                f"Needs your approval · {first} — decide later from the activity card",
                tone="busy",
                badge_tone="waiting",
            )
            self._resume_voice_after_dialog()
            return
        self._deferred_tool_request = None
        # Answered (approved or denied) — the run is no longer parked on the
        # user. "defer" returned above on purpose: it stays pending.
        self._clear_user_wait(wait_key)
        approved = decision in {"once", "session"}
        if decision == "session":
            rank = int(details.get("trust_rank") or 0) or None
            self._controller.grant_session_tool_auto_approval(max_rank=rank)
            if rank and rank >= 3:
                message = (
                    "Trusting enabled tools in this chat, including ones that reach outside or destroy. "
                    "Disabled tools stay disabled; gateway limits still apply."
                )
            else:
                message = (
                    "Trusting enabled tools in this chat. Calls that reach outside or destroy will still ask; "
                    "disabled tools stay disabled and gateway limits still apply."
                )
            self._set_banner(message, tone="info", key="trust")
        worker = self._state("_worker")
        if worker is not None:
            try:
                if run_id and wait_key:
                    worker.provide_tool_approval(approved, run_id=run_id, wait_key=wait_key)
                else:
                    worker.provide_tool_approval(approved)
            except Exception as exc:
                self._set_banner(f"Could not send your decision: {exc}", tone="error")
        else:
            self._set_banner(
                "The run is no longer being followed; reopen the palette to reattach and answer again.",
                tone="warn",
            )
        if model is not None:
            model.resolve_wait(
                wait_key,
                "approved_session" if decision == "session" else ("approved" if approved else "denied"),
            )
        if approved:
            self._set_history_status(f"Approved · {first}", tone="busy", badge_tone="tool")
        else:
            self._set_history_status(f"Denied · {first}", tone="busy", badge_tone="thinking")
        self._resume_voice_after_dialog()

    def _on_ask_decision(self, dialog: Any, payload: Dict[str, Any]) -> None:
        decision = str(getattr(dialog, "decision", "defer") or "defer")
        prompt = str(payload.get("prompt") or "Input required").strip()
        short_prompt = prompt if len(prompt) <= 120 else f"{prompt[:117].rstrip()}..."
        wait_run_id = str(payload.get("run_id") or "").strip()
        wait_key = str(payload.get("wait_key") or "").strip()
        model = self._state("_activity_model")
        if self._state("_ask_dialog") is dialog:
            self._ask_dialog = None
        if decision == "defer":
            self._deferred_ask_payload = dict(payload)
            if model is not None:
                model.resolve_wait(wait_key, "dismissed")
            self._set_history_status(
                f"Waiting for your input (dismissed): {short_prompt}",
                tone="busy",
                badge_tone="waiting",
            )
            self._resume_voice_after_dialog()
            return
        response = str(getattr(dialog, "answer", "") or "") if decision == "send" else ""
        self._deferred_ask_payload = None
        worker = self._state("_worker")
        if worker is not None:
            if wait_run_id and wait_key:
                worker.provide_user_response(str(response or ""), run_id=wait_run_id, wait_key=wait_key)
            else:
                worker.provide_user_response(str(response or ""))
        if model is not None:
            model.resolve_wait(wait_key, "answered")
        self._set_history_status("Answer sent — the run continues", tone="busy", badge_tone="thinking")
        self._resume_voice_after_dialog()

    def _review_wait_step(self, step_id: str) -> None:
        """The activity card's Review/Answer link: re-raise a deferred wait."""
        model = self._state("_activity_model")
        step = model.step(step_id) if model is not None and hasattr(model, "step") else None
        payload = dict(getattr(step, "payload", {}) or {}) if step is not None else {}
        kind = str(getattr(step, "kind", "") or "")
        if kind == "wait_approval" or self._state("_deferred_tool_request"):
            request = self._state("_deferred_tool_request") or {
                "tool_calls": payload.get("tool_calls") or [],
                "run_id": payload.get("run_id") or "",
                "wait_key": payload.get("wait_key") or "",
            }
            self._open_approval_sheet(
                tool_calls=list(request.get("tool_calls") or []),
                run_id=str(request.get("run_id") or ""),
                wait_key=str(request.get("wait_key") or ""),
            )
            return
        deferred = self._state("_deferred_ask_payload")
        if isinstance(deferred, dict):
            self._deferred_ask_payload = None
            self._open_ask_dialog(dict(deferred), reraise=True)

    def _open_ask_dialog(self, payload: Dict[str, Any], *, reraise: bool = False) -> None:
        """Show the modeless question dialog for an ask-user wait. The first
        raise and every re-raise of a deferred question come through here."""
        payload = dict(payload or {})
        prompt = str(payload.get("prompt") or "Input required").strip()
        short_prompt = prompt if len(prompt) <= 120 else f"{prompt[:117].rstrip()}..."
        existing = self._state("_ask_dialog")
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return
            except RuntimeError:
                self._ask_dialog = None
        self._set_history_status(
            f"Waiting for your input: {short_prompt}",
            tone="busy",
            badge_tone="waiting",
        )
        self._note_user_wait(
            wait_key=str(payload.get("wait_key") or "").strip() or "ask",
            kind="ask",
            label=short_prompt,
        )
        if not reraise:
            self._append_run_activity(
                {"kind": "waiting", "text": f"Asked for your input: {short_prompt}"}
            )
        self._surface_for_prompt(
            title="Question",
            message=short_prompt or "The assistant is waiting for your input.",
        )
        renderer = self._state("_renderer")
        dialog = AskUserDialog(
            prompt=prompt,
            render_html=(
                (lambda text: _assistant_html(renderer, text))
                if renderer is not None
                else None
            ),
            parent=self,
        )
        # Modeless like the approval sheet: the palette stays usable (stop,
        # steer, read) while the question is open; the answer arrives via
        # `finished`. No nested event loop.
        self._ask_dialog = dialog
        self._register_aux_dialog(dialog)
        dialog.finished.connect(
            lambda _result, d=dialog, p=dict(payload): self._on_ask_decision(d, p)
        )
        self._pause_voice_for_dialog()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _place_aux_dialog(self, dialog: QDialog, *, anchor: bool = True) -> None:
        """Keep a secondary window fully on screen, the edge gap clear.

        ``anchor`` puts it top-right (first show and re-show); without it the
        window keeps its position and is only pulled back inside (after a
        resize). A window larger than the screen's available area minus the
        gap is shrunk to fit — a fixed-size one (Settings) gets a new fixed
        size; its pages scroll vertically.
        """
        if bool(getattr(dialog, "_aux_placing", False)):
            return
        try:
            screen_geom = self._available_screen_geometry()
            if screen_geom is None:
                return
            dialog._aux_placing = True
            # frameGeometry() is the window INCLUDING its title bar; size() is
            # the client area. Use the larger of the two so a frame Qt has not
            # measured yet cannot under-report.
            frame = dialog.frameGeometry()
            width = max(int(frame.width()), int(dialog.width()))
            height = max(int(frame.height()), int(dialog.height()))
            chrome_w = max(0, width - int(dialog.width()))
            chrome_h = max(0, height - int(dialog.height()))
            gap = self._screen_edge_gap(screen_geom)
            if anchor:
                x = int(screen_geom.x() + screen_geom.width() - width - gap)
                y = int(screen_geom.y() + gap)
            else:
                x, y = int(frame.x()), int(frame.y())
            x, y, fit_w, fit_h = _fit_window_rect(
                x=x, y=y, width=width, height=height, area=screen_geom, gap=gap
            )
            if (fit_w, fit_h) != (width, height):
                client_w = max(1, fit_w - chrome_w)
                client_h = max(1, fit_h - chrome_h)
                if dialog.minimumSize() == dialog.maximumSize():
                    dialog.setFixedSize(client_w, client_h)
                else:
                    dialog.setMinimumSize(
                        min(int(dialog.minimumWidth()), client_w),
                        min(int(dialog.minimumHeight()), client_h),
                    )
                    dialog.resize(client_w, client_h)
            if (int(frame.x()), int(frame.y())) != (x, y):
                dialog.move(x, y)
        except Exception:
            pass
        finally:
            try:
                dialog._aux_placing = False
            except Exception:
                pass

    def _show_aux_dialog(self, dialog: QDialog) -> None:
        self._register_aux_dialog(dialog)
        # NOT adjustSize(): a dialog that computes its own fit (Settings) gets
        # shrunk to a stale layout hint here and then grows again on show,
        # which is exactly the mismatch this placement has to survive.
        dialog.show()
        self._place_aux_dialog(dialog)
        # Place again once the window manager has laid the frame out. On the
        # first open the real size is only known after this turn of the event
        # loop, so the immediate pass above is just there to avoid a flash at
        # the previous position.
        QTimer.singleShot(0, lambda: self._place_aux_dialog(dialog))
        dialog.raise_()
        dialog.activateWindow()

    def _on_settings_saved(self) -> None:
        if self._state("_auto_speak_before_voice") is None:
            self.auto_speak.setChecked(bool(self._controller.preferences.auto_speak))
        self._refresh_capability_state()
        self._refresh_workflows()
        self._request_connection_status_refresh()
        self._refresh_submission_state()
        # Size limits may have changed; the window stays where the user put it.
        self._reflow_shell(reposition=False)

    def _on_tool_settings_saved(self) -> None:
        self._set_status("Tool defaults updated", tone="info")

    def _persist_auto_speak(self) -> None:
        # A partial update: rebuilding the whole preferences object here used
        # to drop every field it did not name (the model/voice overrides).
        checked = bool(self.auto_speak.isChecked())
        if bool(self._state("_voice_conversation_active", False)):
            # Auto-speak is forced on while a conversation runs; toggling it is
            # the user's way of saying "stop the conversation", and the new
            # choice is what survives it.
            self._auto_speak_before_voice = checked
            self._end_voice_conversation()
        self._controller.update_preferences(auto_speak=checked)

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
        in_conversation = bool(self._state("_voice_conversation_active", False))
        self.auto_speak.setEnabled(tts_available)
        self.auto_speak.setToolTip(
            "Speak replies aloud" if tts_available else "Gateway voice output is not configured."
        )
        self.mic_button.setEnabled(stt_available and not in_conversation)
        self.mic_button.setToolTip(
            "Dictation is off during a voice conversation"
            if in_conversation
            else ("Dictate into the message" if stt_available else "Gateway speech input is not configured.")
        )
        conversation_button = getattr(self, "__dict__", {}).get("conversation_button")
        if conversation_button is not None:
            reason = self._voice_conversation_unavailable_reason()
            conversation_button.setEnabled(not reason or in_conversation)
            conversation_button.setToolTip(
                "End the voice conversation (⌘⇧V)"
                if in_conversation
                else (reason or "Start a voice conversation (⌘⇧V)")
            )
        self._update_prompt_placeholder()
        self._refresh_submission_state()
        self._refresh_workspace_hint()

    def _update_prompt_placeholder(self) -> None:
        self.prompt_edit.setPlaceholderText("Ask anything, drop files, or press ⌘⇧V to talk")

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

    def _voice_is_speaking(self) -> bool:
        """Is the player putting audio on the speakers right now?

        Asked of the player, never tracked as a flag. 0.4.10 polled this too,
        and for good reason: speech ends in more ways than it starts — stopped,
        superseded, paused, failed, quit — and a flag has to be cleared in
        every one of them. Paused counts as not speaking, so a pause hands the
        icon back and resuming takes it again.
        """
        manager = getattr(self._state("_controller"), "voice_manager", None)
        try:
            return bool(manager is not None and manager.is_speaking())
        except Exception:
            return False

    def _tray_feedback_state(self) -> str:
        # Speaking wins: it is the only state the user can hear, and the icon
        # is what tells them where the voice is coming from.
        if self._voice_is_speaking():
            return "speaking"
        # A run parked on the user outranks "working": working resolves itself,
        # this one cannot until the user answers it.
        if self._state("_pending_user_waits"):
            return "waiting"
        if self._show_thinking_indicator():
            return "busy"
        if self._tray_completion_unread:
            return "complete"
        return "idle"

    def _decayed_speech_meter(self, *, now: Optional[float] = None) -> Any:
        """The last meter, faded toward silence by how old it is.

        Levels arrive per audio chunk, not per frame, and stop arriving the
        moment playback stalls or ends — without decay the bars would freeze
        at whatever the last chunk happened to be.
        """
        level = self._state("_speech_meter", 0.0)
        stamp = float(self._state("_speech_meter_ts", 0.0) or 0.0)
        if stamp <= 0.0:
            return 0.0
        elapsed = max(0.0, (time.monotonic() if now is None else float(now)) - stamp)
        if elapsed >= _TRAY_VOICE_DECAY_S:
            return 0.0
        scale = 1.0 - (elapsed / _TRAY_VOICE_DECAY_S)
        if isinstance(level, (list, tuple)):
            return [max(0.0, float(value) * scale) for value in level]
        try:
            return max(0.0, float(level) * scale)
        except (TypeError, ValueError):
            return 0.0

    def _refresh_tray_feedback(self) -> None:
        # `_state`, not attribute access: speech now reaches this before the
        # tray exists, and `self._tray` on a __new__-built palette raises.
        tray = self._state("_tray")
        if tray is None:
            return
        state = self._tray_feedback_state()
        if state in {"busy", "speaking"}:
            interval = (
                _TRAY_VOICE_FRAME_INTERVAL_MS
                if state == "speaking"
                else _TRAY_BUSY_FRAME_INTERVAL_MS
            )
            if self._tray_feedback_timer.interval() != interval:
                self._tray_feedback_timer.setInterval(interval)
            if not self._tray_feedback_timer.isActive():
                self._tray_feedback_timer.start()
        else:
            self._tray_feedback_timer.stop()
            self._tray_animation_frame = 0
        try:
            tray.setIcon(
                _tray_feedback_icon(
                    state=state,
                    frame=self._tray_animation_frame,
                    levels=(
                        self._decayed_speech_meter() if state == "speaking" else None
                    ),
                )
            )
        except Exception:
            pass
        tooltip = "AbstractAssistant"
        if state == "speaking":
            tooltip = "AbstractAssistant • Speaking"
        elif state == "busy":
            tooltip = "AbstractAssistant • Thinking..."
        elif state == "complete":
            tooltip = "AbstractAssistant • Reply ready"
        try:
            tray.setToolTip(tooltip)
        except Exception:
            pass

    def _advance_tray_feedback(self) -> None:
        state = self._tray_feedback_state()
        if state not in {"busy", "speaking"}:
            self._tray_feedback_timer.stop()
            return
        if state == "busy":
            # The speaking icon draws the meter, not a frame counter.
            self._tray_animation_frame = (
                self._tray_animation_frame + 1
            ) % _TRAY_BUSY_FRAME_COUNT
        self._refresh_tray_feedback()

    def _on_speech_level(self, level: Any) -> None:
        """A meter reading for the assistant's own voice.

        Feeds the tray only: the composer's voice strip is the MICROPHONE
        meter, fed by `listen(on_audio_level=…)`, and these are output levels.
        """
        self._speech_meter = level
        self._speech_meter_ts = time.monotonic()
        if not self._tray_feedback_timer.isActive():
            # First reading of a speech the start hook did not announce.
            self._refresh_tray_feedback()

    def _install_speech_meter(self) -> None:
        """Own the voice manager's meter callback.

        The hands-free conversation installs its own while it runs and clears
        it on stop, so this is re-asserted afterwards; without it the tray
        would go quiet for every speech after the first conversation ended.
        """
        manager = getattr(self._controller, "voice_manager", None)
        setter = getattr(manager, "set_audio_meter_callback", None)
        if callable(setter):
            try:
                setter(self.speech_level_received.emit)
            except Exception:
                pass

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
        body = "Click the menu bar icon to read it."
        if excerpt:
            body = f"{excerpt}\nClick the menu bar icon to read it."
        self._notify(
            "Reply ready",
            body,
            icon=_tray_feedback_icon(state="complete"),
            duration_ms=7000,
        )

    def _scroll_history_to_latest(self) -> None:
        self._apply_history_scroll_request(self._history_scroll_request(mode="bottom"))

    def apply_typography(self, **updates: Any) -> bool:
        """Change the transcript's reading rhythm and re-render it."""
        global TYPOGRAPHY
        if updates:
            try:
                self._controller.update_preferences(**updates)
            except Exception:
                return False
        TYPOGRAPHY = Typography.from_preferences(self._controller.preferences)
        # Text size is not a transcript setting: it is THE app's type scale.
        # Scaling METRICS moves every window's type and control heights with
        # it, which is what "the same appearance everywhere" means.
        activate_metrics(TYPOGRAPHY.size)
        # The rhythm is baked into each message's HTML, so the transcript has
        # to be re-rendered rather than restyled.
        self._renderer = MarkdownRenderer(theme="friendly_grayscale")
        self._apply_styles()
        self._restyle_every_window()
        try:
            self.refresh_history()
        except Exception:
            pass
        return True

    def _restyle_every_window(self) -> None:
        """Make every window re-read the palette and the type scale.

        Windows are asked, never rebuilt: a theme or text-size change must not
        disturb a run, a transcript or an open dialog.
        """
        targets = list(QApplication.topLevelWidgets()) + self.findChildren(QWidget)
        for widget in targets:
            restyle = getattr(widget, "restyle", None)
            if callable(restyle) and widget is not self:
                try:
                    restyle()
                except Exception:
                    continue
        # Stylesheets are not the whole app: an icon is a rendered bitmap,
        # baked with the palette that was live when its widget was built. A
        # restyle sweep never touched them, so after switching to a light
        # theme the composer and toolbar glyphs stayed near-white — invisible
        # on their own background — until the app was restarted.
        for root in {id(w): w for w in targets + [self]}.values():
            try:
                retint_widget_icons(root)
            except Exception:
                continue

    def apply_theme(self, theme_id: str, *, persist: bool = True) -> bool:
        """Switch the whole app to ``theme_id``.

        Every module holds the same `THEME` object, so the palette is mutated in
        place and then each window is asked to re-read it. Nothing is recreated:
        a theme switch must not disturb a run, a transcript or a dialog.
        """
        from . import ui_themes
        from .theme import DEFAULT_THEME as _DEFAULT, activate as _activate

        wanted = normalize_ui_theme(theme_id)
        theme = ui_themes.build_theme(wanted) or _DEFAULT
        _activate(theme)

        self._renderer = MarkdownRenderer(theme="friendly_grayscale")
        self._apply_styles()
        # Top-level windows AND our own children: the voice strip is a child,
        # so a top-level-only sweep never reached it.
        self._restyle_every_window()
        # Markdown is rendered to HTML per message with the palette baked in,
        # so the transcript has to be re-rendered, not merely restyled.
        try:
            self.refresh_history()
        except Exception:
            pass
        if persist:
            try:
                self._controller.update_preferences(ui_theme=wanted)
            except Exception as exc:
                # Say why. Returning a bare False left the caller with nothing
                # to show, and the choice was lost at the next launch.
                self._set_status(f"Theme not saved: {exc}", tone="warn")
                return False
        return True

    def _apply_styles(self) -> None:
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(_solid(THEME.surface_sunken)))
        palette.setColor(QPalette.Base, QColor(_solid(THEME.surface_raised)))
        palette.setColor(QPalette.Text, QColor(_solid(THEME.text_primary)))
        self.setPalette(palette)
        # Scoped to the palette's own root surface. A dialog is a CHILD of this
        # window in Qt's object tree, so an unscoped sheet cascades into every
        # one of them and its bare type selectors win — Settings rendered 50px
        # buttons where it asks for 30. Dialogs are NOT inside `rootSurface`,
        # so scoping here is what keeps them their own.
        self.setStyleSheet(scope_stylesheet(_themed("""
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
            /* The title doubles as the status readout (tone-colored). */
            QLabel#windowTitle[tone="busy"] { color: #79c7ff; }
            QLabel#windowTitle[tone="voice"] { color: #5ed2a1; }
            QLabel#windowTitle[tone="info"] { color: #b9c7d7; }
            QLabel#windowTitle[tone="warn"] { color: #f0c979; }
            QLabel#windowTitle[tone="error"] { color: #ffb4b4; }
            QPushButton#sessionPicker {
                min-height: 28px;
                max-height: 28px;
                padding: 0px 10px;
                border-radius: 14px;
                border: 1px solid rgba(130, 150, 178, 0.28);
                background: rgba(28, 36, 48, 0.98);
                color: #eef4fb;
                font-size: 12px;
                font-weight: 600;
                text-align: center;
            }
            QPushButton#sessionPicker:hover {
                border-color: rgba(121, 199, 255, 0.42);
                background: rgba(36, 48, 65, 0.99);
            }
            QPushButton#sessionPicker:pressed {
                background: rgba(19, 25, 34, 0.99);
            }
            QPushButton#sessionPicker:disabled {
                color: #8390a2;
                border-color: rgba(130, 150, 178, 0.16);
                background: rgba(24, 30, 39, 0.88);
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
            /* A message has to be visibly a message. The old fill separated
               from the card behind it by a luminance ratio of 1.04 — the
               bubble was effectively invisible. These are the surface and
               border tokens' own colours, so they translate with the theme. */
            /* Both bubbles are an ALPHA OF A TOKEN, never an opaque literal.
               An opaque literal retints to whatever token happens to be
               nearest, which sits a different distance from the card in every
               palette — separation swung 1.29 to 2.18 across themes, and the
               user bubble's old base was `accent`, so on the light themes it
               came out PINK. As an alpha the step is relative to the card and
               inverts correctly, and the rim carries the separation. */
            QFrame#assistantBubble, QFrame#userBubble {
                border-radius: 16px;
                border: 1px solid rgba(166, 187, 214, 0.50);
                background: rgba(166, 187, 214, 0.28);
            }
            /* The user's own turns keep their own identity: `user_bg`, the
               palette's info colour, not the accent. */
            QFrame#userBubble {
                background: rgba(99, 102, 241, 0.30);
                border-color: rgba(99, 102, 241, 0.60);
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
                color: rgba(255, 255, 255, 0.45);
                font-size: 10px;
            }
            QPushButton#liveThinkingToggle {
                background: transparent;
                border: none;
                color: #9bb0c6;
                font-size: 11px;
                padding: 0px 4px;
            }
            QTextBrowser#liveReasoningText {
                background: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.55);
                font-size: 11px;
            }
            QLabel#liveTruncatedNote {
                color: #e8a54a;
                font-size: 11px;
            }
            QLabel#historyEmptyTitle {
                color: #b9c7d7;
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#historyEmptySubtitle {
                color: #71839a;
                font-size: 12px;
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
                min-height: 28px;
                max-height: 28px;
                min-width: 28px;
                max-width: 28px;
                padding: 0px;
                border-radius: 14px;
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
            QFrame#mediaPreviewTile {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QWidget#mediaGallery, QWidget#artifactChipTray, QWidget#attachmentChipStrip {
                background: transparent;
            }
            QFrame#mediaPreviewChip {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(166, 187, 214, 0.16);
                border-radius: 9px;
            }
            QFrame#mediaPreviewChip[hovered="true"] {
                background: rgba(255, 255, 255, 0.12);
                border-color: rgba(121, 199, 255, 0.36);
            }
            QFrame#mediaPreviewThumb {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QFrame#mediaPreviewThumb[hovered="true"] {
                background: rgba(121, 199, 255, 0.20);
                border-radius: 8px;
            }
            QLabel#mediaPreviewChipThumb, QLabel#mediaPreviewChipImage {
                background: transparent;
                border: none;
            }
            QLabel#mediaPreviewChipName {
                background: transparent;
                border: none;
                color: #e4edf7;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#mediaPreviewChipMeta {
                background: transparent;
                border: none;
                color: #8ea1b8;
                font-size: 11px;
                font-weight: 500;
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
            QPushButton#mediaOpenTile {
                padding: 0px;
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(166, 187, 214, 0.12);
            }
            QPushButton#mediaOpenTile:hover {
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
                min-height: 28px;
                max-height: 28px;
                min-width: 28px;
                max-width: 28px;
                padding: 0px;
                border-radius: 9px;
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
            QPushButton#sendButton[busy="true"] {
                background: rgba(145, 39, 39, 0.55);
                border-color: rgba(255, 121, 121, 0.45);
            }
            QPushButton#sendButton[busy="true"]:hover { background: rgba(170, 46, 46, 0.7); }
            QPushButton#sendButton[busy="true"]:pressed { background: rgba(120, 30, 30, 0.7); }
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
                min-height: 28px;
                max-height: 28px;
                min-width: 28px;
                max-width: 28px;
                padding: 0px;
                border-radius: 9px;
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
            """ + build_activity_qss()) + chat_stylesheet(), "QWidget#rootSurface"))


def json_dumps(value: Dict[str, Any]) -> str:
    if not value:
        return ""
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


def _handle_tray_activation(*, palette, menu: Optional[QMenu], reason) -> None:
    if reason == QSystemTrayIcon.Context:
        # Linux shows the menu itself — the D-Bus host renders the exported
        # dbusmenu, and the XEmbed path pops it before emitting Context — so
        # popping our own would show two, at a position Wayland cannot even
        # report. Windows needs it (Qt disables native menus for QApplication)
        # and macOS routes through its own decoy-menu fallback.
        if menu is not None and not sys.platform.startswith("linux"):
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
        # Say it out loud, not only into the frozen-build log: on a desktop
        # with no tray host this is the difference between "the app is broken"
        # and a sentence naming the cause.
        message = (
            "system tray unavailable on this desktop "
            "(GNOME needs the AppIndicator extension; Wayland has no XEmbed tray)"
        )
        _bundle_tray_log(f"{reason or 'refresh'}: {message}")
        warnings.warn(f"#FALLBACK: {message}")
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


def _build_tray_menu(*, palette, quit_app) -> QMenu:
    """The tray icon's menu (on macOS it is popped on a right-click by
    `_handle_tray_activation`; the host menu is only a decoy)."""
    menu = QMenu()
    menu.addAction("Show", palette.show_palette)
    menu.addAction("Hide", palette.hide)
    menu.addAction("New Session", palette._create_session)
    palette._automations_menu_action = menu.addAction("Automations…", palette.open_automations)
    # Shown once the gateway is known to advertise the Automations API.
    hub = getattr(palette, "__dict__", {}).get("_automations")
    if hub is not None:
        palette._automations_menu_action.setVisible(hub.available is True)
    menu.addAction("Settings", palette._open_settings)
    menu.addSeparator()
    menu.addAction("About AbstractAssistant\u2026", lambda: palette._open_settings("about"))
    menu.addSeparator()
    menu.addAction("Quit", quit_app)
    return menu


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


def _redeem_launch_handover(controller: AssistantController, *, base_url: str, handover_file: str) -> "tuple[str, str]":
    """Redeem the gateway console's hand-over file.

    Returns ``(banner_text, tone)``: ``("", "")`` when there is nothing to say,
    an ``info`` notice when an existing sign-in was kept or replaced, an
    ``error`` when the hand-over failed. Runs before the palette exists so its
    first gateway calls already carry the new session."""
    path = str(handover_file or "").strip()
    if not path:
        return "", ""
    from .controller import DesktopHandoverError

    try:
        _connection, notice = controller.redeem_desktop_handover_file(path, fallback_base_url=base_url)
    except DesktopHandoverError as exc:
        return str(exc), "error"
    except Exception as exc:  # pragma: no cover - defensive: never crash the launch
        return f"Could not sign in with the gateway: {exc}. {DesktopHandoverError.REMEDY}", "error"
    return (notice, "info") if notice else ("", "")


def launch_tray_app(
    *,
    config: Optional[Config] = None,
    debug: bool = False,
    data_dir: Optional[Path] = None,
    gateway_handover_file: str = "",
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("AbstractAssistant")
    # Use the real macOS system font (San Francisco) rather than QSS
    # `font-family` aliases like "-apple-system"/"SF Pro Text", which Qt cannot
    # resolve and which emit startup warnings + fall back to Helvetica.
    try:
        from PyQt5.QtGui import QFontDatabase

        app.setFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
    except Exception:
        pass
    app.setWindowIcon(_qt_icon())
    show_on_launch = _env_truthy("ABSTRACTASSISTANT_SHOW_ON_LAUNCH")

    # The URL the launcher named (--gateway-url), captured before the saved
    # connection is merged in: the hand-over belongs to THAT gateway.
    launch_url = str(getattr(getattr(config, "gateway", None), "url", "") or "").strip()
    controller = AssistantController(config=config, data_dir=data_dir, debug=debug)
    handover_text, handover_tone = _redeem_launch_handover(
        controller, base_url=launch_url, handover_file=gateway_handover_file
    )
    if str(gateway_handover_file or "").strip():
        # Opened from the gateway console: the user clicked "Open", show the window.
        show_on_launch = True
    palette = AssistantPalette(controller=controller, debug=debug)
    if handover_text:
        try:
            palette._set_banner(handover_text, tone=handover_tone, key="handover")
        except Exception:
            pass
    # Clean up the worker/hotkey/voice on quit so quitting mid-run cannot tear
    # down a live QThread (crash-on-exit class).
    try:
        app.aboutToQuit.connect(palette.shutdown)
    except Exception:
        pass

    tray = QSystemTrayIcon(_qt_icon(), app)
    app._assistant_tray = tray  # type: ignore[attr-defined]
    tray.setToolTip("AbstractAssistant")
    menu = _build_tray_menu(palette=palette, quit_app=app.quit)
    palette._tray_menu = menu
    _configure_tray_host(tray=tray, palette=palette, menu=menu)

    def _on_tray_activated(reason) -> None:
        try:
            palette._tray_last_activation_ts = time.monotonic()
        except Exception:
            pass
        _handle_tray_activation(palette=palette, menu=menu, reason=reason)

    tray.activated.connect(_on_tray_activated)
    tray_state = _refresh_tray_visibility(tray=tray, palette=palette, reason="startup")
    _schedule_tray_visibility_refresh(tray=tray, palette=palette)
    if not tray_state.available:
        # There is no tray to click, so the window IS the app: show it whatever
        # the launch mode says, and name the reason where the user is looking.
        # Without this the process ran on with no icon and no window at all.
        show_on_launch = True
        try:
            palette.setWindowFlags(palette.windowFlags() & ~Qt.Tool)
            palette._set_banner(
                "No system tray on this desktop, so the assistant stays in this "
                "window. On GNOME, install the AppIndicator extension to get the "
                "tray icon back.",
                tone="warn",
                key="tray",
            )
        except Exception:
            pass
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
