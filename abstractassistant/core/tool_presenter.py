"""Turn a gateway tool call into something a person can judge in two seconds.

Pure Python (no Qt) so the approval sheet, the post-hoc "tools used" cards and
the tests all read one description of a call:

- the summary helpers (``tool_call_summary`` & co.) that ``app.py`` used to
  keep as private functions, kept byte-for-byte compatible;
- ``present_call``: one promoted headline (the command / path / URL / query),
  the remaining parameters flattened one level, long content demoted to a
  preview block, secrets masked, the gateway's risk facts attached;
- ``batch_tier``: the loudest risk tier across a batch, fail-closed to
  "unknown" when any tool is missing from the gateway inventory.

Risk is never inferred from a tool's name here: ``describe_tool_risk`` reads
the gateway's own classification and this module only lays it out.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from abstractassistant.core.tool_risk import describe_tool_risk


SECRET_MASK = "••••••"
_SECRET_KEY_RE = re.compile(r"(?i)(token|secret|password|passwd|api[_-]?key|authorization|cookie)")

# Keys whose values are never rendered inline (spec 3.6 rule 2).
CONTENT_KEYS = frozenset(
    {"content", "text", "body", "html", "script", "stdin", "patch", "source", "code"}
)
INLINE_MAX_CHARS = 120          # longer scalars are cut with an ellipsis
CONTENT_MIN_CHARS = 240         # longer strings become a content block
HEADLINE_MAX_LINES = 8
PREVIEW_LINES = 40
OUTPUT_PREVIEW_MAX_CHARS = 1_200

_COMMAND_KEYS = ("command", "cmd")
_PATH_KEYS = ("path", "file_path", "filepath", "file", "directory_path", "directory", "target")
_URL_KEYS = ("url", "href")
_QUERY_KEYS = ("query", "q", "pattern")

_COMMAND_TOOLS = frozenset({"execute_command", "run_command", "shell_exec", "shell_write_stdin"})
_SEARCH_TOOLS = frozenset({"web_search", "search_web", "skim_websearch", "search_files"})
_WEB_TOOLS = frozenset({"fetch_url", "open_url", "open_browser", "skim_url", "browser_probe"})

# (flag on the inventory item, chip label, chip tone) — spec 3.5.
_FLAG_CHIPS: Tuple[Tuple[str, str, str], ...] = (
    ("destructive_capable", "can delete", "destroy"),
    ("mutating", "writes", "act"),
    ("remote_write_capable", "sends data", "outreach"),
    ("captures_environment", "camera/mic", "outreach"),
    ("comms_send", "messages people", "outreach"),
)

UNKNOWN_RISK_LABEL = "Unknown risk"
UNKNOWN_RISK_WEIGHT = 3  # an unlisted tool weighs like "outreach" when picking a batch label


# --------------------------------------------------------------------------- #
# Summary helpers (moved from app.py; behaviour unchanged)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ToolCallSummary:
    name: str
    reason: str
    parameters: List[tuple[str, str]]
    raw_text: str


def _json_dumps(value: Dict[str, Any]) -> str:
    # Mirrors app.py ``json_dumps``: empty dict → "", no key sorting.
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, indent=2)


def tool_calls_text(tool_calls: Any) -> str:
    if not isinstance(tool_calls, list) or not tool_calls:
        return "No tool details were provided by the workflow."
    blocks: List[str] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "<unknown>").strip() or "<unknown>"
        arguments = call.get("arguments")
        if isinstance(arguments, dict):
            rendered = _json_dumps(arguments)
        else:
            rendered = str(arguments or "")
        blocks.append(f"{name}\n{rendered}".strip())
    return "\n\n".join(blocks) or "No tool details were provided by the workflow."


def tool_call_arguments(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return dict(arguments)
    text = str(arguments or "").strip()
    if not text:
        return {}
    if not text.startswith("{"):
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def tool_call_value_summary(name: str, value: Any) -> str:
    key = str(name or "").strip().lower()
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        count = len(value)
        label = "entry" if count == 1 else "entries"
        return f"object with {count} {label}"
    if isinstance(value, list):
        count = len(value)
        label = "item" if count == 1 else "items"
        return f"list with {count} {label}"

    text = str(value or "").strip()
    if not text:
        return "empty"

    lowered = text.lower()
    looks_like_html = (
        "<html" in lowered
        or lowered.startswith("<!doctype html")
        or lowered.startswith("<div")
    )
    has_newlines = "\n" in text or "\r" in text
    if (
        key in {"content", "body", "text", "html", "script"}
        or has_newlines
        or len(text) > 120
    ):
        kind = "HTML content" if looks_like_html else "text content"
        return f"{kind}, {len(text):,} chars"
    if len(text) > 96:
        return f"{text[:93]}..."
    return text


def tool_call_reason(name: str, arguments: Dict[str, Any]) -> str:
    tool = str(name or "").strip()
    normalized = tool.lower()
    arguments = arguments if isinstance(arguments, dict) else {}
    path = str(
        arguments.get("file_path")
        or arguments.get("filepath")
        or arguments.get("path")
        or arguments.get("file")
        or arguments.get("target")
        or ""
    ).strip()
    cmd = str(arguments.get("cmd") or arguments.get("command") or "").strip()
    url = str(arguments.get("url") or arguments.get("href") or "").strip()
    query = str(
        arguments.get("q") or arguments.get("query") or arguments.get("prompt") or ""
    ).strip()

    if normalized == "write_file" and path:
        return f"Create or replace `{path}`."
    if normalized in {"read_file", "open_file"} and path:
        return f"Read `{path}`."
    if normalized in {"edit_file", "update_file"} and path:
        return f"Modify `{path}`."
    if normalized == "apply_patch":
        return "Apply a patch to one or more local files."
    if normalized in {"execute_command", "run_command"} and cmd:
        return f"Run `{cmd}`."
    if normalized in {"list_files", "search_files"} and path:
        return f"Inspect files under `{path}`."
    if normalized in {"fetch_url", "open_url", "open_browser"} and url:
        return f"Open or fetch `{url}`."
    if normalized in {"web_search", "search_web"} and query:
        return f"Search the web for `{query}`."
    if normalized.startswith("write"):
        return "Write or create local content."
    if normalized.startswith("read"):
        return "Read local content."
    if normalized.startswith("list") or normalized.startswith("search"):
        return "Inspect available resources."
    if normalized.startswith("execute") or normalized.startswith("run"):
        return "Run a command."
    return f"Call `{tool or '<unknown>'}` with the parameters below."


def tool_call_summary(call: Any) -> ToolCallSummary:
    if not isinstance(call, dict):
        return ToolCallSummary(
            name="<unknown>",
            reason="The workflow requested a tool call, but the payload was not structured.",
            parameters=[],
            raw_text=str(call or ""),
        )
    name = str(call.get("name") or "<unknown>").strip() or "<unknown>"
    arguments = tool_call_arguments(call.get("arguments"))
    raw_text = tool_calls_text([call]).strip()
    parameter_rows: List[tuple[str, str]] = []
    if arguments:
        for key, value in arguments.items():
            label = str(key or "").strip()
            if not label:
                continue
            parameter_rows.append((label, tool_call_value_summary(label, value)))
    # app.py wrote ``not in {None, "", {}}`` — a set literal holding a dict,
    # which raises TypeError the moment a scalar payload reaches this branch.
    elif call.get("arguments") not in (None, "", {}):
        parameter_rows.append(
            ("arguments", tool_call_value_summary("arguments", call.get("arguments")))
        )
    return ToolCallSummary(
        name=name,
        reason=tool_call_reason(name, arguments),
        parameters=parameter_rows,
        raw_text=raw_text,
    )


# --------------------------------------------------------------------------- #
# Secrets
# --------------------------------------------------------------------------- #


def is_secret_key(key: Any) -> bool:
    return bool(_SECRET_KEY_RE.search(str(key or "")))


def _mask(value: Any, hits: List[str], path: str = "") -> Any:
    if isinstance(value, dict):
        out: Dict[Any, Any] = {}
        for key, child in value.items():
            here = f"{path}.{key}" if path else str(key)
            if is_secret_key(key):
                hits.append(here)
                out[key] = SECRET_MASK
            else:
                out[key] = _mask(child, hits, here)
        return out
    if isinstance(value, list):
        return [_mask(item, hits, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, tuple):
        return tuple(_mask(item, hits, f"{path}[{index}]") for index, item in enumerate(value))
    return value


def mask_secrets(value: Any) -> Any:
    """Deep copy of ``value`` with every secret-looking key's value replaced.

    Keys matching ``token|secret|password|passwd|api[_-]?key|authorization|cookie``
    (case-insensitive, anywhere in nested dicts/lists) become ``"••••••"``.
    """
    return _mask(value, [])


# --------------------------------------------------------------------------- #
# Presentation model
# --------------------------------------------------------------------------- #


@dataclass
class CallPresentation:
    name: str
    reason: str
    risk: Dict[str, Any]
    headline: str = ""
    headline_kind: str = ""          # command | path | url | query | ""
    headline_key: str = ""
    params: List[Tuple[str, str, str]] = field(default_factory=list)          # key, display, tooltip
    content_blocks: List[Tuple[str, str, str]] = field(default_factory=list)  # key, summary, preview
    flags: List[Tuple[str, str]] = field(default_factory=list)                # label, tone
    raw_json: str = ""
    secrets_masked: bool = False
    available: bool = True
    unknown: bool = False
    success: Optional[bool] = None
    error: str = ""
    output_preview: str = ""
    toolset: str = ""
    approval_default: str = ""
    summary: Optional[ToolCallSummary] = None


def _home_dir() -> str:
    try:
        return os.path.expanduser("~").rstrip("/")
    except Exception:
        return ""


def collapse_home(path: str) -> str:
    """``/Users/me/proj/a.py`` → ``~/proj/a.py`` (only for the current home)."""
    text = str(path or "")
    home = _home_dir()
    if not home or home == "~":
        return text
    if text == home:
        return "~"
    if text.startswith(home + "/"):
        return "~" + text[len(home):]
    return text


def _family(name: str) -> str:
    normalized = str(name or "").strip().lower()
    if normalized in _COMMAND_TOOLS or normalized.startswith(("execute", "run_", "shell")):
        return "command"
    if normalized in _SEARCH_TOOLS or normalized.startswith("search"):
        return "query"
    if normalized in _WEB_TOOLS or normalized.startswith(("fetch", "open_url", "browser")):
        return "url"
    return "path"


def _headline_order(name: str) -> List[Tuple[str, Tuple[str, ...]]]:
    table = {
        "command": ("command", _COMMAND_KEYS),
        "path": ("path", _PATH_KEYS),
        "url": ("url", _URL_KEYS),
        "query": ("query", _QUERY_KEYS),
    }
    family = _family(name)
    if family == "command":
        order = ["command", "path", "url", "query"]
    elif family == "query":
        order = ["query", "path", "url", "command"]
    elif family == "url":
        order = ["url", "query", "path", "command"]
    else:
        order = ["path", "url", "command", "query"]
    return [table[kind] for kind in order]


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _promote_headline(name: str, arguments: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return ``(headline, kind, key)`` for the one argument worth a block."""
    for kind, keys in _headline_order(name):
        for key in keys:
            if key not in arguments:
                continue
            value = arguments.get(key)
            if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                continue
            text = str(value).strip()
            if not text or text == SECRET_MASK:
                continue
            if kind == "command":
                return f"$ {text}", kind, key
            if kind == "path":
                return collapse_home(text), kind, key
            if kind == "url":
                return text, kind, key
            return f"“{text}”", kind, key
    return "", "", ""


def _scalar_display(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def _brief(value: Any) -> str:
    """Compact rendering for nested values inside lists / one-level objects."""
    if isinstance(value, dict):
        count = len(value)
        return f"{{…}} {count} {'key' if count == 1 else 'keys'}"
    if isinstance(value, list):
        return _list_display(value)
    text = _scalar_display(value)
    if len(text) > 40:
        text = text[:39].rstrip() + "…"
    return text


def _list_display(items: List[Any]) -> str:
    count = len(items)
    head = f"[{count} {'item' if count == 1 else 'items'}]"
    shown: List[str] = []
    for item in items[:3]:
        if isinstance(item, dict):
            shown.append("{…}")
        elif isinstance(item, list):
            shown.append("[…]")
        else:
            shown.append(_brief(item))
    if not shown:
        return head
    tail = ", …" if count > 3 else ""
    return f"{head} {', '.join(shown)}{tail}"


def _is_content(key: str, value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if str(key or "").strip().lower() in CONTENT_KEYS:
        return True
    return "\n" in value or "\r" in value or len(value) > CONTENT_MIN_CHARS


def _content_block(key: str, value: str) -> Tuple[str, str, str]:
    text = str(value or "")
    lines = text.splitlines() or [""]
    summary = f"{len(text):,} chars · {len(lines):,} {'line' if len(lines) == 1 else 'lines'}"
    preview_lines = lines[:PREVIEW_LINES]
    preview = "\n".join(preview_lines)
    hidden = len(lines) - len(preview_lines)
    if hidden > 0:
        preview += f"\n… (+{hidden:,} more {'line' if hidden == 1 else 'lines'})"
    return (key, summary, preview)


def _schema_description(schema: Any, key: str) -> str:
    if not isinstance(schema, dict):
        return ""
    entry = schema.get(key)
    if isinstance(entry, dict):
        return str(entry.get("description") or "").strip()
    return ""


def _param_row(key: str, value: Any, description: str) -> Tuple[str, str, str]:
    full = _scalar_display(value)
    display = full
    tooltip_bits: List[str] = []
    if isinstance(value, str) and len(full) > INLINE_MAX_CHARS:
        display = full[: INLINE_MAX_CHARS - 1].rstrip() + "…"
        tooltip_bits.append(full)
    if description:
        tooltip_bits.append(description)
    return (key, display, "\n\n".join(tooltip_bits))


def _split_arguments(
    arguments: Dict[str, Any],
    *,
    headline_key: str,
    schema: Any,
) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str, str]]]:
    params: List[Tuple[str, str, str]] = []
    blocks: List[Tuple[str, str, str]] = []
    for raw_key, value in arguments.items():
        key = str(raw_key or "").strip()
        if not key or key == headline_key:
            continue
        description = _schema_description(schema, key)
        if _is_content(key, value):
            blocks.append(_content_block(key, value))
            continue
        if isinstance(value, dict):
            if not value:
                params.append((key, "{} empty", description))
                continue
            for child_key, child in value.items():
                label = f"{key}.{child_key}"
                if isinstance(child, str) and _is_content(child_key, child):
                    blocks.append(_content_block(label, child))
                elif isinstance(child, (dict, list)):
                    params.append((label, _brief(child), ""))
                else:
                    params.append(_param_row(label, child, ""))
            continue
        if isinstance(value, list):
            params.append((key, _list_display(value), description))
            continue
        params.append(_param_row(key, value, description))
    return params, blocks


def _risk_flags(item: Optional[Dict[str, Any]]) -> List[Tuple[str, str]]:
    if not isinstance(item, dict):
        return []
    flags: List[Tuple[str, str]] = []
    for flag, label, tone in _FLAG_CHIPS:
        if item.get(flag) is True:
            flags.append((label, tone))
    # "can delete" implies "writes"; one chip says it.
    if ("can delete", "destroy") in flags:
        flags = [flag for flag in flags if flag != ("writes", "act")]
    return flags


def _output_preview(call: Dict[str, Any]) -> str:
    for key in ("output_preview", "output", "result"):
        if key not in call:
            continue
        value = call.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False, indent=2)
            except Exception:
                text = str(value)
        text = text.strip()
        if not text:
            continue
        if len(text) > OUTPUT_PREVIEW_MAX_CHARS:
            text = text[: OUTPUT_PREVIEW_MAX_CHARS - 1].rstrip() + "…"
        return text
    return ""


def toolset_glyph(name: str, risk_item: Optional[Dict[str, Any]] = None) -> str:
    """Icon name for a tool: gateway ``toolset`` first, name family second."""
    toolset = ""
    if isinstance(risk_item, dict):
        toolset = str(risk_item.get("toolset") or "").strip().lower()
    normalized = str(name or "").strip().lower()
    if toolset:
        if toolset in {"system", "shell"} or toolset.startswith("shell"):
            return "terminal"
        if toolset == "web" or toolset.startswith("web"):
            return "globe"
        if toolset in {"files", "file", "fs"}:
            return "folder"
        if toolset.startswith("comms") or toolset in {"email", "mail"}:
            return "mail"
        if toolset == "camera":
            return "camera"
    if _family(normalized) == "command":
        return "terminal"
    if normalized in _WEB_TOOLS or normalized in {"web_search", "search_web", "skim_websearch"}:
        return "globe"
    if normalized.startswith("camera"):
        return "camera"
    if normalized.startswith(("send_", "list_email", "read_email", "list_whatsapp", "read_whatsapp")):
        return "mail"
    if normalized.endswith(("_file", "_files", "_folders")) or normalized in {"apply_patch", "search_files"}:
        return "folder"
    return "spark"


def present_call(call: Any, risk: Optional[Dict[str, Any]] = None) -> CallPresentation:
    """Describe one tool call for a card.

    ``risk`` is the gateway inventory item for the tool (``None`` when the
    tool is not in the inventory → ``unknown=True`` and an "Unknown risk"
    tier, never a fabricated safe one).
    """
    summary = tool_call_summary(call)
    call_dict = call if isinstance(call, dict) else {}
    name = summary.name
    raw_arguments = call_dict.get("arguments")
    arguments = tool_call_arguments(raw_arguments)

    hits: List[str] = []
    masked_arguments = _mask(arguments, hits)
    secrets_masked = bool(hits)

    risk_item = dict(risk) if isinstance(risk, dict) else None
    unknown = risk_item is None
    risk_info = describe_tool_risk(risk_item)
    if unknown:
        risk_info = {**risk_info, "label": UNKNOWN_RISK_LABEL, "tone": "unknown", "rank": 0, "tier": ""}
    available = True
    if risk_item is not None:
        if risk_item.get("available") is False or risk_item.get("enabled") is False:
            available = False
    schema = risk_item.get("parameters") if risk_item else None

    headline = kind = headline_key = ""
    params: List[Tuple[str, str, str]] = []
    blocks: List[Tuple[str, str, str]] = []
    if arguments:
        headline, kind, headline_key = _promote_headline(name, masked_arguments)
        params, blocks = _split_arguments(masked_arguments, headline_key=headline_key, schema=schema)
    elif raw_arguments not in (None, "", {}):
        # Spec 3.6 rule 8: never pretend structure for a non-dict payload.
        if isinstance(raw_arguments, str) and _is_content("arguments", raw_arguments):
            blocks.append(_content_block("arguments", raw_arguments))
        elif isinstance(raw_arguments, (dict, list)):
            params.append(("arguments", _brief(raw_arguments), ""))
        else:
            params.append(_param_row("arguments", raw_arguments, ""))

    raw_call: Dict[str, Any] = {"name": name}
    for key in ("call_id", "id", "tool_call_id"):
        if call_dict.get(key) not in (None, ""):
            raw_call[key] = call_dict.get(key)
    if arguments:
        raw_call["arguments"] = masked_arguments
    elif raw_arguments not in (None, ""):
        raw_call["arguments"] = _mask(raw_arguments, [])
    try:
        raw_json = json.dumps(raw_call, ensure_ascii=False, indent=2)
    except Exception:
        raw_json = str(raw_call)

    success: Optional[bool] = None
    if isinstance(call_dict.get("success"), bool):
        success = bool(call_dict.get("success"))
    error = str(call_dict.get("error") or "").strip()

    return CallPresentation(
        name=name,
        reason=summary.reason,
        risk=risk_info,
        headline=headline,
        headline_kind=kind,
        headline_key=headline_key,
        params=params,
        content_blocks=blocks,
        flags=_risk_flags(risk_item),
        raw_json=raw_json,
        secrets_masked=secrets_masked,
        available=available,
        unknown=unknown,
        success=success,
        error=error,
        output_preview=_output_preview(call_dict),
        toolset=str((risk_item or {}).get("toolset") or "").strip().lower(),
        approval_default=str(risk_info.get("approval_default") or ""),
        summary=summary,
    )


def clip_lines(text: str, max_lines: int = HEADLINE_MAX_LINES) -> str:
    """Keep the first ``max_lines`` lines and say how many were hidden."""
    lines = str(text or "").splitlines()
    if len(lines) <= max_lines:
        return str(text or "")
    hidden = len(lines) - max_lines
    return "\n".join(lines[:max_lines]) + f"\n… (+{hidden:,} {'line' if hidden == 1 else 'lines'})"


def batch_tier(calls: Iterable[Any], risks_by_name: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Loudest tier across a batch; ``unknown`` when any tool is unlisted.

    An unlisted tool yields ``Unknown risk`` (tone ``unknown``). For the
    label it counts as loud as ``outreach``: only a listed tool that ranks
    strictly higher (``destroy``) takes the label, and ``unknown`` stays
    ``True`` either way so blanket trust is still refused. Anything quieter
    (``observe``/``act``) must not dress an unlisted tool up as safe.
    """
    lookup = risks_by_name if isinstance(risks_by_name, dict) else {}
    best: Optional[Dict[str, Any]] = None
    unknown = False
    seen_any = False
    for call in calls or []:
        if not isinstance(call, dict):
            continue
        seen_any = True
        name = str(call.get("name") or "").strip()
        item = lookup.get(name) if name else None
        if not isinstance(item, dict):
            unknown = True
            continue
        info = describe_tool_risk(item)
        if best is None or int(info.get("rank") or 0) > int(best.get("rank") or 0):
            best = info
    if not seen_any:
        unknown = True
    if best is None or (unknown and int(best.get("rank") or 0) <= UNKNOWN_RISK_WEIGHT):
        return {"label": UNKNOWN_RISK_LABEL, "tone": "unknown", "rank": 0, "unknown": True}
    return {
        "label": str(best.get("label") or UNKNOWN_RISK_LABEL),
        "tone": str(best.get("tone") or "unknown"),
        "rank": int(best.get("rank") or 0),
        "unknown": unknown,
    }


__all__ = [
    "CONTENT_KEYS",
    "CallPresentation",
    "HEADLINE_MAX_LINES",
    "SECRET_MASK",
    "ToolCallSummary",
    "UNKNOWN_RISK_LABEL",
    "batch_tier",
    "clip_lines",
    "collapse_home",
    "is_secret_key",
    "mask_secrets",
    "present_call",
    "tool_call_arguments",
    "tool_call_reason",
    "tool_call_summary",
    "tool_call_value_summary",
    "tool_calls_text",
    "toolset_glyph",
]
