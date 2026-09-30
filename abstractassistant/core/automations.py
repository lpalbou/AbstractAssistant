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
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "CONTROL_COMMANDS",
    "EMAIL_TEXT",
    "EMAIL_TRIGGER_SOURCE_ID",
    "EmailTriggerForm",
    "email_allowed_recipients",
    "email_trigger_config",
    "email_trigger_label",
    "email_usable",
    "is_email_trigger",
    "is_plain_address",
    "is_plain_domain",
    "notify_for",
    "parse_entry_list",
    "PENDING_TEXT",
    "command_confirmed",
    "current_run",
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
    "last_run_text",
    "next_run_text",
    "relative_span",
    "status_pill",
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
    if is_email_trigger(t):
        return email_trigger_label(t.get("config") or {})
    return f"{source}@{version}"


STATUS_LABELS = {
    "active": "Active",
    "paused": "Paused",
    "completed": "Completed",
    "failed": "Failed",
    "archived": "Archived",
}

# ------------------------------------------------------------ relative time


def relative_span(seconds: float) -> str:
    """A duration for a row: "<1 min", "3 min", "1 h 06 min", "2 d 3 h"."""
    total = max(0, int(seconds))
    if total < 60:
        return "<1 min"
    minutes = total // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h" if minutes == 0 else f"{hours} h {minutes:02d} min"
    days, hours = divmod(hours, 24)
    return f"{days} d" if hours == 0 else f"{days} d {hours} h"


def last_run_text(summary: Mapping[str, Any], *, now: Optional[datetime] = None) -> str:
    """ "last 3 min ago" from the last occurrence's finish (else fire) time; "last —" when none."""
    now = now or datetime.now(timezone.utc)
    last = summary.get("last_occurrence") if isinstance(summary.get("last_occurrence"), Mapping) else None
    when = _parse_ts((last or {}).get("finished_at") or (last or {}).get("fired_at")) if last else None
    if when is None:
        return "last —"
    return f"last {relative_span((now - when).total_seconds())} ago"


def current_run(summary: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """The occurrence in progress, from the gateway's ``current_occurrence``
    (``{index, run_id, attempt, status: admitted|running|backoff}``, null when
    none). Absent = no running state is shown: never inferred from
    ``last_occurrence``."""
    current = summary.get("current_occurrence")
    if isinstance(current, Mapping) and current.get("status") in {"admitted", "running", "backoff"}:
        return current
    return None


def next_run_text(summary: Mapping[str, Any], *, now: Optional[datetime] = None) -> str:
    """ "next in 2 min" from the gateway's next fire time; "next —" when paused,
    ended or not scheduled; "next: now" when due."""
    now = now or datetime.now(timezone.utc)
    if summary.get("status") != "active":
        return "next —"
    when = _parse_ts(summary.get("next_fire_at"))  # the gateway's time only; no client arithmetic
    if when is None:
        return "next —"
    delta = (when - now).total_seconds()
    return "next: now" if delta < 60 else f"next in {relative_span(delta)}"


def status_pill(summary: Mapping[str, Any]) -> Tuple[str, str]:
    """ ``(text, tone)`` of a row's status pill. Tones: active (green), paused
    (amber), running (blue), waiting (highlighted), failed (red), ended (grey)."""
    status = str(summary.get("status") or "")
    attention = summary.get("attention") if isinstance(summary.get("attention"), Mapping) else {}
    if status in {"active", "paused"} and int(attention.get("pending_waits") or 0):
        return "waiting for you", "waiting"
    if status in {"active", "paused"} and current_run(summary) is not None:
        return "running", "running"
    if status == "active":
        return "active", "active"
    if status == "paused":
        return "paused", "paused"
    if status == "failed":
        return "failed", "failed"
    return (status or "unknown"), "ended"


# ----------------------------------------------------------------- controls

CONTROL_COMMANDS = {
    "pause": "automation.pause",
    "resume": "automation.resume",
    "run_now": "automation.run_now",
    "stop_current": "automation.stop_current",
    "archive": "automation.archive",
}
_IN_PROGRESS = {"running", "waiting", "backoff"}


def occurrence_in_progress(summary: Mapping[str, Any]) -> bool:
    """Whether a run is in progress: the gateway's ``current_occurrence`` (see
    ``current_run``), the one source in the whole app — never inferred from
    ``last_occurrence`` or from occurrence rows."""
    return current_run(summary) is not None


def automation_controls(summary: Mapping[str, Any], *, busy: bool = False) -> Dict[str, Tuple[bool, str]]:
    """``control -> (enabled, reason)``. The server decides what the principal
    may do (``capabilities``); the status decides which of them apply now.
    Run now stays enabled while paused (it does not resume)."""
    caps = set(summary.get("capabilities") or ())
    status = summary.get("status")
    running = occurrence_in_progress(summary)
    live = status in {"active", "paused"}

    def gate(control: str, ok: bool, reason: str) -> Tuple[bool, str]:
        if busy:
            return False, "Working…"
        if summary.get("legacy"):
            return False, "Legacy schedule: managed with its existing controls."
        if status == "archived":
            return False, "Archived: history is kept, nothing runs."
        if control not in caps:
            return False, "Not permitted for this automation."
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


# ------------------------------------------------------ control hints

def _controls_spec_path() -> Path:
    """The vendored ``automation_controls.json`` (in-repo, installed, or frozen)."""
    import sys

    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        candidate = Path(frozen_base) / "abstractassistant" / "assets" / "automation_controls.json"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent / "assets" / "automation_controls.json"


# The controls' names, hints and run-now glyph: a BYTE-IDENTICAL copy of
# AbstractUIC's canonical `ui-kit/src/automations/automation_controls.json`
# (the web panel's `CONTROL_HINTS` / `controlHint`, the Observer's rows and
# AbstractCode's terminal read the same file). The AbstractFramework root
# `scripts/check_identity_sync.py` fails when this copy drifts. A missing or
# unreadable copy fails the import: there is no fallback text.
AUTOMATION_CONTROLS: Dict[str, Any] = json.loads(_controls_spec_path().read_text(encoding="utf-8"))
CONTROL_HINTS: Dict[str, str] = dict(AUTOMATION_CONTROLS["hints"])
RUN_NOW_GLYPH: Dict[str, Any] = dict(AUTOMATION_CONTROLS["icons"]["run_now"])


def control_hint(control: str, summary: Optional[Mapping[str, Any]] = None) -> str:
    """A control's tooltip, as the kit's ``controlHint``: the canonical hint,
    plus, for Run now, the next scheduled time when the gateway reports one
    and the Growing line when the automation replays its history."""
    lines = [CONTROL_HINTS[control]]
    if control == "run_now" and summary:
        nxt = summary.get("next_fire_at")
        if nxt:
            lines.append(AUTOMATION_CONTROLS["run_now_next_run_line"].replace("{time}", format_utc(nxt)))
        if summary.get("context_mode") == "growing":
            lines.append(AUTOMATION_CONTROLS["run_now_growing_line"])
    return "\n".join(lines)


# ------------------------------------------ email.received@1 (backlog 0992)
#
# The Qt mirror of the kit's email block in `panel_core.ts` (ui-kit 0.2.0):
# same defaults, same validation, same words (the vendored JSON's `email`
# section). Typed filters only — membership and one literal substring.

EMAIL_TEXT: Dict[str, str] = dict(AUTOMATION_CONTROLS["email"])
EMAIL_TRIGGER_SOURCE_ID = "email.received"
EMAIL_TRIGGER_SOURCE_VERSION = 1
EMAIL_DEFAULT_EVERY_MODEL = "1h"
EMAIL_DEFAULT_EVERY_NO_MODEL = "60s"
EMAIL_MIN_EVERY_SECONDS = 60
EMAIL_DEFAULT_MAX_BATCH = 100
EMAIL_MAX_BATCH = 1000
EMAIL_MAX_FILTER_ENTRIES = 200
EMAIL_MAX_SUBJECT_CONTAINS = 200
EMAIL_MAX_ALLOWED_RECIPIENTS = 50
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def is_email_trigger(trigger: Any) -> bool:
    t = trigger if isinstance(trigger, Mapping) else {}
    return t.get("source_id") == EMAIL_TRIGGER_SOURCE_ID and t.get("source_version") == EMAIL_TRIGGER_SOURCE_VERSION


def email_usable(status: Any) -> bool:
    """True only when ``GET /me/email`` says ``effective_enabled`` (connected,
    the user's switch on, allowed by an administrator). Unknown = not usable."""
    return isinstance(status, Mapping) and status.get("effective_enabled") is True


def parse_entry_list(text: Any) -> List[str]:
    """Split on commas, semicolons and white space; trim, lower-case, dedupe (order kept)."""
    out: List[str] = []
    for raw in re.split(r"[\s,;]+", str(text or "")):
        entry = raw.strip().lower()
        if entry and entry not in out:
            out.append(entry)
    return out


_ADDRESS_FORBIDDEN = re.compile(r'[\s<>,;:"()\[\]]')
_DOMAIN_FORBIDDEN = re.compile(r'[\s<>,;:"()\[\]/*]')


def is_plain_address(value: str) -> bool:
    """``name@example.test`` — the runtime's plain-address rule."""
    a = str(value or "").strip().lower()
    local, at, domain = a.partition("@")
    return bool(at and local and domain) and "@" not in domain and not _ADDRESS_FORBIDDEN.search(a)


def is_plain_domain(value: str) -> bool:
    """``example.test`` — no "@", at least one dot, no pattern characters."""
    d = str(value or "").strip().lower()
    return bool(d) and "@" not in d and "." in d and not d.startswith(".") and not d.endswith(".") and not _DOMAIN_FORBIDDEN.search(d)


def email_default_every(uses_model: bool) -> str:
    return EMAIL_DEFAULT_EVERY_MODEL if uses_model else EMAIL_DEFAULT_EVERY_NO_MODEL


def _duration_seconds(every: str) -> Optional[int]:
    parsed = parse_duration(every)
    return None if parsed is None else parsed[0] * _UNIT_SECONDS[parsed[1]]


@dataclass(frozen=True)
class EmailTriggerForm:
    """The "When an email arrives" fields. List fields are the raw text typed;
    ``every_amount`` 0 / None = the default for ``uses_model``; ``max_batch``
    None = 100; ``has_attachment`` ``any`` | ``yes`` | ``no``."""

    uses_model: bool = True
    every_amount: Optional[int] = None
    every_unit: str = "h"
    max_batch: Optional[int] = None
    from_in: str = ""
    from_domain_in: str = ""
    to_in: str = ""
    subject_contains: str = ""
    has_attachment: str = "any"


def _email_list(text: str, label: str, ok: Callable[[str], bool], kind: str, errors: List[str]) -> Optional[List[str]]:
    items = parse_entry_list(text)
    if not items:
        return None
    bad = [v for v in items if not ok(v)]
    if bad:
        errors.append(f"{label}: {', '.join(bad)} {'is not' if len(bad) == 1 else 'are not'} {kind}.")
    if len(items) > EMAIL_MAX_FILTER_ENTRIES:
        errors.append(f"{label}: at most {EMAIL_MAX_FILTER_ENTRIES} entries.")
    return items


def email_trigger_config(form: EmailTriggerForm) -> Tuple[Dict[str, Any], List[str]]:
    """``email.received@1`` config (explicit ``uses_model``, ``every``,
    ``max_batch``; ``filter`` only when set) + the reasons it is invalid."""
    errors: List[str] = []
    config: Dict[str, Any] = {"uses_model": bool(form.uses_model)}
    if form.every_amount is None:
        config["every"] = email_default_every(form.uses_model)
    elif not isinstance(form.every_amount, int) or form.every_amount < 1 or form.every_unit not in {"m", "h", "d"}:
        errors.append("The check interval must be a whole number of at least 1.")
    else:
        config["every"] = f"{form.every_amount}{form.every_unit}"
    if "every" in config and (_duration_seconds(config["every"]) or 0) < EMAIL_MIN_EVERY_SECONDS:
        errors.append("The check interval is at least 60 seconds.")
    if form.max_batch is None:
        config["max_batch"] = EMAIL_DEFAULT_MAX_BATCH
    elif isinstance(form.max_batch, bool) or not isinstance(form.max_batch, int) or not 1 <= form.max_batch <= EMAIL_MAX_BATCH:
        errors.append(f"At most this many emails per run: a whole number from 1 to {EMAIL_MAX_BATCH}.")
    else:
        config["max_batch"] = form.max_batch
    flt: Dict[str, Any] = {}
    from_in = _email_list(form.from_in, EMAIL_TEXT["from_in"], is_plain_address, "an email address", errors)
    if from_in:
        flt["from_in"] = from_in
    domains = _email_list(form.from_domain_in, EMAIL_TEXT["from_domain_in"], is_plain_domain, "a domain like example.com", errors)
    if domains:
        flt["from_domain_in"] = domains
    to_in = _email_list(form.to_in, EMAIL_TEXT["to_in"], is_plain_address, "an email address", errors)
    if to_in:
        flt["to_in"] = to_in
    subject = str(form.subject_contains or "").strip()
    if subject:
        if len(subject) > EMAIL_MAX_SUBJECT_CONTAINS or "\n" in subject or "\r" in subject:
            errors.append(f"{EMAIL_TEXT['subject_contains']}: one line of at most {EMAIL_MAX_SUBJECT_CONTAINS} characters.")
        else:
            flt["subject_contains"] = subject
    if form.has_attachment == "yes":
        flt["has_attachment"] = True
    elif form.has_attachment == "no":
        flt["has_attachment"] = False
    if flt:
        config["filter"] = flt
    return config, errors


def email_trigger_label(config: Mapping[str, Any]) -> str:
    """"when an email arrives · from … · checked every hour · up to 100 per run"."""
    cfg = config if isinstance(config, Mapping) else {}
    f = cfg.get("filter") if isinstance(cfg.get("filter"), Mapping) else {}
    parts = ["when an email arrives"]
    sources = list(f.get("from_in") or []) + list(f.get("from_domain_in") or [])
    if sources:
        parts.append("from " + ", ".join(sources))
    if f.get("to_in"):
        parts.append("to " + ", ".join(f["to_in"]))
    if isinstance(f.get("subject_contains"), str) and f["subject_contains"]:
        parts.append(f"subject contains “{f['subject_contains']}”")
    if f.get("has_attachment") is True:
        parts.append("with attachments")
    if f.get("has_attachment") is False:
        parts.append("without attachments")
    every = cfg.get("every") if isinstance(cfg.get("every"), str) else email_default_every(cfg.get("uses_model") is not False)
    parts.append(f"checked {interval_label(every)}")
    batch = cfg.get("max_batch") if isinstance(cfg.get("max_batch"), int) else EMAIL_DEFAULT_MAX_BATCH
    parts.append(f"up to {batch} per run")
    return " · ".join(parts)


def email_allowed_recipients(mode: str, addresses: str = "") -> Tuple[List[str], List[str]]:
    """``policy.email_allowed_recipients``: ``["self"]`` for "only me",
    ``["self", ...addresses]`` for "me and these addresses" (at least one)."""
    if mode != "list":
        return ["self"], []
    errors: List[str] = []
    items = [a for a in parse_entry_list(addresses) if a != "self"]
    if not items:
        errors.append("Name at least one address the automation may email, or choose Only me.")
    bad = [a for a in items if not is_plain_address(a)]
    if bad:
        errors.append(f"{EMAIL_TEXT['recipients_list']}: {', '.join(bad)} {'is not an email address' if len(bad) == 1 else 'are not email addresses'}.")
    if len(items) + 1 > EMAIL_MAX_ALLOWED_RECIPIENTS:
        errors.append(f"At most {EMAIL_MAX_ALLOWED_RECIPIENTS - 1} addresses.")
    return ["self", *items], errors


def notify_for(email_me: bool) -> Dict[str, Any]:
    """``notify`` for "Email me the result"."""
    return {"channels": ["console", "email"] if email_me else ["console"]}


def notify_emails(notify: Any) -> bool:
    return isinstance(notify, Mapping) and "email" in (notify.get("channels") or [])


# ------------------------------------------------------- pending commands

# What a control's button says while its command waits for the gateway.
PENDING_TEXT = {
    "pause": "Pausing…",
    "resume": "Resuming…",
    "run_now": "Starting a run…",
    "stop_current": "Stopping…",
    "archive": "Archiving…",
}


def command_confirmed(control: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """Whether ``after`` (a fresh summary) shows the effect of ``control``
    applied to ``before`` — read from the gateway's state, never assumed."""
    status = after.get("status")
    if control == "pause":
        return status == "paused"
    if control == "resume":
        return status == "active"
    if control == "archive":
        return status == "archived"
    if control == "run_now":
        return int(after.get("occurrence_count") or 0) > int(before.get("occurrence_count") or 0) or occurrence_in_progress(after)
    if control == "stop_current":
        return not occurrence_in_progress(after)
    raise ValueError(f"unknown control {control!r}")


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
            asks_approval = wait.get("kind") == "tool_approval"
            out.append(
                AttentionNotice(
                    key=key,
                    automation_id=aid,
                    title=f"{title} needs your approval" if asks_approval else f"{title} is waiting for you",
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
    tool_approval: str = "auto",
    trigger: str = "schedule",
    email: Optional[EmailTriggerForm] = None,
    notify_email: bool = False,
    email_recipients: Optional[Tuple[str, str]] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """The ``POST /api/gateway/automations`` body, or the reasons it cannot be built.

    ``tool_approval`` (decision D1): ``"auto"`` — creating the automation is
    the consent, its runs use their tools without asking — or ``"ask"``.

    Email (framework backlog 0992): ``trigger="email"`` builds
    ``email.received@1`` from ``email`` (``when`` is then ignored);
    ``notify_email`` sends ``notify: {channels: ["console", "email"]}`` (off
    sends nothing: the server default); ``email_recipients=("list", text)``
    sends ``policy.email_allowed_recipients`` (``("self", "")`` sends nothing)."""
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
    if tool_approval not in {"auto", "ask"}:
        errors.append("Tool approval must be automatic or ask each time.")
    is_email = trigger == "email"
    if is_email:
        config, when_errors = email_trigger_config(email or EmailTriggerForm())
    else:
        config, when_errors = schedule_config(when, start_at=start_at, count=count)
    errors.extend(when_errors)
    recipients: Optional[List[str]] = None
    if email_recipients is not None and email_recipients[0] == "list":
        recipients, rcpt_errors = email_allowed_recipients("list", email_recipients[1])
        errors.extend(rcpt_errors)
    if errors or not target:
        return None, errors
    full_target = dict(target)
    full_target["input_data"] = {**dict(target.get("input_data") or {}), "prompt": text}
    policy: Dict[str, Any] = {"tool_approval": tool_approval}
    if recipients is not None:
        policy["email_allowed_recipients"] = recipients
    body: Dict[str, Any] = {
        "request_id": request_id,
        "title": name,
        "target": full_target,
        "trigger": (
            {"source_id": EMAIL_TRIGGER_SOURCE_ID, "source_version": EMAIL_TRIGGER_SOURCE_VERSION, "config": config}
            if is_email
            else {"source_id": "schedule", "source_version": 1, "config": config}
        ),
        "context": {"mode": context},
        "policy": policy,
    }
    if notify_email:
        body["notify"] = notify_for(True)
    return body, []


# ------------------------------------------------------------------- revise


def revise_changes(
    summary: Mapping[str, Any],
    *,
    title: str,
    every: Optional[str],
    context: str,
    definition: Optional[Mapping[str, Any]] = None,
    notify_email: Optional[bool] = None,
    email_recipients: Optional[Tuple[str, str]] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Only the fields that changed (``None`` when nothing did), or errors.
    A new interval keeps the rest of the trigger config (the server mints a
    new binding and re-anchors so no past tick fires); for ``email.received@1``
    the old ``start_at`` is dropped so the revised trigger never re-reads mail,
    and the interval is at least 60 s. With the committed ``definition``,
    ``notify_email`` sends ``notify`` and ``email_recipients`` sends only
    ``policy.email_allowed_recipients`` (the server merges policy)."""
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
    email_trigger = is_email_trigger(trigger)
    before = config.get("every") if trigger.get("source_id") == "schedule" or email_trigger else None
    if every is not None and every != before:
        if parse_duration(every) is None:
            errors.append("Interval must be a whole number of minutes, hours or days (e.g. 30m, 8h, 7d).")
        elif email_trigger and (_duration_seconds(every) or 0) < EMAIL_MIN_EVERY_SECONDS:
            errors.append("The check interval is at least 60 seconds.")
        else:
            new_config = {**dict(config), "every": every}
            if email_trigger:
                new_config.pop("start_at", None)
            changes["trigger"] = {
                "source_id": trigger.get("source_id"),
                "source_version": trigger.get("source_version"),
                "config": new_config,
            }
    if context != summary.get("context_mode"):
        if context not in {"independent", "growing"}:
            errors.append("Context must be Independent or Growing.")
        else:
            changes["context"] = {"mode": context}
    if definition is not None:
        if notify_email is not None and bool(notify_email) != notify_emails(definition.get("notify")):
            changes["notify"] = notify_for(bool(notify_email))
        if email_recipients is not None:
            policy = definition.get("policy") if isinstance(definition.get("policy"), Mapping) else {}
            current = list(policy.get("email_allowed_recipients") or ["self"])
            wanted, rcpt_errors = email_allowed_recipients(*email_recipients)
            errors.extend(rcpt_errors)
            if not rcpt_errors and wanted != current:
                changes["policy"] = {"email_allowed_recipients": wanted}
    if errors:
        return None, errors
    return (changes or None), []


# --------------------------------------------------------------- discussion


def discussion_banner(result: Mapping[str, Any], *, occurrence_index: int) -> Tuple[str, str]:
    """``(text, tone)`` of the notice after Discuss. The discussion carries the
    automation's history through occurrence N, mounts the automation's files
    read-only at ``mounted_workspace`` and works in its own writable
    ``workspace_root`` (both from the discuss response). A response without
    ``mounted_workspace`` is said, never papered over."""
    mounted = str(result.get("mounted_workspace") or "").strip()
    own = str(result.get("workspace_root") or "").strip()
    if not mounted or not own:
        return (
            f"Discussion opened from occurrence {occurrence_index}, but the gateway did not report its workspaces "
            "(mounted_workspace / workspace_root missing).",
            "warn",
        )
    return (
        f"Discussion opened from occurrence {occurrence_index}: the automation's history up to that point is in "
        f"context; its files are mounted read-only at {mounted}; this session has its own writable workspace.",
        "info",
    )


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
