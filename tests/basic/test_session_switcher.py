"""The chat switcher: digests (gateway rows + cached transcripts), and the popup itself."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from abstractassistant.core.session_digest import (
    SessionDigest,
    SessionDigestCache,
    digest_from_record,
    digest_from_snapshot,
    format_count,
    format_duration_ms,
    format_tokens,
    recency_group,
    relative_time,
    session_matches_query,
    sort_digests,
    workspace_label,
)
from abstractassistant.core.gateway_sessions import GatewaySession
from abstractassistant.core.session_cache import SessionCache
from abstractassistant.ui.session_switcher import SessionRow, SessionSwitcher

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


_APP = None


def _app() -> QApplication:
    # The QApplication must outlive the test: a collected one aborts Qt.
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _snapshot() -> dict:
    return {
        "session_id": "sess_1",
        "workspace_root": "/Users/x/proj",
        "last_run_id": "run-9",
        "messages": [
            {"role": "user", "content": "Summarize the release notes", "ts": "2026-09-06T10:00:00+00:00"},
            {
                "role": "tool",
                "content": "",
                "metadata": {"name": "read_file", "success": True},
                "ts": "2026-09-06T10:00:05+00:00",
            },
            {
                "role": "tool",
                "content": "",
                "metadata": {"name": "read_file", "success": False},
                "ts": "2026-09-06T10:00:06+00:00",
            },
            {
                "role": "assistant",
                "content": "Here you go.",
                "ts": "2026-09-06T10:01:00+00:00",
                "metadata": {
                    "_assistant_stats": {
                        "run_id": "run-9",
                        "duration_ms": 65000,
                        "usage": {"input_tokens": 1200, "output_tokens": 300},
                    }
                },
            },
            # A second card for the SAME run must not be counted twice.
            {
                "role": "assistant",
                "content": "(replay)",
                "ts": "2026-09-06T10:01:02+00:00",
                "metadata": {"_assistant_stats": {"run_id": "run-9", "duration_ms": 65000}},
            },
            {"role": "user", "content": "[User response]: yes", "ts": "2026-09-06T10:02:00+00:00"},
            {"role": "user", "content": "And the migration notes?", "ts": "2026-09-06T10:03:00+00:00"},
        ],
    }


@pytest.mark.basic
def test_digest_counts_turns_tools_tokens_and_time_from_the_transcript() -> None:
    digest = digest_from_snapshot({"session_id": "sess_1", "title": "New session"}, _snapshot())

    assert digest.detailed is True
    assert digest.turns == 2                 # the ask_user reply is not a turn
    assert digest.answers == 2
    assert digest.tool_calls == 2
    assert digest.failed_tools == 1
    assert digest.top_tools == ("read_file",)
    assert (digest.input_tokens, digest.output_tokens) == (1200, 300)
    assert digest.total_tokens == 1500
    assert digest.duration_ms == 65000       # one run, counted once
    assert digest.runs == 1
    assert digest.workspace_root == "/Users/x/proj"
    assert digest.preview == "And the migration notes?"
    assert digest.first_prompt == "Summarize the release notes"
    assert digest.unanswered is True         # the transcript ends on the user
    assert digest.empty is False


@pytest.mark.basic
def test_display_title_falls_back_to_the_opening_question() -> None:
    digest = digest_from_snapshot({"session_id": "s", "title": "New session"}, _snapshot())
    assert digest.display_title == "Summarize the release notes"

    named = digest_from_snapshot({"session_id": "s", "title": "Release prep"}, _snapshot())
    assert named.display_title == "Release prep"

    blank = digest_from_snapshot({"session_id": "s", "title": "New session"}, {"messages": []})
    assert blank.display_title == "Untitled session"
    assert blank.empty is True


@pytest.mark.basic
def test_index_only_digest_claims_no_metrics() -> None:
    digest = digest_from_record({"session_id": "s", "title": "Whatever", "updated_at": "2026-09-06T10:00:00+00:00"})
    assert digest.detailed is False
    assert (digest.turns, digest.tool_calls, digest.total_tokens) == (0, 0, 0)
    # An unread transcript must never be reported as an empty chat.
    assert digest.empty is False


@pytest.mark.basic
def test_digest_cache_reads_once_and_again_only_after_a_change(tmp_path: Path) -> None:
    data_dir = tmp_path / "sessions" / "sess_1"
    data_dir.mkdir(parents=True)
    path = data_dir / "session.json"
    path.write_text(json.dumps(_snapshot()), encoding="utf-8")
    record = {"session_id": "sess_1", "title": "New session", "updated_at": "2026-09-06T10:03:00+00:00"}

    cache = SessionDigestCache()
    first = cache.digest(record, data_dir)
    assert first.turns == 2
    assert cache.cached("sess_1") is not None

    reads: list[str] = []
    original = Path.read_text

    def _counting_read(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == path:
            reads.append(str(self))
        return original(self, *args, **kwargs)

    Path.read_text = _counting_read  # type: ignore[assignment]
    try:
        cache.digest(record, data_dir)
        assert reads == []                      # unchanged file: served from cache
        payload = _snapshot()
        payload["messages"].append({"role": "assistant", "content": "done", "ts": "2026-09-06T10:04:00+00:00"})
        path.write_text(json.dumps(payload), encoding="utf-8")
        again = cache.digest(record, data_dir)
        assert reads and again.answers == 3
    finally:
        Path.read_text = original  # type: ignore[assignment]


@pytest.mark.basic
def test_missing_transcript_is_an_empty_chat_not_an_unknown_one(tmp_path: Path) -> None:
    digest = SessionDigestCache().digest({"session_id": "s", "title": "New session"}, tmp_path)
    assert digest.detailed is True and digest.empty is True


@pytest.mark.basic
def test_formatting_helpers_stay_short_and_honest() -> None:
    assert format_count(7) == "7"
    assert format_count(1234) == "1.2k"
    assert format_count(1_500_000) == "1.5M"
    assert format_tokens(39285) == "39.3k tk"
    assert format_duration_ms(8000) == "8 s"
    assert format_duration_ms(245000) == "4 min"
    assert format_duration_ms(4320000) == "1 h 12"
    assert format_duration_ms(0) == ""

    assert relative_time("2026-09-06T11:59:30+00:00", now=NOW) == "just now"
    assert relative_time("2026-09-06T11:40:00+00:00", now=NOW) == "20 min ago"
    assert relative_time("", now=NOW) == ""
    assert recency_group("2026-09-06T09:00:00+00:00", now=NOW) == "Today"
    assert recency_group("2026-09-05T09:00:00+00:00", now=NOW) == "Yesterday"
    assert recency_group("2026-09-02T09:00:00+00:00", now=NOW) == "Previous 7 days"
    assert recency_group("2026-08-20T09:00:00+00:00", now=NOW) == "Previous 30 days"
    assert recency_group("2026-03-18T09:00:00+00:00", now=NOW) == "Older"
    assert recency_group("", now=NOW) == "Older"


@pytest.mark.basic
def test_workspace_label_names_a_gateway_folder_instead_of_its_hash() -> None:
    assert workspace_label("/runtime/workspaces/0a8ef9721a7f4ed484b24309ef5b8ffd") == "gateway folder"
    assert workspace_label("/Users/x/proj/") == "proj"
    assert workspace_label("") == ""


@pytest.mark.basic
def test_filter_matches_title_preview_workspace_and_tools() -> None:
    digest = digest_from_snapshot({"session_id": "s", "title": "New session"}, _snapshot())
    assert session_matches_query(digest, "") is True
    assert session_matches_query(digest, "migration") is True      # preview
    assert session_matches_query(digest, "read_file") is True      # tool
    assert session_matches_query(digest, "proj") is True           # workspace
    assert session_matches_query(digest, "release notes") is True  # two words, both present
    assert session_matches_query(digest, "kubernetes") is False


@pytest.mark.basic
def test_sort_digests_puts_the_most_recent_activity_first() -> None:
    old = SessionDigest(session_id="old", updated_at="2026-01-01T00:00:00+00:00")
    fresh = SessionDigest(session_id="fresh", updated_at="2026-09-01T00:00:00+00:00", last_message_at="2026-09-06T10:00:00+00:00")
    undated = SessionDigest(session_id="undated")
    assert [d.session_id for d in sort_digests([old, undated, fresh])] == ["fresh", "old", "undated"]


# ------------------------------------------------------------------- the popup


def _digests():
    # Anchored to local NOON, not to "now". `now - 5 minutes` crosses into
    # yesterday just after midnight, and the row that must be in the "Today"
    # group silently lands in "Yesterday" — this suite failed exactly that way
    # at 00:0x. Grouping compares LOCAL dates, so the anchor must be local.
    noon = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    stamp = lambda delta: (noon - delta).astimezone(timezone.utc).isoformat()  # noqa: E731
    return [
        SessionDigest(
            session_id="today",
            title="Release prep",
            updated_at=stamp(timedelta(minutes=5)),
            detailed=True,
            messages=8,
            turns=3,
            answers=3,
            tool_calls=12,
            input_tokens=9000,
            output_tokens=1000,
            duration_ms=125000,
            runs=3,
            workspace_root="/Users/x/proj",
            preview="And the migration notes?",
            first_prompt="Summarize the release notes",
            last_role="assistant",
        ),
        SessionDigest(
            session_id="week",
            title="New session",
            updated_at=stamp(timedelta(days=3)),
            detailed=True,
            messages=2,
            turns=1,
            first_prompt="Check the camera tools",
            preview="Check the camera tools",
            failed_tools=2,
            tool_calls=4,
            last_role="user",
        ),
        SessionDigest(session_id="old", title="Archive", updated_at=stamp(timedelta(days=120)), detailed=True),
    ]


def _switcher():
    _app()
    switcher = SessionSwitcher()
    switcher.set_digests(_digests(), active_session_id="today")
    return switcher


@pytest.mark.basic
def test_switcher_groups_rows_and_marks_the_active_session() -> None:
    switcher = _switcher()
    assert [row.session_id for row in switcher.visible_rows()] == ["today", "week", "old"]
    assert sorted(switcher._group_labels) == ["Older", "Previous 7 days", "Today"]
    assert switcher.count_label.text().startswith("3 sessions")

    active_row = switcher.visible_rows()[0]
    assert active_row.property("active") == "true"
    assert switcher.selected_session_id == "today"
    # An unnamed chat is listed by its opening question, never as "New session".
    assert switcher.visible_rows()[1].title_label.text() == "Check the camera tools"


@pytest.mark.basic
def test_switcher_rows_show_metrics_and_never_repeat_the_title() -> None:
    switcher = _switcher()
    row = switcher.visible_rows()[0]
    texts = [w.text() for w in row.metrics_host.findChildren(type(row.title_label)) if w.objectName() == "rowMetric"]
    assert "3" in texts                       # turns
    assert "12" in texts                      # tool calls
    assert "10k tk" in texts
    assert "2 min" in texts
    assert "proj" in texts
    # The second row's preview equals its title: showing it twice says nothing.
    row_two = switcher.visible_rows()[1]
    assert row_two.preview_label.isVisibleTo(row_two) is False


@pytest.mark.basic
def test_switcher_filter_hides_rows_and_their_group_headers() -> None:
    switcher = _switcher()
    switcher.search_edit.setText("camera")
    assert [row.session_id for row in switcher.visible_rows()] == ["week"]
    assert switcher._group_labels["Today"].isVisibleTo(switcher) is False
    assert switcher._group_labels["Previous 7 days"].isVisibleTo(switcher) is True

    switcher.search_edit.setText("nothing matches this")
    assert switcher.visible_rows() == []
    assert switcher.empty_label.isVisibleTo(switcher) is True

    switcher.search_edit.setText("")
    assert len(switcher.visible_rows()) == 3
    assert switcher.empty_label.isVisibleTo(switcher) is False


@pytest.mark.basic
def test_switcher_keyboard_moves_the_selection_and_opens_a_chat() -> None:
    switcher = _switcher()
    chosen: list[str] = []
    switcher.session_chosen.connect(chosen.append)

    switcher.keyPressEvent(_key(Qt.Key_Down))
    assert switcher.selected_session_id == "week"
    switcher.keyPressEvent(_key(Qt.Key_Up))
    assert switcher.selected_session_id == "today"
    switcher.keyPressEvent(_key(Qt.Key_Return))
    assert chosen == ["today"]


@pytest.mark.basic
def test_switcher_delete_asks_in_the_row_before_it_deletes() -> None:
    switcher = _switcher()
    requested: list[str] = []
    switcher.delete_requested.connect(requested.append)

    switcher.keyPressEvent(_key(Qt.Key_Backspace, Qt.ControlModifier))
    row = switcher.visible_rows()[0]
    assert row.confirming_delete is True
    assert requested == []                    # nothing deleted yet

    switcher.keyPressEvent(_key(Qt.Key_Escape))
    assert row.confirming_delete is False

    row.ask_delete()
    row.delete_confirmed.emit(row.session_id)
    assert requested == ["today"]


@pytest.mark.basic
def test_switcher_rename_commits_the_new_title_once() -> None:
    switcher = _switcher()
    renames: list[tuple] = []
    switcher.rename_requested.connect(lambda sid, title: renames.append((sid, title)))

    row = switcher.visible_rows()[0]
    row.start_rename()
    assert row.rename_edit.isVisibleTo(row) is True
    row.rename_edit.setText("  Release  prep  2  ")
    row.rename_edit.returnPressed.emit()
    assert renames == [("today", "Release prep 2")]
    assert row.rename_edit.isVisibleTo(row) is False

    # Committing the unchanged title is not a rename.
    renames.clear()
    row.start_rename()
    row.rename_edit.setText(row.digest.display_title)
    row.rename_edit.returnPressed.emit()
    assert renames == []


@pytest.mark.basic
def test_switcher_new_chat_button_asks_for_one() -> None:
    switcher = _switcher()
    asked: list[bool] = []
    switcher.new_chat_requested.connect(lambda: asked.append(True))
    switcher.new_button.click()
    assert asked == [True]


def _key(key, modifiers=Qt.NoModifier):
    from PyQt5.QtGui import QKeyEvent
    from PyQt5.QtCore import QEvent

    return QKeyEvent(QEvent.KeyPress, key, modifiers)


# ------------------------------------------------------------------- deletion


@pytest.mark.basic
def test_removing_a_session_hides_it_and_keeps_its_text(tmp_path: Path) -> None:
    """The gateway has no delete route: "remove" is a local preference that
    hides the row; the cached folder MOVES to sessions-legacy (it is the only
    copy for a session that exists only here), and the active session moves
    to the newest remaining gateway session."""
    cache = SessionCache(tmp_path)
    first = cache.create_session()
    cache.set_rows(
        [GatewaySession(session_id=first, turns=2), GatewaySession(session_id="sess_other", turns=1)],
        truncated=False,
    )
    folder = cache.data_dir_for(first)
    assert folder.exists()

    new_active = cache.remove_from_list(first)

    assert folder.exists() is False
    assert (tmp_path / "sessions-legacy" / first / "session.json").exists()
    assert cache.is_hidden(first)
    assert new_active == "sess_other" == cache.active_session_id
    # Survives a reload.
    assert SessionCache(tmp_path).is_hidden(first)


@pytest.mark.basic
def test_removing_the_last_session_mints_a_fresh_one(tmp_path: Path) -> None:
    cache = SessionCache(tmp_path)
    only = cache.active_session_id
    active = cache.remove_from_list(only)
    assert active != only
    assert active == cache.active_session_id
    assert (cache.data_dir_for(active) / "session.json").exists()


# ------------------------------------------------------- palette integration


def _palette_with_picker(*, worker=None, active="today"):
    from PyQt5.QtWidgets import QPushButton

    from abstractassistant.app import AssistantPalette

    _app()
    palette = AssistantPalette.__new__(AssistantPalette)
    palette.session_picker = QPushButton()
    palette._worker = worker
    # Shaped like `llm_manager.session_digests()`: the dicts carry the computed
    # `display_title`, which is the whole reason the header can name a session
    # whose stored title is the placeholder "New session".
    palette._session_digests = [
        {
            "session_id": "today",
            "title": "Release prep",
            "display_title": "Release prep",
            "detailed": True,
            "updated_at": "2026-09-06T10:00:00+00:00",
        },
        {
            "session_id": "week",
            "title": "New session",
            "display_title": "Check the camera tools",
            "first_prompt": "Check the camera tools",
            "detailed": True,
        },
    ]
    palette._active_session_id = lambda: active
    palette._refresh_workspace_hint = lambda: None
    return palette


@pytest.mark.basic
def test_palette_header_button_names_the_active_session() -> None:
    from abstractassistant.app import AssistantPalette

    palette = _palette_with_picker()
    AssistantPalette._refresh_session_picker(palette)
    assert palette.session_picker.text() == "Release prep"

    palette = _palette_with_picker(active="week")
    AssistantPalette._refresh_session_picker(palette)
    # An unnamed session is named by its opening question, and a session
    # with nothing in it is never announced as "New".
    assert palette.session_picker.text() == "Check the camera tools"


@pytest.mark.basic
def test_palette_refuses_to_switch_or_delete_while_a_run_is_active() -> None:
    from abstractassistant.app import AssistantPalette

    banners: list[tuple] = []
    switched: list[str] = []
    palette = _palette_with_picker(worker=object())
    palette._set_banner = lambda text, tone="info", key="": banners.append((text, tone))
    palette._controller = type(
        "C",
        (),
        {
            "switch_session": lambda self, sid: switched.append(sid),
            "delete_session": lambda self, sid: switched.append(f"delete:{sid}"),
        },
    )()

    AssistantPalette._switch_to_session(palette, "week")
    assert switched == []
    assert banners and "stop it" in banners[0][0]

    banners.clear()
    AssistantPalette._delete_session(palette, "today")
    assert switched == []
    assert banners and "Stop the run" in banners[0][0]


@pytest.mark.basic
def test_palette_deletes_a_session_and_reloads_when_it_was_the_active_one() -> None:
    from abstractassistant.app import AssistantPalette

    calls: list[str] = []
    palette = _palette_with_picker()
    palette._set_banner = lambda text, tone="info", key="": calls.append(f"banner:{text}")
    palette._set_history_status = lambda *a, **k: None
    palette._set_status = lambda *a, **k: None
    palette._refresh_tray_feedback = lambda: None
    palette._history_scroll_request = lambda **kw: None
    palette.refresh_history = lambda request=None: calls.append("history")
    palette._warm_session_digests = lambda: calls.append("warm")
    palette._controller = type(
        "C", (), {"delete_session": lambda self, sid: (calls.append(f"delete:{sid}"), "week")[1]}
    )()

    AssistantPalette._delete_session(palette, "today")

    assert "delete:today" in calls
    assert "history" in calls          # the deleted session was on screen
    assert "warm" in calls             # metrics recomputed
    assert palette._session_digests == []
    assert palette.session_picker.text() == "Untitled session"


@pytest.mark.basic
def test_switcher_survives_being_rebuilt_from_inside_a_row_signal() -> None:
    """Deleting re-renders the list while the emitting row is alive: the row
    must be torn down safely, not crash the popup."""
    switcher = _switcher()
    remaining = [d for d in _digests() if d.session_id != "today"]
    switcher.delete_requested.connect(
        lambda sid: switcher.set_digests(remaining, active_session_id="week")
    )

    row = switcher.visible_rows()[0]
    row.ask_delete()
    row.delete_confirmed.emit(row.session_id)

    _app().processEvents()
    assert [r.session_id for r in switcher.visible_rows()] == ["week", "old"]
    assert switcher.selected_session_id == "week"


@pytest.mark.basic
def test_rows_never_show_a_parentless_widget() -> None:
    """`setVisible(True)` on a PARENTLESS widget opens a real top-level window.

    Two per row cost ~16 ms and four window-activation flips; at 74 chats that
    was a 1.2 s rebuild and — because macOS closes popups when another window
    takes key status — the switcher closing itself. The offscreen platform
    opens no native windows, so neither timing nor the rendered result can
    catch this; the Show event delivered to an unparented widget can.
    """
    from PyQt5.QtCore import QEvent, QObject
    from PyQt5.QtWidgets import QWidget

    app = _app()

    class _Watch(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.offenders: list[str] = []

        def eventFilter(self, obj, event):  # noqa: N802 (Qt API)
            if (
                event.type() == QEvent.Show
                and isinstance(obj, QWidget)
                and obj.parent() is None
            ):
                self.offenders.append(f"{type(obj).__name__}#{obj.objectName()}")
            return False

    watch = _Watch()
    app.installEventFilter(watch)
    try:
        for digest in _digests():
            SessionRow(digest, active=False)
        app.processEvents()
    finally:
        app.removeEventFilter(watch)

    assert watch.offenders == [], (
        f"shown before being parented (each is a native window): {watch.offenders}"
    )


@pytest.mark.basic
def test_reopening_with_the_same_chats_keeps_the_rows() -> None:
    """A refresh that finds nothing new must not throw away the rows the user
    is looking at — rebuilding is both wasted work and a chance to break."""
    _app()
    # One list, reused: `_digests()` stamps "now" on every call, so building it
    # twice would legitimately differ.
    digests = _digests()
    switcher = SessionSwitcher()
    switcher.set_digests(digests, active_session_id="today")
    rows = list(switcher.visible_rows())

    switcher.set_digests(digests, active_session_id="today")
    assert switcher.visible_rows() == rows, "identical data must not rebuild"

    # A real change still rebuilds.
    switcher.set_digests(digests[:2], active_session_id="today")
    assert len(switcher.visible_rows()) == 2
    # So does a change of which chat is active.
    switcher.set_digests(digests[:2], active_session_id="week")
    assert switcher.visible_rows()[1].property("active") == "true"


@pytest.mark.basic
def test_rebuilding_an_open_switcher_never_squeezes_the_rows() -> None:
    """The reported corruption: rows re-rendered under an open popup kept the
    previous list's height and were drawn on top of each other."""
    from PyQt5.QtCore import QPoint, QRect

    app = _app()
    switcher = SessionSwitcher()
    thin = [
        {"session_id": d.session_id, "title": d.title, "updated_at": d.updated_at}
        for d in _digests()
    ]
    switcher.set_digests(thin, active_session_id="today")
    switcher.open_at(QPoint(40, 40), screen_geometry=QRect(0, 0, 1440, 900))
    for _ in range(20):
        app.processEvents()
    switcher.grab()  # force a real layout pass, as a visible popup gets

    # The metrics land: every row grows, and none may be squeezed under its
    # own minimum (that is what draws one row over the next).
    switcher.set_digests(_digests(), active_session_id="today")
    for _ in range(20):
        app.processEvents()
    switcher.grab()

    rows = switcher.visible_rows()
    assert rows
    for row in rows:
        assert row.height() >= row.minimumSizeHint().height(), (
            f"row {row.session_id} squeezed to {row.height()}px"
        )
    # ...and the list is tall enough to hold them all, so the scroll area
    # scrolls instead of overlapping.
    assert switcher.list_host.height() >= sum(r.height() for r in rows)
    switcher.close()


@pytest.mark.basic
def test_palette_opens_the_switcher_with_digests_already_loaded() -> None:
    """Blazing fast AND correct: the rows carry their metrics on the FIRST
    open, so nothing rebuilds them under the user seconds later."""
    from abstractassistant.app import AssistantPalette

    calls: list[str] = []
    palette = _palette_with_picker()
    palette._session_digests = []
    palette._controller = type(
        "C",
        (),
        {
            "session_digests": lambda self: (
                calls.append("digests"),
                [{"session_id": "today", "title": "Release prep", "detailed": True}],
            )[1]
        },
    )()
    opened: list = []
    registered: list = []
    switcher = type(
        "S",
        (),
        {
            "set_digests": lambda self, records, active_session_id="": opened.append(
                (list(records), active_session_id)
            ),
            "open_at": lambda self, origin, screen_geometry=None: opened.append("open"),
            "isVisible": lambda self: True,
        },
    )()
    palette._session_switcher = switcher
    palette._register_aux_dialog = lambda dialog: registered.append(dialog)
    palette._available_screen_geometry = lambda: None
    palette.mapToGlobal = lambda point: point

    AssistantPalette._open_session_switcher(palette)

    # Digests are read before the popup is shown, not after.
    assert calls == ["digests"]
    assert opened[0][0] and opened[0][0][0]["detailed"] is True
    assert opened[1] == "open"

    # A refresh of the header must NOT re-render an open popup any more: that
    # rebuild is what corrupted the layout and cost the palette its focus.
    opened.clear()
    AssistantPalette._refresh_session_picker(palette)
    assert opened == []

    # Rename/delete refresh it explicitly instead.
    AssistantPalette._refresh_open_session_switcher(palette)
    assert opened and opened[0][1] == "today"


@pytest.mark.basic
def test_an_open_switcher_grows_when_the_gateway_rows_arrive() -> None:
    """The popup opens on the cached list (maybe one row) and the gateway's
    answer lands after: it must grow to show the rows, not scroll a sliver."""
    from PyQt5.QtCore import QPoint, QRect

    app = _app()
    switcher = SessionSwitcher()
    stamp = NOW.isoformat()
    switcher.set_digests([SessionDigest(session_id="a", title="A", updated_at=stamp)], active_session_id="a")
    switcher.open_at(QPoint(10, 10), screen_geometry=QRect(0, 0, 1440, 900))
    for _ in range(10):
        app.processEvents()
    opened = switcher.height()

    switcher.set_digests(
        [SessionDigest(session_id=f"s{i}", title=f"S{i}", updated_at=stamp, turns=2) for i in range(8)],
        active_session_id="a",
    )
    for _ in range(10):
        app.processEvents()

    assert switcher.height() > opened + 150
    switcher.close()
