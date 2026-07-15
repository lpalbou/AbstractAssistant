"""Basic coverage for markdown rendering helpers."""

from __future__ import annotations

import base64
import re
import pytest

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication, QTextBrowser

from abstractassistant.utils.markdown_renderer import (
    MarkdownRenderer,
    _autolink_html_text,
    _prepare_markdown_source,
    split_markdown_mermaid_blocks,
)
from abstractassistant.app import _image_thumbnail_size


@pytest.mark.basic
def test_prepare_markdown_source_wraps_standalone_json_payload() -> None:
    prepared = _prepare_markdown_source(
        '{"assistant":"AbstractAssistant","items":[1,2]}'
    )

    assert prepared.startswith("```json\n{")
    assert '"assistant": "AbstractAssistant"' in prepared
    assert '"items": [' in prepared


@pytest.mark.basic
def test_prepare_markdown_source_wraps_yaml_like_payload() -> None:
    prepared = _prepare_markdown_source(
        "assistant:\n" "  model: gpt-oss-120b\n" "  tools:\n" "    - web\n"
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
def test_prepare_markdown_source_recovers_loose_and_nested_bullets() -> None:
    markdown_text = (
        "**Key Story:** *Anthropic Surpasses OpenAI in Valuation*\n"
        "- Anthropic closed the largest private funding round in AI history\n"
        "- **Claude Opus 4.8** leads the model race\n"
        "- Google I/O & Microsoft Build dominated June launches:\n"
        "- Google released new Gemini family\n"
        "- Microsoft shipped 7 in-house models\n"
        "- NVIDIA open-sourced Cosmos 3\n"
    )

    prepared = _prepare_markdown_source(markdown_text)

    assert (
        "\n\n- Anthropic closed the largest private funding round in AI history"
        in prepared
    )
    assert "\n- Google I/O & Microsoft Build dominated June launches:" in prepared
    assert "\n  - Google released new Gemini family" in prepared
    assert "\n  - Microsoft shipped 7 in-house models" in prepared
    assert "\n- NVIDIA open-sourced Cosmos 3" in prepared


@pytest.mark.basic
def test_prepare_markdown_source_recovers_heading_style_nested_bullets() -> None:
    markdown_text = (
        "**Key Story:** *US-Iran Peace Deal Fragile as Strait of Hormuz Re-Closed*\n"
        "- **June 20, 2026:** Iran re-closed Strait of Hormuz, citing US/Israel ceasefire violations\n"
        "- **VP JD Vance** arrived in Switzerland (Zurich) for peace talks with Iranian negotiators\n"
        "- Oil prices soaring; 20,000 seafarers stranded\n"
        "- **Israel-Hezbollah conflict** added to emergency peace session agenda\n"
        "- **Ukraine War Update:**\n"
        "- Zelensky: Ukrainian FP drones now reach 3,000 km (hit Russia's Tyumen region)\n"
        "- Russian airstrike on Zaporizhzhia: 5 dead, 11 injured\n"
    )

    prepared = _prepare_markdown_source(markdown_text)

    assert "\n- **Ukraine War Update:**" in prepared
    assert (
        "\n  - Zelensky: Ukrainian FP drones now reach 3,000 km (hit Russia's Tyumen region)"
        in prepared
    )
    assert "\n  - Russian airstrike on Zaporizhzhia: 5 dead, 11 injured" in prepared


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
def test_markdown_renderer_autolinks_bare_urls_in_text_and_lists() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "LIENS D'ACHAT:\n"
        "- Ensemble complet : https://www.climaffaires.com/unites-interieures-daikin/3104-daikin.html\n"
        "- Unité intérieure : www.climaled.fr/unite-interieure-daikin\n"
    )

    assert (
        '<a href="https://www.climaffaires.com/unites-interieures-daikin/3104-daikin.html">'
        "https://www.climaffaires.com/unites-interieures-daikin/3104-daikin.html</a>"
    ) in html
    assert (
        '<a href="https://www.climaled.fr/unite-interieure-daikin">'
        "www.climaled.fr/unite-interieure-daikin</a>"
    ) in html


@pytest.mark.basic
def test_markdown_renderer_autolink_excludes_sentence_punctuation() -> None:
    html = _autolink_html_text("<p>Open https://example.com/path?x=1&amp;y=2.</p>")

    assert 'href="https://example.com/path?x=1&amp;y=2"' in html
    assert "https://example.com/path?x=1&amp;y=2</a>." in html


@pytest.mark.basic
def test_markdown_renderer_autolink_does_not_rewrite_existing_links_or_code() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "[Existing](https://example.com/one)\n\n"
        "`https://example.com/code`\n\n"
        "```text\nhttps://example.com/fenced\n```\n"
    )

    assert html.count('<a href="https://example.com/one">Existing</a>') == 1
    assert 'href="https://example.com/code"' not in html
    assert 'href="https://example.com/fenced"' not in html


@pytest.mark.basic
def test_markdown_renderer_formats_raw_json_as_highlighted_code() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render('{"assistant":"AbstractAssistant","ok":true}')

    assert "codehilite" in html
    assert "AbstractAssistant" in html


@pytest.mark.basic
def test_markdown_renderer_highlights_fenced_code_without_language_metadata() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render("```\nprint(1)\n```")

    assert "Markdown rendering error" not in html
    assert "codehilite" in html


@pytest.mark.basic
def test_markdown_renderer_wraps_json_code_blocks_in_a_consistent_panel() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render('```json\n{"model":"gpt-5.4-mini","max_tokens":100}\n```')

    assert 'data-code-language="json"' in html
    assert 'bgcolor="#101722"' in html
    assert "font-size: 0.85em" in html


@pytest.mark.basic
def test_markdown_renderer_highlights_embedded_json_inside_bash_payloads() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "```bash\n"
        "curl -X POST https://openai.abstractframework.ai/v1/chat/completions \\\n"
        '  -H "Content-Type: application/json" \\\n'
        "  -d '{\n"
        '    "model": "gpt-5.4-mini",\n'
        '    "max_tokens": 100\n'
        "  }'\n"
        "```\n"
    )

    assert 'data-code-language="bash"' in html
    assert re.search(
        r'style="color: #ff6fae[^"]*">&quot;model&quot;</span>',
        html,
        flags=re.I,
    )
    assert re.search(
        r'style="color: #f2df6b[^"]*">&quot;gpt-5\.4-mini&quot;</span>',
        html,
        flags=re.I,
    )
    assert re.search(
        r'style="color: #b28cff[^"]*">100</span>',
        html,
        flags=re.I,
    )


@pytest.mark.basic
def test_markdown_renderer_live_theme_uses_color_code_style_and_unwraps_panels() -> None:
    renderer = MarkdownRenderer(theme="friendly_grayscale")
    html = renderer.render(
        "```bash\n"
        "curl -X POST https://openai.abstractframework.ai/v1/chat/completions \\\n"
        '  -H "Content-Type: application/json" \\\n'
        "  -d '{\n"
        '    \"model\": \"gpt-5.4-mini\",\n'
        '    \"max_tokens\": 100\n'
        "  }'\n"
        "```\n"
    )

    lowered = html.lower()
    assert "<pre><code class=\"language-bash\"><table" not in html
    assert 'data-code-language="bash"' in html
    assert "color: #ff6fae" in lowered
    assert '"color: #3b3b3b"' not in lowered


@pytest.mark.basic
def test_markdown_renderer_renders_recovered_nested_bullet_structure() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "**Key Story:** *Anthropic Surpasses OpenAI in Valuation*\n"
        "- Anthropic closed the largest private funding round in AI history\n"
        "- **Claude Opus 4.8** leads the model race\n"
        "- Google I/O & Microsoft Build dominated June launches:\n"
        "- Google released new Gemini family\n"
        "- Microsoft shipped 7 in-house models\n"
        "- NVIDIA open-sourced Cosmos 3\n"
    )

    assert re.search(
        r"<li>Google I/O &amp; Microsoft Build dominated June launches:\s*<ul>\s*"
        r"<li>Google released new Gemini family</li>\s*"
        r"<li>Microsoft shipped 7 in-house models</li>\s*</ul>\s*</li>",
        html,
    )
    assert "<li>NVIDIA open-sourced Cosmos 3</li>" in html


@pytest.mark.basic
def test_markdown_renderer_renders_heading_style_nested_bullet_structure() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "**Key Story:** *US-Iran Peace Deal Fragile as Strait of Hormuz Re-Closed*\n"
        "- **June 20, 2026:** Iran re-closed Strait of Hormuz, citing US/Israel ceasefire violations\n"
        "- **VP JD Vance** arrived in Switzerland (Zurich) for peace talks with Iranian negotiators\n"
        "- Oil prices soaring; 20,000 seafarers stranded\n"
        "- **Israel-Hezbollah conflict** added to emergency peace session agenda\n"
        "- **Ukraine War Update:**\n"
        "- Zelensky: Ukrainian FP drones now reach 3,000 km (hit Russia's Tyumen region)\n"
        "- Russian airstrike on Zaporizhzhia: 5 dead, 11 injured\n"
    )

    assert re.search(
        r"<li><strong>Ukraine War Update:</strong>\s*<ul>\s*"
        r"<li>Zelensky: Ukrainian FP drones now reach 3,000 km \(hit Russia's Tyumen region\)</li>\s*"
        r"<li>Russian airstrike on Zaporizhzhia: 5 dead, 11 injured</li>\s*</ul>\s*</li>",
        html,
    )


def _list_indents_by_text(html: str) -> dict[str, int | None]:
    app = QApplication.instance() or QApplication([])
    browser = QTextBrowser()
    browser.setHtml(html)
    document = browser.document()
    indents: dict[str, int | None] = {}
    block = document.begin()
    while block.isValid():
        text = str(block.text() or "").strip()
        if text:
            text_list = block.textList()
            indents[text] = None if text_list is None else text_list.format().indent()
        block = block.next()
    assert app is not None
    return indents


@pytest.mark.basic
def test_markdown_renderer_qt_document_keeps_nested_list_depths() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "- Google I/O & Microsoft Build dominated June launches:\n"
        "  - Google released new Gemini family\n"
        "  - Microsoft shipped 7 in-house models\n"
        "- NVIDIA open-sourced Cosmos 3\n"
    )

    indents = _list_indents_by_text(html)

    assert indents["Google I/O & Microsoft Build dominated June launches:"] == 1
    assert indents["Google released new Gemini family"] == 2
    assert indents["Microsoft shipped 7 in-house models"] == 2
    assert indents["NVIDIA open-sourced Cosmos 3"] == 1


@pytest.mark.basic
def test_markdown_renderer_qt_document_recovers_heading_style_nested_depths() -> None:
    renderer = MarkdownRenderer()
    html = renderer.render(
        "- **Ukraine War Update:**\n"
        "- Zelensky: Ukrainian FP drones now reach 3,000 km (hit Russia's Tyumen region)\n"
        "- Russian airstrike on Zaporizhzhia: 5 dead, 11 injured\n"
        "- **FIFA World Cup 2026:**\n"
        "- First expanded 48-team tournament preparations continue\n"
    )

    indents = _list_indents_by_text(html)

    assert indents["Ukraine War Update:"] == 1
    assert (
        indents[
            "Zelensky: Ukrainian FP drones now reach 3,000 km (hit Russia's Tyumen region)"
        ]
        == 2
    )
    assert indents["Russian airstrike on Zaporizhzhia: 5 dead, 11 injured"] == 2
    assert indents["FIFA World Cup 2026:"] == 1


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
def test_markdown_renderer_mermaid_png_does_not_clip_bright_text_into_top_edge() -> (
    None
):
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
        "```mermaid\n" "sequenceDiagram\n" "    Alice->>Bob: Hello Bob\n" "```\n"
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
