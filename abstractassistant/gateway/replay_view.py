"""The desktop's reading of a run: AbstractGateway's replay view (`replay_view_v1`).

AbstractGateway 0.17.0 serves `GET /runs/{id}/view` and `GET /runs/{id}/view/stream`; the view is
AbstractRuntime's one reconstruction of a run tree (`abstractruntime.replay`, ADR 0010). This
module keeps the client's copy with the runtime's own `apply_delta` (no second reducer) and turns
each change of that copy into the events the chat and run panels already render. It never reads
ledger records.

- `ViewFold`: the client copy. A `view` frame replaces it; a `delta` frame is applied with
  `abstractruntime.replay.apply_delta` unless it is not newer than the copy (the same cursor
  token, or a run's seq below the copy's): a delta delivered twice or late never rolls the
  copy back.
- `ViewProjector`: copy -> UI events (`status`, `assistant`, `tool_started`, `tool`,
  `tool_request`, `ask_user`, `interaction_closed`, `cycle`, `tool_policy_decision`, `error`).
- `follow_run_view`: GET the view, then the stream with `Last-Event-ID` resume and bounded
  reconnects, until `done`.
"""

from __future__ import annotations

import time
import urllib.error
from typing import Any, Callable, Dict, List, Optional, Set

from abstractruntime.replay import apply_delta

from .client import GatewayHttpError, GatewayStreamIdle

TERMINAL = frozenset({"completed", "failed", "cancelled"})


class ViewOutOfSync(RuntimeError):
    """A delta arrived before any view: the copy cannot be built from it."""


def _cursor_runs(view_or_delta: Dict[str, Any]) -> Dict[str, int]:
    cur = view_or_delta.get("cursor") if isinstance(view_or_delta, dict) else None
    runs = cur.get("runs") if isinstance(cur, dict) else None
    out: Dict[str, int] = {}
    if isinstance(runs, dict):
        for k, v in runs.items():
            try:
                out[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
    return out


def _token(view_or_delta: Dict[str, Any]) -> str:
    cur = view_or_delta.get("cursor") if isinstance(view_or_delta, dict) else None
    return str(cur.get("token") or "") if isinstance(cur, dict) else ""


class ViewFold:
    """The client's copy of one run tree's replay view."""

    def __init__(self) -> None:
        self.view: Optional[Dict[str, Any]] = None
        self.dropped = 0  # deltas refused as duplicate or stale

    @property
    def token(self) -> str:
        return _token(self.view or {})

    def apply_frame(self, event: str, data: Dict[str, Any]) -> bool:
        """Fold one stream frame; True when the copy changed."""
        if event == "view":
            self.view = dict(data)
            return True
        if event != "delta":
            return False
        if self.view is None:
            raise ViewOutOfSync("a replay-view delta arrived before the view")
        new_tok = _token(data)
        if new_tok and new_tok == self.token:
            self.dropped += 1
            return False
        have = _cursor_runs(self.view)
        got = _cursor_runs(data)
        # A delta's cursor names every run of the tree it folded: a run the copy holds that
        # the delta lacks, or a lower seq, means the delta is older than the copy.
        for rid, seq in have.items():
            if got.get(rid, 0) < seq:
                self.dropped += 1
                return False
        self.view = apply_delta(self.view, data)
        return True


def _tool_entries(act: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for row in act.get("tool_calls") or []:
        if not isinstance(row, dict):
            continue
        entry: Dict[str, Any] = {"name": str(row.get("name") or "tool"), "call_uid": str(row.get("id") or "")}
        args = row.get("arguments")
        if isinstance(args, (dict, str)) and args:
            entry["arguments"] = args
        if act.get("started_at"):
            entry["ts"] = str(act.get("started_at"))
        out.append(entry)
    return out


def _result_text(row: Dict[str, Any]) -> str:
    if row.get("error"):
        return f"[{row.get('name') or 'tool'}]: Error: {row.get('error')}"
    out = row.get("output")
    if isinstance(out, str):
        text = out
    elif out is None:
        text = ""
    else:
        import json

        try:
            text = json.dumps(out, ensure_ascii=False)
        except Exception:
            text = str(out)
    return f"[{row.get('name') or 'tool'}]: {text}"


class ViewProjector:
    """Turns successive copies of a view into the UI events the panels render.

    Each event is emitted once per identity: a message id, an activity id, a tool row's
    (activity, call) and final status, an interaction's wait key."""

    def __init__(self) -> None:
        self._status = ""
        self._messages: Set[str] = set()
        self._started: Set[str] = set()
        self._tool_done: Set[str] = set()
        self._cycles = 0
        self._interaction = ""
        self._seen_interactions: Set[str] = set()

    def suppress_history(self, view: Dict[str, Any]) -> None:
        """Mark everything the view holds as already shown, except an open interaction (an
        attach: the transcript comes from the session seed; the open question must still be
        asked)."""
        for m in view.get("messages") or []:
            self._messages.add(str(m.get("id") or ""))
        for act in view.get("activities") or []:
            aid = str(act.get("id") or "")
            self._started.add(aid)
            if act.get("kind") == "llm":
                self._cycles += 1
            for row in act.get("tool_calls") or []:
                if str(row.get("status") or "") not in ("running", "waiting"):
                    self._tool_done.add(f"{aid}|{row.get('id')}")

    def project(self, view: Dict[str, Any]) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        root = str(view.get("root_run_id") or "")
        for act in view.get("activities") or []:
            events.extend(self._activity_events(act))
        for m in view.get("messages") or []:
            ev = self._message_event(m, root)
            if ev is not None:
                events.append(ev)
        events.extend(self._interaction_events(view.get("interaction")))
        status = str(view.get("status") or "")
        if status and status != self._status:
            self._status = status
            if status not in TERMINAL:
                events.append({"type": "status", "status": "waiting" if status == "waiting" else "thinking"})
        return events

    def _activity_events(self, act: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        aid = str(act.get("id") or "")
        kind = str(act.get("kind") or "")
        rid = str(act.get("run_id") or "")
        if aid not in self._started:
            self._started.add(aid)
            if kind == "llm":
                self._cycles += 1
                out.append({"type": "cycle", "iteration": self._cycles, "run_id": rid})
            elif kind == "tool":
                tools = _tool_entries(act)
                if tools:
                    out.append({"type": "tool_started", "tools": tools, "run_id": rid})
            elif kind == "tool_policy":
                out.append({"type": "tool_policy_decision", "decision": act.get("decision"), "tools": [
                    str(r.get("name") or "") for r in act.get("tool_calls") or []] or [str(act.get("name") or "")],
                    "revision": act.get("revision"), "set_by": act.get("set_by"), "run_id": rid,
                    "ts": str(act.get("started_at") or "")})
        for row in act.get("tool_calls") or []:
            st = str(row.get("status") or "")
            key = f"{aid}|{row.get('id')}"
            if st in ("running", "waiting") or key in self._tool_done:
                continue
            self._tool_done.add(key)
            meta = {"name": row.get("name"), "arguments": row.get("arguments"), "call_uid": row.get("id"),
                    "status": st, "run_id": rid}
            if row.get("decided_by"):
                meta["decided_by"] = row.get("decided_by")
            out.append({"type": "tool", "run_id": rid, "message": {
                "content": _result_text(row), "metadata": meta, "ts": str(act.get("ended_at") or "")}})
        if kind != "tool" and str(act.get("status") or "") == "failed" and f"{aid}|failed" not in self._tool_done:
            self._tool_done.add(f"{aid}|failed")
            out.append({"type": "error", "error": str(act.get("error") or f"{act.get('name') or kind} failed"), "run_id": rid})
        return out

    def _message_event(self, m: Dict[str, Any], root: str) -> Optional[Dict[str, Any]]:
        mid = str(m.get("id") or "")
        if not mid or mid in self._messages:
            return None
        self._messages.add(mid)
        if str(m.get("role") or "") != "assistant":
            return None
        text = str(m.get("text") or "")
        final = str(m.get("kind") or "") == "final"
        if not text.strip() and not final:
            return None
        rid = str(m.get("run_id") or root)
        meta = {"run_id": rid, "message_id": mid}
        if m.get("artifact_ids"):
            meta["artifact_ids"] = list(m.get("artifact_ids") or [])
        if final and m.get("repeats"):
            meta["repeats"] = m.get("repeats")
        ts = ""
        order = m.get("order")
        if isinstance(order, list) and order:
            ts = str(order[0] or "")
        return {"type": "assistant", "content": text, "final": final, "ts": ts, "run_id": rid, "meta": meta}

    def _interaction_events(self, it: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        key = str(it.get("wait_key") or "") if isinstance(it, dict) else ""
        if self._interaction and key != self._interaction:
            out.append({"type": "interaction_closed", "wait_key": self._interaction})
        self._interaction = key
        if not key or key in self._seen_interactions:
            return out
        self._seen_interactions.add(key)
        rid = str(it.get("run_id") or "")
        if it.get("kind") == "tool_approval":
            calls = [{"name": r.get("name"), "arguments": r.get("arguments"), "call_id": r.get("id")}
                     for r in it.get("tool_calls") or [] if isinstance(r, dict)]
            out.append({"type": "tool_request", "tool_calls": calls, "wait_key": key, "run_id": rid,
                        "step_id": str(it.get("step_id") or ""), "command": it.get("command")})
        else:
            ev = {"type": "ask_user", "prompt": str(it.get("prompt") or "Input required:"), "wait_key": key,
                  "run_id": rid, "step_id": str(it.get("step_id") or ""), "command": it.get("command")}
            if isinstance(it.get("choices"), list):
                ev["choices"] = list(it["choices"])
            if it.get("allow_free_text") is not None:
                ev["allow_free_text"] = bool(it.get("allow_free_text"))
            out.append(ev)
        return out


def _transient(exc: BaseException) -> bool:
    if isinstance(exc, GatewayStreamIdle):
        return True
    if isinstance(exc, GatewayHttpError):
        status = int(getattr(exc, "status", 0) or 0)
        return status in {408, 425, 429} or status >= 500
    return isinstance(exc, (urllib.error.URLError, ConnectionError, OSError))


def follow_run_view(
    *,
    gateway: Any,
    run_id: str,
    on_view: Callable[[Dict[str, Any]], None],
    should_stop: Callable[[], bool],
    on_offline: Optional[Callable[[str], None]] = None,
    on_online: Optional[Callable[[], None]] = None,
    max_transient_failures: int = 5,
    stream_idle_s: float = 30.0,
) -> ViewFold:
    """Follow one run tree's view until the gateway says `done` (or `should_stop`).

    `on_view(view)` runs after every change of the copy, the first GET included. A reconnect
    sends the copy's cursor as `Last-Event-ID`: the gateway answers with nothing, one delta, or
    the whole view, so nothing is skipped or folded twice."""
    fold = ViewFold()
    status, _etag, body = gateway.get_run_view(run_id=run_id)
    if body is None:
        raise GatewayHttpError("get_run_view answered without a view", status=status)
    fold.apply_frame("view", body)
    on_view(fold.view or {})

    class _Stop:
        def is_set(self) -> bool:
            try:
                return bool(should_stop())
            except Exception:
                return False

    failures = 0
    offline = False
    finished = {"done": False}

    def _frame(event: str, _id: str, data: Dict[str, Any]) -> Optional[bool]:
        nonlocal failures, offline
        failures = 0
        if offline:
            offline = False
            if on_online:
                on_online()
        if event == "done":
            finished["done"] = True
            return False
        if fold.apply_frame(event, data):
            on_view(fold.view or {})
        return None

    while not should_stop() and not finished["done"]:
        try:
            gateway.stream_run_view(run_id=run_id, on_frame=_frame, last_event_id=fold.token or None,
                                    stop_signal=_Stop(), timeout_s=stream_idle_s, max_idle_s=stream_idle_s)
        except Exception as exc:  # noqa: BLE001
            if not _transient(exc):
                raise
            failures += 1
            if failures > max_transient_failures:
                raise
            if not offline:
                offline = True
                if on_offline:
                    on_offline(str(exc))
            deadline = time.monotonic() + min(8.0, 0.5 * (2 ** (failures - 1)))
            while time.monotonic() < deadline and not should_stop():
                time.sleep(0.1)
            continue
        if not finished["done"] and str((fold.view or {}).get("status") or "") in TERMINAL:
            # The stream closed without `done` on a finished tree: one GET settles the copy.
            st, _e, body = gateway.get_run_view(run_id=run_id, etag=f'"{fold.token}"' if fold.token else None)
            if st != 304 and body is not None and fold.apply_frame("view", body):
                on_view(fold.view or {})
            break
    return fold


__all__ = ["ViewFold", "ViewProjector", "ViewOutOfSync", "follow_run_view", "TERMINAL"]
