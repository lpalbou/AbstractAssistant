"""Tool calls in words (operator QA 2026-10-29): the Assistant's port of AbstractUIC's
`tool_call_words.ts` (kit backlog 0068). The same sentences, checked against the kit's shared cases
(`assets/tool_call_words.cases.json`, a copy of the kit's file): a verb, the key argument, the
secondary options in words; a tool without a template reads as "Key: value" lines, never JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

__all__ = ["ToolCallWords", "describe_tool_call", "group_tool_calls", "pretty_quotes", "readable_key", "short_url"]

REGIONS = {
    "us-en": "US English", "uk-en": "UK English", "wt-wt": "any region", "fr-fr": "French (France)",
    "de-de": "German (Germany)", "es-es": "Spanish (Spain)", "it-it": "Italian (Italy)",
    "ca-en": "Canadian English", "au-en": "Australian English", "in-en": "Indian English",
}
TIME_RANGES = {"d": "past day", "w": "past week", "m": "past month", "y": "past year"}


@dataclass
class ToolCallWords:
    verb: str
    lead: str
    key: str
    details: List[str]
    sentence: str
    fallback: Optional[List[Dict[str, str]]]
    noun: Tuple[str, str]


def _s(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip() if isinstance(v, (str, int, float)) else ""


def pretty_quotes(text: str) -> str:
    out, opening = [], True
    for ch in text:
        if ch == '"':
            out.append("“" if opening else "”")
            opening = not opening
        else:
            out.append(ch)
    return "".join(out)


def short_url(raw: str) -> str:
    text = _s(raw)
    try:
        u = urlparse(text)
    except ValueError:
        return text
    if not u.scheme or not u.netloc:
        return text
    host = u.netloc[4:] if u.netloc.startswith("www.") else u.netloc
    parts = [p for p in u.path.rstrip("/").split("/") if p]
    if len(parts) <= 2:
        return f"{host}/{'/'.join(parts)}" if parts else host
    return f"{host}/{parts[0]}/…/{parts[-1]}"


def readable_key(key: str) -> str:
    words = key.replace("_", " ").replace("-", " ").strip()
    words = " ".join(words.split())
    return words[0].upper() + words[1:] if words else key


def _readable_value(v: Any) -> str:
    if v is True:
        return "yes"
    if v is False:
        return "no"
    if v is None:
        return "none"
    if isinstance(v, (list, tuple)):
        return ", ".join(_readable_value(x) for x in v)
    if isinstance(v, Mapping):
        return ", ".join(f"{readable_key(str(k)).lower()} {_readable_value(x)}" for k, x in v.items())
    return str(v)


def _search_details(a: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    n = a.get("num_results", a.get("max_results", a.get("limit")))
    if isinstance(n, int) and not isinstance(n, bool):
        out.append(f"{n} {'result' if n == 1 else 'results'}")
    region = _s(a.get("region")).lower()
    if region:
        out.append(REGIONS.get(region, region))
    rng = _s(a.get("time_range")).lower()
    if rng:
        out.append(TIME_RANGES.get(rng, rng))
    safe = _s(a.get("safe_search")).lower()
    if safe:
        out.append("safe search off" if safe == "off" else f"{safe} safe search")
    return out


def _page_details(a: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    if a.get("include_full_content") is False:
        out.append("summary only")
    if a.get("include_full_content") is True:
        out.append("full content")
    if a.get("keep_links") is False:
        out.append("without links")
    if a.get("keep_links") is True:
        out.append("with links")
    return out


def _path(a: Mapping[str, Any]) -> str:
    return _s(a.get("file_path", a.get("path")))


_TEMPLATES: Dict[str, Tuple[str, str, Any, Any, Tuple[str, str]]] = {
    "fetch_url": ("Fetch", "the page", lambda a: short_url(_s(a.get("url"))), _page_details, ("page fetch", "page fetches")),
    "skim_url": ("Skim", "the page", lambda a: short_url(_s(a.get("url"))), _page_details, ("page skim", "page skims")),
    "web_search": ("Search", "the web for", lambda a: pretty_quotes(_s(a.get("query"))), _search_details, ("web search", "web searches")),
    "skim_websearch": ("Search", "the web for", lambda a: pretty_quotes(_s(a.get("query"))), _search_details, ("web search", "web searches")),
    "read_file": ("Read", "the file", _path, lambda a: [], ("file read", "file reads")),
    "write_file": ("Write", "the file", _path, lambda a: [], ("file write", "file writes")),
    "edit_file": ("Edit", "the file", _path, lambda a: [], ("file edit", "file edits")),
    "list_files": ("List", "the folder", lambda a: _s(a.get("directory_path", a.get("path"))) or "the workspace", lambda a: [], ("folder listing", "folder listings")),
    "execute_command": ("Run", "the command", lambda a: _s(a.get("command")), lambda a: [], ("command", "commands")),
    "send_email": ("Email", "", lambda a: _readable_value(a.get("to")), lambda a: ([f"subject “{_s(a.get('subject'))}”"] if _s(a.get("subject")) else []), ("email", "emails")),
    "browser_probe": ("Check", "the page renders", lambda a: short_url(_s(a.get("target"))) or _s(a.get("target")), lambda a: [], ("page check", "page checks")),
}


def describe_tool_call(call: Mapping[str, Any]) -> ToolCallWords:
    name = _s(call.get("name")) or "tool"
    args = call.get("arguments") if isinstance(call.get("arguments"), Mapping) else {}
    t = _TEMPLATES.get(name)
    if t is None:
        tool = name.split("::")[-1] if "::" in name else name
        verb = readable_key(tool)
        fallback = [{"label": readable_key(str(k)), "value": _readable_value(v)} for k, v in args.items()]
        return ToolCallWords(verb, "", "", [], verb, fallback, (verb.lower(), f"{verb.lower()} calls"))
    verb, lead, key_fn, details_fn, noun = t
    key = key_fn(args)
    details = list(details_fn(args))
    head = " ".join(x for x in (verb, lead, key) if x)
    return ToolCallWords(verb, lead, key, details, f"{head} ({', '.join(details)})" if details else head, None, noun)


def group_tool_calls(calls: Sequence[Mapping[str, Any]]) -> str:
    counts: Dict[str, List[Any]] = {}
    for c in calls:
        w = describe_tool_call(c)
        if w.noun[1] in counts:
            counts[w.noun[1]][0] += 1
        else:
            counts[w.noun[1]] = [1, w.noun]
    return ", ".join(f"{n} {noun[0] if n == 1 else noun[1]}" for n, noun in counts.values())
