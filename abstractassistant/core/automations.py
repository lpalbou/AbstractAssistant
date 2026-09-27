"""Automations v1 — pure presentation rules (Qt-free, network-free).

The Qt mirror of the kit's `panel_core.ts` (`@abstractframework/ui-kit`,
`src/automations/panel_core.ts`): cadence labels, which controls are enabled,
occurrences as chat pairs, the attention cursor to acknowledge, the schedule
presets and the exact ``POST /api/gateway/automations`` body. Plus what only
the Assistant needs: which session kinds belong in the regular list, and the
notification ledger (one tray notification per attention item / pending wait).

Everything here reads STRUCTURE only — statuses, ``notify`` objects, waits,
config fields, ``session_kind`` — never model prose and never id prefixes.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "CONTROL_COMMANDS",
    "REGULAR_SESSION_KINDS",
    "SCHEDULE_PRESETS",
    "API_ERROR_TEXT",
    "AttentionNotice",
    "NotificationLedger",
    "OccurrenceView",
    "ScheduleWhen",
    "api_error_text",
    "attention_ack_cursor",
    "attention_total",
    "automation_controls",
    "build_create_request",
    "default_title",
    "format_utc",
    "group_by_automation",
    "interval_label",
    "is_regular_session_kind",
    "new_attention_notices",
    "occurrence_views",
    "parse_duration",
    "revise_changes",
    "schedule_config",
    "schedule_label",
    "target_from_workflow",
    "trigger_summary",
]

# ------------------------------------------------------------------ cadence

DURATION_RE = re.compile(r"^([1-9][0-9]*)([smhd])$")
_UNIT_WORDS = {"s": ("second", "seconds"), "m": ("minute", "minutes"), "h": ("hour", "hours"), "d": ("day", "days")}


def parse_duration(value: Any) -> Optional[Tuple[int, str]]:
    """``"8h"`` → ``(8, "h")``; anything not matching the contract's duration → None."""
    if not isinstance(value, str):
        return None
    m = DURATION_RE.match(value)
    return (int(m.group(1)), m.group(2)) if m else None


def interval_label(every: str) -> str:
    """``"8h"`` → ``"every 8 hours"``, ``"1h"`` → ``"every hour"`` (fixed UTC intervals)."""
    parsed = parse_duration(every)
    if parsed is None:
        return f"every {every}"
    amount, unit = parsed
    one, many = _UNIT_WORDS[unit]
    return f"every {one}" if amount == 1 else f"every {amount} {many}"


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_utc(ts: Any) -> str:
    """``2026-09-27T08:00:00Z`` → ``2026-09-27 08:00 UTC`` (seconds only when non-zero)."""
    parsed = _parse_ts(ts)
    if parsed is None:
        return str(ts or "")
    base = parsed.strftime("%Y-%m-%d %H:%M")
    return f"{base}{'' if parsed.second == 0 else parsed.strftime(':%S')} UTC"


def schedule_label(config: Mapping[str, Any]) -> str:
    """``schedule@1`` config → ``"every 8 hours (UTC)"`` / ``"once at … UTC"`` + bounds."""
    cfg = config if isinstance(config, Mapping) else {}
    every = cfg.get("every")
    if not isinstance(every, str):
        start = cfg.get("start_at")
        return f"once at {format_utc(start)}" if start else "once, now"
    parts = [f"{interval_label(every)} (UTC)"]
    count = cfg.get("count")
    if isinstance(count, int) and not isinstance(count, bool):
        parts.append(f"{count} {'run' if count == 1 else 'runs'} max")
    until = cfg.get("until")
    if isinstance(until, str) and until:
        parts.append(f"until {format_utc(until)}")
    return " · ".join(parts)


def trigger_summary(trigger: Mapping[str, Any]) -> str:
    """The cadence label of a ``TriggerBinding``."""
    t = trigger if isinstance(trigger, Mapping) else {}
    source, version = t.get("source_id"), t.get("source_version")
    if source == "schedule" and version == 1:
        return schedule_label(t.get("config") or {})
    if source == "manual" and version == 1:
        return "manual runs only"
    return f"{source}@{version}"


STATUS_LABELS = {
    "active": "Active",
    "paused": "Paused",
    "completed": "Completed",
    "failed": "Failed",
    "archived": "Archived",
}

# ----------------------------------------------------------------- controls

CONTROL_COMMANDS = {
    "pause": "automation.pause",
    "resume": "automation.resume",
    "run_now": "automation.run_now",
    "stop_current": "automation.stop_current",
    "archive": "automation.archive",
}
_IN_PROGRESS = {"running", "waiting", "backoff"}


def occurrence_in_progress(summary: Mapping[str, Any], occurrences: Sequence[Mapping[str, Any]] = ()) -> bool:
    last = summary.get("last_occurrence")
    if isinstance(last, Mapping) and last.get("status") in _IN_PROGRESS:
        return True
    return any(o.get("status") in _IN_PROGRESS for o in occurrences)


def automation_controls(
    summary: Mapping[str, Any],
    occurrences: Sequence[Mapping[str, Any]] = (),
    *,
    busy: bool = False,
) -> Dict[str, Tuple[bool, str]]:
    """``control -> (enabled, reason)``. The server decides what the principal
    may do (``capabilities``); the status decides which of them apply now.
    Run now stays enabled while paused (it does not resume)."""
    caps = set(summary.get("capabilities") or ())
    status = summary.get("status")
    running = occurrence_in_progress(summary, occurrences)
    live = status in {"active", "paused"}

    def gate(control: str, ok: bool, reason: str) -> Tuple[bool, str]:
        if busy:
            return False, "Working…"
        if summary.get("legacy"):
            return False, "Legacy schedule: managed with its existing controls."
        if control not in caps:
            return False, "Not permitted for this automation."
        if status == "archived":
            return False, "Archived: history is kept, nothing runs."
        return (True, "") if ok else (False, reason)

    return {
        "pause": gate("pause", status == "active", "Already paused." if status == "paused" else "The automation has ended."),
        "resume": gate("resume", status == "paused", "Already running on schedule." if status == "active" else "The automation has ended."),
        "run_now": gate("run_now", live and not running, "An occurrence is in progress." if running else "The automation has ended."),
        "stop_current": gate("stop_current", running, "Nothing is running."),
        "revise": gate("revise", True, ""),
        "archive": gate("archive", True, ""),
        "discuss": gate("discuss", True, ""),
    }


# ------------------------------------------------------ occurrences as chat


@dataclass(frozen=True)
class OccurrenceView:
    row: Mapping[str, Any]
    tone: str  # quiet | notified | failed | waiting | running
    notable: bool
    badge: str
    status_text: str
    can_discuss: bool


def occurrence_tone(row: Mapping[str, Any]) -> str:
    if row.get("status") == "failed":
        return "failed"
    if row.get("waits") or row.get("status") == "waiting":
        return "waiting"
    if row.get("notify") is not None:
        return "notified"
    if row.get("status") in {"running", "backoff"}:
        return "running"
    return "quiet"


def occurrence_views(rows: Iterable[Mapping[str, Any]]) -> List[OccurrenceView]:
    """Chronological (oldest first) chat pairs, whatever the page order."""
    out: List[OccurrenceView] = []
    for row in sorted((r for r in rows if isinstance(r, Mapping)), key=lambda r: int(r.get("index") or 0)):
        tone = occurrence_tone(row)
        attempts = int(row.get("attempts") or 1)
        attempts_text = f"{attempts} {'attempt' if attempts == 1 else 'attempts'}"
        badge = {
            "failed": f"Failed after {attempts_text}",
            "waiting": "Waiting for you",
            "notified": "Notified",
            "running": "Running",
        }.get(tone, "")
        status = str(row.get("status") or "")
        status_text = f"completed after {attempts_text}" if status == "completed" and attempts > 1 else status
        out.append(
            OccurrenceView(
                row=row,
                tone=tone,
                notable=tone in {"failed", "waiting", "notified"},
                badge=badge,
                status_text=status_text,
                can_discuss=status not in _IN_PROGRESS,
            )
        )
    return out


# ---------------------------------------------------------------- attention


def attention_ack_cursor(summary: Mapping[str, Any]) -> Optional[str]:
    """The cursor to acknowledge after showing ``attention.items``: the LAST
    DISPLAYED item's, never ``attention.cursor`` (items beyond those shown stay
    unseen)."""
    attention = summary.get("attention") if isinstance(summary, Mapping) else None
    items = attention.get("items") if isinstance(attention, Mapping) else None
    if isinstance(items, list) and items and isinstance(items[-1], Mapping):
        cursor = items[-1].get("cursor")
        return cursor if isinstance(cursor, str) and cursor else None
    return None


def attention_total(summaries: Iterable[Mapping[str, Any]]) -> int:
    """Unread count for the tray and the section: unseen items + pending waits."""
    total = 0
    for summary in summaries:
        attention = summary.get("attention") if isinstance(summary, Mapping) else None
        if isinstance(attention, Mapping):
            total += int(attention.get("unseen_count") or 0) + int(attention.get("pending_waits") or 0)
    return total


def group_by_automation(summaries: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """One row per ``automation_id`` (the last summary seen for an id wins;
    first-seen order kept). Never grouped by session."""
    order: List[str] = []
    by_id: Dict[str, Mapping[str, Any]] = {}
    for summary in summaries:
        if not isinstance(summary, Mapping):
            continue
        aid = summary.get("automation_id")
        if not isinstance(aid, str) or not aid:
            continue
        if aid not in by_id:
            order.append(aid)
        by_id[aid] = summary
    return [by_id[aid] for aid in order]


@dataclass(frozen=True)
class AttentionNotice:
    """One tray notification."""

    key: str
    automation_id: str
    title: str
    body: str
    kind: str  # notify | failure | wait


class NotificationLedger:
    """Which attention items and waits were already notified (per gateway).

    Persisted so a relaunch does not replay old notifications; the gateway's
    seen cursor is a different thing (it moves when the user VIEWS the
    automation). Keys are opaque: ``item:<automation_id>:<cursor>`` and
    ``wait:<run_id>:<wait_key>``. Bounded.
    """

    MAX_KEYS = 2000

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = threading.Lock()
        self._keys: List[str] = []
        if self._path is not None and self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                keys = data.get("notified") if isinstance(data, dict) else None
                if isinstance(keys, list):
                    self._keys = [str(k) for k in keys if isinstance(k, str)][-self.MAX_KEYS :]
            except Exception:
                self._keys = []

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._keys

    def add(self, keys: Iterable[str]) -> None:
        with self._lock:
            changed = False
            for key in keys:
                if key not in self._keys:
                    self._keys.append(key)
                    changed = True
            if not changed:
                return
            self._keys = self._keys[-self.MAX_KEYS :]
            if self._path is None:
                return
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), prefix=".notified-")
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump({"schema_version": 1, "notified": self._keys}, handle)
                os.replace(tmp, self._path)
            except Exception:
                pass  # in-memory dedupe still holds for this process


def new_attention_notices(
    summaries: Iterable[Mapping[str, Any]],
    attention_pages: Mapping[str, Sequence[Mapping[str, Any]]],
    ledger: NotificationLedger,
) -> List[AttentionNotice]:
    """Notices not yet notified: every unseen attention item (from the paged
    ``…/attention`` route when fetched, else the summary's own items) and every
    pending interactive wait. Quiet occurrences never produce an item, so they
    never notify. The caller records the keys once the notices are shown."""
    out: List[AttentionNotice] = []
    for summary in summaries:
        aid = str(summary.get("automation_id") or "")
        title = str(summary.get("title") or "Automation")
        attention = summary.get("attention") if isinstance(summary.get("attention"), Mapping) else {}
        items = attention_pages.get(aid)
        if items is None:
            items = attention.get("items") if isinstance(attention.get("items"), list) else []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            cursor = str(item.get("cursor") or "")
            if not cursor:
                continue
            key = f"item:{aid}:{cursor}"
            if key in ledger:
                continue
            kind = str(item.get("kind") or "notify")
            out.append(
                AttentionNotice(
                    key=key,
                    automation_id=aid,
                    title=str(item.get("title") or title),
                    body=str(item.get("body") or ("The automation failed." if kind == "failure" else "")),
                    kind=kind,
                )
            )
        waits = attention.get("waits") if isinstance(attention.get("waits"), list) else []
        for wait in waits:
            if not isinstance(wait, Mapping):
                continue
            run_id, wait_key = str(wait.get("run_id") or ""), str(wait.get("wait_key") or "")
            if not run_id or not wait_key:
                continue
            key = f"wait:{run_id}:{wait_key}"
            if key in ledger:
                continue
            out.append(
                AttentionNotice(
                    key=key,
                    automation_id=aid,
                    title=f"{title} is waiting for you",
                    body=str(wait.get("prompt") or "An occurrence is waiting for your answer."),
                    kind="wait",
                )
            )
    return out


# -------------------------------------------------------- regular sessions

# The regular session list shows chats and discussions; automation and
# occurrence sessions live under the Automations section. A row without a
# `session_kind` comes from a gateway that does not stamp it yet: a chat.
REGULAR_SESSION_KINDS = frozenset({"chat", "discussion"})


def is_regular_session_kind(kind: Any) -> bool:
    value = str(kind or "").strip()
    return value == "" or value in REGULAR_SESSION_KINDS


# ----------------------------------------------------------------- schedule


@dataclass(frozen=True)
class ScheduleWhen:
    """``kind="every"`` with ``amount``/``unit`` (m|h|d), or ``kind="once"`` with ``at``."""

    kind: str
    amount: int = 0
    unit: str = "h"
    at: str = ""


SCHEDULE_PRESETS: Tuple[Tuple[str, ScheduleWhen], ...] = (
    ("every 5 minutes", ScheduleWhen("every", 5, "m")),
    ("every 30 minutes", ScheduleWhen("every", 30, "m")),
    ("every hour", ScheduleWhen("every", 1, "h")),
    ("every 8 hours", ScheduleWhen("every", 8, "h")),
    ("every 24 hours", ScheduleWhen("every", 24, "h")),
    ("every 7 days", ScheduleWhen("every", 7, "d")),
)

_LOCAL_INPUT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(:\d{2})?$")


def utc_from_input(value: str) -> Optional[str]:
    """``YYYY-MM-DD HH:MM[:SS]`` read as UTC → RFC3339, or None."""
    m = _LOCAL_INPUT_RE.match(str(value or "").strip())
    if not m:
        return None
    ts = f"{m.group(1)}T{m.group(2)}{m.group(3) or ':00'}Z"
    return ts if _parse_ts(ts) is not None else None


def schedule_config(when: ScheduleWhen, *, start_at: str = "", count: Optional[int] = None) -> Tuple[Dict[str, Any], List[str]]:
    """``schedule@1`` config + the reasons it is invalid."""
    errors: List[str] = []
    config: Dict[str, Any] = {}
    if when.kind == "once":
        at = utc_from_input(when.at)
        if not at:
            errors.append("Pick the date and time (UTC) to run once.")
        else:
            config["start_at"] = at
        return config, errors
    if when.unit not in {"m", "h", "d"} or not isinstance(when.amount, int) or when.amount < 1:
        errors.append("The interval must be a whole number of minutes, hours or days (at least 1).")
    else:
        config["every"] = f"{when.amount}{when.unit}"
    if start_at:
        s = utc_from_input(start_at)
        if not s:
            errors.append("First run must be a date and time (UTC).")
        else:
            config["start_at"] = s
    if count is not None:
        if not isinstance(count, int) or count < 1:
            errors.append("Maximum runs must be a whole number of at least 1.")
        else:
            config["count"] = count
    return config, errors


def default_title(prompt: str) -> str:
    """The prompt's first line, at most 120 characters."""
    lines = str(prompt or "").strip().split("\n")
    first = lines[0].strip() if lines else ""
    return first if len(first) <= 120 else first[:119] + "…"


def target_from_workflow(selection: Any) -> Optional[Dict[str, Any]]:
    """The create-request ``target`` for the conversation's workflow selection
    (`preferences.WorkflowSelection`): the gateway default as
    ``{flow_id:"@default", interface}``, else ``{bundle_ref, flow_id}``."""
    if selection is None:
        return None
    flow_id = str(getattr(selection, "flow_id", "") or "")
    if not flow_id:
        return None
    if flow_id == "@default":
        interface = str(getattr(selection, "interface", "") or "")
        return {"flow_id": "@default", "interface": interface} if interface else None
    bundle_id = str(getattr(selection, "bundle_id", "") or "")
    if not bundle_id:
        return None
    version = str(getattr(selection, "bundle_version", "") or "")
    return {"bundle_ref": f"{bundle_id}@{version}" if version else bundle_id, "flow_id": flow_id}


def build_create_request(
    *,
    prompt: str,
    when: ScheduleWhen,
    context: str,
    target: Optional[Mapping[str, Any]],
    request_id: str,
    title: str = "",
    start_at: str = "",
    count: Optional[int] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """The ``POST /api/gateway/automations`` body, or the reasons it cannot be built."""
    errors: List[str] = []
    if not target:
        errors.append("This conversation has no workflow to schedule.")
    text = str(prompt or "").strip()
    if not text:
        errors.append("Write the task to run.")
    name = str(title or "").strip() or default_title(text)
    if len(name) > 120:
        errors.append("Title is at most 120 characters.")
    if context not in {"independent", "growing"}:
        errors.append("Context must be Independent or Growing.")
    config, when_errors = schedule_config(when, start_at=start_at, count=count)
    errors.extend(when_errors)
    if errors or not target:
        return None, errors
    full_target = dict(target)
    full_target["input_data"] = {**dict(target.get("input_data") or {}), "prompt": text}
    return (
        {
            "request_id": request_id,
            "title": name,
            "target": full_target,
            "trigger": {"source_id": "schedule", "source_version": 1, "config": config},
            "context": {"mode": context},
        },
        [],
    )


# ------------------------------------------------------------------- revise


def revise_changes(
    summary: Mapping[str, Any], *, title: str, every: Optional[str], context: str
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Only the fields that changed (``None`` when nothing did), or errors.
    A new interval keeps the rest of the schedule config (the server mints a
    new binding and re-anchors so no past tick fires)."""
    errors: List[str] = []
    changes: Dict[str, Any] = {}
    name = str(title or "").strip()
    if not name:
        errors.append("Title is required.")
    elif len(name) > 120:
        errors.append("Title is at most 120 characters.")
    elif name != summary.get("title"):
        changes["title"] = name
    trigger = summary.get("trigger") if isinstance(summary.get("trigger"), Mapping) else {}
    config = trigger.get("config") if isinstance(trigger.get("config"), Mapping) else {}
    before = config.get("every") if trigger.get("source_id") == "schedule" else None
    if every is not None and every != before:
        if parse_duration(every) is None:
            errors.append("Interval must be a whole number of minutes, hours or days (e.g. 30m, 8h, 7d).")
        else:
            changes["trigger"] = {
                "source_id": trigger.get("source_id"),
                "source_version": trigger.get("source_version"),
                "config": {**dict(config), "every": every},
            }
    if context != summary.get("context_mode"):
        if context not in {"independent", "growing"}:
            errors.append("Context must be Independent or Growing.")
        else:
            changes["context"] = {"mode": context}
    if errors:
        return None, errors
    return (changes or None), []


# ------------------------------------------------------------------- errors

API_ERROR_TEXT = {
    "unauthorized": "Sign in to the gateway to manage automations.",
    "forbidden": "You are not allowed to do this with automations.",
    "automation_not_found": "This automation does not exist (or is not yours).",
    "occurrence_not_found": "That occurrence does not exist.",
    "revision_conflict": "The automation changed since this view loaded. Reload it, then try again.",
    "automation_busy": "An occurrence is already running or queued. Wait for it to finish.",
    "invalid_state": "The automation's current state does not allow this.",
    "identity_conflict": "This request id was already used for a different request.",
    "invalid_request": "The gateway rejected the request as malformed.",
    "invalid_definition": "The automation definition is not valid.",
    "unsupported_feature": "The gateway does not support this yet.",
    "unknown_trigger_source": "The gateway does not know this trigger source.",
    "invalid_response": "The gateway gave an unexpected answer.",
    "unreachable": "The gateway could not be reached.",
}


def api_error_text(reason_code: str, message: str = "") -> str:
    """One visible sentence per error code, plus the server's own message."""
    head = API_ERROR_TEXT.get(str(reason_code), f"The gateway refused the request ({reason_code}).")
    detail = str(message or "").strip()
    return f"{head} {detail}" if detail and detail not in head else head
