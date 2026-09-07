from abstractassistant.core.tool_display import (
    compact_tool_call_label,
    compact_tool_call_label_html,
    compact_tool_message_label,
    compact_tool_message_label_html,
)


def test_compact_tool_call_label_shows_preferred_arguments() -> None:
    label = compact_tool_call_label(
        "web_search",
        {"query": "ML Engineering Director Genentech AI4DD 2026", "num_results": 10},
        max_chars=120,
    )

    assert label == 'web_search(query="ML Engineering Director Genentech AI4DD 2026", num_results=10)'
    assert "\n" not in label


def test_compact_tool_call_label_is_single_line_and_bounded() -> None:
    label = compact_tool_call_label(
        "web_search",
        {"query": " ".join(["availability"] * 80), "num_results": 10},
        max_chars=80,
    )

    assert len(label) <= 80
    assert "\n" not in label
    assert label.startswith('web_search(query="availability')
    assert "..." in label


def test_compact_tool_message_label_reads_metadata_arguments() -> None:
    label = compact_tool_message_label(
        {
            "role": "tool",
            "metadata": {
                "name": "fetch_url",
                "arguments": {"url": "https://example.com/products/shed", "max_chars": 4000},
            },
        },
        max_chars=120,
    )

    assert label == 'fetch_url(url="https://example.com/products/shed", max_chars=4000)'


def test_compact_tool_call_label_html_colors_name_and_arguments() -> None:
    label = compact_tool_call_label_html(
        "web_search",
        {"query": "ML Engineering Director Genentech AI4DD 2026", "num_results": 10},
        max_chars=120,
    )

    assert 'color:#63d98b' in label
    assert 'color:#ffc963' in label
    assert 'font-weight:400' in label
    assert "web_search" in label
    assert '<span style="color:#63d98b; font-weight:800;">(</span>' in label
    assert '<span style="color:#63d98b; font-weight:800;">)</span>' in label
    assert "query=&quot;ML Engineering Director Genentech AI4DD 2026&quot;" in label


def test_compact_tool_message_label_html_reads_metadata_arguments() -> None:
    label = compact_tool_message_label_html(
        {
            "role": "tool",
            "metadata": {
                "name": "fetch_url",
                "arguments": {"url": "https://example.com/products/shed", "max_chars": 4000},
            },
        },
        max_chars=120,
    )

    assert 'color:#63d98b' in label
    assert 'font-weight:400' in label
    assert "fetch_url" in label
    assert "max_chars=4000" in label


def test_the_footer_shows_a_total_rather_than_claiming_zero_tokens() -> None:
    """`input : 0 tk` is a CLAIM, and a false one.

    Some servers report usage in the Responses dialect
    (`input_tokens`/`output_tokens`); the provider layer normalizes by reading
    Chat-Completions names only, so both halves arrive as 0 while the total
    survives. 47.5% of runs in the operator's store are affected. Until that is
    fixed upstream (docs/backlog/proposed/0011), show the number we actually
    have instead of two that we do not.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import abstractassistant.app as app_module

    def footer(usage):
        return app_module._assistant_footer_items(
            {
                "role": "assistant",
                "content": "hi",
                "metadata": {"_assistant_stats": {"usage": usage, "tool_calls": 0, "duration_ms": 9400}},
            }
        )

    lost_split = footer({"input_tokens": 0, "output_tokens": 0, "total_tokens": 4157})
    assert any("total : 4,157 tk" in item for item in lost_split), lost_split
    assert not any(item.startswith("input :") for item in lost_split), lost_split
    assert not any(item.startswith("output :") for item in lost_split), lost_split

    # A real split is still shown as a split.
    known = footer({"input_tokens": 4084, "output_tokens": 73, "total_tokens": 4157})
    assert any("input : 4,084 tk" in item for item in known), known
    assert any("output : 73 tk" in item for item in known), known
    assert not any(item.startswith("total :") for item in known), known

    # A genuinely empty usage claims nothing at all.
    empty = footer({"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    assert not any("tk" in item for item in empty), empty
