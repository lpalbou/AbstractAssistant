"""ui.approval: the modeless approval sheet and the shared tool-call card."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QCheckBox, QFrame, QLabel, QPlainTextEdit, QPushButton

import abstractassistant.ui.approval as approval_module
from abstractassistant.ui.approval import (
    APPROVAL_QSS,
    ToolApprovalCallCard,
    ToolApprovalSheet,
    ToolCallCard,
)


_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


EXECUTE = {"name": "execute_command", "toolset": "system", "available": True, "approval_default": "ask", "risk_tier": "destroy", "risk_rank": 4, "mutating": True, "destructive_capable": True}
READ_FILE = {"name": "read_file", "toolset": "files", "available": True, "approval_default": "auto", "risk_tier": "observe", "risk_rank": 1}
WRITE_FILE = {"name": "write_file", "toolset": "files", "available": True, "approval_default": "ask", "risk_tier": "act", "risk_rank": 2, "mutating": True}
SEND_EMAIL = {"name": "send_email", "toolset": "comms.email", "available": False, "approval_default": "ask", "risk_tier": "outreach", "risk_rank": 3, "comms_send": True}
RISKS = {"execute_command": EXECUTE, "read_file": READ_FILE, "write_file": WRITE_FILE, "send_email": SEND_EMAIL}

CMD_CALL = {"name": "execute_command", "arguments": {"command": "rm -rf build", "timeout": 300}}
READ_CALL = {"name": "read_file", "arguments": {"file_path": "/tmp/a.py"}}
WRITE_CALL = {"name": "write_file", "arguments": {"file_path": "/tmp/b.py", "content": "print(1)\n"}}


def _sheet(tool_calls, *, risks=RISKS, run_id="run-a3f9c1", wait_key="wait-1", show=True):
    app = _app()
    sheet = ToolApprovalSheet(tool_calls=tool_calls, risks=risks, run_id=run_id, wait_key=wait_key)
    decisions: list = []
    sheet.decided.connect(lambda decision, info: decisions.append((decision, info)))
    if show:
        sheet.show()
        app.processEvents()
    return sheet, decisions


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_sheet_is_modeless_and_a_tool_window() -> None:
    sheet, _ = _sheet([CMD_CALL])
    assert sheet.isModal() is False
    assert bool(sheet.windowFlags() & Qt.Tool)
    assert bool(sheet.windowFlags() & Qt.WindowStaysOnTopHint)
    assert sheet.width() == 560
    assert 320 <= sheet.height() <= 640
    assert sheet.title_label.text() == "execute_command needs your approval"
    assert sheet.tier_chip.text() == "Destructive"
    assert sheet.tier_chip.property("tone") == "destroy"
    assert sheet.run_label.text() == "· run a3f9c1"


@pytest.mark.basic
def test_allow_once_emits_once_with_batch_identity() -> None:
    sheet, decisions = _sheet([CMD_CALL])
    sheet.allowOnceButton.click()
    assert decisions == [
        (
            "once",
            {
                "run_id": "run-a3f9c1",
                "wait_key": "wait-1",
                "remember": [],
                "tool_calls": [CMD_CALL],
                # The tier the user saw: it caps a "session" grant made here.
                "trust_rank": 4,
            },
        )
    ]
    assert sheet.approval_scope == "once"
    assert sheet.current_batch == {}
    assert sheet.isVisible() is False
    # A second click after the decision emits nothing.
    sheet.allowOnceButton.click()
    assert len(decisions) == 1


@pytest.mark.basic
def test_session_action_emits_session_for_a_trustable_batch() -> None:
    sheet, decisions = _sheet([READ_CALL, WRITE_CALL])
    assert sheet.title_label.text() == "2 tool calls need your approval"
    assert sheet.allow_session_action.isEnabled() is True
    sheet.allow_session_action.trigger()
    assert [d for d, _ in decisions] == ["session"]
    assert sheet.approval_scope == "session"


@pytest.mark.basic
def test_deny_and_defer_buttons_emit_their_decisions() -> None:
    sheet, decisions = _sheet([CMD_CALL])
    sheet.denyButton.click()
    assert [d for d, _ in decisions] == ["deny"]
    assert decisions[0][1]["remember"] == []

    sheet, decisions = _sheet([CMD_CALL])
    sheet.deferButton.click()
    assert [d for d, _ in decisions] == ["defer"]
    assert sheet.isVisible() is False


@pytest.mark.basic
def test_escape_reject_and_close_defer_exactly_once() -> None:
    sheet, decisions = _sheet([CMD_CALL])
    QTest.keyClick(sheet, Qt.Key_Escape)
    assert [d for d, _ in decisions] == ["defer"]
    assert sheet.isVisible() is False
    sheet.reject()
    QTest.keyClick(sheet, Qt.Key_Escape)
    assert len(decisions) == 1

    sheet, decisions = _sheet([CMD_CALL])
    sheet.reject()
    assert [d for d, _ in decisions] == ["defer"]

    sheet, decisions = _sheet([CMD_CALL])
    sheet.close()
    assert [d for d, _ in decisions] == ["defer"]
    assert decisions[0][1]["wait_key"] == "wait-1"


@pytest.mark.basic
def test_return_allows_once_even_with_focus_on_an_expander(monkeypatch: pytest.MonkeyPatch) -> None:
    sheet, decisions = _sheet([CMD_CALL])
    card = sheet.card_widgets[0]
    card.raw_toggle.setFocus()
    _app().processEvents()
    QTest.keyClick(card.raw_toggle, Qt.Key_Return)
    assert card.raw_panel.isHidden() is True  # Return never toggles the expander
    assert [d for d, _ in decisions] == ["once"]

    sheet, decisions = _sheet([CMD_CALL])
    QTest.keyClick(sheet, Qt.Key_Return, Qt.ControlModifier)
    assert [d for d, _ in decisions] == ["once"]

    sheet, decisions = _sheet([CMD_CALL])
    QTest.keyClick(sheet, Qt.Key_D, Qt.ControlModifier)
    assert [d for d, _ in decisions] == ["deny"]


@pytest.mark.basic
def test_shift_return_is_a_no_op_when_blanket_trust_is_refused() -> None:
    # Refused only when a tool is unlisted or switched off on the gateway.
    sheet, decisions = _sheet([READ_CALL, {"name": "mystery_tool", "arguments": {}}])
    assert sheet.allow_session_action.isEnabled() is False
    QTest.keyClick(sheet, Qt.Key_Return, Qt.ShiftModifier)
    assert decisions == []
    sheet, decisions = _sheet([READ_CALL])
    QTest.keyClick(sheet, Qt.Key_Return, Qt.ShiftModifier)
    assert [d for d, _ in decisions] == ["session"]
    assert decisions[0][1]["trust_rank"] == 1


@pytest.mark.basic
def test_return_inside_a_raw_panel_does_not_approve() -> None:
    sheet, decisions = _sheet([CMD_CALL])
    card = sheet.card_widgets[0]
    card.set_full_call_visible(True)
    _app().processEvents()
    card.raw_panel.setFocus()
    QTest.keyClick(card.raw_panel, Qt.Key_Return)
    assert decisions == []
    QTest.keyClick(card.raw_panel, Qt.Key_Return, Qt.ControlModifier)
    assert [d for d, _ in decisions] == ["once"]


@pytest.mark.basic
def test_f_toggles_full_call_on_every_card() -> None:
    sheet, _ = _sheet([READ_CALL, WRITE_CALL])
    assert all(card.raw_panel.isHidden() for card in sheet.card_widgets)
    QTest.keyClick(sheet, Qt.Key_F)
    assert all(card.full_call_visible() for card in sheet.card_widgets)
    QTest.keyClick(sheet, Qt.Key_F)
    assert not any(card.full_call_visible() for card in sheet.card_widgets)


# --------------------------------------------------------------------------- #
# Queue
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_enqueue_repopulates_and_answers_each_batch_by_identity() -> None:
    sheet, decisions = _sheet([CMD_CALL])
    sheet.enqueue([READ_CALL], run_id="run-2", wait_key="wait-2", risks=RISKS)
    assert sheet.pending_count == 1
    assert sheet.queue_note.text() == "1 more batch waiting"
    assert sheet.current_batch["wait_key"] == "wait-1"

    sheet.denyButton.click()
    assert [d for d, _ in decisions] == ["deny"]
    assert decisions[0][1]["wait_key"] == "wait-1"
    assert sheet.isVisible() is True
    assert sheet.pending_count == 0
    assert sheet.queue_note.isHidden() is True
    assert sheet.current_batch["wait_key"] == "wait-2"
    assert sheet.title_label.text() == "read_file needs your approval"
    assert sheet.tier_chip.text() == "Reads only"
    assert [card.presentation.name for card in sheet.card_widgets] == ["read_file"]

    sheet.allowOnceButton.click()
    assert [d for d, _ in decisions] == ["deny", "once"]
    assert decisions[1][1] == {
        "run_id": "run-2",
        "wait_key": "wait-2",
        "remember": [],
        "tool_calls": [READ_CALL],
        "trust_rank": 1,
    }
    assert sheet.isVisible() is False

    # A later batch on an idle sheet loads immediately and re-shows it.
    sheet.enqueue([WRITE_CALL], run_id="run-3", wait_key="wait-3", risks=RISKS)
    assert sheet.isVisible() is True
    assert sheet.current_batch["wait_key"] == "wait-3"


@pytest.mark.basic
def test_escape_defers_the_current_and_every_queued_batch() -> None:
    sheet, decisions = _sheet([CMD_CALL])
    sheet.enqueue([READ_CALL], run_id="run-2", wait_key="wait-2")
    sheet.enqueue([WRITE_CALL], run_id="run-3", wait_key="wait-3")
    assert sheet.queue_note.text() == "2 more batches waiting"
    QTest.keyClick(sheet, Qt.Key_Escape)
    assert [(d, info["wait_key"]) for d, info in decisions] == [("defer", "wait-1"), ("defer", "wait-2"), ("defer", "wait-3")]
    assert sheet.pending_count == 0 and sheet.isVisible() is False


# --------------------------------------------------------------------------- #
# Remember
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_single_tool_batch_uses_the_sheet_checkbox() -> None:
    sheet, decisions = _sheet([WRITE_CALL, {"name": "write_file", "arguments": {"file_path": "/tmp/c.py", "content": "x"}}])
    assert sheet.remember_checkbox.isHidden() is False
    assert sheet.remember_checkbox.text() == "Always allow write_file on this Mac"
    assert sheet.remember_help.isHidden() is False
    assert all(card.remember_checkbox.isHidden() for card in sheet.card_widgets)
    labels = [w.text() for w in sheet.findChildren(QLabel, "toolApprovalDividerLabel")]
    assert labels == ["call 2/2"]

    sheet.remember_checkbox.setChecked(True)
    sheet.allowOnceButton.click()
    assert decisions[0][1]["remember"] == ["write_file"]


@pytest.mark.basic
def test_blanket_trust_is_never_offered_for_destroy_or_outreach_tiers() -> None:
    # execute_command is classified `destroy` (rank 4): approve it one call at
    # a time, never "always allow on this Mac".
    sheet, _ = _sheet([CMD_CALL, {"name": "execute_command", "arguments": {"command": "ls"}}])
    assert sheet.remember_checkbox.isHidden() is True
    assert all(card.remember_offerable is False for card in sheet.card_widgets)


@pytest.mark.basic
def test_return_on_a_focused_deny_or_defer_button_never_approves() -> None:
    sheet, decisions = _sheet([CMD_CALL])
    sheet.denyButton.setFocus()
    _app().processEvents()
    QTest.keyClick(sheet.denyButton, Qt.Key_Return)
    assert [d for d, _ in decisions] == ["deny"]

    sheet, decisions = _sheet([CMD_CALL])
    sheet.deferButton.setFocus()
    _app().processEvents()
    QTest.keyClick(sheet.deferButton, Qt.Key_Return)
    assert [d for d, _ in decisions] == ["defer"]


@pytest.mark.basic
def test_enqueue_ignores_the_same_undecided_wait_raised_twice() -> None:
    sheet, _ = _sheet([CMD_CALL], run_id="run-1", wait_key="wait-1")
    sheet.enqueue([CMD_CALL], run_id="run-1", wait_key="wait-1")
    assert sheet.pending_count == 0
    sheet.enqueue([READ_CALL], run_id="run-1", wait_key="wait-2")
    sheet.enqueue([READ_CALL], run_id="run-1", wait_key="wait-2")
    assert sheet.pending_count == 1


@pytest.mark.basic
def test_mixed_batch_uses_per_card_checkboxes_and_skips_unofferable_tools() -> None:
    email = {"name": "send_email", "arguments": {"to": "a@b", "subject": "hi"}}
    mystery = {"name": "mystery_tool", "arguments": {"x": 1}}
    sheet, decisions = _sheet([READ_CALL, WRITE_CALL, email, mystery])
    assert sheet.remember_checkbox.isHidden() is True
    by_name = {card.presentation.name: card for card in sheet.card_widgets}
    assert by_name["read_file"].remember_checkbox.isHidden() is False
    assert by_name["write_file"].remember_checkbox.isHidden() is False
    assert by_name["send_email"].remember_checkbox.isHidden() is True  # disabled on gateway
    assert by_name["mystery_tool"].remember_checkbox.isHidden() is True  # not in inventory
    # An unlisted tool outranks every known tier but destroy for the label.
    assert sheet.tier_chip.text() == "Unknown risk"
    assert sheet.tier_chip.property("tone") == "unknown"
    assert sheet.batch_risk["unknown"] is True

    by_name["write_file"].remember_checkbox.setChecked(True)
    by_name["read_file"].remember_checkbox.setChecked(False)
    sheet.allowOnceButton.click()
    assert decisions[0][1]["remember"] == ["write_file"]


@pytest.mark.basic
def test_remember_is_not_offered_for_a_lone_unavailable_or_unknown_tool() -> None:
    sheet, _ = _sheet([{"name": "send_email", "arguments": {"to": "a@b"}}])
    assert sheet.remember_checkbox.isHidden() is True
    assert sheet.remember_help.isHidden() is True
    sheet, _ = _sheet([{"name": "mystery_tool", "arguments": {}}])
    assert sheet.remember_checkbox.isHidden() is True
    assert sheet.tier_chip.text() == "Unknown risk"


# --------------------------------------------------------------------------- #
# Blanket trust gating + button discipline
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_session_action_states_how_far_the_grant_reaches() -> None:
    # A destructive batch may still be trusted for the chat — the item says so
    # and the grant it emits is capped at that tier.
    sheet, decisions = _sheet([CMD_CALL])
    assert sheet.allow_session_action.isEnabled() is True
    assert sheet.allow_session_action.text() == "Allow all enabled tools in this chat, including destructive ones"
    assert "destructive" in sheet.allow_session_action.toolTip()
    sheet.allow_session_action.trigger()
    assert decisions[0][0] == "session" and decisions[0][1]["trust_rank"] == 4

    sheet, _ = _sheet([READ_CALL])
    assert sheet.allow_session_action.text() == "Allow all enabled tools in this chat"
    assert "still asks" in sheet.allow_session_action.toolTip()

    sheet, _ = _sheet([READ_CALL, {"name": "mystery_tool", "arguments": {}}])
    assert sheet.allow_session_action.isEnabled() is False
    assert "does not list" in sheet.allow_session_action.toolTip()

    sheet, _ = _sheet([READ_CALL, {"name": "send_email", "arguments": {}}])
    assert sheet.allow_session_action.isEnabled() is False

    sheet, _ = _sheet([{"name": "list_files", "arguments": {"directory_path": "."}}, READ_CALL], risks={**RISKS, "list_files": {**READ_FILE, "name": "list_files"}})
    assert sheet.allow_session_action.isEnabled() is True
    assert sheet.batch_risk == {"label": "Reads only", "tone": "observe", "rank": 1, "unknown": False}


@pytest.mark.basic
def test_only_allow_once_is_a_default_button() -> None:
    sheet, _ = _sheet([CMD_CALL, WRITE_CALL])
    buttons = sheet.findChildren(QPushButton)
    assert sheet.allowOnceButton in buttons
    for button in buttons:
        if button is sheet.allowOnceButton:
            assert button.autoDefault() is True and button.isDefault() is True
        else:
            assert button.autoDefault() is False, button.text()
            assert button.isDefault() is False, button.text()
    assert sheet.deferButton.objectName() == "ghostButton"
    assert sheet.denyButton.objectName() == "secondaryButton"
    assert sheet.allowOnceButton.objectName() == "primaryButton"
    assert sheet.allowMenuButton.menu() is sheet.allow_menu
    assert sheet.allow_session_action in sheet.allow_menu.actions()


@pytest.mark.basic
def test_empty_batch_falls_back_to_raw_text_and_stays_fail_closed() -> None:
    sheet, decisions = _sheet([], risks={})
    assert sheet.title_label.text() == "Tools need your approval"
    assert sheet.tier_chip.text() == "Unknown risk"
    assert sheet.allow_session_action.isEnabled() is False
    panels = sheet.findChildren(QPlainTextEdit, "toolApprovalRawPanel")
    assert len(panels) == 1 and "No tool details" in panels[0].toPlainText()
    sheet.denyButton.click()
    assert [d for d, _ in decisions] == ["deny"]


# --------------------------------------------------------------------------- #
# Card
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_result_mode_card_shows_status_chip_and_error() -> None:
    app = _app()
    card = ToolApprovalCallCard(
        call={"name": "edit_file", "arguments": {"file_path": "broken.py", "pattern": "x"}, "success": False, "error": "pattern not found"},
        index=0,
    )
    card.show()
    app.processEvents()
    assert isinstance(card, ToolCallCard)
    assert card.objectName() == "toolApprovalCallCard"
    chips = [str(chip.text()).strip().upper() for chip in card.findChildren(QLabel, "usageStatusChip")]
    assert chips == ["FAILED"]
    errors = card.findChildren(QLabel, "usageCardError")
    assert len(errors) == 1 and "pattern not found" in errors[0].text()
    assert card.remember_checkbox is None
    # Without a risk lookup a post-hoc card shows no tier chip (not looked up ≠ unknown).
    assert card.findChildren(QLabel, "chip") == []

    done = ToolCallCard(call={"name": "read_file", "arguments": {"file_path": "a"}, "output": "hello"}, index=1, mode="result")
    assert [c.text() for c in done.findChildren(QLabel, "usageStatusChip")] == ["DONE"]
    assert done.output_panel is not None and done.output_panel.toPlainText() == "hello"
    ok = ToolApprovalCallCard(call={"name": "read_file", "arguments": {}, "success": True}, index=2)
    assert [c.text() for c in ok.findChildren(QLabel, "usageStatusChip")] == ["COMPLETED"]
    assert ok.findChildren(QLabel, "usageCardError") == []


@pytest.mark.basic
def test_approval_mode_card_has_risk_chips_headline_and_no_status_chip() -> None:
    app = _app()
    card = ToolCallCard(call={"name": "execute_command", "arguments": {"command": "rm -rf build", "timeout": 300, "api_key": "k"}}, index=0, risk=EXECUTE)
    card.show()
    app.processEvents()
    assert card.findChildren(QLabel, "usageStatusChip") == []
    assert card.findChildren(QLabel, "usageCardError") == []
    chips = [(c.text(), c.property("tone")) for c in card.findChildren(QLabel, "chip")]
    assert chips[0] == ("Destructive", "destroy")
    assert ("can delete", "destroy") in chips
    assert card.headline_label is not None and card.headline_label.text() == "$ rm -rf build"
    keys = [label.text() for label in card.findChildren(QLabel, "toolApprovalParamKey")]
    assert "timeout" in keys and "api_key" in keys
    values = [label.text() for label in card.findChildren(QLabel, "toolApprovalParamValue")]
    assert "300" in values and "••••••" in values and "k" not in values
    assert "k" not in card.raw_panel.toPlainText().replace('"name": "execute_command"', "").replace("api_key", "")
    assert any(label.text() == "Secrets masked" for label in card.findChildren(QLabel, "cardHelp"))
    assert card.raw_toggle.objectName() == "linkButton" and card.raw_toggle.autoDefault() is False
    assert card.raw_panel.objectName() == "toolApprovalRawPanel" and card.raw_panel.isHidden()
    card.raw_toggle.click()
    assert card.raw_panel.isHidden() is False and card.raw_toggle.text().startswith("▾")
    assert isinstance(card.remember_checkbox, QCheckBox)
    assert card.remember_checkbox.objectName() == "rememberTool"
    assert card.remember_checkbox.isHidden() is True
    assert card.remember_checkbox.text() == "Always allow execute_command on this Mac"


@pytest.mark.basic
def test_card_marks_disabled_and_unknown_tools_honestly() -> None:
    disabled = ToolCallCard(call={"name": "send_email", "arguments": {"to": "a@b"}}, index=0, risk=SEND_EMAIL)
    chips = [c.text() for c in disabled.findChildren(QLabel, "chip")]
    assert "Disabled on gateway" in chips
    captions = [label.text() for label in disabled.findChildren(QLabel, "cardHelp")]
    assert "Approval cannot run it." in captions
    assert disabled.property("unavailable") == "true"
    assert disabled.remember_offerable is False

    unknown = ToolCallCard(call={"name": "mystery_tool", "arguments": {}}, index=0)
    chips = [(c.text(), c.property("tone")) for c in unknown.findChildren(QLabel, "chip")]
    assert chips == [("Unknown risk", "unknown")]
    captions = [label.text() for label in unknown.findChildren(QLabel, "cardHelp")]
    assert "This tool is not in the gateway's inventory." in captions
    assert unknown.remember_offerable is False

    auto = ToolCallCard(call={"name": "read_file", "arguments": {"file_path": "a"}}, index=0, risk=READ_FILE)
    captions = [label.text() for label in auto.findChildren(QLabel, "cardHelp")]
    assert "Gateway default: auto · asking because this Mac set Ask" in captions


@pytest.mark.basic
def test_card_content_block_has_preview_expander() -> None:
    body = "\n".join(f"line {i}" for i in range(60))
    card = ToolCallCard(call={"name": "write_file", "arguments": {"file_path": "/tmp/x", "content": body}}, index=0, risk=WRITE_FILE)
    assert len(card.preview_panels) == 1
    panel = card.preview_panels[0]
    assert panel.objectName() == "monoPanel" and panel.isReadOnly() and panel.isHidden()
    assert panel.toPlainText().splitlines()[-1] == "… (+20 more lines)"
    toggles = [b for b in card.findChildren(QPushButton, "linkButton") if "Preview" in b.text()]
    assert len(toggles) == 1
    toggles[0].click()
    assert panel.isHidden() is False


# --------------------------------------------------------------------------- #
# Style discipline
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_approval_qss_uses_tokens_only() -> None:
    assert "qlineargradient" not in APPROVAL_QSS
    assert "qradialgradient" not in APPROVAL_QSS
    assert "QGraphicsDropShadowEffect" not in Path(approval_module.__file__).read_text(encoding="utf-8")
    source = Path(approval_module.__file__).read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}(?![0-9a-zA-Z_])", source), "hex literal in ui/approval.py"
    assert "QFrame#toolApprovalCallCard" in APPROVAL_QSS
    assert "QLabel#usageStatusChip" in APPROVAL_QSS
    sheet, _ = _sheet([CMD_CALL], show=False)
    # The LIVE builder, not the import-frozen constant: the type scale follows
    # the user's text size, so anything captured at import is stale the moment
    # a window is built with a non-default size.
    assert sheet.styleSheet().endswith(approval_module.build_approval_qss())
    assert isinstance(sheet.findChild(QFrame, "toolApprovalCallCard"), QFrame)


@pytest.mark.basic
def test_importing_the_sheet_does_not_import_the_app_module() -> None:
    import subprocess
    import sys

    code = "import sys, abstractassistant.ui.approval; print('abstractassistant.app' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert out.stdout.strip() == "False"
