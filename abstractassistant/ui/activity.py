"""Live run activity: an event-fed step model and the transcript-tail card.

Two halves, one module:

- Model half (``ActivityStep`` / ``RunActivityModel``): pure Python, no Qt.
  The palette feeds it the worker's event payloads (``apply_event``), its own
  run-control notes (``note_local``) and wait outcomes (``resolve_wait``); it
  answers with steps, header copy, a summary and log entries. Every honesty
  rule lives here so it is unit-testable: no elapsed time without a timestamp
  source, no prompt echo, no "ok" a result record did not establish.

- Widget half (``RunActivityCard`` / ``ActivityStepList``): PyQt5 widgets that
  render a model. ``RunActivityCard`` keeps the ``ThinkingIndicatorCard``
  contract the palette tests poke (``_status``, ``set_status``,
  ``sync_to_viewport_width``, ``activated``) and adds the step rows, an
  elapsed counter and pause / log / expand controls.

``ACTIVITY_QSS`` carries every rule the widgets need; it is built from
``abstractassistant.theme`` tokens only (no hex literals, no gradients) and is
appended to the palette stylesheet by the application.
"""

from __future__ import annotations

import html as _html
import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import QPointF, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFontMetrics, QPainter
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from abstractassistant.core.speech_text import speech_plain_text
from abstractassistant.core.tool_display import (
    compact_tool_call_label,
    compact_tool_call_label_html,
)
from abstractassistant.gateway.run_stats import parse_iso_ms
from abstractassistant.icons import symbol_icon
from abstractassistant.theme import METRICS, THEME

__all__ = [
    "ActivityStep",
    "RunActivityModel",
    "RunActivityCard",
    "ActivityStepList",
    "ThinkingDotsWidget",
    "ACTIVITY_QSS",
    "format_duration",
]


# --------------------------------------------------------------------------- #
# Text helpers (model half)
# --------------------------------------------------------------------------- #

_DETAIL_MAX_CHARS = 90
_PROMPT_MAX_CHARS = 80
_TITLE_MAX_CHARS = 160
_RESULT_PREVIEW_MAX_CHARS = 800

STEP_KINDS = (
    "cycle",
    "tool",
    "wait_approval",
    "wait_input",
    "steer",
    "pause",
    "resume",
    "stop",
    "offline",
    "error",
    "replay",
)
STEP_STATUSES = ("running", "ok", "failed", "denied", "waiting", "info")
STEP_TONES = ("thinking", "tool", "attention", "ok", "danger", "info", "paused", "offline")

_LOCAL_KINDS = ("steer", "pause", "resume", "stop")
_WAIT_KINDS = ("wait_approval", "wait_input")
_OPEN_STATUSES = ("running", "waiting")

# Per-kind defaults for locally-noted steps (tone, status).
_LOCAL_DEFAULTS: Dict[str, tuple] = {
    "steer": ("info", "info"),
    "pause": ("paused", "running"),
    "resume": ("thinking", "info"),
    "stop": ("paused", "running"),
}


def _one_line(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clip(text: str, limit: int) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    #[WARNING:TRUNCATION] bounded for a one-line UI surface; the payload keeps the full text
    return value[: max(1, limit - 1)].rstrip() + "…"


def _first_line(text: Any) -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _quote(text: str) -> str:
    return f"“{text}”"


def format_duration(ms: Optional[int]) -> str:
    """``1.8 s`` under ten seconds, ``0:42`` / ``12:05`` above, ``h:mm:ss`` past an hour."""
    if ms is None:
        return ""
    try:
        total_ms = max(0, int(ms))
    except Exception:
        return ""
    if total_ms < 10_000:
        return f"{total_ms / 1000.0:.1f} s"
    total_s = total_ms // 1000
    hours, rem = divmod(total_s, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _elapsed_label(seconds: Optional[float]) -> str:
    """``m:ss`` counter text for the card header (``h:mm:ss`` past an hour)."""
    if seconds is None:
        return ""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _duration_between(started_ts: str, ended_ts: str) -> Optional[int]:
    """Milliseconds between two ledger timestamps — only when BOTH parse."""
    start = parse_iso_ms(started_ts)
    end = parse_iso_ms(ended_ts)
    if start is None or end is None:
        return None
    return max(0, end - start)


def _args_text(args: Any) -> str:
    """Bounded textual form of tool arguments for the run log."""
    if args is None or args == "" or args == {}:
        return ""
    if isinstance(args, str):
        text = args
    else:
        try:
            text = json.dumps(args, ensure_ascii=False)
        except Exception:
            text = str(args)
    if len(text) > 4000:
        #[WARNING:TRUNCATION] bounded for the run log; the ledger keeps the full arguments
        text = text[:3999] + "…"
    return text


def _tool_call_name(call: Any) -> str:
    if isinstance(call, dict):
        return _one_line(call.get("name")) or "tool"
    return "tool"


# --------------------------------------------------------------------------- #
# Model half
# --------------------------------------------------------------------------- #


@dataclass
class ActivityStep:
    """One row of run activity. ``title_plain`` is the accessible text; a
    non-empty ``title_html`` is bounded rich text (tool rows)."""

    step_id: str
    kind: str
    title_plain: str
    title_html: str = ""
    tone: str = "info"
    status: str = "info"
    started_ts: str = ""
    ended_ts: str = ""
    detail: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.status in _OPEN_STATUSES

    @property
    def is_pending_wait(self) -> bool:
        """A wait the user deferred/dismissed: closed as a row, still parked."""
        return self.kind in _WAIT_KINDS and bool(self.payload.get("pending"))

    def duration_ms(self) -> Optional[int]:
        return _duration_between(self.started_ts, self.ended_ts)

    def duration_text(self) -> str:
        return format_duration(self.duration_ms())


class RunActivityModel:
    """Steps of one run, fed by worker event payloads and local notes.

    ``reattached`` runs have no locally-known start time: ``elapsed_s()`` and
    ``summary()['elapsed_ms']`` are ``None`` for them, never a fabricated total.
    """

    def __init__(
        self,
        run_id: str = "",
        *,
        reattached: bool = False,
        clock: Callable[[], float] = time.monotonic,
        max_steps: int = 200,
    ) -> None:
        self.run_id = str(run_id or "")
        self.reattached = bool(reattached)
        self.steps: List[ActivityStep] = []
        self.finished = False
        self.final_status = ""
        self._clock = clock
        self._max_steps = max(8, int(max_steps or 200))
        self._started_at = float(clock())
        self._finished_at: Optional[float] = None
        self._counters: Dict[str, int] = {}
        self._tool_name_counts: Dict[str, int] = {}
        self._wait_occurrences: Dict[str, int] = {}
        self._offline_step_id: Optional[str] = None
        self._paused = False

    # -- lookups ----------------------------------------------------------- #

    def step(self, step_id: str) -> Optional[ActivityStep]:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def current_step(self) -> Optional[ActivityStep]:
        """Latest running/waiting step (a deferred wait still counts: the run
        is parked on it even though the row is closed)."""
        for step in reversed(self.steps):
            if step.is_open or step.is_pending_wait:
                return step
        return None

    def elapsed_s(self) -> Optional[float]:
        if self.reattached:
            return None
        end = self._finished_at if self._finished_at is not None else float(self._clock())
        return max(0.0, end - self._started_at)

    # -- mutation ---------------------------------------------------------- #

    def _next(self, prefix: str) -> str:
        n = int(self._counters.get(prefix, 0)) + 1
        self._counters[prefix] = n
        return f"{prefix}:{n}"

    def _append(self, step: ActivityStep) -> ActivityStep:
        self.steps.append(step)
        self._bound()
        return step

    def _bound(self) -> None:
        overflow = len(self.steps) - self._max_steps
        if overflow <= 0:
            return
        kept: List[ActivityStep] = []
        for step in self.steps:
            if overflow > 0 and not step.is_open:
                overflow -= 1
                continue
            kept.append(step)
        self.steps = kept

    def apply_event(self, payload: Dict[str, Any]) -> List[str]:
        """Fold one worker event; return the ids of the steps it changed."""
        if not isinstance(payload, dict):
            return []
        typ = str(payload.get("type") or "").strip()
        handler = {
            "cycle": self._on_cycle,
            "cycle_result": self._on_cycle_result,
            "tool_started": self._on_tool_started,
            "tool": self._on_tool_result,
            "tool_request": self._on_tool_request,
            "ask_user": self._on_ask_user,
            "status": self._on_status,
            "error": self._on_error,
            "replay_degraded": self._on_replay_degraded,
            "assistant": self._on_assistant,
        }.get(typ)
        if handler is None:
            # run_activity echoes the user's prompt (finding 21); history /
            # composer bookkeeping events carry no activity. Ignore quietly.
            return []
        try:
            changed = handler(payload)
        except Exception:
            return []
        return [step_id for step_id in changed if step_id]

    def note_local(self, kind: str, text: str, *, tone: str = "", status: str = "") -> str:
        """Record a locally-initiated control step (steer / pause / resume /
        stop). Returns the new step id. Empty tone/status take the kind's
        defaults (pause and stop are open until the gateway settles them)."""
        kind_key = str(kind or "").strip().lower() or "steer"
        default_tone, default_status = _LOCAL_DEFAULTS.get(kind_key, ("info", "info"))
        tone_value = str(tone or "").strip() or default_tone
        status_value = str(status or "").strip() or default_status
        text_value = _one_line(text)
        if kind_key == "steer":
            preview = _clip(text_value, _PROMPT_MAX_CHARS)
            title = f"You steered: {_quote(preview)}"
            step_id = self._next("steer")
            payload: Dict[str, Any] = {"preview": preview}
            # A steer resumes nothing, but a paused run reads its guidance on resume.
        else:
            title = text_value or {
                "pause": "Pause requested — applies at the next step boundary",
                "resume": "Resumed",
                "stop": "Stopping…",
            }.get(kind_key, kind_key)
            step_id = self._next("ctl")
            payload = {}
        if kind_key == "resume":
            self._paused = False
            self._close_pending_pause(title="Paused")
        if kind_key == "pause":
            self._close_pending_pause(title="Paused")
        self._append(
            ActivityStep(
                step_id=step_id,
                kind=kind_key,
                title_plain=_clip(title, _TITLE_MAX_CHARS),
                tone=tone_value,
                status=status_value,
                payload=payload,
            )
        )
        return step_id

    def resolve_wait(self, wait_key: str, outcome: str) -> Optional[str]:
        """Settle the latest wait step for ``wait_key`` with a user/auto
        outcome. Returns the step id it updated (``None`` when no wait exists)."""
        key = str(wait_key or "").strip()
        result = str(outcome or "").strip().lower()
        # Newest open wait first (the runtime reuses one wait_key per node, so
        # a second approval batch is a NEWER step with the same key): an
        # undecided ``waiting`` step wins, then a deferred/dismissed one that
        # is still pending, then the newest matching step of any status.
        matches = [
            step
            for step in reversed(self.steps)
            if step.kind in _WAIT_KINDS and (not key or str(step.payload.get("wait_key") or "") == key)
        ]
        target: Optional[ActivityStep] = None
        for step in matches:
            if step.status == "waiting":
                target = step
                break
        if target is None:
            for step in matches:
                if step.payload.get("pending"):
                    target = step
                    break
        if target is None and matches:
            target = matches[0]
        if target is None:
            return None
        # Any older step on the same key is superseded: it can no longer be
        # the one the user is answering.
        for step in matches:
            if step is not target and step.payload.get("pending"):
                step.payload["pending"] = False
        tool = str(target.payload.get("tool") or "")
        extra = target.payload.get("extra_tools") or 0
        suffix = f" · {tool}" if tool else ""
        pending = False
        if result == "approved":
            target.status, target.tone, target.title_plain = "ok", "ok", "Approved by you"
        elif result == "approved_session":
            target.status, target.tone, target.title_plain = "ok", "ok", "Approved by you"
            target.detail = "Trusting enabled tools in this chat"
        elif result == "auto_approved":
            target.status, target.tone = "ok", "ok"
            target.title_plain = f"Auto-approved (trusted in this chat){suffix}"
            if extra:
                target.title_plain += f" +{extra} more"
        elif result == "denied":
            target.status, target.tone, target.title_plain = "denied", "danger", "Denied by you"
        elif result == "deferred":
            target.status, target.tone = "info", "attention"
            target.title_plain = "Deferred — run is waiting"
            pending = True
        elif result == "answered":
            target.status, target.tone, target.title_plain = "ok", "ok", "You answered"
        elif result == "dismissed":
            target.status, target.tone = "info", "attention"
            target.title_plain = "Dismissed — run is waiting"
            pending = True
        else:
            return None
        target.title_html = ""
        target.payload["outcome"] = result
        target.payload["pending"] = pending
        return target.step_id

    def finish(self, status: str = "completed") -> None:
        """Freeze the run. Open steps close as ``info`` (no result observed),
        never as ``ok`` — that would claim an outcome nobody saw."""
        if self.finished:
            return
        self.finished = True
        self.final_status = str(status or "completed").strip().lower() or "completed"
        self._finished_at = float(self._clock())
        for step in self.steps:
            if step.kind == "cycle" and step.status == "running":
                step.status, step.tone = "ok", "ok"
            elif step.is_open:
                step.status = "info"
                if step.tone in ("thinking", "tool", "attention", "paused", "offline"):
                    step.tone = "info"
            if step.kind in _WAIT_KINDS:
                step.payload["pending"] = False
        self._offline_step_id = None

    # -- event handlers ---------------------------------------------------- #

    def _cycle_id(self, iteration: Any, run_id: str) -> str:
        try:
            n = int(iteration)
        except Exception:
            n = 0
        base = f"cycle:{n}"
        existing = self.step(base)
        if existing is not None and run_id and str(existing.payload.get("run_id") or "") not in ("", run_id):
            # A sub-run restarts its own cycle count: keep both distinguishable.
            return f"{base}@{run_id[:8]}"
        return base

    def _on_cycle(self, payload: Dict[str, Any]) -> List[str]:
        run_id = str(payload.get("run_id") or "").strip()
        iteration = payload.get("iteration")
        try:
            n = int(iteration)
        except Exception:
            n = len([s for s in self.steps if s.kind == "cycle"]) + 1
        changed: List[str] = []
        for step in self.steps:
            if step.kind == "cycle" and step.status == "running":
                step.status, step.tone = "ok", "ok"
                changed.append(step.step_id)
            elif step.kind == "tool" and step.status == "running":
                # The agent loop is sequential: a new reasoning cycle means the
                # previous tool round finished. Its outcome was not observed,
                # so the row closes as info — not ok.
                step.status, step.tone = "info", "info"
                changed.append(step.step_id)
        step_id = self._cycle_id(n, run_id)
        step = self.step(step_id)
        title = f"Thinking · cycle {n}"
        ts = str(payload.get("ts") or "").strip()
        if step is None:
            step = self._append(
                ActivityStep(
                    step_id=step_id,
                    kind="cycle",
                    title_plain=title,
                    tone="thinking",
                    status="running",
                    started_ts=ts,
                    payload={"iteration": n, "run_id": run_id},
                )
            )
        else:
            step.status, step.tone, step.title_plain = "running", "thinking", title
            if ts:
                step.started_ts = ts
        changed.append(step.step_id)
        return changed

    def _on_cycle_result(self, payload: Dict[str, Any]) -> List[str]:
        run_id = str(payload.get("run_id") or "").strip()
        step_id = self._cycle_id(payload.get("iteration"), run_id)
        step = self.step(step_id)
        if step is None:
            for candidate in reversed(self.steps):
                if candidate.kind == "cycle" and candidate.status == "running":
                    step = candidate
                    break
        content = str(payload.get("content") or "")
        reasoning = str(payload.get("reasoning") or "")
        ts = str(payload.get("ts") or "").strip()
        detail = _clip(_one_line(speech_plain_text(content or reasoning)), _DETAIL_MAX_CHARS)
        try:
            n = int(payload.get("iteration"))
        except Exception:
            n = 0
        if step is None:
            step = self._append(
                ActivityStep(
                    step_id=step_id,
                    kind="cycle",
                    title_plain=f"Thinking · cycle {max(1, n)}",
                    payload={"iteration": max(1, n), "run_id": run_id},
                )
            )
        step.status, step.tone = "ok", "ok"
        step.ended_ts = ts or step.ended_ts
        step.detail = detail
        step.payload["content"] = content
        step.payload["reasoning"] = reasoning
        return [step.step_id]

    def _tool_step_id(self, name: str, call_id: str) -> str:
        if call_id:
            return f"tool:{call_id}"
        k = int(self._tool_name_counts.get(name, 0)) + 1
        self._tool_name_counts[name] = k
        return f"tool:{name}#{k}"

    @staticmethod
    def _tool_args(entry: Dict[str, Any]) -> Any:
        args = entry.get("arguments")
        if isinstance(args, dict) or (isinstance(args, str) and args.strip()):
            return args
        return entry.get("arguments_text") or entry.get("arguments_preview") or None

    def _on_tool_started(self, payload: Dict[str, Any]) -> List[str]:
        changed: List[str] = []
        run_id = str(payload.get("run_id") or "").strip()
        for entry in payload.get("tools") or []:
            if not isinstance(entry, dict):
                continue
            name = _one_line(entry.get("name"))
            if not name:
                continue
            call_id = str(entry.get("call_id") or "").strip()
            args = self._tool_args(entry)
            step_id = self._tool_step_id(name, call_id)
            ts = str(entry.get("ts") or payload.get("ts") or "").strip()
            step = self.step(step_id)
            title_plain = compact_tool_call_label(name, args)
            title_html = compact_tool_call_label_html(name, args)
            args_text = str(entry.get("arguments_text") or "") or _args_text(args)
            args_preview = str(entry.get("arguments_preview") or "") or _clip(_one_line(args_text), 120)
            step_payload = {
                "name": name,
                "call_id": call_id,
                "arguments": args,
                "arguments_text": args_text,
                "arguments_preview": args_preview,
                "run_id": run_id,
            }
            if step is None:
                step = self._append(
                    ActivityStep(
                        step_id=step_id,
                        kind="tool",
                        title_plain=title_plain,
                        title_html=title_html,
                        tone="tool",
                        status="running",
                        started_ts=ts,
                        payload=step_payload,
                    )
                )
            else:
                step.title_plain, step.title_html = title_plain, title_html
                step.tone, step.status = "tool", "running"
                step.started_ts = ts or step.started_ts
                step.payload.update(step_payload)
            changed.append(step.step_id)
        return changed

    def _on_tool_result(self, payload: Dict[str, Any]) -> List[str]:
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        meta = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        name = _one_line(meta.get("name"))
        if not name:
            match = re.match(r"\s*\[([^\]]+)\]:", str(message.get("content") or ""))
            name = _one_line(match.group(1)) if match else "tool"
        call_id = str(meta.get("call_id") or "").strip()
        ts = str(message.get("ts") or payload.get("ts") or "").strip()
        content = str(message.get("content") or "")
        success = meta.get("success")
        error = str(meta.get("error") or "").strip()

        step: Optional[ActivityStep] = None
        if call_id:
            step = self.step(f"tool:{call_id}")
        if step is None:
            for candidate in self.steps:  # FIFO: the oldest running call by name
                if (
                    candidate.kind == "tool"
                    and candidate.status == "running"
                    and str(candidate.payload.get("name") or "") == name
                ):
                    step = candidate
                    break
        if step is None:
            args = meta.get("arguments")
            if args is None:
                args = meta.get("args")
            step = self._append(
                ActivityStep(
                    step_id=self._tool_step_id(name, call_id),
                    kind="tool",
                    title_plain=compact_tool_call_label(name, args),
                    title_html=compact_tool_call_label_html(name, args),
                    tone="tool",
                    status="running",
                    payload={
                        "name": name,
                        "call_id": call_id,
                        "arguments": args,
                        "arguments_text": _args_text(args),
                        "arguments_preview": _clip(_one_line(_args_text(args)), 120),
                        "run_id": str(payload.get("run_id") or message.get("run_id") or ""),
                    },
                )
            )
        if success is True:
            step.status, step.tone = "ok", "ok"
            step.detail = _clip(_one_line(content), _DETAIL_MAX_CHARS)
        elif success is False:
            step.status, step.tone = "failed", "danger"
            step.detail = _clip(_first_line(error) or _first_line(content), _DETAIL_MAX_CHARS)
        else:
            step.status, step.tone = "info", "info"
            step.detail = _clip(_one_line(content), _DETAIL_MAX_CHARS)
        step.ended_ts = ts or step.ended_ts
        preview = content
        if len(preview) > _RESULT_PREVIEW_MAX_CHARS:
            #[WARNING:TRUNCATION] bounded result preview for the run log
            preview = preview[: _RESULT_PREVIEW_MAX_CHARS - 1] + "…"
        step.payload["result_preview"] = preview
        step.payload["success"] = success
        step.payload["error"] = error
        if call_id and not step.payload.get("call_id"):
            step.payload["call_id"] = call_id
        return [step.step_id]

    def _wait_step_id(self, wait_key: str, payload: Dict[str, Any]) -> str:
        step = str(payload.get("step_id") or payload.get("step") or "").strip()
        if not step:
            n = int(self._wait_occurrences.get(wait_key, 0)) + 1
            self._wait_occurrences[wait_key] = n
            step = str(n)
        return f"wait:{wait_key}:{step}"

    def _on_tool_request(self, payload: Dict[str, Any]) -> List[str]:
        wait_key = str(payload.get("wait_key") or "").strip()
        tool_calls = payload.get("tool_calls") if isinstance(payload.get("tool_calls"), list) else []
        names = [_tool_call_name(call) for call in tool_calls]
        first = names[0] if names else ""
        extra = max(0, len(names) - 1)
        title = "Needs your approval"
        if first:
            title += f" · {first}"
        if extra:
            title += f" +{extra} more"
        step_id = self._wait_step_id(wait_key, payload)
        step = self.step(step_id)
        step_payload = {
            "wait_key": wait_key,
            "run_id": str(payload.get("run_id") or ""),
            "tool_calls": list(tool_calls),
            "tools": names,
            "tool": first,
            "extra_tools": extra,
            "pending": False,
        }
        if step is None:
            self._append(
                ActivityStep(
                    step_id=step_id,
                    kind="wait_approval",
                    title_plain=title,
                    tone="attention",
                    status="waiting",
                    payload=step_payload,
                )
            )
        else:
            step.title_plain, step.title_html = title, ""
            step.tone, step.status = "attention", "waiting"
            step.payload.update(step_payload)
        return [step_id]

    def _on_ask_user(self, payload: Dict[str, Any]) -> List[str]:
        wait_key = str(payload.get("wait_key") or "").strip()
        prompt = _one_line(speech_plain_text(str(payload.get("prompt") or ""))) or "Input required"
        title = f"Asked you: {_quote(_clip(prompt, _PROMPT_MAX_CHARS))}"
        step_id = self._wait_step_id(wait_key, payload)
        step = self.step(step_id)
        step_payload = {
            "wait_key": wait_key,
            "run_id": str(payload.get("run_id") or ""),
            "prompt": str(payload.get("prompt") or ""),
            "pending": False,
        }
        if step is None:
            self._append(
                ActivityStep(
                    step_id=step_id,
                    kind="wait_input",
                    title_plain=title,
                    tone="attention",
                    status="waiting",
                    payload=step_payload,
                )
            )
        else:
            step.title_plain, step.title_html = title, ""
            step.tone, step.status = "attention", "waiting"
            step.payload.update(step_payload)
        return [step_id]

    def _on_status(self, payload: Dict[str, Any]) -> List[str]:
        text = _one_line(payload.get("status")).lower()
        if text == "offline":
            reason = _one_line(payload.get("reason"))
            step = self.step(self._offline_step_id) if self._offline_step_id else None
            if step is not None and step.status == "running":
                step.detail = reason
                step.payload["reason"] = reason
                return [step.step_id]
            step = self._append(
                ActivityStep(
                    step_id=self._next("net"),
                    kind="offline",
                    title_plain="Gateway unreachable — retrying",
                    tone="offline",
                    status="running",
                    detail=reason,
                    payload={"reason": reason},
                )
            )
            self._offline_step_id = step.step_id
            return [step.step_id]
        changed: List[str] = []
        if self._offline_step_id:
            step = self.step(self._offline_step_id)
            self._offline_step_id = None
            if step is not None and step.status == "running":
                step.status, step.tone, step.title_plain = "ok", "ok", "Reconnected"
                step.detail = ""  # the outage reason stays in payload["reason"]
                changed.append(step.step_id)
        if text == "paused":
            self._paused = True
            changed.extend(self._close_pending_pause(title="Paused"))
        return changed

    def _close_pending_pause(self, *, title: str) -> List[str]:
        changed: List[str] = []
        for step in self.steps:
            if step.kind == "pause" and step.is_open:
                step.status, step.title_plain = "info", title
                changed.append(step.step_id)
        return changed

    def _on_error(self, payload: Dict[str, Any]) -> List[str]:
        message = _one_line(payload.get("error") or payload.get("message")) or "Run failed"
        step = self._append(
            ActivityStep(
                step_id=self._next("err"),
                kind="error",
                title_plain=_clip(message, _TITLE_MAX_CHARS),
                tone="danger",
                status="failed",
                detail=_clip(message, _DETAIL_MAX_CHARS),
                payload={"error": str(payload.get("error") or payload.get("message") or "")},
            )
        )
        return [step.step_id]

    def _on_replay_degraded(self, payload: Dict[str, Any]) -> List[str]:
        message = _one_line(payload.get("message")) or "Gateway replay is degraded."
        step = self._append(
            ActivityStep(
                step_id=self._next("err"),
                kind="replay",
                title_plain=_clip(message, _TITLE_MAX_CHARS),
                tone="danger",
                status="failed",
                detail=_clip(message, _DETAIL_MAX_CHARS),
                payload={"message": message},
            )
        )
        return [step.step_id]

    def _on_assistant(self, payload: Dict[str, Any]) -> List[str]:
        if not bool(payload.get("final")):
            return []
        open_ids = [step.step_id for step in self.steps if step.is_open]
        self.finish("completed")
        return open_ids

    # -- derived views ----------------------------------------------------- #

    def header_text(self) -> str:
        if self.finished:
            return {
                "completed": "Done",
                "stopped": "Stopped",
                "cancelled": "Stopped",
                "failed": "Failed",
                "error": "Failed",
            }.get(self.final_status, self.final_status.capitalize() or "Done")
        last = self.steps[-1] if self.steps else None
        if last is not None and last.kind in _LOCAL_KINDS:
            if last.kind == "steer":
                return f"Steering: {_quote(str(last.payload.get('preview') or ''))}"
            if last.kind == "pause":
                return "Pause requested…" if last.is_open else "Paused"
            if last.kind == "resume":
                return "Resumed"
            return "Stopping…"
        if (
            last is not None
            and last.kind == "wait_approval"
            and str(last.payload.get("outcome") or "") == "auto_approved"
        ):
            tool = str(last.payload.get("tool") or "")
            return f"Auto-approved · {tool}" if tool else "Auto-approved"
        if last is not None and last.kind in ("error", "replay"):
            return last.title_plain
        if self._paused:
            return "Paused"
        current = self.current_step()
        if current is None:
            if self.reattached:
                return "Reattached — following the run"
            return "Running…"
        if current.kind == "cycle":
            return f"Thinking · cycle {current.payload.get('iteration', '')}".rstrip()
        if current.kind == "tool":
            return f"Running {current.title_plain}"
        if current.kind == "wait_approval":
            tool = str(current.payload.get("tool") or "")
            extra = int(current.payload.get("extra_tools") or 0)
            text = f"Needs your approval · {tool}" if tool else "Needs your approval"
            return f"{text} +{extra} more" if extra else text
        if current.kind == "wait_input":
            return "Waiting for your answer"
        if current.kind == "offline":
            return "Gateway unreachable — retrying"
        return current.title_plain

    def header_tone(self) -> str:
        if self.finished:
            return "danger" if self.final_status in ("failed", "error") else "ok"
        last = self.steps[-1] if self.steps else None
        if last is not None and last.kind in _LOCAL_KINDS:
            return last.tone or "info"
        if last is not None and last.kind == "wait_approval" and last.payload.get("outcome") == "auto_approved":
            return "ok"
        if last is not None and last.kind in ("error", "replay"):
            return "danger"
        if self._paused:
            return "paused"
        current = self.current_step()
        if current is None:
            return "thinking"
        return current.tone or "thinking"

    def summary(self) -> Dict[str, Any]:
        cycles = sum(1 for s in self.steps if s.kind == "cycle")
        tools = sum(1 for s in self.steps if s.kind == "tool")
        failures = sum(1 for s in self.steps if s.kind == "tool" and s.status == "failed")
        waits = sum(1 for s in self.steps if s.kind in _WAIT_KINDS)
        elapsed = self.elapsed_s()
        return {
            "cycles": cycles,
            "tools": tools,
            "tool_failures": failures,
            "waits": waits,
            "elapsed_ms": None if elapsed is None else int(elapsed * 1000),
            "steps": len(self.steps),
        }

    def summary_text(self) -> str:
        """``3 cycles · 4 tools (1 failed) · 1 approval · 41 s`` (elapsed only when known)."""
        data = self.summary()
        parts: List[str] = []
        if data["cycles"]:
            parts.append(f"{data['cycles']} cycle" + ("s" if data["cycles"] != 1 else ""))
        if data["tools"]:
            text = f"{data['tools']} tool" + ("s" if data["tools"] != 1 else "")
            if data["tool_failures"]:
                text += f" ({data['tool_failures']} failed)"
            parts.append(text)
        if data["waits"]:
            parts.append(f"{data['waits']} wait" + ("s" if data["waits"] != 1 else ""))
        if data["elapsed_ms"] is not None:
            parts.append(format_duration(data["elapsed_ms"]))
        return " · ".join(parts)

    def to_log_entries(self) -> List[Dict[str, Any]]:
        """Entries in the shape ``RunActivityDialog`` renders."""
        entries: List[Dict[str, Any]] = []
        for step in self.steps:
            if step.kind == "cycle":
                n = step.payload.get("iteration")
                entries.append({"kind": "cycle", "n": n, "ts": step.started_ts})
                content = str(step.payload.get("content") or "")
                reasoning = str(step.payload.get("reasoning") or "")
                if content or reasoning:
                    entries.append(
                        {
                            "kind": "thinking",
                            "n": n,
                            "content": content,
                            "reasoning": reasoning,
                            "ts": step.ended_ts,
                        }
                    )
            elif step.kind == "tool":
                entries.append(
                    {
                        "kind": "tools",
                        "tools": [
                            {
                                "name": str(step.payload.get("name") or "tool"),
                                "arguments_text": str(step.payload.get("arguments_text") or ""),
                                "arguments_preview": str(step.payload.get("arguments_preview") or ""),
                            }
                        ],
                        "ts": step.started_ts,
                    }
                )
                if step.status != "running":
                    preview = str(step.payload.get("result_preview") or "")
                    if step.status == "failed" and step.payload.get("error"):
                        preview = f"{step.payload.get('error')}\n{preview}".strip()
                    entries.append(
                        {
                            "kind": "tool_result",
                            "name": str(step.payload.get("name") or "tool"),
                            "preview": preview,
                            "ts": step.ended_ts,
                        }
                    )
            elif step.kind in _WAIT_KINDS:
                entries.append({"kind": "waiting", "text": step.title_plain, "ts": step.started_ts})
            else:
                text = step.title_plain
                if step.detail and step.detail != step.title_plain:
                    text = f"{text} · {step.detail}"
                entries.append({"kind": "status", "text": text, "ts": step.started_ts})
        return entries


# --------------------------------------------------------------------------- #
# Stylesheet (tokens only)
# --------------------------------------------------------------------------- #


def _alpha(color: str, alpha: float) -> str:
    """Derive ``rgba(...)`` from a theme hex token (no new literals)."""
    value = str(color or "").strip()
    if value.startswith("#") and len(value) == 7:
        r, g, b = (int(value[i : i + 2], 16) for i in (1, 3, 5))
        return f"rgba({r}, {g}, {b}, {alpha:.2f})"
    return value


def _token(name: str, fallback: str) -> str:
    """Theme token with a token fallback (``attention`` lands in theme.py later)."""
    return str(getattr(THEME, name, "") or fallback)


def _build_activity_qss() -> str:
    t, m = THEME, METRICS
    attention = _token("attention", t.warning)
    attention_bg = _token("attention_bg", t.warning_bg)
    attention_border = _token("attention_border", _alpha(attention, 0.42))
    # One calm component: the surface stays close to the transcript's own
    # cards; the tone lives in the border and the header text. Backgrounds
    # are tinted at ≤ 0.10 alpha so four rows never read as a colour block.
    tones = {
        "thinking": (t.accent, _alpha(t.accent, 0.07), _alpha(t.accent, 0.28)),
        "tool": (t.warning, _alpha(t.warning, 0.07), _alpha(t.warning, 0.28)),
        "waiting": (attention, attention_bg, attention_border),
        "attention": (attention, attention_bg, attention_border),
        "paused": (t.text_muted, t.overlay_faint, t.border_strong),
        "offline": (t.warning, t.warning_bg, _alpha(t.warning, 0.32)),
        "ok": (t.positive, _alpha(t.positive, 0.06), _alpha(t.positive, 0.26)),
        "danger": (t.danger_text, t.danger_bg, _alpha(t.danger, 0.35)),
        "info": (t.text_secondary, t.overlay_faint, t.border_subtle),
    }
    tone_rules = []
    for tone, (fg, bg, border) in tones.items():
        tone_rules.append(
            f"""
            QFrame#thinkingBubble[tone="{tone}"] {{
                border-color: {border};
                background: {bg};
            }}
            QLabel#thinkingStatusText[tone="{tone}"] {{
                color: {fg};
            }}"""
        )
    radius = m.radius_control + 1
    return (
        f"""
            /* Live run activity card (abstractassistant.ui.activity). */
            QFrame#thinkingIndicator {{
                border: none;
                background: transparent;
            }}
            QFrame#thinkingBubble {{
                border-radius: {radius}px;
                border: 1px solid {t.border_subtle};
                background: {t.overlay_faint};
            }}
            QLabel#thinkingStatusText {{
                color: {t.text_secondary};
                font-size: {m.font_caption}px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}"""
        + "".join(tone_rules)
        + f"""
            QLabel#activityElapsed {{
                color: {t.text_faint};
                font-size: {m.font_caption}px;
                font-weight: 600;
                background: transparent;
                border: none;
                padding: 0px 2px;
            }}
            QLabel#activityDoneGlyph {{
                background: transparent;
                border: none;
            }}
            QFrame#thinkingBubble QPushButton#iconButton {{
                min-height: 22px;
                max-height: 22px;
                min-width: 22px;
                max-width: 22px;
                padding: 0px;
                border-radius: {m.radius_chip}px;
                background: transparent;
                border: 1px solid transparent;
            }}
            QFrame#thinkingBubble QPushButton#iconButton:hover {{
                background: {t.overlay_hover};
                border-color: {t.border_subtle};
            }}
            QFrame#thinkingBubble QPushButton#iconButton:pressed {{
                background: {t.overlay_active};
            }}
            QWidget#activityStepList {{
                background: transparent;
                border: none;
            }}
            QFrame#activityStepRow {{
                background: transparent;
                border: none;
                border-radius: {m.radius_chip}px;
            }}
            QFrame#activityStepRow:hover {{
                background: {t.overlay_faint};
            }}
            QLabel#activityStepGlyph {{
                background: transparent;
                border: none;
            }}
            QLabel#activityStepTitle {{
                color: {t.text_secondary};
                font-size: {m.font_ui}px;
                background: transparent;
                border: none;
            }}
            QFrame#activityStepRow[status="running"] QLabel#activityStepTitle {{
                color: {t.text_primary};
            }}
            QFrame#activityStepRow[status="waiting"] QLabel#activityStepTitle {{
                color: {attention};
            }}
            QFrame#activityStepRow[status="failed"] QLabel#activityStepTitle,
            QFrame#activityStepRow[status="denied"] QLabel#activityStepTitle {{
                color: {t.danger_text};
            }}
            QLabel#activityStepMeta {{
                color: {t.text_faint};
                font-size: {m.font_caption}px;
                background: transparent;
                border: none;
            }}
            QPushButton#activityMoreLink {{
                background: transparent;
                border: none;
                color: {t.accent};
                font-size: {m.font_caption}px;
                font-weight: 600;
                text-align: left;
                padding: 0px 6px;
                min-height: 18px;
                max-height: 18px;
            }}
            QPushButton#activityMoreLink:hover {{
                text-decoration: underline;
            }}
            QFrame#activityStepRow QPushButton#linkButton {{
                background: transparent;
                border: none;
                color: {t.accent};
                font-size: {m.font_caption}px;
                font-weight: 600;
                padding: 0px 4px;
                min-height: 18px;
                max-height: 18px;
            }}
            QFrame#activityStepRow QPushButton#linkButton:hover {{
                text-decoration: underline;
                color: {t.accent_text};
            }}
        """
    )


def build_activity_qss() -> str:
    """Rebuilt on demand so a theme switch reaches the activity card too."""
    return _build_activity_qss()


ACTIVITY_QSS: str = build_activity_qss()


# --------------------------------------------------------------------------- #
# Widget half
# --------------------------------------------------------------------------- #

_ROW_HEIGHT = 22
_GLYPH_PX = 14
_ICON_BUTTON_PX = 22
_MAX_COLLAPSED_ROWS = 4
_SPINNER_INTERVAL_MS = 100


def _polish(widget: QWidget) -> None:
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def _set_prop(widget: QWidget, name: str, value: Any) -> None:
    if widget.property(name) != value:
        widget.setProperty(name, value)
        _polish(widget)


def _glyph_for(status: str, spinner_frame: int = 0) -> tuple:
    attention = _token("attention", THEME.warning)
    if status == "running":
        return f"spinner{int(spinner_frame) % 8}", THEME.accent
    if status == "ok":
        return "circle-check", THEME.positive
    if status in ("failed", "denied"):
        return "circle-x", THEME.danger
    if status == "waiting":
        return "hand", attention
    return "info", THEME.text_muted


def _icon_button(name: str, tooltip: str, parent: Optional[QWidget] = None) -> QPushButton:
    button = QPushButton(parent)
    button.setObjectName("iconButton")
    button.setFocusPolicy(Qt.NoFocus)
    button.setCursor(Qt.PointingHandCursor)
    button.setFixedSize(_ICON_BUTTON_PX, _ICON_BUTTON_PX)
    button.setIconSize(QSize(_GLYPH_PX, _GLYPH_PX))
    button.setIcon(symbol_icon(name, color=THEME.text_secondary, size=_GLYPH_PX))
    button.setToolTip(tooltip)
    return button


class ThinkingDotsWidget(QWidget):
    """Three bouncing dots. The timer only runs while the widget is visible."""

    _INTERVAL_MS = 33

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(40, 18)
        self._tick = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(self._INTERVAL_MS)
        self._timer.timeout.connect(self._update_tick)
        self._rise = QColor(THEME.accent)
        self._rise.setAlpha(235)
        self._rest = QColor(THEME.text_faint)
        self._rest.setAlpha(140)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._timer.stop()
        super().hideEvent(event)

    def _update_tick(self) -> None:
        self._tick += 0.28
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        dot_radius = 3.0
        spacing = 9.0
        center_x = self.width() / 2.0
        center_y = self.height() / 2.0
        for i in range(3):
            phase = i * 0.95
            offset = math.sin(self._tick - phase)
            if offset > 0:
                y_shift = -offset * 4.5
                color = self._rise
            else:
                y_shift = 0.0
                color = self._rest
            painter.setBrush(QBrush(color))
            painter.drawEllipse(
                QPointF(center_x + (i - 1) * spacing, center_y + y_shift), dot_radius, dot_radius
            )
        painter.end()


class _StepRow(QFrame):
    """One 22 px activity row: glyph · title · meta · [Review/Answer]."""

    review_requested = pyqtSignal(str)

    def __init__(self, *, interactive: bool = True, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("activityStepRow")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(_ROW_HEIGHT)
        self._interactive = bool(interactive)
        self.step_id = ""
        self.status = ""
        self._title_plain = ""
        self._title_html = ""
        self._tool_name = ""
        self._tool_args: Any = None
        self._title_px = 240

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        self._glyph = QLabel(self)
        self._glyph.setObjectName("activityStepGlyph")
        self._glyph.setFixedSize(_GLYPH_PX, _GLYPH_PX)
        self._glyph.setScaledContents(True)
        layout.addWidget(self._glyph, 0, Qt.AlignVCenter)

        self._title = QLabel(self)
        self._title.setObjectName("activityStepTitle")
        self._title.setTextInteractionFlags(Qt.NoTextInteraction)
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self._title, 1, Qt.AlignVCenter)

        self._meta = QLabel(self)
        self._meta.setObjectName("activityStepMeta")
        self._meta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._meta, 0, Qt.AlignVCenter)

        self._link = QPushButton(self)
        self._link.setObjectName("linkButton")
        self._link.setFocusPolicy(Qt.NoFocus)
        self._link.setCursor(Qt.PointingHandCursor)
        self._link.setFlat(True)
        self._link.hide()
        self._link.clicked.connect(self._emit_review)
        layout.addWidget(self._link, 0, Qt.AlignVCenter)

    def _emit_review(self) -> None:
        if self.step_id:
            self.review_requested.emit(self.step_id)

    def set_title_budget(self, px: int) -> None:
        self._title_px = max(60, int(px or 0))
        self._apply_title()

    def update_from(self, step: ActivityStep, *, spinner_frame: int = 0) -> None:
        self.step_id = step.step_id
        self.status = step.status
        self._title_plain = step.title_plain
        self._title_html = step.title_html
        self._tool_name = str(step.payload.get("name") or "") if step.kind == "tool" else ""
        self._tool_args = step.payload.get("arguments") if step.kind == "tool" else None
        _set_prop(self, "status", step.status)
        self.set_spinner_frame(spinner_frame)
        self._apply_title()
        tooltip = step.title_plain
        if step.detail and step.detail != step.title_plain:
            tooltip = f"{step.title_plain}\n{step.detail}"
        self.setToolTip(tooltip)
        self._meta.setText(step.duration_text())
        self._meta.setVisible(bool(self._meta.text()))
        show_link = self._interactive and (step.status == "waiting" or step.is_pending_wait)
        if show_link:
            self._link.setText("Answer" if step.kind == "wait_input" else "Review")
        self._link.setVisible(show_link)

    def set_spinner_frame(self, frame: int) -> None:
        name, color = _glyph_for(self.status, frame)
        self._glyph.setPixmap(symbol_icon(name, color=color, size=_GLYPH_PX).pixmap(_GLYPH_PX, _GLYPH_PX))

    def _apply_title(self) -> None:
        metrics = QFontMetrics(self._title.font())
        if self._tool_name:
            # Shrink the compact label until it fits. The row keeps the
            # transcript's neutral text colours (name a little stronger than
            # its arguments) instead of the syntax-coloured label: the card
            # is one calm component, not a debug panel.
            budget = 120
            plain = compact_tool_call_label(self._tool_name, self._tool_args, max_chars=budget)
            while metrics.horizontalAdvance(plain) > self._title_px and budget > 16:
                budget = max(16, int(budget * 0.8))
                plain = compact_tool_call_label(self._tool_name, self._tool_args, max_chars=budget)
            name = self._tool_name
            rest = plain[len(name):] if plain.startswith(name) else ""
            if rest:
                self._title.setTextFormat(Qt.RichText)
                self._title.setText(
                    f'<span style="color:{THEME.text_primary}; font-weight:600">{_html.escape(name)}</span>'
                    f'<span style="color:{THEME.text_secondary}">{_html.escape(rest)}</span>'
                )
            else:
                self._title.setTextFormat(Qt.PlainText)
                self._title.setText(metrics.elidedText(plain, Qt.ElideRight, self._title_px))
            return
        self._title.setTextFormat(Qt.PlainText)
        self._title.setText(metrics.elidedText(self._title_plain, Qt.ElideRight, self._title_px))


class RunActivityCard(QFrame):
    """Transcript-tail card: header pill (dots + status + elapsed + controls)
    over a collapsible list of the run's most recent steps.

    ``set_status`` writes the header label verbatim (elided to the viewport);
    the step rows come from ``set_model`` / ``refresh``. The two are
    independent on purpose: the palette owns the header copy.
    """

    activated = pyqtSignal()
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    log_requested = pyqtSignal()
    review_requested = pyqtSignal(str)

    _TONES = frozenset({"thinking", "tool", "waiting"} | set(STEP_TONES))

    def __init__(
        self,
        status_text: str = "",
        tooltip: str = "",
        tone: str = "thinking",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("thinkingIndicator")
        self.setFrameShape(QFrame.NoFrame)
        self._raw_text = ""
        self._tooltip = ""
        self._max_text_px = 460
        self._model: Optional[RunActivityModel] = None
        self._expanded = False
        self._show_all = False
        self._paused = False
        self._spin_frame = 0
        self._rows: Dict[str, _StepRow] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._bubble = QFrame(self)
        self._bubble.setObjectName("thinkingBubble")
        self._bubble.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bubble_layout = QVBoxLayout(self._bubble)
        bubble_layout.setContentsMargins(8, 3, 6, 3)
        bubble_layout.setSpacing(2)

        # Header row -------------------------------------------------------
        self._header = QWidget(self._bubble)
        self._header.setObjectName("activityHeader")
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setFixedHeight(24)
        header = QHBoxLayout(self._header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(2)

        self._dots = ThinkingDotsWidget(self._header)
        header.addWidget(self._dots, 0, Qt.AlignVCenter)

        self._done_glyph = QLabel(self._header)
        self._done_glyph.setObjectName("activityDoneGlyph")
        self._done_glyph.setFixedSize(_GLYPH_PX + 4, _GLYPH_PX)
        self._done_glyph.setAlignment(Qt.AlignCenter)
        self._done_glyph.hide()
        header.addWidget(self._done_glyph, 0, Qt.AlignVCenter)

        self._status = QLabel("", self._header)
        self._status.setObjectName("thinkingStatusText")
        self._status.setTextFormat(Qt.PlainText)
        self._status.hide()
        header.addWidget(self._status, 0, Qt.AlignVCenter)
        header.addStretch(1)

        self._elapsed = QLabel("", self._header)
        self._elapsed.setObjectName("activityElapsed")
        self._elapsed.hide()
        header.addWidget(self._elapsed, 0, Qt.AlignVCenter)

        self.pause_button = _icon_button("pause", "Pause after the current step", self._header)
        self.pause_button.clicked.connect(self._on_pause_clicked)
        header.addWidget(self.pause_button, 0, Qt.AlignVCenter)

        self.stop_button = _icon_button("stop", "Stop the run (⌘.)", self._header)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.stop_button.hide()  # opt-in: show_stop_button(True)
        header.addWidget(self.stop_button, 0, Qt.AlignVCenter)

        self.log_button = _icon_button("list-tree", "Open the run log", self._header)
        self.log_button.clicked.connect(self._on_log_clicked)
        header.addWidget(self.log_button, 0, Qt.AlignVCenter)

        self.expand_button = _icon_button("chevron-down", "Show steps", self._header)
        self.expand_button.clicked.connect(self._on_expand_clicked)
        header.addWidget(self.expand_button, 0, Qt.AlignVCenter)

        bubble_layout.addWidget(self._header)

        # Step list --------------------------------------------------------
        self._steps_host = QWidget(self._bubble)
        self._steps_host.setObjectName("activityStepList")
        steps_layout = QVBoxLayout(self._steps_host)
        steps_layout.setContentsMargins(0, 0, 0, 2)
        steps_layout.setSpacing(0)
        self._more_link = QPushButton("", self._steps_host)
        self._more_link.setObjectName("activityMoreLink")
        self._more_link.setFocusPolicy(Qt.NoFocus)
        self._more_link.setCursor(Qt.PointingHandCursor)
        self._more_link.setFlat(True)
        self._more_link.clicked.connect(self._toggle_all_steps)
        self._more_link.hide()
        steps_layout.addWidget(self._more_link, 0, Qt.AlignLeft)
        self._rows_host = QWidget(self._steps_host)
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        steps_layout.addWidget(self._rows_host)
        self._steps_host.hide()
        bubble_layout.addWidget(self._steps_host)

        root.addWidget(self._bubble)

        # Timers (visibility-aware; see showEvent / hideEvent) --------------
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(_SPINNER_INTERVAL_MS)
        self._spinner_timer.timeout.connect(self._tick_spinner)

        self.set_status(status_text, tooltip=tooltip, tone=tone)

    # -- compatibility surface (ThinkingIndicatorCard) ----------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.button() == Qt.LeftButton and self._header.rect().contains(
            self._header.mapFrom(self, event.pos())
        ):
            self.activated.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def set_status(self, text: str, tooltip: str = "", tone: str = "thinking") -> None:
        self._raw_text = str(text or "").strip()
        base_tip = str(tooltip or self._raw_text).strip()
        hint = "Click to open the run log"
        self._tooltip = f"{base_tip}\n{hint}" if base_tip else hint
        normalized_tone = str(tone or "thinking").strip().lower()
        if normalized_tone not in self._TONES:
            normalized_tone = "thinking"
        for widget in (self._bubble, self._status):
            _set_prop(widget, "tone", normalized_tone)
        self._apply_text()

    def sync_to_viewport_width(self, width: int) -> None:
        # Keep the pill inside the transcript: dots (~40px) + paddings + margin.
        self._max_text_px = max(120, int(width or 0) - 96)
        self._apply_text()
        self._apply_row_budgets()

    def _header_controls_px(self) -> int:
        px = 0
        for button in (self.pause_button, self.stop_button, self.log_button, self.expand_button):
            if not button.isHidden():
                px += _ICON_BUTTON_PX + 2
        if not self._elapsed.isHidden():
            px += max(36, self._elapsed.sizeHint().width()) + 2
        return px

    def _apply_text(self) -> None:
        display = self._raw_text
        if display:
            metrics = QFontMetrics(self._status.font())
            budget = max(80, self._max_text_px - self._header_controls_px())
            display = metrics.elidedText(display, Qt.ElideRight, budget)
        self._status.setText(display)
        self._status.setVisible(bool(display))
        self._bubble.setToolTip(self._tooltip)
        self._header.setToolTip(self._tooltip)

    # -- model binding ------------------------------------------------------

    def model(self) -> Optional[RunActivityModel]:
        return self._model

    def set_model(self, model: Optional[RunActivityModel]) -> None:
        self._model = model
        self._show_all = False
        self.refresh()

    def sync_header_from_model(self) -> None:
        """Opt-in: derive the header copy/tone from the model (§2.3 copy)."""
        if self._model is None:
            return
        self.set_status(self._model.header_text(), tone=self._model.header_tone())

    def refresh(self, step_ids: Optional[List[str]] = None) -> None:
        model = self._model
        steps = list(model.steps) if model is not None else []
        if self._show_all or len(steps) <= _MAX_COLLAPSED_ROWS:
            visible = steps
        else:
            visible = steps[-_MAX_COLLAPSED_ROWS:]
        # The link is a toggle: it opens the full list and folds it back.
        hidden = len(steps) - len(visible)
        overflow = len(steps) - _MAX_COLLAPSED_ROWS
        if hidden > 0:
            self._more_link.setText(f"{hidden} earlier step{'s' if hidden != 1 else ''}…")
            self._more_link.setToolTip("Show every step of this run")
            self._more_link.setVisible(True)
        elif self._show_all and overflow > 0:
            self._more_link.setText(f"Show only the last {_MAX_COLLAPSED_ROWS} steps")
            self._more_link.setToolTip("Fold the earlier steps away")
            self._more_link.setVisible(True)
        else:
            self._more_link.setVisible(False)

        visible_ids = [step.step_id for step in visible]
        if visible_ids != list(self._rows.keys()):
            self._rebuild_rows(visible)
        else:
            wanted = set(step_ids or []) if step_ids else None
            for step in visible:
                if wanted is None or step.step_id in wanted:
                    self._rows[step.step_id].update_from(step, spinner_frame=self._spin_frame)
        self._apply_row_budgets()
        self._sync_done_glyph()
        self._sync_elapsed()
        self._sync_spinner_timer()

    def _rebuild_rows(self, steps: List[ActivityStep]) -> None:
        for index in reversed(range(self._rows_layout.count())):
            item = self._rows_layout.takeAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._rows = {}
        for step in steps:
            row = _StepRow(interactive=True, parent=self._rows_host)
            row.review_requested.connect(self.review_requested.emit)
            row.update_from(step, spinner_frame=self._spin_frame)
            self._rows_layout.addWidget(row)
            self._rows[step.step_id] = row

    def _apply_row_budgets(self) -> None:
        # Row: 6 + glyph 14 + 6 + title + 6 + meta (~40) + link (~48) + 6.
        budget = max(80, self._max_text_px + 96 - 32 - 72 - 60)
        for row in self._rows.values():
            row.set_title_budget(budget)

    def _toggle_all_steps(self) -> None:
        self._show_all = not self._show_all
        if self._show_all and not self._expanded:
            self.set_expanded(True)
        self.refresh()

    def _show_all_steps(self) -> None:
        """Open the full step list (kept as the explicit, non-toggling entry)."""
        if not self._show_all:
            self._toggle_all_steps()

    def _sync_done_glyph(self) -> None:
        model = self._model
        done = bool(model is not None and model.finished)
        if done:
            failed = model.final_status in ("failed", "error")
            name, color = ("circle-x", THEME.danger) if failed else ("circle-check", THEME.positive)
            self._done_glyph.setPixmap(symbol_icon(name, color=color, size=_GLYPH_PX).pixmap(_GLYPH_PX, _GLYPH_PX))
        self._done_glyph.setVisible(done)
        self._dots.setVisible(not done)
        self.pause_button.setVisible(not done)
        if done:
            self.stop_button.hide()

    # -- elapsed ------------------------------------------------------------

    def _sync_elapsed(self) -> None:
        model = self._model
        if model is None or model.reattached:
            self._elapsed.hide()
            self._elapsed_timer.stop()
            self._apply_text()
            return
        self._tick_elapsed()
        self._elapsed.show()
        if model.finished:
            self._elapsed_timer.stop()
        elif not self._elapsed_timer.isActive() and self.isVisible():
            self._elapsed_timer.start()
        self._apply_text()

    def _tick_elapsed(self) -> None:
        model = self._model
        if model is None:
            return
        self._elapsed.setText(_elapsed_label(model.elapsed_s()))
        self._elapsed.setToolTip("Elapsed since you sent the message")

    # -- spinner ------------------------------------------------------------

    def _running_rows(self) -> List[_StepRow]:
        return [row for row in self._rows.values() if row.status == "running"]

    def _sync_spinner_timer(self) -> None:
        active = self._expanded and self.isVisible() and bool(self._running_rows())
        if active and not self._spinner_timer.isActive():
            self._spinner_timer.start()
        elif not active:
            self._spinner_timer.stop()

    def _tick_spinner(self) -> None:
        self._spin_frame = (self._spin_frame + 1) % 8
        rows = self._running_rows()
        if not rows:
            self._spinner_timer.stop()
            return
        for row in rows:
            row.set_spinner_frame(self._spin_frame)

    # -- controls -----------------------------------------------------------

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self._steps_host.setVisible(self._expanded)
        self.expand_button.setIcon(
            symbol_icon(
                "chevron-up" if self._expanded else "chevron-down",
                color=THEME.text_secondary,
                size=_GLYPH_PX,
            )
        )
        self.expand_button.setToolTip("Hide steps" if self._expanded else "Show steps")
        self._sync_spinner_timer()

    def is_expanded(self) -> bool:
        return self._expanded

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)
        self.pause_button.setIcon(
            symbol_icon("play" if self._paused else "pause", color=THEME.text_secondary, size=_GLYPH_PX)
        )
        self.pause_button.setToolTip("Resume the run" if self._paused else "Pause after the current step")

    def is_paused(self) -> bool:
        return self._paused

    def show_stop_button(self, visible: bool) -> None:
        self.stop_button.setVisible(bool(visible))
        self._apply_text()

    def _on_pause_clicked(self) -> None:
        if self._paused:
            self.resume_requested.emit()
        else:
            self.pause_requested.emit()

    def _on_log_clicked(self) -> None:
        self.log_requested.emit()

    def _on_expand_clicked(self) -> None:
        self.set_expanded(not self._expanded)

    # -- visibility ---------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self._sync_elapsed()
        self._sync_spinner_timer()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._elapsed_timer.stop()
        self._spinner_timer.stop()
        super().hideEvent(event)


class ActivityStepList(QWidget):
    """Read-only list of every step of a finished run (post-run expansion)."""

    def __init__(self, model: Optional[RunActivityModel] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("activityStepList")
        self._model: Optional[RunActivityModel] = None
        self._title_px = 320
        self._rows: List[_StepRow] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        if model is not None:
            self.set_model(model)

    def set_model(self, model: Optional[RunActivityModel]) -> None:
        self._model = model
        self.refresh()

    def set_title_budget(self, px: int) -> None:
        self._title_px = max(80, int(px or 0))
        for row in self._rows:
            row.set_title_budget(self._title_px)

    def refresh(self) -> None:
        for index in reversed(range(self._layout.count())):
            item = self._layout.takeAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._rows = []
        steps = list(self._model.steps) if self._model is not None else []
        for step in steps:
            row = _StepRow(interactive=False, parent=self)
            row.update_from(step)
            row.set_title_budget(self._title_px)
            self._layout.addWidget(row)
            self._rows.append(row)
        self.setVisible(bool(steps))

    def rows(self) -> List[_StepRow]:
        return list(self._rows)
