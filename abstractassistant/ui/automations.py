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

import html
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from PyQt5.QtCore import QEvent, QObject, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
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
    AUTOMATION_CONTROLS,
    DEFAULT_GROWING_MAX_TOKENS,
    GROWING_CONTEXT_HELP,
    CONTROL_COMMANDS,
    EMAIL_DEFAULT_MAX_BATCH,
    EMAIL_MAX_BATCH,
    EMAIL_TEXT,
    EmailTriggerForm,
    control_hint,
    email_usable,
    is_email_trigger,
    current_run,
    PENDING_TEXT,
    command_confirmed,
    SCHEDULE_PRESETS,
    STATUS_LABELS,
    NotificationLedger,
    ScheduleWhen,
    api_error_text,
    attention_ack_cursor,
    attention_total,
    active_short_reason,
    active_toggle_command,
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
from ..gateway.client import WAIT_KINDS
from ..icons import symbol_icon
from ..theme import THEME
from .switch import AfSwitch
from .styles import alpha, dialog_stylesheet, refresh_style

__all__ = [
    "AUTOMATIONS_POLL_VISIBLE_MS",
    "AUTOMATIONS_POLL_HIDDEN_MS",
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
    QWidget#autoOccurrence, QWidget#autoAnswerColumn {{ background: transparent; border: none; }}
    /* An answer side that is not an answer (failure, wait, nothing yet): the
       chat's assistant bubble shape, toned by the occurrence. */
    QFrame#autoNote {{
        background: {THEME.overlay_faint};
        border: 1px solid {THEME.border_subtle};
        border-radius: 16px;
    }}
    QFrame#autoNote[tone="quiet"] {{ background: transparent; border-color: {alpha(THEME.text_faint, 0.18)}; }}
    QFrame#autoNote[tone="failed"] {{ background: {THEME.danger_bg}; border: 1px solid {alpha(THEME.danger, 0.55)}; }}
    QFrame#autoNote[tone="waiting"] {{ background: {THEME.attention_bg}; border: 1px solid {THEME.attention_border}; }}
    QLabel#autoTurnMeta {{ color: {THEME.text_faint}; font-size: 10px; font-weight: 700; }}
    QLabel#autoTurnMeta[tone="failed"] {{ color: {THEME.danger_text}; }}
    QLabel#autoTurnMeta[tone="waiting"] {{ color: {THEME.attention_text}; }}
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
    /* The Discuss action under an answer: compact, like the chat's action row. */
    QLabel#autoWrapButton {{
        color: {THEME.text_muted};
        background: transparent;
        border: 1px solid {THEME.border_subtle};
        border-radius: 9px;
        padding: 2px 9px;
        font-size: 10px;
        font-weight: 600;
    }}
    QLabel#autoWrapButton:hover {{ color: {THEME.text_primary}; background: {THEME.overlay_hover}; }}
    QLabel#autoWrapButton:disabled {{ color: {THEME.text_faint}; border-color: {alpha(THEME.text_faint, 0.18)}; }}
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


# ------------------------------------------------------------ the view

# (role, markdown content, timestamp, bubble width) -> the chat's message widget.
# The palette provides it (its `MessageCard`), so an occurrence reads exactly
# like a chat turn.
TurnRenderer = Callable[[str, str, str, int], QWidget]
# (list viewport width, role) -> that role's bubble width: the chat's own rule
# (`app._message_bubble_width`), so the task bubble's right edge and the answer
# card's left edge land where a chat's do.
BubbleWidth = Callable[..., int]


def _clock_utc(ts: Any, *, seconds: bool = False) -> str:
    """A caption's time: ``13:42 UTC`` today, with the date on other days."""
    try:
        when = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return format_utc(ts)
    clock = when.strftime("%H:%M:%S" if seconds else "%H:%M")
    if when.date() != datetime.now(timezone.utc).date():
        clock = f"{when.strftime('%Y-%m-%d')} {clock}"
    return f"{clock} UTC"


def _button(text: str, name: str = "autoControl", *, parent: Optional[QWidget] = None, tooltip: str = "") -> QPushButton:
    button = QPushButton(text, parent)
    button.setObjectName(name)
    button.setCursor(Qt.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)
    return button


# DESIGN 2026-09-30 §6: an email switch without a mailbox says what to do.
NOTIFY_UNAVAILABLE_REASON = "Connect a mailbox first."


def _text_label(text: str, name: str, *, parent: QWidget, tone: str = "") -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextFormat(Qt.PlainText)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    if tone:
        label.setProperty("tone", tone)
    return label


class WrappingButton(QLabel):
    """A button whose label wraps: the Discuss control's full wording must
    fit a narrow palette without widening the list (a QPushButton's text
    never wraps and forced a horizontal scroll)."""

    clicked = pyqtSignal()

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("autoWrapButton")
        self.setWordWrap(True)
        self.setTextFormat(Qt.PlainText)
        self.setCursor(Qt.PointingHandCursor)
        # Its height is its height for the width it gets (heightForWidth).
        # A `Minimum` vertical policy made its sizeHint its MINIMUM height —
        # and a word-wrapped label's sizeHint is taken at a narrow guessed
        # width (2-3 lines). The occurrence list's minimum height summed that
        # over every row, and the scroll area never sizes its content below
        # its minimum: 26 px of empty space per occurrence under the last one.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        # One line when the row has room (a word-wrapped QLabel otherwise
        # guesses a narrow, two-line shape); the layout shrinks it and it
        # wraps (heightForWidth) only when the palette is narrower.
        margins = self.contentsMargins()
        width = self.fontMetrics().horizontalAdvance(self.text()) + margins.left() + margins.right() + 2 * self.frameWidth() + 2
        return QSize(width, self.heightForWidth(width))

    def click(self) -> None:
        if self.isEnabled():
            self.clicked.emit()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.LeftButton:
            self.click()
            return
        super().mouseReleaseEvent(event)


# The web panel's wording (ui-kit 12f736a), word for word.
DISCUSS_LABEL = "Discuss — fork at this occurrence (own workspace, automation files read-only)"


def discuss_help(index: int) -> str:
    return (
        f"Starts a new session that forks this automation at #{index} with its full history (runs 1–{index}). "
        "It works in its own writable workspace; the automation's files are mounted read-only for the file "
        "tools (shell commands are not sandboxed), and nothing is written back into the automation's session."
    )


class OccurrencePair(QWidget):
    """One occurrence as a chat exchange, with the chat's own geometry: the
    task turn is the chat's user bubble (right-aligned) under a muted caption,
    the answer is the chat's assistant card (left) under a muted status line,
    and Discuss is a compact action under the card. No frame around the pair."""

    discuss_requested = pyqtSignal(int, str)
    wait_answered = pyqtSignal(str, str, str, object)  # run_id, wait_key, kind, answer

    def __init__(
        self,
        view,
        *,
        discuss_enabled: bool,
        discuss_reason: str,
        render_turn: "TurnRenderer",
        bubble_width: "BubbleWidth",
        viewport_width: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("autoOccurrence")
        self.view = view
        self._bubble_width = bubble_width
        # The turns are rendered by the palette's own chat message widget
        # (markdown, tables, code, JSON) — never by a second renderer here.
        # (role, card) so a resize gives each the chat's width for its role.
        self.turn_cards: List[QWidget] = []
        self._turn_roles: List[str] = []
        row = view.row
        self.index = int(row.get("index") or 0)
        quiet = view.tone == "quiet"
        user_width = bubble_width(viewport_width, role="user")
        answer_width = bubble_width(viewport_width, role="assistant")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)  # the chat's gap between turns

        # -- the task turn: the chat's user bubble, caption above it ---------
        task = QVBoxLayout()
        task.setContentsMargins(0, 0, 0, 0)
        task.setSpacing(3)
        trig = row.get("trigger") if isinstance(row.get("trigger"), Mapping) else {}
        meta = f"#{self.index} · {trig.get('summary') or trig.get('source_id') or 'trigger'} · fired {_clock_utc(row.get('fired_at'))}"
        self.task_meta = _text_label(meta, "autoTurnMeta", parent=self)
        self.task_meta.setAlignment(Qt.AlignRight)
        self.task_meta.setToolTip(f"fired {format_utc(row.get('fired_at'))}")
        task.addWidget(self.task_meta)
        self.trigger_text = self._turn("user", str(row.get("user_turn") or ""), str(row.get("fired_at") or ""), user_width, render_turn)
        task.addWidget(self.trigger_text)
        layout.addLayout(task)

        # -- the answer side: a column exactly as wide as the chat's card ----
        self.answer = QWidget(self)
        self.answer.setObjectName("autoAnswerColumn")
        self.answer.setProperty("tone", view.tone)
        self.answer.setFixedWidth(answer_width)
        al = QVBoxLayout(self.answer)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(3)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self.badge = QLabel(view.badge, self.answer)
        self.badge.setObjectName("autoTurnBadge")
        self.badge.setProperty("tone", view.tone)
        self.badge.setVisible(bool(view.badge))
        head.addWidget(self.badge, 0)
        finished = row.get("finished_at")
        self.status_meta = _text_label(
            f"{view.status_text}{' · ' + _clock_utc(finished, seconds=True) if finished else ''}",
            "autoTurnMeta",
            parent=self.answer,
            tone=view.tone if view.tone in {"failed", "waiting"} else "",
        )
        if finished:
            self.status_meta.setToolTip(f"finished {format_utc(finished)}")
        head.addWidget(self.status_meta, 1)
        al.addLayout(head)

        notify = row.get("notify") if isinstance(row.get("notify"), Mapping) else None
        if notify is not None and notify.get("title"):
            al.addWidget(_text_label(str(notify.get("title")), "autoTurnBadge", parent=self.answer, tone="notified"))

        # A failure, a wait or "nothing yet" is said in a card of the chat's
        # assistant-bubble shape, toned by the occurrence.
        self.note: Optional[QFrame] = None
        failure = row.get("failure") if isinstance(row.get("failure"), Mapping) else None
        waits = [w for w in (row.get("waits") or []) if isinstance(w, Mapping)]
        answer_text = str(row.get("answer") or "")
        self.wait_inputs: List[Dict[str, Any]] = []
        if failure is not None or waits or not answer_text:
            self.note = QFrame(self.answer)
            self.note.setObjectName("autoNote")
            self.note.setProperty("tone", view.tone)
            nl = QVBoxLayout(self.note)
            nl.setContentsMargins(12, 10, 12, 12)
            nl.setSpacing(6)
            if failure is not None:
                attempts = int(failure.get("attempts") or row.get("attempts") or 1)
                failure_text = f"{failure.get('message') or 'The occurrence failed.'} ({failure.get('reason_code') or 'failed'}, {attempts} attempt{'s' if attempts != 1 else ''})"
                nl.addWidget(_text_label(failure_text, "autoTurnText", parent=self.note))
            # Pending waits, answered from here by their KIND (decision D1).
            for wait in waits:
                nl.addWidget(self._wait_box(wait, row, parent=self.note))
            if failure is None and not waits and not answer_text:
                nl.addWidget(_text_label("(no answer)", "autoTurnText", parent=self.note, tone="quiet"))
            al.addWidget(self.note)
        self.answer_text: Optional[QWidget] = None
        if answer_text:
            self.answer_text = self._turn(
                "assistant", answer_text, str(row.get("finished_at") or row.get("fired_at") or ""), answer_width, render_turn
            )
            al.addWidget(self.answer_text)
        if quiet:
            # Quiet runs stay readable but recede.
            from PyQt5.QtWidgets import QGraphicsOpacityEffect

            for card in [*self.turn_cards, *([self.note] if self.note is not None else [])]:
                effect = QGraphicsOpacityEffect(card)
                effect.setOpacity(0.62)
                card.setGraphicsEffect(effect)

        artifacts = row.get("artifacts") if isinstance(row.get("artifacts"), list) else []
        if artifacts:
            names = ", ".join(str(a.get("name") or a.get("artifact_id")) for a in artifacts if isinstance(a, Mapping))
            al.addWidget(_text_label(f"Files: {names}", "autoTurnMeta", parent=self.answer))

        # -- Discuss: a compact action under the card, right-aligned --------
        self.discuss_row = QWidget(self.answer)
        dr = QHBoxLayout(self.discuss_row)
        dr.setContentsMargins(0, 1, 0, 0)
        dr.setSpacing(0)
        dr.addStretch(1)
        self.discuss_button = WrappingButton(DISCUSS_LABEL, self.discuss_row)
        self.discuss_button.setToolTip(
            discuss_help(self.index) if discuss_enabled and view.can_discuss else (discuss_reason or "Not while it is running")
        )
        self.discuss_button.setEnabled(bool(discuss_enabled and view.can_discuss))
        self.discuss_button.clicked.connect(self._start_discuss)
        dr.addWidget(self.discuss_button, 0)
        al.addWidget(self.discuss_row)

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

        side = QHBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.addWidget(self.answer, 0)
        side.addStretch(1)
        layout.addLayout(side)

    def _turn(self, role: str, content: str, ts: str, width: int, render_turn: "TurnRenderer") -> QWidget:
        card = render_turn(role, content, ts, width)
        self.turn_cards.append(card)
        self._turn_roles.append(role)
        return card

    def fit(self, viewport_width: int) -> None:
        """The chat's widths for this list width (a resize, a first layout)."""
        for role, card in zip(self._turn_roles, self.turn_cards):
            card.set_bubble_width(self._bubble_width(viewport_width, role=role))
        self.answer.setFixedWidth(self._bubble_width(viewport_width, role="assistant"))

    def _wait_box(self, wait: Mapping[str, Any], row: Mapping[str, Any], *, parent: QWidget) -> QWidget:
        box = QWidget(parent)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 2, 0, 0)
        bl.setSpacing(4)
        run_id = str(wait.get("run_id") or row.get("run_id") or "")
        wait_key = str(wait.get("wait_key") or "")
        kind = str(wait.get("kind") or "")
        entry: Dict[str, Any] = {"run_id": run_id, "wait_key": wait_key, "kind": kind, "choices": [], "edit": None, "send": None}
        self.wait_inputs.append(entry)
        if kind not in WAIT_KINDS:
            # Fail loudly: without a kind there is no answer this client may send.
            bl.addWidget(_text_label(
                f"This run is waiting, but the gateway did not say what answer it expects (kind {kind or 'missing'}). "
                "Answer it from the Observer.", "autoTurnText", parent=box))
            return box
        if kind == "tool_approval":
            bl.addWidget(_text_label(str(wait.get("prompt") or "The run asks to use these tools:"), "autoTurnText", parent=box))
            # `details` = the tool calls this approval would run: [{name, arguments, call_id?}].
            calls = wait.get("details") if isinstance(wait.get("details"), list) else []
            if not calls:
                bl.addWidget(_text_label("The gateway did not list the tool calls to approve.", "autoTurnMeta", parent=box))
            for call in calls:
                if isinstance(call, Mapping):
                    args = call.get("arguments")
                    preview = _clip(json.dumps(args, ensure_ascii=False, sort_keys=True) if args is not None else "", 200)
                    bl.addWidget(_text_label(f"• {call.get('name') or 'tool'} {preview}".rstrip(), "autoTurnMeta", parent=box))
            buttons = QHBoxLayout()
            approve = _button("Approve", "autoPrimary", parent=box)
            deny = _button("Deny", "autoControl", parent=box)
            approve.clicked.connect(lambda _=False: self.wait_answered.emit(run_id, wait_key, kind, True))
            deny.clicked.connect(lambda _=False: self.wait_answered.emit(run_id, wait_key, kind, False))
            buttons.addWidget(approve)
            buttons.addWidget(deny)
            buttons.addStretch(1)
            bl.addLayout(buttons)
            entry.update(approve=approve, deny=deny)
            return box
        if kind == "event":
            # The answer is the event's payload: a JSON value typed here
            # (no choice buttons: the runtime defines none for events).
            bl.addWidget(_text_label(str(wait.get("prompt") or "The run waits for an event."), "autoTurnText", parent=box))
            row_e = QHBoxLayout()
            edit = QLineEdit(box)
            edit.setObjectName("autoInput")
            edit.setPlaceholderText('Event payload (JSON), e.g. {"key": "value"}')
            send = _button("Send event", "autoPrimary", parent=box)
            error = _text_label("", "autoViewError", parent=box)
            error.hide()
            send.clicked.connect(lambda _=False: self._send_event(run_id, wait_key, edit, error))
            edit.returnPressed.connect(lambda: self._send_event(run_id, wait_key, edit, error))
            row_e.addWidget(edit, 1)
            row_e.addWidget(send, 0)
            bl.addLayout(row_e)
            bl.addWidget(error)
            entry.update(edit=edit, send=send, error=error)
            return box
        bl.addWidget(_text_label(str(wait.get("prompt") or "The occurrence is waiting for your answer."), "autoTurnText", parent=box))
        choices_row = QHBoxLayout()
        choices_row.setSpacing(6)
        for choice in wait.get("choices") or []:
            b = _button(str(choice), "autoSmall", parent=box)
            b.clicked.connect(lambda _=False, c=str(choice): self._emit_text(run_id, wait_key, kind, c))
            choices_row.addWidget(b)
            entry["choices"].append(b)
        choices_row.addStretch(1)
        bl.addLayout(choices_row)
        free = QHBoxLayout()
        edit = QLineEdit(box)
        edit.setObjectName("autoInput")
        edit.setPlaceholderText("Or type an answer…")
        send = _button("Answer", "autoPrimary", parent=box)
        send.clicked.connect(lambda _=False: self._send_free(run_id, wait_key, kind, edit))
        edit.returnPressed.connect(lambda: self._send_free(run_id, wait_key, kind, edit))
        free.addWidget(edit, 1)
        free.addWidget(send, 0)
        bl.addLayout(free)
        entry.update(edit=edit, send=send)
        return box

    def _emit_text(self, run_id: str, wait_key: str, kind: str, text: str) -> None:
        self.wait_answered.emit(run_id, wait_key, kind, text)

    def _send_event(self, run_id: str, wait_key: str, edit: QLineEdit, error: QLabel) -> None:
        text = edit.text().strip()
        if not text:
            error.setText("Enter a JSON payload.")
            error.show()
            return
        try:
            payload = json.loads(text)
        except ValueError as exc:
            error.setText(f"The payload is not valid JSON ({exc}).")
            error.show()
            return
        error.hide()
        self.wait_answered.emit(run_id, wait_key, "event", payload)

    def _send_free(self, run_id: str, wait_key: str, kind: str, edit: QLineEdit) -> None:
        text = edit.text().strip()
        if text:
            self._emit_text(run_id, wait_key, kind, text)

    def _start_discuss(self) -> None:
        self.discuss_box.show()
        self.discuss_edit.setFocus(Qt.ShortcutFocusReason)

    def _submit_discuss(self) -> None:
        prompt = self.discuss_edit.text().strip()
        if prompt:
            self.discuss_requested.emit(self.index, prompt)


class AutomationView(QFrame):
    """An automation opened in the palette: its occurrences as a chat, with
    the "Active" switch (on = runs on its schedule, off = paused) and run now /
    edit / archive / discuss."""

    back_requested = pyqtSignal()
    control_requested = pyqtSignal(str)  # pause | resume | run_now | stop_current | archive
    revise_requested = pyqtSignal(object)  # changes
    discuss_requested = pyqtSignal(int, str)
    wait_answered = pyqtSignal(str, str, str, object)
    load_more_requested = pyqtSignal()
    retry_requested = pyqtSignal()

    # Names from the shared `automation_controls.json` (the kit's CONTROL_LABELS).
    # Pause/Resume are not buttons: the "Active" switch sends them (operator
    # 2026-09-30: a persistent on/off state is a switch labelled by the
    # feature, never a Pause/Resume verb pair). These are the one-shot actions.
    CONTROL_LABELS = tuple(
        (control, AUTOMATION_CONTROLS["labels"][control])
        for control in ("run_now", "stop_current", "revise", "archive")
    )
    ACTIVE_LABEL = AUTOMATION_CONTROLS["labels"]["active"]
    # Controls drawn with the kit's glyph (the web clients' icon for the same action).
    CONTROL_ICONS = {"run_now": "play-circle"}

    def __init__(self, *, render_turn: "TurnRenderer", bubble_width: "BubbleWidth", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._render_turn = render_turn
        self._bubble_width = bubble_width
        self.setObjectName("autoView")
        self.summary: Dict[str, Any] = {}
        self.occurrences: List[Dict[str, Any]] = []
        # A command sent and not yet confirmed by the gateway's state.
        self.pending: Optional[str] = None
        self._pending_before: Dict[str, Any] = {}
        self._pending_token = 0
        self.next_cursor: Optional[str] = None
        self.busy = False
        self.pairs: List[OccurrencePair] = []

        # The list spans the history card's full inner width, exactly like the
        # chat's transcript (same x-edges for the bubbles); only the header is
        # inset.
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 2)
        root.setSpacing(6)
        top = QVBoxLayout()
        top.setContentsMargins(4, 0, 4, 0)
        top.setSpacing(6)
        root.addLayout(top)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.back_button = _button("← Chat", "autoControl", parent=self, tooltip="Back to the conversation")
        self.back_button.clicked.connect(self.back_requested.emit)
        head.addWidget(self.back_button, 0)
        self.title_label = QLabel("", self)
        self.title_label.setObjectName("autoViewTitle")
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.title_label, 1)
        top.addLayout(head)
        self.meta_label = _text_label("", "autoViewMeta", parent=self)
        top.addWidget(self.meta_label)

        controls = QHBoxLayout()
        controls.setSpacing(5)
        # The automation's state, first in the bar (as the web panel's bar).
        # The switch shows the gateway's status and changes only when the
        # gateway confirms: a click sends pause/resume and the switch is busy
        # until then.
        self.active_switch = AfSwitch(self.ACTIVE_LABEL, self, reason_inline=True)
        self.active_switch.set_hint(control_hint("active"))
        self.active_switch.clicked.connect(lambda _checked=False: self._on_active_clicked())
        controls.addWidget(self.active_switch)
        controls.addSpacing(6)
        self.control_buttons: Dict[str, QPushButton] = {}
        for control, label in self.CONTROL_LABELS:
            button = _button(label, "autoControl", parent=self, tooltip=control_hint(control))
            self._set_control_icon(control, button)
            button.clicked.connect(lambda _=False, c=control: self._on_control(c))
            controls.addWidget(button)
            self.control_buttons[control] = button
        controls.addStretch(1)
        top.addLayout(controls)

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
        top.addWidget(self.archive_confirm)

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
        self.edit_max_tokens = QSpinBox(self.edit_box)
        self.edit_max_tokens.setObjectName("autoInput")
        self.edit_max_tokens.setRange(1, 2_147_483_647)
        self.edit_max_tokens.setValue(DEFAULT_GROWING_MAX_TOKENS)
        self.edit_max_tokens.setPrefix("Max tokens: ")
        self.edit_max_tokens.setAccessibleName("Max growing context (tokens)")
        self.edit_max_tokens.setToolTip(GROWING_CONTEXT_HELP)
        self.edit_max_tokens.setVisible(False)
        self.edit_context.currentIndexChanged.connect(lambda: self.edit_max_tokens.setVisible(self.edit_context.currentData() == "growing"))
        self.edit_save = _button("Save", "autoPrimary", parent=self.edit_box)
        self.edit_save.clicked.connect(self._save_edit)
        self.edit_cancel = _button("Cancel", "autoControl", parent=self.edit_box)
        self.edit_cancel.clicked.connect(self.edit_box.hide)
        for w, stretch in ((self.edit_title, 1), (self.edit_every, 0), (self.edit_context, 0), (self.edit_max_tokens, 0), (self.edit_save, 0), (self.edit_cancel, 0)):
            el.addWidget(w, stretch)
        self.edit_box.hide()
        top.addWidget(self.edit_box)

        self.error_row = QWidget(self)
        er = QHBoxLayout(self.error_row)
        er.setContentsMargins(0, 0, 0, 0)
        self.error_label = _text_label("", "autoViewError", parent=self.error_row)
        er.addWidget(self.error_label, 1)
        self.retry_button = _button("Retry", "autoControl", parent=self.error_row, tooltip="Send the same request again (same command id)")
        self.retry_button.clicked.connect(self.retry_requested.emit)
        er.addWidget(self.retry_button, 0)
        self.error_row.hide()
        top.addWidget(self.error_row)

        self.notice_label = _text_label("", "autoViewNotice", parent=self)
        self.notice_label.hide()
        top.addWidget(self.notice_label)
        self.attention_label = _text_label("", "autoAttention", parent=self)
        self.attention_label.hide()
        top.addWidget(self.attention_label)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("autoScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_host.setObjectName("autoList")
        self.list_layout = QVBoxLayout(self.list_host)
        # The chat's transcript: no margins, 8 px between turns.
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.list_host)
        self.scroll.viewport().installEventFilter(self)
        root.addWidget(self.scroll, 1)
        self.restyle()

    def restyle(self) -> None:
        self.setStyleSheet(automation_row_qss())

    # ------------------------------------------------------------ state

    @property
    def automation_id(self) -> str:
        return str(self.summary.get("automation_id") or "")

    def controls(self) -> Dict[str, Any]:
        return automation_controls(self.summary, busy=self.busy)

    def set_summary(self, summary: Mapping[str, Any]) -> None:
        """Re-render the header and controls. The chat pairs are rebuilt only
        when what they show changes (the discuss gate): a 60-s poll must not
        wipe an answer or a discuss prompt being typed."""
        incoming = dict(summary)
        if incoming == self.summary:
            return
        before = self.controls()["discuss"] if self.summary else None
        self.summary = incoming
        self._check_pending()
        self.title_label.setText(str(summary.get("title") or "Automation"))
        trigger = summary.get("trigger") if isinstance(summary.get("trigger"), Mapping) else {}
        status = STATUS_LABELS.get(str(summary.get("status") or ""), str(summary.get("status") or ""))
        mode = "Growing — each run sees the previous runs" if summary.get("context_mode") == "growing" else "Independent — each run starts fresh"
        current = current_run(summary)
        running = f"run #{current.get('index')} running" if current is not None else ""
        parts = [trigger_summary(trigger), status, running, _next_run_text(summary), mode, f"{int(summary.get('occurrence_count') or 0)} runs"]
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
        if not self.edit_box.isVisibleTo(self):  # never under the user's typing
            self.edit_title.setText(str(summary.get("title") or ""))
            has_interval = trigger.get("source_id") == "schedule" or is_email_trigger(trigger)
            every = (trigger.get("config") or {}).get("every") if has_interval else None
            self.edit_every.setText(str(every or ""))
            self.edit_every.setEnabled(has_interval)
            self.edit_context.setCurrentIndex(1 if summary.get("context_mode") == "growing" else 0)
            self.edit_max_tokens.setValue(int(summary.get("growing_max_tokens", DEFAULT_GROWING_MAX_TOKENS)))
        self._apply_controls()
        if self.controls()["discuss"] != before:
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

    def _apply_active_switch(self, state: Optional[Dict[str, Any]]) -> None:
        switch = self.active_switch
        switch.blockSignals(True)
        switch.setChecked(self.summary.get("status") == "active")
        switch.blockSignals(False)
        if state is None:  # nothing loaded, or a command waiting for the gateway
            switch.set_busy(self.pending is not None)
            switch.set_unavailable(None if self.pending is not None else "Not loaded yet.")
            if self.pending is not None:
                switch.setToolTip(PENDING_TEXT.get(self.pending, "Waiting for the gateway…"))
            return
        switch.set_busy(False)
        enabled, reason = state["active"]
        switch.set_unavailable(None if enabled else reason, short=active_short_reason(self.summary, reason))

    def _apply_controls(self) -> None:
        if not self.summary:
            self._apply_active_switch(None)
            for button in self.control_buttons.values():
                button.setEnabled(False)
            return
        if self.pending is not None:
            self._apply_active_switch(None)
            for control, button in self.control_buttons.items():
                button.setEnabled(False)
                button.setToolTip(PENDING_TEXT[self.pending] if control == self.pending else "Waiting for the gateway…")
            return
        state = self.controls()
        self._apply_active_switch(state)
        for control, button in self.control_buttons.items():
            enabled, reason = state[control]
            button.setEnabled(bool(enabled))
            # What the control does (the kit's hint, with the next scheduled
            # time for Run now); a disabled control first says why.
            hint = control_hint(control, self.summary)
            button.setToolTip(hint if enabled else f"{reason}\n{hint}")
            button.setAccessibleDescription(hint)

    def _set_control_icon(self, control: str, button: QPushButton) -> None:
        glyph = self.CONTROL_ICONS.get(control)
        if glyph:
            button.setIcon(symbol_icon(glyph, color=THEME.text_secondary, size=12))
            button.setIconSize(QSize(12, 12))
        else:
            button.setIcon(QIcon())

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
            pair = OccurrencePair(
                view,
                discuss_enabled=discuss_enabled,
                discuss_reason=discuss_reason,
                render_turn=self._render_turn,
                bubble_width=self._bubble_width,
                viewport_width=self.list_width(),
                parent=self.list_host,
            )
            pair.discuss_requested.connect(self.discuss_requested.emit)
            pair.wait_answered.connect(self.wait_answered.emit)
            self.list_layout.addWidget(pair)
            self.pairs.append(pair)

    def list_width(self) -> int:
        """The width the turns are laid out in: the list's viewport, as the
        chat sizes its bubbles from the transcript's viewport."""
        return int(self.scroll.viewport().width() or self.width())

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        # The bubbles follow the list's own width (the viewport is sized after
        # this frame, and pairs built before the first layout start narrow).
        if obj is self.scroll.viewport() and event.type() == QEvent.Resize:
            self._fit_turns()
        return super().eventFilter(obj, event)

    def _fit_turns(self) -> None:
        width = self.list_width()
        for pair in self.pairs:
            pair.fit(width)

    def scroll_to_latest(self) -> None:
        """Newest run in view — after the rebuilt pairs are laid out."""
        from PyQt5.QtCore import QTimer

        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    # ------------------------------------------------------------ actions

    def _on_active_clicked(self) -> None:
        # The click already flipped the QCheckBox; the switch shows the
        # gateway's state until it confirms, so put it back and send the
        # transition the kit's activeToggleCommand names.
        self._apply_controls()
        if not self.summary or not self.controls()["active"][0]:
            return
        self._on_control(active_toggle_command(self.summary))

    def _on_control(self, control: str) -> None:
        if control == "revise":
            self.archive_confirm.hide()
            self.edit_box.setVisible(not self.edit_box.isVisibleTo(self))
            return
        if control == "archive":
            self.edit_box.hide()
            self.archive_confirm.show()
            return
        if self.pending is not None:
            return  # one command at a time; the buttons are disabled anyway
        self.begin_pending(control)
        self.control_requested.emit(control)

    def _confirm_archive(self) -> None:
        self.archive_confirm.hide()
        if self.pending is not None:
            return
        self.begin_pending("archive")
        self.control_requested.emit("archive")

    # ---------------------------------------------------------- pending

    PENDING_TIMEOUT_MS = 30_000

    def begin_pending(self, control: str) -> None:
        """The clicked control shows a spinner and every control is disabled
        until the gateway's state confirms the command (or it fails)."""
        from PyQt5.QtCore import QTimer

        self.pending = control
        self._pending_before = dict(self.summary)
        self._pending_token += 1
        token = self._pending_token
        button = self.control_buttons.get(control)  # pause/resume: the Active switch (busy)
        if button is not None:
            button.setText(PENDING_TEXT[control])
            button.setIcon(symbol_icon("loader", color=THEME.accent_text, size=12))
        self._apply_controls()
        # Owned by the view: it dies with the view, never fires into a deleted one.
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._expire_pending(token))
        timer.timeout.connect(timer.deleteLater)
        timer.start(self.PENDING_TIMEOUT_MS)

    def end_pending(self, error: str = "") -> None:
        """Back to the normal controls: confirmed (``error`` empty) or failed."""
        if self.pending is None:
            return
        button = self.control_buttons.get(self.pending)
        if button is not None:
            button.setText(dict(self.CONTROL_LABELS)[self.pending])
            self._set_control_icon(self.pending, button)
        self.pending = None
        self._pending_before = {}
        self._apply_controls()
        if error:
            self.set_error(error)

    def _expire_pending(self, token: int) -> None:
        if self.pending is not None and token == self._pending_token:
            self.end_pending("The gateway has not confirmed the change yet; it may still be applying it. Refresh or try again.")

    def _check_pending(self) -> None:
        if self.pending is not None and self.summary and command_confirmed(self.pending, self._pending_before, self.summary):
            self.end_pending()

    def _save_edit(self) -> None:
        every = self.edit_every.text().strip() if self.edit_every.isEnabled() else None
        changes, errors = revise_changes(
            self.summary,
            title=self.edit_title.text(),
            every=every or None,
            context=str(self.edit_context.currentData()),
            growing_max_tokens=self.edit_max_tokens.value(),
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
    interval, once, or when an email arrives), CONTEXT (Independent /
    Growing), TOOLS, EMAIL (email me the result, allowed recipients).

    The email options are offered only once ``set_email_status`` received a
    usable ``GET /me/email``; until then (and when it is not usable) they are
    disabled under "Connect a mailbox first — open My email", and nothing
    email-shaped is sent."""

    submitted = pyqtSignal(object)  # the POST /automations body
    open_my_email_requested = pyqtSignal()

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

        # The fields scroll inside a height capped to the screen (a 13" laptop
        # has ~800-900 px); the preview, the error and Cancel / Schedule stay
        # in a fixed footer, always visible.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)
        self.form_scroll = QScrollArea(self)
        self.form_scroll.setObjectName("autoScroll")
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.NoFrame)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.form_body = QWidget()
        self.form_body.setObjectName("autoList")
        root = QVBoxLayout(self.form_body)
        root.setContentsMargins(0, 0, 6, 0)
        root.setSpacing(8)
        self.form_scroll.setWidget(self.form_body)
        outer.addWidget(self.form_scroll, 1)

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
        self.preset_combo.addItem(EMAIL_TEXT["trigger_label"], "email")
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
        self._build_email_trigger(root)

        root.addWidget(_text_label("Context", "autoViewTitle", parent=self))
        self.independent = QRadioButton("Independent — each run starts fresh", self)
        self.growing = QRadioButton("Growing — each run sees the previous runs", self)
        self.independent.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.independent)
        group.addButton(self.growing)
        root.addWidget(self.independent)
        root.addWidget(self.growing)
        self.growing_max_tokens = QSpinBox(self)
        self.growing_max_tokens.setObjectName("autoInput")
        self.growing_max_tokens.setRange(1, 2_147_483_647)
        self.growing_max_tokens.setValue(DEFAULT_GROWING_MAX_TOKENS)
        self.growing_max_tokens.setPrefix("Max growing context (tokens): ")
        self.growing_max_tokens.setAccessibleName("Max growing context (tokens)")
        self.growing_max_tokens.setToolTip(GROWING_CONTEXT_HELP)
        self.growing_max_tokens.setVisible(False)
        self.growing.toggled.connect(self.growing_max_tokens.setVisible)
        root.addWidget(self.growing_max_tokens)

        root.addWidget(_text_label("Tools", "autoViewTitle", parent=self))
        self.tools_auto = QRadioButton("Tools run without asking (you approve them now by creating this automation)", self)
        self.tools_ask = QRadioButton("Ask each time (every run waits for your approval)", self)
        self.tools_auto.setChecked(True)
        tools_group = QButtonGroup(self)
        tools_group.addButton(self.tools_auto)
        tools_group.addButton(self.tools_ask)
        root.addWidget(self.tools_auto)
        root.addWidget(self.tools_ask)
        self.untrusted_label = _text_label(EMAIL_TEXT["untrusted_hint"], "autoViewMeta", parent=self)
        root.addWidget(self.untrusted_label)

        self._build_email_options(root)

        root.addStretch(1)
        self.preview_label = _text_label("", "autoViewMeta", parent=self)
        outer.addWidget(self.preview_label)
        self.error_label = _text_label("", "autoViewError", parent=self)
        self.error_label.hide()
        outer.addWidget(self.error_label)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = _button("Cancel", "autoControl", parent=self)
        self.cancel_button.clicked.connect(self.close)
        self.submit_button = _button("Schedule", "autoPrimary", parent=self)
        self.submit_button.clicked.connect(self._submit)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.submit_button)
        outer.addLayout(buttons)
        for signal in (
            self.prompt_edit.textChanged, self.at_edit.textChanged, self.custom_amount.valueChanged, self.custom_unit.currentIndexChanged,
            self.email_every_amount.valueChanged, self.email_every_unit.currentIndexChanged, self.email_max_batch.valueChanged,
            self.email_from_in.textChanged, self.email_from_domain_in.textChanged, self.email_to_in.textChanged,
            self.email_subject.textChanged, self.email_has_attachment.currentIndexChanged,
            self.notify_email.toggled, self.recipients_list.toggled, self.recipients_edit.textChanged,
        ):
            signal.connect(self._update_preview)
        self.email_status: Optional[Dict[str, Any]] = None
        self.email_trigger_available: Optional[bool] = None
        self.set_email_status(None)
        self._sync_when()

    # --------------------------------------------------------------- email

    def _build_email_trigger(self, root: QVBoxLayout) -> None:
        """"When an email arrives": interval (1 hour by default, never under
        60 s — the rule is stated), max batch, typed filters."""
        self.email_box = QWidget(self)
        box = QVBoxLayout(self.email_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        every = QHBoxLayout()
        every.addWidget(_text_label(EMAIL_TEXT["every_label"], "autoViewMeta", parent=self.email_box))
        self.email_every_amount = QSpinBox(self.email_box)
        self.email_every_amount.setObjectName("autoInput")
        self.email_every_amount.setRange(1, 10_000)
        self.email_every_amount.setValue(1)
        self.email_every_unit = QComboBox(self.email_box)
        self.email_every_unit.setObjectName("autoInput")
        for label, unit in (("minutes", "m"), ("hours", "h"), ("days", "d")):
            self.email_every_unit.addItem(label, unit)
        self.email_every_unit.setCurrentIndex(1)
        every.addWidget(self.email_every_amount)
        every.addWidget(self.email_every_unit)
        every.addStretch(1)
        box.addLayout(every)
        self.email_rule = _text_label(EMAIL_TEXT["interval_rule"], "autoViewMeta", parent=self.email_box)
        box.addWidget(self.email_rule)
        batch = QHBoxLayout()
        batch.addWidget(_text_label(EMAIL_TEXT["max_batch_label"], "autoViewMeta", parent=self.email_box))
        self.email_max_batch = QSpinBox(self.email_box)
        self.email_max_batch.setObjectName("autoInput")
        self.email_max_batch.setRange(1, EMAIL_MAX_BATCH)
        self.email_max_batch.setValue(EMAIL_DEFAULT_MAX_BATCH)
        batch.addWidget(self.email_max_batch)
        batch.addStretch(1)
        box.addLayout(batch)
        box.addWidget(_text_label(EMAIL_TEXT["max_batch_hint"], "autoViewMeta", parent=self.email_box))
        box.addWidget(_text_label(EMAIL_TEXT["filters_legend"], "autoViewTitle", parent=self.email_box))

        def line(key: str) -> QLineEdit:
            edit = QLineEdit(self.email_box)
            edit.setObjectName("autoInput")
            edit.setPlaceholderText(EMAIL_TEXT[key])
            edit.setToolTip(EMAIL_TEXT[key])
            box.addWidget(edit)
            return edit

        self.email_from_in = line("from_in")
        self.email_from_domain_in = line("from_domain_in")
        self.email_to_in = line("to_in")
        self.email_subject = line("subject_contains")
        self.email_subject.setMaxLength(200)
        attach = QHBoxLayout()
        attach.addWidget(_text_label(EMAIL_TEXT["has_attachment"], "autoViewMeta", parent=self.email_box))
        self.email_has_attachment = QComboBox(self.email_box)
        self.email_has_attachment.setObjectName("autoInput")
        for value in ("any", "yes", "no"):
            self.email_has_attachment.addItem(EMAIL_TEXT[f"has_attachment_{value}"], value)
        attach.addWidget(self.email_has_attachment)
        attach.addStretch(1)
        box.addLayout(attach)
        box.addWidget(_text_label(EMAIL_TEXT["list_hint"], "autoViewMeta", parent=self.email_box))
        root.addWidget(self.email_box)

    def _build_email_options(self, root: QVBoxLayout) -> None:
        root.addWidget(_text_label("Mailbox", "autoViewTitle", parent=self))
        full, link = EMAIL_TEXT["not_set_up"], EMAIL_TEXT["open_my_email"]
        lead = full[: len(full) - len(link)] if full.endswith(link) else f"{full} "
        self._email_notice_parts = (lead, link)
        self.email_notice = QLabel("", self)
        self.email_notice.setObjectName("autoViewNotice")
        self.email_notice.setTextFormat(Qt.RichText)
        self.email_notice.setWordWrap(True)
        self.email_notice.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
        self.email_notice.linkActivated.connect(lambda _href: self.open_my_email_requested.emit())
        self._render_email_notice()
        root.addWidget(self.email_notice)
        # A switch labelled by the feature; it sets this form's state and the
        # sheet's one primary action (Schedule) saves it.
        self.notify_email = AfSwitch(EMAIL_TEXT["notify_label"], self)
        self.notify_email.set_hint(EMAIL_TEXT["notify_hint"])
        root.addWidget(self.notify_email)
        root.addWidget(_text_label(EMAIL_TEXT["notify_hint"], "autoViewMeta", parent=self))
        self.recipients_container = QWidget(self)
        recipients_layout = QVBoxLayout(self.recipients_container)
        recipients_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.recipients_container)
        recipients_layout.addWidget(_text_label(EMAIL_TEXT["recipients_legend"], "autoViewMeta", parent=self))
        self.recipients_self = QRadioButton(EMAIL_TEXT["recipients_self"], self)
        self.recipients_list = QRadioButton(EMAIL_TEXT["recipients_list"], self)
        self.recipients_self.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.recipients_self)
        group.addButton(self.recipients_list)
        self._recipients_group = group
        recipients_layout.addWidget(self.recipients_self)
        recipients_layout.addWidget(self.recipients_list)
        self.recipients_edit = QLineEdit(self)
        self.recipients_edit.setObjectName("autoInput")
        self.recipients_edit.setPlaceholderText("colleague@example.com")
        recipients_layout.addWidget(self.recipients_edit)
        recipients_layout.addWidget(_text_label(EMAIL_TEXT["recipients_hint"], "autoViewMeta", parent=self))

    def _render_email_notice(self) -> None:
        # The link in the theme's accent (Qt's default link blue is unreadable on the dark themes).
        lead, link = self._email_notice_parts
        self.email_notice.setText(
            f'{html.escape(lead, quote=False)}<a href="my-email" style="color: {THEME.accent_text};">{html.escape(link, quote=False)}</a>'
        )

    def set_email_status(self, status: Optional[Mapping[str, Any]]) -> None:
        """``GET /me/email`` (None = unknown or the call failed = not set up)."""
        self.email_status = dict(status) if isinstance(status, Mapping) else None
        usable = email_usable(self.email_status)
        cause = ""
        if isinstance(self.email_status, Mapping) and isinstance(self.email_status.get("admin_disabled"), Mapping):
            cause = str(self.email_status["admin_disabled"].get("cause") or "")
        self.email_notice.setToolTip(cause)
        self.email_notice.setVisible(not usable)
        # Unavailable (still focusable, reason on hover), never a dead checkbox.
        self.notify_email.set_unavailable(None if usable else NOTIFY_UNAVAILABLE_REASON)
        for widget in (self.recipients_self, self.recipients_list):
            widget.setEnabled(usable)
        self._apply_email_gate()

    def _apply_email_gate(self) -> None:
        offered = self.email_is_usable() and self.email_trigger_available is True
        item = self.preset_combo.model().item(self.preset_combo.findData("email"))
        item.setEnabled(offered)
        item.setToolTip("" if offered or not self.email_is_usable() else "This gateway does not offer the email.received@1 trigger source.")
        if not offered and self.preset_combo.currentData() == "email":
            self.preset_combo.setCurrentIndex(3)
        self._sync_recipients()
        self._update_preview()

    def email_is_usable(self) -> bool:
        return email_usable(self.email_status)

    def _sync_recipients(self) -> None:
        self.recipients_container.setVisible(self.notify_email.isChecked())
        self.recipients_edit.setEnabled(self.email_is_usable() and self.recipients_list.isChecked())

    def email_form(self) -> EmailTriggerForm:
        return EmailTriggerForm(
            uses_model=True,
            every_amount=int(self.email_every_amount.value()),
            every_unit=str(self.email_every_unit.currentData()),
            max_batch=int(self.email_max_batch.value()),
            from_in=self.email_from_in.text(),
            from_domain_in=self.email_from_domain_in.text(),
            to_in=self.email_to_in.text(),
            subject_contains=self.email_subject.text(),
            has_attachment=str(self.email_has_attachment.currentData()),
        )

    def restyle(self) -> None:
        self.setStyleSheet(dialog_stylesheet() + automation_row_qss())
        self._render_email_notice()

    # The tallest the sheet may be: a 13" laptop's usable height, or less on a smaller screen.
    MAX_HEIGHT = 900

    def height_cap(self) -> int:
        screen = self.screen() if hasattr(self, "screen") else None
        available = screen.availableGeometry().height() if screen is not None else self.MAX_HEIGHT
        return max(360, min(self.MAX_HEIGHT, available - 48))

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        """The whole form when it fits, else the height cap (the fields scroll)."""
        margins = self.layout().contentsMargins()
        body = self.form_body.sizeHint()
        footer = sum(
            w.sizeHint().height() + self.layout().spacing()
            for w in (self.preview_label, self.error_label, self.submit_button)
            if w.isVisibleTo(self) or w is self.submit_button
        )
        width = max(body.width() + margins.left() + margins.right() + self.form_scroll.verticalScrollBar().sizeHint().width(), 460)
        height = body.height() + footer + margins.top() + margins.bottom() + self.layout().spacing()
        return QSize(width, min(height, self.height_cap()))

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        # Qt's own first sizing stops at 2/3 of the screen; use the cap instead.
        if not getattr(self, "_sized_once", False):
            self._sized_once = True
            self.resize(self.sizeHint())
        super().showEvent(event)

    def set_trigger_sources(self, items: Sequence[Mapping[str, Any]]) -> None:
        """``schedule@1`` must be offered by the gateway, else nothing can be scheduled."""
        available = any(
            isinstance(i, Mapping) and i.get("id") == "schedule" and i.get("version") == 1 and i.get("available") is True
            for i in items
        )
        self.schedule_available = available
        # `email.received@1` is offered only when the gateway lists it (and the account is usable).
        self.email_trigger_available = any(
            isinstance(i, Mapping) and i.get("id") == "email.received" and i.get("version") == 1 and i.get("available") is True
            for i in items
        )
        if not available:
            self.set_error("This gateway does not offer the schedule@1 trigger source.")
        self._apply_email_gate()

    def set_error(self, text: str) -> None:
        value = str(text or "").strip()
        self.error_label.setText(value)
        self.error_label.setVisible(bool(value))

    def when(self) -> ScheduleWhen:
        data = self.preset_combo.currentData()
        if data == "email":
            return SCHEDULE_PRESETS[3][1]  # unused: the email trigger ignores `when`
        if data == "custom":
            return ScheduleWhen("every", int(self.custom_amount.value()), str(self.custom_unit.currentData()))
        if data == "once":
            return ScheduleWhen("once", at=self.at_edit.text().strip())
        return data

    def _sync_when(self) -> None:
        self.setMaximumHeight(self.height_cap())
        data = self.preset_combo.currentData()
        self.custom_host.setVisible(data == "custom")
        self.email_box.setVisible(data == "email")
        self.untrusted_label.setVisible(data == "email")
        self.at_edit.setVisible(data != "email")
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
            growing_max_tokens=self.growing_max_tokens.value(),
            target=self.target,
            request_id=self.request_id,
            title=self.title_edit.text(),
            start_at="" if when.kind == "once" or self.preset_combo.currentData() == "email" else self.at_edit.text().strip(),
            tool_approval="ask" if self.tools_ask.isChecked() else "auto",
            # Nothing email-shaped without a usable account.
            **(
                {
                    "trigger": "email" if self.preset_combo.currentData() == "email" and self.email_trigger_available is True else "schedule",
                    "email": self.email_form(),
                    "notify_email": self.notify_email.isChecked(),
                    "email_recipients": ("list" if self.recipients_list.isChecked() else "self", self.recipients_edit.text()),
                }
                if self.email_is_usable()
                else {}
            ),
        )

    def _update_preview(self) -> None:
        if not hasattr(self, "email_status"):
            return  # still building
        self._sync_recipients()
        body, errors = self.build_body()
        if body is not None and body["trigger"]["source_id"] != "schedule":
            self.preview_label.setText(trigger_summary(body["trigger"]))
        elif body is not None:
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
    gateway connection; ``available`` says whether the gateway advertises the
    Automations API (capabilities ``contracts.common.automations.available``)
    and raises when that cannot be read. ``notify(title, body)`` shows a tray
    notification.
    ``synchronous=True`` runs calls inline (tests).
    """

    summaries_changed = pyqtSignal(object)
    _finished = pyqtSignal(object, object)

    def __init__(
        self,
        *,
        client_factory: Callable[[], AutomationsClient],
        available: Callable[[], bool],
        notify: Callable[[str, str], None],
        ledger: NotificationLedger,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._client_factory = client_factory
        self._available = available
        self._notify = notify
        self.ledger = ledger
        self.synchronous = False
        self.summaries: List[Dict[str, Any]] = []
        # None = not asked yet; False = the gateway has no Automations API.
        self.available: Optional[bool] = None
        self.error = ""
        self._polling = False
        self._poll_again = False
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
            # A poll is in flight: run another right after it (a command result
            # must not wait for the next interval to show its confirmed state).
            self._poll_again = True
            return
        self._polling = True
        self._poll_again = False

        def work():
            if not self._available():
                return None  # not advertised: no Automations surface at all
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
            if ok and value is None:
                self.available = False
                self.error = ""
                self.summaries = []
            elif ok:
                summaries, pages = value
                self.available = True
                self.error = ""
                self.summaries = [dict(s) for s in summaries]
                notices = new_attention_notices(self.summaries, pages, self.ledger)
                for notice in notices:
                    self._notify(notice.title, notice.body or notice.title)
                self.ledger.add(n.key for n in notices)
            else:
                self.error = self.error_text(value)
            self.summaries_changed.emit(list(self.summaries))
            if on_done is not None:
                on_done()
            if self._poll_again:
                self._poll_again = False
                self.poll()

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

    def my_email(self, done: Callable[[bool, Any], None]) -> None:
        """``GET /me/email`` (the Schedule sheet's email options)."""
        self._submit(lambda: self._client_factory().my_email(), done)

    def run(self, work: Callable[[], Any], done: Callable[[bool, Any], None]) -> None:
        """Any other blocking call (the wait answer), off the GUI thread."""
        self._submit(work, done)
