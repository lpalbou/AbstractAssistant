"""Modeless tool-approval sheet and the tool-call card it shares with the
post-hoc "tools used" dialog.

Design rules (spec §3, adversarial findings 4 & 5):

- The sheet is never modal and never runs a nested event loop. It reports
  through ``decided(decision, info)`` — ``once`` | ``session`` | ``deny`` |
  ``defer`` — exactly once per batch, and each batch carries its own
  ``run_id`` / ``wait_key`` so a second request can be queued behind the first
  (``enqueue``) instead of stealing its answer.
- ``Allow once`` is the only default button; every other push button has
  ``autoDefault`` off so Return can never toggle an expander. Esc, the window
  close button and ``reject()`` all mean "decide later" — a dismissal never
  tells the model "denied".
- Blanket trust ("Allow all enabled tools in this chat") lives in a menu
  next to the primary button and is disabled for batches that reach outside,
  destroy, or include a tool the gateway does not list.
- Risk comes from the gateway inventory via ``describe_tool_risk``; the card
  only lays it out. Colors come from ``theme.py`` tokens only.

Placement (centring over the palette, raise/activate) is the caller's job.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List, Optional

from PyQt5.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAbstractSpinBox,
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from abstractassistant.core.tool_presenter import (
    CallPresentation,
    batch_tier,
    clip_lines,
    present_call,
    tool_calls_text,
    toolset_glyph,
)
from abstractassistant.icons import symbol_icon
from abstractassistant.theme import METRICS, THEME
from abstractassistant.ui.styles import MONO_STACK, dialog_stylesheet, refresh_style


SHEET_WIDTH = 560
SHEET_MIN_HEIGHT = 320
SHEET_MAX_HEIGHT = 640
# Above this tier the blanket grant is still OFFERED, but it names what it
# covers: a grant made on a destructive batch is a decision, not a default.
SESSION_TRUST_PLAIN_MAX_RANK = 2
SESSION_TRUST_LABELS = {
    3: "Allow all enabled tools in this chat, including ones that reach outside",
    4: "Allow all enabled tools in this chat, including destructive ones",
}

_T = THEME
_M = METRICS

# Every value below is a THEME/METRICS token; the module carries no literals.
APPROVAL_QSS = f"""
    QFrame#toolApprovalCallCard {{
        background: {_T.overlay_faint};
        border: 1px solid {_T.border_subtle};
        border-radius: {_M.radius_control + 1}px;
    }}
    QFrame#toolApprovalCallCard[unavailable="true"] {{
        border-style: dashed;
    }}
    QLabel#toolApprovalName {{
        color: {_T.text_strong};
        font-size: {_M.font_body}px;
        font-weight: 700;
    }}
    QLabel#toolApprovalReason {{
        color: {_T.text_muted};
        font-size: {_M.font_caption}px;
    }}
    QFrame#toolApprovalHeadline {{
        background: {_T.code.background};
        border: 1px solid {_T.code.border};
        border-radius: {_M.radius_control - 1}px;
    }}
    QFrame#toolApprovalHeadline QLabel#mono {{
        color: {_T.code.text};
        font-size: {_M.font_ui}px;
    }}
    QLabel#toolApprovalParamKey {{
        color: {_T.text_muted};
        font-size: {_M.font_caption}px;
        font-weight: 600;
    }}
    QLabel#toolApprovalParamValue {{
        color: {_T.text_secondary};
        font-size: {_M.font_caption}px;
        font-family: {MONO_STACK};
    }}
    QLabel#toolApprovalDividerLabel {{
        color: {_T.text_faint};
        font-size: {_M.font_caption}px;
        font-weight: 600;
        letter-spacing: 0.04em;
    }}
    QLabel#chip[tone="unknown"] {{
        border-style: dashed;
    }}
    QLabel#usageStatusChip {{
        padding: 1px 8px;
        border-radius: 8px;
        font-size: {_M.font_caption}px;
        font-weight: 700;
        letter-spacing: 0.04em;
        color: {_T.text_secondary};
        background: {_T.overlay_faint};
        border: 1px solid {_T.border_subtle};
    }}
    QLabel#usageStatusChip[tone="ok"] {{
        color: {_T.positive};
        background: {_T.positive_bg};
        border-color: {_T.positive_bg};
    }}
    QLabel#usageStatusChip[tone="failed"] {{
        color: {_T.danger_text};
        background: {_T.danger_bg};
        border-color: {_T.danger_bg};
    }}
    QLabel#usageCardIndex {{
        color: {_T.text_faint};
        font-size: {_M.font_caption}px;
        font-weight: 700;
    }}
    /* Post-hoc dialogs in app.py reuse these two names for their subtitle
       and Close button; style them as the shared subtitle / secondary. */
    QLabel#toolApprovalHint {{
        color: {_T.text_muted};
        font-size: {_M.font_caption}px;
    }}
    QPushButton#toolApprovalSecondaryButton {{
        background: {_T.overlay_faint};
        color: {_T.text_secondary};
        border: 1px solid {_T.border_subtle};
    }}
    QPushButton#toolApprovalSecondaryButton:hover {{
        background: {_T.overlay_hover};
        border-color: {_T.border_strong};
        color: {_T.text_strong};
    }}
    QLabel#queueNote {{
        color: {_T.attention_text};
        font-size: {_M.font_caption}px;
        font-weight: 600;
    }}
    QLabel#usageCardError {{
        color: {_T.danger_text};
        font-size: {_M.font_caption}px;
        background: {_T.danger_bg};
        border: 1px solid {_T.danger_bg};
        border-radius: {_M.radius_chip + 2}px;
        padding: 8px 10px;
    }}
    QCheckBox#rememberTool {{
        font-size: {_M.font_ui}px;
    }}
    QPushButton#secondaryButton[role="deny"]:hover {{
        background: {_T.danger_bg};
        color: {_T.danger_text};
        border-color: {_T.danger_text};
    }}
    QPushButton#primaryButton[role="menu"] {{
        padding: 3px 9px;
    }}
    QPushButton#primaryButton[role="menu"]::menu-indicator {{
        image: none;
        width: 0px;
    }}
    QMenu {{
        background: {_T.surface_raised};
        color: {_T.text_primary};
        border: 1px solid {_T.border_strong};
        border-radius: {_M.radius_control - 2}px;
        padding: 4px;
        font-size: {_M.font_ui}px;
    }}
    QMenu::item {{
        padding: 6px 12px;
        border-radius: {_M.radius_chip}px;
    }}
    QMenu::item:selected {{
        background: {_T.accent_bg};
        color: {_T.text_strong};
    }}
    QMenu::item:disabled {{
        color: {_T.text_faint};
    }}
"""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


class _ReturnSwallow(QObject):
    """Eat plain Return/Enter inside read-only panels so reading the JSON can
    never activate the dialog's default button (Cmd+Return still works)."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt API)
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter) and not (
                event.modifiers() & ~Qt.KeypadModifier
            ):
                return True
        return super().eventFilter(obj, event)


def _chip(text: str, tone: str, parent: Optional[QWidget] = None) -> QLabel:
    chip = QLabel(str(text or ""), parent)
    chip.setObjectName("chip")
    chip.setProperty("tone", str(tone or "neutral"))
    chip.setAlignment(Qt.AlignCenter)
    return chip


def _key_hint(text: str, parent: Optional[QWidget] = None) -> QLabel:
    """Muted key cap (``⏎`` / ``D`` / ``esc``) shown beside an action."""
    hint = QLabel(str(text or ""), parent)
    hint.setObjectName("keyHint")
    hint.setAlignment(Qt.AlignCenter)
    hint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    return hint


def _status_chip(text: str, tone: str, parent: Optional[QWidget] = None) -> QLabel:
    chip = QLabel(str(text or "").upper(), parent)
    chip.setObjectName("usageStatusChip")
    chip.setProperty("tone", str(tone or "neutral"))
    chip.setAlignment(Qt.AlignCenter)
    return chip


def _wrapped_label(text: str, object_name: str, parent: Optional[QWidget] = None) -> QLabel:
    """Word-wrapped, selectable label that never widens its card: a long token
    without spaces gets clipped instead of pushing the fixed-width sheet."""
    label = QLabel(str(text or ""), parent)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    return label


def _mono_panel(text: str, object_name: str, *, min_h: int, max_h: int, parent: Optional[QWidget] = None) -> QPlainTextEdit:
    panel = QPlainTextEdit(parent)
    panel.setObjectName(object_name)
    panel.setReadOnly(True)
    panel.setPlainText(str(text or ""))
    panel.setMinimumHeight(min_h)
    panel.setMaximumHeight(max_h)
    panel.setLineWrapMode(QPlainTextEdit.WidgetWidth)
    swallow = _ReturnSwallow(panel)
    panel.installEventFilter(swallow)
    panel.hide()
    return panel


def _expander(title: str, panel: QWidget, parent: Optional[QWidget] = None) -> QPushButton:
    """`▸ Title` link that toggles ``panel``; never a default button."""
    button = QPushButton(f"▸ {title}", parent)
    button.setObjectName("linkButton")
    button.setCheckable(True)
    button.setAutoDefault(False)
    button.setDefault(False)
    button.setCursor(Qt.PointingHandCursor)

    def _toggle(checked: bool) -> None:
        panel.setVisible(bool(checked))
        button.setText(f"{'▾' if checked else '▸'} {title}")

    button.toggled.connect(_toggle)
    return button


def _icon_color(presentation: CallPresentation) -> str:
    if presentation.success is False:
        return _T.danger
    if not presentation.available:
        return _T.text_faint
    tone = str(presentation.risk.get("tone") or "")
    if tone == "destroy":
        return _T.danger
    if tone == "outreach":
        return _T.warning
    if tone == "unknown":
        return _T.text_muted
    return _T.accent


# --------------------------------------------------------------------------- #
# Card
# --------------------------------------------------------------------------- #


class ToolCallCard(QFrame):
    """One tool call, judged at a glance.

    ``mode="approval"`` (the sheet) shows the risk chips, the promoted
    headline, secondary parameters, previews and a hidden remember box.
    ``mode="result"`` (post-hoc dialogs) adds the ``usageStatusChip``
    (COMPLETED / FAILED / DONE), the error block and an Output expander.
    """

    def __init__(
        self,
        *,
        call: Any,
        index: int,
        mode: str = "approval",
        risk: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("toolApprovalCallCard")
        self.index = int(index or 0)
        self.call: Dict[str, Any] = call if isinstance(call, dict) else {}
        self.presentation: CallPresentation = present_call(call, risk)
        p = self.presentation
        self.mode = "result" if str(mode or "").lower() == "result" or isinstance(p.success, bool) else "approval"
        result_mode = self.mode == "result"
        self.setProperty("unavailable", "true" if not p.available else "false")

        self.remember_checkbox: Optional[QCheckBox] = None
        self.raw_toggle: QPushButton
        self.raw_panel: QPlainTextEdit
        self.preview_panels: List[QPlainTextEdit] = []
        self.output_panel: Optional[QPlainTextEdit] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # -- header: glyph · name / reason · chips ------------------------- #
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        root.addLayout(header)

        glyph = QLabel(self)
        glyph.setObjectName("toolApprovalIcon")
        size = _M.icon_md
        glyph.setPixmap(
            symbol_icon(toolset_glyph(p.name, risk), color=_icon_color(p), size=size).pixmap(size, size)
        )
        glyph.setFixedSize(size + 2, size + 4)
        header.addWidget(glyph, 0, Qt.AlignTop)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 0, 0)
        title_wrap.setSpacing(2)
        header.addLayout(title_wrap, 1)

        self.name_label = QLabel(p.name, self)
        self.name_label.setObjectName("toolApprovalName")
        self.name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        title_wrap.addWidget(self.name_label)

        self.reason_label = _wrapped_label(p.reason, "toolApprovalReason", self)
        title_wrap.addWidget(self.reason_label)

        chips = QHBoxLayout()
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(4)
        header.addLayout(chips, 0)
        header.setAlignment(chips, Qt.AlignTop | Qt.AlignRight)

        self.risk_chip: Optional[QLabel] = None
        # A post-hoc card built without a lookup is "not looked up", not
        # "unknown tool": only the approval sheet fails closed on a chip.
        if risk is not None or not result_mode:
            self.risk_chip = _chip(str(p.risk.get("label") or ""), str(p.risk.get("tone") or "unknown"), self)
            self.risk_chip.setToolTip(str(p.risk.get("sentence") or ""))
            chips.addWidget(self.risk_chip)
        for label, tone in p.flags:
            chips.addWidget(_chip(label, tone, self))
        if not p.available:
            chips.addWidget(_chip("Disabled on gateway", "warn", self))
        self.status_chip: Optional[QLabel] = None
        if result_mode:
            if p.success is True:
                self.status_chip = _status_chip("completed", "ok", self)
            elif p.success is False:
                self.status_chip = _status_chip("failed", "failed", self)
            else:
                self.status_chip = _status_chip("done", "neutral", self)
            chips.addWidget(self.status_chip)
            order = QLabel(f"#{self.index + 1}", self)
            order.setObjectName("usageCardIndex")
            chips.addWidget(order)

        # -- honesty captions ---------------------------------------------- #
        captions: List[str] = []
        if p.unknown and not result_mode:
            captions.append("This tool is not in the gateway's inventory.")
        if not p.available:
            captions.append("Approval cannot run it." if not result_mode else "Disabled on the gateway.")
        if not result_mode and p.approval_default == "auto":
            captions.append("Gateway default: auto · asking because this Mac set Ask")
        for caption in captions:
            note = _wrapped_label(caption, "cardHelp", self)
            root.addWidget(note)

        # -- headline block ------------------------------------------------ #
        self.headline_label: Optional[QLabel] = None
        if p.headline:
            well = QFrame(self)
            well.setObjectName("toolApprovalHeadline")
            well_layout = QVBoxLayout(well)
            well_layout.setContentsMargins(10, 8, 10, 8)
            self.headline_label = _wrapped_label(clip_lines(p.headline), "mono", well)
            self.headline_label.setToolTip(p.headline if "\n" in p.headline else "")
            well_layout.addWidget(self.headline_label)
            root.addWidget(well)

        # -- secondary parameters ----------------------------------------- #
        if p.params:
            grid_host = QWidget(self)
            grid = QGridLayout(grid_host)
            grid.setContentsMargins(2, 0, 2, 0)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(4)
            grid.setColumnStretch(1, 1)
            for row, (key, value, tooltip) in enumerate(p.params):
                key_label = QLabel(str(key), grid_host)
                key_label.setObjectName("toolApprovalParamKey")
                key_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                if tooltip:
                    key_label.setToolTip(tooltip)
                grid.addWidget(key_label, row, 0)
                value_label = _wrapped_label(str(value), "toolApprovalParamValue", grid_host)
                if tooltip:
                    value_label.setToolTip(tooltip)
                grid.addWidget(value_label, row, 1)
            root.addWidget(grid_host)

        # -- content blocks (never inline) --------------------------------- #
        for key, summary, preview in p.content_blocks:
            row = QHBoxLayout()
            row.setContentsMargins(2, 0, 2, 0)
            row.setSpacing(8)
            caption = QLabel(f"{key} · {summary}", self)
            caption.setObjectName("toolApprovalParamKey")
            row.addWidget(caption)
            panel = _mono_panel(preview, "monoPanel", min_h=120, max_h=200, parent=self)
            self.preview_panels.append(panel)
            row.addWidget(_expander("Preview", panel, self))
            row.addStretch(1)
            root.addLayout(row)
            root.addWidget(panel)

        # -- result-only: error + output ----------------------------------- #
        if p.error:
            root.addWidget(_wrapped_label(p.error, "usageCardError", self))
        if result_mode and p.output_preview:
            self.output_panel = _mono_panel(p.output_preview, "monoPanel", min_h=100, max_h=200, parent=self)
            root.addWidget(_expander("Output", self.output_panel, self), 0, Qt.AlignLeft)
            root.addWidget(self.output_panel)

        # -- full call ------------------------------------------------------ #
        raw_row = QHBoxLayout()
        raw_row.setContentsMargins(0, 0, 0, 0)
        raw_row.setSpacing(8)
        self.raw_panel = _mono_panel(p.raw_json, "toolApprovalRawPanel", min_h=132, max_h=220, parent=self)
        self.raw_toggle = _expander("Full call (JSON)", self.raw_panel, self)
        raw_row.addWidget(self.raw_toggle)
        if p.secrets_masked:
            masked = QLabel("Secrets masked", self)
            masked.setObjectName("cardHelp")
            masked.setToolTip("Values under token / secret / password / api key / authorization / cookie keys are hidden here and in the JSON.")
            raw_row.addWidget(masked)
        raw_row.addStretch(1)
        root.addLayout(raw_row)
        root.addWidget(self.raw_panel)

        # -- remember (approval only; the sheet decides who shows it) ------ #
        if not result_mode:
            self.remember_checkbox = QCheckBox(f"Always allow {p.name} on this Mac", self)
            self.remember_checkbox.setObjectName("rememberTool")
            self.remember_checkbox.setEnabled(self.remember_offerable)
            self.remember_checkbox.hide()
            root.addWidget(self.remember_checkbox)

        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)

    # -- API used by the sheet ------------------------------------------- #

    @property
    def remember_offerable(self) -> bool:
        """Never offer blanket per-tool trust for disabled or unlisted tools,
        nor for outreach/destroy tiers — those are approved one call at a time."""
        p = self.presentation
        if not (p.available and not p.unknown):
            return False
        risk = getattr(p, "risk", None)
        if isinstance(risk, dict):
            rank = int(risk.get("rank") or 0)
        else:
            rank = int(getattr(p, "risk_rank", 0) or 0)
        return 0 < rank <= 2

    @property
    def remember_checked(self) -> bool:
        box = self.remember_checkbox
        return bool(box is not None and box.isEnabled() and box.isChecked())

    def set_full_call_visible(self, visible: bool) -> None:
        self.raw_toggle.setChecked(bool(visible))

    def full_call_visible(self) -> bool:
        return bool(self.raw_toggle.isChecked())


def ToolApprovalCallCard(*, call: Any, index: int, parent: Optional[QWidget] = None) -> ToolCallCard:  # noqa: N802
    """Constructor-compatible alias for the post-hoc dialogs: result mode
    when the call carries a boolean ``success``, approval mode otherwise."""
    success = call.get("success") if isinstance(call, dict) else None
    mode = "result" if isinstance(success, bool) else "approval"
    return ToolCallCard(call=call, index=index, mode=mode, parent=parent)


# --------------------------------------------------------------------------- #
# Sheet
# --------------------------------------------------------------------------- #


def _is_text_control(widget: Optional[QWidget]) -> bool:
    return isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox))


class ToolApprovalSheet(QDialog):
    """Modeless approval sheet; one decision per batch via ``decided``."""

    decided = pyqtSignal(str, object)
    stop_requested = pyqtSignal()

    def __init__(
        self,
        *,
        tool_calls: Any,
        risks: Optional[Dict[str, Any]] = None,
        run_id: str = "",
        wait_key: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("toolApprovalSheet")
        self.setWindowTitle("Approve tools")
        self.setModal(False)
        self.setWindowFlags(
            Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.CustomizeWindowHint
            | Qt.WindowTitleHint
            | Qt.WindowCloseButtonHint
        )
        self.setFixedWidth(SHEET_WIDTH)
        self.setMinimumHeight(SHEET_MIN_HEIGHT)
        self.setMaximumHeight(SHEET_MAX_HEIGHT)
        self.setSizeGripEnabled(False)

        self.approval_scope = "once"
        self.current_batch: Dict[str, Any] = {}
        self.card_widgets: List[ToolCallCard] = []
        self.batch_risk: Dict[str, Any] = {}
        self._queue: Deque[Dict[str, Any]] = deque()
        self._decided = True  # nothing loaded yet
        self._single_remember = False
        self._host_items: List[QWidget] = []

        self._build_chrome()
        self.setStyleSheet(dialog_stylesheet() + APPROVAL_QSS)
        self._install_shortcuts()
        self._load_batch(self._batch(tool_calls, risks, run_id, wait_key))

    # -- construction ------------------------------------------------------ #

    def _build_chrome(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        root.addLayout(header)

        glyph = QLabel(self)
        glyph.setObjectName("toolApprovalSheetIcon")
        size = 20
        glyph.setPixmap(symbol_icon("shield-alert", color=_T.warning, size=size).pixmap(size, size))
        glyph.setFixedSize(size + 2, size + 4)
        header.addWidget(glyph, 0, Qt.AlignTop)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 0, 0)
        title_wrap.setSpacing(3)
        header.addLayout(title_wrap, 1)

        self.title_label = QLabel("", self)
        self.title_label.setObjectName("dialogTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        title_wrap.addWidget(self.title_label)

        caption = QHBoxLayout()
        caption.setContentsMargins(0, 0, 0, 0)
        caption.setSpacing(6)
        title_wrap.addLayout(caption)
        lead = QLabel("Highest risk in this batch:", self)
        lead.setObjectName("dialogSubtitle")
        caption.addWidget(lead)
        self.tier_chip = _chip("", "unknown", self)
        caption.addWidget(self.tier_chip)
        self.run_label = QLabel("", self)
        self.run_label.setObjectName("dialogSubtitle")
        caption.addWidget(self.run_label)
        caption.addStretch(1)

        top_divider = QFrame(self)
        top_divider.setObjectName("divider")
        root.addWidget(top_divider)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._scroll, 1)

        self._host = QWidget()
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setContentsMargins(0, 0, 4, 0)
        self._host_layout.setSpacing(8)
        self._host_layout.addStretch(1)
        self._scroll.setWidget(self._host)

        self.remember_checkbox = QCheckBox("", self)
        self.remember_checkbox.setObjectName("rememberTool")
        self.remember_checkbox.hide()
        root.addWidget(self.remember_checkbox)

        self.remember_help = QLabel(
            "Takes effect from your next message; this pre-approves the tool even where the gateway would ask.",
            self,
        )
        self.remember_help.setObjectName("cardHelp")
        self.remember_help.setWordWrap(True)
        self.remember_help.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.remember_help.hide()
        root.addWidget(self.remember_help)

        bottom_divider = QFrame(self)
        bottom_divider.setObjectName("divider")
        root.addWidget(bottom_divider)

        self.queue_note = QLabel("", self)
        self.queue_note.setObjectName("queueNote")
        self.queue_note.hide()
        root.addWidget(self.queue_note)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        root.addLayout(actions)

        self.deferButton = QPushButton("Decide later", self)
        self.deferButton.setObjectName("ghostButton")
        self.deferButton.setToolTip("Keep the run waiting; the assistant asks again later (Esc)")
        self.deferButton.setAutoDefault(False)
        self.deferButton.setDefault(False)
        self.deferButton.clicked.connect(lambda: self._decide("defer"))
        actions.addWidget(self.deferButton)
        self.defer_hint = _key_hint("esc", self)
        actions.addWidget(self.defer_hint, 0, Qt.AlignVCenter)
        actions.addStretch(1)

        self.denyButton = QPushButton("Deny", self)
        self.denyButton.setObjectName("secondaryButton")
        self.denyButton.setProperty("role", "deny")
        self.denyButton.setToolTip("Don't run these calls (D or ⌘D)")
        self.denyButton.setAutoDefault(False)
        self.denyButton.setDefault(False)
        self.denyButton.clicked.connect(self._deny)
        actions.addWidget(self.denyButton)
        self.deny_hint = _key_hint("D", self)
        actions.addWidget(self.deny_hint, 0, Qt.AlignVCenter)
        actions.addSpacing(6)

        split = QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(2)
        actions.addLayout(split)

        self.allowOnceButton = QPushButton("Allow once", self)
        self.allowOnceButton.setObjectName("primaryButton")
        self.allowOnceButton.setToolTip("Run these calls once (⏎)")
        self.allowOnceButton.setAutoDefault(True)
        self.allowOnceButton.setDefault(True)
        self.allowOnceButton.clicked.connect(self._allow_once)
        split.addWidget(self.allowOnceButton)

        # QPushButton.setMenu() turns a click into "open the menu", so the
        # blanket grant hangs off a sibling chevron: a split button.
        self.allowMenuButton = QPushButton("▾", self)
        self.allowMenuButton.setObjectName("primaryButton")
        self.allowMenuButton.setProperty("role", "menu")
        self.allowMenuButton.setToolTip("More ways to allow")
        self.allowMenuButton.setAutoDefault(False)
        self.allowMenuButton.setDefault(False)
        self.allowMenuButton.setFixedWidth(_M.control_sm)
        self.allow_menu = QMenu(self.allowMenuButton)
        self.allow_menu.setToolTipsVisible(True)
        self.allow_session_action = QAction("Allow all enabled tools in this chat", self.allow_menu)
        self.allow_session_action.triggered.connect(self._allow_session)
        self.allow_menu.addAction(self.allow_session_action)
        self.allowMenuButton.setMenu(self.allow_menu)
        split.addWidget(self.allowMenuButton)
        self.allow_hint = _key_hint("⏎", self)
        actions.addWidget(self.allow_hint, 0, Qt.AlignVCenter)

    def _install_shortcuts(self) -> None:
        def _bind(sequence: str, slot) -> None:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(slot)

        _bind("Ctrl+Return", self._allow_once)
        _bind("Ctrl+Enter", self._allow_once)
        _bind("Shift+Return", self._allow_session)
        _bind("Shift+Enter", self._allow_session)
        _bind("Ctrl+D", self._deny)
        _bind("Ctrl+.", self.stop_requested.emit)

    # -- batches ----------------------------------------------------------- #

    @staticmethod
    def _batch(tool_calls: Any, risks: Optional[Dict[str, Any]], run_id: str, wait_key: str) -> Dict[str, Any]:
        calls = [call for call in list(tool_calls or []) if isinstance(call, dict)] if isinstance(tool_calls, list) else []
        return {
            "tool_calls": calls,
            "raw_tool_calls": tool_calls,
            "risks": dict(risks) if isinstance(risks, dict) else {},
            "run_id": str(run_id or "").strip(),
            "wait_key": str(wait_key or "").strip(),
        }

    @property
    def pending_count(self) -> int:
        """Batches waiting behind the one on screen."""
        return len(self._queue)

    def enqueue(
        self,
        tool_calls: Any,
        *,
        run_id: str = "",
        wait_key: str = "",
        risks: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Queue a later batch; it is shown once the current one is decided.

        With nothing on screen (every earlier batch decided) the batch loads
        immediately and the sheet re-shows itself where it last was.
        """
        batch = self._batch(tool_calls, risks, run_id, wait_key)
        ident = (str(batch.get("run_id") or ""), str(batch.get("wait_key") or ""))
        if ident != ("", ""):
            # The same undecided wait raised twice (re-shown from the palette
            # and from the activity card) is one question, not two.
            current = self.current_batch or {}
            if (str(current.get("run_id") or ""), str(current.get("wait_key") or "")) == ident:
                if not self.isVisible():
                    self.show()
                return
            for queued in self._queue:
                if (str(queued.get("run_id") or ""), str(queued.get("wait_key") or "")) == ident:
                    return
        if not self.current_batch:
            self._load_batch(batch)
            if not self.isVisible():
                self.show()
            return
        self._queue.append(batch)
        self._refresh_queue_note()

    def _refresh_queue_note(self) -> None:
        count = len(self._queue)
        if count <= 0:
            self.queue_note.clear()
            self.queue_note.hide()
            return
        self.queue_note.setText(f"{count} more batch{'es' if count != 1 else ''} waiting")
        self.queue_note.show()

    def _clear_host(self) -> None:
        for widget in self._host_items:
            self._host_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self._host_items = []
        self.card_widgets = []

    def _add_host_item(self, widget: QWidget) -> None:
        # Keep the trailing stretch last.
        self._host_layout.insertWidget(self._host_layout.count() - 1, widget)
        self._host_items.append(widget)

    def _divider_row(self, text: str) -> QWidget:
        row = QWidget(self._host)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)
        left = QFrame(row)
        left.setObjectName("divider")
        layout.addWidget(left, 1)
        label = QLabel(text, row)
        label.setObjectName("toolApprovalDividerLabel")
        layout.addWidget(label, 0)
        right = QFrame(row)
        right.setObjectName("divider")
        layout.addWidget(right, 1)
        return row

    def _load_batch(self, batch: Dict[str, Any]) -> None:
        self._clear_host()
        self.current_batch = batch
        self._decided = False
        calls: List[Dict[str, Any]] = list(batch.get("tool_calls") or [])
        risks: Dict[str, Any] = dict(batch.get("risks") or {})
        run_id = str(batch.get("run_id") or "")

        tier = batch_tier(calls, risks)
        self.batch_risk = tier

        count = len(calls)
        if count == 0:
            title = "Tools need your approval"
        elif count == 1:
            title = f"{present_call(calls[0]).name} needs your approval"
        else:
            title = f"{count} tool calls need your approval"
        self.title_label.setText(title)

        self.tier_chip.setText(str(tier.get("label") or ""))
        self.tier_chip.setProperty("tone", str(tier.get("tone") or "unknown"))
        refresh_style(self.tier_chip)
        if run_id:
            self.run_label.setText(f"· run {run_id[-6:]}")
            self.run_label.show()
        else:
            self.run_label.clear()
            self.run_label.hide()

        if calls:
            for index, call in enumerate(calls):
                if index > 0:
                    self._add_host_item(self._divider_row(f"call {index + 1}/{count}"))
                name = str(call.get("name") or "").strip()
                risk = risks.get(name) if name else None
                card = ToolCallCard(
                    call=call,
                    index=index,
                    mode="approval",
                    risk=risk if isinstance(risk, dict) else None,
                    parent=self._host,
                )
                self._add_host_item(card)
                self.card_widgets.append(card)
        else:
            fallback = _mono_panel(
                tool_calls_text(batch.get("raw_tool_calls")),
                "toolApprovalRawPanel",
                min_h=132,
                max_h=260,
                parent=self._host,
            )
            fallback.show()
            self._add_host_item(fallback)

        # Remember: one box for a single-tool batch, per-card boxes otherwise.
        names = [card.presentation.name for card in self.card_widgets]
        unique = list(dict.fromkeys(names))
        self.remember_checkbox.setChecked(False)
        self._single_remember = False
        any_remember = False
        if len(unique) == 1 and self.card_widgets[0].remember_offerable:
            self._single_remember = True
            any_remember = True
            self.remember_checkbox.setText(f"Always allow {unique[0]} on this Mac")
            self.remember_checkbox.show()
            for card in self.card_widgets:
                if card.remember_checkbox is not None:
                    card.remember_checkbox.hide()
        else:
            self.remember_checkbox.hide()
            for card in self.card_widgets:
                box = card.remember_checkbox
                if box is None:
                    continue
                box.setChecked(False)
                if card.remember_offerable and len(unique) > 1:
                    box.show()
                    any_remember = True
                else:
                    box.hide()
        self.remember_help.setVisible(any_remember)

        self._configure_session_action(tier)
        self._refresh_queue_note()
        self.allowOnceButton.setFocus(Qt.OtherFocusReason)
        self._fit_height()

    def _configure_session_action(self, tier: Dict[str, Any]) -> None:
        """The blanket grant is always on offer for a batch of listed, enabled
        tools — but it states how far it reaches, and the grant it emits is
        capped at the tier the user is looking at."""
        reason = ""
        rank = int(tier.get("rank") or 0)
        if tier.get("unknown"):
            reason = "Not offered: this batch includes a tool the gateway does not list."
        elif any(not card.presentation.available for card in self.card_widgets):
            reason = "Not offered: a tool in this batch is disabled on the gateway."
        self.allow_session_action.setEnabled(not reason)
        self.allow_session_action.setText(
            SESSION_TRUST_LABELS.get(rank, "Allow all enabled tools in this chat")
        )
        if reason:
            self.allow_session_action.setToolTip(reason)
            self.allowMenuButton.setToolTip(reason)
            return
        scope = str(tier.get("label") or "").strip().lower()
        if rank > SESSION_TRUST_PLAIN_MAX_RANK and scope:
            tip = (
                f"Auto-approve every tool this Mac has not switched off — up to and including “{scope}” "
                "calls like the ones above — for the rest of this chat (⇧⏎)"
            )
        else:
            tip = (
                "Auto-approve every tool this Mac has not switched off, for the rest of this chat (⇧⏎). "
                "A later batch that reaches outside or destroys still asks."
            )
        self.allow_session_action.setToolTip(tip)
        self.allowMenuButton.setToolTip("More ways to allow (⇧⏎ allows all enabled tools in this chat)")

    def _fit_height(self) -> None:
        layout = self.layout()
        if layout is not None:
            layout.activate()
        content = self._host.sizeHint().height()
        chrome = self.sizeHint().height() - self._scroll.sizeHint().height()
        wanted = chrome + content + 8
        height = min(max(SHEET_MIN_HEIGHT, wanted), SHEET_MAX_HEIGHT)
        self.resize(SHEET_WIDTH, height)

    # -- decisions --------------------------------------------------------- #

    def _remembered_names(self) -> List[str]:
        names: List[str] = []
        if self._single_remember:
            if self.remember_checkbox.isChecked() and self.card_widgets:
                names.append(self.card_widgets[0].presentation.name)
            return names
        for card in self.card_widgets:
            if card.remember_checked and card.presentation.name not in names:
                names.append(card.presentation.name)
        return names

    def _decide(self, decision: str) -> None:
        if self._decided or not self.current_batch:
            return
        self._decided = True
        batch = self.current_batch
        if decision in ("once", "session"):
            self.approval_scope = decision
        remember = self._remembered_names() if decision in ("once", "session") else []
        info = {
            "run_id": str(batch.get("run_id") or ""),
            "wait_key": str(batch.get("wait_key") or ""),
            "remember": remember,
            "tool_calls": list(batch.get("tool_calls") or []),
            # How far a "session" grant may reach: the loudest tier shown here.
            "trust_rank": int((self.batch_risk or {}).get("rank") or 0),
        }
        self.decided.emit(decision, info)
        self._advance()

    def _advance(self) -> None:
        if self._queue:
            self._load_batch(self._queue.popleft())
            return
        self.current_batch = {}
        self._clear_host()
        self.hide()

    def _defer_all(self) -> None:
        """Esc / close: every batch on screen or queued keeps waiting."""
        pending: List[Dict[str, Any]] = []
        if self.current_batch and not self._decided:
            self._decided = True
            pending.append(self.current_batch)
        while self._queue:
            pending.append(self._queue.popleft())
        self.current_batch = {}
        self._clear_host()
        self._refresh_queue_note()
        for batch in pending:
            self.decided.emit(
                "defer",
                {
                    "run_id": str(batch.get("run_id") or ""),
                    "wait_key": str(batch.get("wait_key") or ""),
                    "remember": [],
                    "tool_calls": list(batch.get("tool_calls") or []),
                },
            )
        self.hide()

    def _allow_once(self) -> None:
        self._decide("once")

    def _allow_session(self) -> None:
        if not self.allow_session_action.isEnabled():
            return
        self._decide("session")

    def _deny(self) -> None:
        self._decide("deny")

    def toggle_full_calls(self) -> None:
        cards = list(self.card_widgets)
        if not cards:
            return
        show = not any(card.full_call_visible() for card in cards)
        for card in cards:
            card.set_full_call_visible(show)

    # -- Qt overrides ------------------------------------------------------ #

    def accept(self) -> None:  # noqa: D401 (Qt API)
        self._decide("once")

    def reject(self) -> None:
        self._defer_all()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self._defer_all()
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        key = event.key()
        if key == Qt.Key_Escape:
            self._defer_all()
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            focus = QApplication.focusWidget()
            decisions = tuple(
                b for b in (self.deferButton, self.denyButton, self.allowOnceButton, self.allowMenuButton) if b is not None
            )
            if focus in decisions and focus.isEnabled():
                # Return activates the decision button that HAS focus (Deny,
                # Decide later…), never the default Allow button behind it.
                # Elsewhere (an expander, a checkbox) it still means Allow once.
                focus.click()
                event.accept()
                return
        plain = not (event.modifiers() & ~Qt.KeypadModifier)
        if plain and not _is_text_control(QApplication.focusWidget()):
            if key == Qt.Key_F:
                self.toggle_full_calls()
                event.accept()
                return
            if key == Qt.Key_D:
                self._deny()
                event.accept()
                return
        super().keyPressEvent(event)


__all__ = ["ToolCallCard", "ToolApprovalCallCard", "ToolApprovalSheet", "APPROVAL_QSS"]
