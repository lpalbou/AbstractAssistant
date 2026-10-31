"""The session switcher: a searchable list of sessions with real metrics.

The header's session control opens this popup instead of a plain dropdown.
Every row shows what the session actually holds — when it was last touched, how many
turns and tool calls it ran, the tokens and wall time it spent, the folder it
worked in and any pending human attention. Overview cards show just the
turn/tool/time facts; the rest stays in tooltips and context actions.

The rows are the gateway's sessions (see `core/gateway_sessions`); the popup
first paints the cached list and is re-rendered when the gateway answers, with
a header line when the rows are only cached. Rows are grouped by recency,
filtered as you type, and can be renamed (a local label) or archived on the
gateway after inline confirmation. The gateway keeps their runs and history. The widget owns no data: it renders `SessionDigest` values and emits
what the user chose.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence
from datetime import datetime, timezone
from functools import lru_cache

from pathlib import Path

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QSize, Qt, QUrl, QTimer, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFontMetrics, QTextLayout, QTextOption, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.session_digest import (
    RECENCY_GROUPS,
    SessionDigest,
    parse_timestamp,
    format_count,
    format_duration_ms,
    format_tokens,
    recency_group,
    session_matches_query,
    sort_digests,
)
from ..core.automations import (
    AUTOMATION_CONTROLS,
    PENDING_TEXT,
    active_short_reason,
    active_toggle_command,
    attention_total,
    automation_controls,
    control_hint,
    command_confirmed,
    group_by_automation,
    last_run_text,
    next_run_text,
    current_run,
    trigger_summary,
    is_event_trigger,
)
from ..icons import symbol_icon
from ..theme import METRICS, THEME
from .automations import automation_row_qss
from .switch import AfSwitch

ACTIVE_LABEL = AUTOMATION_CONTROLS["labels"]["active"]
from .styles import dialog_stylesheet, refresh_style

__all__ = [
    "AutomationTabRow",
    "SessionRow",
    "SessionSwitcher",
    "SESSION_SWITCHER_QSS",
    "folder_button",
    "open_folder",
]


SWITCHER_WIDTH = 460
SWITCHER_HEIGHT = 560


def _luminance(color: QColor) -> float:
    rgb = (color.redF(), color.greenF(), color.blueF())
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))


def _mix(left: QColor, right: QColor, amount: float) -> QColor:
    return QColor(
        *(
            round(a * (1 - amount) + b * amount)
            for a, b in zip(
                (left.red(), left.green(), left.blue()), (right.red(), right.green(), right.blue())
            )
        )
    )


@lru_cache(maxsize=32)
def _card_palette(
    header: str, primary: str, secondary: str, attention: str, attention_text: str, danger_text: str
) -> Dict[str, str]:
    raised = QColor(header)
    base = _mix(raised, QColor("black"), 0.20)

    def tinted(color: str) -> QColor:
        amount = 0.06
        while amount > 0.0001:
            result = _mix(base, QColor(color), amount)
            if _luminance(result) < _luminance(raised):
                return result
            amount /= 2
        return base

    unread, needs = tinted("#20c5df"), tinted(attention)
    backgrounds = (base, unread, needs)

    def readable(color: str, minimum: float = 4.5) -> str:
        original = QColor(color)
        target = QColor("white" if _luminance(base) < 0.18 else "black")
        for step in range(21):
            candidate = _mix(original, target, step / 20)
            ratios = [
                (max(_luminance(candidate), _luminance(bg)) + 0.05)
                / (min(_luminance(candidate), _luminance(bg)) + 0.05)
                for bg in backgrounds
            ]
            if min(ratios) >= minimum:
                return candidate.name()
        return target.name()

    return {
        "base": base.name(),
        "unread": unread.name(),
        "attention": needs.name(),
        "primary": readable(primary),
        "secondary": readable(secondary),
        "attention_text": readable(attention_text),
        "danger": readable(danger_text),
        "unread_marker": readable("#20c5df", 3),
        "attention_marker": readable(attention, 3),
    }


def card_palette() -> Dict[str, str]:
    return _card_palette(
        THEME.surface_raised,
        THEME.text_primary,
        THEME.text_secondary,
        THEME.attention,
        THEME.attention_text,
        THEME.danger_text,
    )


def _build_qss() -> str:
    palette = card_palette()
    card = palette["base"]
    return f"""
    QFrame#switcherCard {{ background: {THEME.surface_raised}; border: 1px solid {THEME.border_strong}; border-radius: {METRICS.radius_card}px; }}
    QLabel#switcherTitle {{ color: {THEME.text_strong}; font-size: {METRICS.font_body}px; font-weight: 600; }}
    QLabel#switcherGroup {{ color: {THEME.text_muted}; font-size: {METRICS.font_caption}px; font-weight: 400; padding: 8px 0 0 0; }}
    QLabel#switcherStatus, QLabel#switcherHint {{ color: {THEME.text_muted}; font-size: {METRICS.font_caption}px; }}
    QLabel#switcherStatus[tone="warn"] {{ color: {THEME.attention_text}; }}
    QLabel#switcherEmpty {{ color: {THEME.text_muted}; font-size: {METRICS.font_ui}px; padding: 24px 8px; }}
    QLineEdit#switcherSearch, QLineEdit#rowRename {{ background: {card}; color: {THEME.text_primary}; border: 1px solid {THEME.border_subtle}; border-radius: 9px; padding: 7px 10px; font-size: {METRICS.font_ui}px; }}
    QLineEdit#switcherSearch:focus, QLineEdit#rowRename:focus {{ border-color: {THEME.accent}; }}
    QFrame#sessionRow {{ background: {card}; border: 1px solid transparent; border-radius: 16px; }}
    QFrame#sessionRow:hover {{ border-color: {THEME.border_strong}; }}
    QFrame#sessionRow[active="true"] {{ border-color: {THEME.border_strong}; }}
    QFrame#sessionRow[selected="true"] {{ border-color: {THEME.border_strong}; }}
    QFrame#sessionRow:focus {{ border: 1px dashed {THEME.text_secondary}; }}
    QFrame#sessionRow[unread="true"] {{ background: {palette["unread"]}; border-color: {palette["unread_marker"]}; }}
    QFrame#sessionRow[automation="true"][unread="true"] {{ background: {palette["attention"]}; border-color: {palette["attention_marker"]}; }}
    QFrame#sessionRow[attention="true"] {{ background: {palette["attention"]}; border-color: {palette["attention_marker"]}; }}
    QLabel#rowTitle {{ color: {palette["primary"]}; font-size: {METRICS.font_body}px; font-weight: 400; }}
    QLabel#rowTime, QLabel#rowPreview, QLabel#rowMetric {{ color: {palette["secondary"]}; font-size: {METRICS.font_ui}px; font-weight: 400; }}
    QLabel#rowMetric[tone="warn"] {{ color: {palette["attention_text"]}; }}
    QLabel#rowMetric[tone="danger"] {{ color: {palette["danger"]}; }}
    QLabel#rowMetricIcon {{ background: transparent; border: none; }}
    QPushButton#rowAction, QPushButton#rowIcon, QPushButton#rowFolder {{ min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; padding: 0; border: none; border-radius: 7px; background: transparent; }}
    QPushButton#rowAction:hover, QPushButton#rowIcon:hover, QPushButton#rowFolder:hover {{ background: {THEME.overlay_hover}; }}
    QPushButton#rowAction:focus, QPushButton#rowIcon:focus {{ border: 1px solid {THEME.accent}; }}
    QPushButton#switcherPrimary {{ color: {THEME.primary_text}; background: {THEME.primary}; border: none; border-radius: 9px; padding: 6px 10px; font-size: {METRICS.font_ui}px; font-weight: 400; }}
    QPushButton#switcherPrimary:hover {{ background: {THEME.primary_hover}; }}
    QPushButton#switcherTab, QPushButton#switcherScope, QPushButton#switcherLoadMore {{ color: {THEME.text_secondary}; background: {card}; border: 1px solid {THEME.border_subtle}; border-radius: 8px; padding: 6px 10px; font-size: {METRICS.font_ui}px; font-weight: 400; }}
    QPushButton#switcherTab:checked, QPushButton#switcherScope:checked {{ color: {THEME.text_primary}; border-color: {THEME.accent}; }}
    QPushButton#switcherTab:focus, QPushButton#switcherLoadMore:focus {{ border-color: {THEME.accent}; }}
    QFrame#switcherFooter, QFrame#switcherHeader, QScrollArea#switcherScroll, QWidget#switcherList {{ background: transparent; border: none; }}
    """


class TwoLineTitle(QLabel):
    """Plain-text, word-wrapped title with a genuine two-line ellipsis."""

    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.full_text = " ".join(str(text or "").split())
        self.setTextFormat(Qt.PlainText)
        self.setObjectName("rowTitle")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setToolTip(self.full_text)
        self.fit(300)

    def fit(self, width: int) -> None:
        width = max(40, int(width))
        layout = QTextLayout(self.full_text, self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        first = layout.createLine()
        first.setLineWidth(width)
        split = first.textLength()
        layout.endLayout()
        metrics = QFontMetrics(self.font())
        lines = [self.full_text]
        if split < len(self.full_text):
            lines = [
                self.full_text[:split].rstrip(),
                metrics.elidedText(self.full_text[split:].strip(), Qt.ElideRight, width),
            ]
        self.setText("\n".join(lines))
        self.setFixedHeight(metrics.lineSpacing() * len(lines))

    def resizeEvent(self, event) -> None:
        self.fit(event.size().width())
        super().resizeEvent(event)


def build_switcher_qss() -> str:
    """Rebuilt on demand so a theme switch reaches the popup too."""
    return _build_qss()


SESSION_SWITCHER_QSS: str = build_switcher_qss()


def _metric(icon: str, text: str, tooltip: str, tone: str = "", *, wrap: bool = False) -> QWidget:
    """One small icon+number chip on a row's metric line. ``wrap`` = served text that
    must be shown whole: the label wraps onto more lines instead of being cut."""
    host = QWidget()
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(3)
    palette = card_palette()
    color = {
        "warn": palette["attention_text"],
        "accent": palette["primary"],
        "danger": palette["danger"],
    }.get(tone, palette["secondary"])
    if icon:
        glyph = QLabel()
        glyph.setObjectName("rowMetricIcon")
        glyph.setPixmap(symbol_icon(icon, color=color, size=13).pixmap(13, 13))
        host.metric_icon = (icon, tone, glyph)
        row.addWidget(glyph, 0, Qt.AlignTop if wrap else Qt.AlignVCenter)
    label = QLabel(text)
    label.setObjectName("rowMetric")
    if tone:
        label.setProperty("tone", tone)
    if wrap:
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    row.addWidget(label, 1 if wrap else 0, Qt.AlignTop if wrap else Qt.AlignVCenter)
    host.setToolTip(tooltip)
    return host


def card_relative_time(stamp: str) -> str:
    at = parse_timestamp(stamp)
    if at is None:
        return ""
    seconds = max(0, (datetime.now(timezone.utc) - at).total_seconds())
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


class RowCard(QFrame):
    """Shared compact card shell with independent selection, unread and attention facts."""

    def __init__(self, parent: Optional[QWidget] = None, *, active: bool = False) -> None:
        super().__init__(parent)
        self._selected = False
        self.setObjectName("sessionRow")
        self.setProperty("active", "true" if active else "false")
        self.setProperty("selected", "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMinimumWidth(0)
        # Never wider than the list: long content elides, it never pushes.
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 10, 10)
        root.setSpacing(8)
        self.spine = QLabel(self)
        self.spine.setObjectName("rowStateMarker")
        self.spine.setFixedSize(12, 14)
        self.spine.setAlignment(Qt.AlignCenter)
        self.spine.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        root.addWidget(self.spine, 0, Qt.AlignVCenter)
        self.column = QVBoxLayout()
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(6)
        root.addLayout(self.column, 1)

    def archive_action(self, callback) -> QPushButton:
        button = _icon_button(
            "archive",
            "Archive conversation",
            parent=self,
            name="rowAction",
            tint=card_palette()["danger"],
        )
        button.setAccessibleName("Archive " + self.accessibleName())
        button.clicked.connect(lambda: self._confirm_archive(callback))
        policy = button.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        button.setSizePolicy(policy)
        button.hide()
        return button

    def _confirm_archive(self, callback) -> None:
        if getattr(self, "_archive_confirm", None) is not None:
            return
        host = QWidget(self)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 4, 0, 0)
        label = QLabel(f"Archive this {getattr(self, 'archive_kind', 'conversation')}?", host)
        label.setObjectName("rowMetric")
        layout.addWidget(label, 1)
        yes = QPushButton("Archive", host)
        no = QPushButton("Cancel", host)
        layout.addWidget(yes)
        layout.addWidget(no)

        def close() -> None:
            self.column.removeWidget(host)
            host.hide()
            host.deleteLater()
            self._archive_confirm = None

        def confirm() -> None:
            close()
            callback()

        yes.clicked.connect(confirm)
        no.clicked.connect(close)
        self._archive_confirm = host
        self.column.addWidget(host)
        no.setFocus()

    def _reveal_actions(self) -> None:
        if sip.isdeleted(self):
            return
        action = getattr(self, "archive_button", None)
        if action is not None:
            focus = QApplication.focusWidget()
            action.setVisible(
                self.underMouse()
                or focus is self
                or (focus is not None and self.isAncestorOf(focus))
            )

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._reveal_actions()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        QTimer.singleShot(0, self._reveal_actions)

    def set_card_state(
        self,
        *,
        unread: bool = False,
        attention: bool = False,
        working: bool = False,
        failed: bool = False,
    ) -> None:
        self.setProperty("unread", "true" if unread else "false")
        self.setProperty("attention", "true" if attention else "false")
        self.setProperty("working", "true" if working else "false")
        self.setProperty("failed", "true" if failed else "false")
        automation = getattr(self, "archive_kind", "") == "automation"
        palette = card_palette()
        color = (
            palette["attention_marker"]
            if attention or (unread and automation)
            else palette["unread_marker"]
            if unread
            else palette["secondary"]
            if working
            else THEME.danger
        )
        self.spine.setText("◆" if attention else "◌" if working else "●")
        self.spine.setStyleSheet(
            f"color: {color}; background: transparent; border: none; font-size: 13px; font-weight: 400;"
        )
        self.spine.setToolTip(
            "Needs you"
            if attention
            else "Working"
            if working
            else "New results"
            if automation and unread
            else "New messages"
            if unread
            else "Failed"
        )
        self.spine.setVisible(bool(unread or attention or working or failed))
        refresh_style(self)

    def set_spine_tone(self, tone: str) -> None:
        # Compatibility for the existing automation state/command callbacks.
        self.set_card_state(attention=tone == "warn", working=tone == "active")

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self.setProperty("selected", "true" if selected else "false")
        refresh_style(self)

    @property
    def selected(self) -> bool:
        return self._selected


class SessionRow(RowCard):
    """One session: title, preview, metrics, and in-place rename. (No delete:
    a session exists iff the gateway lists it, and the gateway has none.)"""

    archive_requested = pyqtSignal(str)
    chosen = pyqtSignal(str)
    rename_committed = pyqtSignal(str, str)
    focus_requested = pyqtSignal(object)
    # A discussion row's "about automation <title>" badge was clicked.
    automation_requested = pyqtSignal(str)

    def __init__(
        self,
        digest: SessionDigest,
        *,
        active: bool,
        parent: Optional[QWidget] = None,
        automation_title: str = "",
    ) -> None:
        super().__init__(parent, active=active)
        self.digest = digest
        self.session_id = digest.session_id
        self._active = bool(active)
        self.set_card_state(
            unread=digest.unread,
            attention=digest.needs_attention,
            working=digest.state == "running",
        )
        self.setAccessibleName(
            digest.display_title
            + (
                ". Needs you"
                if digest.needs_attention
                else ". New messages"
                if digest.unread
                else ""
            )
        )
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self.title_label = TwoLineTitle(digest.display_title, self)
        head.addWidget(self.title_label, 1)
        self.rename_edit = QLineEdit(self)
        self.rename_edit.setObjectName("rowRename")
        self.rename_edit.hide()
        self.rename_edit.returnPressed.connect(self._commit_rename)
        self.rename_edit.installEventFilter(self)
        head.addWidget(self.rename_edit, 1)
        self.rename_button = _icon_button(
            "square-pen", "Rename this conversation", parent=self, name="rowAction"
        )
        self.rename_button.clicked.connect(self.start_rename)
        self.rename_button.hide()
        self.archive_button = self.archive_action(
            lambda: self.archive_requested.emit(self.session_id)
        )
        head.addWidget(self.archive_button, 0, Qt.AlignVCenter)
        self.column.addLayout(head)
        self.about_button = None
        if digest.session_kind == "discussion":
            self.about_button = QPushButton(f"About {automation_title or 'an automation'}", self)
            self.about_button.full_text = (
                f"about automation {automation_title}"
                if automation_title
                else "about an automation"
            )
            self.about_button.setObjectName("aboutAutomation")
            self.about_button.clicked.connect(
                lambda: self.automation_requested.emit(digest.automation_id)
            )
            self.column.addWidget(self.about_button, 0, Qt.AlignLeft)
        self.time_label = QLabel(card_relative_time(digest.last_activity), self)
        self.time_label.hide()
        self._preview_text = digest.preview
        self.preview_label = QLabel(digest.preview, self)
        self.preview_label.hide()
        self.metrics_host = QWidget(self)
        metrics = QHBoxLayout(self.metrics_host)
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setSpacing(10)
        for widget in self._metric_widgets():
            metrics.addWidget(widget, 0, Qt.AlignVCenter)
        metrics.addStretch(1)
        self.metrics_host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.column.addWidget(self.metrics_host)
        self.setToolTip(self._tooltip())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _metric_widgets(self) -> List[QWidget]:
        digest = self.digest
        out = []
        prefix = "" if digest.detailed else "≥"
        if digest.turns:
            out.append(
                _metric(
                    "message-square",
                    prefix + format_count(digest.turns),
                    f"{prefix}{digest.turns} turns",
                )
            )
        if digest.tool_calls:
            out.append(
                _metric(
                    "wrench",
                    prefix + format_count(digest.tool_calls),
                    f"{prefix}{digest.tool_calls} tool calls",
                )
            )
        if digest.needs_attention:
            out.append(
                _metric(
                    "hand", "Needs you", "A question or approval needs your response.", tone="warn"
                )
            )
        elif digest.state == "running":
            out.append(_metric("loader", "Working", "A turn is running."))
        elif digest.last_activity:
            out.append(
                _metric("clock", card_relative_time(digest.last_activity), self._time_tooltip())
            )
        elif digest.empty:
            out.append(_metric("", "Ready when you are", "No messages yet."))
        return out

    def _menu(self, point) -> None:
        menu = QMenu(self)
        menu.addAction("Rename conversation", self.start_rename)
        if self.digest.workspace_root:
            menu.addAction("Open folder", lambda: open_folder(self.digest.workspace_root))
        menu.addAction(
            "Archive conversation…",
            lambda: self._confirm_archive(lambda: self.archive_requested.emit(self.session_id)),
        )
        menu.exec_(self.mapToGlobal(point))

    def _time_tooltip(self) -> str:
        digest = self.digest
        lines = []
        if digest.last_activity:
            lines.append(f"Last activity: {digest.last_activity}")
        if digest.created_at:
            lines.append(f"Created: {digest.created_at}")
        return "\n".join(lines)

    def _tooltip(self) -> str:
        digest = self.digest
        # Everything the row could not fit lives here.
        lines = [digest.display_title]
        if digest.preview:
            lines.append(digest.preview)
        if digest.workspace_root:
            lines.append(f"Files: {digest.workspace_root}")
        lines.append(
            f"{digest.turns} turns · {digest.tool_calls} tool calls · {format_tokens(digest.total_tokens)} · {format_duration_ms(digest.duration_ms)}"
        )
        return "\n".join(lines)

    def elide_labels(self, width: int) -> None:
        self.title_label.fit(max(80, int(width) - 55))

    # ---------------------------------------------------------------- actions

    def start_rename(self) -> None:
        self.rename_edit.setText(self.digest.display_title)
        self.title_label.hide()
        self.rename_edit.show()
        self.rename_edit.setFocus(Qt.ShortcutFocusReason)
        self.rename_edit.selectAll()

    def _commit_rename(self) -> None:
        title = " ".join(self.rename_edit.text().split()).strip()
        self.cancel_rename()
        if title and title != self.digest.display_title:
            self.rename_committed.emit(self.session_id, title)

    def cancel_rename(self) -> None:
        self.rename_edit.hide()
        self.title_label.show()

    # ----------------------------------------------------------------- events

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        if (
            obj is self.rename_edit
            and event.type() == QEvent.KeyPress
            and event.key() == Qt.Key_Escape
        ):
            self.cancel_rename()
            return True
        return super().eventFilter(obj, event)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self._reveal_actions()
        self.focus_requested.emit(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        QTimer.singleShot(0, self._reveal_actions)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.LeftButton and not self.rename_edit.isVisible():
            self.chosen.emit(self.session_id)
            return
        super().mouseReleaseEvent(event)


# ----------------------------------------------------------- folders


def open_folder(path: str) -> bool:
    """Open a local folder in the OS file manager."""
    return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))


def _icon_button(
    icon: str, tooltip: str, *, parent: QWidget, name: str = "rowIcon", tint: str = ""
) -> QPushButton:
    """A compact icon-only control; what it does is in its tooltip."""
    button = QPushButton(parent)
    button.setObjectName(name)
    button.setIcon(symbol_icon(icon, color=tint or THEME.text_secondary, size=14))
    button.setIconSize(QSize(14, 14))
    button.setFixedSize(26, 24)
    button.setCursor(Qt.PointingHandCursor)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip.split(" (")[0])
    return button


def folder_button(path: str, *, parent: QWidget) -> QPushButton:
    """A workspace folder as a folder glyph: opens it when it exists on this
    machine; disabled with the reason when it lives on the gateway host."""
    local = bool(path) and Path(path).expanduser().is_dir()
    button = _icon_button(
        "folder",
        f"Open workspace folder\n{path}"
        if local
        else f"Workspace folder on the gateway host:\n{path}",
        parent=parent,
        name="rowFolder",
        tint=THEME.text_secondary if local else THEME.text_faint,
    )
    button.setEnabled(local)
    button.setCursor(Qt.PointingHandCursor if local else Qt.ArrowCursor)
    button.clicked.connect(lambda _=False, p=str(path): open_folder(p))
    button.folder_path = str(path)
    return button


def missing_folder_button(field: str, *, parent: QWidget) -> QPushButton:
    """The folder glyph when the gateway does not report the folder:
    disabled, naming the missing field."""
    button = _icon_button(
        "folder",
        f"The gateway does not report this folder ({field}).",
        parent=parent,
        name="rowFolder",
        tint=THEME.text_faint,
    )
    button.setEnabled(False)
    button.setCursor(Qt.ArrowCursor)
    button.folder_path = ""
    return button


# --------------------------------------------------------- automation tab


class AutomationTabRow(RowCard):
    """Watch-style title, run count, cadence and next/status facts. Controls live in its view."""

    open_requested = pyqtSignal(str, str)  # automation_id, "latest"
    control_requested = pyqtSignal(str, str)  # automation_id, pause|resume
    focus_requested = pyqtSignal(object)

    def __init__(self, summary: Dict[str, Any], *, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.archive_kind = "automation"
        self.setProperty("automation", "true")
        self.summary = dict(summary)
        self.automation_id = str(summary.get("automation_id") or "")
        attention = summary.get("attention") if isinstance(summary.get("attention"), dict) else {}
        unseen = int(attention.get("unseen_count") or 0)
        needs_you = bool(attention.get("pending_waits"))
        self.set_card_state(
            unread=bool(unseen),
            attention=needs_you,
            working=current_run(summary) is not None and not needs_you,
            failed=(summary.get("last_occurrence") or {}).get("status") == "failed",
        )
        self.setAccessibleName(
            str(summary.get("title") or "Automation")
            + (". Needs you" if needs_you else f". {unseen} new results" if unseen else "")
        )
        self.title_label = TwoLineTitle(str(summary.get("title") or "Automation"), self)
        title_row = QHBoxLayout()
        title_row.addWidget(self.title_label, 1)
        self.archive_button = self.archive_action(
            lambda: self.control_requested.emit(self.automation_id, "archive")
        )
        archive_enabled, archive_reason = automation_controls(summary)["archive"]
        self.archive_button.setEnabled(archive_enabled)
        self.archive_button.setToolTip("Archive automation" if archive_enabled else archive_reason)
        title_row.addWidget(self.archive_button)
        self.column.addLayout(title_row)
        self.state_chip = None
        self.time_label = QLabel("", self)
        self.time_label.hide()
        self._result_text_full = self._result_text(summary, summary.get("last_occurrence"))
        self.result_label = QLabel(self._result_text_full, self)
        self.result_label.setToolTip(self._result_text_full)
        self.result_label.hide()
        self.metrics_host = QWidget(self)
        metrics = QHBoxLayout(self.metrics_host)
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setSpacing(10)
        trigger = summary.get("trigger") if isinstance(summary.get("trigger"), dict) else {}
        self._schedule = trigger_summary(trigger, summary)
        metrics.addWidget(
            _metric(
                "refresh-cw", str(int(summary.get("occurrence_count") or 0)), "Served run count"
            )
        )
        self.schedule_chip = _metric("clock", self._compact_schedule(summary), self._schedule)
        metrics.addWidget(self.schedule_chip)
        self._next_chip = _metric("play", "", "Next run")
        metrics.addWidget(self._next_chip)
        if needs_you:
            self.state_chip = _metric(
                "hand", "Needs you", "A question or approval needs your response.", tone="warn"
            )
            metrics.addWidget(self.state_chip)
        elif unseen:
            metrics.addWidget(
                _metric(
                    "message-square", str(unseen) + " new", f"{unseen} unseen results", tone="warn"
                )
            )
        metrics.addStretch(1)
        # Keep compatibility with command callbacks; the visible switch lives in AutomationView.
        self.active_switch = self._active_switch(summary)
        self.active_switch.hide()
        self.column.addWidget(self.metrics_host)
        self.folder = (
            folder_button(summary["workspace_root"], parent=self)
            if summary.get("workspace_root")
            else missing_folder_button("AutomationSummary.workspace_root", parent=self)
        )
        self.folder.hide()
        self.refresh_times()
        self.setToolTip(f"{summary.get('title') or ''}\n{self._schedule}\n{self._result_text_full}")

    @staticmethod
    def _compact_schedule(summary: Dict[str, Any]) -> str:
        trigger = summary.get("trigger") or {}
        config = trigger.get("config") or {}
        kind = config.get("kind")
        if kind in {"daily", "weekly", "monthly"}:
            return str(kind).title()
        if kind == "once":
            return "Once"
        if is_event_trigger(trigger):
            return "Email" if "email" in str(trigger.get("source_id")) else "Event"
        every = str(config.get("every") or "")
        if every.endswith("m"):
            try:
                minutes = int(every[:-1])
                return (
                    f"{minutes // 1440}d"
                    if minutes and minutes % 1440 == 0
                    else f"{minutes // 60}h"
                    if minutes and minutes % 60 == 0
                    else every
                )
            except ValueError:
                pass
        return every or "Scheduled"

    def _active_switch(self, summary: Dict[str, Any]) -> AfSwitch:
        """The automation's state as a switch labelled "Active" (operator
        2026-09-30: a persistent on/off state is a switch labelled by the
        feature, never a Pause/Resume verb or a word-and-glyph button). It
        shows the gateway's status and never changes before the gateway
        confirms a command; archived / ended / legacy / not permitted = the
        switch unavailable, the reason after the label ("Active — Archived")
        and on hover. The card's only control."""
        controls = automation_controls(summary)
        sw = AfSwitch(ACTIVE_LABEL, self, reason_inline=True)
        sw.setObjectName("rowActive")
        sw.setChecked(summary.get("status") == "active")
        sw.set_hint(control_hint("active"))
        enabled, reason = controls["active"]
        sw.set_unavailable(None if enabled else reason, short=active_short_reason(summary, reason))
        sw.setAccessibleName(f"Active: {summary.get('title') or 'automation'}")
        # Never squeezed by the chips: the label (and a short reason) stay whole.
        sw.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        sw.setMinimumWidth(sw.sizeHint().width())
        sw.state_control = active_toggle_command(summary)
        sw.clicked.connect(lambda _checked=False: self._clicked())
        return sw

    def _clicked(self) -> None:
        sw = self.active_switch
        # The click flipped the box; the switch shows the gateway's state
        # until the command is confirmed.
        sw.blockSignals(True)
        sw.setChecked(self.summary.get("status") == "active")
        sw.blockSignals(False)
        if self.pending is not None or not sw.is_actionable():
            return  # never send the same command twice
        control = sw.state_control
        self.set_pending(control)
        self.control_requested.emit(self.automation_id, control)

    @property
    def pending(self) -> Optional[str]:
        return getattr(self, "_pending", None)

    def set_pending(self, control: str) -> None:
        """Busy until the gateway confirms (or refuses)."""
        self._pending = control
        self.archive_button.setEnabled(False)
        self.active_switch.set_busy(True)
        self.active_switch.setToolTip(PENDING_TEXT[control])

    def restore_state(self, reason: str = "") -> None:
        """Back to the gateway's state (the command failed or was never confirmed)."""
        self._pending = None
        self.archive_button.setEnabled(automation_controls(self.summary)["archive"][0])
        layout = self.active_switch.parentWidget().layout()
        fresh = self._active_switch(self.summary)
        if reason:
            fresh.setToolTip(f"{fresh.toolTip()}\nLast attempt failed: {reason}")
        if layout is not None:
            layout.replaceWidget(self.active_switch, fresh)
        fresh.hide()
        self.active_switch.hide()
        self.active_switch.deleteLater()
        self.active_switch = fresh

    # ------------------------------------------------------------- content

    @staticmethod
    def _result_text(summary: Dict[str, Any], last: Optional[Dict[str, Any]]) -> str:
        current = current_run(summary)
        if current is not None:
            text = f"Run #{current.get('index')} running"
            return f"{text} · paused after this run" if summary.get("status") == "paused" else text
        if last is None:
            return "No run yet."
        text = " ".join(str(last.get("excerpt") or "").split())
        if not text and last.get("status") == "waiting":
            attention = (
                summary.get("attention") if isinstance(summary.get("attention"), dict) else {}
            )
            waits = [
                w for w in attention.get("waits") or [] if isinstance(w, dict) and w.get("prompt")
            ]
            text = " ".join(str(waits[0]["prompt"]).split()) if waits else ""
        status = str(last.get("status") or "")
        # Never "running" from the last occurrence: that is current_occurrence's job.
        if status in {"admitted", "running", "backoff"}:
            status = ""
        return text or f"Run #{last.get('index')} {status}".strip()

    @staticmethod
    def _chip_label(chip: QWidget) -> QLabel:
        return next(w for w in chip.findChildren(QLabel) if w.objectName() == "rowMetric")

    def refresh_times(self, now=None) -> None:
        """Last and next run times, relative to ``now`` (again on every poll)."""
        last = last_run_text(self.summary, now=now)  # "last 40 min ago" / "last —"
        nxt = next_run_text(self.summary, now=now)  # "next in 2 min" / "next —" / "next: now"
        trigger = (
            self.summary.get("trigger") if isinstance(self.summary.get("trigger"), dict) else {}
        )
        if is_event_trigger(trigger):
            nxt = ""  # it runs when something happens: no next run to show
        self.time_label.setText(last[len("last ") :])
        self.time_label.setToolTip(f"Last run: {last[len('last ') :]}")
        state = str(self.summary.get("status") or "")
        text = (
            "Paused"
            if state == "paused"
            else "Ended"
            if state in {"completed", "archived"}
            else nxt.replace("next in ", "").replace("next: ", "").replace("next —", "")
        )
        text = (
            text.replace(" minutes", "m")
            .replace(" minute", "m")
            .replace(" min", "m")
            .replace(" hours", "h")
            .replace(" hour", "h")
            .replace(" days", "d")
            .replace(" day", "d")
        )
        self._chip_label(self._next_chip).setText(text)
        self._next_chip.setVisible(bool(text))
        self._meta_text = " · ".join(p for p in (self._schedule, last, nxt) if p)
        self.metrics_host.setToolTip(self._meta_text)

    @property
    def meta_text(self) -> str:
        return self._meta_text

    # ----------------------------------------------------------- behaviour

    @property
    def archived(self) -> bool:
        return self.summary.get("status") == "archived"

    def matches(self, query: str) -> bool:
        needle = " ".join(str(query or "").lower().split())
        if not needle:
            return True
        hay = " ".join(
            str(x or "").lower()
            for x in (self.summary.get("title"), self._meta_text, self._result_text_full)
        )
        return all(word in hay for word in needle.split())

    def elide_labels(self, width: int) -> None:
        self.title_label.fit(max(80, int(width) - 35))

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self._reveal_actions()
        self.focus_requested.emit(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        QTimer.singleShot(0, self._reveal_actions)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.LeftButton:
            self.open_requested.emit(self.automation_id, "latest")
            return
        super().mouseReleaseEvent(event)


TAB_HINTS = {
    "sessions": "↑↓ move · ↵ open · ⌘1/⌘2 tabs · esc close",
    "automations": "↑↓ move · ↵ open · ⌘1/⌘2 tabs · esc close",
}


class SessionSwitcher(QDialog):
    """The popup: two tabs (Sessions | Automations), search, keyboard
    navigation, row actions."""

    archive_requested = pyqtSignal(str)
    session_chosen = pyqtSignal(str)
    new_chat_requested = pyqtSignal()
    rename_requested = pyqtSignal(str, str)
    load_more_requested = pyqtSignal()
    tab_changed = pyqtSignal(str)
    # An automation (row, Open, a discussion's badge) was chosen: the view
    # opens at its latest run.
    automation_chosen = pyqtSignal(str)
    # (automation_id, "top" | "latest")
    automation_open_requested = pyqtSignal(str, str)
    automation_control_requested = pyqtSignal(str, str)
    new_automation_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sessionSwitcher")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.restyle()
        self.resize(SWITCHER_WIDTH, SWITCHER_HEIGHT)

        self._digests: List[SessionDigest] = []
        self._more = False
        self._rows: List[SessionRow] = []
        self._group_labels: Dict[str, QLabel] = {}
        self._active_id = ""
        self._selected_index = -1
        self._tab = "sessions"
        self._automations: List[Dict[str, Any]] = []
        self._automation_status = ""
        self._automations_available = False
        self._auto_rows: List[AutomationTabRow] = []
        # automation_id -> (control, summary before, token): sent, not yet confirmed.
        self._pending: Dict[str, tuple] = {}
        self._pending_token = 0
        self.load_more_button: Optional[QPushButton] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("switcherCard")
        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.title_label = QLabel("Conversations")
        self.title_label.setObjectName("switcherTitle")
        header.addWidget(self.title_label, 0, Qt.AlignVCenter)
        # The counts live in the tab labels ("Sessions · 146+"), the detail in
        # their tooltips: the header line holds only the title and its buttons.
        self._count_text = ""
        header.addStretch(1)
        self.show_archived = QPushButton("Show archived")
        self.show_archived.setObjectName("switcherScope")
        self.show_archived.setCheckable(True)
        self.show_archived.setCursor(Qt.PointingHandCursor)
        self.show_archived.setToolTip("Also list archived automations (their history is kept)")
        self.show_archived.toggled.connect(lambda _checked: self._rebuild_automations())
        header.addWidget(self.show_archived, 0, Qt.AlignVCenter)
        self.new_automation_button = QPushButton("New automation")
        self.new_automation_button.setObjectName("switcherPrimary")
        self.new_automation_button.setCursor(Qt.PointingHandCursor)
        self.new_automation_button.setIcon(symbol_icon("plus", color=THEME.text_strong, size=12))
        self.new_automation_button.setIconSize(QSize(12, 12))
        self.new_automation_button.setToolTip(
            "Create an automation: a task that runs on a schedule"
        )
        self.new_automation_button.clicked.connect(self._on_new_automation)
        header.addWidget(self.new_automation_button, 0, Qt.AlignVCenter)
        self.new_button = QPushButton("New conversation")
        self.new_button.setObjectName("switcherPrimary")
        self.new_button.setCursor(Qt.PointingHandCursor)
        self.new_button.setIcon(symbol_icon("plus", color=THEME.text_strong, size=12))
        self.new_button.setIconSize(QSize(12, 12))
        self.new_button.setToolTip("Start a new session (⌘N)")
        self.new_button.clicked.connect(self._on_new_chat)
        header.addWidget(self.new_button, 0, Qt.AlignVCenter)
        root.addLayout(header)

        # Sessions | Automations (a segmented control under the title).
        self.tab_bar = QWidget(self)
        tabs = QHBoxLayout(self.tab_bar)
        tabs.setContentsMargins(0, 0, 0, 0)
        tabs.setSpacing(0)
        self.tab_buttons: Dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, text, tip in (
            ("sessions", "Conversations", "⌘1"),
            ("automations", "Automations", "⌘2"),
        ):
            button = QPushButton(text, self.tab_bar)
            button.setObjectName("switcherTab")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(f"{text} ({tip})")
            button.clicked.connect(lambda _=False, k=key: self.set_tab(k, emit=True))
            group.addButton(button)
            tabs.addWidget(button, 1)
            self.tab_buttons[key] = button
        self.tab_buttons["sessions"].setChecked(True)
        root.addWidget(self.tab_bar)

        # Where the rows come from when it is not simply "the gateway, now".
        self.status_label = QLabel("", self)
        self.status_label.setObjectName("switcherStatus")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        root.addWidget(self.status_label)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("switcherSearch")
        self.search_edit.setPlaceholderText("Filter by topic, folder or tool…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.search_edit.installEventFilter(self)
        root.addWidget(self.search_edit)

        self.pages = QStackedWidget(self)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("switcherScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_host.setObjectName("switcherList")
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_host)
        self.pages.addWidget(self.scroll)

        self.auto_scroll = QScrollArea()
        self.auto_scroll.setObjectName("switcherScroll")
        self.auto_scroll.setWidgetResizable(True)
        self.auto_scroll.setFrameShape(QFrame.NoFrame)
        self.auto_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.auto_host = QWidget()
        self.auto_host.setObjectName("switcherList")
        self.auto_layout = QVBoxLayout(self.auto_host)
        self.auto_layout.setContentsMargins(0, 0, 6, 0)
        self.auto_layout.setSpacing(8)
        self.auto_layout.addStretch(1)
        self.auto_scroll.setWidget(self.auto_host)
        self.pages.addWidget(self.auto_scroll)
        root.addWidget(self.pages, 1)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("switcherEmpty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        root.addWidget(self.empty_label)

        footer = QFrame()
        footer.setObjectName("switcherFooter")
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.setSpacing(8)
        self.hint_label = QLabel(TAB_HINTS["sessions"])
        self.hint_label.setObjectName("switcherHint")
        footer_row.addWidget(self.hint_label, 1, Qt.AlignVCenter)
        root.addWidget(footer)
        self._apply_tab()

    def restyle(self) -> None:
        """Re-read the palette (the theme changed, or this is the first paint)."""
        self.setStyleSheet(dialog_stylesheet() + build_switcher_qss() + automation_row_qss())
        for row in list(getattr(self, "_rows", ()) or ()) + list(
            getattr(self, "_auto_rows", ()) or ()
        ):
            row.set_card_state(
                unread=row.property("unread") == "true",
                attention=row.property("attention") == "true",
                working=row.property("working") == "true",
                failed=row.property("failed") == "true",
            )
            palette = card_palette()
            for metric in row.findChildren(QWidget):
                details = getattr(metric, "metric_icon", None)
                if details:
                    icon, tone, glyph = details
                    color = {
                        "warn": palette["attention_text"],
                        "accent": palette["primary"],
                        "danger": palette["danger"],
                    }.get(tone, palette["secondary"])
                    glyph.setPixmap(symbol_icon(icon, color=color, size=13).pixmap(13, 13))
            row.archive_button.setIcon(symbol_icon("archive", color=palette["danger"], size=12))
            row.title_label.fit(row.title_label.width())

    # ------------------------------------------------------------------ tabs

    @property
    def tab(self) -> str:
        return self._tab

    def set_tab(self, tab: str, *, emit: bool = False) -> None:
        if tab not in TAB_HINTS:
            raise ValueError(f"unknown switcher tab {tab!r}")
        if tab == "automations" and not self._automations_available:
            tab = "sessions"
        changed = tab != self._tab
        self._tab = tab
        self._apply_tab()
        if emit and changed:
            self.tab_changed.emit(tab)

    def _apply_tab(self) -> None:
        sessions = self._tab == "sessions"
        self.tab_bar.setVisible(self._automations_available)
        for key, button in self.tab_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == self._tab)
            button.blockSignals(False)
        self.pages.setCurrentIndex(0 if sessions else 1)
        self.title_label.setText("Conversations" if sessions else "Automations")
        self.new_button.setVisible(sessions)
        self.show_archived.setVisible(not sessions)
        self.new_automation_button.setVisible(not sessions)
        self.hint_label.setText(TAB_HINTS[self._tab])
        self.search_edit.setPlaceholderText(
            "Filter by topic, folder or tool…"
            if sessions
            else "Filter by title, schedule or result…"
        )
        self._refresh_count()
        self._apply_filter()
        self._select_index(0 if not sessions else self._active_index())

    # ------------------------------------------------------------- rendering

    def set_status(self, text: str, *, tone: str = "", tooltip: str = "") -> None:
        """The header line under the title ("" hides it)."""
        value = str(text or "").strip()
        self.status_label.setText(value)
        self.status_label.setToolTip(str(tooltip or ""))
        self.status_label.setProperty("tone", str(tone or ""))
        refresh_style(self.status_label)
        self.status_label.setVisible(bool(value))

    @property
    def status_text(self) -> str:
        return self.status_label.text() if self.status_label.isVisibleTo(self) else ""

    def set_digests(
        self, digests: Sequence[Any], *, active_session_id: str = "", more: bool = False
    ) -> None:
        """Render the Sessions tab. Accepts `SessionDigest` values or dicts.
        ``more``: the gateway has more sessions than those given ("Load more")."""
        active = str(active_session_id or "").strip()
        parsed: List[SessionDigest] = []
        for item in digests or []:
            if isinstance(item, SessionDigest):
                parsed.append(item)
            elif isinstance(item, dict) and str(item.get("session_id") or "").strip():
                fields = {k: v for k, v in item.items() if k in SessionDigest.__dataclass_fields__}
                if isinstance(fields.get("top_tools"), list):
                    fields["top_tools"] = tuple(fields["top_tools"])
                parsed.append(SessionDigest(**fields))
        ordered = sort_digests(parsed)
        if ordered == self._digests and active == self._active_id and bool(more) == self._more:
            # Nothing changed: reopening the popup, or a refresh that found the
            # same chats, must not throw away rows the user is looking at.
            return
        self._active_id = active
        self._digests = ordered
        self._more = bool(more)
        self._rebuild()

    def set_automations(
        self, summaries: Sequence[Any], *, status: str = "", available: bool = True
    ) -> None:
        """Render the Automations tab: one row per ``automation_id``.
        ``available`` = the gateway offers automations (else no tab at all)."""
        grouped = [dict(s) for s in group_by_automation(summaries or [])]
        text = str(status or "").strip()
        if (
            grouped == self._automations
            and text == self._automation_status
            and bool(available) == self._automations_available
        ):
            # Same rows: only their relative times move ("last 3 min ago").
            for row in self._auto_rows:
                row.refresh_times()
            return
        self._automations = grouped
        self._automation_status = text
        self._automations_available = bool(available)
        if not self._automations_available and self._tab == "automations":
            self._tab = "sessions"
        self._rebuild()

    @property
    def automation_rows(self) -> List["AutomationTabRow"]:
        """The rows of the Automations tab (archived ones only when shown)."""
        return list(self._auto_rows)

    @property
    def automation_tab_rows(self) -> List[AutomationTabRow]:
        return list(self._auto_rows)

    def _clear(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _rebuild(self) -> None:
        self._rebuild_sessions()
        self._rebuild_automations()

    def _rebuild_sessions(self) -> None:
        self._clear(self.list_layout)
        self._rows = []
        self._group_labels = {}
        self.load_more_button = None
        titles = {str(s.get("automation_id")): str(s.get("title") or "") for s in self._automations}
        by_group: Dict[str, List[SessionDigest]] = {}
        for digest in self._digests:
            by_group.setdefault(recency_group(digest.last_activity), []).append(digest)
        for group in RECENCY_GROUPS:
            entries = by_group.get(group)
            if not entries:
                continue
            label = QLabel(group.upper(), self.list_host)
            label.setObjectName("switcherGroup")
            self.list_layout.addWidget(label)
            self._group_labels[group] = label
            for digest in entries:
                row = SessionRow(
                    digest,
                    active=digest.session_id == self._active_id,
                    parent=self.list_host,
                    automation_title=titles.get(digest.automation_id, ""),
                )
                row.automation_requested.connect(self._on_automation_chosen)
                row.archive_requested.connect(self.archive_requested.emit)
                row.chosen.connect(self._on_row_chosen)
                row.rename_committed.connect(self.rename_requested.emit)
                row.focus_requested.connect(self._on_row_hovered)
                self.list_layout.addWidget(row)
                self._rows.append(row)
        if self._more:
            button = QPushButton("Load more sessions", self.list_host)
            button.setObjectName("switcherLoadMore")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(self._on_load_more)
            self.list_layout.addWidget(button)
            self.load_more_button = button
        self.list_layout.addStretch(1)
        self._after_rebuild()

    def _rebuild_automations(self) -> None:
        self._clear(self.auto_layout)
        self._auto_rows = []
        if self._automation_status:
            status = QLabel(self._automation_status, self.auto_host)
            status.setObjectName("switcherStatus")
            status.setWordWrap(True)
            self.auto_layout.addWidget(status)
        show_archived = self.show_archived.isChecked()
        for summary in self._automations:
            if summary.get("status") == "archived" and not show_archived:
                continue
            row = AutomationTabRow(summary, parent=self.auto_host)
            row.open_requested.connect(self._on_automation_open)
            row.control_requested.connect(self._on_row_control)
            pending = self._pending.get(row.automation_id)
            if pending is not None:
                control, before, _token = pending
                if command_confirmed(control, before, summary):
                    del self._pending[row.automation_id]
                else:
                    row.set_pending(control)
            row.focus_requested.connect(self._on_row_hovered)
            self.auto_layout.addWidget(row)
            self._auto_rows.append(row)
        self.auto_layout.addStretch(1)
        self._after_rebuild()

    def _after_rebuild(self) -> None:
        self.tab_bar.setVisible(self._automations_available)
        self._refresh_count()
        self._apply_filter()
        if self._tab == "sessions":
            self._select_active()
        else:
            self._select_index(self._first_visible_index())
        self._fit_list()
        self._grow_to_rows()

    def _grow_to_rows(self) -> None:
        """An open popup grows (never shrinks) up to its full height when rows
        arrive after it opened."""
        if not self.isVisible():
            return
        layout, host, scroll = (
            (self.list_layout, self.list_host, self.scroll)
            if self._tab == "sessions"
            else (self.auto_layout, self.auto_host, self.auto_scroll)
        )
        layout.activate()
        wanted = self.height() - scroll.height() + host.sizeHint().height()
        target = min(SWITCHER_HEIGHT, wanted)
        if target > self.height():
            self.resize(SWITCHER_WIDTH, target)

    def _fit_list(self) -> None:
        """Settle rows built without a resize to elide them (see 0.6 notes)."""
        for row in list(self._rows) + list(self._auto_rows):
            row.elide_labels(self.width() - 60)
        self.list_layout.activate()
        self.auto_layout.activate()

    def _refresh_count(self) -> None:
        """The tab labels carry the counts ("Sessions · 146+", "Automations ·
        4 · 2 new"); their tooltips carry the detail."""
        if not hasattr(self, "tab_buttons"):
            return
        total = len(self._digests)
        plus = "+" if self._more else ""
        today = sum(1 for d in self._digests if recency_group(d.last_activity) == "Today")
        # The gateway reports no total: "N+" while more pages exist.
        detail = [f"{total}{plus} session{'s' if total != 1 or self._more else ''}"]
        if today:
            detail.append(f"{today} today")
        self._sessions_detail = " · ".join(detail)
        self.tab_buttons["sessions"].setText(f"Conversations · {total}{plus}")
        self.tab_buttons["sessions"].setToolTip(f"{self._sessions_detail} (⌘1)")

        archived = sum(1 for s in self._automations if s.get("status") == "archived")
        listed = len(self._automations) - (0 if self.show_archived.isChecked() else archived)
        unread = attention_total(self._automations)
        detail = [f"{listed} automation{'s' if listed != 1 else ''}"]
        if archived:
            detail.append(
                f"{archived} archived" + (" (hidden)" if not self.show_archived.isChecked() else "")
            )
        if unread:
            detail.append(f"{unread} new")
        self._automations_detail = " · ".join(detail)
        self.tab_buttons["automations"].setText(
            f"Automations · {listed}" + (f" · {unread} new" if unread else "")
        )
        self.tab_buttons["automations"].setToolTip(f"{self._automations_detail} (⌘2)")
        self._count_text = (
            self._sessions_detail if self._tab == "sessions" else self._automations_detail
        )

    @property
    def count_text(self) -> str:
        """The current tab's count detail (the tab's tooltip)."""
        return self._count_text

    # -------------------------------------------------------------- filtering

    def _apply_filter(self) -> None:
        if not hasattr(self, "empty_label"):
            return
        query = self.search_edit.text()
        visible_groups: Dict[str, bool] = {}
        any_visible = False
        for row in self._rows:
            visible = session_matches_query(row.digest, query)
            row.setVisible(visible)
            group = recency_group(row.digest.last_activity)
            visible_groups[group] = visible_groups.get(group, False) or visible
            any_visible = any_visible or visible
        for group, label in self._group_labels.items():
            label.setVisible(bool(visible_groups.get(group)))
        any_automation = False
        for row in self._auto_rows:
            visible = row.matches(query)
            row.setVisible(visible)
            any_automation = any_automation or visible
        if self._tab == "sessions":
            if not self._rows:
                self.empty_label.setText("No sessions yet. Start one with New session.")
                self.empty_label.show()
            elif not any_visible:
                self.empty_label.setText("No session matches this filter.")
                self.empty_label.show()
            else:
                self.empty_label.hide()
        else:
            if not self._auto_rows and not self._automation_status:
                self.empty_label.setText(
                    "No automation yet. Schedule a conversation with the clock button."
                )
                self.empty_label.show()
            elif self._auto_rows and not any_automation:
                self.empty_label.setText("No automation matches this filter.")
                self.empty_label.show()
            else:
                self.empty_label.hide()
        if self._selected_index >= 0:
            row = self._row_at(self._selected_index)
            if row is None or not row.isVisibleTo(self):
                self._select_index(self._first_visible_index())

    def visible_rows(self) -> List[QWidget]:
        """Rows of the current tab the filter kept — asked of the popup itself,
        so the answer is the same whether or not it is on screen."""
        rows = self._rows if self._tab == "sessions" else self._auto_rows
        return [row for row in rows if row.isVisibleTo(self)]

    # ------------------------------------------------------------- selection

    def _row_at(self, index: int) -> Optional[QWidget]:
        rows = self.visible_rows()
        if 0 <= index < len(rows):
            return rows[index]
        return None

    def _first_visible_index(self) -> int:
        return 0 if self.visible_rows() else -1

    def _active_index(self) -> int:
        for index, row in enumerate(self.visible_rows()):
            if getattr(row, "session_id", None) == self._active_id:
                return index
        return self._first_visible_index()

    def _select_index(self, index: int) -> None:
        rows = self.visible_rows()
        for row in list(self._rows) + list(self._auto_rows):
            row.set_selected(False)
        if not rows or index < 0:
            self._selected_index = -1
            return
        clamped = max(0, min(int(index), len(rows) - 1))
        self._selected_index = clamped
        row = rows[clamped]
        row.set_selected(True)
        scroll = self.scroll if self._tab == "sessions" else self.auto_scroll
        scroll.ensureWidgetVisible(row, 0, 40)

    def _select_active(self) -> None:
        self._select_index(self._active_index())

    def _on_row_hovered(self, row: Any) -> None:
        rows = self.visible_rows()
        if row in rows:
            self._selected_index = rows.index(row)
            for other in list(self._rows) + list(self._auto_rows):
                other.set_selected(other is row)

    @property
    def selected_session_id(self) -> str:
        row = self._row_at(self._selected_index)
        return str(getattr(row, "session_id", "") or "") if row is not None else ""

    @property
    def selected_automation_id(self) -> str:
        row = self._row_at(self._selected_index)
        return (
            str(getattr(row, "automation_id", "") or "")
            if row is not None and self._tab == "automations"
            else ""
        )

    # ---------------------------------------------------------------- actions

    def _on_row_chosen(self, session_id: str) -> None:
        self.session_chosen.emit(str(session_id))
        self.close()

    def _on_automation_chosen(self, automation_id: str) -> None:
        self.automation_chosen.emit(str(automation_id))
        self.close()

    def _on_automation_open(self, automation_id: str, where: str) -> None:
        self.automation_open_requested.emit(str(automation_id), str(where))
        self.close()

    def _on_new_chat(self) -> None:
        self.new_chat_requested.emit()
        self.close()

    PENDING_TIMEOUT_MS = 30_000

    def _on_row_control(self, automation_id: str, control: str) -> None:
        from PyQt5.QtCore import QTimer

        summary = next(
            (s for s in self._automations if s.get("automation_id") == automation_id), {}
        )
        self._pending_token += 1
        token = self._pending_token
        self._pending[automation_id] = (control, dict(summary), token)
        # Owned by the popup: it dies with it, never fires into a deleted one.
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._expire_pending(automation_id, token))
        timer.timeout.connect(timer.deleteLater)
        timer.start(self.PENDING_TIMEOUT_MS)
        for row in self._auto_rows:
            if row.automation_id == automation_id:
                row.set_pending(control)
        self.automation_control_requested.emit(automation_id, control)

    def is_pending(self, automation_id: str) -> bool:
        return automation_id in self._pending

    def command_failed(self, automation_id: str, reason: str) -> None:
        """The gateway refused (or never answered): the card's button comes
        back, its tooltip carrying the reason; the status line says it too."""
        self._pending.pop(automation_id, None)
        for row in self._auto_rows:
            if row.automation_id == automation_id:
                row.restore_state(reason)
        self.set_status(reason, tone="warn")

    def _expire_pending(self, automation_id: str, token: int) -> None:
        pending = self._pending.get(automation_id)
        if pending is not None and pending[2] == token:
            self.command_failed(
                automation_id,
                "The gateway has not confirmed the change yet; it may still be applying it.",
            )

    def _on_new_automation(self) -> None:
        self.new_automation_requested.emit()
        self.close()

    def select_automation(self, automation_id: str) -> bool:
        """Select a row of the Automations tab (after creating it)."""
        for index, row in enumerate(self.visible_rows()):
            if getattr(row, "automation_id", None) == automation_id:
                self._select_index(index)
                return True
        return False

    def _on_load_more(self) -> None:
        if self.load_more_button is not None:
            self.load_more_button.setEnabled(False)
            self.load_more_button.setText("Loading…")
        self.load_more_requested.emit()

    def open_at(self, global_pos, *, screen_geometry=None) -> None:
        """Show the popup at ``global_pos``, kept inside the screen.

        Clamped with the popup's ACTUAL size after layout — its minimum size
        wins over any requested width, so a constant would let content push it
        off screen — on ``screen_geometry``, else the screen holding the anchor."""
        self.adjustSize()
        self.resize(SWITCHER_WIDTH, min(SWITCHER_HEIGHT, self.height() or SWITCHER_HEIGHT))
        layout = self.layout()
        if layout is not None:
            layout.activate()
        minimum = self.minimumSizeHint()
        width = max(self.width(), minimum.width())
        height = max(self.height(), minimum.height())
        self.resize(width, height)
        x, y = int(global_pos.x()), int(global_pos.y())
        if screen_geometry is None:
            screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry() if screen is not None else None
        if screen_geometry is not None:
            x = max(
                screen_geometry.x() + 8,
                min(x, screen_geometry.x() + screen_geometry.width() - width - 8),
            )
            y = max(
                screen_geometry.y() + 8,
                min(y, screen_geometry.y() + screen_geometry.height() - height - 8),
            )
        self.move(x, y)
        self.show()
        self.raise_()
        self.search_edit.clear()
        self.search_edit.setFocus(Qt.ShortcutFocusReason)
        if self._tab == "sessions":
            self._select_active()
        else:
            self._select_index(self._first_visible_index())

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        for row in list(self._rows) + list(self._auto_rows):
            row.elide_labels(self.width() - 60)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        # ←/→ switch tabs while the filter is empty (else they move the caret).
        if (
            obj is self.search_edit
            and event.type() == QEvent.KeyPress
            and not self.search_edit.text()
        ):
            if (
                event.key() in (Qt.Key_Left, Qt.Key_Right)
                and not event.modifiers()
                and self._automations_available
            ):
                self.set_tab("sessions" if event.key() == Qt.Key_Left else "automations", emit=True)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key_Escape:
            self.close()
            event.accept()
            return
        if modifiers & Qt.ControlModifier and key in (Qt.Key_1, Qt.Key_2):
            self.set_tab("sessions" if key == Qt.Key_1 else "automations", emit=True)
            event.accept()
            return
        if key in (Qt.Key_Down, Qt.Key_Up):
            step = 1 if key == Qt.Key_Down else -1
            self._select_index(max(0, self._selected_index + step))
            selected = self._row_at(self._selected_index)
            if selected is not None:
                selected.setFocus(Qt.TabFocusReason)
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self._tab == "sessions":
                session_id = self.selected_session_id
                if session_id:
                    self._on_row_chosen(session_id)
            else:
                automation_id = self.selected_automation_id
                if automation_id:
                    self._on_automation_open(automation_id, "latest")
            event.accept()
            return
        if key == Qt.Key_N and modifiers & Qt.ControlModifier:
            self._on_new_chat()
            event.accept()
            return
        super().keyPressEvent(event)
