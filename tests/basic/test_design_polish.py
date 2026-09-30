"""Design-system guarantees added in the round-two design QA pass.

Everything here is a rule the reviewer applied by hand once; the tests keep
it from regressing: tokens only, an 11 px type floor, no gradients, a footer
for page actions, labelled checkbox rows, bounded tool descriptions, key-cap
hints on the approval sheet, self-owned voice-strip tints, and calm activity
tones that cover every state the model can produce.
"""

from __future__ import annotations

import dataclasses
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton, QSizePolicy

import abstractassistant.ui.settings.common as common_module
import abstractassistant.ui.settings.dialog as dialog_module
import abstractassistant.ui.settings.pages as pages_module
import abstractassistant.ui.styles as styles_module
import abstractassistant.ui.voice_strip as strip_module
from abstractassistant.theme import THEME
from abstractassistant.ui.activity import ACTIVITY_QSS, STEP_TONES, RunActivityCard, RunActivityModel
from abstractassistant.ui.approval import APPROVAL_QSS, ToolApprovalSheet
from abstractassistant.ui.dialogs import AskUserDialog
from abstractassistant.ui.settings.common import Card, SettingsPage
from abstractassistant.ui.settings.pages import short_description
from abstractassistant.ui.styles import alpha, dialog_stylesheet, tone_colors
from abstractassistant.ui.voice_strip import VOICE_STRIP_QSS, VoiceStrip


_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def _theme_hexes() -> set:
    values = set()
    for value in dataclasses.asdict(THEME).values():
        if isinstance(value, str):
            values.add(value.lower())
        elif isinstance(value, dict):
            values.update(str(v).lower() for v in value.values() if isinstance(v, str))
    return values


# --------------------------------------------------------------------------- #
# Tokens, type floor, gradients
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_theme_has_the_attention_family() -> None:
    assert THEME.attention.startswith("#") and len(THEME.attention) == 7
    assert THEME.attention_text.startswith("#")
    assert THEME.attention_bg.startswith("rgba(")
    assert THEME.attention_border.startswith("rgba(")


@pytest.mark.basic
def test_alpha_derives_rgba_from_hex_tokens_only() -> None:
    assert alpha("#ff6b6e", 0.5) == "rgba(255, 107, 110, 0.50)"
    assert alpha("rgba(1, 2, 3, 0.4)", 0.9) == "rgba(1, 2, 3, 0.4)"  # passthrough
    assert alpha("#79c7ff", 2.0).endswith("1.00)")


@pytest.mark.basic
def test_every_shared_stylesheet_paints_only_theme_hexes() -> None:
    allowed = _theme_hexes()
    for name, sheet in (
        ("dialog", dialog_stylesheet()),
        ("settings", dialog_module.SETTINGS_QSS),
        ("approval", APPROVAL_QSS),
        ("activity", ACTIVITY_QSS),
        ("voice", VOICE_STRIP_QSS),
    ):
        found = {h.lower() for h in _HEX.findall(sheet)}
        assert found, f"{name}: paints nothing"
        assert found <= allowed, f"{name}: literal hex not in THEME: {sorted(found - allowed)}"
        assert "qlineargradient" not in sheet and "qradialgradient" not in sheet, name


@pytest.mark.basic
def test_no_text_below_eleven_pixels_in_any_shared_stylesheet() -> None:
    for name, sheet in (
        ("dialog", dialog_stylesheet()),
        ("settings", dialog_module.SETTINGS_QSS),
        ("approval", APPROVAL_QSS),
        ("activity", ACTIVITY_QSS),
        ("voice", VOICE_STRIP_QSS),
    ):
        sizes = [int(px) for px in re.findall(r"font-size:\s*(\d+)px", sheet)]
        assert sizes, name
        assert min(sizes) >= 11, f"{name}: font-size {min(sizes)}px is below the 11 px floor"


@pytest.mark.basic
def test_source_files_carry_no_hex_literals() -> None:
    for module in (styles_module, common_module, pages_module, dialog_module, strip_module):
        source = Path(module.__file__).read_text(encoding="utf-8")
        hits = [
            h for h in re.findall(r"#[0-9a-fA-F]{3,8}(?![0-9a-zA-Z_])", source)
            # docstring / comment references like "#rrggbb" are not colours
            if h.lower() != "#rrggbb"
        ]
        assert hits == [], f"{module.__name__}: hex literal(s) {hits}"


@pytest.mark.basic
def test_tone_table_covers_every_tone_the_widgets_use() -> None:
    tones = tone_colors()
    for tone in ("neutral", "info", "success", "ok", "warning", "warn", "error", "danger", "attention",
                 "observe", "act", "outreach", "destroy", "unknown", "thinking", "tool", "waiting", "idle"):
        assert tone in tones, tone
    # observe is deliberately neutral so the loud tiers stand out (spec §1.2)
    assert tones["observe"] == tones["neutral"]
    sheet = dialog_stylesheet()
    for tone in tones:
        assert f'QLabel#chip[tone="{tone}"]' in sheet
    assert "QLabel#keyHint" in sheet and "QTextBrowser#askPrompt" in sheet


# --------------------------------------------------------------------------- #
# Settings shell
# --------------------------------------------------------------------------- #


class _Ctl:
    preferences = None

    def __init__(self) -> None:
        from abstractassistant.preferences import AssistantPreferences

        self.preferences = AssistantPreferences(hotkey_enabled=False)

    def update_preferences(self, **updates):
        from abstractassistant.preferences import AssistantPreferences

        payload = self.preferences.to_dict()
        payload.update(updates)
        self.preferences = AssistantPreferences.from_dict(payload)
        return self.preferences

    def tool_inventory(self):
        long = "Take one photo now and wait for the file. " + ("More guidance for the model. " * 20)
        return {
            "tool_mode": "approval",
            "items": [
                {"name": "camera_capture_photo", "toolset": "camera", "description": long, "available": True, "risk_tier": "outreach", "policy_default": "ask", "selected_mode": "ask"},
            ],
        }


@pytest.mark.basic
def test_page_footer_hosts_actions_and_feedback_without_stretching_buttons() -> None:
    _app()
    page = SettingsPage(_Ctl())
    assert page.footer_frame.isHidden()
    save = QPushButton("Save")
    page.add_actions(save)
    assert page.actions() == [save]
    assert save.sizePolicy().horizontalPolicy() == QSizePolicy.Fixed
    assert not page.footer_frame.isHidden()
    page.say("Saved.", tone="ok")
    assert page.feedback.text() == "Saved." and page.feedback.property("tone") == "ok"
    # The feedback label keeps the slack even when empty, so it is never hidden.
    page.say("")
    assert page.feedback.text() == "" and not page.feedback.isHidden()


@pytest.mark.basic
def test_card_rows_label_checkboxes_and_align_label_baselines() -> None:
    _app()
    card = Card("Replies")
    box = QCheckBox("Speak replies automatically")
    row = card.add_row("Read aloud", box)
    label = row.findChild(QLabel, "rowLabel")
    assert label is not None and label.text() == "Read aloud"
    assert label.contentsMargins().top() == 1  # text-height control: no nudge
    from PyQt5.QtWidgets import QLineEdit

    row2 = card.add_row("Gateway URL", QLineEdit())
    label2 = row2.findChild(QLabel, "rowLabel")
    assert label2.contentsMargins().top() == 6  # 28 px control: baseline nudge
    assert common_module.LABEL_COLUMN_MIN <= label2.minimumWidth() <= common_module.LABEL_COLUMN_MAX


@pytest.mark.basic
def test_every_settings_page_puts_its_actions_in_the_footer() -> None:
    from abstractassistant.ui.settings import SettingsDialog

    _app()
    dlg = SettingsDialog(controller=_Ctl(), apply_hotkey=lambda: None, parent=None)
    assert [b.text() for b in dlg.page_connection.actions()] == ["Reload status", "Sign out", "Connect"]
    # Voice: switches and choices only, each applied as it changes (no Save).
    assert [b.text() for b in dlg.page_voice.actions()] == []
    assert [b.text() for b in dlg.page_workspace.actions()] == ["Reset", "Save"]
    assert [b.text() for b in dlg.page_tools.actions()] == ["Use gateway defaults", "Save"]
    assert [b.text() for b in dlg.page_window.actions()] == ["Save"]
    assert [b.text() for b in dlg.page_about.actions()] == ["Copy diagnostics"]
    # Exactly one primary per page footer.
    for page in dlg.pages.values():
        primaries = [b for b in page.actions() if b.objectName() == "primaryButton"]
        assert len(primaries) <= 1, page.title
    # Every switch row on the Voice and Window pages has a label in the left column.
    for page in (dlg.page_voice, dlg.page_window):
        for box in page.findChildren(QCheckBox):
            row = box.parentWidget()
            while row is not None and row.objectName() != "cardRow":
                row = row.parentWidget()
            assert row is not None and row.findChild(QLabel, "rowLabel") is not None, box.text()
    assert dlg.connection_feedback is dlg.page_connection.feedback


@pytest.mark.basic
def test_tools_page_shows_the_first_sentence_and_keeps_the_rest_in_the_tooltip() -> None:
    from abstractassistant.ui.settings import SettingsDialog

    _app()
    dlg = SettingsDialog(controller=_Ctl(), apply_hotkey=lambda: None, parent=None)
    dlg.show_section("tools")
    info = dlg.page_tools._rows["camera_capture_photo"]
    help_label = info["row"].help_label
    assert help_label.text() == "Take one photo now and wait for the file."
    assert "More guidance" in help_label.toolTip()
    assert "more guidance" in info["search"]  # the filter still matches the full text


@pytest.mark.basic
def test_short_description_bounds_long_first_sentences() -> None:
    assert short_description("") == ""
    assert short_description("Read a file. Then more.") == "Read a file."
    assert short_description("No terminal punctuation here") == "No terminal punctuation here"
    long = "word " * 80
    clipped = short_description(long)
    assert clipped.endswith("…") and len(clipped) <= 150


@pytest.mark.basic
def test_window_page_lists_only_real_shortcuts() -> None:
    keys = {k for k, _ in pages_module._SHORTCUTS}
    assert keys == {"⏎", "⇧⏎", "Esc", "⌘.", "⌘N", "⌘,", "⌘⇧V"}
    assert {k for k, _ in pages_module._APPROVAL_SHORTCUTS} == {"⏎", "⌘D", "Esc", "F"}


# --------------------------------------------------------------------------- #
# Approval sheet
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_approval_sheet_shows_key_cap_hints_next_to_each_action() -> None:
    _app()
    sheet = ToolApprovalSheet(tool_calls=[{"name": "read_file", "arguments": {"file_path": "a"}}], risks={}, run_id="r", wait_key="w")
    hints = {label.text() for label in sheet.findChildren(QLabel, "keyHint")}
    assert hints == {"esc", "D", "⏎"}
    assert sheet.defer_hint.objectName() == "keyHint"
    assert sheet.queue_note.objectName() == "queueNote"
    assert "QLabel#toolApprovalHint" in APPROVAL_QSS
    assert "QPushButton#toolApprovalSecondaryButton" in APPROVAL_QSS


# --------------------------------------------------------------------------- #
# Activity card + voice strip
# --------------------------------------------------------------------------- #


@pytest.mark.basic
def test_activity_qss_is_self_sufficient_for_every_tone() -> None:
    for tone in set(STEP_TONES) | {"waiting"}:
        assert f'QFrame#thinkingBubble[tone="{tone}"]' in ACTIVITY_QSS, tone
        assert f'QLabel#thinkingStatusText[tone="{tone}"]' in ACTIVITY_QSS, tone
    # Base rules so the card renders the same outside the palette stylesheet.
    assert "QFrame#thinkingBubble {" in ACTIVITY_QSS
    assert "QLabel#thinkingStatusText {" in ACTIVITY_QSS
    assert "QFrame#thinkingIndicator" in ACTIVITY_QSS


@pytest.mark.basic
def test_activity_tool_rows_use_neutral_text_roles_not_syntax_colours() -> None:
    _app()
    model = RunActivityModel(run_id="r")
    model.apply_event({"type": "tool_started", "tools": [{"name": "read_file", "arguments": {"file_path": "src/main.py"}, "call_id": "c1"}]})
    card = RunActivityCard()
    card.set_model(model)
    card.set_expanded(True)
    row = card._rows["tool:c1"]
    html = row._title.text()
    assert "read_file" in html and "file_path" in html
    hexes = {h.lower() for h in _HEX.findall(html)}
    assert hexes <= {THEME.text_primary.lower(), THEME.text_secondary.lower()}
    assert card.pause_button.toolTip() == "Pause after the current step"


@pytest.mark.basic
def test_voice_strip_owns_its_state_tints() -> None:
    _app()
    strip = VoiceStrip()
    assert strip.styleSheet() == VOICE_STRIP_QSS
    for state in ("starting", "listening", "heard", "thinking", "speaking", "paused", "error"):
        strip.set_state(state)
        assert strip.property("state") == state
        assert strip.status.property("state") == state
    for state in ("starting", "heard", "thinking", "paused", "error"):
        assert f'QFrame#voiceStrip[state="{state}"]' in VOICE_STRIP_QSS, state
    strip.set_state("speaking")
    assert not strip.stop_button.isHidden() and strip.pause_button.isHidden()
    assert strip.interrupt_button.toolTip().startswith("Stop the run")


@pytest.mark.basic
def test_ask_dialog_prompt_is_styled_by_the_shared_builder() -> None:
    _app()
    dialog = AskUserDialog(prompt="Which folder?")
    assert dialog.prompt_view.objectName() == "askPrompt"
    assert dialog.prompt_view.styleSheet() == ""  # no per-widget literal
    assert dialog.windowTitle() == "Question"
