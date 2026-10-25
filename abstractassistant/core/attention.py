"""What needs the person, folded from their own event stream (framework backlog 1047).

The gateway writes one ordered stream per person (``GET /api/gateway/me/events``,
CloudEvents 1.0 names, ``sequence`` = the cursor). This module folds it into the
two numbers the palette and the tray show:

- **needs you**: human-gated waits (``attention.raised`` with ``kind`` ``approval``
  or ``question`` and a ``wait_key``) not yet resolved — an ``attention.seen`` naming
  the same ``record_key`` (or the same run + wait key), or a ``run.finished`` of
  that run (a wait cannot outlive its run), removes one;
- **new results**: automation attention items (``attention.raised`` with
  ``kind`` ``notify`` or ``failure``) whose ``seq`` is above the latest
  ``attention.seen`` ``seq`` of the same automation (the gateway's badge rule).

Pure: no Qt, no network. A wait read from history is only a hint — the caller
confirms it against the run itself (``GET /runs/{id}``) before acting on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

__all__ = [
    "AttentionModel",
    "PendingWait",
    "RaisedItem",
    "WAIT_KINDS",
    "attention_banner_text",
]

WAIT_KINDS = frozenset({"approval", "question"})


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
    def key(self) -> Tuple[str, str]:
        return (self.run_id, self.wait_key)

    @property
    def notice_key(self) -> str:
        """The notification ledger key (same form as the automation waits)."""
        return f"wait:{self.run_id}:{self.wait_key}"


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
    _waits: Dict[Tuple[str, str], PendingWait] = field(default_factory=dict)
    _resolved: Set[str] = field(default_factory=set)
    cursor: int = 0

    def reset(self) -> None:
        self._raised.clear()
        self._seen.clear()
        self._waits.clear()
        self._resolved.clear()
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
        if typ == "attention.seen":
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
            if record_key and record_key in self._resolved:
                return None  # seen before it was raised (replayed history)
            wait = PendingWait(
                run_id=run_id,
                wait_key=wait_key,
                kind=kind or "approval",
                session_id=str(data.get("session_id") or ""),
                step_id=str(data.get("step_id") or ""),
                record_key=record_key,
            )
            fresh = wait.key not in self._waits
            self._waits[wait.key] = wait
            return RaisedItem(kind=wait.kind, record_key=record_key, wait=wait) if fresh else None
        aid = str(data.get("automation_id") or "")
        seq = _int(data.get("seq"))
        if not aid or seq <= 0:
            return None
        known = seq in self._raised.get(aid, set())
        self._raised.setdefault(aid, set()).add(seq)
        if known or seq <= self._seen.get(aid, 0):
            return None
        return RaisedItem(kind=kind or "notify", record_key=record_key, automation_id=aid, seq=seq)

    def _see(self, data: Mapping[str, Any]) -> None:
        record_key = str(data.get("record_key") or "")
        run_id, wait_key = str(data.get("run_id") or ""), str(data.get("wait_key") or "")
        if record_key or (run_id and wait_key):
            if record_key:
                self._resolved.add(record_key)
            for key, wait in list(self._waits.items()):
                if (record_key and wait.record_key == record_key) or (run_id and wait_key and key == (run_id, wait_key)):
                    self._waits.pop(key, None)
            if not data.get("automation_id"):
                return
        aid = str(data.get("automation_id") or "")
        seq = _int(data.get("seq"))
        if not aid:
            return
        self._seen[aid] = max(self._seen.get(aid, 0), seq)
        self._raised[aid] = {s for s in self._raised.get(aid, set()) if s > self._seen[aid]}

    def drop_wait(self, run_id: str, wait_key: str = "") -> bool:
        """The live run says it no longer waits: forget it (True if one went)."""
        gone = [k for k in self._waits if k[0] == run_id and (not wait_key or k[1] == wait_key)]
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
