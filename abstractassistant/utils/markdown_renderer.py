"""Markdown rendering helpers for AbstractAssistant."""

from __future__ import annotations

from dataclasses import dataclass
import html
import importlib.util
import json
import re

import markdown
from pygments.formatters import HtmlFormatter

from .mermaid_renderer import mermaid_block_to_data_uri


_MARKDOWNISH_RE = re.compile(
    r"(^#{1,6}\s|^>\s|```|`[^`]+`|"
    r"\[[^\]]+\]\([^)]+\)|!\[[^\]]*\]\([^)]+\)|\*\*[^*\n]+\*\*|"
    r"__[^_\n]+__|^\|.*\|.*$|^(-{3,}|\*{3,}|_{3,})\s*$)",
    flags=re.M,
)
_YAML_KEY_RE = re.compile(r"^[A-Za-z0-9_.\"'/-]+\s*:\s*(?:.*)?$")
_YAML_LIST_RE = re.compile(r"^-\s+.+$")
_MERMAID_FENCE_RE = re.compile(r"(^|\n)```mermaid[^\n]*\n(?P<code>.*?)(?:\n```)(?=\n|$)", flags=re.I | re.S)


@dataclass(frozen=True)
class MarkdownRenderBlock:
    kind: str
    text: str = ""
    data_uri: str = ""


def _try_parse_json_block(text: str) -> str | None:
    trimmed = str(text or "").strip()
    if not trimmed or trimmed.startswith("```"):
        return None
    if not (
        (trimmed.startswith("{") and trimmed.endswith("}"))
        or (trimmed.startswith("[") and trimmed.endswith("]"))
    ):
        return None
    try:
        parsed = json.loads(trimmed)
    except Exception:
        return None
    return json.dumps(parsed, indent=2, ensure_ascii=False)


def _looks_like_yaml_block(text: str) -> bool:
    trimmed = str(text or "").strip()
    if not trimmed or trimmed.startswith("```") or _MARKDOWNISH_RE.search(trimmed):
        return False

    lines = [line.rstrip() for line in trimmed.splitlines() if line.strip()]
    if len(lines) < 2:
        return False

    structured_lines = 0
    key_lines = 0
    for line in lines:
        stripped = line.strip()
        if stripped in {"---", "..."}:
            structured_lines += 1
            continue
        if stripped.startswith("#"):
            continue
        if _YAML_KEY_RE.match(stripped):
            key_lines += 1
            structured_lines += 1
            continue
        if _YAML_LIST_RE.match(stripped):
            structured_lines += 1
            continue
        if line[:1].isspace() and stripped:
            structured_lines += 1
            continue
        return False
    return key_lines > 0 and structured_lines > 1


def _prepare_markdown_source(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return ""

    parsed_json = _try_parse_json_block(normalized)
    if parsed_json is not None:
        return f"```json\n{parsed_json}\n```"

    if _looks_like_yaml_block(normalized):
        return f"```yaml\n{normalized.strip()}\n```"

    return normalized


def _replace_mermaid_fences(text: str) -> str:
    parts: list[str] = []
    for block in split_markdown_mermaid_blocks(text):
        if block.kind == "mermaid" and block.data_uri:
            parts.append(
                '\n<div class="mermaid-diagram">'
                f'<img src="{block.data_uri}" alt="Rendered Mermaid flowchart" />'
                "</div>\n"
            )
            continue
        parts.append(block.text)
    return "".join(parts)


def split_markdown_mermaid_blocks(text: str) -> list[MarkdownRenderBlock]:
    raw = str(text or "")
    if not raw:
        return []

    blocks: list[MarkdownRenderBlock] = []
    last_pos = 0

    for match in _MERMAID_FENCE_RE.finditer(raw):
        code = str(match.group("code") or "").strip()
        if not code:
            continue
        data_uri = mermaid_block_to_data_uri(code)
        if not data_uri:
            continue
        before = raw[last_pos:match.start()]
        if before:
            blocks.append(MarkdownRenderBlock(kind="markdown", text=before))
        blocks.append(MarkdownRenderBlock(kind="mermaid", text=code, data_uri=data_uri))
        last_pos = match.end()

    tail = raw[last_pos:]
    if tail or not blocks:
        blocks.append(MarkdownRenderBlock(kind="markdown", text=tail if blocks else raw))
    return blocks


class MarkdownRenderer:
    """Markdown renderer with fenced-code and table support."""

    def __init__(self, theme: str = "monokai"):
        self.theme = theme
        self.formatter = HtmlFormatter(
            style=theme,
            cssclass="codehilite",
            noclasses=False,
            linenos=False,
        )
        self.extensions = [
            "fenced_code",
            "tables",
            "nl2br",
            "sane_lists",
        ]
        self.extension_configs = {}
        if self._has_pymdownx():
            self.extensions.extend(
                [
                    "pymdownx.highlight",
                    "pymdownx.inlinehilite",
                    "pymdownx.superfences",
                ]
            )
            self.extension_configs.update(
                {
                    "pymdownx.highlight": {
                        "css_class": "codehilite",
                        "pygments_style": theme,
                        "linenums": False,
                        "guess_lang": False,
                    },
                    "pymdownx.superfences": {
                        "preserve_tabs": True,
                    },
                }
            )
        else:
            self.extensions.append("codehilite")
            self.extension_configs["codehilite"] = {
                "css_class": "codehilite",
                "pygments_style": theme,
                "linenums": False,
                "guess_lang": False,
            }

    @staticmethod
    def _has_pymdownx() -> bool:
        return importlib.util.find_spec("pymdownx") is not None

    def render(self, markdown_text: str) -> str:
        try:
            prepared = _replace_mermaid_fences(_prepare_markdown_source(markdown_text))
            md = markdown.Markdown(
                extensions=self.extensions,
                extension_configs=self.extension_configs,
                output_format="html5",
            )
            html_content = md.convert(prepared)
            pygments_css = self.formatter.get_style_defs(".codehilite")
            full_html = f"""
            <style>
            {self._get_base_css()}
            {pygments_css}
            </style>
            <div class="markdown-content">
            {html_content}
            </div>
            """
            return full_html
        except Exception as e:
            safe_text = html.escape(str(markdown_text or ""))
            safe_error = html.escape(str(e))
            return f"<pre>{safe_text}</pre><p><em>Markdown rendering error: {safe_error}</em></p>"

    def _get_base_css(self) -> str:
        return """
        .markdown-content {
            font-family: "Helvetica Neue", "Helvetica", Arial;
            font-size: 14px;
            line-height: 1.6;
            color: #e2e8f0;
            background: transparent;
            padding: 16px;
        }
        
        .markdown-content h1, .markdown-content h2, .markdown-content h3,
        .markdown-content h4, .markdown-content h5, .markdown-content h6 {
            color: #f8fafc;
            margin-top: 24px;
            margin-bottom: 16px;
            font-weight: 600;
            line-height: 1.25;
        }

        .markdown-content h1 {
            font-size: 2.2em;
            border-bottom: 2px solid #4a5568;
            padding-bottom: 8px;
        }

        .markdown-content h2 {
            font-size: 1.7em;
            border-bottom: 1px solid #4a5568;
            padding-bottom: 4px;
        }

        .markdown-content h3 {
            font-size: 1.4em;
            color: #cbd5e0;
        }
        
        .markdown-content h4, .markdown-content h5, .markdown-content h6 {
            font-size: 1em;
            color: #a0aec0;
        }
        
        .markdown-content p {
            margin-bottom: 16px;
        }
        
        .markdown-content ul, .markdown-content ol {
            margin-bottom: 16px;
            padding-left: 24px;
        }
        
        .markdown-content li {
            margin-bottom: 4px;
        }

        .markdown-content img {
            max-width: 100%;
            width: auto;
            height: auto;
            max-height: 180px;
            border-radius: 8px;
        }

        .markdown-content .mermaid-diagram {
            margin: 12px 0 16px 0;
            padding: 12px;
            border-radius: 12px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.95), rgba(12, 18, 28, 0.98));
        }

        .markdown-content .mermaid-diagram img {
            display: block;
            width: 100%;
            max-width: 100%;
            max-height: none;
            height: auto;
            border-radius: 0;
        }

        .markdown-content code {
            background: #2d3748;
            color: #e2e8f0;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
            font-size: 0.9em;
        }
        
        .markdown-content pre {
            background: #1a202c;
            color: #e2e8f0;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            border: 1px solid #4a5568;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .markdown-content pre code {
            background: transparent;
            padding: 0;
            border-radius: 0;
            white-space: inherit;
        }

        .markdown-content blockquote {
            border-left: 4px solid #4299e1;
            padding-left: 16px;
            margin: 16px 0;
            color: #cbd5e0;
            font-style: italic;
        }
        
        .markdown-content table {
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 16px;
        }

        .markdown-content th, .markdown-content td {
            border: 1px solid #4a5568;
            padding: 8px 12px;
            text-align: left;
        }
        
        .markdown-content th {
            background: #2d3748;
            font-weight: 600;
        }
        
        .markdown-content tr:nth-child(even) {
            background: rgba(45, 55, 72, 0.3);
        }
        
        .markdown-content a {
            color: #63b3ed;
            text-decoration: none;
        }
        
        .markdown-content a:hover {
            color: #90cdf4;
            text-decoration: underline;
        }
        
        .markdown-content strong {
            font-weight: 600;
            color: #f7fafc;
        }
        
        .markdown-content em {
            font-style: italic;
            color: #e2e8f0;
        }
        
        .markdown-content hr {
            border: none;
            border-top: 2px solid #4a5568;
            margin: 24px 0;
        }
        
        /* Syntax highlighting adjustments for dark theme */
        .highlight {
            background: #1a202c !important;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
            border: 1px solid #4a5568;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
        }

        .highlight pre {
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            margin: 0 !important;
            white-space: inherit !important;
        }
        """


# Global instance for easy access
markdown_renderer = MarkdownRenderer(theme="monokai")


def render_markdown(text: str) -> str:
    """Convenience function to render markdown text.
    
    Args:
        text: Markdown text to render
        
    Returns:
        HTML string with embedded CSS
    """
    return markdown_renderer.render(text)
