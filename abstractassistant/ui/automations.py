"""Automations v1 in the palette (Qt): the switcher rows, the automation view,
the "Schedule this conversation…" sheet, and the hub that talks to the gateway.

The Assistant executes nothing itself: an automation is a runtime root owned by
the gateway, and this module is a view, a creator and a responder over
contract F (`gateway/automations.py`). The widgets own no data — they render
summaries / occurrence rows and emit what the user chose; `AutomationsHub` does
every network call OFF the GUI thread and hands results back through a queued
signal. The rules (labels, enabled controls, chat pairs, create body,
notifications) are the Qt-free `core/automations.py`.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from PyQt5.QtCore import QObject, QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.automations import (
    CONTROL_COMMANDS,
    SCHEDULE_PRESETS,
    STATUS_LABELS,
    NotificationLedger,
    ScheduleWhen,
    api_error_text,
    attention_ack_cursor,
    attention_total,
    automation_controls,
    build_create_request,
    format_utc,
    group_by_automation,
    new_attention_notices,
    occurrence_views,
    parse_duration,
    revise_changes,
    schedule_label,
    trigger_summary,
)
from ..gateway.automations import AutomationApiError, AutomationsClient
from ..icons import symbol_icon
from ..theme import THEME
from .styles import alpha, dialog_stylesheet, refresh_style

__all__ = [
    "AUTOMATIONS_POLL_VISIBLE_MS",
    "AUTOMATIONS_POLL_HIDDEN_MS",
    "AutomationRow",
    "AutomationView",
    "AutomationsHub",
    "ScheduleSheet",
    "automation_row_qss",
]

# The palette polls the full automation list every 60 s while it is visible
# (mission A). While it is hidden it keeps a slower cadence so a final failure
# or a human wait still reaches the tray.
AUTOMATIONS_POLL_VISIBLE_MS = 60_000
AUTOMATIONS_POLL_HIDDEN_MS = 300_000

_EXCERPT_MAX = 160


def _clip(text: Any, limit: int = _EXCERPT_MAX) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _next_run_text(summary: Mapping[str, Any]) -> str:
    status = summary.get("status")
    if status == "paused":
        return "paused"
    if status in {"archived", "completed", "failed"}:
        return STATUS_LABELS.get(str(status), str(status)).lower()
    nxt = summary.get("next_fire_at")
    if not nxt:
        return "no next run"
    try:
        when = datetime.fromisoformat(str(nxt).replace("Z", "+00:00"))
        delta = (when - datetime.now(timezone.utc)).total_seconds()
    except ValueError:
        return f"next {format_utc(nxt)}"
    if delta <= 60:
        return "next: now"
    if delta < 3600:
        return f"next in {int(delta // 60)} min"
    if delta < 86400:
        return f"next in {int(delta // 3600)} h"
    return f"next {format_utc(nxt)}"


# ----------------------------------------------------------------- styles


def automation_row_qss() -> str:
    """Rules for the automation widgets (appended to the switcher's and the
    palette's stylesheets; rebuilt on a theme switch)."""
    return f"""
    QLabel#autoBadge {{
        color: {THEME.attention_text};
        background: {THEME.attention_bg};
        border: 1px solid {THEME.attention_border};
        border-radius: 7px;
        padding: 0px 6px;
        font-size: 9px;
        font-weight: 800;
        letter-spacing: 0.06em;
    }}
    QPushButton#aboutAutomation {{
        color: {THEME.accent_text};
        background: {alpha(THEME.accent, 0.10)};
        border: 1px solid {THEME.accent_border};
        border-radius: 7px;
        padding: 0px 6px;
        font-size: 9px;
        font-weight: 700;
    }}
    QLabel#autoCadence {{ color: {THEME.text_muted}; font-size: 10px; font-weight: 600; }}
    QLabel#autoExcerpt {{ color: {THEME.text_muted}; font-size: 11px; }}
    QLabel#autoExcerpt[tone="warn"] {{ color: {THEME.attention_text}; }}
    QFrame#autoView {{ background: transparent; border: none; }}
    QScrollArea#autoScroll, QWidget#autoList {{ background: transparent; border: none; }}
    QLabel#autoViewTitle {{ color: {THEME.text_strong}; font-size: 13px; font-weight: 800; }}
    QLabel#autoViewMeta {{ color: {THEME.text_muted}; font-size: 11px; }}
    QLabel#autoViewError {{
        color: {THEME.danger_text}; background: {THEME.danger_bg};
        border-radius: 8px; padding: 6px 8px; font-size: 11px;
    }}
    QLabel#autoViewNotice {{ color: {THEME.text_secondary}; font-size: 11px; }}
    QLabel#autoAttention {{
        color: {THEME.attention_text}; background: {THEME.attention_bg};
        border: 1px solid {THEME.attention_border}; border-radius: 8px; padding: 5px 8px; font-size: 11px;
    }}
    QFrame#autoTrigger {{
        background: {alpha(THEME.accent, 0.08)};
        border: 1px solid {THEME.border_subtle};
        border-radius: 10px;
    }}
    QFrame#autoAnswer {{
        background: {THEME.overlay_faint};
        border: 1px solid {THEME.border_subtle};
        border-radius: 10px;
    }}
    QFrame#autoTrigger[tone="quiet"], QFrame#autoAnswer[tone="quiet"] {{
        background: transparent;
        border-color: {alpha(THEME.text_faint, 0.18)};
    }}
    QFrame#autoAnswer[tone="failed"] {{ background: {THEME.danger_bg}; border: 1px solid {alpha(THEME.danger, 0.55)}; }}
    QFrame#autoAnswer[tone="waiting"] {{ background: {THEME.attention_bg}; border: 1px solid {THEME.attention_border}; }}
    QFrame#autoAnswer[tone="notified"] {{ border: 1px solid {THEME.accent_border}; }}
    QLabel#autoTurnMeta {{ color: {THEME.text_faint}; font-size: 10px; font-weight: 700; }}
    QLabel#autoTurnText {{ color: {THEME.text_primary}; font-size: 12px; }}
    QLabel#autoTurnText[tone="quiet"] {{ color: {THEME.text_muted}; }}
    QLabel#autoTurnBadge {{ color: {THEME.attention_text}; font-size: 10px; font-weight: 800; }}
    QLabel#autoTurnBadge[tone="failed"] {{ color: {THEME.danger_text}; }}
    QLabel#autoTurnBadge[tone="notified"] {{ color: {THEME.accent_text}; }}
    QPushButton#autoControl, QPushButton#autoSmall {{
        color: {THEME.text_secondary};
        background: {THEME.overlay_faint};
        border: 1px solid {THEME.border_subtle};
        border-radius: 8px;
        padding: 3px 9px;
        font-size: 11px;
        font-weight: 600;
        min-height: 20px;
    }}
    QPushButton#autoControl:hover, QPushButton#autoSmall:hover {{ background: {THEME.overlay_hover}; }}
    QPushButton#autoControl:disabled, QPushButton#autoSmall:disabled {{ color: {THEME.text_faint}; }}
    QPushButton#autoDanger {{
        color: {THEME.text_strong}; background: {THEME.danger_bg};
        border: 1px solid {alpha(THEME.danger, 0.55)}; border-radius: 8px; padding: 3px 10px; font-size: 11px;
    }}
    QPushButton#autoPrimary {{
        color: {THEME.primary_text}; background: {THEME.primary};
        border: none; border-radius: 8px; padding: 4px 12px; font-size: 11px; font-weight: 700;
    }}
    QPushButton#autoPrimary:disabled {{ background: {alpha(THEME.primary, 0.45)}; }}
    QLineEdit#autoInput, QPlainTextEdit#autoInput, QComboBox#autoInput, QSpinBox#autoInput {{
        background: {THEME.surface_raised}; border: 1px solid {THEME.border_subtle};
        border-radius: 7px; padding: 3px 7px; color: {THEME.text_primary}; font-size: 12px;
    }}
    """


# ---------------------------------------------------------- switcher rows


class AutomationRow(QFrame):
    """One automation in the switcher's Automations section."""

    chosen = pyqtSignal(str)

    def __init__(self, summary: Mapping[str, Any], *, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.summary = dict(summary)
        self.automation_id = str(summary.get("automation_id") or "")
        self.setObjectName("sessionRow")
        self.setProperty("active", "false")
        self.setProperty("selected", "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 7)
        root.setSpacing(9)
        self.spine = QFrame(self)
        self.spine.setObjectName("rowSpine")
        self.spine.setFixedWidth(3)
        self.spine.setProperty("tone", self._spine_tone())
        self.spine.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        root.addWidget(self.spine)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        root.addLayout(column, 1)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self.title_label = QLabel(str(summary.get("title") or "Automation"), self)
        self.title_label.setObjectName("rowTitle")
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.title_label, 1)
        self.badge_label = QLabel(self.badge_text, self)
        self.badge_label.setObjectName("autoBadge")
        self.badge_label.setVisible(bool(self.badge_text))
        head.addWidget(self.badge_label, 0, Qt.AlignVCenter)
        self.next_label = QLabel(_next_run_text(summary), self)
        self.next_label.setObjectName("rowTime")
        self.next_label.setToolTip(f"Next run: {format_utc(summary.get('next_fire_at'))}" if summary.get("next_fire_at") else "")
        head.addWidget(self.next_label, 0, Qt.AlignVCenter)
        column.addLayout(head)

        status = STATUS_LABELS.get(str(summary.get("status") or ""), str(summary.get("status") or ""))
        mode = "growing" if summary.get("context_mode") == "growing" else "independent"
        self.cadence_label = QLabel(f"{self.cadence} · {status} · {mode}", self)
        self.cadence_label.setObjectName("autoCadence")
        self.cadence_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        column.addWidget(self.cadence_label)

        last = summary.get("last_occurrence") if isinstance(summary.get("last_occurrence"), Mapping) else None
        excerpt = ""
        tone = ""
        if last is not None:
            last_status = str(last.get("status") or "")
            excerpt = f"#{last.get('index')} {last_status}: {_clip(last.get('excerpt'))}".rstrip(": ")
            if last_status in {"failed", "waiting"}:
                tone = "warn"
        self.excerpt_label = QLabel(excerpt or "No run yet.", self)
        self.excerpt_label.setObjectName("autoExcerpt")
        if tone:
            self.excerpt_label.setProperty("tone", tone)
        self.excerpt_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        column.addWidget(self.excerpt_label)
        self.setToolTip(
            "\n".join(
                line
                for line in (
                    str(summary.get("title") or ""),
                    self.cadence,
                    f"Next run: {format_utc(summary.get('next_fire_at'))}" if summary.get("next_fire_at") else "",
                    f"Automation id: {self.automation_id}",
                )
                if line
            )
        )

    @property
    def cadence(self) -> str:
        trigger = self.summary.get("trigger")
        return trigger_summary(trigger) if isinstance(trigger, Mapping) else ""

    @property
    def badge_text(self) -> str:
        attention = self.summary.get("attention") if isinstance(self.summary.get("attention"), Mapping) else {}
        parts = []
        unseen = int(attention.get("unseen_count") or 0)
        waits = int(attention.get("pending_waits") or 0)
        if unseen:
            parts.append(f"{unseen} NEW")
        if waits:
            parts.append("WAITING")
        return " · ".join(parts)

    def _spine_tone(self) -> str:
        attention = self.summary.get("attention") if isinstance(self.summary.get("attention"), Mapping) else {}
        if int(attention.get("pending_waits") or 0) or int(attention.get("unseen_count") or 0):
            return "warn"
        status = self.summary.get("status")
        if status == "active":
            return "fresh"
        return "idle"

    def matches(self, query: str) -> bool:
        needle = " ".join(str(query or "").lower().split())
        if not needle:
            return True
        hay = " ".join(
            str(x or "").lower()
            for x in (self.summary.get("title"), self.cadence, (self.summary.get("last_occurrence") or {}).get("excerpt"))
        )
        return all(word in hay for word in needle.split())

    def elide_labels(self, width: int) -> None:
        from PyQt5.QtGui import QFontMetrics

        available = max(80, int(width) - 150)
        self.title_label.setText(
            QFontMetrics(self.title_label.font()).elidedText(str(self.summary.get("title") or ""), Qt.ElideRight, available)
        )

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.LeftButton:
            self.chosen.emit(self.automation_id)
            return
        super().mouseReleaseEvent(event)


# ------------------------------------------------------------ the view


def _button(text: str, name: str = "autoControl", *, parent: Optional[QWidget] = None, tooltip: str = "") -> QPushButton:
    button = QPushButton(text, parent)
    button.setObjectName(name)
    button.setCursor(Qt.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)
    return button


def _text_label(text: str, name: str, *, parent: QWidget, tone: str = "") -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextFormat(Qt.PlainText)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    if tone:
        label.setProperty("tone", tone)
    return label


class OccurrencePair(QWidget):
    """One occurrence as two chat turns: the trigger/task turn and the answer."""

    discuss_requested = pyqtSignal(int, str)
    wait_answered = pyqtSignal(str, str, str)

    def __init__(self, view, *, discuss_enabled: bool, discuss_reason: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.view = view
        row = view.row
        self.index = int(row.get("index") or 0)
        quiet = view.tone == "quiet"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # -- the trigger / task turn (the "user" side) ----------------------
        self.trigger = QFrame(self)
        self.trigger.setObjectName("autoTrigger")
        self.trigger.setProperty("tone", "quiet" if quiet else "")
        tl = QVBoxLayout(self.trigger)
        tl.setContentsMargins(10, 6, 10, 6)
        tl.setSpacing(2)
        trig = row.get("trigger") if isinstance(row.get("trigger"), Mapping) else {}
        meta = f"#{self.index} · {trig.get('summary') or trig.get('source_id') or 'trigger'} · fired {format_utc(row.get('fired_at'))}"
        tl.addWidget(_text_label(meta, "autoTurnMeta", parent=self.trigger))
        self.trigger_text = _text_label(str(row.get("user_turn") or ""), "autoTurnText", parent=self.trigger, tone="quiet" if quiet else "")
        tl.addWidget(self.trigger_text)
        wrap_t = QHBoxLayout()
        wrap_t.setContentsMargins(40, 0, 0, 0)
        wrap_t.addWidget(self.trigger)
        layout.addLayout(wrap_t)

        # -- the answer turn --------------------------------------------------
        self.answer = QFrame(self)
        self.answer.setObjectName("autoAnswer")
        self.answer.setProperty("tone", view.tone)
        al = QVBoxLayout(self.answer)
        al.setContentsMargins(10, 6, 10, 8)
        al.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.badge = QLabel(view.badge, self.answer)
        self.badge.setObjectName("autoTurnBadge")
        self.badge.setProperty("tone", view.tone)
        self.badge.setVisible(bool(view.badge))
        head.addWidget(self.badge, 0)
        finished = row.get("finished_at")
        head.addWidget(
            _text_label(
                f"{view.status_text}{' · ' + format_utc(finished) if finished else ''}",
                "autoTurnMeta",
                parent=self.answer,
            ),
            1,
        )
        self.discuss_button = _button("Discuss", "autoSmall", parent=self.answer, tooltip=(
            "Open a forked session seeded with this automation's turns up to here "
            "(read-only workspace; nothing is written back)" if discuss_enabled and view.can_discuss else (discuss_reason or "Not while it is running")
        ))
        self.discuss_button.setEnabled(bool(discuss_enabled and view.can_discuss))
        self.discuss_button.clicked.connect(self._start_discuss)
        head.addWidget(self.discuss_button, 0)
        al.addLayout(head)

        notify = row.get("notify") if isinstance(row.get("notify"), Mapping) else None
        if notify is not None and notify.get("title"):
            al.addWidget(_text_label(str(notify.get("title")), "autoTurnBadge", parent=self.answer, tone="notified"))
        failure = row.get("failure") if isinstance(row.get("failure"), Mapping) else None
        answer_text = str(row.get("answer") or "")
        if failure is not None:
            attempts = int(failure.get("attempts") or row.get("attempts") or 1)
            failure_text = f"{failure.get('message') or 'The occurrence failed.'} ({failure.get('reason_code') or 'failed'}, {attempts} attempt{'s' if attempts != 1 else ''})"
            al.addWidget(_text_label(failure_text, "autoTurnText", parent=self.answer))
        self.answer_text = _text_label(
            answer_text or ("" if failure is not None else ("(no answer)" if view.tone != "waiting" else "")),
            "autoTurnText",
            parent=self.answer,
            tone="quiet" if quiet else "",
        )
        self.answer_text.setVisible(bool(self.answer_text.text()))
        al.addWidget(self.answer_text)

        artifacts = row.get("artifacts") if isinstance(row.get("artifacts"), list) else []
        if artifacts:
            names = ", ".join(str(a.get("name") or a.get("artifact_id")) for a in artifacts if isinstance(a, Mapping))
            al.addWidget(_text_label(f"Files: {names}", "autoTurnMeta", parent=self.answer))

        # -- pending human waits, answered from here -------------------------
        self.wait_inputs: List[Dict[str, Any]] = []
        for wait in row.get("waits") or []:
            if not isinstance(wait, Mapping):
                continue
            box = QWidget(self.answer)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 2, 0, 0)
            bl.setSpacing(4)
            bl.addWidget(_text_label(str(wait.get("prompt") or "The occurrence is waiting for your answer."), "autoTurnText", parent=box))
            choices_row = QHBoxLayout()
            choices_row.setSpacing(6)
            choice_buttons = []
            run_id, wait_key = str(wait.get("run_id") or row.get("run_id") or ""), str(wait.get("wait_key") or "")
            for choice in wait.get("choices") or []:
                b = _button(str(choice), "autoSmall", parent=box)
                b.clicked.connect(lambda _=False, r=run_id, k=wait_key, c=str(choice): self.wait_answered.emit(r, k, c))
                choices_row.addWidget(b)
                choice_buttons.append(b)
            choices_row.addStretch(1)
            bl.addLayout(choices_row)
            free = QHBoxLayout()
            edit = QLineEdit(box)
            edit.setObjectName("autoInput")
            edit.setPlaceholderText("Or type an answer…")
            send = _button("Answer", "autoPrimary", parent=box)
            send.clicked.connect(lambda _=False, r=run_id, k=wait_key, e=edit: self._send_free(r, k, e))
            edit.returnPressed.connect(lambda r=run_id, k=wait_key, e=edit: self._send_free(r, k, e))
            free.addWidget(edit, 1)
            free.addWidget(send, 0)
            bl.addLayout(free)
            al.addWidget(box)
            self.wait_inputs.append({"run_id": run_id, "wait_key": wait_key, "choices": choice_buttons, "edit": edit, "send": send})

        # -- the discuss prompt (inline, shown on demand) -------------------
        self.discuss_box = QWidget(self.answer)
        dl = QHBoxLayout(self.discuss_box)
        dl.setContentsMargins(0, 2, 0, 0)
        self.discuss_edit = QLineEdit(self.discuss_box)
        self.discuss_edit.setObjectName("autoInput")
        self.discuss_edit.setPlaceholderText("What do you want to discuss about this result?")
        self.discuss_edit.returnPressed.connect(self._submit_discuss)
        self.discuss_send = _button("Start", "autoPrimary", parent=self.discuss_box)
        self.discuss_send.clicked.connect(self._submit_discuss)
        dl.addWidget(self.discuss_edit, 1)
        dl.addWidget(self.discuss_send, 0)
        self.discuss_box.hide()
        al.addWidget(self.discuss_box)

        wrap_a = QHBoxLayout()
        wrap_a.setContentsMargins(0, 0, 40, 0)
        wrap_a.addWidget(self.answer)
        layout.addLayout(wrap_a)

    def _send_free(self, run_id: str, wait_key: str, edit: QLineEdit) -> None:
        text = edit.text().strip()
        if text:
            self.wait_answered.emit(run_id, wait_key, text)

    def _start_discuss(self) -> None:
        self.discuss_box.show()
        self.discuss_edit.setFocus(Qt.ShortcutFocusReason)

    def _submit_discuss(self) -> None:
        prompt = self.discuss_edit.text().strip()
        if prompt:
            self.discuss_requested.emit(self.index, prompt)


class AutomationView(QFrame):
    """An automation opened in the palette: its occurrences as a chat, with
    pause / resume / run now / edit / archive / discuss."""

    back_requested = pyqtSignal()
    control_requested = pyqtSignal(str)  # pause | resume | run_now | stop_current | archive
    revise_requested = pyqtSignal(object)  # changes
    discuss_requested = pyqtSignal(int, str)
    wait_answered = pyqtSignal(str, str, str)
    load_more_requested = pyqtSignal()
    retry_requested = pyqtSignal()

    CONTROL_LABELS = (
        ("pause", "Pause"),
        ("resume", "Resume"),
        ("run_now", "Run now"),
        ("stop_current", "Stop current"),
        ("revise", "Edit"),
        ("archive", "Archive"),
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("autoView")
        self.summary: Dict[str, Any] = {}
        self.occurrences: List[Dict[str, Any]] = []
        self.next_cursor: Optional[str] = None
        self.busy = False
        self.pairs: List[OccurrencePair] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.back_button = _button("← Chat", "autoControl", parent=self, tooltip="Back to the conversation")
        self.back_button.clicked.connect(self.back_requested.emit)
        head.addWidget(self.back_button, 0)
        self.title_label = QLabel("", self)
        self.title_label.setObjectName("autoViewTitle")
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.title_label, 1)
        root.addLayout(head)
        self.meta_label = _text_label("", "autoViewMeta", parent=self)
        root.addWidget(self.meta_label)

        controls = QHBoxLayout()
        controls.setSpacing(5)
        self.control_buttons: Dict[str, QPushButton] = {}
        for control, label in self.CONTROL_LABELS:
            button = _button(label, "autoControl", parent=self)
            button.clicked.connect(lambda _=False, c=control: self._on_control(c))
            controls.addWidget(button)
            self.control_buttons[control] = button
        controls.addStretch(1)
        root.addLayout(controls)

        # Archive confirmation, inside the palette (never a modal).
        self.archive_confirm = QWidget(self)
        ac = QHBoxLayout(self.archive_confirm)
        ac.setContentsMargins(0, 0, 0, 0)
        ac.addWidget(_text_label("Archive this automation? Its history is kept; nothing runs any more.", "autoViewNotice", parent=self.archive_confirm), 1)
        self.archive_yes = _button("Archive", "autoDanger", parent=self.archive_confirm)
        self.archive_yes.clicked.connect(self._confirm_archive)
        self.archive_no = _button("Cancel", "autoControl", parent=self.archive_confirm)
        self.archive_no.clicked.connect(self.archive_confirm.hide)
        ac.addWidget(self.archive_yes)
        ac.addWidget(self.archive_no)
        self.archive_confirm.hide()
        root.addWidget(self.archive_confirm)

        # Edit (title + interval + context), inline.
        self.edit_box = QWidget(self)
        el = QHBoxLayout(self.edit_box)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(6)
        self.edit_title = QLineEdit(self.edit_box)
        self.edit_title.setObjectName("autoInput")
        self.edit_title.setPlaceholderText("Title")
        self.edit_every = QLineEdit(self.edit_box)
        self.edit_every.setObjectName("autoInput")
        self.edit_every.setPlaceholderText("every (e.g. 30m, 8h, 7d)")
        self.edit_every.setMaximumWidth(110)
        self.edit_context = QComboBox(self.edit_box)
        self.edit_context.setObjectName("autoInput")
        self.edit_context.addItem("Independent", "independent")
        self.edit_context.addItem("Growing", "growing")
        self.edit_save = _button("Save", "autoPrimary", parent=self.edit_box)
        self.edit_save.clicked.connect(self._save_edit)
        self.edit_cancel = _button("Cancel", "autoControl", parent=self.edit_box)
        self.edit_cancel.clicked.connect(self.edit_box.hide)
        for w, stretch in ((self.edit_title, 1), (self.edit_every, 0), (self.edit_context, 0), (self.edit_save, 0), (self.edit_cancel, 0)):
            el.addWidget(w, stretch)
        self.edit_box.hide()
        root.addWidget(self.edit_box)

        self.error_row = QWidget(self)
        er = QHBoxLayout(self.error_row)
        er.setContentsMargins(0, 0, 0, 0)
        self.error_label = _text_label("", "autoViewError", parent=self.error_row)
        er.addWidget(self.error_label, 1)
        self.retry_button = _button("Retry", "autoControl", parent=self.error_row, tooltip="Send the same request again (same command id)")
        self.retry_button.clicked.connect(self.retry_requested.emit)
        er.addWidget(self.retry_button, 0)
        self.error_row.hide()
        root.addWidget(self.error_row)

        self.notice_label = _text_label("", "autoViewNotice", parent=self)
        self.notice_label.hide()
        root.addWidget(self.notice_label)
        self.attention_label = _text_label("", "autoAttention", parent=self)
        self.attention_label.hide()
        root.addWidget(self.attention_label)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("autoScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_host.setObjectName("autoList")
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 6, 0)
        self.list_layout.setSpacing(10)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)
        self.restyle()

    def restyle(self) -> None:
        self.setStyleSheet(automation_row_qss())

    # ------------------------------------------------------------ state

    @property
    def automation_id(self) -> str:
        return str(self.summary.get("automation_id") or "")

    def controls(self) -> Dict[str, Any]:
        return automation_controls(self.summary, self.occurrences, busy=self.busy)

    def set_summary(self, summary: Mapping[str, Any]) -> None:
        self.summary = dict(summary)
        self.title_label.setText(str(summary.get("title") or "Automation"))
        trigger = summary.get("trigger") if isinstance(summary.get("trigger"), Mapping) else {}
        status = STATUS_LABELS.get(str(summary.get("status") or ""), str(summary.get("status") or ""))
        mode = "Growing — each run sees the previous runs" if summary.get("context_mode") == "growing" else "Independent — each run starts fresh"
        parts = [trigger_summary(trigger), status, _next_run_text(summary), mode, f"{int(summary.get('occurrence_count') or 0)} runs"]
        self.meta_label.setText(" · ".join(p for p in parts if p))
        attention = summary.get("attention") if isinstance(summary.get("attention"), Mapping) else {}
        lines = []
        for item in attention.get("items") or []:
            if isinstance(item, Mapping):
                prefix = "Failed" if item.get("kind") == "failure" else "New"
                lines.append(f"{prefix} · #{item.get('index')} {item.get('title') or ''}".rstrip())
        if int(attention.get("pending_waits") or 0):
            lines.append(f"{int(attention.get('pending_waits'))} occurrence(s) waiting for you")
        self.attention_label.setText("\n".join(lines))
        self.attention_label.setVisible(bool(lines))
        self.edit_title.setText(str(summary.get("title") or ""))
        every = (trigger.get("config") or {}).get("every") if trigger.get("source_id") == "schedule" else None
        self.edit_every.setText(str(every or ""))
        self.edit_every.setEnabled(trigger.get("source_id") == "schedule")
        self.edit_context.setCurrentIndex(1 if summary.get("context_mode") == "growing" else 0)
        self._apply_controls()
        self._rebuild_pairs()

    def set_occurrences(self, rows: Sequence[Mapping[str, Any]], *, next_cursor: Optional[str], append: bool = False) -> None:
        incoming = [dict(r) for r in rows if isinstance(r, Mapping)]
        if append:
            known = {r.get("run_id") for r in self.occurrences}
            self.occurrences.extend(r for r in incoming if r.get("run_id") not in known)
        else:
            self.occurrences = incoming
        self.next_cursor = next_cursor if isinstance(next_cursor, str) and next_cursor else None
        self._apply_controls()
        self._rebuild_pairs()

    def set_busy(self, busy: bool) -> None:
        self.busy = bool(busy)
        self._apply_controls()

    def set_error(self, text: str, *, retry: bool = False) -> None:
        value = str(text or "").strip()
        self.error_label.setText(value)
        self.retry_button.setVisible(bool(retry))
        self.error_row.setVisible(bool(value))

    def set_notice(self, text: str) -> None:
        value = str(text or "").strip()
        self.notice_label.setText(value)
        self.notice_label.setVisible(bool(value))

    # --------------------------------------------------------- rendering

    def _apply_controls(self) -> None:
        if not self.summary:
            for button in self.control_buttons.values():
                button.setEnabled(False)
            return
        state = self.controls()
        for control, button in self.control_buttons.items():
            enabled, reason = state[control]
            button.setEnabled(bool(enabled))
            button.setToolTip(reason if not enabled else "")

    def _rebuild_pairs(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.pairs = []
        discuss_enabled, discuss_reason = self.controls()["discuss"] if self.summary else (False, "")
        views = occurrence_views(self.occurrences)
        if self.next_cursor:
            more = _button("Load older runs", "autoSmall", parent=self.list_host)
            more.clicked.connect(self.load_more_requested.emit)
            self.load_more_button = more
            self.list_layout.addWidget(more, 0, Qt.AlignHCenter)
        else:
            self.load_more_button = None
        if not views:
            self.list_layout.addWidget(_text_label("No run yet.", "autoViewNotice", parent=self.list_host))
        for view in views:
            pair = OccurrencePair(view, discuss_enabled=discuss_enabled, discuss_reason=discuss_reason, parent=self.list_host)
            pair.discuss_requested.connect(self.discuss_requested.emit)
            pair.wait_answered.connect(self.wait_answered.emit)
            self.list_layout.addWidget(pair)
            self.pairs.append(pair)

    def scroll_to_latest(self) -> None:
        """Newest run in view — after the rebuilt pairs are laid out."""
        from PyQt5.QtCore import QTimer

        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    # ------------------------------------------------------------ actions

    def _on_control(self, control: str) -> None:
        if control == "revise":
            self.archive_confirm.hide()
            self.edit_box.setVisible(not self.edit_box.isVisibleTo(self))
            return
        if control == "archive":
            self.edit_box.hide()
            self.archive_confirm.show()
            return
        self.control_requested.emit(control)

    def _confirm_archive(self) -> None:
        self.archive_confirm.hide()
        self.control_requested.emit("archive")

    def _save_edit(self) -> None:
        every = self.edit_every.text().strip() if self.edit_every.isEnabled() else None
        changes, errors = revise_changes(
            self.summary,
            title=self.edit_title.text(),
            every=every or None,
            context=str(self.edit_context.currentData()),
        )
        if errors:
            self.set_error(" ".join(errors))
            return
        self.edit_box.hide()
        if changes:
            self.revise_requested.emit(changes)


# ------------------------------------------------------ schedule sheet


class ScheduleSheet(QDialog):
    """"Schedule this conversation…": WHAT (workflow + task), WHEN (fixed UTC
    interval or once), CONTEXT (Independent / Growing)."""

    submitted = pyqtSignal(object)  # the POST /automations body

    def __init__(
        self,
        *,
        target: Optional[Mapping[str, Any]],
        target_label: str,
        prompt: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("scheduleSheet")
        self.setWindowTitle("Schedule this conversation")
        self.setModal(False)
        self.setStyleSheet(dialog_stylesheet() + automation_row_qss())
        self.target = dict(target) if target else None
        # One id per submit action; kept only for a retry after a failure the
        # gateway never answered (see `submit_failed`).
        self.request_id = uuid.uuid4().hex
        self.schedule_available: Optional[bool] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        root.addWidget(_text_label("What", "autoViewTitle", parent=self))
        root.addWidget(_text_label(f"Workflow: {target_label or 'none'}", "autoViewMeta", parent=self))
        self.title_edit = QLineEdit(self)
        self.title_edit.setObjectName("autoInput")
        self.title_edit.setPlaceholderText("Title (defaults to the task's first line)")
        root.addWidget(self.title_edit)
        self.prompt_edit = QPlainTextEdit(self)
        self.prompt_edit.setObjectName("autoInput")
        self.prompt_edit.setPlainText(str(prompt or ""))
        self.prompt_edit.setPlaceholderText("The task each run performs")
        self.prompt_edit.setMinimumHeight(70)
        root.addWidget(self.prompt_edit)

        root.addWidget(_text_label("When (UTC)", "autoViewTitle", parent=self))
        self.preset_combo = QComboBox(self)
        self.preset_combo.setObjectName("autoInput")
        for label, when in SCHEDULE_PRESETS:
            self.preset_combo.addItem(label, when)
        self.preset_combo.addItem("every N…", "custom")
        self.preset_combo.addItem("once at…", "once")
        self.preset_combo.setCurrentIndex(3)  # every 8 hours
        self.preset_combo.currentIndexChanged.connect(self._sync_when)
        root.addWidget(self.preset_combo)
        custom = QHBoxLayout()
        self.custom_amount = QSpinBox(self)
        self.custom_amount.setObjectName("autoInput")
        self.custom_amount.setRange(1, 10_000)
        self.custom_amount.setValue(2)
        self.custom_unit = QComboBox(self)
        self.custom_unit.setObjectName("autoInput")
        for label, unit in (("minutes", "m"), ("hours", "h"), ("days", "d")):
            self.custom_unit.addItem(label, unit)
        self.custom_unit.setCurrentIndex(1)
        custom.addWidget(self.custom_amount)
        custom.addWidget(self.custom_unit)
        custom.addStretch(1)
        self.custom_host = QWidget(self)
        self.custom_host.setLayout(custom)
        root.addWidget(self.custom_host)
        self.at_edit = QLineEdit(self)
        self.at_edit.setObjectName("autoInput")
        self.at_edit.setPlaceholderText("First run / run once at YYYY-MM-DD HH:MM (UTC); empty = now")
        root.addWidget(self.at_edit)

        root.addWidget(_text_label("Context", "autoViewTitle", parent=self))
        self.independent = QRadioButton("Independent — each run starts fresh", self)
        self.growing = QRadioButton("Growing — each run sees the previous runs", self)
        self.independent.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.independent)
        group.addButton(self.growing)
        root.addWidget(self.independent)
        root.addWidget(self.growing)

        self.preview_label = _text_label("", "autoViewMeta", parent=self)
        root.addWidget(self.preview_label)
        self.error_label = _text_label("", "autoViewError", parent=self)
        self.error_label.hide()
        root.addWidget(self.error_label)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = _button("Cancel", "autoControl", parent=self)
        self.cancel_button.clicked.connect(self.close)
        self.submit_button = _button("Schedule", "autoPrimary", parent=self)
        self.submit_button.clicked.connect(self._submit)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.submit_button)
        root.addLayout(buttons)
        for signal in (self.prompt_edit.textChanged, self.at_edit.textChanged, self.custom_amount.valueChanged, self.custom_unit.currentIndexChanged):
            signal.connect(self._update_preview)
        self._sync_when()

    def restyle(self) -> None:
        self.setStyleSheet(dialog_stylesheet() + automation_row_qss())

    def set_trigger_sources(self, items: Sequence[Mapping[str, Any]]) -> None:
        """``schedule@1`` must be offered by the gateway, else nothing can be scheduled."""
        available = any(
            isinstance(i, Mapping) and i.get("id") == "schedule" and i.get("version") == 1 and i.get("available") is True
            for i in items
        )
        self.schedule_available = available
        if not available:
            self.set_error("This gateway does not offer the schedule@1 trigger source.")
        self._update_preview()

    def set_error(self, text: str) -> None:
        value = str(text or "").strip()
        self.error_label.setText(value)
        self.error_label.setVisible(bool(value))

    def when(self) -> ScheduleWhen:
        data = self.preset_combo.currentData()
        if data == "custom":
            return ScheduleWhen("every", int(self.custom_amount.value()), str(self.custom_unit.currentData()))
        if data == "once":
            return ScheduleWhen("once", at=self.at_edit.text().strip())
        return data

    def _sync_when(self) -> None:
        data = self.preset_combo.currentData()
        self.custom_host.setVisible(data == "custom")
        self.at_edit.setPlaceholderText(
            "Run once at YYYY-MM-DD HH:MM (UTC)" if data == "once" else "First run at YYYY-MM-DD HH:MM (UTC); empty = now"
        )
        self._update_preview()

    def build_body(self):
        when = self.when()
        return build_create_request(
            prompt=self.prompt_edit.toPlainText(),
            when=when,
            context="growing" if self.growing.isChecked() else "independent",
            target=self.target,
            request_id=self.request_id,
            title=self.title_edit.text(),
            start_at="" if when.kind == "once" else self.at_edit.text().strip(),
        )

    def _update_preview(self) -> None:
        body, errors = self.build_body()
        if body is not None:
            config = body["trigger"]["config"]
            first = "" if "every" not in config else (f", first run at {format_utc(config['start_at'])}" if config.get("start_at") else ", first run now")
            self.preview_label.setText(f"{schedule_label(config)}{first}")
        else:
            self.preview_label.setText(" ".join(errors))
        self.submit_button.setEnabled(body is not None and self.schedule_available is not False)

    def _submit(self) -> None:
        body, errors = self.build_body()
        if body is None:
            self.set_error(" ".join(errors))
            return
        self.set_error("")
        self.submit_button.setEnabled(False)
        self.submitted.emit(body)

    def submit_failed(self, text: str, *, reuse_id: bool) -> None:
        """``reuse_id`` = the gateway never answered, so the next submit is a
        retry of the same request; otherwise it is a new request."""
        if not reuse_id:
            self.request_id = uuid.uuid4().hex
        self.set_error(text)
        self.submit_button.setEnabled(True)
        self._update_preview()


# ------------------------------------------------------------------ the hub


class AutomationsHub(QObject):
    """Every automation call, off the GUI thread; the state the palette shows.

    ``client_factory`` returns an :class:`AutomationsClient` for the current
    gateway connection. ``notify(title, body)`` shows a tray notification.
    ``synchronous=True`` runs calls inline (tests).
    """

    summaries_changed = pyqtSignal(object)
    _finished = pyqtSignal(object, object)

    def __init__(
        self,
        *,
        client_factory: Callable[[], AutomationsClient],
        notify: Callable[[str, str], None],
        ledger: NotificationLedger,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._client_factory = client_factory
        self._notify = notify
        self.ledger = ledger
        self.synchronous = False
        self.summaries: List[Dict[str, Any]] = []
        # None = not asked yet; False = the gateway has no Automations API.
        self.available: Optional[bool] = None
        self.error = ""
        self._polling = False
        self._retry: Optional[Callable[[], None]] = None
        self._finished.connect(self._deliver)

    # ------------------------------------------------------------ plumbing

    def _submit(self, work: Callable[[], Any], done: Callable[[bool, Any], None]) -> None:
        if self.synchronous:
            try:
                result = (True, work())
            except Exception as exc:  # noqa: BLE001 - handed to `done`
                result = (False, exc)
            done(*result)
            return

        def _run() -> None:
            try:
                outcome = (True, work())
            except Exception as exc:  # noqa: BLE001
                outcome = (False, exc)
            try:
                self._finished.emit(done, outcome)
            except RuntimeError:
                return  # the hub was destroyed (quit mid-call)

        threading.Thread(target=_run, name="automations", daemon=True).start()

    def _deliver(self, done: Any, outcome: Any) -> None:
        ok, value = outcome
        done(ok, value)

    @staticmethod
    def error_text(exc: Any) -> str:
        if isinstance(exc, AutomationApiError):
            return api_error_text(exc.reason_code, exc.message)
        return f"{type(exc).__name__}: {exc}"

    @property
    def unread(self) -> int:
        return attention_total(self.summaries)

    def summary(self, automation_id: str) -> Optional[Dict[str, Any]]:
        for s in self.summaries:
            if s.get("automation_id") == automation_id:
                return s
        return None

    def titles(self) -> Dict[str, str]:
        return {str(s.get("automation_id")): str(s.get("title") or "") for s in self.summaries}

    # --------------------------------------------------------------- poll

    def poll(self, *, on_done: Optional[Callable[[], None]] = None) -> None:
        """Fetch every summary (full pages) + the unseen attention pages, then
        notify what is new. One poll at a time."""
        if self._polling:
            return
        self._polling = True

        def work():
            client = self._client_factory()
            summaries = group_by_automation(client.list_all())
            pages: Dict[str, List[Dict[str, Any]]] = {}
            for summary in summaries:
                attention = summary.get("attention") if isinstance(summary.get("attention"), Mapping) else {}
                if int(attention.get("unseen_count") or 0) > 0:
                    pages[str(summary["automation_id"])] = self._attention_all(client, str(summary["automation_id"]))
            return summaries, pages

        def done(ok: bool, value: Any) -> None:
            self._polling = False
            if ok:
                summaries, pages = value
                self.available = True
                self.error = ""
                self.summaries = [dict(s) for s in summaries]
                notices = new_attention_notices(self.summaries, pages, self.ledger)
                for notice in notices:
                    self._notify(notice.title, notice.body or notice.title)
                self.ledger.add(n.key for n in notices)
            elif isinstance(value, AutomationApiError) and value.status == 404 and value.reason_code == "invalid_response":
                # A plain 404 without the automation envelope: the route does
                # not exist on this gateway.
                self.available = False
                self.error = ""
                self.summaries = []
            else:
                self.error = self.error_text(value)
            self.summaries_changed.emit(list(self.summaries))
            if on_done is not None:
                on_done()

        self._submit(work, done)

    @staticmethod
    def _attention_all(client: AutomationsClient, automation_id: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        seen = set()
        for _ in range(50):
            page = client.attention(automation_id, cursor=cursor)
            items.extend(i for i in (page.get("items") or []) if isinstance(i, dict))
            nxt = page.get("next_cursor")
            if not isinstance(nxt, str) or not nxt or nxt in seen:
                break
            seen.add(nxt)
            cursor = nxt
        return items

    # ---------------------------------------------------------- one automation

    def load_occurrences(self, automation_id: str, done: Callable[[bool, Any], None], *, cursor: Optional[str] = None) -> None:
        self._submit(lambda: self._client_factory().occurrences(automation_id, cursor=cursor), done)

    def mark_seen(self, summary: Mapping[str, Any], done: Optional[Callable[[bool, Any], None]] = None) -> None:
        """Acknowledge the attention items the view DISPLAYED (the last one's
        cursor), never the summary's latest cursor."""
        cursor = attention_ack_cursor(summary)
        if not cursor:
            return
        aid = str(summary.get("automation_id") or "")

        def finished(ok: bool, value: Any) -> None:
            if ok:
                self.poll()
            if done is not None:
                done(ok, value)

        self._submit(lambda: self._client_factory().seen(aid, cursor), finished)

    @staticmethod
    def no_gateway_answer(exc: Any) -> bool:
        """The request failed before the gateway answered (it may or may not
        have been applied): only then is the same id sent again."""
        return isinstance(exc, AutomationApiError) and exc.status == 0

    @property
    def can_retry(self) -> bool:
        return self._retry is not None

    def _retryable(self, call: Callable[[], Any], done: Callable[[bool, Any], None]) -> None:
        """Send ``call`` (whose ids are fixed by the caller). One user action =
        one id: :meth:`retry` re-sends the SAME id only after a failure with no
        gateway answer; a success or a gateway error ends the action, so the
        next attempt is a new action with a new id."""

        def finished(ok: bool, value: Any) -> None:
            if not ok and self.no_gateway_answer(value):
                self._retry = lambda: self._submit(call, finished)
            else:
                self._retry = None
            done(ok, value)

        self._retry = None
        self._submit(call, finished)

    def retry(self) -> None:
        if self._retry is not None:
            again, self._retry = self._retry, None
            again()

    def command(self, automation_id: str, control: str, done: Callable[[bool, Any], None]) -> None:
        command_id = uuid.uuid4().hex
        type_ = CONTROL_COMMANDS[control]
        self._retryable(lambda: self._client_factory().command(automation_id, type_, command_id=command_id), done)

    def revise(self, summary: Mapping[str, Any], changes: Mapping[str, Any], done: Callable[[bool, Any], None]) -> None:
        command_id = uuid.uuid4().hex
        aid = str(summary.get("automation_id") or "")
        revision = summary.get("revision")
        expected = int(revision) if isinstance(revision, int) and not isinstance(revision, bool) else None
        self._retryable(
            lambda: self._client_factory().revise(aid, changes=dict(changes), expected_revision=expected, command_id=command_id),
            done,
        )

    def discuss(self, automation_id: str, index: int, prompt: str, done: Callable[[bool, Any], None]) -> None:
        request_id = uuid.uuid4().hex
        self._retryable(
            lambda: self._client_factory().discuss(automation_id, occurrence_index=index, prompt=prompt, request_id=request_id),
            done,
        )

    def create(self, body: Mapping[str, Any], done: Callable[[bool, Any], None]) -> None:
        self._submit(lambda: self._client_factory().create(dict(body)), done)

    def trigger_sources(self, done: Callable[[bool, Any], None]) -> None:
        self._submit(lambda: self._client_factory().trigger_sources(), done)

    def run(self, work: Callable[[], Any], done: Callable[[bool, Any], None]) -> None:
        """Any other blocking call (the wait answer), off the GUI thread."""
        self._submit(work, done)
