"""Links in an answer: what counts as one, and what a click is allowed to do.

Qt-free on purpose — detection and policy are the parts worth unit-testing, and
the renderer (HTML) and the palette (clicks) both consume them.

Two rules shape everything here:

1. THE TEXT IS WRITTEN BY A MODEL, and may be echoing a web page or a tool result.
   A link in an answer is therefore untrusted input. Opening a local file hands it
   to the OS, and for a whole family of types "open" means RUN (`.app`, `.command`,
   `.sh`, `.pkg`, `.workflow`, a `.webloc` that points anywhere…). So a click opens
   only kinds that are inert to open — media, documents, text — and REVEALS
   everything else in Finder, where the user can see what it is first. A `file://`
   URL naming another host is refused outright: following it would mount a share.

2. NOTHING HERE MAY BLOCK THE UI. Existence checks run while a message renders, on
   paths the model chose; a stat on an autofs or network mount can hang for a
   minute. Only paths under local, user-owned roots are ever touched at render
   time (`is_safe_to_stat`); everything else is decided when the user clicks.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

# Roots a local path must start with to be recognised in running prose. A bare
# `/` match would link `and/or`-style fragments, regex literals (`/foo/g`) and
# dates; a known root is what makes "/usr/bin/env" a path and "/g" not one.
_KNOWN_ROOTS: Tuple[str, ...] = (
    "/Users/",
    "/Applications/",
    "/Library/",
    "/System/",
    "/Volumes/",
    "/private/",
    "/tmp/",
    "/var/",
    "/etc/",
    "/opt/",
    "/usr/",
    "/bin/",
    "/sbin/",
    "/home/",
    "/mnt/",
    "/srv/",
    "~/",
)

# A path starts at a known root that is NOT glued to something that makes it a
# different thing: `host:/Users/…` is on another machine, `C:/Users/…` is Windows,
# `${HOME}/tmp/…` is a template tail, `a/Users/…` is mid-word. ASCII classes on
# purpose — `\w` is Unicode-aware, and "报告在/Users/…" has no space to offer.
_PATH_START_RE = re.compile(
    r"(?<![A-Za-z0-9_/~.\-:$}\\])(?:" + "|".join(re.escape(root) for root in _KNOWN_ROOTS) + r")"
)
_FILE_URL_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])file://[^\s<>\"'`]+")

# Where a candidate MUST end whatever the disk says.
_HARD_STOPS = frozenset('<>`|\n\r\t"“”')
_GLOB_CHARS = frozenset("*?")
# Where it PROBABLY ends: legal in a file name, but in prose far more often a
# separator. The disk gets the casting vote when it may be asked (see below).
_SOFT_STOPS = frozenset(" ,;'’‘—–→←⇒，。；：！？、）】」』》")

_TRAILING_PUNCTUATION = ".,;:!?"
_CLOSERS = {")": "(", "]": "[", "}": "{"}
_LINE_SUFFIX_RE = re.compile(r"^(?P<path>.+?)(?::\d+){1,2}:?$")
# Bidi overrides and control characters make a name DISPLAY as something else
# ("gpj.exe" tricks). Such a name is never offered as a link.
_DECEPTIVE_CHARS_RE = re.compile("[\u0000-\u001f\u007f\u200e\u200f\u202a-\u202e\u2066-\u2069]")

_MAX_PATH_CHARS = 1024  # PATH_MAX on macOS; also what bounds every loop below
_MAX_EXISTENCE_PROBES = 12

# Inert to open: the default app DISPLAYS these. Anything not listed is revealed.
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".ico"}
_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif"}
_DOCUMENT_EXT = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".pages", ".numbers", ".key", ".rtf", ".epub"}
_TEXT_EXT = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".xml", ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".scss",
    ".c", ".h", ".cpp", ".hpp", ".rs", ".go", ".java", ".kt", ".swift", ".rb", ".php", ".sql", ".tex",
    ".diff", ".patch", ".lock", ".env.example",
}
# `.html`/`.svg` render active content in a browser, and shell/script sources are
# one chmod away from a payload: they stay in the reveal bucket with the rest.

_OPENABLE_KINDS = {"image", "video", "audio", "document", "text"}
_CHIP_KINDS = {"image", "video", "audio", "document", "text"}


@dataclass(frozen=True)
class PathSpan:
    start: int
    end: int
    path: str  # as written (may start with "~/")


def expand_path(path: str) -> str:
    """`~` expanded and `..` collapsed — lexically, without touching the disk."""
    text = str(path or "").strip()
    if not text:
        return ""
    if text == "~" or text.startswith("~/"):
        text = str(Path.home()) + text[1:]
    return os.path.normpath(text)


def _strip_trailing(token: str) -> str:
    """Sentence punctuation and unbalanced closers off the end — in ONE pass.

    Counting brackets inside the loop made this quadratic: a model (or a page it
    quoted) emitting `/Users/x/y` followed by 80,000 `)` froze the GUI thread for
    seconds per render. Counts are taken once and adjusted as characters go.
    """
    text = token
    opened = {opener: text.count(opener) for opener in _CLOSERS.values()}
    closed = {closer: text.count(closer) for closer in _CLOSERS}
    end = len(text)
    while end > 0:
        ch = text[end - 1]
        if ch in _TRAILING_PUNCTUATION:
            end -= 1
            continue
        if ch in _CLOSERS and closed[ch] > opened[_CLOSERS[ch]]:
            closed[ch] -= 1
            end -= 1
            continue
        break
    return text[:end]


def _looks_like_path(token: str) -> bool:
    """A root alone (`/usr/`) or a single segment is a mention, not a target."""
    if not token or len(token) > _MAX_PATH_CHARS or _DECEPTIVE_CHARS_RE.search(token):
        return False
    body = token[2:] if token.startswith("~/") else token.lstrip("/")
    segments = [segment for segment in body.split("/") if segment]
    if token.startswith("~/"):
        return len(segments) >= 1
    return len(segments) >= 2


def _split_line_suffix(token: str) -> Optional[str]:
    """`notes.md:42:7` → `notes.md`. None when the colons mean something else
    (`/usr/bin:/bin` is a list, and one link over a list is wrong)."""
    if ":" not in token:
        return token
    match = _LINE_SUFFIX_RE.match(token)
    if match and ":" not in match.group("path"):
        return match.group("path")
    return None


def _is_stump(path: str, following: str) -> bool:
    """True when `path` is the front half of a longer name that really exists.

    "/Users/a/My Documents/x.pdf" reaches us as "/Users/a/My". Linking that is a
    confident link to the wrong place; the directory listing says which it is.
    """
    expanded = expand_path(path)
    parent, base = os.path.dirname(expanded), os.path.basename(expanded)
    if not base or not following or not is_safe_to_stat(parent):
        return False
    try:
        with os.scandir(parent) as entries:
            for count, entry in enumerate(entries):
                if count > 2000:
                    break
                if entry.name.startswith(base + following[0]):
                    return True
    except OSError:
        return False
    return False


_HAS_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")


def find_path_spans(text: str, *, open_ended: bool = False, closes_inline: bool = False) -> List[PathSpan]:
    """Local paths in running prose.

    `open_ended`: the text is followed by inline markup rather than by a real
    boundary. Markdown eats glob stars as emphasis (`/x/*.txt and /y/b-*` reaches us
    as "/x/" + <em>…), so a candidate that runs to the very end of such a node has
    an unknown end and is not linked. `closes_inline` is the same doubt at a CLOSING
    inline tag, where a bold path (`**/Users/a/x.png**`) legitimately ends: there a
    candidate links only if it looks finished — it has an extension, or it exists.

    Prose cannot delimit a path that contains spaces or commas, so the rule is
    LONGEST EXISTING PATH, ELSE THE CAUTIOUS TOKEN, ELSE NOTHING:
    - where the disk may be asked (`is_safe_to_stat`), every soft break is a
      candidate end and the longest one that exists wins — so
      "/Users/a/My Documents/report final (v2).pdf" links whole, or not at all;
    - elsewhere the candidate ends at the first soft break, unverified;
    - a quote right before the path, or a backslash-escaped space inside it,
      delimits explicitly;
    - a glob, a `:`-joined list or a name with deceptive characters never links.
    """
    raw = str(text or "")
    spans: List[PathSpan] = []
    position = 0
    for match in _PATH_START_RE.finditer(raw):
        start = match.start()
        if start < position:
            continue
        # `https://host/Users/x` — the URL autolinker owns that text.
        if raw[max(0, start - 2) : start] in {":/", "//"}:
            continue

        quote = raw[start - 1] if start > 0 and raw[start - 1] in "\"“'" else ""
        closing = {"\"": "\"", "“": "”", "'": "'"}.get(quote, "")

        # The greedy run: up to a hard stop, the closing quote, or the length cap.
        limit = min(len(raw), start + _MAX_PATH_CHARS)
        end = start
        soft_breaks: List[int] = []
        globbed = False
        while end < limit:
            ch = raw[end]
            if ch == "\\" and end + 1 < limit and raw[end + 1] == " ":
                end += 2  # a shell-escaped space is part of the name
                continue
            if closing and ch == closing:
                break
            if ch in _HARD_STOPS and ch != closing:
                break
            if ch == "*" or (ch == "?" and end + 1 < len(raw) and not raw[end + 1].isspace()):
                globbed = True  # `a.txt?` ends a question; `a?.txt` is a pattern
                break
            if ch == "?":
                break
            if ch in _SOFT_STOPS and not (closing and ch == " "):
                soft_breaks.append(end)
            end += 1
        too_long = end >= limit and limit < len(raw)  # cut mid-name by the cap: not a path
        if globbed or too_long or (open_ended and end >= len(raw)):
            position = end
            continue

        def _candidate(stop: int) -> Optional[Tuple[int, str]]:
            token = _strip_trailing(raw[start:stop])
            path = _split_line_suffix(token.replace("\\ ", " "))
            if path is None or not _looks_like_path(path):
                return None
            # the link covers the path itself, never its `:42:7` suffix
            return start + len(token) - (len(token.replace("\\ ", " ")) - len(path)), path

        chosen: Optional[Tuple[int, str]] = None
        if closing and end < len(raw) and raw[end] == closing:
            chosen = _candidate(end)  # explicitly delimited: take it whole
        else:
            stops = soft_breaks + [end]
            cautious = _candidate(stops[0])
            if cautious is not None and is_safe_to_stat(cautious[1]):
                for probe, stop in enumerate(reversed(stops)):
                    if probe >= _MAX_EXISTENCE_PROBES:
                        break
                    longer = _candidate(stop)
                    if longer is not None and exists_locally(longer[1]):
                        chosen = longer
                        break
                if chosen is None and not _is_stump(cautious[1], raw[stops[0] : stops[0] + 1]):
                    chosen = cautious
            else:
                chosen = cautious
        if chosen is None:
            position = max(position, soft_breaks[0] if soft_breaks else end)
            continue
        span_end, path = chosen
        if closes_inline and span_end >= len(raw):
            if not (_HAS_EXTENSION_RE.search(path) or exists_locally(path)):
                position = span_end
                continue
        spans.append(PathSpan(start, span_end, path))
        position = span_end
    return spans


def find_file_url_spans(text: str) -> List[PathSpan]:
    """Bare `file://…` URLs naming THIS machine (another host is never linked)."""
    spans: List[PathSpan] = []
    for match in _FILE_URL_RE.finditer(str(text or "")):
        token = _strip_trailing(match.group(0))
        if len(token) > _MAX_PATH_CHARS:
            continue
        local = local_path_from_href(token)
        if local and _looks_like_path(local):
            spans.append(PathSpan(match.start(), match.start() + len(token), local))
    return spans


def path_from_code_span(code_text: str, *, exists: Optional[Callable[[str], bool]] = None) -> Optional[str]:
    """The path an inline code span IS, or None when it merely contains one.

    Backticks delimit, so a span may hold a path WITH spaces — but so does
    `/usr/bin/env python`. A spaced candidate is accepted only when it exists
    (checked through `exists`, which the caller restricts to safe roots);
    otherwise the span must be one unbroken token. A `:line:col` suffix is
    dropped from the target; globs and `:`-joined lists are not paths.
    """
    text = str(code_text or "").strip()
    if not text or "\n" in text or not text.startswith(_KNOWN_ROOTS):
        return None
    if any(ch in _GLOB_CHARS for ch in text):
        return None
    text = text.replace("\\ ", " ")
    path = _split_line_suffix(text)
    if path is None or not _looks_like_path(path):
        return None
    if not any(ch.isspace() for ch in path):
        return path
    if exists is not None and exists(path):
        return path
    return None


def is_safe_to_stat(path: str) -> bool:
    """True when touching `path` at render time cannot leave this machine.

    Home, temp and the shared user folder are local by construction. `/Volumes`,
    `/net`, `/home` (autofs on macOS) and everything else can be a network mount,
    where a stat may block for the mount timeout — those are left to click time.
    """
    expanded = expand_path(path)
    if not expanded.startswith("/"):
        return False
    roots = [
        str(Path.home()),
        "/tmp",
        "/private/tmp",
        "/var/folders",
        "/private/var/folders",
        "/Users/Shared",
    ]
    return any(expanded == root or expanded.startswith(root.rstrip("/") + "/") for root in roots)


_SAFE_STAT_ROOTS_CACHE: Optional[Tuple[str, ...]] = None


def _has_symlink_component(expanded: str) -> bool:
    """True if any component below the filesystem root is a symlink (never follows).

    `is_safe_to_stat` is lexical: `~/link -> /Volumes/share` passes it, and a plain
    `exists()` then walks straight onto the mount it was meant to avoid. `lstat`
    reads the link itself, which lives on the local disk.
    """
    current = "/"
    for part in [p for p in expanded.split("/") if p]:
        current = os.path.join(current, part)
        try:
            if os.path.islink(current):
                # /tmp and /var are system symlinks into /private: those are fine.
                if current in {"/tmp", "/var", "/etc"}:
                    continue
                return True
        except (OSError, ValueError):
            return True
    return False


def exists_locally(path: str) -> bool:
    """`os.path.exists`, but only ever asked of paths that are safe to stat — and
    never THROUGH a symlink, whose target is decided at click time instead."""
    if not is_safe_to_stat(path):
        return False
    expanded = expand_path(path)
    try:
        if _has_symlink_component(expanded):
            return False
        return os.path.exists(expanded)
    except (OSError, ValueError):
        return False


def path_kind(path: str) -> str:
    """image / video / audio / document / text / folder / other — from the NAME.

    Extension only: the kind decides what a click may do, and that decision must
    not depend on a stat of a path the model chose. A trailing slash reads as a
    folder; whether an extensionless name is one is settled at click time.
    """
    raw = str(path or "").strip()
    if raw.endswith("/"):
        return "folder"
    name = os.path.basename(expand_path(raw)).lower()
    _stem, ext = os.path.splitext(name)
    if ext in _IMAGE_EXT:
        return "image"
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _AUDIO_EXT:
        return "audio"
    if ext in _DOCUMENT_EXT:
        return "document"
    if ext in _TEXT_EXT:
        return "text"
    return "other"


def click_action(path: str) -> str:
    """"open" or "reveal" for a local path. See rule 1 in the module docstring."""
    return "open" if path_kind(path) in _OPENABLE_KINDS else "reveal"


def file_href(path: str) -> str:
    """A `file:///…` URL for a local path (always host-less, always absolute)."""
    expanded = expand_path(path)
    if not expanded.startswith("/"):
        return ""
    return "file://" + quote(expanded, safe="/")


def local_path_from_href(href: str) -> Optional[str]:
    """The local path a `file:` URL names — or None if it names another host.

    `file://server/share/x` is a UNC-style reference: asking the OS to open it
    mounts `server`. Only the empty host and `localhost` are this machine.
    """
    text = str(href or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if str(parsed.scheme or "").lower() != "file":
        return None
    host = str(parsed.netloc or "").strip().lower()
    if host not in {"", "localhost"}:
        return None
    path = unquote(parsed.path or "")
    if not path.startswith("/") or _DECEPTIVE_CHARS_RE.search(path):
        # `%00` unquotes to a real NUL: every os.path call then raises ValueError
        # (not OSError), which escaped the click slot and ABORTED the app
        # (adversarial find, 2026-09-17). Control and bidi characters name nothing.
        return None
    return os.path.normpath(path)


def describe_link(href: str) -> str:
    """One line for the hover tooltip: what this is and what a click will do."""
    local = local_path_from_href(href)
    if local is None:
        parsed = urlparse(str(href or ""))
        if str(parsed.scheme or "").lower() == "file":
            return "Link to another computer — not opened"
        return str(href or "").strip()
    kind = path_kind(local)
    noun = {
        "image": "Image",
        "video": "Video",
        "audio": "Audio",
        "document": "Document",
        "text": "Text file",
        "folder": "Folder",
    }.get(kind, "File")
    verb = "Click to open" if click_action(local) == "open" else "Click to show in Finder"
    return f"{noun} · {local}\n{verb} · right-click for more"


def mentioned_local_files(markdown_text: str, *, limit: int = 6) -> List[str]:
    """Existing local files an answer points at, in order, for the chip row.

    Only kinds that are inert to open get a chip (a chip's click OPENS), and only
    files that exist right now under a safe-to-stat root: a chip for a file that
    is not there is a broken promise, and the inline link still covers the rest.
    Fenced code blocks are skipped — a path in a listing is not a deliverable.
    """
    text = _strip_fenced_blocks(unfence_lone_targets(str(markdown_text or "")))
    found: List[str] = []
    seen: set[str] = set()

    def _consider(candidate: str) -> None:
        expanded = expand_path(candidate)
        if not expanded or expanded in seen or len(found) >= limit:
            return
        if path_kind(expanded) not in _CHIP_KINDS:
            return
        if not exists_locally(expanded) or os.path.isdir(expanded):
            return
        # A chip's click OPENS its file, so judge what the name really points at:
        # `clip.mp4` symlinked to an app bundle must not earn a chip.
        real = os.path.realpath(expanded)
        if real != expanded and (
            not is_safe_to_stat(real) or os.path.isdir(real) or path_kind(real) not in _CHIP_KINDS
        ):
            return
        seen.add(expanded)
        found.append(real)

    position = 0
    for match in re.finditer(r"`([^`\n]+)`", text):
        for span in find_path_spans(text[position : match.start()]):
            _consider(span.path)
        in_code = path_from_code_span(match.group(1), exists=exists_locally)
        if in_code:
            _consider(in_code)
        position = match.end()
    for span in find_path_spans(text[position:]):
        _consider(span.path)
    return found


_FENCE_RE = re.compile(r"(?ms)^(?P<indent>[ \t]*)(?P<fence>```|~~~)[^\n]*\n(?P<body>.*?)\n[ \t]*(?P=fence)[ \t]*$")
def unfence_lone_targets(markdown_text: str) -> str:
    """A fenced block that holds NOTHING but one local path becomes inline code.

    Models answer "where is it?" with

        ```
        /Users/…/clip.mp4
        ```

    as often as with backticks. That is not code — it is the deliverable, set on
    its own line — and as a fence it was the one place a link could never appear
    (seen live 2026-09-17, in the very session the clickable-path ask came from).
    Anything else in a fence stays code: a command that mentions a path, several
    paths, and a lone URL too (no evidence that one is ever the deliverable, and the
    renderer's contract has always been that fenced URLs are not rewritten).
    """

    def _replace(match: "re.Match[str]") -> str:
        body = match.group("body").strip()
        if not body or "\n" in body or "`" in body:
            return match.group(0)
        if path_from_code_span(body, exists=exists_locally):
            return f"{match.group('indent')}`{body}`"
        return match.group(0)

    return _FENCE_RE.sub(_replace, str(markdown_text or ""))


def _strip_fenced_blocks(text: str) -> str:
    return re.sub(r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$", "", text)
