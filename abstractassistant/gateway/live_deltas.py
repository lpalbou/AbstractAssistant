"""Live reply deltas from the gateway run stream (contract S).

The gateway multiplexes two VOLATILE events onto ``/runs/{id}/ledger/stream``
next to the durable ``step`` rows. They carry no ``id:`` line, so they never
move the ledger cursor, and they are never written to the ledger:

``llm.delta``      ``{"run_id","root_run_id","parent_run_id","node_id","call_id","seq","text","channel","snapshot","truncated"?}``
``llm.delta_end``  ``{"run_id","root_run_id","parent_run_id","node_id","call_id","seq","reason","detail"?}``

``reason`` is ``completed`` | ``failed`` | ``cancelled`` | ``unavailable``; the
last says the call ran WITHOUT streaming and ``detail`` says why
(``structured_output`` | ``remote_core`` | ``provider_cannot_stream`` |
``sink_error`` | ``usage_unavailable``). The hub is keyed by the ROOT run, so
a subscriber to the root also receives its child runs' deltas (``run_id`` is
the emitting run; ``parent_run_id`` is null for a root).

``call_id`` is the ``llm_call`` step id. A ``snapshot: true`` delta (sent on
subscribe/reconnect) carries the channel's text so far and REPLACES it; later
deltas append. ``truncated: true`` means the gateway dropped the oldest part of
the call's live text (its per-call cap) — the durable ``llm_call`` record and
the final assistant message still carry everything.

Parsing is tolerant: unknown fields (the runtime's ``kind``, ...) are ignored.
One ``llm.delta_end`` arrives per llm_call ATTEMPT (a retry gets a fresh
``call_id``), and a call that ran without streaming still ends with one, so a
``delta_end`` for a call that never streamed is normal and changes nothing.

The client never parses ``<think>``: the server splits reasoning into its
own channel. On every (re)connect the client drops all live text before the
snapshots arrive (contract S-2.3), and it ignores deltas for a call whose
durable record it already holds (S-2.2).

This module is Qt-free: the palette, the worker and the CLI share it.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Dict, Optional

DELTA_EVENT = "llm.delta"
DELTA_END_EVENT = "llm.delta_end"
LIVE_EVENTS = frozenset({DELTA_EVENT, DELTA_END_EVENT})

CHANNELS = ("content", "reasoning")
END_REASONS = ("completed", "failed", "cancelled", "unavailable")
UNAVAILABLE_DETAILS = {
    "structured_output": "this step returns structured output",
    "remote_core": "the gateway uses a remote model server",
    "provider_cannot_stream": "the model provider cannot stream",
    "sink_error": "the gateway's live channel failed",
    "usage_unavailable": "the provider cannot report token usage while streaming",
}

# Worker → UI event types.
ASSISTANT_DELTA = "assistant_delta"
ASSISTANT_DELTA_END = "assistant_delta_end"
# Emitted on every (re)connect of the run stream: drop all live text; the
# gateway re-sends a snapshot of each reply still being written.
ASSISTANT_DELTA_RESET = "assistant_delta_reset"


def _lineage(data: Dict[str, Any], rid: str) -> Dict[str, Any]:
    root = str(data.get("root_run_id") or "").strip()
    parent = str(data.get("parent_run_id") or "").strip()
    return {
        "root_run_id": root,
        "parent_run_id": parent,
        # A child run's call (an agent subworkflow): shown with a label.
        "subagent": bool(parent) or bool(root and rid and root != rid),
    }


def _seq(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def to_ui_event(event_name: str, data: Any, *, run_id: str = "") -> Optional[Dict[str, Any]]:
    """Normalize one SSE live event into the worker's UI event dict.

    Returns None (with a warning) for a malformed payload: a live delta is
    only a preview, so a bad one is dropped loudly rather than ending the run
    follow — the durable record still delivers the reply.
    """
    if not isinstance(data, dict):
        warnings.warn(f"#FALLBACK: {event_name} payload is not an object; dropping")
        return None
    rid = str(data.get("run_id") or run_id or "").strip()
    call_id = str(data.get("call_id") or "").strip()
    seq = _seq(data.get("seq"))
    if not call_id or seq is None:
        warnings.warn(f"#FALLBACK: {event_name} without call_id/seq; dropping")
        return None
    if event_name == DELTA_EVENT:
        channel = str(data.get("channel") or "").strip()
        if channel not in CHANNELS:
            warnings.warn(f"#FALLBACK: llm.delta with unknown channel {channel!r}; dropping")
            return None
        text = data.get("text")
        if not isinstance(text, str):
            warnings.warn("#FALLBACK: llm.delta without text; dropping")
            return None
        return {
            "type": ASSISTANT_DELTA,
            "run_id": rid,
            "node_id": str(data.get("node_id") or ""),
            "call_id": call_id,
            "seq": seq,
            "text": text,
            "channel": channel,
            "snapshot": data.get("snapshot") is True,
            "truncated": data.get("truncated") is True,
            **_lineage(data, rid),
        }
    if event_name == DELTA_END_EVENT:
        reason = str(data.get("reason") or "").strip()
        if reason not in END_REASONS:
            warnings.warn(f"#FALLBACK: llm.delta_end with unknown reason {reason!r}; treating as failed")
            reason = "failed"
        return {
            "type": ASSISTANT_DELTA_END,
            "run_id": rid,
            "node_id": str(data.get("node_id") or ""),
            "call_id": call_id,
            "seq": seq,
            "reason": reason,
            "detail": str(data.get("detail") or "").strip(),
            **_lineage(data, rid),
        }
    raise ValueError(f"not a live delta event: {event_name!r}")


@dataclass
class LiveReply:
    """The growing text of one streamed LLM call."""

    run_id: str
    call_id: str
    node_id: str = ""
    subagent: bool = False
    content: str = ""
    reasoning: str = ""
    truncated: bool = False
    ended: str = ""  # "" while live, else the delta_end reason

    def __post_init__(self) -> None:
        self._last_seq: Dict[str, int] = {}

    def apply_delta(self, ev: Dict[str, Any]) -> bool:
        """Fold one ``assistant_delta``; returns True when the text changed.

        A snapshot replaces the channel's text; a live delta appends unless
        its ``seq`` was already applied on that channel (a reconnect replays
        the snapshot, so duplicates are expected, not errors).
        """
        channel = str(ev.get("channel") or "")
        if channel not in CHANNELS:
            raise ValueError(f"unknown delta channel {channel!r}")
        seq = int(ev.get("seq") or 0)
        text = str(ev.get("text") or "")
        before = (self.content, self.reasoning, self.truncated)
        if ev.get("truncated") is True:
            self.truncated = True
        if ev.get("snapshot") is True:
            setattr(self, channel, text)
            self._last_seq[channel] = seq
        else:
            last = self._last_seq.get(channel)
            if last is not None and seq <= last:
                return False
            setattr(self, channel, getattr(self, channel) + text)
            self._last_seq[channel] = seq
        return (self.content, self.reasoning, self.truncated) != before


TRUNCATED_NOTE = (
    "Showing the latest part only: the gateway keeps a bounded live preview per reply and dropped "
    "the oldest text. The complete reply replaces this when it finishes."
)


def subagent_caption(node_id: str) -> str:
    """Label of a live card streamed by a child run."""
    node = str(node_id or "").strip()
    return f"sub-agent · {node}" if node else "sub-agent"


def end_reason_text(reason: str, detail: str = "") -> str:
    """The user-facing line when a live reply is discarded or unavailable."""
    if reason == "unavailable":
        why = UNAVAILABLE_DETAILS.get(str(detail or "").strip())
        if why:
            return f"Live reply unavailable for this step: {why}. The answer appears when it is finished."
        suffix = f" ({detail})" if detail else ""
        return f"Live reply unavailable for this step{suffix}. The answer appears when it is finished."
    if reason == "cancelled":
        return "Live reply discarded: the run was stopped."
    if reason == "failed":
        return "Live reply discarded: the model call failed."
    return ""
