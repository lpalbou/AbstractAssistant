"""Basic coverage for tool-call file-activity classification."""

from __future__ import annotations

import pytest

from abstractassistant.core.file_activity import (
    FileOperation,
    distinct_file_count,
    file_operations_from_tool_calls,
    grouped_file_operations,
)


def _ops(tool_calls):
    return [
        (op.action, op.path, op.detail)
        for op in file_operations_from_tool_calls(tool_calls)
    ]


@pytest.mark.basic
def test_file_activity_classifies_dedicated_file_tools() -> None:
    calls = [
        {"name": "write_file", "arguments": {"file_path": "notes/plan.md", "content": "x"}},
        {"name": "write_file", "arguments": {"file_path": "log.txt", "mode": "a", "content": "x"}},
        {"name": "edit_file", "arguments": {"file_path": "src/app.py", "pattern": "a"}},
        {"name": "delete_file", "arguments": {"path": "tmp/scratch.txt"}},
        {"name": "move_file", "arguments": {"source": "a.txt", "destination": "b.txt"}},
    ]

    assert _ops(calls) == [
        ("created", "notes/plan.md", ""),
        ("modified", "log.txt", ""),
        ("modified", "src/app.py", ""),
        ("deleted", "tmp/scratch.txt", ""),
        ("moved", "a.txt", "b.txt"),
    ]


@pytest.mark.basic
def test_file_activity_parses_execute_command_segments() -> None:
    calls = [
        {
            "name": "execute_command",
            "arguments": {
                "command": "mkdir -p docs && touch docs/notes.md; mv draft.md docs/draft.md && rm old.log"
            },
        }
    ]

    assert _ops(calls) == [
        ("created", "docs", ""),
        ("created", "docs/notes.md", ""),
        ("moved", "draft.md", "docs/draft.md"),
        ("deleted", "old.log", ""),
    ]


@pytest.mark.basic
def test_file_activity_handles_redirects_without_misreading_targets() -> None:
    calls = [
        {"name": "execute_command", "arguments": {"command": "echo hi > notes.txt"}},
        {"name": "execute_command", "arguments": {"command": "echo hi >> journal.log 2>&1"}},
        {"name": "execute_command", "arguments": {"command": "rm a.txt > rm.log"}},
    ]

    assert _ops(calls) == [
        ("created", "notes.txt", ""),
        ("modified", "journal.log", ""),
        ("created", "rm.log", ""),
        ("deleted", "a.txt", ""),
    ]


@pytest.mark.basic
def test_file_activity_stays_conservative_on_globs_and_failures() -> None:
    calls = [
        # Glob expansion cannot be resolved client-side: report nothing.
        {"name": "execute_command", "arguments": {"command": "rm -rf *.log"}},
        # A failed call did not change the file system.
        {"name": "write_file", "arguments": {"file_path": "x.txt", "content": ""}, "success": False},
        # Read-only tools never count as file activity.
        {"name": "read_file", "arguments": {"file_path": "x.txt"}},
        {"name": "list_files", "arguments": {"directory_path": "."}},
        {"name": "web_search", "arguments": {"query": "abc"}},
    ]

    assert _ops(calls) == []


@pytest.mark.basic
def test_file_activity_accepts_json_string_arguments() -> None:
    calls = [
        {"name": "write_file", "arguments": '{"file_path": "out/report.md", "content": "x"}'}
    ]

    assert _ops(calls) == [("created", "out/report.md", "")]


@pytest.mark.basic
def test_file_activity_distinct_count_and_grouping() -> None:
    calls = [
        {"name": "write_file", "arguments": {"file_path": "a.txt", "content": "x"}},
        {"name": "edit_file", "arguments": {"file_path": "a.txt", "pattern": "x"}},
        {"name": "move_file", "arguments": {"source": "b.txt", "destination": "c.txt"}},
        {"name": "delete_file", "arguments": {"path": "d.txt"}},
    ]
    ops = file_operations_from_tool_calls(calls)

    # a.txt (created + modified) counts once; the move counts by destination.
    assert distinct_file_count(ops) == 3

    grouped = grouped_file_operations(ops)
    assert [action for action, _ in grouped] == ["created", "modified", "moved", "deleted"]
    moved = dict(grouped)["moved"][0]
    assert isinstance(moved, FileOperation)
    assert moved.label == "b.txt \u2192 c.txt"


@pytest.mark.basic
def test_file_activity_deduplicates_repeated_operations() -> None:
    calls = [
        {"name": "write_file", "arguments": {"file_path": "a.txt", "content": "x"}},
        {"name": "write_file", "arguments": {"file_path": "a.txt", "content": "y"}},
    ]

    assert _ops(calls) == [("created", "a.txt", "")]
