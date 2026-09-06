"""The session switcher: a searchable list of sessions with real metrics.

The header's session control opens this popup instead of a plain dropdown.
Every row shows what the session actually holds — when it was last touched, how many
turns and tool calls it ran, the tokens and wall time it spent, the folder it
worked in, and whether the last question went unanswered — so picking one
is a decision made on facts rather than on a truncated first sentence.

Rows are grouped by recency, filtered as you type, and can be renamed or
deleted in place (delete asks for confirmation inside the row, never with a
modal). The widget owns no data: it renders `SessionDigest` values and emits
what the user chose.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PyQt5.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
from ..icons import symbol_icon
from ..theme import METRICS, THEME
from .styles import alpha, dialog_stylesheet, refresh_style

__all__ = ["SessionRow", "SessionSwitcher", "SESSION_SWITCHER_QSS"]


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
        color: {THEME.text_strong};
        background: {THEME.primary};
        border: none;
        border-radius: 9px;
        padding: 5px 12px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#switcherPrimary:hover {{ background: {THEME.primary_hover}; }}
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


SESSION_SWITCHER_QSS: str = _build_qss()


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
    """One session: title, preview, metrics, and in-place rename/delete."""

    chosen = pyqtSignal(str)
    rename_committed = pyqtSignal(str, str)
    delete_confirmed = pyqtSignal(str)
    focus_requested = pyqtSignal(object)

    def __init__(self, digest: SessionDigest, *, active: bool, parent: Optional[QWidget] = None) -> None:
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

        self.delete_button = QPushButton()
        self.delete_button.setObjectName("rowAction")
        self.delete_button.setIcon(symbol_icon("trash", color=THEME.text_muted, size=12))
        self.delete_button.setIconSize(QSize(12, 12))
        self.delete_button.setToolTip("Delete this session and its transcript")
        self.delete_button.setCursor(Qt.PointingHandCursor)
        self.delete_button.clicked.connect(self.ask_delete)
        self.delete_button.hide()
        head.addWidget(self.delete_button, 0, Qt.AlignVCenter)
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
        self.metrics_host.setVisible(bool(digest.detailed))
        column.addWidget(self.metrics_host)

        # -- delete confirmation (replaces the row's content) --------------- #
        self.confirm_host = QWidget(self)
        confirm = QHBoxLayout(self.confirm_host)
        confirm.setContentsMargins(0, 2, 0, 2)
        confirm.setSpacing(8)
        message = QLabel("Delete this session and its transcript?")
        message.setObjectName("rowConfirm")
        confirm.addWidget(message, 1)
        yes = QPushButton("Delete")
        yes.setObjectName("rowConfirmYes")
        yes.setCursor(Qt.PointingHandCursor)
        yes.clicked.connect(lambda: self.delete_confirmed.emit(self.session_id))
        confirm.addWidget(yes, 0)
        no = QPushButton("Cancel")
        no.setObjectName("rowConfirmNo")
        no.setCursor(Qt.PointingHandCursor)
        no.clicked.connect(self.cancel_delete)
        confirm.addWidget(no, 0)
        self.confirm_host.hide()
        column.addWidget(self.confirm_host)

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

    def _metric_widgets(self) -> List[QWidget]:
        digest = self.digest
        out: List[QWidget] = []
        if digest.empty:
            out.append(_metric("message-square", "empty", "This session has no messages yet.", tone="warn"))
            return out
        if digest.turns:
            out.append(
                _metric(
                    "message-square",
                    format_count(digest.turns),
                    f"{digest.turns} question(s) you asked · {digest.answers} answer(s)",
                )
            )
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
        folder = workspace_label(digest.workspace_root)
        if folder:
            out.append(_metric("folder", folder, f"Workspace folder: {digest.workspace_root}"))
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

    def ask_delete(self) -> None:
        self.cancel_rename()
        self.metrics_host.hide()
        self.preview_label.hide()
        self.confirm_host.show()

    def cancel_delete(self) -> None:
        self.confirm_host.hide()
        self.preview_label.setVisible(bool(self._preview_text))
        self.metrics_host.setVisible(bool(self.digest.detailed))

    @property
    def confirming_delete(self) -> bool:
        return self.confirm_host.isVisibleTo(self)

    # ----------------------------------------------------------------- events

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        if obj is self.rename_edit and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.cancel_rename()
            return True
        return super().eventFilter(obj, event)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if not self.confirming_delete:
            self.rename_button.show()
            self.delete_button.show()
        self.focus_requested.emit(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.rename_button.hide()
        self.delete_button.hide()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.LeftButton and not self.confirming_delete and not self.rename_edit.isVisible():
            self.chosen.emit(self.session_id)
            return
        super().mouseReleaseEvent(event)


class SessionSwitcher(QDialog):
    """The popup: search, grouped rows, keyboard navigation, row actions."""

    session_chosen = pyqtSignal(str)
    new_chat_requested = pyqtSignal()
    rename_requested = pyqtSignal(str, str)
    delete_requested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sessionSwitcher")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(dialog_stylesheet() + SESSION_SWITCHER_QSS)
        self.resize(SWITCHER_WIDTH, SWITCHER_HEIGHT)

        self._digests: List[SessionDigest] = []
        self._rows: List[SessionRow] = []
        self._group_labels: Dict[str, QLabel] = {}
        self._active_id = ""
        self._selected_index = -1

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
        title = QLabel("Sessions")
        title.setObjectName("switcherTitle")
        header.addWidget(title, 0, Qt.AlignVCenter)
        self.count_label = QLabel("")
        self.count_label.setObjectName("switcherCount")
        header.addWidget(self.count_label, 1, Qt.AlignVCenter)
        self.new_button = QPushButton("New session")
        self.new_button.setObjectName("switcherPrimary")
        self.new_button.setCursor(Qt.PointingHandCursor)
        self.new_button.setIcon(symbol_icon("plus", color=THEME.text_strong, size=12))
        self.new_button.setIconSize(QSize(12, 12))
        self.new_button.setToolTip("Start a new session (⌘N)")
        self.new_button.clicked.connect(self._on_new_chat)
        header.addWidget(self.new_button, 0, Qt.AlignVCenter)
        root.addLayout(header)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("switcherSearch")
        self.search_edit.setPlaceholderText("Filter by topic, folder or tool…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        root.addWidget(self.search_edit)

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
        root.addWidget(self.scroll, 1)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("switcherEmpty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.hide()
        root.addWidget(self.empty_label)

        footer = QFrame()
        footer.setObjectName("switcherFooter")
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.setSpacing(8)
        hint = QLabel("↑↓ move · ↵ open · ⌘⌫ delete · esc close")
        hint.setObjectName("switcherHint")
        footer_row.addWidget(hint, 1, Qt.AlignVCenter)
        root.addWidget(footer)

    # -------------------------------------------------------------- rendering

    def set_digests(self, digests: Sequence[Any], *, active_session_id: str = "") -> None:
        """Render the session list. Accepts `SessionDigest` values or dicts."""
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
        if ordered == self._digests and active == self._active_id:
            # Nothing changed: reopening the popup, or a refresh that found the
            # same chats, must not throw away rows the user is looking at.
            return
        self._active_id = active
        self._digests = ordered
        self._rebuild()

    def _clear_rows(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._rows = []
        self._group_labels = {}

    def _rebuild(self) -> None:
        self._clear_rows()
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
                row = SessionRow(digest, active=digest.session_id == self._active_id, parent=self.list_host)
                row.chosen.connect(self._on_row_chosen)
                row.rename_committed.connect(self.rename_requested.emit)
                row.delete_confirmed.connect(self._on_delete_confirmed)
                row.focus_requested.connect(self._on_row_hovered)
                self.list_layout.addWidget(row)
                self._rows.append(row)
        self.list_layout.addStretch(1)
        self._refresh_count()
        self._apply_filter()
        self._select_active()
        self._fit_list()

    def _fit_list(self) -> None:
        """Settle rows that were built without a resize to trigger them.

        Rows created while the popup is already open never receive the
        `resizeEvent` that elides their labels, and the scroll area has not yet
        re-measured the list it was handed — without this the column can squeeze
        every row below its minimum, drawing one row on top of the next.
        """
        for row in self._rows:
            row.elide_labels(self.width() - 60)
        self.list_layout.activate()

    def _refresh_count(self) -> None:
        total = len(self._digests)
        today = sum(1 for d in self._digests if recency_group(d.last_activity) == "Today")
        parts = [f"{total} session{'s' if total != 1 else ''}"]
        if today:
            parts.append(f"{today} today")
        self.count_label.setText(" · ".join(parts))

    # -------------------------------------------------------------- filtering

    def _apply_filter(self) -> None:
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
        if not self._rows:
            self.empty_label.setText("No sessions yet. Start one with New session.")
            self.empty_label.show()
        elif not any_visible:
            self.empty_label.setText("No session matches this filter.")
            self.empty_label.show()
        else:
            self.empty_label.hide()
        if self._selected_index >= 0:
            row = self._row_at(self._selected_index)
            if row is None or not row.isVisible():
                self._select_index(self._first_visible_index())

    def visible_rows(self) -> List[SessionRow]:
        """Rows the filter kept — asked of the popup itself, so the answer is
        the same whether or not it is currently on screen."""
        return [row for row in self._rows if row.isVisibleTo(self)]

    # ------------------------------------------------------------- selection

    def _row_at(self, index: int) -> Optional[SessionRow]:
        rows = self.visible_rows()
        if 0 <= index < len(rows):
            return rows[index]
        return None

    def _first_visible_index(self) -> int:
        return 0 if self.visible_rows() else -1

    def _select_index(self, index: int) -> None:
        rows = self.visible_rows()
        for row in self._rows:
            row.set_selected(False)
        if not rows:
            self._selected_index = -1
            return
        clamped = max(0, min(int(index), len(rows) - 1))
        self._selected_index = clamped
        row = rows[clamped]
        row.set_selected(True)
        self.scroll.ensureWidgetVisible(row, 0, 40)

    def _select_active(self) -> None:
        rows = self.visible_rows()
        for index, row in enumerate(rows):
            if row.session_id == self._active_id:
                self._select_index(index)
                return
        self._select_index(self._first_visible_index())

    def _on_row_hovered(self, row: Any) -> None:
        rows = self.visible_rows()
        if row in rows:
            self._selected_index = rows.index(row)
            for other in self._rows:
                other.set_selected(other is row)

    @property
    def selected_session_id(self) -> str:
        row = self._row_at(self._selected_index)
        return row.session_id if row is not None else ""

    # ---------------------------------------------------------------- actions

    def _on_row_chosen(self, session_id: str) -> None:
        self.session_chosen.emit(str(session_id))
        self.close()

    def _on_delete_confirmed(self, session_id: str) -> None:
        self.delete_requested.emit(str(session_id))

    def _on_new_chat(self) -> None:
        self.new_chat_requested.emit()
        self.close()

    def open_at(self, global_pos, *, screen_geometry=None) -> None:
        """Show the popup at ``global_pos``, kept inside the screen."""
        self.adjustSize()
        self.resize(SWITCHER_WIDTH, min(SWITCHER_HEIGHT, self.height() or SWITCHER_HEIGHT))
        x, y = int(global_pos.x()), int(global_pos.y())
        if screen_geometry is not None:
            x = max(screen_geometry.x() + 8, min(x, screen_geometry.x() + screen_geometry.width() - SWITCHER_WIDTH - 8))
            y = max(screen_geometry.y() + 8, min(y, screen_geometry.y() + screen_geometry.height() - self.height() - 8))
        self.move(x, y)
        self.show()
        self.raise_()
        self.search_edit.clear()
        self.search_edit.setFocus(Qt.ShortcutFocusReason)
        self._select_active()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        for row in self._rows:
            row.elide_labels(self.width() - 60)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key_Escape:
            row = self._row_at(self._selected_index)
            if row is not None and row.confirming_delete:
                row.cancel_delete()
                event.accept()
                return
            self.close()
            event.accept()
            return
        if key in (Qt.Key_Down, Qt.Key_Up):
            step = 1 if key == Qt.Key_Down else -1
            self._select_index(max(0, self._selected_index + step))
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            session_id = self.selected_session_id
            if session_id:
                self._on_row_chosen(session_id)
            event.accept()
            return
        if key == Qt.Key_N and modifiers & Qt.ControlModifier:
            self._on_new_chat()
            event.accept()
            return
        if key in (Qt.Key_Backspace, Qt.Key_Delete) and modifiers & Qt.ControlModifier:
            row = self._row_at(self._selected_index)
            if row is not None:
                row.ask_delete()
            event.accept()
            return
        super().keyPressEvent(event)
