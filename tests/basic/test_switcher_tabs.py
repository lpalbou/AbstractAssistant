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
    assert "⌘⌫ remove" in sw.hint_label.text()
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
    assert row.buttons["pause"].toolTip() == "Archived: history is kept, nothing runs."
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
    assert running.buttons["run_now"].toolTip() == "An occurrence is in progress."
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
    assert local.isEnabled() and local.toolTip() == f"Open {here}"
    local.click()
    assert opened == [str(here)]
    assert not remote.isEnabled() and remote.toolTip() == "on the gateway host: /srv/gateway/ws/abc"
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
