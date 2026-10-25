"""What needs the person, folded from their own event stream (framework backlog 1047).

The gateway writes one ordered stream per person (``GET /api/gateway/me/events``,
CloudEvents 1.0 names, ``sequence`` = the cursor). This module folds it into the
two numbers the palette and the tray show:

- **needs you**: human-gated waits (``attention.raised`` with ``kind`` ``approval``
  or ``question`` and a ``wait_key``), one per ``(run_id, wait_key, step_id)``, not yet
  resolved — the gateway's ``attention.seen {kind, run_id, wait_key, step_id, outcome}``
  for the same wait (or one naming its ``record_key``), or a ``run.finished`` of that
  run (a wait cannot outlive its run), removes one;
- **new results**: automation attention items (``attention.raised`` with
  ``kind`` ``notify`` or ``failure``) whose ``seq`` is above the latest
  ``attention.seen`` ``seq`` of the same automation (the gateway's badge rule).

Pure: no Qt, no network. A wait read from history is only a hint — the caller
confirms it against the run itself (``GET /runs/{id}``) before acting on it.

It also remembers who already notified the person of a record
(``notification.sent {channel, record_key, device}``): the gateway's rule
(``events_stream.already_notified``) is that an app stays silent when another
client channel (the tray, Code, the watch) on the SAME device showed it less
than a minute ago — the tray is the default notifier.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

__all__ = [
    "DEVICE_CHANNELS",
    "NOTIFY_DEDUPE_S",
    "OWN_CHANNEL",
    "device_id",
    "AttentionModel",
    "PendingWait",
    "RaisedItem",
    "WAIT_KINDS",
    "attention_banner_text",
]

WAIT_KINDS = frozenset({"approval", "question"})
# The client channels that show a person a notification on a device (the
# gateway's CLIENT_CHANNELS). `console` and `email` never silence this app.
DEVICE_CHANNELS = frozenset({"tray", "assistant", "code", "watch"})
OWN_CHANNEL = "assistant"
NOTIFY_DEDUPE_S = 60.0


def device_id() -> str:
    """This machine's opaque id for the dedupe rule, exactly as the gateway tray computes it
    (`abstractgateway.tray.client.device_id`): sha256 of the lower-cased host name, 16 hex."""
    import hashlib
    import platform

    return hashlib.sha256(str(platform.node() or "unknown").strip().lower().encode("utf-8")).hexdigest()[:16]


def _epoch(value: Any) -> Optional[float]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class PendingWait:
    """A run parked on the person (an approval or a question)."""

    run_id: str
    wait_key: str
    kind: str
    session_id: str = ""
    step_id: str = ""
    record_key: str = ""

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.run_id, self.wait_key, self.step_id)

    @property
    def notice_key(self) -> str:
        """The notification ledger key (the automation waits' form, plus the step: the
        same node asking again is a new question)."""
        base = f"wait:{self.run_id}:{self.wait_key}"
        return f"{base}:{self.step_id}" if self.step_id else base


@dataclass(frozen=True)
class RaisedItem:
    """One ``attention.raised`` that is unseen at the moment it was folded."""

    kind: str
    record_key: str
    automation_id: str = ""
    seq: int = 0
    wait: Optional[PendingWait] = None

    @property
    def is_wait(self) -> bool:
        return self.wait is not None


def _data(event: Mapping[str, Any]) -> Mapping[str, Any]:
    data = event.get("data")
    return data if isinstance(data, Mapping) else {}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass
class AttentionModel:
    """Raised minus seen over automation attention and human-gated waits."""

    _raised: Dict[str, Set[int]] = field(default_factory=dict)
    _seen: Dict[str, int] = field(default_factory=dict)
    _waits: Dict[Tuple[str, str, str], PendingWait] = field(default_factory=dict)
    _resolved: Set[str] = field(default_factory=set)
    # (automation id, item seq) -> the record key of its attention item.
    _record_keys: Dict[Tuple[str, int], str] = field(default_factory=dict)
    # record key -> [(client channel, device id, when it was shown in epoch s or None)].
    _notified: Dict[str, List[Tuple[str, str, Optional[float]]]] = field(default_factory=dict)
    cursor: int = 0

    def reset(self) -> None:
        self._raised.clear()
        self._seen.clear()
        self._waits.clear()
        self._resolved.clear()
        self._record_keys.clear()
        self._notified.clear()
        self.cursor = 0

    # ------------------------------------------------------------ folding

    def apply(self, event: Mapping[str, Any]) -> Optional[RaisedItem]:
        """Fold one event (in stream order). Returns the item when the event
        raised something that is unseen right now, else None."""
        seq = _int(event.get("sequence"))
        if seq and seq > self.cursor:
            self.cursor = seq
        typ = str(event.get("type") or "")
        data = _data(event)
        if typ == "attention.raised":
            return self._raise(data)
        if typ == "notification.sent":
            self._note_notification(event, data)
        elif typ == "attention.seen":
            self._see(data)
        elif typ == "run.finished":
            run_id = str(data.get("run_id") or "")
            if run_id:
                for key in [k for k in self._waits if k[0] == run_id]:
                    self._waits.pop(key, None)
        return None

    def _raise(self, data: Mapping[str, Any]) -> Optional[RaisedItem]:
        kind = str(data.get("kind") or "")
        record_key = str(data.get("record_key") or "")
        wait_key = str(data.get("wait_key") or "")
        if kind in WAIT_KINDS or wait_key:
            run_id = str(data.get("run_id") or "")
            if not run_id or not wait_key:
                return None
            step_id = str(data.get("step_id") or "")
            if (record_key and record_key in self._resolved) or (step_id and f"step:{run_id}:{wait_key}:{step_id}" in self._resolved):
                return None  # seen before it was raised (replayed history)
            wait = PendingWait(
                run_id=run_id,
                wait_key=wait_key,
                kind=kind or "approval",
                session_id=str(data.get("session_id") or ""),
                step_id=step_id,
                record_key=record_key,
            )
            fresh = wait.key not in self._waits
            self._waits[wait.key] = wait
            return RaisedItem(kind=wait.kind, record_key=record_key, wait=wait) if fresh else None
        aid = str(data.get("automation_id") or "")
        seq = _int(data.get("seq"))
        if not aid or seq <= 0:
            return None
        if record_key:
            self._record_keys[(aid, seq)] = record_key
        known = seq in self._raised.get(aid, set())
        self._raised.setdefault(aid, set()).add(seq)
        if known or seq <= self._seen.get(aid, 0):
            return None
        return RaisedItem(kind=kind or "notify", record_key=record_key, automation_id=aid, seq=seq)

    def _see(self, data: Mapping[str, Any]) -> None:
        record_key = str(data.get("record_key") or "")
        run_id, wait_key = str(data.get("run_id") or ""), str(data.get("wait_key") or "")
        step_id = str(data.get("step_id") or "")
        if record_key or (run_id and wait_key):
            if record_key:
                self._resolved.add(record_key)
            elif step_id:
                self._resolved.add(f"step:{run_id}:{wait_key}:{step_id}")
            for key, wait in list(self._waits.items()):
                same_wait = run_id and wait_key and key[:2] == (run_id, wait_key) and (not step_id or not key[2] or key[2] == step_id)
                if (record_key and wait.record_key == record_key) or same_wait:
                    self._waits.pop(key, None)
            if not data.get("automation_id"):
                return
        aid = str(data.get("automation_id") or "")
        seq = _int(data.get("seq"))
        if not aid:
            return
        self._seen[aid] = max(self._seen.get(aid, 0), seq)
        self._raised[aid] = {s for s in self._raised.get(aid, set()) if s > self._seen[aid]}

    def _note_notification(self, event: Mapping[str, Any], data: Mapping[str, Any]) -> None:
        channel = str(data.get("channel") or "")
        if channel not in DEVICE_CHANNELS:
            return
        record_key = str(data.get("record_key") or "")
        notice = str(data.get("notice") or "")
        if not record_key and notice.startswith("attention:"):
            record_key = notice[len("attention:"):]
        if not record_key:
            return
        device = str(data.get("device") or "")
        self._notified.setdefault(record_key, []).append((channel, device, _epoch(event.get("time"))))

    def notified_elsewhere(
        self, record_key: str, *, device: str, now: Optional[float] = None, within_s: float = NOTIFY_DEDUPE_S
    ) -> str:
        """The client channel (not this app) that showed ``record_key`` on ``device``
        less than ``within_s`` seconds ago, else "" (the gateway's ``already_notified``)."""
        clock = time.time() if now is None else float(now)
        for channel, on, when in self._notified.get(str(record_key or ""), []):
            if channel == OWN_CHANNEL or not device or on != device or when is None:
                continue
            if 0 <= clock - when <= float(within_s):
                return channel
        return ""

    def record_key_for(self, notice_key: str) -> str:
        """The stream's record key behind a notification-ledger key
        (``item:<automation>:att1:<seq>`` or ``wait:<run>:<wait_key>[...]``), "" if unknown."""
        key = str(notice_key or "")
        if key.startswith("item:"):
            aid, _, cursor = key[len("item:"):].partition(":")
            seq = _int(cursor.rpartition(":")[2])
            return self._record_keys.get((aid, seq), "")
        if key.startswith("wait:"):
            run_id, _, rest = key[len("wait:"):].partition(":")
            for wait in self._waits.values():
                if wait.run_id == run_id and (rest == wait.wait_key or rest.startswith(wait.wait_key + ":")):
                    return wait.record_key
        return ""

    def drop_wait(self, run_id: str, wait_key: str = "") -> bool:
        """The live run says it no longer waits: forget it (True if one went)."""
        gone = [k for k in self._waits if k[0] == run_id and (not wait_key or k[1] == wait_key)]  # every step
        for key in gone:
            self._waits.pop(key, None)
        return bool(gone)

    # ------------------------------------------------------------ reading

    @property
    def new_results(self) -> int:
        return sum(len([s for s in seqs if s > self._seen.get(aid, 0)]) for aid, seqs in self._raised.items())

    @property
    def needs_you(self) -> int:
        return len(self._waits)

    @property
    def total(self) -> int:
        return self.new_results + self.needs_you

    def waits(self) -> List[PendingWait]:
        return list(self._waits.values())

    def waits_outside(self, session_id: str) -> List[PendingWait]:
        """Waits in conversations other than the one on screen."""
        sid = str(session_id or "")
        return [w for w in self._waits.values() if not sid or w.session_id != sid]


def attention_banner_text(*, needs_you: int, new_results: int) -> str:
    """The palette banner's words (empty = no banner)."""
    parts: List[str] = []
    if needs_you == 1:
        parts.append("A conversation is waiting for you")
    elif needs_you > 1:
        parts.append(f"{needs_you} conversations are waiting for you")
    if new_results == 1:
        parts.append("1 new result from your automations")
    elif new_results > 1:
        parts.append(f"{new_results} new results from your automations")
    return " · ".join(parts)
