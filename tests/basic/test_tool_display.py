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
