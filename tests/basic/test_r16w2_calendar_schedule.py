"""R16.1 (round 16, W2): calendar scheduling in the Assistant.

The Schedule sheet's "When" is the kit's AfScheduleDialog (wording byte for byte
from the vendored ``automation_controls.json`` ``schedule`` block): Repeat ·
Daily · Weekly (state-showing day chips) · Monthly (day 1–31 / last) · Once at… ·
When an email arrives. Clients write ``schedule@2``; Once / Daily / Weekly /
Monthly are worded by the GATEWAY (``POST /automations/schedule-preview`` →
``first_run_sentence``, ``time_zone``) and every next run is SERVED
(``next_run_at``, ``next_run_local``, ``schedule_rule_text``) — the Assistant
computes none of it. Headless Qt over the HTTP stub gateway of test_automations.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

from test_automations import AUTOMATIONS_PATH, MORNING, _fixture, _qt, palette, stub  # noqa: F401 (fixtures)

from abstractassistant.core import automations as rules
from abstractassistant.core.automations import SCHEDULE_TEXT, ScheduleWhen
from abstractassistant.ui.automations import ScheduleSheet, ServedScheduleLine

PREVIEW_PATH = f"{AUTOMATIONS_PATH}/schedule-preview"
PACKAGE = Path(rules.__file__).resolve().parent.parent


def _sheet(window) -> ScheduleSheet:
    window._poll_automations()
    window._open_schedule_sheet()
    return window._schedule_sheet


# ------------------------------------------------------------ wording parity


@pytest.mark.basic
def test_the_when_wording_is_the_vendored_kit_schedule_block(palette, stub) -> None:  # noqa: F811
    """The parity table: every "When" string the Qt sheet shows IS the kit's JSON."""
    window, _ = palette
    sheet = _sheet(window)
    parity = {
        "legend": [w.text() for w in sheet.form_body.findChildren(type(sheet.preview_label)) if w.text() == SCHEDULE_TEXT["legend"]],
        "kind_every": sheet.kind_buttons["every"].text(),
        "kind_daily": sheet.kind_buttons["daily"].text(),
        "kind_weekly": sheet.kind_buttons["weekly"].text(),
        "kind_monthly": sheet.kind_buttons["monthly"].text(),
        "kind_once": sheet.kind_buttons["once"].text(),
        "day_label": sheet.calendar.day_label.text(),
        "last_day": sheet.calendar.month_day.itemText(31),
        "time_label": sheet.calendar.time_edit.accessibleName(),
        "time_zone_hint": sheet.served_line.tz_label.toolTip(),
        "time_zone_change": sheet.served_line.tz_link.text(),
        "time_zone_change_hint": sheet.served_line.tz_link.toolTip(),
    }
    assert parity.pop("legend") == [SCHEDULE_TEXT["legend"]]
    for key, shown in parity.items():
        assert shown == SCHEDULE_TEXT[key], key
    assert [sheet.calendar.day_chips[d].accessibleName() for d in rules.CALENDAR_DAYS] == [SCHEDULE_TEXT["days"][d] for d in rules.CALENDAR_DAYS]
    assert sheet.kind_buttons["email"].text() == rules.EMAIL_TEXT["trigger_label"]
    assert rules.time_zone_line("Europe/Paris") == "in Europe/Paris (your account's time zone)"
    assert rules.time_zone_line("Europe/Paris", "automation") == "in Europe/Paris (this automation's time zone)"
    assert rules.time_zone_default_label("Europe/Paris") == "Gateway default (Europe/Paris)"
    # No "(UTC)" on the section any more: only Repeat is a UTC interval.
    assert SCHEDULE_TEXT["legend"] == "When"


# ------------------------------------------------------------ sheet states


@pytest.mark.basic
def test_repeat_reads_the_gateways_sentence_without_a_zone_line(palette, stub) -> None:  # noqa: F811
    """Gate finding 2: the Repeat line is the gateway's first_run_sentence too (no
    local sentence); a UTC interval shows no account time-zone line."""
    window, _ = palette
    sheet = _sheet(window)
    assert sheet.kind() == "every"
    assert sheet.served_line.isVisibleTo(sheet) and not sheet.calendar.isVisibleTo(sheet)
    sheet.at_edit.setText("2030-01-01 06:00")
    sheet.served_line.flush()
    sent = stub.calls("POST", PREVIEW_PATH)[-1]["body"]["trigger"]
    assert sent == {"source_id": "schedule", "source_version": 2, "config": {"kind": "every", "every": "8h", "start_at": "2030-01-01T06:00:00Z"}}
    assert sheet.served_line.sentence.text() == sheet.served_line.answer["first_run_sentence"]
    assert not sheet.served_line.tz_host.isVisibleTo(sheet), "a UTC interval: no account time-zone line"
    assert sheet.preview_label.text() == ""
    # Only the email trigger keeps a local line.
    assert not rules.is_served_preview_kind("email") and not rules.shows_account_zone("every")


@pytest.mark.basic
@pytest.mark.parametrize(
    "kind, setup, config",
    [
        ("daily", lambda s: None, {"kind": "daily", "at": "08:00"}),
        ("weekly", lambda s: (s.calendar.day_chips["wed"].setChecked(True), s.calendar.day_chips["fri"].setChecked(True)),
         {"kind": "weekly", "days": ["mon", "wed", "fri"], "at": "08:00"}),
        ("monthly", lambda s: s.calendar.month_day.setCurrentIndex(s.calendar.month_day.findData("last")),
         {"kind": "monthly", "day": "last", "at": "08:00"}),
        ("once", lambda s: s.at_edit.setText("2030-01-01 07:30"), {"kind": "once", "at": "2030-01-01T07:30"}),
    ],
)
def test_served_kinds_show_the_gateways_sentence_and_time_zone_verbatim(palette, stub, kind, setup, config) -> None:  # noqa: F811
    window, _ = palette
    sheet = _sheet(window)
    sheet.set_kind(kind)
    setup(sheet)
    assert sheet.served_line.isVisibleTo(sheet)
    assert sheet.calendar.isVisibleTo(sheet) is (kind != "once")
    assert sheet.calendar.days_host.isVisibleTo(sheet) is (kind == "weekly")
    assert sheet.calendar.month_day.isVisibleTo(sheet) is (kind == "monthly")
    assert sheet.stop_host.isVisibleTo(sheet) is (kind != "once")
    assert sheet.served_line.sentence.text() == SCHEDULE_TEXT["describing"]
    sheet.served_line.flush()
    sent = stub.calls("POST", PREVIEW_PATH)[-1]["body"]
    assert sent == {"trigger": {"source_id": "schedule", "source_version": 2, "config": config}}, "the right trigger, no time_zone (the gateway fills it)"
    answer = sheet.served_line.answer
    assert sheet.served_line.sentence.text() == answer["first_run_sentence"], "verbatim"
    assert "(served)" in sheet.served_line.sentence.text()
    assert sheet.served_line.tz_label.text() == "in Europe/Paris (your account's time zone)"
    assert sheet.served_line.tz_host.isVisibleTo(sheet) and sheet.served_line.tz_link.isVisibleTo(sheet)
    sheet.submit_button.click()
    body = stub.calls("POST", AUTOMATIONS_PATH)[-1]["body"]
    assert body["trigger"] == {"source_id": "schedule", "source_version": 2, "config": config}


@pytest.mark.basic
def test_day_chips_show_their_state_with_a_check_mark(palette, stub) -> None:  # noqa: F811
    window, _ = palette
    sheet = _sheet(window)
    sheet.set_kind("weekly")
    mon, tue = sheet.calendar.day_chips["mon"], sheet.calendar.day_chips["tue"]
    assert mon.isCheckable() and mon.isChecked() and mon.text() == "✓ Mon"
    assert not tue.isChecked() and tue.text() == "Tue"
    tue.click()
    assert tue.isChecked() and tue.text() == "✓ Tue"
    mon.click()
    tue.click()
    assert not any(c.isChecked() for c in sheet.calendar.day_chips.values())
    # No day: the kit's sentence, nothing asked, nothing created.
    calls = len(stub.calls("POST", PREVIEW_PATH))
    sheet.served_line.flush()
    assert sheet.served_line.sentence.text() == SCHEDULE_TEXT["error_days"]
    assert len(stub.calls("POST", PREVIEW_PATH)) == calls
    body, errors = sheet.build_body()
    assert body is None and SCHEDULE_TEXT["error_days"] in errors


@pytest.mark.basic
def test_the_calendar_fields_are_kept_across_kind_switches(palette, stub) -> None:  # noqa: F811
    """As the kit's CalendarRuleState: Weekly → Monthly → Weekly keeps the picked
    days (and the month day / time); an emptied day set stays empty."""
    window, _ = palette
    sheet = _sheet(window)
    sheet.set_kind("weekly")
    sheet.calendar.day_chips["thu"].setChecked(True)
    sheet.set_kind("monthly")
    sheet.calendar.month_day.setCurrentIndex(sheet.calendar.month_day.findData(15))
    sheet.set_kind("weekly")
    assert sheet.when() == ScheduleWhen("weekly", at="08:00", days=("mon", "thu"))
    sheet.set_kind("monthly")
    assert sheet.when() == ScheduleWhen("monthly", at="08:00", day=15)
    sheet.set_kind("weekly")
    for chip in sheet.calendar.day_chips.values():
        chip.setChecked(False)
    sheet.set_kind("daily")
    sheet.set_kind("weekly")
    assert sheet.when().days == (), "an emptied set stays empty"


@pytest.mark.basic
def test_a_refused_preview_shows_the_gateways_own_sentence(palette, stub) -> None:  # noqa: F811
    window, _ = palette
    sheet = _sheet(window)
    sentence = "time_zone 'Mars/Olympus' is not an IANA time zone."
    stub.preview_refusal = (422, {"detail": {"reason_code": "invalid_definition", "message": sentence, "field": "trigger.config.time_zone"}})
    sheet.set_kind("daily")
    sheet.served_line.flush()
    assert sheet.served_line.sentence.text() == sentence
    assert sheet.served_line.sentence.objectName() == "autoViewError"
    assert not sheet.served_line.tz_host.isVisibleTo(sheet)


@pytest.mark.basic
def test_the_latest_preview_wins() -> None:
    _qt()
    line = ServedScheduleLine()
    pending: List[Any] = []
    line.provider = lambda trigger, done: pending.append((trigger, done))
    first = {"source_id": "schedule", "source_version": 2, "config": {"kind": "daily", "at": "08:00"}}
    second = {"source_id": "schedule", "source_version": 2, "config": {"kind": "daily", "at": "09:00"}}
    line.request(first)
    line.flush()
    line.request(second)
    line.flush()
    assert [t for t, _ in pending] == [first, second]
    pending[1][1](True, {"time_zone": "Asia/Tokyo", "first_run_sentence": "Second."})
    pending[0][1](True, {"time_zone": "Europe/Paris", "first_run_sentence": "First (stale)."})
    assert line.sentence.text() == "Second." and line.tz_label.text() == "in Asia/Tokyo (your account's time zone)"
    # Debounced: nothing is sent until the timer (or flush) fires.
    line.request(first)
    assert len(pending) == 2


@pytest.mark.basic
def test_a_line_without_a_provider_fails_loudly() -> None:
    _qt()
    line = ServedScheduleLine()
    line.request({"source_id": "schedule", "source_version": 2, "config": {"kind": "daily", "at": "08:00"}})
    with pytest.raises(RuntimeError, match="schedule-preview provider"):
        line.flush()


@pytest.mark.basic
def test_change_in_preferences_opens_settings_workflow(palette, stub, monkeypatch) -> None:  # noqa: F811
    window, _ = palette
    opened: List[str] = []
    monkeypatch.setattr(window, "_open_settings", lambda section="": opened.append(section))
    sheet = _sheet(window)
    sheet.set_kind("daily")
    sheet.served_line.flush()
    sheet.served_line.tz_link.click()
    assert opened == ["workflow"]


# ------------------------------------------------------------ the edit form


@pytest.mark.basic
def test_the_edit_form_edits_a_calendar_rule_and_keeps_its_time_zone(palette, stub) -> None:  # noqa: F811
    window, _ = palette
    window._poll_automations()
    window._open_automation(MORNING)
    view = window.automation_view
    view.control_buttons["revise"].click()
    assert view.edit_calendar_host.isVisibleTo(view) and not view.edit_every.isVisibleTo(view)
    assert view.edit_calendar_kind.currentData() == "daily" and view.edit_calendar.time_edit.time().toString("HH:mm") == "08:00"
    view.edit_served.flush()
    assert view.edit_served.tz_label.text() == "in Europe/Paris (this automation's time zone)"
    assert not view.edit_served.tz_link.isVisibleTo(view), "an existing automation's zone is its own: no preferences link"
    view.edit_calendar_kind.setCurrentIndex(view.edit_calendar_kind.findData("weekly"))
    view.edit_calendar.day_chips["sat"].setChecked(True)
    view.edit_served.flush()
    preview = stub.calls("POST", PREVIEW_PATH)[-1]["body"]["trigger"]
    assert preview["config"] == {"kind": "weekly", "days": ["mon", "sat"], "at": "08:00", "time_zone": "Europe/Paris"}
    view.edit_save.click()
    patch = stub.calls("PATCH")[-1]["body"]["changes"]
    assert patch["trigger"] == {"source_id": "schedule", "source_version": 2, "config": {"kind": "weekly", "days": ["mon", "sat"], "at": "08:00", "time_zone": "Europe/Paris"}}


@pytest.mark.basic
def test_a_revised_rule_keeps_the_bindings_zone_and_limits_not_start_at() -> None:
    summary = next(s for s in _fixture("list.json")["items"] if s["automation_id"] == MORNING)
    summary["trigger"]["config"].update({"count": 10, "until": "2027-01-01T00:00:00+00:00"})
    changes, errors = rules.revise_changes(summary, title=summary["title"], every=None, context=summary["context_mode"],
                                           calendar=ScheduleWhen("weekly", at="08:00", days=("tue",)))
    assert errors == [] and changes["trigger"]["config"] == {
        "kind": "weekly", "days": ["tue"], "at": "08:00", "time_zone": "Europe/Paris", "count": 10, "until": "2027-01-01T00:00:00+00:00",
    }


@pytest.mark.basic
def test_every_schedule_row_reads_the_served_rule_verbatim() -> None:
    """Gate finding 2: schedule@1 and @2, Repeat with bounds included — the gateway's words only."""
    row = {"source_id": "schedule", "source_version": 2, "config": {"kind": "every", "every": "8h", "count": 3, "time_zone": "Europe/Paris"}}
    assert rules.trigger_summary(row, {"schedule_rule_text": "Every 8 hours (UTC) · 3 runs max"}) == "Every 8 hours (UTC) · 3 runs max"
    v1 = {"source_id": "schedule", "source_version": 1, "config": {"every": "24h"}}
    assert rules.trigger_summary(v1, {"schedule_rule_text": "Every 24 hours (UTC)"}) == "Every 24 hours (UTC)"
    assert rules.trigger_summary(v1, {}) == "schedule@1"
    assert not hasattr(rules, "schedule_label"), "no local schedule sentence remains"
    daily = {"source_id": "schedule", "source_version": 2, "config": {"kind": "daily", "at": "08:00"}}
    assert rules.trigger_summary(daily, {"schedule_rule_text": "Every day at 08:00 (Europe/Paris)"}) == "Every day at 08:00 (Europe/Paris)"
    assert rules.trigger_summary(daily, {}) == "schedule@2", "a missing served text never becomes a made-up sentence"


@pytest.mark.basic
def test_revise_changes_reads_calendar_rules_structurally() -> None:
    summary = next(s for s in _fixture("list.json")["items"] if s["automation_id"] == MORNING)
    same = rules.calendar_when_from(summary["trigger"]["config"])
    assert same == ScheduleWhen("daily", at="08:00")
    assert rules.revise_changes(summary, title=summary["title"], every=None, context=summary["context_mode"], calendar=same) == (None, [])
    changes, errors = rules.revise_changes(summary, title=summary["title"], every=None, context=summary["context_mode"],
                                           calendar=ScheduleWhen("monthly", at="06:15", day=31))
    assert errors == [] and changes["trigger"]["config"] == {"kind": "monthly", "day": 31, "at": "06:15", "time_zone": "Europe/Paris"}
    _, errors = rules.revise_changes(summary, title=summary["title"], every=None, context=summary["context_mode"],
                                     calendar=ScheduleWhen("monthly", at="25:00", day=0))
    assert errors == [SCHEDULE_TEXT["error_at"], SCHEDULE_TEXT["error_day"]]


# ------------------------------------------------------- served display only


@pytest.mark.basic
def test_the_header_card_and_hint_show_the_served_next_run(palette, stub) -> None:  # noqa: F811
    window, _ = palette
    window._poll_automations()
    window._open_automation(MORNING)
    view = window.automation_view
    meta = view.meta_label.text()
    assert meta.startswith("Every day at 08:00 (Europe/Paris) · Active")
    assert "next 2026-09-28 08:00 Europe/Paris" in meta
    assert "Next scheduled run: 2026-09-28 08:00 Europe/Paris." in view.control_buttons["run_now"].toolTip()
    # A mutant gateway value moves every display: the client computes nothing.
    moved = dict(stub.summary(MORNING), next_run_at="2026-09-29T06:00:00+00:00", next_run_local="2026-09-29T08:00:00+02:00",
                 schedule_rule_text="Every day at 08:00 (Europe/Paris) [moved]")
    view.set_summary(moved)
    assert view.meta_label.text().startswith("Every day at 08:00 (Europe/Paris) [moved]")
    assert "next 2026-09-29 08:00 Europe/Paris" in view.meta_label.text()
    assert "Next scheduled run: 2026-09-29 08:00 Europe/Paris." in view.control_buttons["run_now"].toolTip()


@pytest.mark.basic
def test_formatting_the_served_local_time_is_a_cut_not_a_conversion() -> None:
    # The offset is NOT applied: the wall time is the gateway's, already in the zone.
    assert rules.format_served_local("2026-03-29T03:30:00+02:00", "Europe/Paris") == "2026-03-29 03:30 Europe/Paris"
    assert rules.format_served_local("2026-11-01T01:30:00-08:00", "America/Los_Angeles") == "2026-11-01 01:30 America/Los_Angeles"
    assert rules.format_served_local(None, "UTC") == ""


@pytest.mark.basic
def test_no_client_side_next_run_arithmetic_remains() -> None:
    """Grep-proof (A4): the next run is read from `next_run_at` / `next_run_local`
    only; no client file reads `next_fire_at` or adds a timedelta to a schedule —
    except `served_summary`, the ONE fallback for a gateway before round 16 that
    serves only `next_fire_at` (the served UTC string, copied, never computed)."""
    sources = [PACKAGE / "core" / "automations.py", PACKAGE / "ui" / "automations.py", PACKAGE / "ui" / "session_switcher.py"]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
        if path.parent.name == "core":
            head, rest = code.split("\ndef served_summary(", 1)
            fallback, tail = rest.split("\ndef ", 1)
            assert 'summary.get("next_fire_at")' in fallback
            code = head + "\ndef " + tail
        assert '"next_fire_at"' not in code and "'next_fire_at'" not in code, path.name
        assert not re.search(r"timedelta\(", code), path.name
        assert "zoneinfo" not in code and "ZoneInfo" not in code, path.name


# ------------------------------------------------------- Settings: time zone


class _TzController:
    def __init__(self) -> None:
        self.block: Dict[str, Any] = {
            "value": None, "gateway_default": "Europe/Paris", "effective": "Europe/Paris", "label": "Time zone",
            "help": "Daily, weekly and monthly automations run at their wall-clock time in this zone.",
            "choices": ["America/Los_Angeles", "Asia/Tokyo", "Europe/Paris", "UTC"],
        }
        self.puts: List[Any] = []
        self.refuse = ""

    def account_time_zone(self):
        return dict(self.block)

    def set_time_zone(self, value):
        self.puts.append(value)
        if self.refuse:
            from abstractassistant.gateway.client import GatewayHttpError

            raise GatewayHttpError("refused", status=400, body_text='{"detail": {"reason": "preference_refused", "message": "%s"}}' % self.refuse)
        self.block = dict(self.block, value=value, effective=value or self.block["gateway_default"])
        return dict(self.block)


@pytest.mark.basic
def test_settings_workflow_page_sets_the_account_time_zone() -> None:
    from test_settings_pages import _dialog

    dlg, ctl = _dialog()
    tz = _TzController()
    ctl.account_time_zone = tz.account_time_zone
    ctl.set_time_zone = tz.set_time_zone
    page = dlg.page_workflow
    page._refresh_time_zone()
    combo = page.time_zone_combo
    assert page.time_zone_card.isVisibleTo(dlg) or not dlg.isVisible()
    assert [combo.itemText(i) for i in range(combo.count())] == ["Gateway default (Europe/Paris)", "America/Los_Angeles", "Asia/Tokyo", "Europe/Paris", "UTC"]
    assert combo.itemData(0) is None and combo.currentIndex() == 0
    assert page.time_zone_help.text() == tz.block["help"] and combo.isEditable()
    page._on_time_zone_chosen(combo.findText("Asia/Tokyo"))
    assert tz.puts == ["Asia/Tokyo"] and page.feedback.text() == "Saved."
    assert combo.currentText() == "Asia/Tokyo"
    page._on_time_zone_chosen(0)
    assert tz.puts == ["Asia/Tokyo", None], "Gateway default stores null"
    tz.refuse = "time_zone 'UTC' refused: not allowed here."
    page._on_time_zone_chosen(combo.findText("UTC"))
    assert page.feedback.text() == "Not saved. time_zone 'UTC' refused: not allowed here."
    assert combo.currentIndex() == 0, "the stored value stays selected"
    dlg.close()


@pytest.mark.basic
def test_settings_says_loudly_when_the_gateway_serves_no_time_zone() -> None:
    """Gate finding 1: the time_zone block is REQUIRED — never a hidden row; the
    card stays with the state sentence and a disabled list."""
    from test_settings_pages import _dialog
    from abstractassistant.ui.settings.pages import TIME_ZONE_NOT_SERVED

    dlg, ctl = _dialog()
    ctl.account_time_zone = lambda: None
    page = dlg.page_workflow
    page._refresh_time_zone()
    assert TIME_ZONE_NOT_SERVED == "This gateway did not serve a time zone (needs gateway ≥ the round-16 build)."
    assert page.time_zone_block is None
    assert page.time_zone_card.isVisibleTo(page) and page.time_zone_help.isVisibleTo(page)
    assert page.time_zone_help.text() == TIME_ZONE_NOT_SERVED
    assert not page.time_zone_combo.isEnabled() and page.time_zone_combo.count() == 0
    dlg.close()


@pytest.mark.basic
def test_the_absence_sentence_reads_loud_in_the_error_colour() -> None:
    """The Time zone card's absence sentence carries the error tone, and Settings'
    stylesheet colours that tone with the theme's error colour (light and dark)."""
    from test_settings_pages import _dialog
    from abstractassistant import theme as theme_mod
    from abstractassistant.ui.settings.dialog import build_settings_qss
    from abstractassistant.ui_themes import build_theme

    dlg, ctl = _dialog()
    ctl.account_time_zone = lambda: None
    page = dlg.page_workflow
    page._refresh_time_zone()
    assert page.time_zone_help.property("tone") == "error"
    import copy

    saved = copy.deepcopy(theme_mod.THEME)
    for mode in ("light", "dark"):
        theme_mod.activate(build_theme(mode))
        qss = build_settings_qss()
        rule = re.search(r'QLabel#rowHelp\[tone="error"\]\s*\{([^}]*)\}', qss)
        assert rule and f"color: {theme_mod.THEME.danger_text}" in rule.group(1), mode
    theme_mod.activate(saved)
    dlg.close()


@pytest.mark.basic
def test_the_card_schedule_chip_shows_the_served_rule_whole() -> None:
    """No truncation of served text: the schedule chip's label wraps (never elided)."""
    _qt()
    from PyQt5.QtWidgets import QLabel
    from abstractassistant.ui import session_switcher as switcher_module

    long_rule = "Every Mon, Tue, Wed, Thu and Fri at 07:30 (America/Los_Angeles) · 12 runs max · until 2027-01-01"
    summary = dict(next(s for s in _fixture("list.json")["items"] if s["automation_id"] == MORNING), schedule_rule_text=long_rule)
    row = switcher_module.AutomationTabRow(summary)
    row.resize(380, 200)
    row.show()
    _qt().processEvents()
    label = next(w for w in row.schedule_chip.findChildren(QLabel) if w.objectName() == "rowMetric")
    assert label.text() == long_rule, "verbatim, never cut"
    assert label.wordWrap(), "wraps onto a second line instead of eliding"
    assert label.height() > label.fontMetrics().height() * 1.5, "it actually took a second line at a narrow width"
    row.close()
