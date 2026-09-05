"""Small secondary dialogs that share the application stylesheet.

Kept out of ``app.py`` (which imports this module) so they stay importable
and testable on their own. Nothing here talks to the gateway: the palette
feeds the dialog its data and reads the decision back.
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .styles import dialog_stylesheet


class _PromptBrowser(QTextBrowser):
    """Read-only rich-text view that sizes itself to its document."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("askPrompt")
        self.setOpenExternalLinks(True)
        self.setFrameShape(QTextBrowser.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Styled by the shared builder (`QTextBrowser#askPrompt`).
        self.document().setDocumentMargin(0)

    def refresh_height(self, *, max_height: int = 260) -> None:
        self.document().setTextWidth(max(120, self.viewport().width() or self.width() or 480))
        height = int(self.document().size().height()) + 6
        self.setFixedHeight(max(24, min(max_height, height)))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.refresh_height()


class AskUserDialog(QDialog):
    """The run asked the user a question (an ``abstract.ask`` / user wait).

    Replaces the single-line ``QInputDialog``: the question renders as
    markdown, the answer is multi-line (Enter sends, Shift+Enter breaks a
    line), and the three outcomes are explicit:

    - ``send``  — ``answer`` is the reply text;
    - ``empty`` — the user chose to continue the run with no answer;
    - ``defer`` — keep the run waiting (the palette re-asks when shown again).
    """

    def __init__(
        self,
        *,
        prompt: str,
        render_html: Optional[Callable[[str], str]] = None,
        title: str = "The assistant has a question",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.decision = "defer"
        self.answer = ""
        self._prompt_text = str(prompt or "").strip() or "Input required"
        self.setWindowTitle("Question")
        # Modeless, like the approval sheet: the palette stays usable (stop,
        # steer, read) while the question is open. A tool window that stays on
        # top is still found when the palette is re-focused.
        self.setModal(False)
        self.setWindowFlags(
            Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.CustomizeWindowHint
            | Qt.WindowTitleHint
            | Qt.WindowCloseButtonHint
        )
        self.setMinimumSize(460, 280)
        self.resize(560, 340)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        heading = QLabel(title)
        heading.setObjectName("dialogTitle")
        root.addWidget(heading)

        hint = QLabel("The run is paused until you answer. Return sends; Shift+Return adds a line.")
        hint.setObjectName("dialogSubtitle")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addSpacing(4)

        self.prompt_view = _PromptBrowser(self)
        if callable(render_html):
            try:
                self.prompt_view.setHtml(render_html(self._prompt_text))
            except Exception:
                self.prompt_view.setPlainText(self._prompt_text)
        else:
            self.prompt_view.setPlainText(self._prompt_text)
        root.addWidget(self.prompt_view)

        self.answer_edit = QPlainTextEdit(self)
        self.answer_edit.setObjectName("askAnswer")
        self.answer_edit.setPlaceholderText("Type your answer…")
        self.answer_edit.setMinimumHeight(88)
        self.answer_edit.installEventFilter(self)
        root.addWidget(self.answer_edit, 1)
        root.addSpacing(4)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.defer_button = QPushButton("Keep waiting")
        self.defer_button.setObjectName("ghostButton")
        self.defer_button.setToolTip("Close this window; the run stays paused and asks again when you reopen the assistant (Esc).")
        self.defer_button.clicked.connect(self._defer)
        buttons.addWidget(self.defer_button)
        buttons.addStretch(1)
        self.empty_button = QPushButton("Continue without answering")
        self.empty_button.setObjectName("secondaryButton")
        self.empty_button.setToolTip("Resume the run with an empty reply.")
        self.empty_button.clicked.connect(self._send_empty)
        buttons.addWidget(self.empty_button)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("primaryButton")
        self.send_button.setDefault(True)
        self.send_button.clicked.connect(self._send)
        buttons.addWidget(self.send_button)
        root.addLayout(buttons)

        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Return), self, activated=self._send)
        QShortcut(QKeySequence(Qt.META | Qt.Key_Return), self, activated=self._send)

        self.setStyleSheet(dialog_stylesheet())
        self.prompt_view.refresh_height()
        self.answer_edit.setFocus()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(560, 340)

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.answer_edit and event is not None and event.type() == event.KeyPress:
            key = int(event.key())
            modifiers = int(event.modifiers())
            if key in {Qt.Key_Return, Qt.Key_Enter} and not (modifiers & int(Qt.ShiftModifier)):
                self._send()
                return True
        return super().eventFilter(obj, event)

    def _send(self) -> None:
        text = self.answer_edit.toPlainText().strip()
        if not text:
            # An empty Send is ambiguous; make the user pick the explicit path.
            self.answer_edit.setProperty("invalid", True)
            self.answer_edit.style().unpolish(self.answer_edit)
            self.answer_edit.style().polish(self.answer_edit)
            self.answer_edit.setPlaceholderText("Type an answer, or choose “Continue without answering”.")
            return
        self.answer = text
        self.decision = "send"
        self.accept()

    def _send_empty(self) -> None:
        self.answer = ""
        self.decision = "empty"
        self.accept()

    def _defer(self) -> None:
        self.answer = ""
        self.decision = "defer"
        self.reject()

    def reject(self) -> None:  # noqa: D401 - Esc / close = keep waiting
        if self.decision == "send":
            self.decision = "defer"
        super().reject()


__all__ = ["AskUserDialog"]
