"""Transcript-to-UI helpers for AbstractAssistant.

AbstractAgent/ReAct persists tool observations as role="tool" messages so the model can
continue the loop. Those observations are useful for debugging but are too noisy for
end-user chat history rendering.

This module provides a small, UI-agnostic transformation:
- hide tool messages from the user-visible transcript
- attach a compact tool summary + clickable resources to the next user-visible assistant message
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple
from urllib.parse import unquote, urlparse


def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        s = str(item or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


_URL_RE = re.compile(r"https?://[^\s)\]\"'<>]+")
_WIN_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"'<>]+")
_FILE_HEADER_RE = re.compile(r"(?im)^File:\s+(.+?)(?:\s\(|\n|$)")
_URL_HEADER_RE = re.compile(r"(?im)\bURL:\s*(https?://\S+)")
_HTML_IMG_RE = re.compile(r"(?is)<img[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"'][^>]*>")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_ARTIFACT_RE = re.compile(r"\"\\$artifact\"\\s*:\\s*\"([a-zA-Z0-9_-]+)\"")

_IMAGE_EXTS: set[str] = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _extract_urls(text: str, *, limit: int = 10) -> List[str]:
    candidates = _URL_RE.findall(str(text or ""))
    out: List[str] = []
    for raw in candidates:
        cleaned = str(raw).rstrip(").,;]\"'")
        if not cleaned:
            continue
        out.append(cleaned)
        if len(out) >= int(limit):
            break
    return _dedupe_preserve_order(out)


def _extract_primary_url(text: str) -> List[str]:
    raw_text = str(text or "")
    match = _URL_HEADER_RE.search(raw_text)
    if match:
        cleaned = str(match.group(1) or "").rstrip(").,;]\"'")
        if cleaned:
            return [cleaned]
    return _extract_urls(raw_text, limit=1)


def _extract_primary_file_path(text: str) -> List[str]:
    raw_text = str(text or "")
    match = _FILE_HEADER_RE.search(raw_text)
    if match:
        candidate = str(match.group(1) or "").strip().strip("'\"").rstrip(").,;]\"'")
        if candidate:
            if candidate.startswith("~"):
                try:
                    candidate = str(Path(candidate).expanduser())
                except Exception:
                    pass
            return [candidate]

    # Common pattern for write/edit tools: "... 'absolute/path' ..."
    quoted = re.search(r"'([^']+)'", raw_text)
    if quoted:
        candidate = str(quoted.group(1) or "").strip().rstrip(").,;]\"'")
        if candidate:
            if candidate.startswith("~"):
                try:
                    candidate = str(Path(candidate).expanduser())
                except Exception:
                    pass
            return [candidate]

    return _extract_file_paths(raw_text, limit=1)


def _extract_resources_for_tool(tool_name: str, content: str) -> Tuple[List[str], List[str]]:
    name = str(tool_name or "").strip()
    # URL tools
    if name in {"fetch_url"}:
        return _extract_primary_url(content), []
    # File tools
    if name in {"read_file", "write_file", "edit_file", "analyze_code"}:
        return [], _extract_primary_file_path(content)
    # Default: keep resource extraction bounded to avoid noisy chips (e.g. file contents).
    return _extract_urls(content, limit=3), _extract_file_paths(content, limit=3)


def _extract_artifact_refs(text: str) -> List[Dict[str, str]]:
    raw = str(text or "").strip()
    if not raw:
        return []

    out: List[Dict[str, str]] = []

    def _walk(val: Any) -> None:
        if isinstance(val, dict):
            if "$artifact" in val and isinstance(val.get("$artifact"), str) and str(val.get("$artifact")).strip():
                entry = {"artifact_id": str(val.get("$artifact")).strip()}
                if isinstance(val.get("filename"), str) and str(val.get("filename")).strip():
                    entry["filename"] = str(val.get("filename")).strip()
                if isinstance(val.get("content_type"), str) and str(val.get("content_type")).strip():
                    entry["content_type"] = str(val.get("content_type")).strip()
                out.append(entry)
            for v in val.values():
                _walk(v)
        elif isinstance(val, list):
            for item in val:
                _walk(item)

    if raw.startswith("{") or raw.startswith("["):
        try:
            parsed = json.loads(raw)
            _walk(parsed)
        except Exception:
            out = []

    if not out:
        for hit in _ARTIFACT_RE.findall(raw):
            if hit:
                out.append({"artifact_id": str(hit)})
    return out


def _extract_file_paths(text: str, *, limit: int = 10) -> List[str]:
    raw_text = str(text or "")
    # Avoid capturing URL path segments.
    for url in _URL_RE.findall(raw_text):
        raw_text = raw_text.replace(url, " ")

    candidates: List[str] = []
    candidates.extend(_WIN_PATH_RE.findall(raw_text))
    # Unix-ish absolute paths (macOS/Linux). Prefer absolute to avoid CWD ambiguity.
    candidates.extend(re.findall(r"(?:~|/)[^\s\"'<>]+", raw_text))

    out: List[str] = []
    for raw in candidates:
        cleaned = str(raw).strip().rstrip(").,;]\"'")
        if not cleaned:
            continue
        # Expand "~" when present so open() works reliably.
        if cleaned.startswith("~"):
            try:
                cleaned = str(Path(cleaned).expanduser())
            except Exception:
                pass
        out.append(cleaned)
        if len(out) >= int(limit):
            break
    return _dedupe_preserve_order(out)


def _tool_name_from_message(message: Dict[str, Any]) -> str:
    metadata = message.get("metadata")
    if isinstance(metadata, dict):
        name = metadata.get("name")
        if isinstance(name, str) and name.strip():
            raw = name.strip()
            if raw.lower().startswith("tool:"):
                raw = raw.split(":", 1)[1].strip()
            return raw or "tool"

    content = str(message.get("content") or "")

    # Common gateway tool transcript format: "[tool:web_search] ok"
    m = re.match(r"\s*\[\s*tool\s*:\s*([^\]\s]+)\s*\]", content, flags=re.I)
    if m:
        raw = str(m.group(1) or "").strip()
        if raw.lower().startswith("tool:"):
            raw = raw.split(":", 1)[1].strip()
        return raw or "tool"

    # Legacy/tool observation format: "[tool_name]:" (no "tool:" prefix).
    m = re.match(r"\s*\[([^\]]+)\]:", content)
    if m:
        raw = str(m.group(1) or "").strip()
        if raw.lower().startswith("tool:"):
            raw = raw.split(":", 1)[1].strip()
        return raw or "tool"

    # Some tool logs omit the trailing ":".
    m = re.match(r"\s*\[\s*([^\]\s:]+)\s*\]\s*(?:ok|error|done)?\b", content, flags=re.I)
    if m:
        raw = str(m.group(1) or "").strip()
        if raw.lower().startswith("tool:"):
            raw = raw.split(":", 1)[1].strip()
        return raw or "tool"

    return "tool"


def _extract_ask_user_prompt_from_tool_calls(metadata: Dict[str, Any]) -> str:
    """Best-effort extraction of ask_user(prompt=...) from tool-call metadata."""
    meta = dict(metadata or {}) if isinstance(metadata, dict) else {}
    tool_calls = meta.get("tool_calls")
    if tool_calls is None:
        tool_calls = meta.get("toolCalls")
    if not isinstance(tool_calls, list):
        return ""

    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        name = call.get("name")
        if name is None and isinstance(call.get("function"), dict):
            name = call["function"].get("name")
        if str(name or "").strip() != "ask_user":
            continue

        args = call.get("arguments")
        if args is None and isinstance(call.get("function"), dict):
            args = call["function"].get("arguments")

        parsed_args: Any = args
        if isinstance(args, str):
            try:
                parsed_args = json.loads(args)
            except Exception:
                parsed_args = args
        if isinstance(parsed_args, dict):
            prompt = parsed_args.get("prompt")
            if isinstance(prompt, str) and prompt.strip():
                return prompt.strip()
    return ""


def _extract_user_response_from_tool_content(content: str) -> str:
    raw = str(content or "").strip()
    if not raw:
        return ""

    # JSON payloads (common for tool outputs).
    if raw.startswith("{") and raw.endswith("}"):
        try:
            obj = json.loads(raw)
        except Exception:
            obj = None
        if isinstance(obj, dict):
            val = obj.get("response")
            if isinstance(val, str) and val.strip():
                return val.strip()

    # Loose "response: ..." formats.
    m = re.search(r"(?im)^\s*response\s*[:=]\s*(.+?)\s*$", raw)
    if m:
        return str(m.group(1) or "").strip()

    # Common "[tool]:" prefix.
    raw = re.sub(r"^\s*\[[^\]]+\]\s*:\s*", "", raw).strip()
    return raw


def _short_label_for_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = str(parsed.netloc or "").strip()
        if host:
            return host
    except Exception:
        pass
    return url


def _short_label_for_path(path: str) -> str:
    p = str(path or "").strip()
    if not p:
        return p
    try:
        parts = [part for part in Path(p).parts if part]
        tail = parts[-3:] if len(parts) > 3 else parts
        if tail:
            return "…/" + "/".join(tail) if len(parts) > len(tail) else "/".join(tail)
    except Exception:
        return p
    return p


def _is_image_target(target: str) -> bool:
    t = str(target or "").strip()
    if not t:
        return False
    if t.startswith("data:"):
        return False
    try:
        if t.startswith(("http://", "https://", "file://")):
            parsed = urlparse(t)
            suffix = Path(parsed.path or "").suffix.lower()
            return suffix in _IMAGE_EXTS
        suffix = Path(t).suffix.lower()
        return suffix in _IMAGE_EXTS
    except Exception:
        return False


def _normalize_image_target(target: str) -> Tuple[str, str]:
    """Return (kind, normalized_target)."""
    t = str(target or "").strip()
    if t.startswith("file://"):
        try:
            parsed = urlparse(t)
            file_path = unquote(parsed.path)
            return "file", str(Path(file_path).expanduser()) if file_path else file_path
        except Exception:
            return "file", t
    if t.startswith(("http://", "https://")):
        return "url", t
    # Only treat absolute-ish paths as files.
    if t.startswith(("~", "/", "\\")) or _WIN_PATH_RE.match(t):
        try:
            return "file", str(Path(t).expanduser()) if t.startswith("~") else t
        except Exception:
            return "file", t
    return "url", t


def _extract_images_from_text(text: str, *, limit: int = 6) -> Tuple[str, List[Dict[str, str]]]:
    """Extract image references and return cleaned text + thumbnail descriptors."""
    raw = str(text or "")
    thumbs: List[Dict[str, str]] = []

    def _add(target: str, label: str) -> None:
        if not _is_image_target(target):
            return
        kind, norm = _normalize_image_target(target)
        if not norm:
            return
        thumbs.append({"kind": kind, "target": norm, "label": str(label or "").strip()})

    # Markdown images: ![alt](url "title")
    def _md_repl(match: re.Match) -> str:
        alt = str(match.group(1) or "").strip()
        inner = str(match.group(2) or "").strip()
        # Strip optional title: take first token that looks like a URL/path.
        inner = inner.strip().strip("<>")
        target = inner.split()[0] if inner else ""
        _add(target, alt)
        return ""  # remove from visible transcript; thumbnails will render below.

    cleaned = _MD_IMAGE_RE.sub(_md_repl, raw)

    # HTML image tags (sometimes returned by models).
    def _html_repl(match: re.Match) -> str:
        target = str(match.group(1) or "").strip()
        _add(target, "")
        return ""

    cleaned = _HTML_IMG_RE.sub(_html_repl, cleaned)

    # Also detect bare image URLs / paths (do not remove from text).
    for url in _extract_urls(cleaned, limit=20):
        if _is_image_target(url):
            _add(url, _short_label_for_url(url))
    for path in _extract_file_paths(cleaned, limit=20):
        if _is_image_target(path):
            _add(path, _short_label_for_path(path))

    # Dedupe + cap.
    seen: set[str] = set()
    uniq: List[Dict[str, str]] = []
    for th in thumbs:
        target = str(th.get("target") or "")
        if not target or target in seen:
            continue
        seen.add(target)
        uniq.append(th)
        if len(uniq) >= int(limit):
            break

    # Light whitespace cleanup after removing markdown/html images.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, uniq


def _images_from_links(links: Sequence[Dict[str, str]], *, limit: int = 6) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for link in links or []:
        if not isinstance(link, dict):
            continue
        target = str(link.get("target") or "").strip()
        if not target or not _is_image_target(target):
            continue
        kind, norm = _normalize_image_target(target)
        label = str(link.get("label") or "").strip()
        out.append({"kind": kind, "target": norm, "label": label})
        if len(out) >= int(limit):
            break
    # Dedupe preserve order
    seen: set[str] = set()
    uniq: List[Dict[str, str]] = []
    for item in out:
        t = str(item.get("target") or "")
        if not t or t in seen:
            continue
        seen.add(t)
        uniq.append(item)
    return uniq


def _build_tool_summary(tool_events: Sequence[Dict[str, Any]]) -> str:
    summaries: List[str] = []
    for event in tool_events:
        s = str(event.get("summary") or "").strip()
        if s:
            summaries.append(s)
    summaries = _dedupe_preserve_order(summaries)
    if summaries:
        max_lines = 4
        shown = summaries[:max_lines]
        extra = max(0, len(summaries) - len(shown))
        joined = "\n".join(shown)
        if extra:
            joined = f"{joined}\n…+{extra} more"
        return joined.strip()

    order: List[str] = []
    counts: Dict[str, int] = {}
    for event in tool_events:
        name = str(event.get("name") or "tool").strip() or "tool"
        if name not in counts:
            counts[name] = 0
            order.append(name)
        counts[name] += 1

    parts: List[str] = []
    for name in order:
        count = counts.get(name, 0)
        if count > 1:
            parts.append(f"{name}×{count}")
        else:
            parts.append(name)
    joined = " • ".join(parts).strip()
    return f"🛠 {joined}" if joined else "🛠 tools"


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _truncate(text: str, *, max_len: int) -> str:
    s = _collapse_ws(text)
    if len(s) <= int(max_len):
        return s
    return s[: max(0, int(max_len) - 1)].rstrip() + "…"


def _try_parse_json(text: str) -> Any:
    raw_full = str(text or "")
    if not raw_full:
        return None

    raw = raw_full.lstrip()
    if raw.startswith("{") or raw.startswith("["):
        try:
            return json.loads(raw)
        except Exception:
            pass

    # Tool transcripts sometimes prefix the JSON with a status header, e.g.
    # "[tool:web_search] ok\n{...}". Attempt to decode from the first JSON token.
    # Keep this bounded to avoid expensive scans on large tool outputs.
    if len(raw_full) > 12000:
        raw_full = raw_full[:12000]
    decoder = json.JSONDecoder()
    hits = 0
    for m in re.finditer(r"[\[{]", raw_full):
        try:
            obj, _end = decoder.raw_decode(raw_full, m.start())
            return obj
        except Exception:
            pass
        hits += 1
        if hits >= 6:
            break
    return None


def _format_tool_event_summary(*, name: str, status_label: str, output_preview: str, meta: Dict[str, Any]) -> str:
    tool = str(name or "").strip() or "tool"
    if tool.lower().startswith("tool:"):
        tool = tool.split(":", 1)[1].strip() or "tool"
    status = str(status_label or "").strip().lower()
    status_icon = "✅" if status == "ok" else "⚠️" if status == "error" else "🛠"

    raw = str(output_preview or "").strip()
    obj = _try_parse_json(raw)

    # web_search-like tools
    if tool in {"web_search", "search_query", "web.search"} or tool.endswith("web_search"):
        query = ""
        engine = ""
        region = ""
        time_range = ""
        if isinstance(obj, dict):
            query = str(obj.get("query") or obj.get("q") or "").strip()
            engine = str(obj.get("engine") or obj.get("backend") or "").strip()
            params = obj.get("params")
            if isinstance(params, dict):
                region = str(params.get("region") or "").strip()
                time_range = str(params.get("time_range") or params.get("timeRange") or "").strip()
        if not query:
            args = meta.get("input") or meta.get("args") or meta.get("params")
            if isinstance(args, dict):
                query = str(args.get("query") or args.get("q") or "").strip()
        q = _truncate(query, max_len=72) if query else ""
        parts = [p for p in (engine, region, time_range) if p]
        suffix = f" ({', '.join(parts)})" if parts else ""
        if q:
            return f'{status_icon} 🔎 {tool}: “{q}”{suffix}'.strip()

    # fetch_url-like tools
    if tool in {"fetch_url", "web_fetch", "web.fetch"} or tool.endswith("fetch_url"):
        url = ""
        if isinstance(obj, dict):
            url = str(obj.get("url") or obj.get("URL") or "").strip()
        if not url:
            urls = _extract_primary_url(raw)
            url = urls[0] if urls else ""
        label = _short_label_for_url(url) if url else ""
        if label:
            return f"{status_icon} 🌐 {tool}: {label}".strip()

    # file tools
    if tool in {"read_file", "write_file", "edit_file", "delete_file"} or tool.endswith("_file"):
        icon = "📄"
        if tool.startswith(("write_", "edit_")):
            icon = "✍️"
        elif tool.startswith("delete_"):
            icon = "🗑️"
        path = ""
        paths = _extract_primary_file_path(raw)
        if paths:
            path = paths[0]
        label = _short_label_for_path(path) if path else ""
        if label:
            return f"{status_icon} {icon} {tool}: {label}".strip()

    # command tools
    if tool in {"execute_command", "exec_command", "run_command", "shell"}:
        cmd = ""
        if isinstance(obj, dict):
            cmd = str(obj.get("cmd") or obj.get("command") or obj.get("expression") or "").strip()
        if not cmd:
            cmd = raw.splitlines()[0] if raw else ""
        if cmd:
            return f"{status_icon} ⌨️ {tool}: {_truncate(cmd, max_len=90)}".strip()

    # generic fallback
    preview = raw.splitlines()[0] if raw else ""
    snippet = _truncate(preview, max_len=96) if preview else ""
    if snippet:
        return f"{status_icon} {tool}: {snippet}".strip()
    return f"{status_icon} {tool}".strip()


def _build_tool_links(tool_events: Sequence[Dict[str, Any]], *, limit: int = 30) -> List[Dict[str, str]]:
    urls: List[str] = []
    paths: List[str] = []
    artifacts: List[Dict[str, Any]] = []
    run_id = ""
    for event in tool_events:
        urls.extend([str(u) for u in (event.get("urls") or []) if isinstance(u, str)])
        paths.extend([str(p) for p in (event.get("paths") or []) if isinstance(p, str)])
        arts = event.get("artifacts")
        if isinstance(arts, list):
            artifacts.extend([dict(a) for a in arts if isinstance(a, dict)])
        if not run_id:
            rid = str(event.get("run_id") or "").strip()
            if rid:
                run_id = rid

    links: List[Dict[str, str]] = []
    for url in _dedupe_preserve_order(urls):
        # Treat file:// links as files.
        if url.startswith("file://"):
            try:
                parsed = urlparse(url)
                file_path = unquote(parsed.path)
                if file_path:
                    links.append({"kind": "file", "target": file_path, "label": _short_label_for_path(file_path)})
                    continue
            except Exception:
                pass
        links.append({"kind": "url", "target": url, "label": _short_label_for_url(url)})
        if len(links) >= int(limit):
            return links

    for path in _dedupe_preserve_order(paths):
        links.append({"kind": "file", "target": path, "label": _short_label_for_path(path)})
        if len(links) >= int(limit):
            break

    for art in artifacts:
        artifact_id = str(art.get("artifact_id") or "").strip()
        if not artifact_id:
            continue
        label = str(art.get("filename") or "").strip() or f"artifact:{artifact_id[:8]}"
        link: Dict[str, str] = {"kind": "artifact", "target": artifact_id, "label": label}
        if run_id:
            link["run_id"] = run_id
        ct = str(art.get("content_type") or "").strip()
        if ct:
            link["content_type"] = ct
        links.append(link)
        if len(links) >= int(limit):
            break
    return links


def build_display_messages(raw_messages: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return user-visible transcript messages with attached tool summaries.

    Rules:
    - Drop role="system".
    - Drop assistant internal tool-call placeholders (`metadata.kind=="tool_calls"` with empty content).
    - Drop empty assistant messages.
    - Drop role="tool" bubbles, but attach a compact summary + resource links to the
      next user-visible assistant message.
    """
    pending_tools: List[Dict[str, Any]] = []
    out: List[Dict[str, Any]] = []

    for msg in raw_messages:
        if not isinstance(msg, dict):
            continue

        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        metadata = msg.get("metadata")
        meta = dict(metadata) if isinstance(metadata, dict) else {}
        kind = str(meta.get("kind") or "").strip().lower()

        if role == "system":
            continue

        if role == "tool":
            name = _tool_name_from_message(msg)
            if name == "ask_user":
                response_text = _extract_user_response_from_tool_content(content)
                if response_text:
                    out.append(
                        {
                            "role": "user",
                            "content": response_text,
                            "ui_kind": "agent_answer",
                        }
                    )
                continue

            success = meta.get("success") if isinstance(meta, dict) else None
            error = str(meta.get("error") or "").strip() if isinstance(meta, dict) else ""
            output_preview = (
                str(meta.get("output_preview") or content or "").strip() if isinstance(meta, dict) else content.strip()
            )
            artifacts = []
            if isinstance(meta, dict):
                arts = meta.get("artifacts")
                if isinstance(arts, list):
                    artifacts = [dict(a) for a in arts if isinstance(a, dict)]
            if not artifacts:
                artifacts = _extract_artifact_refs(output_preview or content)
            run_id = str(msg.get("run_id") or meta.get("run_id") or "").strip()
            if not output_preview and error:
                output_preview = error
            if not output_preview:
                output_preview = "(no output)"
            if error and name in {"write_file", "edit_file", "delete_file"}:
                lowered = error.lower()
                if "workspace" in lowered or "workspace_root" in lowered or "outside" in lowered:
                    output_preview = (
                        f"{output_preview}\n\n"
                        "Hint: Gateway workspace restrictions blocked this path. "
                        "Set ABSTRACTGATEWAY_WORKSPACE_DIR or ABSTRACTGATEWAY_WORKSPACE_MOUNTS on the gateway."
                    )
            status_label = "ok" if success is True else "error" if error or success is False else "done"

            # Heuristic: gateway tool messages often embed a status header in the output.
            tool_payload_preview = output_preview
            try:
                lines = output_preview.splitlines()
            except Exception:
                lines = []
            if lines:
                head = str(lines[0] or "")
                # "[tool:name] ok" or "[name] ok"
                m = re.match(r"^\s*\[\s*tool\s*:[^\]]+\]\s*(ok|error|done)?\s*$", head, flags=re.I)
                if m:
                    hint = str(m.group(1) or "").strip().lower()
                    if status_label == "done" and hint in {"ok", "error"}:
                        status_label = hint
                    rest = "\n".join(lines[1:]).strip()
                    if rest:
                        tool_payload_preview = rest
                else:
                    m = re.match(r"^\s*\[\s*[^\]]+\s*\]\s*(ok|error)\b", head, flags=re.I)
                    if m and status_label == "done":
                        status_label = str(m.group(1) or "").strip().lower() or status_label
                        rest = "\n".join(lines[1:]).strip()
                        if rest:
                            tool_payload_preview = rest
                    elif status_label == "done":
                        m = re.match(r"^\s*(ok|error)\s*$", head, flags=re.I)
                        if m:
                            status_label = str(m.group(1) or "").strip().lower() or status_label
                            rest = "\n".join(lines[1:]).strip()
                            if rest:
                                tool_payload_preview = rest

            summary = _format_tool_event_summary(
                name=str(name),
                status_label=str(status_label),
                output_preview=str(tool_payload_preview),
                meta=meta,
            )
            urls, paths = _extract_resources_for_tool(name, content)
            pending_tools.append(
                {
                    "name": name,
                    "status": status_label,
                    "summary": summary,
                    "urls": urls,
                    "paths": paths,
                    "artifacts": artifacts,
                    "run_id": run_id,
                }
            )
            continue

        if role == "assistant":
            from_tool_calls_prompt = False
            if kind == "tool_calls" and not content.strip():
                # Internal placeholder used to preserve tool-call metadata for providers.
                prompt = _extract_ask_user_prompt_from_tool_calls(meta)
                if prompt:
                    content = prompt
                    kind = ""
                    meta = {}
                    from_tool_calls_prompt = True
                else:
                    continue

            ui_kind = ""
            if from_tool_calls_prompt:
                ui_kind = "agent_question"
            elif re.match(r"(?is)^\s*\[\s*agent\s+question\s*\]\s*:\s*", content):
                ui_kind = "agent_question"
                content = re.sub(r"(?is)^\s*\[\s*agent\s+question\s*\]\s*:\s*", "", content).strip()

            cleaned_content, content_images = _extract_images_from_text(content)
            rendered = dict(msg)
            rendered["content"] = cleaned_content
            if ui_kind:
                rendered["ui_kind"] = ui_kind
            images: List[Dict[str, str]] = list(content_images)
            if pending_tools:
                rendered["tool_summary"] = _build_tool_summary(pending_tools)
                links = _build_tool_links(pending_tools)
                if links:
                    rendered["tool_links"] = links
                    images.extend(_images_from_links(links))
                pending_tools = []
            if images:
                # Dedupe by target.
                seen_targets: set[str] = set()
                deduped: List[Dict[str, str]] = []
                for img in images:
                    if not isinstance(img, dict):
                        continue
                    target = str(img.get("target") or "").strip()
                    if not target or target in seen_targets:
                        continue
                    seen_targets.add(target)
                    deduped.append({"kind": str(img.get("kind") or "url"), "target": target, "label": str(img.get("label") or "")})
                if deduped:
                    rendered["image_thumbnails"] = deduped

            if not cleaned_content.strip() and not rendered.get("tool_summary") and not rendered.get("image_thumbnails"):
                # Avoid blank bubbles in the user-visible transcript.
                continue
            out.append(rendered)
            continue

        # Default: user / other roles.
        if role == "user" and re.match(r"(?is)^\s*\[\s*user\s+response\s*\]\s*:\s*", content):
            cleaned = re.sub(r"(?is)^\s*\[\s*user\s+response\s*\]\s*:\s*", "", content).strip()
            out.append({"role": "user", "content": cleaned, "ui_kind": "agent_answer"})
        else:
            out.append(dict(msg))

    # Best-effort: attach any leftover tool events to the last assistant message.
    if pending_tools and out:
        for rendered in reversed(out):
            if str(rendered.get("role") or "") != "assistant":
                continue
            rendered.setdefault("tool_summary", _build_tool_summary(pending_tools))
            links = _build_tool_links(pending_tools)
            if links:
                rendered.setdefault("tool_links", links)
            break

    return out
