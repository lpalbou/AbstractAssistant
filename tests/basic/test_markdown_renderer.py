"""Basic coverage for markdown rendering helpers."""

from __future__ import annotations

import pytest

from PyQt5.QtCore import QSize

from abstractassistant.utils.markdown_renderer import MarkdownRenderer, _prepare_markdown_source
from abstractassistantv2.app import _image_thumbnail_size


@pytest.mark.basic
def test_prepare_markdown_source_wraps_standalone_json_payload() -> None:
    prepared = _prepare_markdown_source('{"assistant":"AbstractAssistant","items":[1,2]}')

    assert prepared.startswith("```json\n{")
    assert '"assistant": "AbstractAssistant"' in prepared
    assert '"items": [' in prepared


@pytest.mark.basic
def test_prepare_markdown_source_wraps_yaml_like_payload() -> None:
    prepared = _prepare_markdown_source(
        "assistant:\n"
        "  model: gpt-oss-120b\n"
        "  tools:\n"
        "    - web\n"
    )

    assert prepared.startswith("```yaml\nassistant:")
    assert "model: gpt-oss-120b" in prepared
    assert prepared.rstrip().endswith("```")


@pytest.mark.basic
def test_prepare_markdown_source_preserves_existing_markdown() -> None:
    markdown_text = (
        "I'm **AbstractAssistant**.\n\n"
        "| Name | Value |\n"
        "| --- | --- |\n"
        "| mode | chat |\n"
    )

    assert _prepare_markdown_source(markdown_text) == markdown_text


@pytest.mark.basic
def test_markdown_renderer_renders_inline_formatting_and_tables() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "I'm **AbstractAssistant**.\n\n"
        "| Name | Value |\n"
        "| --- | --- |\n"
        "| mode | chat |\n"
    )

    assert "<strong>AbstractAssistant</strong>" in html
    assert "<table>" in html
    assert "<td>chat</td>" in html


@pytest.mark.basic
def test_markdown_renderer_formats_raw_json_as_highlighted_code() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render('{"assistant":"AbstractAssistant","ok":true}')

    assert "codehilite" in html
    assert "AbstractAssistant" in html


@pytest.mark.basic
def test_image_thumbnail_size_keeps_ratio_with_fixed_preview_height() -> None:
    landscape = _image_thumbnail_size(QSize(400, 100))
    portrait = _image_thumbnail_size(QSize(100, 400))

    assert landscape == QSize(200, 50)
    assert portrait.height() == 50
    assert portrait.width() in {12, 13}
