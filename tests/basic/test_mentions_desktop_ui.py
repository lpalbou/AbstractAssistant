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


def test_new_attachment_after_a_failed_mention_is_a_fresh_palette_send(palette, tmp_path):
    window, controller = palette
    controller.session_run_id = lambda: ""
    _palette_chips(window)
    window._submit()
    worker = controller.workers[-1]
    worker.not_addressed()
    worker.done(text=TEXT, stopped="Castor cannot answer right now.", unsent=[worker.entity("castor")])
    worker.finish()
    _pump()
    assert window._mention_resend is not None
    rows_before = len(controller.messages)
    image = tmp_path / "new.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nnew attachment")
    window._attachments = [str(image)]

    window._submit()
    fresh_worker = controller.workers[-1]
    assert fresh_worker.resend is None
    assert len(controller.messages) == rows_before + 1
    assert window._pending_submission["attachments"] == [str(image)]


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


# ---- review 2026-11-11: F1, F2 and the boundary ---------------------------------------------


def _entities_only_running(window, controller):
    """An entities-only message in flight: the gateway kept the words, Castor is answering."""
    _palette_chips(window)
    window._submit()
    worker = controller.workers[-1]
    worker.not_addressed()
    worker.ask("castor")
    _pump()
    return worker


@pytest.mark.parametrize("previous_run", ["run-previous-agent-turn", ""])
def test_a_followup_while_only_entities_answer_waits_and_goes_as_its_own_message(palette, previous_run):
    """F1: the chat's last run is an earlier, FINISHED one (or none in a new chat): a plain
    follow-up is never steered into it; it waits for the answers and is sent as a new message."""
    window, controller = palette
    controller.previous_run = previous_run
    worker = _entities_only_running(window, controller)
    window.prompt_edit.setPlainText("and you, what about tomorrow?")
    window._submit()
    assert controller.commands == []  # no guidance to any run
    assert window.prompt_edit.toPlainText() == "and you, what about tomorrow?"
    assert window.chat_status_label.text() == "Your message will send when the answers are in."
    assert window.title_label.text() != "Steering the run…"
    assert len(controller.workers) == 1
    worker.answer("castor", "Hello.")
    worker.answer("pollux", "Hi.")
    worker.done(text=TEXT)
    worker.finish()
    _pump(0.05)
    assert len(controller.workers) == 2  # sent as its own message once the chain ended
    assert controller.workers[-1].kwargs["prompt"] == "and you, what about tomorrow?"
    assert controller.commands == []


def test_stop_pause_and_resume_never_reach_a_finished_run_while_only_entities_answer(palette):
    """F1: Stop ends the asking (the worker) and cancels no run; pause and resume are offered
    disabled and do nothing."""
    window, controller = palette
    controller.previous_run = "run-previous-agent-turn"
    worker = _entities_only_running(window, controller)
    _menu, act_pause, act_resume, act_stop = window._run_control_menu()
    assert not act_pause.isEnabled() and not act_resume.isEnabled() and act_stop.isEnabled()
    window._pause_active_run()
    window._resume_active_run()
    window._cancel_active_run()
    assert controller.commands == []
    assert worker.interrupted


def test_a_reattached_agent_run_after_an_entities_only_message_shows_its_progress(palette):
    """F2: the entities-only mark belongs to its message; a later agent run that is reattached
    shows its thinking card, its status and the no-reply line as always."""
    window, controller = palette
    worker = _entities_only_running(window, controller)
    worker.answer("castor", "Hello.")
    worker.answer("pollux", "Hi.")
    worker.done(text=TEXT)
    worker.finish()
    _pump()
    controller.previous_run = "run-live"
    window._on_reattach_candidate({"run_id": "run-live", "status": "running"})
    attached = controller.workers[-1]
    assert attached.kwargs == {"attach": "run-live"}
    attached.status("thinking")
    _pump()
    assert window._thinking_card is not None
    assert window.title_label.text() == "Thinking…"
    attached.finish()
    _pump()
    assert window.chat_status_label.text() == "The workflow completed, but it returned no written reply."


def test_an_entities_only_send_shows_no_workflow_line_even_before_the_gateway_answers(palette):
    """The chips say no agent will run (entity chips, no `@agent`): no "Running assistant
    workflow…" flash while the start is on its way. A gateway that starts the agent anyway
    gets its run shown."""
    window, controller = palette
    _palette_chips(window)
    window._submit()
    _pump()
    assert window._thinking_card is None
    assert window.title_label.text() == "AbstractAssistant"
    assert window._avatar_presentation().state != "thinking"
    assert [p.author_name for p in _cards(window, PendingMentionCard)] == ["Castor", "Pollux"]
    worker = controller.workers[-1]
    worker.event_emitted.emit({"type": "run_activity", "run_id": "run-agent", "summary": "Running"})
    worker.status("thinking")
    _pump()
    assert window._thinking_card is not None


def test_typed_at_name_words_before_a_picked_chip_are_words_and_the_chip_keeps_its_place(field):
    """Positions come from the chip, never from a search of the words for "@Name"."""
    edit = field
    edit.insertPlainText("@Castor said ")
    QTest.keyClicks(edit, "@cas")
    QTest.keyClick(edit, Qt.Key_Return)
    text, chips = edit.message_payload()
    assert text == "@Castor said @Castor"
    assert [(c["id"], c["start"]) for c in chips] == [("castor", 13)]


def _js_slice(text: str, begin: int, end: int) -> str:
    """JavaScript's String.slice: UTF-16 code units."""
    return text.encode("utf-16-le")[2 * begin:2 * end].decode("utf-16-le")


def test_offsets_are_utf16_code_units_like_the_web_after_an_emoji(palette):
    """(e) `start` counts UTF-16 code units (the kit's unit): after "🌊 Wave" the desktop's
    offsets read right in the web, the sent bubble draws its chips in place, and a web copy
    pastes its chips into the desktop."""
    window, controller = palette
    edit = window.prompt_edit
    edit.insertPlainText("🌊 Wave ")
    _palette_chips(window)
    text, chips = edit.message_payload()
    assert text == "🌊 Wave " + TEXT
    assert [(c["id"], c["start"]) for c in chips] == [("castor", 11), ("pollux", 23)]
    for chip in chips:
        word = "@" + chip["name"]
        assert _js_slice(text, chip["start"], chip["start"] + len(word)) == word
    # The clipboard the web reads.
    cursor = edit.textCursor()
    cursor.select(cursor.Document)
    edit.setTextCursor(cursor)
    copied = edit.createMimeDataFromSelection()
    import json

    from abstractassistant.ui.mention_chip import MENTION_CLIPBOARD_TYPE

    box = json.loads(bytes(copied.data(MENTION_CLIPBOARD_TYPE)).decode("utf-8"))
    assert [(m["id"], m["start"]) for m in box["mentions"]] == [("castor", 11), ("pollux", 23)]
    # A web copy (UTF-16 offsets) pastes as chips.
    edit.clear()
    edit.insertFromMimeData(copied)
    assert [m["id"] for m in edit.mentions()] == ["castor", "pollux"]
    # The sent bubble draws both chips where their words are.
    window._submit()
    _pump()
    user = _message_cards(window, "user")[0]
    assert user._mention_chips_placed == 2
    assert user._user_browser.document().toPlainText().startswith("🌊 Wave Hi ")


def test_a_sent_chip_shows_its_card_on_keyboard_focus(palette):
    """(c) Tab reaches a sent chip (an anchor) and its card shows after the same rest."""
    window, controller = palette
    _palette_chips(window)
    window._submit()
    _pump()
    browser = _message_cards(window, "user")[0]._user_browser
    browser.setFocus()
    QTest.keyClick(browser, Qt.Key_Tab)  # the keyboard reaches the first chip
    cursor = browser.textCursor()
    assert cursor.selectionEnd() - cursor.selectionStart() == 1
    _pump(0.25)
    card = window.findChild(app_module.QFrame, "mentionCard")
    assert card is not None and card.isVisible()
    assert card.name_label.text() == "Castor"
    browser.anchorClicked.emit(app_module.QUrl("mention:0"))  # Enter on the chip opens nothing
