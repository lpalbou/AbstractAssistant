"""The session switcher: a searchable list of sessions with real metrics.

The header's session control opens this popup instead of a plain dropdown.
Every row shows what the session actually holds — when it was last touched, how many
turns and tool calls it ran, the tokens and wall time it spent, the folder it
worked in, and whether the last question went unanswered — so picking one
is a decision made on facts rather than on a truncated first sentence.

The rows are the gateway's sessions (see `core/gateway_sessions`); the popup
first paints the cached list and is re-rendered when the gateway answers, with
a header line when the rows are only cached. Rows are grouped by recency,
filtered as you type, and can be renamed (a local label) or removed from the
list in place (asked inside the row, never with a modal — the gateway keeps
the runs). The widget owns no data: it renders `SessionDigest` values and emits
what the user chose.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from pathlib import Path

from PyQt5.QtCore import QEvent, QSize, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFontMetrics
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
    format_count,
    format_duration_ms,
    format_tokens,
    recency_group,
    relative_time,
    session_matches_query,
    sort_digests,
    workspace_label,
)
from ..core.automations import (
    attention_total,
    automation_controls,
    group_by_automation,
    last_run_text,
    next_run_text,
    occurrence_in_progress,
    status_pill,
    trigger_summary,
)
from ..icons import symbol_icon
from ..theme import METRICS, THEME
from .automations import automation_row_qss
from .styles import alpha, dialog_stylesheet, refresh_style

__all__ = ["AutomationTabRow", "SessionRow", "SessionSwitcher", "SESSION_SWITCHER_QSS", "folder_button", "open_folder"]


SWITCHER_WIDTH = 460
SWITCHER_HEIGHT = 560
# Chips beyond this would push the row wider than the popup; the rest of the
# facts stay in the row's tooltip.
_MAX_METRICS = 5


def _same_text(left: str, right: str) -> str:
    """Do two strings say the same thing (ignoring case and any ellipsis)?"""
    def _key(value: str) -> str:
        return " ".join(str(value or "").lower().replace("…", "").split()).strip()

    a, b = _key(left), _key(right)
    return bool(a and b and (a == b or a.startswith(b) or b.startswith(a)))


def _build_qss() -> str:
    return f"""
    QFrame#switcherCard {{
        background: {THEME.surface_sunken};
        border: 1px solid {THEME.border_strong};
        border-radius: {METRICS.radius_card}px;
    }}
    QLabel#switcherTitle {{
        color: {THEME.text_strong};
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 0.01em;
    }}
    QLabel#switcherCount {{
        color: {THEME.text_faint};
        font-size: 11px;
        font-weight: 600;
    }}
    QLineEdit#switcherSearch {{
        background: {THEME.surface_raised};
        border: 1px solid {THEME.border_subtle};
        border-radius: 9px;
        padding: 6px 10px;
        color: {THEME.text_primary};
        font-size: 12px;
        selection-background-color: {alpha(THEME.accent, 0.35)};
    }}
    QLineEdit#switcherSearch:focus {{
        border-color: {THEME.accent_border};
        background: {THEME.surface_raised};
    }}
    QLabel#switcherGroup {{
        color: {THEME.text_faint};
        font-size: 10px;
        font-weight: 800;
        letter-spacing: 0.10em;
        padding: 10px 2px 2px 2px;
    }}
    QLabel#switcherStatus {{
        color: {THEME.text_faint};
        font-size: 11px;
    }}
    QLabel#switcherStatus[tone="warn"] {{ color: {THEME.attention}; }}
    QLabel#switcherEmpty {{
        color: {THEME.text_faint};
        font-size: 12px;
        padding: 28px 8px;
    }}

    QFrame#sessionRow {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 10px;
    }}
    QFrame#sessionRow:hover {{
        background: {THEME.overlay_faint};
        border-color: {THEME.border_subtle};
    }}
    QFrame#sessionRow[selected="true"] {{
        background: {alpha(THEME.accent, 0.10)};
        border-color: {THEME.accent_border};
    }}
    QFrame#sessionRow[active="true"] {{
        background: {alpha(THEME.accent, 0.14)};
        border-color: {THEME.accent_border};
    }}
    QFrame#rowSpine {{
        background: {THEME.border_subtle};
        border: none;
        border-radius: 2px;
    }}
    QFrame#rowSpine[tone="active"] {{ background: {THEME.accent}; }}
    QFrame#rowSpine[tone="fresh"] {{ background: {THEME.positive}; }}
    QFrame#rowSpine[tone="warn"] {{ background: {THEME.attention}; }}
    QFrame#rowSpine[tone="idle"] {{ background: {alpha(THEME.text_faint, 0.45)}; }}

    QLabel#rowTitle {{
        color: {THEME.text_primary};
        font-size: 12px;
        font-weight: 700;
    }}
    QFrame#sessionRow[active="true"] QLabel#rowTitle {{ color: {THEME.text_strong}; }}
    QLabel#rowTime {{
        color: {THEME.text_faint};
        font-size: 10px;
        font-weight: 700;
    }}
    QLabel#rowPreview {{
        color: {THEME.text_muted};
        font-size: 11px;
    }}
    QLabel#rowMetric {{
        color: {THEME.text_muted};
        font-size: 10px;
        font-weight: 600;
    }}
    QLabel#rowMetric[tone="warn"] {{ color: {THEME.attention}; }}
    QLabel#rowMetric[tone="accent"] {{ color: {THEME.accent_text}; }}
    QLabel#rowMetricIcon {{ background: transparent; border: none; }}
    QLabel#rowBadge {{
        color: {THEME.accent_text};
        background: {alpha(THEME.accent, 0.16)};
        border: 1px solid {THEME.accent_border};
        border-radius: 7px;
        padding: 0px 6px;
        font-size: 9px;
        font-weight: 800;
        letter-spacing: 0.06em;
    }}
    QLineEdit#rowRename {{
        background: {THEME.surface_raised};
        border: 1px solid {THEME.accent_border};
        border-radius: 7px;
        padding: 3px 7px;
        color: {THEME.text_strong};
        font-size: 12px;
        font-weight: 700;
    }}
    QPushButton#rowAction {{
        min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px;
        padding: 0px;
        border: none;
        border-radius: 7px;
        background: transparent;
    }}
    QPushButton#rowAction:hover {{ background: {THEME.overlay_hover}; }}
    QLabel#rowConfirm {{
        color: {THEME.danger_text};
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#rowConfirmYes {{
        color: {THEME.text_strong};
        background: {THEME.danger_bg};
        border: 1px solid {alpha(THEME.danger, 0.55)};
        border-radius: 8px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#rowConfirmYes:hover {{ background: {alpha(THEME.danger, 0.28)}; }}
    QPushButton#rowConfirmNo {{
        color: {THEME.text_secondary};
        background: {THEME.overlay_faint};
        border: 1px solid {THEME.border_subtle};
        border-radius: 8px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 600;
    }}
    QPushButton#rowConfirmNo:hover {{ background: {THEME.overlay_hover}; }}

    QPushButton#switcherPrimary {{
        color: {THEME.primary_text};
        background: {THEME.primary};
        border: none;
        border-radius: 9px;
        padding: 5px 12px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#switcherPrimary:hover {{ background: {THEME.primary_hover}; }}
    QPushButton#switcherScope {{
        color: {THEME.text_muted};
        background: transparent;
        border: 1px solid {THEME.border_subtle};
        border-radius: 9px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 600;
    }}
    QPushButton#switcherScope:checked {{
        color: {THEME.accent_text};
        border-color: {THEME.accent_border};
    }}
    QPushButton#switcherTab {{
        color: {THEME.text_muted};
        background: {THEME.overlay_faint};
        border: 1px solid {THEME.border_subtle};
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#switcherTab:checked {{
        color: {THEME.accent_text};
        background: {alpha(THEME.accent, 0.14)};
        border-color: {THEME.accent_border};
    }}
    QPushButton#rowFolder, QPushButton#rowIcon {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 0px;
    }}
    QPushButton#rowFolder:hover, QPushButton#rowIcon:hover {{
        background: {THEME.overlay_hover};
        border-color: {THEME.border_subtle};
    }}
    QPushButton#switcherLoadMore {{
        color: {THEME.accent_text};
        background: {THEME.overlay_faint};
        border: 1px solid {THEME.border_subtle};
        border-radius: 8px;
        padding: 6px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#switcherLoadMore:hover {{ background: {THEME.overlay_hover}; }}
    QFrame#autoTabRow {{
        background: {THEME.overlay_faint};
        border: 1px solid {THEME.border_subtle};
        border-radius: 10px;
    }}
    QFrame#autoTabRow:hover {{ border-color: {THEME.border_strong}; }}
    QFrame#autoTabRow[selected="true"] {{
        background: {alpha(THEME.accent, 0.10)};
        border-color: {THEME.accent_border};
    }}
    QLabel#autoTabTitle {{ color: {THEME.text_strong}; font-size: 12px; font-weight: 700; }}
    QLabel#autoTabMeta {{ color: {THEME.text_muted}; font-size: 10px; font-weight: 600; }}
    QLabel#autoTabResult {{ color: {THEME.text_secondary}; font-size: 11px; }}
    QLabel#autoTabResult[tone="failed"] {{ color: {THEME.danger_text}; }}
    QLabel#autoPill {{
        border-radius: 8px;
        padding: 1px 7px;
        font-size: 9px;
        font-weight: 800;
        letter-spacing: 0.04em;
        color: {THEME.text_muted};
        background: {alpha(THEME.text_faint, 0.16)};
        border: 1px solid {alpha(THEME.text_faint, 0.35)};
    }}
    QLabel#autoPill[tone="active"] {{ color: {THEME.positive}; background: {THEME.positive_bg}; border-color: {alpha(THEME.positive, 0.45)}; }}
    QLabel#autoPill[tone="paused"] {{ color: {THEME.warning}; background: {THEME.warning_bg}; border-color: {alpha(THEME.warning, 0.45)}; }}
    QLabel#autoPill[tone="running"] {{ color: {THEME.accent_text}; background: {THEME.accent_bg}; border-color: {THEME.accent_border}; }}
    QLabel#autoPill[tone="waiting"] {{ color: {THEME.attention_text}; background: {THEME.attention_bg}; border-color: {THEME.attention_border}; }}
    QLabel#autoPill[tone="failed"] {{ color: {THEME.danger_text}; background: {THEME.danger_bg}; border-color: {alpha(THEME.danger, 0.55)}; }}
    QLabel#autoNew {{
        color: {THEME.accent_text};
        font-size: 9px;
        font-weight: 800;
    }}
    QLabel#switcherHint {{
        color: {THEME.text_faint};
        font-size: 10px;
    }}
    QFrame#switcherFooter, QFrame#switcherHeader {{
        background: transparent;
        border: none;
    }}
    QScrollArea#switcherScroll, QWidget#switcherList {{
        background: transparent;
        border: none;
    }}
    """


def build_switcher_qss() -> str:
    """Rebuilt on demand so a theme switch reaches the popup too."""
    return _build_qss()


SESSION_SWITCHER_QSS: str = build_switcher_qss()


def _metric(icon: str, text: str, tooltip: str, tone: str = "") -> QWidget:
    """One small icon+number chip on a row's metric line."""
    host = QWidget()
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(3)
    color = {"warn": THEME.attention, "accent": THEME.accent_text}.get(tone, THEME.text_muted)
    if icon:
        glyph = QLabel()
        glyph.setObjectName("rowMetricIcon")
        glyph.setPixmap(symbol_icon(icon, color=color, size=11).pixmap(11, 11))
        row.addWidget(glyph, 0, Qt.AlignVCenter)
    label = QLabel(text)
    label.setObjectName("rowMetric")
    if tone:
        label.setProperty("tone", tone)
    row.addWidget(label, 0, Qt.AlignVCenter)
    host.setToolTip(tooltip)
    return host


class SessionRow(QFrame):
    """One session: title, preview, metrics, and in-place rename. (No delete:
    a session exists iff the gateway lists it, and the gateway has none.)"""

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
        super().__init__(parent)
        self.digest = digest
        self.session_id = digest.session_id
        self._active = bool(active)
        self._selected = False
        self.setObjectName("sessionRow")
        self.setProperty("active", "true" if active else "false")
        self.setProperty("selected", "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMinimumWidth(0)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 7)
        root.setSpacing(9)

        self.spine = QFrame()
        self.spine.setObjectName("rowSpine")
        self.spine.setFixedWidth(3)
        self.spine.setProperty("tone", self._spine_tone())
        self.spine.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        root.addWidget(self.spine)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        root.addLayout(column, 1)

        # -- line 1: title, badges, time, actions -------------------------- #
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self.title_label = QLabel(digest.display_title)
        self.title_label.setObjectName("rowTitle")
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.title_label, 1)

        self.rename_edit = QLineEdit(self)
        self.rename_edit.setObjectName("rowRename")
        self.rename_edit.hide()
        self.rename_edit.returnPressed.connect(self._commit_rename)
        self.rename_edit.installEventFilter(self)
        head.addWidget(self.rename_edit, 1)

        # A discussion is an ordinary session forked from an automation: the
        # gateway's `session_kind` says so (never the id), and the badge names
        # the automation and opens it.
        self.about_button: Optional[QPushButton] = None
        if digest.session_kind == "discussion":
            label = f"about automation {automation_title}" if automation_title else "about an automation"
            self.about_button = QPushButton(label, self)
            self.about_button.setObjectName("aboutAutomation")
            self.about_button.setCursor(Qt.PointingHandCursor)
            self.about_button.setToolTip(
                "A session seeded with this automation's history up to one run; the automation's "
                "files are mounted read-only and the session has its own writable workspace. "
                "Click to open the automation."
            )
            self.about_button.clicked.connect(
                lambda: self.automation_requested.emit(self.digest.automation_id)
            )
            head.addWidget(self.about_button, 0, Qt.AlignVCenter)

        if active:
            badge = QLabel("ACTIVE")
            badge.setObjectName("rowBadge")
            head.addWidget(badge, 0, Qt.AlignVCenter)

        self.time_label = QLabel(relative_time(digest.last_activity))
        self.time_label.setObjectName("rowTime")
        self.time_label.setToolTip(self._time_tooltip())
        head.addWidget(self.time_label, 0, Qt.AlignVCenter)

        self.rename_button = QPushButton()
        self.rename_button.setObjectName("rowAction")
        self.rename_button.setIcon(symbol_icon("square-pen", color=THEME.text_muted, size=12))
        self.rename_button.setIconSize(QSize(12, 12))
        self.rename_button.setToolTip("Rename this session")
        self.rename_button.setCursor(Qt.PointingHandCursor)
        self.rename_button.clicked.connect(self.start_rename)
        self.rename_button.hide()
        head.addWidget(self.rename_button, 0, Qt.AlignVCenter)

        column.addLayout(head)

        # -- line 2: preview ----------------------------------------------- #
        # The preview is the chat's latest question; when that is also its
        # title (a one-turn chat) repeating it says nothing.
        preview_text = "" if _same_text(digest.preview, digest.display_title) else digest.preview
        self._preview_text = preview_text
        # Parented on construction, like every other widget here: `setVisible`
        # on a PARENTLESS widget shows a real top-level window. Two of those per
        # row cost ~16 ms and four window-activation flips, which for 74 chats
        # meant a 1.2 s rebuild and — because macOS closes popups when another
        # window takes key status — the switcher closing itself.
        self.preview_label = QLabel(preview_text, self)
        self.preview_label.setObjectName("rowPreview")
        self.preview_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.preview_label.setVisible(bool(preview_text))
        column.addWidget(self.preview_label)

        # -- line 3: metrics ------------------------------------------------ #
        self.metrics_host = QWidget(self)
        metrics = QHBoxLayout(self.metrics_host)
        metrics.setContentsMargins(0, 1, 0, 0)
        metrics.setSpacing(10)
        for widget in self._metric_widgets()[:_MAX_METRICS]:
            metrics.addWidget(widget, 0, Qt.AlignVCenter)
        metrics.addStretch(1)
        # Never let the chips widen the row: the popup's width rules, and any
        # metric that does not fit is in the row's tooltip.
        self.metrics_host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.metrics_host.setVisible(self._has_metrics())
        column.addWidget(self.metrics_host)

        self.setToolTip(self._tooltip())

    # ------------------------------------------------------------- appearance

    def _spine_tone(self) -> str:
        digest = self.digest
        if self._active:
            return "active"
        if digest.detailed and (digest.failed_tools or digest.unanswered):
            return "warn"
        group = recency_group(digest.last_activity)
        if group in {"Today", "Yesterday"}:
            return "fresh"
        if group == "Older":
            return "idle"
        return "normal"

    def _has_metrics(self) -> bool:
        # A gateway row whose transcript is not cached yet still knows its turns.
        return bool(self.digest.detailed or self.digest.turns)

    def _metric_widgets(self) -> List[QWidget]:
        digest = self.digest
        out: List[QWidget] = []
        if digest.empty:
            out.append(_metric("message-square", "empty", "This session has no messages yet.", tone="warn"))
            return out
        if digest.turns:
            tooltip = (
                f"{digest.turns} question(s) you asked · {digest.answers} answer(s)"
                if digest.detailed
                else f"{digest.turns} turn(s) on the gateway"
            )
            out.append(_metric("message-square", format_count(digest.turns), tooltip))
        if digest.state == "waiting":
            out.append(_metric("hand", "waiting", "A run of this session is waiting for you.", tone="warn"))
        elif digest.state == "running":
            out.append(_metric("clock", "running", "A run of this session is still running.", tone="accent"))
        if digest.tool_calls:
            tools = ", ".join(digest.top_tools) if digest.top_tools else ""
            tooltip = f"{digest.tool_calls} tool call(s)"
            if tools:
                tooltip += f" · most used: {tools}"
            out.append(_metric("wrench", format_count(digest.tool_calls), tooltip))
        if digest.total_tokens:
            out.append(
                _metric(
                    "",
                    format_tokens(digest.total_tokens),
                    f"{digest.input_tokens:,} input + {digest.output_tokens:,} output tokens across {digest.runs} run(s)",
                )
            )
        duration = format_duration_ms(digest.duration_ms)
        if duration:
            out.append(_metric("clock", duration, "Total time the gateway spent running this session."))
        if digest.workspace_root:
            # Clickable: opens the folder when it is on this machine.
            out.append(folder_button(digest.workspace_root, parent=self))
        elif digest.state and not digest.workspace_reported:
            # A gateway session whose `/runs` row does not carry the folder.
            out.append(missing_folder_button("/runs row workspace_root", parent=self))
        if digest.failed_tools:
            out.append(
                _metric(
                    "circle-alert",
                    format_count(digest.failed_tools),
                    f"{digest.failed_tools} tool call(s) reported a failure.",
                    tone="warn",
                )
            )
        if digest.unanswered:
            out.append(_metric("hand", "no reply", "The last message is yours: this session never got an answer.", tone="warn"))
        return out

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
        lines.append(f"Session id: {digest.session_id}")
        return "\n".join(lines)

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self.setProperty("selected", "true" if selected else "false")
        refresh_style(self)

    @property
    def selected(self) -> bool:
        return self._selected

    def elide_labels(self, width: int) -> None:
        """Keep one line per label whatever the popup's width is."""
        available = max(80, int(width) - 150)
        metrics = QFontMetrics(self.title_label.font())
        self.title_label.setText(metrics.elidedText(self.digest.display_title, Qt.ElideRight, available))
        if self._preview_text:
            preview_metrics = QFontMetrics(self.preview_label.font())
            self.preview_label.setText(
                preview_metrics.elidedText(self._preview_text, Qt.ElideRight, max(80, int(width) - 60))
            )

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
        if obj is self.rename_edit and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.cancel_rename()
            return True
        return super().eventFilter(obj, event)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.rename_button.show()
        self.focus_requested.emit(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.rename_button.hide()
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


def _icon_button(icon: str, tooltip: str, *, parent: QWidget, name: str = "rowIcon", tint: str = "") -> QPushButton:
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
        f"Open {path}" if local else f"on the gateway host: {path}",
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
        "folder", f"The gateway does not report this folder ({field}).", parent=parent, name="rowFolder",
        tint=THEME.text_faint,
    )
    button.setEnabled(False)
    button.setCursor(Qt.ArrowCursor)
    button.folder_path = ""
    return button


# --------------------------------------------------------- automation tab


class AutomationTabRow(QFrame):
    """One automation in the Automations tab.

    Line 1: title (elided) + status pill (+ "N new"); line 2: cadence · context
    · last … ago · next in …; line 3: the last result (red when failed); on the
    right, an icon toolbar chosen by the automation's state (the same rules as
    the automation view: ``core.automations.automation_controls``)."""

    open_requested = pyqtSignal(str, str)  # automation_id, "top" | "latest"
    edit_requested = pyqtSignal(str)
    control_requested = pyqtSignal(str, str)  # automation_id, pause|resume|run_now|stop_current|archive
    focus_requested = pyqtSignal(object)

    def __init__(self, summary: Dict[str, Any], *, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("autoTabRow")
        self.setProperty("selected", "false")
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.summary = dict(summary)
        self.automation_id = str(summary.get("automation_id") or "")
        self._selected = False
        aid = self.automation_id

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 7, 8, 7)
        outer.setSpacing(3)

        # -- line 1: title, pill, new count ------------------------------------
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self.title_label = QLabel(str(summary.get("title") or "Automation"), self)
        self.title_label.setObjectName("autoTabTitle")
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.title_label, 1)
        pill_text, pill_tone = status_pill(summary)
        self.pill = QLabel(pill_text, self)
        self.pill.setObjectName("autoPill")
        self.pill.setProperty("tone", pill_tone)
        head.addWidget(self.pill, 0, Qt.AlignVCenter)
        attention = summary.get("attention") if isinstance(summary.get("attention"), dict) else {}
        unseen = int(attention.get("unseen_count") or 0)
        self.new_badge = QLabel(f"{unseen} new", self)
        self.new_badge.setObjectName("autoNew")
        self.new_badge.setVisible(unseen > 0)
        head.addWidget(self.new_badge, 0, Qt.AlignVCenter)
        outer.addLayout(head)

        # -- line 2: schedule and times; toolbar on the right ------------------
        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(6)
        self.meta_label = QLabel("", self)
        self.meta_label.setObjectName("autoTabMeta")
        self.meta_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        middle.addWidget(self.meta_label, 1)
        outer.addLayout(middle)

        # -- line 3: the last result (full width) --------------------------------
        last = summary.get("last_occurrence") if isinstance(summary.get("last_occurrence"), dict) else None
        result, failed = self._result_text(summary, last)
        self.result_label = QLabel(result, self)
        self.result_label.setObjectName("autoTabResult")
        self.result_label.setProperty("tone", "failed" if failed else "")
        self.result_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._result_text_full = result
        outer.addWidget(self.result_label)

        # -- the icon toolbar, right-aligned -------------------------------------
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(2)
        bottom.addStretch(1)
        controls = automation_controls(summary)
        self.buttons: Dict[str, QPushButton] = {}

        def add(key: str, icon: str, tooltip: str, state, slot) -> None:
            enabled, reason = state
            button = _icon_button(
                icon,
                tooltip if enabled else f"{tooltip} — {reason}",
                parent=self,
                tint=THEME.text_secondary if enabled else THEME.text_faint,
            )
            button.setEnabled(bool(enabled))
            button.clicked.connect(slot)
            bottom.addWidget(button, 0, Qt.AlignVCenter)
            self.buttons[key] = button

        always = (True, "")
        add("open", "eye", "Open", always, lambda: self.open_requested.emit(aid, "top"))
        if last is not None:
            add("last", "arrow-down-to-line", "Last run", always, lambda: self.open_requested.emit(aid, "latest"))
        if summary.get("status") == "paused":
            add("resume", "play", "Resume", controls["resume"], lambda: self.control_requested.emit(aid, "resume"))
        else:
            add("pause", "pause", "Pause", controls["pause"], lambda: self.control_requested.emit(aid, "pause"))
        add("run_now", "zap", "Run now", controls["run_now"], lambda: self.control_requested.emit(aid, "run_now"))
        if occurrence_in_progress(summary):
            add("stop_current", "stop", "Stop the current run", controls["stop_current"], lambda: self.control_requested.emit(aid, "stop_current"))
        add("revise", "square-pen", "Modify", controls["revise"], lambda: self.edit_requested.emit(aid))
        add("archive", "archive", "Archive", controls["archive"], self.ask_archive)
        root = summary.get("workspace_root")
        if isinstance(root, str) and root:
            self.folder = folder_button(root, parent=self)
        else:
            self.folder = missing_folder_button("AutomationSummary.workspace_root", parent=self)
        bottom.addWidget(self.folder, 0, Qt.AlignVCenter)
        self.controls_host = QWidget(self)
        self.controls_host.setLayout(bottom)
        outer.addWidget(self.controls_host)

        # -- archive confirmation, inside the row (never a modal) --------------
        self.confirm_host = QWidget(self)
        confirm = QHBoxLayout(self.confirm_host)
        confirm.setContentsMargins(0, 0, 0, 0)
        message = QLabel("Archive? History is kept; nothing runs any more.", self.confirm_host)
        message.setObjectName("rowConfirm")
        message.setWordWrap(True)
        confirm.addWidget(message, 1)
        self.archive_yes = QPushButton("Archive", self.confirm_host)
        self.archive_yes.setObjectName("rowConfirmYes")
        self.archive_yes.clicked.connect(self._confirm_archive)
        confirm.addWidget(self.archive_yes, 0)
        no = QPushButton("Cancel", self.confirm_host)
        no.setObjectName("rowConfirmNo")
        no.clicked.connect(self.cancel_archive)
        confirm.addWidget(no, 0)
        self.confirm_host.hide()
        outer.addWidget(self.confirm_host)

        self.refresh_times()
        self.setToolTip(f"{summary.get('title') or ''}\nAutomation id: {aid}")

    # ------------------------------------------------------------- content

    @staticmethod
    def _result_text(summary: Dict[str, Any], last: Optional[Dict[str, Any]]) -> tuple:
        if last is None:
            return "No run yet.", False
        status = str(last.get("status") or "")
        text = " ".join(str(last.get("excerpt") or "").split())
        if not text and status == "waiting":
            attention = summary.get("attention") if isinstance(summary.get("attention"), dict) else {}
            waits = [w for w in attention.get("waits") or [] if isinstance(w, dict) and w.get("prompt")]
            text = f"waiting for you: {' '.join(str(waits[0]['prompt']).split())}" if waits else "waiting for you"
        head = f"#{last.get('index')} {status}"
        return (f"{head}: {text}" if text else head), status == "failed"

    def refresh_times(self, now=None) -> None:
        """Line 2, relative to ``now`` (called again on every poll)."""
        trigger = self.summary.get("trigger") if isinstance(self.summary.get("trigger"), dict) else {}
        mode = "growing" if self.summary.get("context_mode") == "growing" else "independent"
        parts = [
            trigger_summary(trigger),
            mode,
            last_run_text(self.summary, now=now),
            next_run_text(self.summary, now=now),
        ]
        self._meta_text = " · ".join(p for p in parts if p)
        self.meta_label.setText(self._meta_text)
        self.meta_label.setToolTip(self._meta_text)

    @property
    def meta_text(self) -> str:
        return self._meta_text

    # ------------------------------------------------------------- archive

    def ask_archive(self) -> None:
        self.controls_host.hide()
        self.confirm_host.show()

    def cancel_archive(self) -> None:
        self.confirm_host.hide()
        self.controls_host.show()

    @property
    def confirming_archive(self) -> bool:
        return self.confirm_host.isVisibleTo(self)

    def _confirm_archive(self) -> None:
        self.cancel_archive()
        self.control_requested.emit(self.automation_id, "archive")

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

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self.setProperty("selected", "true" if selected else "false")
        refresh_style(self)

    def elide_labels(self, width: int) -> None:
        metrics = QFontMetrics(self.title_label.font())
        self.title_label.setText(
            metrics.elidedText(str(self.summary.get("title") or ""), Qt.ElideRight, max(60, int(width) - 170))
        )
        result_metrics = QFontMetrics(self.result_label.font())
        room = max(60, int(width) - 30)
        self.result_label.setText(result_metrics.elidedText(self._result_text_full, Qt.ElideRight, room))
        self.result_label.setToolTip(self._result_text_full)
        meta_metrics = QFontMetrics(self.meta_label.font())
        self.meta_label.setText(meta_metrics.elidedText(self._meta_text, Qt.ElideRight, max(80, int(width) - 30)))

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.focus_requested.emit(self)
        super().enterEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.LeftButton and not self.confirming_archive:
            self.open_requested.emit(self.automation_id, "top")
            return
        super().mouseReleaseEvent(event)


TAB_HINTS = {
    "sessions": "↑↓ move · ↵ open · ⌘1/⌘2 tabs · esc close",
    "automations": "↑↓ move · ↵ open · ⌘1/⌘2 tabs · esc close",
}


class SessionSwitcher(QDialog):
    """The popup: two tabs (Sessions | Automations), search, keyboard
    navigation, row actions."""

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
    automation_edit_requested = pyqtSignal(str)
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
        self.title_label = QLabel("Sessions")
        self.title_label.setObjectName("switcherTitle")
        header.addWidget(self.title_label, 0, Qt.AlignVCenter)
        self.count_label = QLabel("")
        self.count_label.setObjectName("switcherCount")
        # The count never widens the popup: it takes what the header leaves
        # and is elided (full text in its tooltip).
        self.count_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.count_label.setMinimumWidth(0)
        self._count_text = ""
        header.addWidget(self.count_label, 1, Qt.AlignVCenter)
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
        self.new_automation_button.setToolTip("Create an automation: a task that runs on a schedule")
        self.new_automation_button.clicked.connect(self._on_new_automation)
        header.addWidget(self.new_automation_button, 0, Qt.AlignVCenter)
        self.new_button = QPushButton("New session")
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
        for key, text, tip in (("sessions", "Sessions", "⌘1"), ("automations", "Automations", "⌘2")):
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
        self.list_layout.setContentsMargins(0, 0, 6, 0)
        self.list_layout.setSpacing(2)
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
        self.auto_layout.setSpacing(6)
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
        for row in list(getattr(self, "_rows", ()) or ()) + list(getattr(self, "_auto_rows", ()) or ()):
            refresh_style(row)

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
        self.title_label.setText("Sessions" if sessions else "Automations")
        self.new_button.setVisible(sessions)
        self.show_archived.setVisible(not sessions)
        self.new_automation_button.setVisible(not sessions)
        self.hint_label.setText(TAB_HINTS[self._tab])
        self.search_edit.setPlaceholderText(
            "Filter by topic, folder or tool…" if sessions else "Filter by title, schedule or result…"
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

    def set_digests(self, digests: Sequence[Any], *, active_session_id: str = "", more: bool = False) -> None:
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

    def set_automations(self, summaries: Sequence[Any], *, status: str = "", available: bool = True) -> None:
        """Render the Automations tab: one row per ``automation_id``.
        ``available`` = the gateway offers automations (else no tab at all)."""
        grouped = [dict(s) for s in group_by_automation(summaries or [])]
        text = str(status or "").strip()
        if grouped == self._automations and text == self._automation_status and bool(available) == self._automations_available:
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
            row.edit_requested.connect(self._on_automation_edit)
            row.control_requested.connect(self.automation_control_requested.emit)
            row.focus_requested.connect(self._on_row_hovered)
            self.auto_layout.addWidget(row)
            self._auto_rows.append(row)
        self.auto_layout.addStretch(1)
        self.tab_buttons["automations"].setText(
            "Automations" + (f" · {attention_total(self._automations)} new" if attention_total(self._automations) else "")
        )
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
        if not hasattr(self, "count_label"):
            return
        if self._tab == "sessions":
            total = len(self._digests)
            today = sum(1 for d in self._digests if recency_group(d.last_activity) == "Today")
            # The gateway reports no total: "N+" while more pages exist.
            parts = [f"{total}{'+' if self._more else ''} session{'s' if total != 1 or self._more else ''}"]
            if today:
                parts.append(f"{today} today")
        else:
            shown = [s for s in self._automations if s.get("status") != "archived" or self.show_archived.isChecked()]
            unread = attention_total(self._automations)
            parts = [f"{len(shown)} automation{'s' if len(shown) != 1 else ''}"]
            if unread:
                parts.append(f"{unread} new")
        self._count_text = " · ".join(parts)
        self.count_label.setToolTip(self._count_text)
        self._elide_count()

    @property
    def count_text(self) -> str:
        """The full count line (the label may show it elided)."""
        return self._count_text

    def _elide_count(self) -> None:
        width = self.count_label.width()
        metrics = QFontMetrics(self.count_label.font())
        text = self._count_text
        self.count_label.setText(text if width <= 1 else metrics.elidedText(text, Qt.ElideRight, width))

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
                self.empty_label.setText("No automation yet. Schedule a conversation with the clock button.")
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
        return str(getattr(row, "automation_id", "") or "") if row is not None and self._tab == "automations" else ""

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

    def _on_automation_edit(self, automation_id: str) -> None:
        self.automation_edit_requested.emit(str(automation_id))
        self.close()

    def _on_new_chat(self) -> None:
        self.new_chat_requested.emit()
        self.close()

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
            x = max(screen_geometry.x() + 8, min(x, screen_geometry.x() + screen_geometry.width() - width - 8))
            y = max(screen_geometry.y() + 8, min(y, screen_geometry.y() + screen_geometry.height() - height - 8))
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
        self._elide_count()
        for row in list(self._rows) + list(self._auto_rows):
            row.elide_labels(self.width() - 60)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        # ←/→ switch tabs while the filter is empty (else they move the caret).
        if obj is self.search_edit and event.type() == QEvent.KeyPress and not self.search_edit.text():
            if event.key() in (Qt.Key_Left, Qt.Key_Right) and not event.modifiers() and self._automations_available:
                self.set_tab("sessions" if event.key() == Qt.Key_Left else "automations", emit=True)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key_Escape:
            row = self._row_at(self._selected_index)
            if isinstance(row, AutomationTabRow) and row.confirming_archive:
                row.cancel_archive()
                event.accept()
                return
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
                    self._on_automation_open(automation_id, "top")
            event.accept()
            return
        if key == Qt.Key_N and modifiers & Qt.ControlModifier:
            self._on_new_chat()
            event.accept()
            return
        super().keyPressEvent(event)
