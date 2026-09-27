"""What a chat is worth knowing at a glance.

The session switcher needs more than "date - first question": how recent the
chat is, how much work it holds (turns, tool calls, tokens, wall time), where
its files live, and whether the last turn actually got answered. WHICH sessions
exist, their turn counts, states and titles come from the gateway
(`gateway_sessions`, cached by `session_cache`); the per-transcript metrics here
are computed from each session's CACHED `session.json`, so a digest is a local
read, never a gateway call.

Transcripts can be megabytes, so reads are cached by (path, mtime, size).
Measured on a real store — 74 chats, 9.8 MB — that is 42 ms cold and under 2 ms
warm, cheap enough that the switcher reads them synchronously when it opens:
filling metrics in afterwards meant rebuilding rows under an open popup, which
is what `digest_from_record`'s index-only digest (`detailed=False`) was for.
It survives as the fallback when a transcript cannot be read.

Everything here is Qt-free and pure: the formatting helpers take an explicit
``now`` so they can be tested without freezing the clock.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "SessionDigest",
    "SessionDigestCache",
    "digest_from_record",
    "digest_from_snapshot",
    "format_count",
    "format_duration_ms",
    "format_tokens",
    "parse_timestamp",
    "recency_group",
    "relative_time",
    "session_matches_query",
    "sort_digests",
    "workspace_label",
]

# Group headers, newest first. `recency_group` returns one of these.
RECENCY_GROUPS: Tuple[str, ...] = (
    "Today",
    "Yesterday",
    "Previous 7 days",
    "Previous 30 days",
    "Older",
)

_PREVIEW_MAX = 140
_TOP_TOOLS = 3


# --------------------------------------------------------------------- model


@dataclass(frozen=True)
class SessionDigest:
    """One chat, as the switcher shows it.

    ``detailed`` is False for an index-only digest: the transcript has not been
    read yet, so every count is 0 and the UI must not present them as facts.
    """

    session_id: str
    title: str = "New session"
    created_at: str = ""
    updated_at: str = ""
    detailed: bool = False
    # transcript-derived
    messages: int = 0
    turns: int = 0                       # user prompts (excluding ask_user replies)
    answers: int = 0                     # assistant replies
    tool_calls: int = 0
    failed_tools: int = 0
    top_tools: Tuple[str, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    runs: int = 0
    workspace_root: str = ""
    last_run_id: str = ""
    preview: str = ""
    first_prompt: str = ""
    last_role: str = ""
    last_message_at: str = ""
    attachments: int = 0
    # gateway-derived: the liveliest run state of the session
    # (waiting / running / failed / done / unknown), "" when not on the gateway
    state: str = ""
    # False for a session another client of the gateway started (see
    # session_cache.OWN_SESSION_PREFIX)
    own: bool = True

    @property
    def total_tokens(self) -> int:
        return int(self.input_tokens) + int(self.output_tokens)

    @property
    def display_title(self) -> str:
        """What to show: the session's name, else its opening question."""
        title = str(self.title or "").strip()
        if title and title.lower() != "new session":
            return title
        if self.first_prompt:
            return self.first_prompt
        return "Untitled session"

    @property
    def empty(self) -> bool:
        """A session with nothing in it (never used, or only a draft)."""
        return bool(self.detailed and self.messages == 0)

    @property
    def unanswered(self) -> bool:
        """The transcript ends on the user: the last question got no reply."""
        return bool(self.detailed and self.last_role == "user")

    @property
    def last_activity(self) -> str:
        """The most recent of the index stamp and the last message stamp."""
        candidates = [s for s in (self.last_message_at, self.updated_at, self.created_at) if s]
        return max(candidates, key=lambda s: parse_timestamp(s) or datetime.min.replace(tzinfo=timezone.utc)) if candidates else ""

    def with_details(self, other: "SessionDigest") -> "SessionDigest":
        """Index metadata (title, stamps) wins; transcript metrics come from
        ``other``. Used when a background read upgrades a drawn row."""
        return replace(
            other,
            session_id=self.session_id,
            title=self.title,
            created_at=self.created_at or other.created_at,
            updated_at=self.updated_at or other.updated_at,
        )


# ----------------------------------------------------------------- computing


def _clean_text(value: Any, *, limit: int = _PREVIEW_MAX) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def digest_from_record(record: Dict[str, Any]) -> SessionDigest:
    """Index-only digest: what `sessions.json` knows, with no transcript read."""
    rec = record if isinstance(record, dict) else {}
    return SessionDigest(
        session_id=str(rec.get("session_id") or "").strip(),
        title=_clean_text(rec.get("title") or "New session", limit=120) or "New session",
        created_at=str(rec.get("created_at") or ""),
        updated_at=str(rec.get("updated_at") or ""),
        detailed=False,
    )


def _usage_tokens(usage: Any) -> Tuple[int, int]:
    if not isinstance(usage, dict):
        return 0, 0

    def _pick(*names: str) -> int:
        for name in names:
            value = usage.get(name)
            if isinstance(value, (int, float)) and value >= 0:
                return int(value)
        return 0

    return _pick("input_tokens", "prompt_tokens"), _pick("output_tokens", "completion_tokens")


def digest_from_snapshot(record: Dict[str, Any], snapshot: Dict[str, Any]) -> SessionDigest:
    """Full digest: index metadata plus everything the transcript proves."""
    base = digest_from_record(record)
    snap = snapshot if isinstance(snapshot, dict) else {}
    messages = snap.get("messages")
    messages = list(messages) if isinstance(messages, list) else []

    turns = answers = tool_calls = failed_tools = attachments = 0
    input_tokens = output_tokens = duration_ms = 0
    tool_counts: Dict[str, int] = {}
    seen_runs: set = set()
    preview = ""
    first_prompt = ""
    last_role = ""
    last_ts = ""

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "")
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        stamp = str(message.get("ts") or "").strip()
        if stamp:
            last_ts = stamp
        if role in {"user", "assistant"}:
            last_role = role
        if role == "user":
            # A runtime ask_user answer is not a turn the user opened.
            if not content.startswith("[User response]:"):
                turns += 1
                text = _clean_text(content)
                if text:
                    preview = text
                    if not first_prompt:
                        first_prompt = _clean_text(content, limit=80)
            media = metadata.get("attachments") or metadata.get("media")
            if isinstance(media, list):
                attachments += len(media)
        elif role == "assistant":
            answers += 1
            stats = metadata.get("_assistant_stats")
            if isinstance(stats, dict):
                run_id = str(stats.get("run_id") or "").strip()
                if run_id and run_id not in seen_runs:
                    seen_runs.add(run_id)
                    value = stats.get("duration_ms")
                    if isinstance(value, (int, float)) and value > 0:
                        duration_ms += int(value)
                    gained_in, gained_out = _usage_tokens(stats.get("usage"))
                    input_tokens += gained_in
                    output_tokens += gained_out
        elif role == "tool":
            tool_calls += 1
            name = str(metadata.get("name") or "").strip()
            if name:
                tool_counts[name] = tool_counts.get(name, 0) + 1
            if metadata.get("success") is False:
                failed_tools += 1

    top_tools = tuple(
        name for name, _count in sorted(tool_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:_TOP_TOOLS]
    )
    return SessionDigest(
        session_id=base.session_id,
        title=base.title,
        created_at=base.created_at,
        updated_at=base.updated_at,
        detailed=True,
        messages=len(messages),
        turns=turns,
        answers=answers,
        tool_calls=tool_calls,
        failed_tools=failed_tools,
        top_tools=top_tools,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
        runs=len(seen_runs),
        workspace_root=str(snap.get("workspace_root") or "").strip(),
        last_run_id=str(snap.get("last_run_id") or "").strip(),
        preview=preview,
        first_prompt=first_prompt,
        last_role=last_role,
        last_message_at=last_ts,
        attachments=attachments,
    )


class SessionDigestCache:
    """Transcript digests, cached by file identity.

    A chat is re-read only when its `session.json` changed (mtime or size), so
    reopening the switcher is instant and a long transcript is parsed once.
    Safe to call from a worker thread.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[str, Tuple[Tuple[float, int], SessionDigest]] = {}

    def cached(self, session_id: str) -> Optional[SessionDigest]:
        with self._lock:
            entry = self._entries.get(str(session_id or "").strip())
        return entry[1] if entry else None

    def digest(self, record: Dict[str, Any], data_dir: Any) -> SessionDigest:
        """The full digest for one chat, reading its transcript if needed."""
        base = digest_from_record(record)
        if not base.session_id:
            return base
        path = Path(data_dir) / "session.json"
        try:
            stat = path.stat()
            key = (float(stat.st_mtime), int(stat.st_size))
        except Exception:
            # No transcript on disk yet: an empty chat, not an unknown one.
            return replace(base, detailed=True)
        with self._lock:
            entry = self._entries.get(base.session_id)
        if entry is not None and entry[0] == key:
            return base.with_details(entry[1])
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return base
        digest = digest_from_snapshot(record, payload if isinstance(payload, dict) else {})
        with self._lock:
            self._entries[base.session_id] = (key, digest)
        return digest

    def warm(self, records: Sequence[Dict[str, Any]], data_dir_for) -> List[SessionDigest]:
        """Digest every record (call this on a worker thread)."""
        out: List[SessionDigest] = []
        for record in records or []:
            if not isinstance(record, dict):
                continue
            try:
                out.append(self.digest(record, data_dir_for(str(record.get("session_id") or ""))))
            except Exception:
                out.append(digest_from_record(record))
        return out

    def forget(self, session_id: str) -> None:
        with self._lock:
            self._entries.pop(str(session_id or "").strip(), None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# ---------------------------------------------------------------- formatting


def parse_timestamp(value: Any) -> Optional[datetime]:
    """ISO-8601 (with or without zone) → aware datetime, or None."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def relative_time(value: Any, *, now: Optional[datetime] = None) -> str:
    """"just now", "12 min ago", "3 h ago", "Yesterday", "Mar 18"."""
    parsed = parse_timestamp(value)
    if parsed is None:
        return ""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = parsed.astimezone()
    local_now = current.astimezone()
    seconds = (current - parsed).total_seconds()
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    same_day = local.date() == local_now.date()
    if same_day:
        hours = int(seconds // 3600)
        return f"{hours} h ago" if hours >= 1 else "just now"
    days = (local_now.date() - local.date()).days
    if days == 1:
        return "Yesterday"
    if days < 7:
        return local.strftime("%A")
    if local.year == local_now.year:
        return local.strftime("%b %-d") if hasattr(local, "strftime") else local.strftime("%b %d")
    return local.strftime("%b %-d, %Y")


def recency_group(value: Any, *, now: Optional[datetime] = None) -> str:
    """Which switcher section a chat belongs to."""
    parsed = parse_timestamp(value)
    if parsed is None:
        return RECENCY_GROUPS[-1]
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = parsed.astimezone()
    local_now = current.astimezone()
    days = (local_now.date() - local.date()).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return "Previous 7 days"
    if days < 30:
        return "Previous 30 days"
    return "Older"


def format_count(value: Any) -> str:
    """1 → "1", 1234 → "1.2k", 1200000 → "1.2M"."""
    try:
        count = int(value)
    except Exception:
        return "0"
    if count < 1000:
        return str(count)
    if count < 1_000_000:
        trimmed = f"{count / 1000:.1f}".rstrip("0").rstrip(".")
        return f"{trimmed}k"
    trimmed = f"{count / 1_000_000:.1f}".rstrip("0").rstrip(".")
    return f"{trimmed}M"


def format_tokens(value: Any) -> str:
    return f"{format_count(value)} tk"


def format_duration_ms(value: Any) -> str:
    """Wall time a chat spent running: "8 s", "4 min", "1 h 12"."""
    try:
        ms = int(value)
    except Exception:
        return ""
    if ms <= 0:
        return ""
    seconds = ms / 1000.0
    if seconds < 60:
        return f"{int(round(seconds))} s"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"{int(round(minutes))} min"
    hours = int(minutes // 60)
    rest = int(minutes % 60)
    return f"{hours} h {rest:02d}" if rest else f"{hours} h"


def workspace_label(root: Any) -> str:
    """The folder name a chat works in, without the path noise.

    A gateway-minted workspace is a bare hex id; showing it would be noise, so
    it reads as what it is instead.
    """
    text = str(root or "").strip().rstrip("/")
    if not text:
        return ""
    name = text.rsplit("/", 1)[-1] or text
    compact = name.replace("-", "")
    if len(compact) >= 24 and all(c in "0123456789abcdefABCDEF" for c in compact):
        return "gateway folder"
    return name


def session_matches_query(digest: SessionDigest, query: str) -> bool:
    """Filter across title, preview, workspace and tool names."""
    needle = " ".join(str(query or "").split()).strip().lower()
    if not needle:
        return True
    haystack = " ".join(
        [
            digest.display_title,
            digest.title,
            digest.preview,
            digest.first_prompt,
            digest.workspace_root,
            " ".join(digest.top_tools),
            digest.session_id,
        ]
    ).lower()
    return all(part in haystack for part in needle.split())


def sort_digests(digests: Sequence[SessionDigest]) -> List[SessionDigest]:
    """Most recently active first; undated chats last."""
    floor = datetime.min.replace(tzinfo=timezone.utc)

    def _key(digest: SessionDigest):
        return parse_timestamp(digest.last_activity) or floor

    return sorted(list(digests or []), key=_key, reverse=True)
