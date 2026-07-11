"""Derive file activity (created/modified/moved/deleted) from executed tool calls.

This is a pure, UI-independent classifier used by message stats surfaces.
It must stay conservative: an operation is only reported when the tool name
and arguments (or a simple shell command) prove it. Guessing would produce
dishonest stats, which is worse than omitting an entry.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

ACTION_CREATED = "created"
ACTION_MODIFIED = "modified"
ACTION_MOVED = "moved"
ACTION_DELETED = "deleted"

# Display/reporting order for grouped summaries.
ACTION_ORDER = (ACTION_CREATED, ACTION_MODIFIED, ACTION_MOVED, ACTION_DELETED)

_PATH_KEYS = (
    "file_path",
    "filepath",
    "path",
    "target_path",
    "filename",
    "file",
)
_MOVE_SOURCE_KEYS = ("source", "source_path", "src", "from", "from_path", "old_path") + _PATH_KEYS
_MOVE_DEST_KEYS = ("destination", "destination_path", "dest", "dst", "to", "to_path", "new_path", "target")

_WRITE_TOOLS = {"write_file", "create_file", "save_file"}
_EDIT_TOOLS = {"edit_file", "update_file", "replace_in_file", "str_replace", "apply_patch", "patch_file"}
_DELETE_TOOLS = {"delete_file", "remove_file", "rm_file", "delete_path"}
_MOVE_TOOLS = {"move_file", "rename_file", "mv_file", "move_path", "rename_path"}
_COPY_TOOLS = {"copy_file", "cp_file", "duplicate_file"}
_MKDIR_TOOLS = {"create_directory", "make_directory", "mkdir"}
_COMMAND_TOOLS = {"execute_command", "run_command", "shell_exec", "run_shell", "bash", "sh"}

# Path tokens containing shell expansion/control characters cannot be trusted
# verbatim (globs, substitutions, descriptors, background/grouping operators).
_UNSAFE_PATH_CHARS = re.compile(r"[*?\[\]{}$`\\&<>();|!]")

# Optional fd prefix (2, &) + > or >> + optional inline path, e.g. ">out", "2>>log".
_REDIRECT_TOKEN = re.compile(r"^(\d*|&)(>>|>)(.*)$")


@dataclass(frozen=True)
class FileOperation:
    """One proven file-system mutation performed by a tool call."""

    action: str  # one of ACTION_ORDER
    path: str
    detail: str = ""  # e.g. destination path for moves
    via: str = ""  # tool name that performed the operation

    @property
    def label(self) -> str:
        if self.action == ACTION_MOVED and self.detail:
            return f"{self.path} \u2192 {self.detail}"
        return self.path

    @property
    def subject_path(self) -> str:
        """The path identifying the affected file for distinct counting.

        Moves count by destination (the file's current identity).
        """
        if self.action == ACTION_MOVED and self.detail:
            return self.detail
        return self.path


def _coerce_arguments(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return dict(arguments)
    text = str(arguments or "").strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return dict(parsed)
    return {}

def _first_path(arguments: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _safe_command_path(token: str) -> str:
    """Return the token as a path when it is a plain literal, else ''."""
    text = str(token or "").strip()
    if not text or text.startswith("-"):
        return ""
    if _UNSAFE_PATH_CHARS.search(text):
        return ""
    return text


def _split_command_segments(command: str) -> List[str]:
    """Split a shell command on top-level separators (&&, ||, ;, |).

    Quoted separators are respected by scanning with a minimal quote state
    machine; anything too complex simply yields fewer parseable segments.
    """
    segments: List[str] = []
    current: List[str] = []
    quote = ""
    index = 0
    text = str(command or "")
    while index < len(text):
        char = text[index]
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            elif char == "\\" and quote == '"' and index + 1 < len(text):
                current.append(text[index + 1])
                index += 1
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            index += 1
            continue
        two = text[index : index + 2]
        if two in {"&&", "||"}:
            segments.append("".join(current))
            current = []
            index += 2
            continue
        if char in {";", "|", "\n"}:
            segments.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    return [segment.strip() for segment in segments if segment.strip()]


def _strip_command_prefixes(tokens: List[str]) -> List[str]:
    """Drop env assignments and wrappers (sudo/env/nohup/time) before argv0."""
    out = list(tokens)
    while out:
        head = out[0]
        if "=" in head and not head.startswith(("-", "/", ".")) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", head):
            out.pop(0)
            continue
        if head in {"sudo", "env", "nohup", "time", "command"}:
            out.pop(0)
            continue
        break
    return out


def _positional_args(tokens: List[str]) -> List[str]:
    """Non-flag arguments after argv0, honoring the `--` terminator."""
    args: List[str] = []
    terminated = False
    for token in tokens[1:]:
        if not terminated and token == "--":
            terminated = True
            continue
        if not terminated and token.startswith("-"):
            continue
        args.append(token)
    return args


def _split_redirects(tokens: List[str]) -> Tuple[List[str], List[FileOperation]]:
    """Separate redirect constructs from command tokens.

    Returns the remaining tokens (executable + its real arguments) and the
    file operations proven by ``>``/``>>`` targets. Redirect targets must be
    removed from the argument stream, otherwise ``rm a > log`` would misreport
    ``log`` as deleted.
    """
    remaining: List[str] = []
    ops: List[FileOperation] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        match = _REDIRECT_TOKEN.match(token)
        if not match:
            remaining.append(token)
            index += 1
            continue
        action = ACTION_MODIFIED if match.group(2) == ">>" else ACTION_CREATED
        inline = match.group(3).strip()
        path = ""
        if inline:
            # `>&2` / `2>&1` duplicate descriptors, not files.
            if not inline.startswith("&"):
                path = _safe_command_path(inline)
        elif index + 1 < len(tokens):
            candidate = tokens[index + 1]
            if not candidate.startswith("&"):
                path = _safe_command_path(candidate)
            index += 1  # consume the redirect target either way
        if path:
            ops.append(FileOperation(action=action, path=path))
        index += 1
    return remaining, ops


def _operations_from_command_segment(segment: str) -> List[FileOperation]:
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        return []
    tokens = _strip_command_prefixes(tokens)
    if not tokens:
        return []

    tokens, ops = _split_redirects(tokens)
    if not tokens:
        return ops

    executable = tokens[0].rsplit("/", 1)[-1]
    args = [_safe_command_path(arg) for arg in _positional_args(tokens)]
    args = [arg for arg in args if arg]

    if executable in {"rm", "unlink"}:
        ops.extend(FileOperation(action=ACTION_DELETED, path=path) for path in args)
    elif executable == "rmdir":
        ops.extend(FileOperation(action=ACTION_DELETED, path=path) for path in args)
    elif executable == "mv" and len(args) >= 2:
        destination = args[-1]
        for source in args[:-1]:
            ops.append(FileOperation(action=ACTION_MOVED, path=source, detail=destination))
    elif executable == "cp" and len(args) == 2:
        ops.append(FileOperation(action=ACTION_CREATED, path=args[1]))
    elif executable == "touch":
        ops.extend(FileOperation(action=ACTION_CREATED, path=path) for path in args)
    elif executable == "mkdir":
        ops.extend(FileOperation(action=ACTION_CREATED, path=path) for path in args)
    return ops


def _operations_from_command(command: str) -> List[FileOperation]:
    ops: List[FileOperation] = []
    for segment in _split_command_segments(command):
        ops.extend(_operations_from_command_segment(segment))
    return ops


def _operations_from_tool_call(name: str, arguments: Dict[str, Any]) -> List[FileOperation]:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return []

    if normalized in _COMMAND_TOOLS:
        command = str(arguments.get("command") or arguments.get("cmd") or "").strip()
        return _operations_from_command(command) if command else []

    if normalized in _WRITE_TOOLS:
        path = _first_path(arguments, _PATH_KEYS)
        if not path:
            return []
        mode = str(arguments.get("mode") or "").strip().lower()
        action = ACTION_MODIFIED if mode in {"a", "append", "a+"} else ACTION_CREATED
        return [FileOperation(action=action, path=path)]

    if normalized in _EDIT_TOOLS:
        path = _first_path(arguments, _PATH_KEYS)
        return [FileOperation(action=ACTION_MODIFIED, path=path)] if path else []

    if normalized in _DELETE_TOOLS:
        path = _first_path(arguments, _PATH_KEYS)
        return [FileOperation(action=ACTION_DELETED, path=path)] if path else []

    if normalized in _MOVE_TOOLS:
        source = _first_path(arguments, _MOVE_SOURCE_KEYS)
        destination = _first_path(arguments, _MOVE_DEST_KEYS)
        if source and destination:
            return [FileOperation(action=ACTION_MOVED, path=source, detail=destination)]
        return []

    if normalized in _COPY_TOOLS:
        destination = _first_path(arguments, _MOVE_DEST_KEYS)
        return [FileOperation(action=ACTION_CREATED, path=destination)] if destination else []

    if normalized in _MKDIR_TOOLS:
        path = _first_path(arguments, _PATH_KEYS + ("directory", "directory_path", "dir"))
        return [FileOperation(action=ACTION_CREATED, path=path)] if path else []

    return []


def file_operations_from_tool_calls(tool_calls: Any) -> List[FileOperation]:
    """Classify file mutations from executed tool calls.

    Calls whose recorded result failed (``success is False``) are excluded:
    a failed write did not change the file system.
    """
    if not isinstance(tool_calls, list):
        return []
    ops: List[FileOperation] = []
    seen: set[Tuple[str, str, str]] = set()
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        if call.get("success") is False:
            continue
        name = str(call.get("name") or "").strip()
        arguments = _coerce_arguments(call.get("arguments"))
        for op in _operations_from_tool_call(name, arguments):
            key = (op.action, op.path, op.detail)
            if key in seen:
                continue
            seen.add(key)
            ops.append(FileOperation(action=op.action, path=op.path, detail=op.detail, via=name))
    return ops


def distinct_file_count(operations: Iterable[FileOperation]) -> int:
    """Number of distinct files affected (moves count by destination)."""
    return len({op.subject_path for op in operations if op.subject_path})


def grouped_file_operations(
    operations: Iterable[FileOperation],
) -> List[Tuple[str, List[FileOperation]]]:
    """Group operations by action in stable reporting order."""
    buckets: Dict[str, List[FileOperation]] = {}
    for op in operations:
        buckets.setdefault(op.action, []).append(op)
    return [(action, buckets[action]) for action in ACTION_ORDER if action in buckets]


__all__ = [
    "ACTION_CREATED",
    "ACTION_DELETED",
    "ACTION_MODIFIED",
    "ACTION_MOVED",
    "ACTION_ORDER",
    "FileOperation",
    "distinct_file_count",
    "file_operations_from_tool_calls",
    "grouped_file_operations",
]
