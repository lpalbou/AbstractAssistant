"""The desktop composer's `@` mentions and the transcript around them (operator rulings
2026-11-08/10/11, "following the same logic as other apps").

Driven on the real widgets offscreen with a fake worker (tests/basic/mention_desktop_fake.py);
nothing reaches a gateway. Each test names the behaviour it guards; each was checked red against
a mutant of that behaviour.
"""

from __future__ import annotations

import time

import pytest
from PyQt5.QtCore import QCoreApplication, QEvent, QPoint, QRect, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from mention_desktop_fake import ENTITIES, SMOKE, MentionController

import abstractassistant.app as app_module
from abstractassistant.core.mentions import EntityRoster, Mention
from abstractassistant.ui.mention_chip import chip_rect, document_mentions
from abstractassistant.ui.mention_composer import MentionTextEdit, as_mentions
from abstractassistant.ui.pending_bubble import PendingMentionCard

pytestmark = pytest.mark.basic

TEXT = "Hi @Castor and @Pollux what do you both think?"


def _pump(seconds: float = 0.0) -> None:
    app = SMOKE["_app"]()
    end = time.monotonic() + seconds
    while True:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        if time.monotonic() >= end:
            return
        time.sleep(0.01)


@pytest.fixture
def field():
    """A bare composer field in a window, with the roster already read."""
    SMOKE["_app"]()
    window = QMainWindow()
    host = QWidget()
    QVBoxLayout(host).addWidget(edit := MentionTextEdit())
    window.setCentralWidget(host)
    window.resize(520, 360)
    window.show()
    edit.set_mentions_enabled(True)
    edit.set_mention_names(EntityRoster.from_payload(ENTITIES))
    edit.setFocus()
    yield edit
    window.hide()
    window.deleteLater()
    _pump()


@pytest.fixture
def palette():
    SMOKE["_app"]()
    controller = MentionController()
    window = app_module.AssistantPalette(controller=controller)
    SMOKE["_wait_for_bootstrap"](window)
    window._hide_if_inactive = lambda: None
    window._available_screen_geometry = lambda: QRect(0, 0, 1600, 1000)
    window.show()
    controller.update_preferences(window_width=760, window_height=640)
    window._reflow_shell()
    _pump()
    yield window, controller
    window.shutdown()
    window.hide()
    window.deleteLater()
    _pump()


def _type_two_chips(edit) -> None:
    QTest.keyClicks(edit, "Hi @cas")
    QTest.keyClick(edit, Qt.Key_Return)
    QTest.keyClicks(edit, "and @pol")
    QTest.keyClick(edit, Qt.Key_Tab)
    QTest.keyClicks(edit, "what do you both think?")


def _palette_chips(window) -> None:
    edit = window.prompt_edit
    edit.setFocus()
    QTest.keyClicks(edit, "Hi @cas")
    for _ in range(300):  # the roster is read off the GUI thread
        _pump()
        if edit.mention_roster() is not None:
            break
        time.sleep(0.01)
    assert edit.mention_roster() is not None, "the names were never read"
    QTest.keyClick(edit, Qt.Key_Return)
    QTest.keyClicks(edit, "and @pol")
    QTest.keyClick(edit, Qt.Key_Return)
    QTest.keyClicks(edit, "what do you both think?")


def _cards(window, kind):
    out = []
    for i in range(window.history_layout.count()):
        widget = window.history_layout.itemAt(i).widget()
        if isinstance(widget, kind) and not widget.isHidden():
            out.append(widget)
    return out


def _message_cards(window, role):
    return [c for c in _cards(window, app_module.MessageCard) if c._role == role]


# ---- the composer ---------------------------------------------------------------------------


def test_a_picked_chip_is_the_mention_and_deleting_it_removes_it(field):
    """Typing `@cas` + Enter puts Castor's chip in the sentence; the mention list IS the chips in
    the text, through Backspace, undo and redo, copy and paste."""
    edit = field
    QTest.keyClicks(edit, "Hi @cas")
    assert edit.mention_list_open()
    assert [c["name"] for c in edit.picker().items] == ["Castor"]
    QTest.keyClick(edit, Qt.Key_Return)
    assert not edit.mention_list_open()
    assert edit.toPlainText() == "Hi @Castor "
    assert [m["id"] for m in edit.mentions()] == ["castor"]
    # One Backspace takes the space, the next the whole chip: the mention goes with it.
    QTest.keyClick(edit, Qt.Key_Backspace)
    QTest.keyClick(edit, Qt.Key_Backspace)
    assert edit.toPlainText() == "Hi "
    assert edit.mentions() == []
    edit.undo()
    assert [m["id"] for m in edit.mentions()] == ["castor"]
    edit.redo()
    assert edit.mentions() == []
    edit.undo()
    # Copy and paste carry the chip; a name already in the text is pasted as words.
    edit.selectAll()
    copied = edit.createMimeDataFromSelection()
    assert copied.text() == "Hi @Castor"
    edit.moveCursor(edit.textCursor().End)
    QTest.keyClicks(edit, " ")
    edit.insertFromMimeData(copied)
    assert edit.toPlainText() == "Hi @Castor Hi @Castor"
    assert [m["id"] for m in edit.mentions()] == ["castor"]
    edit.clear()
    edit.insertFromMimeData(copied)
    assert [m["id"] for m in edit.mentions()] == ["castor"]


def test_a_typed_at_name_is_words_and_a_picked_name_is_not_offered_again(field):
    """Nothing is read out of the words (no-heuristics ruling); one chip per name."""
    edit = field
    edit.setPlainText("Hi @Castor")
    assert edit.mentions() == []
    assert edit.message_payload() == ("Hi @Castor", [])
    edit.clear()
    QTest.keyClicks(edit, "@cas")
    QTest.keyClick(edit, Qt.Key_Return)
    QTest.keyClicks(edit, "@cas")
    assert edit.picker().items == []
    assert edit.picker().empty_label.text() == "Already mentioned."


def test_the_send_carries_the_words_and_each_chip_with_its_index_and_offset(field):
    edit = field
    QTest.keyClicks(edit, "  ")  # leading spaces are trimmed like every send; offsets follow
    _type_two_chips(edit)
    text, chips = edit.message_payload()
    assert text == TEXT
    assert [(c["id"], c["name"], c["kind"], c["index"], c["start"]) for c in chips] == [
        ("castor", "Castor", "entity", 0, 3),
        ("pollux", "Pollux", "entity", 1, 15),
    ]
    for chip in chips:
        assert text[chip["start"]:chip["start"] + len(chip["name"]) + 1] == "@" + chip["name"]
    mentions = as_mentions(chips)
    assert mentions == [Mention("castor", "Castor", "entity", 0, 3), Mention("pollux", "Pollux", "entity", 1, 15)]


# ---- the transcript -------------------------------------------------------------------------


def test_pending_bubbles_show_until_answered_and_go_at_once_on_refusal(palette):
    window, controller = palette
    _palette_chips(window)
    window._submit()
    worker = controller.workers[-1]
    assert [m.id for m in worker.mentions] == ["castor", "pollux"]
    worker.not_addressed()
    _pump()
    pending = _cards(window, PendingMentionCard)
    assert [p.author_name for p in pending] == ["Castor", "Pollux"]
    assert all(p.dots.animating for p in pending)
    worker.ask("castor")
    worker.answer("castor", "It reads well to me.")
    _pump()
    assert [p.author_name for p in _cards(window, PendingMentionCard)] == ["Pollux"]
    answers = _message_cards(window, "assistant")
    assert [a._author_badge.author_name for a in answers] == ["Castor"]
    # A refusal: the bubble goes at once (no history rebuild needed) and the sentence shows.
    worker.ask("pollux")
    worker.skip("pollux", "Pollux is in another conversation.")
    assert _cards(window, PendingMentionCard) == []
    assert window.chat_status_label.text() == "Pollux is in another conversation."
    assert not window.chat_status_label.isHidden()
    worker.done(text=TEXT, notes=["Pollux is in another conversation."])
    worker.finish()
    _pump()
    assert _cards(window, PendingMentionCard) == []
    assert window.chat_status_label.text() == "Pollux is in another conversation."


def test_the_words_show_once_for_several_mentions_and_for_a_resend(palette):
    """One user bubble with its chips, then each answer in arrival order under its author;
    sending the same words again after a stop asks only the unsent chips and adds no bubble."""
    window, controller = palette
    _palette_chips(window)
    window._submit()
    worker = controller.workers[-1]
    worker.not_addressed()
    worker.answer("pollux", "Pollux first.")
    worker.answer("castor", "Then Castor.")
    worker.done(text=TEXT)
    worker.finish()
    _pump()
    users = _message_cards(window, "user")
    assert len(users) == 1
    assert users[0]._mention_chips_placed == 2
    assert [m["id"] for m in document_mentions(users[0]._user_browser.document())] == ["castor", "pollux"]
    assert [a._author_badge.author_name for a in _message_cards(window, "assistant")] == ["Pollux", "Castor"]

    # A second message stops at Pollux: the words come back with Pollux's chip only.
    window.prompt_edit.clear()
    _palette_chips(window)
    window._submit()
    worker = controller.workers[-1]
    worker.not_addressed()
    worker.answer("castor", "Castor again.")
    summary = worker.done(text=TEXT, stopped="Pollux cannot answer right now.", unsent=[worker.entity("pollux")])
    worker.finish()
    _pump()
    assert summary.resend is not None
    assert window.prompt_edit.toPlainText() == TEXT
    assert [m["id"] for m in window.prompt_edit.mentions()] == ["pollux"]
    rows_before = len(controller.messages)
    window._submit()
    resend_worker = controller.workers[-1]
    assert resend_worker.resend is summary.resend
    _pump()
    assert window._thinking_card is None  # a resend starts no agent run
    assert window.title_label.text() == "AbstractAssistant"
    assert [p.author_name for p in _cards(window, PendingMentionCard)] == ["Pollux"]
    assert len(controller.messages) == rows_before  # no second copy of the person's words
    assert len(_message_cards(window, "user")) == 2


def test_no_informational_line_and_no_agent_indicator_when_only_entities_answer(palette):
    """Operator 2026-11-10/11: no line above the composer about who reads what; while only
    entities answer, their bubbles are the whole indicator (no thinking card, no busy header,
    the assistant's orb does not think)."""
    window, controller = palette

    def lines() -> list:
        return [label.text() for label in window.findChildren(QLabel) if label.isVisible()]

    def assert_no_line(*words) -> None:
        shown = lines()
        for phrase in words:
            assert not any(phrase in text for text in shown), (phrase, shown)

    _palette_chips(window)
    _pump()
    assert_no_line("will read this conversation", "stays out of this message")
    assert window.chat_status_label.isHidden()
    window._submit()
    worker = controller.workers[-1]
    worker.not_addressed()
    worker.ask("castor")
    _pump()
    assert_no_line("will read this conversation", "stays out of this message", "Running assistant workflow")
    assert window.chat_status_label.isHidden()
    assert window._thinking_card is None
    assert window._avatar_presentation().state != "thinking"
    assert len(_cards(window, PendingMentionCard)) == 2
    worker.answer("castor", "Yes.")
    worker.answer("pollux", "Yes too.")
    worker.done(text=TEXT)
    worker.finish()
    _pump()
    assert window.chat_status_label.isHidden()  # no "no written reply" line either


def test_a_sent_chip_shows_its_entity_card_after_a_rest(palette):
    window, controller = palette
    _palette_chips(window)
    window._submit()
    _pump()
    user = _message_cards(window, "user")[0]
    browser = user._user_browser
    doc = browser.document()
    castor = document_mentions(doc)[0]
    rect = chip_rect(doc, castor["position"])
    watcher = browser._mention_hover_watcher
    watcher.hover(QPoint(int(rect.center().x()), int(rect.center().y())))
    card = window.findChild(app_module.QFrame, "mentionCard")
    assert card is None or card.isHidden()  # not before the rest
    _pump(0.25)
    card = window.findChild(app_module.QFrame, "mentionCard")
    assert card is not None and card.isVisible()
    assert card.name_label.text() == "Castor"
    assert card.state_label.text() == "Castor is in a conversation."
    watcher.hover(QPoint(int(rect.right() + 40), int(rect.center().y())))
    assert card.isHidden()
