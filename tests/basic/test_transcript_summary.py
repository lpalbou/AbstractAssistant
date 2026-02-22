import pytest

from abstractassistant.core.transcript_summary import build_display_messages


@pytest.mark.basic
def test_build_display_messages_hides_tool_messages_and_attaches_summary() -> None:
    raw = [
        {"role": "user", "content": "detect browser zoom", "timestamp": "2026-02-04T12:00:00+00:00"},
        {"role": "assistant", "content": "", "metadata": {"kind": "tool_calls"}},
        {
            "role": "tool",
            "content": "[fetch_url]: URL: https://example.com/page\nStatus: 200 OK",
            "metadata": {"name": "fetch_url", "success": True},
        },
        {
            "role": "tool",
            "content": "[remember_note]: Stored memory_note span_id=span_123 tags={\"topic\":\"x\"}",
            "metadata": {"name": "remember_note", "success": True},
        },
        {"role": "assistant", "content": "Here you go.", "metadata": {"kind": "final_answer"}},
    ]

    out = build_display_messages(raw)
    assert out and out[0].get("role") == "user"
    assert any(m.get("ui_kind") == "tool_result" for m in out)

    assistant = out[-1]
    summary = str(assistant.get("tool_summary") or "")
    assert "fetch_url" in summary
    assert "remember_note" in summary

    links = assistant.get("tool_links") or []
    assert any(
        isinstance(link, dict)
        and link.get("kind") == "url"
        and link.get("target") == "https://example.com/page"
        for link in links
    )


@pytest.mark.basic
def test_build_display_messages_groups_multiple_tool_cycles_and_prefers_primary_file_path() -> None:
    raw = [
        {"role": "user", "content": "open docs", "timestamp": "2026-02-04T12:00:00+00:00"},
        {"role": "assistant", "content": "", "metadata": {"kind": "tool_calls"}},
        {
            "role": "tool",
            "content": "[fetch_url]: URL: https://example.com/a\nStatus: 200 OK",
            "metadata": {"name": "fetch_url", "success": True},
        },
        {"role": "assistant", "content": "", "metadata": {"kind": "tool_calls"}},
        {
            "role": "tool",
            "content": (
                "[read_file]: File: /Users/test/repo/docs/architecture.md (2 lines)\n\n"
                "1: see http://should-not-become-a-chip.example\n"
                "2: and /tmp/also-should-not-become-a-chip"
            ),
            "metadata": {"name": "read_file", "success": True},
        },
        {"role": "assistant", "content": "Done.", "metadata": {"kind": "final_answer"}},
    ]

    out = build_display_messages(raw)
    assert out and out[0].get("role") == "user"
    assert any(m.get("ui_kind") == "tool_result" for m in out)

    assistant = out[-1]
    summary = str(assistant.get("tool_summary") or "")
    assert "fetch_url" in summary
    assert "read_file" in summary

    links = assistant.get("tool_links") or []
    assert any(
        isinstance(link, dict)
        and link.get("kind") == "file"
        and link.get("target") == "/Users/test/repo/docs/architecture.md"
        for link in links
    )
    assert not any(
        isinstance(link, dict)
        and link.get("kind") == "url"
        and str(link.get("target") or "").startswith("http://should-not-become-a-chip")
        for link in links
    )


@pytest.mark.basic
def test_build_display_messages_extracts_markdown_images_as_thumbnails() -> None:
    raw = [
        {"role": "user", "content": "show me", "timestamp": "2026-02-04T12:00:00+00:00"},
        {
            "role": "assistant",
            "content": "Here is one:\n\n![cat](https://example.com/cat.png)\n",
            "metadata": {"kind": "final_answer"},
        },
    ]

    out = build_display_messages(raw)
    assert [m.get("role") for m in out] == ["user", "assistant"]

    assistant = out[1]
    assert "cat.png" not in str(assistant.get("content") or "")
    thumbs = assistant.get("image_thumbnails") or []
    assert any(
        isinstance(th, dict)
        and th.get("kind") == "url"
        and th.get("target") == "https://example.com/cat.png"
        for th in thumbs
    )


@pytest.mark.basic
def test_build_display_messages_promotes_image_tool_links_to_thumbnails() -> None:
    raw = [
        {"role": "user", "content": "fetch image", "timestamp": "2026-02-04T12:00:00+00:00"},
        {"role": "assistant", "content": "", "metadata": {"kind": "tool_calls"}},
        {
            "role": "tool",
            "content": "[fetch_url]: URL: https://example.com/pic.jpg\nStatus: 200 OK",
            "metadata": {"name": "fetch_url", "success": True},
        },
        {"role": "assistant", "content": "Done.", "metadata": {"kind": "final_answer"}},
    ]

    out = build_display_messages(raw)
    assistant = out[-1]
    thumbs = assistant.get("image_thumbnails") or []
    assert any(
        isinstance(th, dict)
        and th.get("kind") == "url"
        and th.get("target") == "https://example.com/pic.jpg"
        for th in thumbs
    )


@pytest.mark.basic
def test_build_display_messages_includes_artifact_links() -> None:
    raw = [
        {"role": "user", "content": "make file", "timestamp": "2026-02-04T12:00:00+00:00"},
        {
            "role": "tool",
            "content": "{\"$artifact\":\"art_123\",\"filename\":\"report.md\",\"content_type\":\"text/markdown\"}",
            "metadata": {"name": "write_file", "success": True, "run_id": "run_1"},
        },
        {"role": "assistant", "content": "Saved.", "metadata": {"kind": "final_answer"}},
    ]
    out = build_display_messages(raw)
    assistant = out[-1]
    links = assistant.get("tool_links") or []
    assert any(
        isinstance(link, dict)
        and link.get("kind") == "artifact"
        and link.get("target") == "art_123"
        and link.get("run_id") == "run_1"
        for link in links
    )
