"""Convert assistant markdown replies into text worth speaking.

The transcript renders markdown; TTS must not read it raw — "### **Title**"
becomes hash-hash-hash noise, URLs are unpronounceable, and markdown-heavy
blocks defeat the synthesizer's sentence segmentation (live 2026-07-28: the
first stream segment swallowed a whole heading block, pushing first audio out
by several seconds). This module reduces markdown to plain prose and makes
sure every block ends with sentence punctuation so streaming synthesis can
split early and speak fast.
"""

from __future__ import annotations

import re


_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]*)`")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
# The label may be EMPTY ("[](url)"): requiring one character left the raw
# brackets in the spoken text ("bracket bracket paren link").
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")
_BARE_URL_RE = re.compile(r"https?://\S+")
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>\s?")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+")
_HR_RE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")
_EMPHASIS_RE = re.compile(r"(\*{1,3}|_{1,3}|~~)(?=\S)(.+?)(?<=\S)\1")
_TABLE_DIVIDER_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
# Pictographs/emoji and joiners; deliberately narrow so accented and
# non-Latin PROSE is never touched.
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # pictographs, emoticons, symbols
    "\U00002600-\U000027BF"  # misc symbols + dingbats
    "\U0001F1E6-\U0001F1FF"  # regional indicators (flags)
    "\U0000FE0E\U0000FE0F"   # variation selectors
    "\U0000200D"             # zero-width joiner
    "\U000020E3"             # combining keycap
    "]+"
)
_SENTENCE_END = (".", "!", "?", ":", ";", ",", "…")


def _strip_emphasis(text: str) -> str:
    # Nested emphasis unwraps one layer per pass ("***bold italic***").
    for _ in range(3):
        stripped = _EMPHASIS_RE.sub(r"\2", text)
        if stripped == text:
            break
        text = stripped
    return text


def _table_row_to_prose(line: str) -> str:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    cells = [cell for cell in cells if cell]
    return ", ".join(cells)


def speech_plain_text(markdown: str) -> str:
    """Return the spoken-prose version of a markdown reply.

    Guarantees: no markdown syntax, no URLs/emoji, and every retained block
    ends with punctuation (so a heading or list item forms its own short
    sentence for the synthesizer instead of fusing into the next block).
    """
    text = str(markdown or "")
    if not text.strip():
        return ""

    # Reading code aloud is noise; say that something was omitted instead.
    text = _FENCED_CODE_RE.sub(" Code block omitted. ", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _IMAGE_RE.sub(r"\1", text)
    text = _LINK_RE.sub(lambda m: m.group(1) or " link ", text)
    text = _AUTOLINK_RE.sub(" link ", text)
    text = _BARE_URL_RE.sub(" link ", text)

    lines_out: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line
        if _HR_RE.match(line) or _TABLE_DIVIDER_RE.match(line):
            continue
        line = _BLOCKQUOTE_RE.sub("", line)
        is_block = bool(_HEADER_RE.match(line) or _BULLET_RE.match(line))
        line = _HEADER_RE.sub("", line)
        line = _BULLET_RE.sub("", line)
        if "|" in line and line.strip().startswith("|"):
            line = _table_row_to_prose(line)
            is_block = True
        line = _strip_emphasis(line)
        line = _EMOJI_RE.sub("", line)
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            lines_out.append("")
            continue
        # Standalone blocks (headings, list items, table rows) become their
        # own short sentences: early segmentation = fast first audio.
        if is_block and not line.endswith(_SENTENCE_END):
            line += "."
        lines_out.append(line)

    prose = "\n".join(lines_out)
    prose = re.sub(r"\n{3,}", "\n\n", prose).strip()
    return prose
