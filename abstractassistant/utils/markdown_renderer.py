"""Markdown rendering helpers for AbstractAssistant."""

from __future__ import annotations

from dataclasses import dataclass
import html
from html.parser import HTMLParser
import json
import re

from markdown_it import MarkdownIt
from pygments import highlight as pygments_highlight
from pygments.filter import Filter
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.style import Style
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
    Whitespace,
)
from pygments.util import ClassNotFound

from .mermaid_renderer import mermaid_block_to_data_uri

_MARKDOWNISH_RE = re.compile(
    r"(^#{1,6}\s|^>\s|```|`[^`]+`|"
    r"\[[^\]]+\]\([^)]+\)|!\[[^\]]*\]\([^)]+\)|\*\*[^*\n]+\*\*|"
    r"__[^_\n]+__|^\|.*\|.*$|^(-{3,}|\*{3,}|_{3,})\s*$)",
    flags=re.M,
)
_YAML_KEY_RE = re.compile(r"^[A-Za-z0-9_.\"'/-]+\s*:\s*(?:.*)?$")
_YAML_LIST_RE = re.compile(r"^-\s+.+$")
_MERMAID_FENCE_RE = re.compile(
    r"(^|\n)```mermaid[^\n]*\n(?P<code>.*?)(?:\n```)(?=\n|$)", flags=re.I | re.S
)
_LIST_ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<marker>[-+*]|\d+[.)])\s+(?P<body>.*\S)\s*$"
)
_BARE_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>'\"]+")
_SHELL_DATA_FLAG_RE = re.compile(r"(?:^|[ \t])(?:-d|--data(?:-raw|-binary)?)\s+")
_AUTOLINK_SKIP_TAGS = {"a", "code", "pre", "script", "style"}
_SHELL_LANGUAGES = {"bash", "shell", "sh", "zsh", "console"}
_JSONISH_LANGUAGES = {"json", "jsonc"}
_APP_CODE_THEMES = {"monokai", "friendly_grayscale"}
_WRAPPED_CODE_PANEL_RE = re.compile(
    r"<pre><code(?:\s+class=\"[^\"]*\")?>(?P<panel><table\b[^>]*class=\"codepanel\"[\s\S]*?</table>)</code></pre>",
    flags=re.I,
)
# Menlo-first: 'SF Mono' is not resolvable in Qt on macOS (see AGENTS.md,
# 2026-02-22 font stack note), so leading with it forces fallback scanning.
_CODE_MONO_FONT = (
    "'Menlo', 'Monaco', 'Consolas', 'Liberation Mono', monospace"
)
_CODE_PANEL_STYLE = (
    "margin: 10px 0 14px 0; "
    "border-collapse: collapse; "
    "border-spacing: 0; "
    "border: none;"
)
_CODE_PANEL_ACCENT_BG = "#344b73"
_CODE_PANEL_BODY_BG = "#101722"
_CODE_PANEL_CELL_STYLE = (
    "padding: 14px 16px !important; "
    "background-color: #101722 !important; "
    "border: none !important; "
    "text-align: left; "
    "vertical-align: top;"
)
_CODE_BLOCK_PRE_STYLE = (
    "margin: 0; "
    "padding: 0; "
    "background-color: transparent; "
    "border: none; "
    "color: #edf2f8; "
    f"font-family: {_CODE_MONO_FONT}; "
    "font-size: 0.85em; "
    "line-height: 1.4; "
    "white-space: pre-wrap; "
    "overflow-wrap: anywhere; "
    "word-break: break-word;"
)
_CODE_BLOCK_CODE_STYLE = (
    f"font-family: {_CODE_MONO_FONT}; "
    "font-size: inherit; "
    "line-height: inherit; "
    "color: #edf2f8; "
    "font-weight: 400; "
    "background: transparent; "
    "white-space: inherit;"
)
_SHELL_JSON_QUOTE_STYLE = "color: #d7dee9;"


class _AbstractAssistantCodeStyle(Style):
    background_color = "#0f1520"
    default_style = ""
    styles = {
        Text: "#edf2f8",
        Whitespace: "#edf2f8",
        Comment: "italic #7f8da1",
        Comment.Preproc: "#7bdcff",
        Keyword: "bold #7bdcff",
        Keyword.Constant: "#7bdcff",
        Keyword.Namespace: "#7bdcff",
        Literal: "#f2df6b",
        Literal.Date: "#f2df6b",
        String: "#f2df6b",
        String.Double: "#f2df6b",
        String.Single: "#f2df6b",
        Number: "#b28cff",
        Operator: "#aebdd2",
        Punctuation: "#dbe3ef",
        Name.Builtin: "#8bd5ff",
        Name.Function: "#8bd5ff",
        Name.Class: "bold #8bd5ff",
        Name.Tag: "bold #ff6fae",
        Name.Attribute: "#ff6fae",
        Name.Variable: "#ff6fae",
        Name.Variable.Instance: "#ff6fae",
        Name.Label: "#ff6fae",
        Generic.Heading: "bold #edf2f8",
        Generic.Subheading: "bold #edf2f8",
        Generic.Output: "#c8d2df",
        Error: "#ff8f8f",
    }


# Words that introduce ANOTHER command, so the next word is still a command.
_SHELL_COMMAND_WRAPPERS = frozenset(
    {"sudo", "doas", "env", "time", "nohup", "xargs", "command", "exec", "nice", "watch", "then", "do", "else"}
)
# After any of these, the next word starts a new command.
_SHELL_COMMAND_BREAKERS = frozenset({"|", "||", "&&", ";", ";;", "&", "(", ")", "{", "}", "!", "|&"})
_SHELL_FLAG_RE = re.compile(r"^-{1,2}[A-Za-z0-9][A-Za-z0-9-]*$")
_SHELL_COMMAND_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.+-]*$")
_SHELL_REDIRECT_RE = re.compile(r"^(&?>>|&?>|<<<|<<|<|\d?>>|\d?>)(.*)$", re.S)


class _ShellReadabilityFilter(Filter):
    """Re-tag the parts of a shell command that Pygments leaves as plain text.

    The bash lexer emits ``Token.Text`` for command names, sub-commands, flags
    and arguments alike — on a real pipeline that is 16 of 26 tokens, so the
    block renders in one flat colour while the same style makes Python
    perfectly legible. This tags what a reader actually scans for: the command
    being run, its flags, and its redirections.
    """

    def filter(self, lexer, stream):  # noqa: A003 (Pygments API)
        expect_command = True
        for ttype, value in stream:
            if ttype not in Text or not value.strip():
                if ttype in Punctuation or ttype in Operator:
                    if value.strip() in _SHELL_COMMAND_BREAKERS:
                        expect_command = True
                elif "\n" in value and ttype in Text:
                    # A real newline ends the command; a backslash-newline
                    # (String.Escape) continues it.
                    expect_command = True
                yield ttype, value
                continue

            lead_len = len(value) - len(value.lstrip())
            trail_len = len(value) - len(value.rstrip())
            lead = value[:lead_len]
            word = value[lead_len : len(value) - trail_len]
            trail = value[len(value) - trail_len :] if trail_len else ""
            if lead:
                yield ttype, lead

            redirect = _SHELL_REDIRECT_RE.match(word)
            if redirect:
                operator, rest = redirect.groups()
                yield Operator, operator
                if rest:
                    yield ttype, rest
                expect_command = False
            elif _SHELL_FLAG_RE.match(word):
                yield Name.Attribute, word
            elif expect_command and _SHELL_COMMAND_RE.match(word):
                yield Name.Function, word
                expect_command = word in _SHELL_COMMAND_WRAPPERS
            else:
                yield ttype, word
                expect_command = False

            if trail:
                yield ttype, trail
                if "\n" in trail:
                    expect_command = True


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

    return _normalize_loose_markdown_lists(normalized)


def _normalize_loose_markdown_lists(text: str) -> str:
    lines = str(text or "").split("\n")
    normalized: list[str] = []
    in_fence = False
    active_nested_prefixes: tuple[str, ...] = ()
    active_nested_indent = ""
    active_heading_indent = ""
    pending_parent: tuple[tuple[str, ...], str, bool] | None = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            normalized.append(line)
            active_nested_prefixes = ()
            active_nested_indent = ""
            active_heading_indent = ""
            pending_parent = None
            continue
        if in_fence:
            normalized.append(line)
            continue

        match = _LIST_ITEM_RE.match(line)
        if not match:
            active_nested_prefixes = ()
            active_nested_indent = ""
            active_heading_indent = ""
            pending_parent = None
            normalized.append(line)
            continue

        indent = str(match.group("indent") or "")
        marker = str(match.group("marker") or "-")
        body = str(match.group("body") or "")
        nested_indent = _sublist_indent(indent, marker)

        if pending_parent and not indent:
            prefixes, candidate_indent, force_heading_children = pending_parent
            if force_heading_children or (
                prefixes and _line_starts_with_any_prefix(body, prefixes)
            ):
                active_nested_prefixes = () if force_heading_children else prefixes
                active_nested_indent = candidate_indent
                active_heading_indent = (
                    candidate_indent if force_heading_children else ""
                )
                indent = candidate_indent
                line = f"{indent}{marker} {body}"
            pending_parent = None
        elif active_heading_indent and not indent:
            if _body_has_trailing_colon(body) and _is_heading_like_list_label(body):
                active_heading_indent = ""
                active_nested_indent = ""
            else:
                indent = active_heading_indent
                line = f"{indent}{marker} {body}"
        elif active_nested_prefixes and not indent:
            if _line_starts_with_any_prefix(body, active_nested_prefixes):
                indent = active_nested_indent
                line = f"{indent}{marker} {body}"
            else:
                active_nested_prefixes = ()
                active_nested_indent = ""
                active_heading_indent = ""

        if not indent and normalized and normalized[-1].strip():
            previous = normalized[-1].strip()
            if not _LIST_ITEM_RE.match(previous) and not previous.startswith(
                (">", "```")
            ):
                normalized.append("")

        normalized.append(line)

        pending_parent = None
        if not indent and _body_has_trailing_colon(body):
            prefixes = _extract_nested_list_prefixes(body)
            if _is_heading_like_list_label(body):
                pending_parent = ((), nested_indent, True)
            elif prefixes:
                pending_parent = (prefixes, nested_indent, False)

    return "\n".join(normalized)


def _sublist_indent(indent: str, marker: str) -> str:
    return f"{indent}{' ' * (len(str(marker or '-')) + 1)}"


def _extract_nested_list_prefixes(body: str) -> tuple[str, ...]:
    plain = re.sub(r"[*_`~]+", "", str(body or "")).strip().rstrip(":").strip()
    if not plain:
        return ()
    parts = [
        segment.strip()
        for segment in re.split(r"\s+(?:and|or)\s+|[,&/|]", plain)
        if segment.strip()
    ]
    prefixes: list[str] = []
    for part in parts:
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", part)
        if not words:
            continue
        token = words[0].strip("-_/").lower()
        if token and token not in prefixes:
            prefixes.append(token)
    return tuple(prefixes)


def _body_has_trailing_colon(body: str) -> bool:
    plain = re.sub(r"[*_`~]+", "", str(body or "")).strip()
    return plain.endswith(":")


def _is_heading_like_list_label(body: str) -> bool:
    plain = re.sub(r"[*_`~]+", "", str(body or "")).strip()
    if not plain.endswith(":"):
        return False
    heading = plain.rstrip(":").strip()
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", heading)
    return bool(words) and len(words) <= 4


def _line_starts_with_any_prefix(body: str, prefixes: tuple[str, ...]) -> bool:
    plain = re.sub(r"[*_`~]+", "", str(body or "")).lstrip()
    folded = plain.lower()
    for prefix in prefixes:
        if folded == prefix:
            return True
        if folded.startswith(prefix + " "):
            return True
        if folded.startswith(prefix + ":"):
            return True
        if folded.startswith(prefix + "’") or folded.startswith(prefix + "'"):
            return True
    return False


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


def _split_url_trailing_punctuation(url: str) -> tuple[str, str]:
    link = str(url or "")
    trailing = ""
    while link and link[-1] in ".,;:!":
        trailing = link[-1] + trailing
        link = link[:-1]
    for opening, closing in (("(", ")"), ("[", "]"), ("{", "}")):
        while link.endswith(closing) and link.count(closing) > link.count(opening):
            trailing = link[-1] + trailing
            link = link[:-1]
    return link, trailing


def _autolink_text_node(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return ""

    rendered: list[str] = []
    pos = 0
    for match in _BARE_URL_RE.finditer(raw):
        rendered.append(html.escape(raw[pos : match.start()], quote=False))
        url, trailing = _split_url_trailing_punctuation(match.group(0))
        if not url:
            rendered.append(html.escape(match.group(0), quote=False))
            pos = match.end()
            continue
        href = url if re.match(r"(?i)^https?://", url) else f"https://{url}"
        safe_href = html.escape(href, quote=True)
        safe_label = html.escape(url, quote=False)
        rendered.append(f'<a href="{safe_href}">{safe_label}</a>')
        rendered.append(html.escape(trailing, quote=False))
        pos = match.end()
    rendered.append(html.escape(raw[pos:], quote=False))
    return "".join(rendered)


class _HtmlTextAutolinker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self._text_buffer: list[str] = []
        self._skip_depth = 0

    def result(self) -> str:
        self._flush_text()
        return "".join(self.parts)

    def _flush_text(self) -> None:
        if not self._text_buffer:
            return
        raw = "".join(self._text_buffer)
        self._text_buffer = []
        if self._skip_depth > 0:
            self.parts.append(raw)
            return
        self.parts.append(_autolink_text_node(html.unescape(raw)))

    def handle_starttag(self, tag: str, attrs) -> None:
        self._flush_text()
        raw = self.get_starttag_text()
        self.parts.append(raw if raw is not None else f"<{tag}>")
        if str(tag or "").lower() in _AUTOLINK_SKIP_TAGS:
            self._skip_depth += 1

    def handle_startendtag(self, tag: str, attrs) -> None:
        self._flush_text()
        raw = self.get_starttag_text()
        self.parts.append(raw if raw is not None else f"<{tag} />")

    def handle_endtag(self, tag: str) -> None:
        self._flush_text()
        self.parts.append(f"</{tag}>")
        if str(tag or "").lower() in _AUTOLINK_SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        self._text_buffer.append(str(data or ""))

    def handle_entityref(self, name: str) -> None:
        self._text_buffer.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._text_buffer.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._flush_text()
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._flush_text()
        self.parts.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._flush_text()
        self.parts.append(f"<?{data}>")


def _autolink_html_text(html_content: str) -> str:
    parser = _HtmlTextAutolinker()
    try:
        parser.feed(str(html_content or ""))
        parser.close()
        return parser.result()
    except Exception:
        return str(html_content or "")


def _unwrap_generated_code_panels(html_content: str) -> str:
    raw = str(html_content or "")
    if not raw or "codepanel" not in raw:
        return raw
    return _WRAPPED_CODE_PANEL_RE.sub(lambda match: match.group("panel"), raw)


def _normalized_code_language(lang_name: str, code: str) -> str:
    raw = str(lang_name or "").strip().lower()
    alias_map = {
        "shell-session": "bash",
        "text/plain": "text",
        "json5": "json",
    }
    language = alias_map.get(raw, raw)
    if not language:
        if _looks_like_json_code(code):
            return "json"
        if _looks_like_shell_command(code):
            return "bash"
        return "text"
    if language in _JSONISH_LANGUAGES:
        return "json"
    if language in _SHELL_LANGUAGES:
        return "bash"
    return language


def _looks_like_json_code(code: str) -> bool:
    trimmed = str(code or "").strip()
    if not trimmed:
        return False
    if not (
        (trimmed.startswith("{") and trimmed.endswith("}"))
        or (trimmed.startswith("[") and trimmed.endswith("]"))
    ):
        return False
    try:
        json.loads(trimmed)
    except Exception:
        return False
    return True


def _looks_like_shell_command(code: str) -> bool:
    first_line = (
        str(code or "").strip().splitlines()[0] if str(code or "").strip() else ""
    )
    return bool(
        re.match(
            r"^(?:[$#]\s*)?(?:curl|wget|http|httpie|python|python3|node|npm|pnpm|yarn)\b",
            first_line,
        )
    )


def _find_balanced_json_end(text: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escape = False
    for index in range(int(start or 0), len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
            if depth < 0:
                return None
    return None


def _split_shell_embedded_json_payload(code: str) -> tuple[str, str, str, str] | None:
    raw = str(code or "")
    for match in _SHELL_DATA_FLAG_RE.finditer(raw):
        quote_index = match.end()
        if quote_index >= len(raw):
            continue
        quote = raw[quote_index]
        if quote not in {"'", '"'}:
            continue
        json_start = quote_index + 1
        if json_start >= len(raw) or raw[json_start] != "{":
            continue
        json_end = _find_balanced_json_end(raw, json_start)
        if json_end is None or json_end >= len(raw) or raw[json_end] != quote:
            continue
        return raw[:quote_index], quote, raw[json_start:json_end], raw[json_end:]
    return None


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
        before = raw[last_pos : match.start()]
        if before:
            blocks.append(MarkdownRenderBlock(kind="markdown", text=before))
        blocks.append(MarkdownRenderBlock(kind="mermaid", text=code, data_uri=data_uri))
        last_pos = match.end()

    tail = raw[last_pos:]
    if tail or not blocks:
        blocks.append(
            MarkdownRenderBlock(kind="markdown", text=tail if blocks else raw)
        )
    return blocks


def _themed_panel(fragment: str) -> str:
    """A colour fragment of the code panel, in the active palette."""
    from ..retint import retint_stylesheet
    from ..theme import DEFAULT_THEME, THEME

    return retint_stylesheet(str(fragment or ""), source=DEFAULT_THEME, target=THEME)


class MarkdownRenderer:
    """Markdown renderer with CommonMark/GFM parsing for Qt rich text."""

    def __init__(self, theme: str = "monokai"):
        self.theme = theme
        formatter_style = (
            _AbstractAssistantCodeStyle if theme in _APP_CODE_THEMES else theme
        )
        self.formatter = HtmlFormatter(
            style=formatter_style,
            cssclass="codehilite",
            noclasses=True,
            linenos=False,
            nowrap=True,
        )
        self._markdown = MarkdownIt(
            "gfm-like",
            {
                "breaks": True,
                "html": True,
                "linkify": False,
                "highlight": self._highlight_code,
            },
        )

    def _highlight_segment(self, code: str, language: str) -> str:
        try:
            lexer = (
                get_lexer_by_name(language, stripall=False)
                if language
                else TextLexer(stripall=False)
            )
        except ClassNotFound:
            lexer = TextLexer(stripall=False)
        if str(language or "").lower() in _SHELL_LANGUAGES:
            lexer.add_filter(_ShellReadabilityFilter())
        return pygments_highlight(code, lexer, self.formatter)

    def _render_shell_with_embedded_json(self, code: str, language: str) -> str | None:
        segments = _split_shell_embedded_json_payload(code)
        if segments is None:
            return None
        prefix, quote, payload, suffix = segments
        open_quote = html.escape(quote)
        close_quote = html.escape(str(suffix[:1] or quote))
        trailing = suffix[1:] if suffix[:1] == quote else suffix
        return (
            self._highlight_segment(prefix, language)
            + f'<span style="{_SHELL_JSON_QUOTE_STYLE}">{open_quote}</span>'
            + self._highlight_segment(payload, "json")
            + f'<span style="{_SHELL_JSON_QUOTE_STYLE}">{close_quote}</span>'
            + self._highlight_segment(trailing, language)
        )

    def _code_block_html(self, highlighted: str, language: str) -> str:
        safe_language = html.escape(str(language or "text"), quote=True)
        return (
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'class="codepanel" data-code-language="{safe_language}" style="{_CODE_PANEL_STYLE}">'
            f"<tr>"
            f'<td width="4" bgcolor="{_themed_panel(_CODE_PANEL_ACCENT_BG)}"></td>'
            f'<td bgcolor="{_themed_panel(_CODE_PANEL_BODY_BG)}" style="{_themed_panel(_CODE_PANEL_CELL_STYLE)}">'
            f'<pre class="codehilite" style="{_themed_panel(_CODE_BLOCK_PRE_STYLE)}">'
            f'<code style="{_themed_panel(_CODE_BLOCK_CODE_STYLE)}">{highlighted}</code>'
            "</pre></td></tr></table>"
        )

    def _highlight_code(self, code: str, lang_name: str, _attrs: str) -> str:
        language = _normalized_code_language(
            re.split(r"[\s,{]+", str(lang_name or "").strip(), maxsplit=1)[0],
            code,
        )
        if language == "bash":
            highlighted = self._render_shell_with_embedded_json(code, language)
            if highlighted is None:
                highlighted = self._highlight_segment(code, language)
        else:
            highlighted = self._highlight_segment(code, language)
        return self._code_block_html(highlighted, language)

    def render(self, markdown_text: str) -> str:
        try:
            prepared = _replace_mermaid_fences(_prepare_markdown_source(markdown_text))
            html_content = _autolink_html_text(
                _unwrap_generated_code_panels(self._markdown.render(prepared))
            )
            full_html = f"""
            <style>
            {self._get_base_css()}
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
        """The reply stylesheet, in the palette that is active right now.

        Markdown is rendered to HTML with its colours baked in, so a theme
        switch has to re-render the transcript — and this is what makes the
        re-render come out in the new palette. See `retint.py`.
        """
        from ..retint import retint_stylesheet
        from ..theme import DEFAULT_THEME, THEME

        return retint_stylesheet(self._base_css(), source=DEFAULT_THEME, target=THEME)

    def _base_css(self) -> str:
        return """
        .markdown-content {
            font-size: 13px;
            line-height: 1.45;
            color: #edf2f8;
            background: transparent;
            padding: 0;
        }
        
        .markdown-content h1, .markdown-content h2, .markdown-content h3,
        .markdown-content h4, .markdown-content h5, .markdown-content h6 {
            color: #f8fafc;
            margin-top: 14px;
            margin-bottom: 7px;
            font-weight: 600;
            line-height: 1.2;
        }

        .markdown-content h1 {
            font-size: 2.2em;
            border-bottom: 2px solid rgba(166, 187, 214, 0.30);
            padding-bottom: 5px;
        }

        .markdown-content h2 {
            font-size: 1.7em;
            border-bottom: 1px solid rgba(166, 187, 214, 0.30);
            padding-bottom: 3px;
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
            margin-bottom: 10px;
        }
        
        .markdown-content ul, .markdown-content ol {
            margin-bottom: 10px;
            padding-left: 20px;
        }

        .markdown-content ul ul,
        .markdown-content ul ol,
        .markdown-content ol ul,
        .markdown-content ol ol {
            margin: 6px 0 0 0;
            padding-left: 12px;
        }

        .markdown-content ul ul {
            list-style-type: circle;
        }

        .markdown-content ul ul ul {
            list-style-type: square;
        }

        .markdown-content li {
            margin-bottom: 4px;
        }

        .markdown-content li ul,
        .markdown-content li ol {
            margin-top: 4px;
        }

        .markdown-content img {
            max-width: 100%;
            width: auto;
            height: auto;
            max-height: 180px;
            border-radius: 8px;
        }

        .markdown-content .mermaid-diagram {
            margin: 8px 0 10px 0;
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
            font-family: __CODE_MONO_FONT__;
            font-size: 1em;
            line-height: inherit;
        }
        
        .markdown-content pre {
            background: transparent;
            color: #edf2f8;
            padding: 0;
            border-radius: 0;
            margin: 0;
            border: none;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            word-break: break-word;
            font-family: __CODE_MONO_FONT__;
            font-size: 1em;
            line-height: 1.55;
        }

        .markdown-content pre code {
            background: transparent;
            padding: 0;
            border-radius: 0;
            white-space: inherit;
            color: inherit;
            font-size: inherit;
            line-height: inherit;
        }

        .markdown-content blockquote {
            border-left: 3px solid #79c7ff;
            padding-left: 16px;
            margin: 10px 0;
            color: #cbd5e0;
            font-style: italic;
        }
        
        .markdown-content table {
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 10px;
        }

        .markdown-content table.codepanel {
            margin: 10px 0 14px 0;
            border: none;
        }

        .markdown-content table.codepanel td,
        .markdown-content table.codepanel th {
            border: none;
            padding: 0;
            text-align: left;
            vertical-align: top;
        }

        .markdown-content th, .markdown-content td {
            border: 1px solid rgba(166, 187, 214, 0.30);
            padding: 8px 12px;
            text-align: left;
        }
        
        .markdown-content th {
            background: #2d3748;
            font-weight: 600;
        }
        
        .markdown-content a {
            color: #79c7ff;
            text-decoration: none;
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
            border-top: 2px solid rgba(166, 187, 214, 0.30);
            margin: 14px 0;
        }
        
        /* Syntax highlighting adjustments for dark theme */
        .codehilite {
            background: transparent !important;
            border-radius: 0;
            padding: 0;
            margin: 0;
            border: none;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            color: #edf2f8 !important;
        }

        .codehilite pre {
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            margin: 0 !important;
            white-space: inherit !important;
            color: inherit !important;
            font-size: inherit !important;
            line-height: inherit !important;
        }
        """.replace("__CODE_MONO_FONT__", _CODE_MONO_FONT)


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
