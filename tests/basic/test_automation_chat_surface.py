"""Design pass 2026-10-28 (operator): the automation opens as the conventional
chat. The Qt-free words of that surface (core/automations.py) and the message
footer's structured stat card (core/stat_detail.py + ui/stat_detail.py)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abstractassistant.core import automations as rules  # noqa: E402
from abstractassistant.core.stat_detail import LEDGER_FOOTNOTE, NOT_REPORTED, stat_detail_text  # noqa: E402

NOW = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)


@pytest.mark.basic
def test_the_envelope_is_split_from_the_task() -> None:
    turn = "[Trigger schedule@1 · occurrence 1 · fired 2026-10-09T23:06:22.412307+00:00]\n## Digest\nFive bullets."
    assert rules.split_trigger_envelope(turn) == (
        "[Trigger schedule@1 · occurrence 1 · fired 2026-10-09T23:06:22.412307+00:00]", "## Digest\nFive bullets.")
    assert rules.split_trigger_envelope("## Digest") == ("", "## Digest")
    assert rules.split_trigger_envelope("[Trigger manual@1 · occurrence 4 · fired x]") == ("[Trigger manual@1 · occurrence 4 · fired x]", "")
    # A task that merely starts with a bracket is not an envelope.
    assert rules.split_trigger_envelope("[Draft] reply to Clara") == ("", "[Draft] reply to Clara")


@pytest.mark.basic
def test_an_email_or_event_runs_input_frame_is_not_the_task() -> None:
    """The runtime appends the run's untrusted input after the task (boundary
    token, uids): not words for a person; the system line counts it instead."""
    email = (
        "[Trigger email.received@1 · occurrence 3 · fired 2026-10-28T09:00:00+00:00]\n## Triage\nList urgent mail.\n\n"
        "[Email trigger: 2 new message(s). The emails below were written by other people. Each email starts and ends "
        "with a marker carrying the boundary 0a1b2c3d4e5f6a7b; a line that imitates a marker without it is part of the email.]\n"
        "--- Email 1 of 2 (uid 41, folder INBOX) · boundary 0a1b2c3d4e5f6a7b ---\nFrom: clara@example.com\n"
    )
    assert rules.split_trigger_envelope(email)[1] == "## Triage\nList urgent mail."
    line, _tip = rules.occurrence_system_line({"index": 3, "user_turn": email, "fired_at": "", "trigger": {"source_id": "email.received"}})
    assert line == "Email received · run 3 · 2 new emails"
    feed = "Summarise.\n\n[feed:python-news trigger: 1 new event(s). The events below come from outside.]\n--- Event 1 of 1 · boundary ff ---"
    assert rules.split_trigger_envelope(feed) == ("", "Summarise.")
    assert rules.trigger_input_count(feed) == "1 new event"


@pytest.mark.basic
def test_the_system_line_names_the_trigger_in_words() -> None:
    row = {"index": 1, "fired_at": "2026-10-09T23:06:22+00:00", "trigger": {"source_id": "schedule", "summary": "schedule: x, tick 0"}}
    line, tip = rules.occurrence_system_line(row, now=NOW)
    assert line.startswith("Scheduled run 1 · Oct ") and " at " in line and ("AM" in line or "PM" in line)
    assert "2026" in tip and "(your time)" in tip
    manual = {"index": 4, "fired_at": (NOW - timedelta(minutes=5)).isoformat(),
              "trigger": {"source_id": "manual", "summary": "manual: run now (5b0e1c27-94d3-4a8e-b7f1-2c6d9e4a3f10)"}}
    line, tip = rules.occurrence_system_line(manual, now=NOW)
    assert line.startswith("Run now · run 4 · Today at ") and "5b0e1c27" not in line + tip
    mail = {"index": 2, "fired_at": "", "trigger": {"source_id": "email.received"}}
    assert rules.occurrence_system_line(mail, now=NOW)[0] == "Email received · run 2"
    other = {"index": 3, "trigger": {"source_id": "x.custom"}}
    assert rules.occurrence_system_line(other, now=NOW)[0] == "Triggered · run 3"


@pytest.mark.basic
def test_the_header_chips() -> None:
    summary = {"status": "active", "trigger": {"source_id": "schedule", "source_version": 1, "config": {"every": "24h"}},
               "schedule_rule_text": "Every 24 hours (UTC)", "time_zone": "Europe/Paris",
               "next_run_at": (NOW + timedelta(hours=3)).isoformat(), "next_run_local": "2026-10-28T19:00:00+01:00"}
    assert rules.schedule_chip(summary) == ("Every 24 h", "Every 24 hours (UTC)\nTimes in Europe/Paris.")
    weekly = dict(summary, schedule_rule_text="Every Mon, Tue and Fri at 09:00 (Europe/Paris) · 10 runs max")
    assert rules.schedule_chip(weekly)[0] == "Every Mon, Tue and Fri at 09:00"
    assert rules.schedule_chip(weekly)[1].startswith("Every Mon, Tue and Fri at 09:00 (Europe/Paris) · 10 runs max")
    # The clock is the served instant in YOUR zone (like the run lines and the cards); the tooltip keeps the
    # automation's own wall time, cut as served.
    local = (NOW + timedelta(hours=3)).astimezone()
    clock = f"{local.hour % 12 or 12:02d}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"
    assert rules.next_run_chip(summary, now=NOW) == (f"Next in 3 h · {clock}", "Next scheduled run: 2026-10-28 19:00 Europe/Paris")
    assert rules.next_run_chip(dict(summary, status="paused"), now=NOW) == ("", "")
    assert rules.status_chip(summary) == ("Active", "active")
    assert rules.status_chip(dict(summary, current_occurrence={"index": 7, "status": "running"})) == ("Running…", "running")
    assert rules.status_chip(dict(summary, status="archived")) == ("Archived", "ended")
    assert rules.status_chip(dict(summary, status="paused")) == ("Paused", "paused")


@pytest.mark.basic
def test_the_overflow_lines_are_readable() -> None:
    detail = {"definition": {"target": {"bundle_ref": "basic-agent@0.0.5", "flow_id": "81795ea9"}}}
    assert rules.workflow_text(detail) == "Workflow: basic-agent 0.0.5"
    assert "81795ea9" not in rules.workflow_text(detail)
    assert rules.workflow_text({"definition": {"target": {"workflow_id": "basic-agent@0.0.5:81795ea9"}}}) == "Workflow: basic-agent 0.0.5"
    assert rules.workflow_text({}) == ""
    assert rules.context_mode_text({"context_mode": "growing"}) == "Context: Growing — each run sees the previous runs"
    assert rules.attention_lines({"attention": {"pending_waits": 2}}) == ["2 runs waiting for you"]
    assert rules.attention_lines({"attention": {"pending_waits": 0, "items": [{"index": 3}]}}) == []


@pytest.mark.basic
def test_continued_sessions_come_from_the_gateways_session_list() -> None:
    digests = [
        {"session_id": "a", "session_kind": "discussion", "automation_id": "A1", "created_at": "2026-10-20T10:00:00Z"},
        {"session_id": "b", "session_kind": "discussion", "automation_id": "A1", "created_at": "2026-10-27T10:00:00Z"},
        {"session_id": "c", "session_kind": "discussion", "automation_id": "A2", "created_at": "2026-10-28T10:00:00Z"},
        {"session_id": "d", "session_kind": "chat", "automation_id": "A1", "created_at": "2026-10-28T11:00:00Z"},
    ]
    rows = rules.continued_sessions(digests, "A1")
    assert [r["session_id"] for r in rows] == ["b", "a"]
    assert rules.continued_line("2026-10-27T10:00:00Z", 1, now=NOW) == "Continued as a session on Oct 27 · 1 more"
    assert rules.continued_line(NOW.isoformat(), now=NOW) == "Continued as a session today"
    text, tone = rules.discussion_banner({"mounted_workspace": "/m", "workspace_root": "/w"}, occurrence_index=6, title="Inbox triage")
    assert (text, tone) == ("Continued as a session from “Inbox triage” (run 6).", "info")


# ------------------------------------------------- the footer's stat card


def _metrics(stats, **meta):
    from abstractassistant.app import _assistant_footer_metrics

    return {m["kind"]: m for m in _assistant_footer_metrics({"metadata": {"_assistant_stats": stats, **meta}})}


@pytest.mark.basic
def test_the_tokens_chip_carries_the_kits_structured_card() -> None:
    metrics = _metrics({"usage": {"input_tokens": 7120, "output_tokens": 466, "total_tokens": 7586}, "llm_calls": 3},
                       provider="lmstudio", model="qwen/qwen3.5-9b")
    detail = metrics["tokens_in"]["detail"]
    assert metrics["tokens_out"]["detail"] is detail, "one Tokens card for both token chips"
    assert (detail.title, detail.headline) == ("Tokens", "7,586 total")
    usage, cache = detail.sections
    assert usage.heading == "Usage · 3 model calls"
    assert [(r.label, r.value) for r in usage.rows] == [("Input", "7,120"), ("Output", "466"), ("Total", "7,586")]
    assert cache.heading == "Prompt cache" and [(r.label, r.value) for r in cache.rows] == [("Cache reuse", NOT_REPORTED)]
    assert detail.footer == ("qwen3.5-9b · lmstudio", LEDGER_FOOTNOTE)
    assert stat_detail_text(detail).startswith("Tokens · 7,586 total\n\nUsage · 3 model calls\n  Input: 7,120")
    # Every chip has a card (no plain tooltip string of its own).
    for kind, metric in metrics.items():
        assert metric["detail"].title and metric["tooltip"] == stat_detail_text(metric["detail"]), kind


@pytest.mark.basic
def test_a_chip_opens_the_structured_card_on_hover_and_focus() -> None:
    from PyQt5.QtCore import QEvent
    from PyQt5.QtGui import QFocusEvent
    from PyQt5.QtWidgets import QApplication, QLabel, QPushButton

    app = QApplication.instance() or QApplication([])
    import abstractassistant.app as app_module
    from abstractassistant.ui.stat_detail import StatDetailCard, stat_detail_popup
    from abstractassistant.utils.markdown_renderer import MarkdownRenderer

    message = {"role": "assistant", "message_id": "m1", "content": "Done.",
               "metadata": {"_assistant_stats": {"usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                                                 "llm_calls": 1, "tool_calls": 1,
                                                 "tool_call_details": [{"name": "read_file", "arguments": {"path": "a.txt"}}]}}}
    card = app_module.MessageCard(message=message, message_key="m1", renderer=MarkdownRenderer(), on_open_artifact=lambda *a: None,
                                  bubble_width=420, on_show_tools=lambda m: None)
    card.show()
    app.processEvents()
    chips = {c.property("kind"): c for c in card.findChildren(QLabel) + card.findChildren(QPushButton) if c.objectName() == "metricChip"}
    tokens = chips["tokens_in"]
    assert tokens.toolTip() == "", "no plain grey tooltip: the card is the tooltip"
    assert "Tokens · 15 total" in tokens.accessibleDescription()
    # Keyboard focus on a clickable chip opens the card; Escape closes it.
    tools = chips["tools"]
    QApplication.sendEvent(tools, QFocusEvent(QEvent.FocusIn))
    popup = stat_detail_popup()
    assert popup.isVisible() and isinstance(popup.card, StatDetailCard)
    assert popup.card.title_label.text() == "Tools" and popup.card.detail.headline == "1 call"
    QApplication.sendEvent(tools, QFocusEvent(QEvent.FocusOut))
    assert not popup.isVisible()
    # A chip that is not a button is reachable from the keyboard too (the kit's tabIndex 0).
    assert tokens.focusPolicy() != app_module.Qt.NoFocus
    QApplication.sendEvent(tokens, QFocusEvent(QEvent.FocusIn))
    assert popup.isVisible() and popup.card.title_label.text() == "Tokens"
    QApplication.sendEvent(tokens, QFocusEvent(QEvent.FocusOut))
    assert not popup.isVisible()
    card.deleteLater()
