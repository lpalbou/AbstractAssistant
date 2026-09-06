"""Building blocks shared by the Settings pages.

Every page is a titled, scrollable column of cards. Cards hold rows: a label
on the left, a control on the right, an optional help line underneath. The
controller is reached only through :func:`safe_call`, so a page never crashes
on a controller that lacks a method (older controllers, test stubs) — it shows
the honest "unavailable" text instead.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, List, Optional, Sequence

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..styles import refresh_style


_MISSING = object()

# The label column of every card row: wide enough for "Gateway user token",
# narrow enough that the control column keeps ≥ 360 px at the dialog minimum.
LABEL_COLUMN_MIN = 128
LABEL_COLUMN_MAX = 152


def _label_baseline_offset(control: Optional[QWidget]) -> int:
    """Top margin that puts a row label's text on the control's baseline."""
    if control is None:
        return 0
    from PyQt5.QtWidgets import QAbstractButton, QLabel as _QLabel

    if isinstance(control, (QAbstractButton, _QLabel)):
        # Checkboxes, radios and value labels are text-height already.
        return 1
    return 6


def _let_shrink(widget: QWidget) -> None:
    """Word-wrapped labels must not widen the page: a long unbreakable path
    or sentence otherwise sets the card's minimum width and the whole page
    grows past the viewport (clipping the right edge)."""
    if isinstance(widget, QLabel) and widget.wordWrap():
        policy = widget.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Ignored)
        widget.setSizePolicy(policy)
        widget.setMinimumWidth(40)


def safe_call(obj: Any, name: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    """Call ``obj.name(*args, **kwargs)`` if it exists; ``default`` otherwise."""
    fn = getattr(obj, name, None)
    if not callable(fn):
        return default
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        value = getattr(obj, name, _MISSING)
    except Exception:
        return default
    return default if value is _MISSING else value


class Chip(QLabel):
    """Small tone-colored pill (`QLabel#chip[tone]`)."""

    def __init__(self, text: str = "", tone: str = "neutral", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("chip")
        self.setAlignment(Qt.AlignCenter)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", str(tone or "neutral"))
        refresh_style(self)


class Note(QLabel):
    """Inline notice (`QLabel#statusNote[tone]`)."""

    def __init__(self, text: str = "", tone: str = "info", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("statusNote")
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.set_tone(tone)
        self.setVisible(bool(text))

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", str(tone or "info"))
        refresh_style(self)

    def show_text(self, text: str, tone: str = "info") -> None:
        self.setText(str(text or ""))
        self.set_tone(tone)
        self.setVisible(bool(str(text or "").strip()))


class Card(QFrame):
    """A titled card holding rows."""

    def __init__(self, title: str = "", help_text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsCard")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(8)
        self.title_label: Optional[QLabel] = None
        self.help_label: Optional[QLabel] = None
        if title:
            head = QHBoxLayout()
            head.setSpacing(8)
            self.title_label = QLabel(title)
            self.title_label.setObjectName("cardTitle")
            head.addWidget(self.title_label)
            head.addStretch(1)
            self._head = head
            self._layout.addLayout(head)
        if help_text:
            self.help_label = QLabel(help_text)
            self.help_label.setObjectName("cardHelp")
            self.help_label.setWordWrap(True)
            _let_shrink(self.help_label)
            self._layout.addWidget(self.help_label)
        self._rows = 0

    def add_header_widget(self, widget: QWidget) -> None:
        head = getattr(self, "_head", None)
        if head is not None:
            head.addWidget(widget, 0, Qt.AlignVCenter)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        _let_shrink(widget)
        self._layout.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def add_row(
        self,
        label: str,
        control: Optional[QWidget] = None,
        *,
        help_text: str = "",
        stretch_control: bool = True,
        trailing: Sequence[QWidget] = (),
    ) -> QFrame:
        """A label / control row with an optional help line under the control."""
        row = QFrame(self)
        row.setObjectName("cardRow")
        row.setProperty("first", "true" if self._rows == 0 else "false")
        grid = QGridLayout(row)
        grid.setContentsMargins(0, 10 if self._rows else 2, 0, 4)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        # An unlabeled row (a checkbox, a compound widget) spans the full
        # width instead of wasting the label column.
        labeled = bool(str(label or "").strip())
        column = 1 if labeled else 0
        span = 1 if labeled else 2
        grid.setColumnStretch(1, 1)
        if labeled:
            name = QLabel(label)
            name.setObjectName("rowLabel")
            name.setMinimumWidth(LABEL_COLUMN_MIN)
            name.setMaximumWidth(LABEL_COLUMN_MAX)
            name.setWordWrap(True)
            name.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            # Top-aligned so a multi-line help text never pushes it down, but
            # nudged so its baseline sits on the control's text baseline
            # (a 28 px control centres 12 px text ~6 px below its top edge).
            name.setContentsMargins(0, _label_baseline_offset(control), 0, 0)
            grid.addWidget(name, 0, 0)
            row.label_widget = name  # type: ignore[attr-defined]
        if control is not None:
            _let_shrink(control)
            if trailing or not stretch_control:
                # A compact control (spin box, combo) sits at the left of its
                # column with the slack after it — never centered by the grid.
                box = QHBoxLayout()
                box.setSpacing(6)
                box.addWidget(control, 1 if stretch_control else 0)
                for extra in trailing:
                    box.addWidget(extra, 0)
                if not stretch_control:
                    box.addStretch(1)
                grid.addLayout(box, 0, column, 1, span)
            else:
                grid.addWidget(control, 0, column, 1, span)
        if help_text:
            help_label = QLabel(help_text)
            help_label.setObjectName("rowHelp")
            help_label.setWordWrap(True)
            _let_shrink(help_label)
            grid.addWidget(help_label, 1, column, 1, span)
            row.help_label = help_label  # type: ignore[attr-defined]
        self._layout.addWidget(row)
        self._rows += 1
        return row


class SegmentedControl(QFrame):
    """A row of mutually exclusive checkable buttons (`QFrame#segmented`)."""

    changed = pyqtSignal(str)

    def __init__(self, options: Iterable[tuple[str, str]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("segmented")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: List[QPushButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.set_options(options)
        self._group.buttonClicked.connect(self._on_clicked)

    def set_options(self, options: Iterable[tuple[str, str]]) -> None:
        layout = self.layout()
        for button in self._buttons:
            self._group.removeButton(button)
        # Empty the layout completely (buttons AND the trailing stretch), and
        # detach old buttons now: deleteLater alone leaves them painted under
        # the new ones until the event loop runs.
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._buttons = []
        items = list(options)
        for index, (value, label) in enumerate(items):
            button = QPushButton(label)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setFocusPolicy(Qt.NoFocus)
            button.setProperty("value", value)
            position = "only" if len(items) == 1 else ("first" if index == 0 else ("last" if index == len(items) - 1 else "mid"))
            button.setProperty("segment", position)
            layout.addWidget(button)
            self._group.addButton(button)
            self._buttons.append(button)
        layout.addStretch(1)

    def values(self) -> List[str]:
        return [str(b.property("value")) for b in self._buttons]

    def value(self) -> str:
        checked = self._group.checkedButton()
        return str(checked.property("value")) if checked is not None else ""

    def set_value(self, value: str) -> None:
        target = str(value or "")
        for button in self._buttons:
            button.setChecked(str(button.property("value")) == target)

    def set_tooltips(self, tips: dict) -> None:
        for button in self._buttons:
            tip = tips.get(str(button.property("value")))
            if tip:
                button.setToolTip(str(tip))

    def set_option_enabled(self, value: str, enabled: bool, tooltip: str = "") -> None:
        """Grey out one segment (e.g. a reasoning level the model lacks)."""
        target = str(value or "")
        for button in self._buttons:
            if str(button.property("value")) == target:
                button.setEnabled(bool(enabled))
                if tooltip:
                    button.setToolTip(str(tooltip))

    def option_enabled(self, value: str) -> bool:
        target = str(value or "")
        for button in self._buttons:
            if str(button.property("value")) == target:
                return bool(button.isEnabled())
        return False

    def _on_clicked(self, button) -> None:
        self.changed.emit(str(button.property("value")))


class SettingsPage(QWidget):
    """Base page: title, subtitle, scrollable column of cards."""

    title = "Page"
    nav_title = ""  # short sidebar label; defaults to `title`
    subtitle = ""
    icon = "gear"
    changed = pyqtSignal()

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QVBoxLayout()
        header.setContentsMargins(20, 16, 20, 8)
        header.setSpacing(3)
        self.title_label = QLabel(self.title, self)
        self.title_label.setObjectName("sectionTitle")
        header.addWidget(self.title_label)
        # Parented before `setVisible`: showing a parentless widget opens a real
        # top-level window (~8 ms and two activation flips per page).
        self.subtitle_label = QLabel(self.subtitle, self)
        self.subtitle_label.setObjectName("sectionHelp")
        self.subtitle_label.setWordWrap(True)
        _let_shrink(self.subtitle_label)
        self.subtitle_label.setVisible(bool(self.subtitle))
        header.addWidget(self.subtitle_label)
        outer.addLayout(header)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("settingsPageHost")
        self.body = QVBoxLayout(host)
        self.body.setContentsMargins(20, 4, 20, 16)
        self.body.setSpacing(12)
        self.body.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(host)
        outer.addWidget(self.scroll, 1)

        # Footer: feedback on the left, the page's persistent actions on the
        # right. It sits outside the scroll area so Save is always reachable
        # and the confirmation lands next to the button that produced it.
        self.footer_frame = QFrame(self)
        self.footer_frame.setObjectName("pageFooter")
        self.footer = QHBoxLayout(self.footer_frame)
        self.footer.setContentsMargins(20, 8, 20, 12)
        self.footer.setSpacing(8)
        # The feedback label always occupies the footer's slack (even when
        # empty) so the action buttons keep their natural width on the right.
        self.feedback = QLabel("")
        self.feedback.setObjectName("feedbackNote")
        self.feedback.setWordWrap(True)
        _let_shrink(self.feedback)
        self.footer.addWidget(self.feedback, 1, Qt.AlignVCenter)
        self._action_widgets: List[QWidget] = []
        self.footer_frame.hide()
        outer.addWidget(self.footer_frame)

    def add_card(self, card: Card, stretch: int = 0) -> Card:
        self.body.addWidget(card, stretch)
        return card

    def add_actions(self, *widgets: QWidget) -> None:
        """Place buttons in the page footer (right-aligned, in order)."""
        for widget in widgets:
            policy = widget.sizePolicy()
            policy.setHorizontalPolicy(QSizePolicy.Fixed)
            widget.setSizePolicy(policy)
            self.footer.addWidget(widget, 0, Qt.AlignVCenter)
            self._action_widgets.append(widget)
        self.footer_frame.setVisible(bool(self._action_widgets) or bool(self.feedback.text().strip()))

    def actions(self) -> List[QWidget]:
        return list(self._action_widgets)

    def say(self, text: str, tone: str = "ok") -> None:
        self.feedback.setText(str(text or ""))
        self.feedback.setProperty("tone", tone)
        refresh_style(self.feedback)
        self.footer_frame.setVisible(bool(self._action_widgets) or bool(str(text or "").strip()))

    def refresh(self) -> None:  # pragma: no cover - overridden
        return None


def button(text: str, kind: str = "secondary", *, tooltip: str = "", on_click: Optional[Callable[[], None]] = None) -> QPushButton:
    widget = QPushButton(text)
    widget.setObjectName(f"{kind}Button")
    widget.setAutoDefault(False)
    if tooltip:
        widget.setToolTip(tooltip)
    if on_click is not None:
        widget.clicked.connect(lambda _checked=False: on_click())
    return widget


__all__ = [
    "Card",
    "Chip",
    "Note",
    "SegmentedControl",
    "SettingsPage",
    "button",
    "safe_attr",
    "safe_call",
]
