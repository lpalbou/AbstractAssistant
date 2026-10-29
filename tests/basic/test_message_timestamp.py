"""The desktop's message stamp says what the kit's says (panel-chat formatMessageStamp)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from abstractassistant.app import _format_message_timestamp as stamp


def _local(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi).astimezone()


NOW = _local(2026, 10, 28, 15, 0)


@pytest.mark.basic
def test_today_is_the_time_only() -> None:
    assert stamp(_local(2026, 10, 28, 0, 46).isoformat(), NOW) == "12:46 AM"


@pytest.mark.basic
def test_yesterday_has_the_kits_separator() -> None:
    assert stamp(_local(2026, 10, 27, 22, 52).isoformat(), NOW) == "Yesterday · 10:52 PM"


@pytest.mark.basic
def test_earlier_this_year_has_no_zero_padded_day() -> None:
    assert stamp(_local(2026, 10, 1, 22, 52).isoformat(), NOW) == "Oct 1 · 10:52 PM"
    assert stamp(_local(2026, 10, 21, 22, 52).isoformat(), NOW) == "Oct 21 · 10:52 PM"


@pytest.mark.basic
def test_another_year_adds_the_year() -> None:
    assert stamp(_local(2025, 10, 21, 22, 52).isoformat(), NOW) == "Oct 21, 2025 · 10:52 PM"


@pytest.mark.basic
def test_a_bad_timestamp_is_never_shown_raw() -> None:
    for raw in ("not a date", "2026-13-45T99:00", "{'ts': 1}"):
        assert stamp(raw, NOW) == ""


@pytest.mark.basic
def test_a_bare_date_is_that_local_day_without_a_time_and_utc_converts_to_local() -> None:
    assert stamp("2026-10-27", NOW) == "Yesterday"
    assert stamp("2026-10-28", NOW) == "Today"
    assert stamp("2026-03-02", NOW) == "Mar 2"
    utc = (_local(2026, 10, 27, 22, 52)).astimezone(tz=None).astimezone(__import__("datetime").timezone.utc)
    assert stamp(utc.isoformat().replace("+00:00", "Z"), NOW) == "Yesterday · 10:52 PM"


@pytest.mark.basic
def test_a_future_day_uses_the_dated_form() -> None:
    assert stamp((NOW + timedelta(days=2)).isoformat(), NOW) == "Oct 30 · 03:00 PM"
