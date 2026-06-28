"""Compact, single-line tool labels for UI status surfaces."""

from __future__ import annotations

import json
import re
from html import escape
from typing import Any, Dict, List


DEFAULT_TOOL_LABEL_MAX_CHARS = 120
TOOL_NAME_COLOR = "#63d98b"
TOOL_ARGUMENT_COLOR = "#ffc963"


def _one_line(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clip(text: str, max_chars: int) -> str:
    limit = max(16, int(max_chars or DEFAULT_TOOL_LABEL_MAX_CHARS))
    value = _one_line(text)
    if len(value) <= limit:
        return value
    if "(" in value and limit > 8:
        return value[: limit - 4].rstrip() + "...)"
    return value[: limit - 3].rstrip() + "..."


def _coerce_arguments(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return dict(arguments)
    text = str(arguments or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return dict(parsed)
    return {"arguments": text}


def _preferred_keys(tool_name: str, args: Dict[str, Any]) -> List[str]:
    name = str(tool_name or "").strip().lower()
    if name in {"web_search", "search_web", "skim_websearch"}:
        preferred = ["query", "q", "num_results", "max_results", "max_chars", "region", "time"]
    elif name in {"fetch_url", "open_url", "skim_url"}:
        preferred = ["url", "max_chars", "timeout"]
    elif name in {"execute_command", "run_command"}:
        preferred = ["command", "cmd", "cwd", "timeout"]
    elif name in {"open_attachment"}:
        preferred = ["artifact_id", "handle", "start_line", "end_line", "max_chars"]
    elif name in {"write_file", "edit_file", "read_file", "open_file", "list_files", "skim_files", "skim_folders"}:
        preferred = [
            "file_path",
            "filepath",
            "path",
            "target_path",
            "start_line",
            "end_line",
            "max_chars",
            "content",
            "text",
        ]
    elif "search" in name:
        preferred = ["query", "q", "pattern", "path", "max_results", "num_results"]
    else:
        preferred = ["path", "file_path", "filepath", "url", "query", "q", "command", "cmd", "id", "max_chars"]

    out = [key for key in preferred if key in args]
    if out:
        return out[:4]
    return [str(key) for key in list(args.keys())[:3]]


def _format_value(key: str, value: Any, *, max_chars: int) -> str:
    label = str(key or "").strip().lower()
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        text = _one_line(value)
        if not text:
            return '""'
        if label in {"content", "text", "body", "html", "script"} and (len(text) > max_chars or "\n" in value):
            return f"{len(value)} chars"
        clipped = _clip(text, max_chars)
        return json.dumps(clipped, ensure_ascii=False)
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if len(items) <= 3 and all(not isinstance(v, (dict, list, tuple, set)) for v in items):
            rendered = ", ".join(_format_value(label, v, max_chars=max(12, max_chars // 3)) for v in items)
            return "[" + rendered + "]"
        return f"list({len(items)})"
    if isinstance(value, dict):
        if len(value) <= 3 and all(not isinstance(v, (dict, list, tuple, set)) for v in value.values()):
            parts = [
                f"{k}={_format_value(str(k), v, max_chars=max(12, max_chars // 3))}"
                for k, v in value.items()
            ]
            return "{" + ", ".join(parts) + "}"
        return f"dict({len(value)})"
    return _clip(str(value), max_chars)


def compact_tool_call_label(
    name: Any,
    arguments: Any = None,
    *,
    max_chars: int = DEFAULT_TOOL_LABEL_MAX_CHARS,
) -> str:
    """Return `tool_name(key=value, ...)` as a bounded one-line label."""

    tool_name = _one_line(name) or "tool"
    args = _coerce_arguments(arguments)
    if not args:
        return _clip(f"{tool_name}()", max_chars)

    keys = _preferred_keys(tool_name, args)
    remaining = max(24, int(max_chars or DEFAULT_TOOL_LABEL_MAX_CHARS) - len(tool_name) - 8)
    value_budget = max(18, min(64, remaining // max(1, len(keys))))
    parts = [f"{key}={_format_value(key, args.get(key), max_chars=value_budget)}" for key in keys]
    return _clip(f"{tool_name}({', '.join(parts)})", max_chars)


def compact_tool_call_label_html(
    name: Any,
    arguments: Any = None,
    *,
    max_chars: int = DEFAULT_TOOL_LABEL_MAX_CHARS,
) -> str:
    """Return a bounded rich-text label with colored tool name and arguments."""

    tool_name = _one_line(name) or "tool"
    plain = compact_tool_call_label(tool_name, arguments, max_chars=max_chars)
    if plain.startswith(tool_name):
        name_part = tool_name
        args_part = plain[len(tool_name) :]
    elif "(" in plain:
        name_part, args_part = plain.split("(", 1)
        args_part = "(" + args_part
    else:
        name_part = plain
        args_part = ""
    if args_part.startswith("("):
        inner = args_part[1:]
        close = ""
        if inner.endswith(")"):
            inner = inner[:-1]
            close = ")"
        return (
            f'<span style="color:{TOOL_NAME_COLOR}; font-weight:800;">{escape(name_part)}</span>'
            f'<span style="color:{TOOL_NAME_COLOR}; font-weight:800;">(</span>'
            f'<span style="color:{TOOL_ARGUMENT_COLOR}; font-weight:400;">{escape(inner)}</span>'
            f'<span style="color:{TOOL_NAME_COLOR}; font-weight:800;">{escape(close)}</span>'
        )

    return (
        f'<span style="color:{TOOL_NAME_COLOR}; font-weight:800;">{escape(name_part)}</span>'
        f'<span style="color:{TOOL_ARGUMENT_COLOR}; font-weight:400;">{escape(args_part)}</span>'
    )


def compact_tool_message_label(message: Any, *, max_chars: int = DEFAULT_TOOL_LABEL_MAX_CHARS) -> str:
    """Extract a compact tool label from a stored tool message."""

    if not isinstance(message, dict):
        return compact_tool_call_label("tool", None, max_chars=max_chars)
    metadata = message.get("metadata")
    meta = metadata if isinstance(metadata, dict) else {}
    name = str(meta.get("name") or "").strip()
    if not name:
        content = str(message.get("content") or "")
        match = re.match(r"\s*\[([^\]]+)\]:", content)
        if match:
            name = str(match.group(1) or "").strip()
    arguments = meta.get("arguments")
    if arguments is None:
        arguments = meta.get("args")
    return compact_tool_call_label(name or "tool", arguments, max_chars=max_chars)


def compact_tool_message_label_html(message: Any, *, max_chars: int = DEFAULT_TOOL_LABEL_MAX_CHARS) -> str:
    """Extract a compact rich-text tool label from a stored tool message."""

    if not isinstance(message, dict):
        return compact_tool_call_label_html("tool", None, max_chars=max_chars)
    metadata = message.get("metadata")
    meta = metadata if isinstance(metadata, dict) else {}
    name = str(meta.get("name") or "").strip()
    if not name:
        content = str(message.get("content") or "")
        match = re.match(r"\s*\[([^\]]+)\]:", content)
        if match:
            name = str(match.group(1) or "").strip()
    arguments = meta.get("arguments")
    if arguments is None:
        arguments = meta.get("args")
    return compact_tool_call_label_html(name or "tool", arguments, max_chars=max_chars)


__all__ = [
    "DEFAULT_TOOL_LABEL_MAX_CHARS",
    "TOOL_ARGUMENT_COLOR",
    "TOOL_NAME_COLOR",
    "compact_tool_call_label",
    "compact_tool_call_label_html",
    "compact_tool_message_label",
    "compact_tool_message_label_html",
]
