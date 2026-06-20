"""Basic coverage for markdown rendering helpers."""

from __future__ import annotations

import base64
import pytest

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QImage

from abstractassistant.utils.markdown_renderer import (
    MarkdownRenderer,
    _prepare_markdown_source,
    split_markdown_mermaid_blocks,
)
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
def test_markdown_renderer_falls_back_when_pymdownx_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MarkdownRenderer, "_has_pymdownx", staticmethod(lambda: False))

    renderer = MarkdownRenderer()
    html = renderer.render("```python\nprint(1)\n```")

    assert "Markdown rendering error" not in html
    assert "codehilite" in html


@pytest.mark.basic
def test_markdown_renderer_renders_mermaid_flowchart_as_inline_image() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "Here is the loop:\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "    A[Observation] --> B[Thought (Reasoning)]\n"
        "    B --> C[Action]\n"
        "    C --> D[Observation (Feedback)]\n"
        "    D --> A\n"
        "```\n"
    )

    assert '<div class="mermaid-diagram">' in html
    assert "data:image/png;base64," in html
    assert "Thought (Reasoning)" not in html


@pytest.mark.basic
def test_markdown_renderer_mermaid_png_does_not_clip_bright_text_into_top_edge() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "```mermaid\n"
        "flowchart LR\n"
        "    A[Observation] --> B[Thought (Reasoning)]\n"
        "    B --> C[Action]\n"
        "    C --> D[Observation (Feedback)]\n"
        "    D --> A\n"
        "```\n"
    )

    marker = "data:image/png;base64,"
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    raw = base64.b64decode(html[start:end])
    image = QImage()
    assert image.loadFromData(raw, "PNG")

    bright_pixels = 0
    sample_rows = min(24, image.height())
    for y in range(sample_rows):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if (
                color.alpha() > 150
                and color.red() > 235
                and color.green() > 235
                and color.blue() > 235
            ):
                bright_pixels += 1

    assert bright_pixels == 0


@pytest.mark.basic
def test_markdown_renderer_recovers_common_mermaid_router_formatting_mistakes() -> None:
    blocks = split_markdown_mermaid_blocks(
        "```mermaid\n"
        "flowchart TD\n"
        "    Start([Start]) --> Init[Initialize context & goals]\n"
        "    Init --> Think1[Thought: what should I do next?]\n"
        "    Think1 -->|Tool needed?| Decision{Tool?\\nYes / No}\n"
        "    Decision -->|Yes| ExecTool[Execute tool]\n"
        "    ExecTool --> ObsTool[Observation: tool result]\n"
        "    ObsTool --> Think2[Thought: interpret result]\n"
        "    Think2 -->|Finished?|\\n{Done?\\nYes / No} -->|Yes| End[Answer / End]\n"
        "    Think2 -->|No| Decision2{Tool?\\nYes / No}\n"
        "    Decision2 -->|Yes| ExecTool2[Execute tool]\n"
        "    ExecTool2 -.->|Error| HandleErr[Handle error]\n"
        "    HandleErr --> Think1\n"
        "    classDef process fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;\n"
        "```\n"
    )

    mermaid_blocks = [block for block in blocks if block.kind == "mermaid"]
    assert len(mermaid_blocks) == 1
    assert mermaid_blocks[0].data_uri.startswith("data:image/png;base64,")


@pytest.mark.basic
def test_markdown_renderer_falls_back_for_unsupported_mermaid_dialects() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "```mermaid\n"
        "sequenceDiagram\n"
        "    Alice->>Bob: Hello Bob\n"
        "```\n"
    )

    assert '<div class="mermaid-diagram">' not in html
    assert "sequenceDiagram" in html


@pytest.mark.basic
def test_image_thumbnail_size_keeps_ratio_with_fixed_preview_height() -> None:
    landscape = _image_thumbnail_size(QSize(400, 100))
    portrait = _image_thumbnail_size(QSize(100, 400))

    assert landscape == QSize(200, 50)
    assert portrait.height() == 50
    assert portrait.width() in {12, 13}
