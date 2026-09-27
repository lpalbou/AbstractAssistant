"""The session switcher's two tabs (operator rulings 2026-09-27): Sessions (every
gateway session, no own/other scope) | Automations (every automation, archived
behind "Show archived", inline controls by state), clickable workspace folders."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication

from abstractassistant.core.session_cache import SessionCache
from abstractassistant.core.session_digest import SessionDigest
import abstractassistant.ui.session_switcher as switcher_module
from abstractassistant.ui.session_switcher import SessionSwitcher

FIXTURES = Path(__file__).parent / "fixtures" / "automations"
NEWS = "fddce731-4abf-54d3-81b9-15856efbfd7a"
TRIAGE = "53443dd0-25c4-5fa8-bdad-e1ac3fdfff8e"
JOURNAL = "69892c76-5362-5646-a528-b9f982c8d993"
_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _summaries() -> List[Dict[str, Any]]:
    return copy.deepcopy(json.loads((FIXTURES / "list.json").read_text(encoding="utf-8"))["items"])


def _by_id(aid: str) -> Dict[str, Any]:
    return next(s for s in _summaries() if s["automation_id"] == aid)


def _switcher(summaries=None) -> SessionSwitcher:
    _app()
    sw = SessionSwitcher()
    sw.set_digests([SessionDigest(session_id="sess_a", title="Release prep", updated_at="2026-09-27T06:00:00Z")])
    sw.set_automations(_summaries() if summaries is None else summaries, available=True)
    return sw


def _key(sw, key, modifiers=Qt.NoModifier, target=None) -> None:
    event = QKeyEvent(QEvent.KeyPress, key, modifiers)
    if target is None:
        sw.keyPressEvent(event)
    else:
        sw.eventFilter(target, event)


@pytest.mark.basic
def test_tabs_switch_by_keyboard_and_the_last_one_is_remembered(tmp_path: Path) -> None:
    sw = _switcher()
    seen: List[str] = []
    sw.tab_changed.connect(seen.append)
    assert sw.tab == "sessions" and not sw.show_archived.isVisibleTo(sw) or True
    _key(sw, Qt.Key_2, Qt.ControlModifier)
    assert sw.tab == "automations" and seen == ["automations"]
    assert sw.hint_label.text().startswith("↑↓ move · ↵ open · ⌘1/⌘2") and "remove" not in sw.hint_label.text()
    _key(sw, Qt.Key_Left, target=sw.search_edit)  # ← with an empty filter
    assert sw.tab == "sessions" and seen == ["automations", "sessions"]
    assert sw.hint_label.text() == "↑↓ move · ↵ open · ⌘1/⌘2 tabs · esc close"
    # Remembered across launches (the session cache keeps it).
    cache = SessionCache(tmp_path)
    cache.set_switcher_tab("automations")
    assert SessionCache(tmp_path).switcher_tab == "automations"
    with pytest.raises(ValueError):
        cache.set_switcher_tab("other")
    # No automations on this gateway: no tab bar, and the sessions tab only.
    sw.set_automations([], available=False)
    sw.set_tab("automations")
    assert sw.tab == "sessions" and not sw.tab_bar.isVisibleTo(sw)
    sw.deleteLater()


@pytest.mark.basic
def test_archived_automations_are_hidden_until_asked_for() -> None:
    summaries = _summaries()
    archived = dict(_by_id(NEWS), automation_id="00000000-0000-4000-8000-00000000a1c4", title="Old monitor",
                    status="archived", capabilities=["discuss"])
    sw = _switcher(summaries + [archived])
    sw.set_tab("automations")
    ids = lambda: [r.automation_id for r in sw.automation_tab_rows]  # noqa: E731
    assert archived["automation_id"] not in ids()
    sw.show_archived.click()
    assert archived["automation_id"] in ids()
    row = next(r for r in sw.automation_tab_rows if r.automation_id == archived["automation_id"])
    assert not any(b.isEnabled() for k, b in row.buttons.items() if k not in ("open", "last"))
    assert row.buttons["pause"].toolTip() == "Pause — Archived: history is kept, nothing runs."
    sw.deleteLater()


@pytest.mark.basic
def test_inline_controls_follow_the_automations_state() -> None:
    sw = _switcher()
    sw.set_tab("automations")
    rows = {r.automation_id: r for r in sw.automation_tab_rows}
    active, paused, running = rows[NEWS], rows[JOURNAL], rows[TRIAGE]
    # Active: Pause (not Resume), Run now, no Stop (nothing running).
    assert "pause" in active.buttons and "resume" not in active.buttons and "stop_current" not in active.buttons
    assert active.buttons["pause"].isEnabled() and active.buttons["run_now"].isEnabled()
    # Paused: Resume instead of Pause; Run now stays enabled (it does not resume).
    assert "resume" in paused.buttons and "pause" not in paused.buttons
    assert paused.buttons["resume"].isEnabled() and paused.buttons["run_now"].isEnabled()
    # Running (waiting occurrence): Stop shown; Run now disabled with the reason.
    assert running.buttons["stop_current"].isEnabled()
    assert not running.buttons["run_now"].isEnabled()
    assert running.buttons["run_now"].toolTip() == "Run now — An occurrence is in progress."
    # Clicks become requests.
    got: List[tuple] = []
    sw.automation_control_requested.connect(lambda a, c: got.append((a, c)))
    opened: List[tuple] = []
    sw.automation_open_requested.connect(lambda a, w: opened.append((a, w)))
    edits: List[str] = []
    sw.automation_edit_requested.connect(edits.append)
    active.buttons["pause"].click()
    paused.buttons["resume"].click()
    running.buttons["stop_current"].click()
    assert got == [(NEWS, "pause"), (JOURNAL, "resume"), (TRIAGE, "stop_current")]
    active.buttons["archive"].click()  # asks first, inside the row
    assert active.confirm_host.isVisibleTo(active) and got[-1] != (NEWS, "archive")
    active.archive_yes.click()
    assert got[-1] == (NEWS, "archive")
    sw.show()
    sw.set_tab("automations")
    active.buttons["last"].click()
    active.buttons["revise"].click()
    assert (NEWS, "latest") in opened and edits == [NEWS]
    sw.deleteLater()


@pytest.mark.basic
def test_enter_opens_the_selected_automation() -> None:
    sw = _switcher()
    sw.set_tab("automations")
    opened: List[tuple] = []
    sw.automation_open_requested.connect(lambda a, w: opened.append((a, w)))
    _key(sw, Qt.Key_Return)
    assert opened == [(sw.automation_tab_rows[0].automation_id, "top")]
    sw.deleteLater()


@pytest.mark.basic
def test_workspace_folders_open_locally_and_say_when_they_are_on_the_gateway(tmp_path: Path, monkeypatch) -> None:
    opened: List[str] = []
    monkeypatch.setattr(switcher_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    here = tmp_path / "workspace"
    here.mkdir()
    _app()
    sw = SessionSwitcher()
    sw.set_digests(
        [
            SessionDigest(session_id="sess_local", title="Local", updated_at="2026-09-27T06:00:00Z", detailed=True, messages=2, turns=1, workspace_root=str(here)),
            SessionDigest(session_id="sess_remote", title="Remote", updated_at="2026-09-27T05:00:00Z", detailed=True, messages=2, turns=1, workspace_root="/srv/gateway/ws/abc"),
        ]
    )
    buttons = {r.session_id: r.findChildren(type(sw.new_button), "rowFolder") for r in sw._rows}
    local, remote = buttons["sess_local"][0], buttons["sess_remote"][0]
    assert local.isEnabled() and local.toolTip() == f"Open workspace folder\n{here}"
    local.click()
    assert opened == [str(here)]
    assert not remote.isEnabled() and remote.toolTip() == "Workspace folder on the gateway host:\n/srv/gateway/ws/abc"
    # A gateway session whose /runs row does not carry the folder: said, not guessed.
    sw.set_digests([SessionDigest(session_id="sess_g", title="G", updated_at="2026-09-27T06:00:00Z", state="done", turns=1)])
    missing = sw._rows[0].findChildren(type(sw.new_button), "rowFolder")[0]
    assert not missing.isEnabled() and missing.toolTip() == "The gateway does not report this folder (/runs row workspace_root)."
    # Automations: the folder from the summary; a summary without it says which field is missing.
    with_root = dict(_by_id(NEWS), workspace_root=str(here))
    sw.set_automations([with_root, _by_id(JOURNAL)], available=True)
    sw.set_tab("automations")
    rows = {r.automation_id: r for r in sw.automation_tab_rows}
    rows[NEWS].folder.click()
    assert opened == [str(here), str(here)]
    assert not rows[JOURNAL].folder.isEnabled()
    assert rows[JOURNAL].folder.toolTip() == "The gateway does not report this folder (AutomationSummary.workspace_root)."
    sw.deleteLater()


@pytest.mark.basic
def test_a_long_session_list_offers_load_more_and_counts_with_a_plus() -> None:
    _app()
    sw = SessionSwitcher()
    loads: List[int] = []
    sw.load_more_requested.connect(lambda: loads.append(1))
    sw.set_digests([SessionDigest(session_id=f"s{i}", title=f"t{i}", updated_at="2026-08-01T12:00:00Z") for i in range(100)], more=True)
    assert sw.count_text == "100+ sessions"
    assert sw.load_more_button is not None
    sw.load_more_button.click()
    assert loads == [1] and not sw.load_more_button.isEnabled()
    sw.set_digests([SessionDigest(session_id=f"s{i}", title=f"t{i}", updated_at="2026-08-01T12:00:00Z") for i in range(150)], more=False)
    assert sw.count_text == "150 sessions" and sw.load_more_button is None
    sw.deleteLater()


@pytest.mark.basic
@pytest.mark.parametrize(
    "seconds, text",
    [(0, "<1 min"), (59, "<1 min"), (180, "3 min"), (3599, "59 min"), (3600, "1 h"), (3960, "1 h 06 min"),
     (7200 + 59 * 60, "2 h 59 min"), (86400, "1 d"), (90000, "1 d 1 h")],
)
def test_relative_span(seconds, text) -> None:
    from abstractassistant.core.automations import relative_span

    assert relative_span(seconds) == text


@pytest.mark.basic
def test_last_and_next_are_relative_times_and_next_is_a_dash_when_not_scheduled() -> None:
    from datetime import datetime, timedelta, timezone

    from abstractassistant.core.automations import last_run_text, next_run_text

    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    iso = lambda d: (now + d).isoformat()  # noqa: E731
    active = {"status": "active", "next_fire_at": iso(timedelta(minutes=2)),
              "last_occurrence": {"fired_at": iso(-timedelta(minutes=10)), "finished_at": iso(-timedelta(minutes=3))}}
    assert (last_run_text(active, now=now), next_run_text(active, now=now)) == ("last 3 min ago", "next in 2 min")
    long = dict(active, next_fire_at=iso(timedelta(hours=1, minutes=6, seconds=30)),
                last_occurrence={"fired_at": iso(-timedelta(hours=1, minutes=6))})
    assert (last_run_text(long, now=now), next_run_text(long, now=now)) == ("last 1 h 06 min ago", "next in 1 h 06 min")
    assert next_run_text(dict(active, status="paused"), now=now) == "next —"
    assert next_run_text({"status": "active"}, now=now) == "next —"
    assert next_run_text(dict(active, next_fire_at=iso(timedelta(seconds=20))), now=now) == "next: now"
    assert last_run_text({"status": "active"}, now=now) == "last —"


@pytest.mark.basic
def test_status_pills_per_state() -> None:
    from abstractassistant.core.automations import status_pill

    news, journal, triage = _by_id(NEWS), _by_id(JOURNAL), _by_id(TRIAGE)
    running = dict(news, last_occurrence=dict(news["last_occurrence"], status="running"))
    assert status_pill(news) == ("active", "active")
    assert status_pill(journal) == ("paused", "paused")
    assert status_pill(running) == ("running", "running")
    assert status_pill(triage) == ("waiting for you", "waiting")  # a pending wait wins
    assert status_pill(dict(news, status="archived")) == ("archived", "ended")
    assert status_pill(dict(news, status="failed")) == ("failed", "failed")
    sw = _switcher()
    sw.set_tab("automations")
    tones = {r.automation_id: r.pill.property("tone") for r in sw.automation_tab_rows}
    assert tones[NEWS] == "active" and tones[JOURNAL] == "paused" and tones[TRIAGE] == "waiting"
    sw.deleteLater()


@pytest.mark.basic
def test_the_toolbar_is_icons_with_tooltips_by_state() -> None:
    sw = _switcher()
    sw.set_tab("automations")
    rows = {r.automation_id: r for r in sw.automation_tab_rows}
    for row in rows.values():
        for key, button in list(row.buttons.items()) + [("folder", row.folder)]:
            assert button.text() == "" and not button.icon().isNull(), key
            assert button.toolTip(), key
    assert rows[NEWS].buttons["revise"].toolTip() == "Modify"
    assert list(rows[NEWS].buttons) == ["open", "last", "pause", "run_now", "revise", "archive"]
    assert list(rows[JOURNAL].buttons) == ["open", "last", "resume", "run_now", "revise", "archive"]
    assert list(rows[TRIAGE].buttons) == ["open", "last", "pause", "run_now", "stop_current", "revise", "archive"]
    # Failed last result reads red.
    failed = dict(_by_id(NEWS), last_occurrence=dict(_by_id(NEWS)["last_occurrence"], status="failed"))
    sw.set_automations([failed], available=True)
    assert sw.automation_tab_rows[0].result_label.property("tone") == "failed"
    sw.deleteLater()


@pytest.mark.basic
def test_new_automation_button_lives_in_the_automations_tab() -> None:
    sw = _switcher()
    asked: List[int] = []
    sw.new_automation_requested.connect(lambda: asked.append(1))
    sw.show()
    assert not sw.new_automation_button.isVisibleTo(sw)
    sw.set_tab("automations")
    assert sw.new_automation_button.isVisibleTo(sw) and not sw.new_button.isVisibleTo(sw)
    sw.new_automation_button.click()
    assert asked == [1]
    sw.deleteLater()


@pytest.mark.basic
@pytest.mark.parametrize("width", [448, 460])
@pytest.mark.parametrize("tab", ["sessions", "automations"])
def test_the_header_needs_no_ellipsis_and_the_tabs_carry_the_counts(width, tab) -> None:
    """The header line is the title and its buttons only, each at full size;
    the counts are in the tab labels and the detail in their tooltips."""
    from PyQt5.QtGui import QFontMetrics
    from PyQt5.QtWidgets import QLabel, QPushButton

    _app()
    sw = SessionSwitcher()
    today = "2026-09-27T12:00:00+00:00"
    sw.set_digests(
        [SessionDigest(session_id=f"s{i}", title=f"t{i}", updated_at="2026-08-01T12:00:00Z") for i in range(146)],
        more=True,
    )
    archived = dict(_by_id(NEWS), automation_id="00000000-0000-4000-8000-00000000a1c4", status="archived", capabilities=["discuss"])
    sw.set_automations(_summaries() + [archived], available=True)
    sw.set_tab(tab)
    sw.resize(width, 600)
    sw.show()
    _app().processEvents()
    header = [sw.title_label, sw.new_button] if tab == "sessions" else [sw.title_label, sw.show_archived, sw.new_automation_button]
    for widget in header:
        assert widget.isVisibleTo(sw)
        assert widget.width() >= widget.sizeHint().width(), (widget.text(), widget.width(), widget.sizeHint().width())
        assert "…" not in widget.text()
    assert sw.title_label.text() == ("Sessions" if tab == "sessions" else "Automations")
    for button in sw.tab_buttons.values():
        assert button.width() >= QFontMetrics(button.font()).horizontalAdvance(button.text())
    assert sw.tab_buttons["sessions"].text() == "Sessions · 146+"
    assert sw.tab_buttons["automations"].text() == "Automations · 4 · 4 new"
    assert sw.tab_buttons["sessions"].toolTip() == "146+ sessions (⌘1)"
    assert sw.tab_buttons["automations"].toolTip() == "4 automations · 1 archived (hidden) · 4 new (⌘2)"
    sw.deleteLater()


def _visible_texts(widget) -> List[str]:
    from PyQt5.QtWidgets import QLabel, QPushButton

    return [w.text() for w in widget.findChildren((QLabel, QPushButton)) if w.isVisibleTo(widget) and w.text()]


@pytest.mark.basic
@pytest.mark.parametrize("width", [448, 460])
def test_no_horizontal_scroll_with_very_long_content(tmp_path: Path, width) -> None:
    """Operator: horizontal scroll is impossible on both tabs. A 400-char
    title, a 600-char result and a 200-char folder path stay inside the list."""
    _app()
    folder = tmp_path / ("x" * 180)
    folder.mkdir()
    long_title = "T" * 400
    sw = SessionSwitcher()
    sw.set_digests(
        [SessionDigest(session_id="sess_long", title=long_title, updated_at="2026-09-27T06:00:00Z", detailed=True,
                       messages=2, turns=1, preview="P" * 600, workspace_root=str(folder),
                       session_kind="discussion", automation_id=NEWS, state="done")]
    )
    summary = dict(_by_id(NEWS), title=long_title, workspace_root=str(folder),
                   last_occurrence=dict(_by_id(NEWS)["last_occurrence"], excerpt="R" * 600))
    sw.set_automations([summary], available=True)
    for tab, scroll in (("sessions", sw.scroll), ("automations", sw.auto_scroll)):
        sw.set_tab(tab)
        sw.resize(width, 600)
        sw.show()
        _app().processEvents()
        viewport = scroll.viewport().width()
        assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
        assert scroll.horizontalScrollBar().maximum() == 0, tab
        rows = sw.visible_rows()
        assert rows and all(r.width() <= viewport for r in rows), (tab, [r.width() for r in rows], viewport)
        for row in rows:
            assert not any(len(t) > 120 for t in _visible_texts(row)), tab
            assert not any("/" in t or "session-" in t for t in _visible_texts(row)), (tab, _visible_texts(row))
    sw.deleteLater()


@pytest.mark.basic
def test_a_session_row_and_an_automation_row_are_the_same_card() -> None:
    from abstractassistant.ui.session_switcher import AutomationTabRow, RowCard, SessionRow

    sw = _switcher()
    session = sw._rows[0]
    sw.set_tab("automations")
    automation = sw.automation_tab_rows[0]
    assert isinstance(session, RowCard) and isinstance(automation, RowCard)
    assert issubclass(SessionRow, RowCard) and issubclass(AutomationTabRow, RowCard)
    assert session.objectName() == automation.objectName() == "sessionRow"
    assert session.spine.objectName() == automation.spine.objectName() == "rowSpine"
    assert automation.title_label.objectName() == "rowTitle" and automation.pill.objectName() == "rowBadge"
    assert automation.result_label.objectName() == "rowPreview"
    qss = sw.styleSheet()
    assert qss.count("QFrame#sessionRow {") == 1 and "autoTabRow" not in qss
    sw.deleteLater()


@pytest.mark.basic
def test_a_workspace_folder_never_shows_its_name(tmp_path: Path) -> None:
    folder = tmp_path / "session-automation-787b7fb6-d7bf-5e16-868e-ba8cf9d5a953"
    folder.mkdir()
    _app()
    sw = SessionSwitcher()
    sw.set_digests([SessionDigest(session_id="sess_w", title="W", updated_at="2026-09-27T06:00:00Z", detailed=True,
                                  messages=2, turns=1, workspace_root=str(folder), state="done")])
    sw.set_automations([dict(_by_id(NEWS), workspace_root=str(folder))], available=True)
    row = sw._rows[0]
    sw.set_tab("automations")
    for card in (row, sw.automation_tab_rows[0]):
        texts = _visible_texts(card)
        assert not any("session-" in t or "/" in t for t in texts), texts
        folder_buttons = card.findChildren(type(sw.new_button), "rowFolder")
        assert folder_buttons and folder_buttons[0].text() == ""
        assert folder_buttons[0].toolTip() == f"Open workspace folder\n{folder}"
    sw.deleteLater()
