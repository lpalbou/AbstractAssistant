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

import json
import re
import threading
import time
import urllib.error
import warnings
from typing import Any, Callable, Dict, List, Optional, Set

from abstractruntime.replay import ReplayView, apply_delta

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


_MEDIA_KEYS = frozenset({"image_artifact", "video_artifact", "audio_artifact", "music_artifact"})
_SKIP_TOOLS = frozenset({"send_telegram_message", "send_telegram_artifact"})
# Activity-view texts are bounded so one verbose call cannot bloat the event stream.
_ACTIVITY_TEXT_MAX_CHARS = 4000


def _bounded(text: str, limit: int = _ACTIVITY_TEXT_MAX_CHARS) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    #[WARNING:TRUNCATION] bounded for the live activity view; the view keeps the full value
    return value[: limit - 1] + "…"


def _tool_entries(act: Dict[str, Any]) -> List[Dict[str, Any]]:
    """`tool_started` entries (the run-activity card pairs them with results by `call_uid`)."""
    out = []
    for row in act.get("tool_calls") or []:
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        args = row.get("arguments")
        try:
            text = str(args) if args else ""
        except Exception:
            text = ""
        entry: Dict[str, Any] = {
            "name": str(row.get("name")).strip(),
            "call_uid": f"{act.get('id')}#{row.get('id')}",
            "arguments_preview": _bounded(text, 120),
            "arguments_text": _bounded(text),
        }
        if isinstance(args, (dict, str)) and args:
            entry["arguments"] = args
        if act.get("started_at"):
            entry["ts"] = str(act.get("started_at"))
        out.append(entry)
    return out


def _tool_message(row: Dict[str, Any], act: Dict[str, Any]) -> Dict[str, Any]:
    """A finished tool row as the transcript's tool message (the shape the session seed writes)."""
    from .history_seed import _extract_artifacts_from_output, _truncate_output

    out = row.get("output")
    try:
        preview = "" if out is None else (out if isinstance(out, str) else json.dumps(out, indent=2, ensure_ascii=False))
    except Exception:
        preview = str(out)
    preview = _truncate_output(preview)
    st = str(row.get("status") or "")
    rid = str(act.get("run_id") or "")
    meta: Dict[str, Any] = {
        "name": str(row.get("name") or "tool"),
        "call_id": str(row.get("id") or "") or None,
        "call_uid": f"{act.get('id')}#{row.get('id')}",
        "success": st == "completed",
        "error": str(row.get("error") or "") or None,
        "arguments": row.get("arguments"),
        "output_preview": preview,
        "status": st,
        "run_id": rid,
    }
    if row.get("decided_by"):
        meta["decided_by"] = row.get("decided_by")
    artifacts = _extract_artifacts_from_output(out) if out is not None else []
    if artifacts:
        meta["artifacts"] = artifacts
    return {"role": "tool", "content": preview, "ts": str(act.get("ended_at") or ""), "metadata": meta, "run_id": rid}


def stats_from_view(view: Dict[str, Any]) -> Dict[str, Any]:
    """The answer's stats block (`_assistant_stats`) from the view: usage, calls, duration."""
    from .run_stats import compact_tool_call_for_ui, parse_iso_ms

    usage = view.get("usage") if isinstance(view.get("usage"), dict) else {}
    lo = hi = None
    details: List[Dict[str, Any]] = []
    for act in view.get("activities") or []:
        for key in ("started_at", "ended_at"):
            ms = parse_iso_ms(act.get(key))
            if ms is not None:
                lo = ms if lo is None else min(lo, ms)
                hi = ms if hi is None else max(hi, ms)
        if act.get("kind") == "tool":
            for row in act.get("tool_calls") or []:
                if str(row.get("status") or "") in ("completed", "failed", "denied"):
                    details.append(compact_tool_call_for_ui({
                        "name": row.get("name"), "arguments": row.get("arguments"), "call_uid": row.get("id"),
                        "success": row.get("status") == "completed", "error": row.get("error")}))
    return {
        "duration_ms": max(0, hi - lo) if lo is not None and hi is not None else 0,
        "llm_calls": int(usage.get("llm_calls") or 0),
        "tool_calls": len(details),
        "tool_call_details": details,
        "usage": {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens", "total_tokens")},
    }


def finished_llm_calls(view: Dict[str, Any]) -> Set[str]:
    """Step ids of llm calls whose durable record the view holds (live text for them is over)."""
    out: Set[str] = set()
    for act in view.get("activities") or []:
        if act.get("kind") == "llm" and str(act.get("status") or "") in TERMINAL:
            out.update(str(s) for s in act.get("step_ids") or [] if s)
    return out


# Output fields that hold the run's own bookkeeping, never something to show the person: the
# agent scratchpad and node traces carry the offloaded system prompt, provider request and step
# list (`{"$artifact"}` refs the runtime offloads by size). QA 2026-10-28 (b): two such refs
# showed as raw-id chips under an automation's answer and could not be opened.
_INTERNAL_PATH_PARTS = frozenset({"scratchpad", "node_traces", "node_trace", "trace", "traces"})


def _is_internal_path(path: str) -> bool:
    parts = [p for p in re.split(r"[.\[\]]", str(path or "")) if p and not p.isdigit()]
    return any(p in _INTERNAL_PATH_PARTS or p.startswith("_") for p in parts)


def _view_artifacts(view: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The view's artifact entries by id (`path`: where it was first referenced, `run_id`: its run)."""
    return {str(a.get("id") or ""): a for a in view.get("artifacts") or [] if isinstance(a, dict) and a.get("id")}


def _media_meta(meta: Dict[str, Any], artifact_ids: Any, arts: Dict[str, Dict[str, Any]], *, source: str = "") -> None:
    """Name each artifact by the output field that held it (`image_artifact` -> an image tile);
    the palette reads these keys for the answer's media.

    Only what the person can use is attached. A listed ref under the run's bookkeeping
    (`_is_internal_path`) is left out; a kept ref carries the run that owns it, which is the
    run the gateway serves it through (a child run's artifact is not visible through the root).

    A ref the view does not list has no path: for a final message folded from the ledger
    (`source == "ledger"`) that only happens to a ref deeper than the runtime's listing walk,
    i.e. inside the bookkeeping (AbstractRuntime backlog 0862), so it is left out; for a final
    built from the run snapshot (`run_output`: no completion record was folded, nothing of the
    output is listed) it is kept as before, opened through the message's run."""
    for art in artifact_ids or []:
        entry = arts.get(str(art))
        ref: Dict[str, Any] = {"$artifact": str(art)}
        if entry is None:
            if source == "ledger":
                warnings.warn(f"#REPLAY: final message artifact {art!r} is not listed by the replay view; not shown")
                continue
            path = ""
        else:
            path = str(entry.get("path") or "")
            if _is_internal_path(path):
                continue
            if entry.get("run_id"):
                ref["run_id"] = str(entry["run_id"])
        parts = re.split(r"[.\[\]]", path)
        field = next((k for k in reversed(parts) if k and not k.isdigit()), "")
        if field in _MEDIA_KEYS and field not in meta:
            meta[field] = ref
        elif "artifact" not in meta:
            meta["artifact"] = ref
            meta["artifact_id"] = str(art)
        else:
            meta.setdefault("media", []).append(ref)


def final_fallback_event(view: Dict[str, Any], output: Any = None) -> Dict[str, Any]:
    """A completed run whose view has no final message (its output had no text: media only, or
    nothing): an empty final answer carrying the output's artifacts, so the worker's recovery
    (an output artifact's text, "Generated image ready.", an empty-answer notice) runs.

    `output` is the run's own output (`GET /runs/{id}`): its media fields are taken as they are
    (with their content type). The view names an artifact by its EARLIEST reference, so an image
    a tool made and the run then returned is not under `output` there."""
    root = str(view.get("root_run_id") or "")
    if isinstance(output, dict):
        meta0: Dict[str, Any] = {"run_id": root}
        for key in (*sorted(_MEDIA_KEYS), "artifact", "artifact_ref"):
            ref = output.get(key)
            if isinstance(ref, dict) and str(ref.get("$artifact") or "").strip():
                meta0["artifact" if key == "artifact_ref" else key] = dict(ref)
        if isinstance(meta0.get("artifact"), dict):
            meta0.setdefault("artifact_id", str(meta0["artifact"]["$artifact"]))
        if len(meta0) > 1:
            return {"type": "assistant", "content": "", "final": True, "ts": "", "run_id": root, "meta": meta0}
    arts = _view_artifacts(view)
    ids = [a for a, e in arts.items() if str(e.get("path") or "").split(".", 1)[0].split("[", 1)[0] == "output"
           and str(e.get("run_id") or "") == root]
    meta: Dict[str, Any] = {"run_id": root}
    _media_meta(meta, ids, arts)
    return {"type": "assistant", "content": "", "final": True, "ts": "", "run_id": root, "meta": meta}


class ViewProjector:
    """Turns successive copies of a view into the UI events the panels render.

    Each event is emitted once per identity: a message id, an activity id, a tool row's
    (activity, call) and final status, an interaction's wait key."""

    def __init__(self) -> None:
        self._status = ""
        self._display: Dict[str, str] = {}
        self._messages: Set[str] = set()
        self._started: Set[str] = set()
        self._tool_done: Set[str] = set()
        self._cycles: Dict[str, int] = {}
        # Interactions by OCCURRENCE (run, wait key, seq of its waiting record): the runtime
        # reuses a node's wait key for every question it asks, so a key alone would swallow
        # the second question (the 2026-07-28 stall). `_shown`: occurrence -> wait key.
        self._shown: Dict[str, str] = {}
        self._asked: Set[str] = set()
        self._assistant_ids: Set[str] = set()
        self.final_shown = False
        self.error_shown = False

    def suppress_history(self, view: Dict[str, Any]) -> None:
        """Mark everything the view holds as already shown, except an open interaction (an
        attach: the transcript comes from the session seed; the open question must still be
        asked)."""
        for m in view.get("messages") or []:
            # The final answer still passes: the worker appends it only when the seeded
            # transcript lacks it (a session seed can miss the last turn).
            if str(m.get("kind") or "") != "final":
                self._messages.add(str(m.get("id") or ""))
        for r in view.get("runs") or []:
            self._display[str(r.get("run_id") or "")] = str(r.get("display_status") or "")
        for act in view.get("activities") or []:
            aid = str(act.get("id") or "")
            if str(act.get("status") or "") in ("running", "waiting"):
                continue  # still going: its start is shown so its result pairs with it
            self._started.add(aid)
            if act.get("kind") == "llm":
                rid = str(act.get("run_id") or "")
                self._cycles[rid] = self._cycles.get(rid, 0) + 1
            if str(act.get("status") or "") == "failed":
                self._tool_done.add(f"{aid}|failed")
            for row in act.get("tool_calls") or []:
                if str(row.get("status") or "") not in ("running", "waiting"):
                    self._tool_done.add(f"{aid}|{row.get('id')}")

    def project(self, view: Dict[str, Any]) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        root = str(view.get("root_run_id") or "")
        self._root = root
        for r in view.get("runs") or []:
            rid = str(r.get("run_id") or "")
            text = str(r.get("display_status") or "")
            if text and text != self._display.get(rid) and str(r.get("status") or "") not in TERMINAL:
                events.append({"type": "status", "status": text, "run_id": rid})
            self._display[rid] = text
        for act in view.get("activities") or []:
            events.extend(self._activity_events(act))
        arts = _view_artifacts(view)
        for m in view.get("messages") or []:
            ev = self._message_event(m, root, arts)
            if ev is not None:
                events.append(ev)
        events.extend(self._interaction_events(view.get("interaction"), view.get("open_waits")))
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
                self._cycles[rid] = self._cycles.get(rid, 0) + 1
                ev: Dict[str, Any] = {"type": "cycle", "iteration": self._cycles[rid], "run_id": rid}
                if act.get("started_at"):
                    ev["ts"] = str(act.get("started_at"))
                out.append(ev)
            elif kind == "tool":
                tools = _tool_entries(act)
                if tools:
                    out.append({"type": "tool_started", "tools": tools, "run_id": rid})
            elif kind == "tool_policy":
                policy = act.get("policy") if isinstance(act.get("policy"), dict) else {}
                set_by = policy.get("set_by") if isinstance(policy.get("set_by"), dict) else {}
                out.append({
                    "type": "tool_policy_decision", "decision": str(act.get("decision") or ""),
                    "source": str(act.get("source") or ""),
                    "tools": [{"name": str(r.get("name") or ""), "call_id": str(r.get("id") or ""),
                               "matched": str(r.get("matched") or "")}
                              for r in act.get("tool_calls") or [] if isinstance(r, dict) and r.get("name")],
                    "set_by": str(set_by.get("user_id") or ""), "set_at": str(policy.get("set_at") or ""),
                    "run_id": rid, "ts": str(act.get("started_at") or "")})
        for row in act.get("tool_calls") or []:
            st = str(row.get("status") or "")
            key = f"{aid}|{row.get('id')}"
            if kind != "tool" or st in ("running", "waiting") or key in self._tool_done:
                continue
            self._tool_done.add(key)
            if str(row.get("name") or "") in _SKIP_TOOLS:
                continue
            out.append({"type": "tool", "run_id": rid, "message": _tool_message(row, act)})
        if kind != "tool" and str(act.get("status") or "") == "failed" and f"{aid}|failed" not in self._tool_done:
            self._tool_done.add(f"{aid}|failed")
            if rid == getattr(self, "_root", ""):
                self.error_shown = True  # a child's failed step may be recovered: not the run's reason
            out.append({"type": "error", "error": str(act.get("error") or f"{act.get('name') or kind} failed"), "run_id": rid})
        return out

    def _message_event(self, m: Dict[str, Any], root: str, arts: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        mid = str(m.get("id") or "")
        if not mid or mid in self._messages:
            return None
        self._messages.add(mid)
        role = str(m.get("role") or "")
        kind = str(m.get("kind") or "")
        # Assistant turns, and a workflow's `abstract.message` (a system `event` message).
        if not (role == "assistant" or (role == "system" and kind == "event")):
            return None
        if kind == "question":
            return None  # asked through the interaction (the ask dialog), not as a reply
        text = str(m.get("text") or "")
        final = kind == "final"
        if not text.strip() and not final:
            return None
        rid = str(m.get("run_id") or root)
        meta: Dict[str, Any] = {"run_id": rid, "message_id": mid}
        _media_meta(meta, m.get("artifact_ids"), arts, source=str(m.get("source") or ""))
        ev_extra: Dict[str, Any] = {}
        if final and m.get("repeats"):
            meta["repeats"] = m.get("repeats")
            if str(m.get("repeats")) in self._assistant_ids:
                ev_extra["repeats_shown"] = True  # the same text is already in the transcript
        if final:
            self.final_shown = True
        elif role == "assistant":
            self._assistant_ids.add(mid)
        ts = ""
        order = m.get("order")
        if isinstance(order, list) and order:
            ts = str(order[0] or "")
        return {"type": "assistant", "content": text, "final": final, "ts": ts, "run_id": rid, "meta": meta, **ev_extra}

    @staticmethod
    def _occurrence(w: Dict[str, Any]) -> str:
        return f"{w.get('run_id') or ''}|{w.get('wait_key') or ''}|{w.get('seq') or 0}"

    def _interaction_events(self, it: Any, open_waits: Any) -> List[Dict[str, Any]]:
        """Close every shown wait that is no longer open anywhere in the tree (`open_waits`),
        then ask the view's interaction (the newest open one) if this occurrence was never
        asked. An older wait that is still open stays on screen while a newer one is asked."""
        out: List[Dict[str, Any]] = []
        still_open = {self._occurrence(w) for w in open_waits or [] if isinstance(w, dict) and w.get("person_facing")}
        if isinstance(it, dict):
            still_open.add(self._occurrence(it))
        for occ in [o for o in self._shown if o not in still_open]:
            key = self._shown.pop(occ)
            out.append({"type": "interaction_closed", "wait_key": key, "run_id": occ.split("|", 1)[0]})
        if not isinstance(it, dict) or not it.get("wait_key"):
            return out
        occ = self._occurrence(it)
        if occ in self._shown or occ in self._asked:
            return out
        key = str(it.get("wait_key"))
        self._shown[occ] = key
        self._asked.add(occ)
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


def _retrying(call: Callable[[], Any], *, should_stop: Callable[[], bool], attempts: int = 4) -> Any:
    """`call()` with a short backoff on transient transport errors (a blip right after a run
    starts must not end its follow); the last error, or a non-transient one, is raised."""
    for n in range(attempts):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001
            if not _transient(exc) or n == attempts - 1 or should_stop():
                raise
            _sleep(min(4.0, 0.5 * (2 ** n)), should_stop)
    raise AssertionError("unreachable")


def _sleep(seconds: float, should_stop: Callable[[], bool]) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline and not should_stop():
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


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
    the whole view, so nothing is skipped or folded twice. Consecutive transport failures are
    counted until a stream connects again; a stream that ends without `done` (a proxy closing
    an idle connection) is reconnected after a backoff, never in a tight loop."""
    fold = ViewFold()
    status, _etag, body = _retrying(lambda: gateway.get_run_view(run_id=run_id), should_stop=should_stop)
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

    state = {"failures": 0, "offline": False, "done": False, "quiet": 0}

    def _opened() -> None:
        state["failures"] = 0
        if state["offline"]:
            state["offline"] = False
            if on_online:
                on_online()

    def _frame(event: str, _id: str, data: Dict[str, Any]) -> Optional[bool]:
        state["quiet"] = 0
        if event == "done":
            state["done"] = True
            return False
        if fold.apply_frame(event, data):
            on_view(fold.view or {})
        return None

    while not should_stop() and not state["done"]:
        try:
            gateway.stream_run_view(run_id=run_id, on_frame=_frame, last_event_id=fold.token or None,
                                    stop_signal=_Stop(), timeout_s=stream_idle_s, max_idle_s=stream_idle_s,
                                    on_open=_opened)
        except Exception as exc:  # noqa: BLE001
            if not _transient(exc):
                raise
            state["failures"] += 1
            if state["failures"] > max_transient_failures:
                raise
            if not state["offline"]:
                state["offline"] = True
                if on_offline:
                    on_offline(str(exc))
            _sleep(min(8.0, 0.5 * (2 ** (state["failures"] - 1))), should_stop)
            continue
        if state["done"] or should_stop():
            break
        if str((fold.view or {}).get("status") or "") in TERMINAL:
            # The stream closed without `done` on a finished tree: one GET settles the copy.
            st, _e, body = gateway.get_run_view(run_id=run_id, etag=f'"{fold.token}"' if fold.token else None)
            if st != 304 and body is not None and fold.apply_frame("view", body):
                on_view(fold.view or {})
            break
        state["quiet"] += 1
        _sleep(min(5.0, 0.25 * (2 ** min(state["quiet"], 5))), should_stop)
    return fold


def follow_run_ledger_locally(
    *,
    gateway: Any,
    run_id: str,
    on_view: Callable[[Dict[str, Any]], None],
    should_stop: Callable[[], bool],
    on_offline: Optional[Callable[[str], None]] = None,
    on_online: Optional[Callable[[], None]] = None,
    poll_s: float = 0.5,
    page_size: int = 2000,
    max_transient_failures: int = 5,
) -> ViewFold:
    """A gateway without the view routes (before AbstractGateway 0.17.0): read the run tree's
    ledgers (`GET /runs/{id}/ledger`) and snapshots (`GET /runs/{id}`) and fold them with
    AbstractRuntime's own reducer (`ReplayView.apply`), here instead of on the gateway. The same
    view, the same projection; only where the fold runs differs.

    A pass reads every run's new records and the snapshots of runs not yet finished, then folds
    them; the read positions move only once the fold succeeded (a failed pass is read again,
    and folding by seq is idempotent). The view is rendered when its cursor token changes."""
    rv = ReplayView(str(run_id))
    consumed: Dict[str, int] = {}
    finished: Set[str] = set()  # runs whose snapshot is terminal: not re-read
    fold = ViewFold()
    failures = 0
    offline = False
    drained_terminal = False
    root_input: Optional[Dict[str, Any]] = None
    while not should_stop():
        try:
            grew = True
            while grew:  # a fold can discover a child run: read its ledger before rendering
                grew = False
                records: List[Dict[str, Any]] = []
                snaps: Dict[str, Any] = {}
                positions: Dict[str, int] = {}
                for rid in rv.run_ids or [str(run_id)]:
                    at = consumed.get(rid, 0)
                    while True:
                        page = gateway.get_ledger(run_id=rid, after=at, limit=page_size)
                        page = page if isinstance(page, dict) else {}
                        items = [r for r in page.get("items") or [] if isinstance(r, dict)]
                        records.extend(items)
                        at = int(page.get("next_after") or at + len(items))
                        if len(items) < page_size:
                            break
                    positions[rid] = at
                    if rid in finished:
                        continue
                    snap = gateway.get_run(run_id=rid)
                    if isinstance(snap, dict) and snap:
                        snap = dict(snap, run_id=str(snap.get("run_id") or rid))
                        if rid == str(run_id):
                            # The run summary carries no input: the view's prompt message needs it.
                            if root_input is None:
                                data = gateway.get_run_input_data(run_id=rid)
                                root_input = data.get("input_data") if isinstance(data, dict) else {}
                            snap["input_data"] = root_input or {}
                        snaps[rid] = snap
                before = set(rv.run_ids)
                rv.apply(records, runs_by_id=snaps)
                consumed.update(positions)
                for rid, snap in snaps.items():
                    if str(snap.get("status") or "").lower() in TERMINAL:
                        finished.add(rid)
                grew = bool(set(rv.run_ids) - before)
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
            _sleep(min(8.0, 0.5 * (2 ** (failures - 1))), should_stop)
            continue
        failures = 0
        if offline:
            offline = False
            if on_online:
                on_online()
        token = str(rv.cursor.get("token") or "")
        if fold.view is None or token != fold.token:
            fold.apply_frame("view", rv.to_json())
            on_view(fold.view or {})
        if rv.is_terminal():
            if drained_terminal:
                break
            drained_terminal = True  # one more pass: the terminal record can precede the last appends
            continue
        _sleep(poll_s, should_stop)
    return fold


class LiveText:
    """The reply being written, until the view stream carries it.

    The view holds only committed state; a run started with `_runtime.stream` also sends
    `llm.delta` / `llm.delta_end` frames (contract S) on `GET /runs/{root}/ledger/stream`, for
    the root and every run below it. This thread reads that stream for those frames only (its
    `step` rows are the view's business and are skipped) and hands them to `on_delta` as the
    palette's `assistant_delta*` events. Each (re)connect first sends `assistant_delta_reset`
    (the gateway then re-sends a snapshot of every reply still open). A failure here never ends
    the run's follow: the committed message still arrives through the view. Stopped by `stop()`.

    Replace with the view stream's own ephemeral text once the runtime and gateway ship it."""

    def __init__(self, *, gateway: Any, run_id: str, on_delta: Callable[[Dict[str, Any]], None],
                 after: int = 0, idle_s: float = 30.0) -> None:
        self._gateway = gateway
        self._run_id = str(run_id)
        self._on_delta = on_delta
        self._after = max(0, int(after))
        self._idle_s = float(idle_s)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=f"live-text-{self._run_id[:8]}", daemon=True)
        self.problem = ""

    def start(self) -> "LiveText":
        self._thread.start()
        return self

    def stop(self, join_s: float = 2.0) -> None:
        self._stop.set()
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(join_s)

    def _emit(self, ev: Dict[str, Any]) -> None:
        if self._stop.is_set():
            return  # stopped: nothing reaches the palette after the follow has ended
        try:
            self._on_delta(ev)
        except Exception as exc:  # noqa: BLE001
            if not self.problem:
                self.problem = f"live reply handler failed: {exc}"
                warnings.warn(f"#FALLBACK: {self.problem} (run {self._run_id})")

    def _loop(self) -> None:
        from .live_deltas import ASSISTANT_DELTA_RESET, to_ui_event

        def _step(ev: Dict[str, Any]) -> Optional[bool]:
            cur = ev.get("cursor") if isinstance(ev, dict) else None
            if isinstance(cur, int):
                self._after = max(self._after, cur)
            return None

        def _delta(name: str, data: Dict[str, Any]) -> None:
            ev = to_ui_event(name, data, run_id=self._run_id)  # a malformed frame warns and is skipped
            if ev is not None:
                self._emit(ev)

        def _open() -> None:
            self._emit({"type": ASSISTANT_DELTA_RESET, "run_id": self._run_id})

        backoff = 0.5
        while not self._stop.is_set():
            try:
                # No idle limit: a long tool run sends neither steps nor deltas, and that is not
                # a failure. `timeout_s` is the socket's (the gateway sends keep-alives).
                self._gateway.stream_ledger(run_id=self._run_id, after=self._after, on_step=_step,
                                            stop_signal=self._stop, timeout_s=self._idle_s,
                                            max_idle_s=None, on_delta=_delta, on_open=_open)
                # The gateway ended the stream (`done`, or a proxy closed it): reconnect calmly;
                # the follower stops this thread once the view says the run is done.
                backoff = 1.0
            except GatewayStreamIdle:
                backoff = 0.5  # a quiet socket: reconnect, nothing to report
            except Exception as exc:  # noqa: BLE001
                if not self.problem:
                    self.problem = f"live reply stream failed: {exc}"
                    warnings.warn(f"#FALLBACK: {self.problem} (run {self._run_id}); the reply appears when it is committed")
                backoff = min(backoff * 2.0, 5.0)
            self._stop.wait(backoff)


def follow_run(
    *,
    gateway: Any,
    run_id: str,
    on_view: Callable[[Dict[str, Any]], None],
    should_stop: Callable[[], bool],
    on_offline: Optional[Callable[[str], None]] = None,
    on_online: Optional[Callable[[], None]] = None,
    on_live: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_mode: Optional[Callable[[str], None]] = None,
) -> ViewFold:
    """Follow a run tree until it is done: the gateway's replay view when it serves one
    (`supports_replay_view`), else the same view folded here from its ledger. `on_mode("view"
    | "local")` says which, before anything renders. `on_live` gets the live reply text."""
    mode = "view" if _retrying(gateway.supports_replay_view, should_stop=should_stop) else "local"
    if on_mode:
        on_mode(mode)
    live: List[LiveText] = []

    def _on_view(view: Dict[str, Any]) -> None:
        if on_live and not live and str(view.get("status") or "") not in TERMINAL:
            # Start after the records the view already holds: the stream's step rows are skipped,
            # so there is no reason to read the run's history again.
            root_seq = _cursor_runs(view).get(str(run_id), 0)
            live.append(LiveText(gateway=gateway, run_id=run_id, on_delta=on_live, after=root_seq).start())
        on_view(view)

    try:
        follower = follow_run_view if mode == "view" else follow_run_ledger_locally
        return follower(gateway=gateway, run_id=run_id, on_view=_on_view, should_stop=should_stop,
                        on_offline=on_offline, on_online=on_online)
    finally:
        for lt in live:
            lt.stop()


__all__ = ["ViewFold", "ViewProjector", "ViewOutOfSync", "LiveText", "follow_run", "follow_run_view", "final_fallback_event",
           "follow_run_ledger_locally", "finished_llm_calls", "stats_from_view", "TERMINAL"]
