"""AskUserDialog: multi-line answers, markdown prompts, three explicit outcomes."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from abstractassistant.ui.dialogs import AskUserDialog
from abstractassistant.ui.styles import dialog_stylesheet


_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


@pytest.mark.basic
def test_dialog_stylesheet_builds_from_tokens_and_applies() -> None:
    _app()
    sheet = dialog_stylesheet()
    assert "QDialog" in sheet and "primaryButton" in sheet and 'tone="destroy"' in sheet
    dialog = AskUserDialog(prompt="Which folder?")
    assert dialog.styleSheet().strip()  # applied without Qt rejecting it


@pytest.mark.basic
def test_send_returns_the_typed_answer() -> None:
    _app()
    dialog = AskUserDialog(prompt="Which folder should I use?")
    dialog.answer_edit.setPlainText("  ~/projects/site \n")
    dialog._send()
    assert dialog.decision == "send"
    assert dialog.answer == "~/projects/site"


@pytest.mark.basic
def test_empty_send_is_refused_until_an_explicit_choice() -> None:
    _app()
    dialog = AskUserDialog(prompt="Anything else?")
    dialog._send()
    assert dialog.decision == "defer"  # nothing happened yet
    assert dialog.answer_edit.property("invalid") is True

    dialog._send_empty()
    assert dialog.decision == "empty"
    assert dialog.answer == ""


@pytest.mark.basic
def test_escape_and_keep_waiting_defer_the_question() -> None:
    _app()
    dialog = AskUserDialog(prompt="Confirm?")
    dialog.answer_edit.setPlainText("half typed")
    dialog._defer()
    assert dialog.decision == "defer"
    assert dialog.answer == ""

    dialog = AskUserDialog(prompt="Confirm?")
    dialog.reject()  # Esc / window close
    assert dialog.decision == "defer"


@pytest.mark.basic
def test_prompt_renders_through_the_supplied_markdown_renderer() -> None:
    _app()
    seen: list[str] = []

    def _render(text: str) -> str:
        seen.append(text)
        return f"<p><b>{text}</b></p>"

    dialog = AskUserDialog(prompt="**Pick one**", render_html=_render)
    assert seen == ["**Pick one**"]
    assert "Pick one" in dialog.prompt_view.toPlainText()
