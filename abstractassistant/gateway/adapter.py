"""
Translate gateway ledger records into AbstractAssistant UI events.

This adapter is intentionally minimal and mirrors the behavior of
`abstractcode/web` for status/messages/waits.
"""

from typing import Any, Dict, List, Optional

from .events import (
    event_name_from_wait_key,
    extract_emit_event,
    extract_flow_end_output,
    extract_tool_calls_from_wait,
    extract_wait_from_record,
    is_tool_approval_wait,
    _coerce_wait_reason,
    normalize_ui_event_name,
    parse_status_payload,
)
from .history_seed import tool_messages_from_record
from .types import StepRecord, WaitState

# Activity-view texts are bounded so a single verbose cycle cannot bloat the
# UI event stream; the transcript/ledger keep the full text.
_ACTIVITY_TEXT_MAX_CHARS = 4000


def _bounded_activity_text(text: str) -> str:
    value = str(text or "")
    if len(value) <= _ACTIVITY_TEXT_MAX_CHARS:
        return value
    #[WARNING:TRUNCATION] bounded for the live activity view; the ledger keeps the full text
    return value[: _ACTIVITY_TEXT_MAX_CHARS - 1] + "…"


class GatewayEventAdapter:
    """Adapter that maps ledger records into AbstractAssistant event dicts."""

    def __init__(self) -> None:
        # Wait-occurrence bookkeeping. A wait_key is STABLE across repeated
        # waits from the same node (e.g. "tool_calls:<run_id>:act" for EVERY
        # tool-approval batch of that agent run), so a key alone cannot
        # identify one question: dedup by key alone silently swallowed the
        # second approval request and the run parked forever while the UI
        # showed a running tool (live stall, 2026-07-28). One occurrence =
        # one waiting ledger record = one step_id.
        #
        # Two mark families with different lifetimes:
        # - seeded marks: occurrences known answered BEFORE this stream
        #   (reattach replay). Never cleared — a terminal replay must stay
        #   silent through its resume records.
        # - live marks: occurrences emitted during this stream. Cleared by
        #   the wait's resume record — the question was answered, and the
        #   NEXT wait on the same key is a new question that must prompt.
        # A mark of "" means "occurrence unknown" and suppresses the key
        # wholesale (synthetic rehydration records carry no step_id).
        self._seeded_wait_marks: Dict[str, set] = {}
        self._live_wait_marks: Dict[str, set] = {}
        self._seen_tool_call_ids: set[str] = set()
        self._cycles_by_run: Dict[str, int] = {}

    def seed_seen_wait_keys(self, wait_keys) -> None:
        """Mark whole wait keys as already-handled (every occurrence).

        Wholesale suppression: prefer ``seed_handled_wait_occurrences`` so a
        pending repeat of the same key can still prompt."""
        for key in wait_keys or []:
            k = str(key or "").strip()
            if k:
                self._seeded_wait_marks.setdefault(k, set()).add("")

    def seed_handled_wait_occurrences(self, occurrences) -> None:
        """Mark specific wait occurrences (wait_key, step_id) as handled so a
        reattach replay does not re-open already-answered dialogs, while a
        NEW occurrence of the same wait_key still prompts."""
        for pair in occurrences or []:
            try:
                key, step = pair
            except Exception:
                continue
            k = str(key or "").strip()
            if not k:
                continue
            self._seeded_wait_marks.setdefault(k, set()).add(str(step or "").strip())

    def _wait_already_handled(self, wait_key: str, step_id: str) -> bool:
        for marks in (self._seeded_wait_marks.get(wait_key), self._live_wait_marks.get(wait_key)):
            if not marks:
                continue
            if "" in marks:
                return True
            if step_id and step_id in marks:
                return True
            if not step_id:
                # Unknown occurrence (synthetic record): anything already
                # handled for this key is the same pending question.
                return True
        return False

    def seed_tool_call_ids(self, call_ids: List[str]) -> None:
        for cid in call_ids:
            c = str(cid or "").strip()
            if c:
                self._seen_tool_call_ids.add(c)

    def handle_record(self, rec: StepRecord | None) -> List[Dict[str, Any]]:
        """Return UI events derived from a single ledger record."""
        events: List[Dict[str, Any]] = []
        record_ts = ""
        record_step_id = ""
        if isinstance(rec, dict):
            record_ts = str(rec.get("ended_at") or rec.get("started_at") or "").strip()
            record_step_id = str(rec.get("step_id") or "").strip()

        # Realtime run activity (2026-07-10): STARTED records carry the full effect payload
        # BEFORE execution, so the user can see what the agent is doing while the call is
        # still in flight — a reasoning cycle beginning, or a tool launching with its args.
        # Previously only tool RESULTS surfaced; the in-flight phase was a silent "thinking".
        if isinstance(rec, dict):
            raw_status = rec.get("status")
            status0 = str(getattr(raw_status, "value", raw_status) or "").strip().lower()
            effect = rec.get("effect") if isinstance(rec.get("effect"), dict) else {}
            etype = str(effect.get("type") or "").strip().lower()
            if status0 == "started" and etype == "llm_call" and str(rec.get("node_id") or "") == "reason":
                rid = str(rec.get("run_id") or "")
                n = int(self._cycles_by_run.get(rid, 0)) + 1
                self._cycles_by_run[rid] = n
                cycle_event: Dict[str, Any] = {"type": "cycle", "iteration": n}
                if record_ts:
                    # Ledger timestamp of the cycle start (live activity
                    # durations are computed ONLY from ledger timestamps).
                    cycle_event["ts"] = record_ts
                events.append(cycle_event)
            elif status0 == "completed" and etype == "llm_call" and str(rec.get("node_id") or "") == "reason":
                # The model's ACTUAL output for this cycle (its intermediate
                # "thinking" between tool rounds) lives on the COMPLETED
                # record's result — never on the STARTED payload, whose
                # `messages` are the conversation INTO the model (echoing the
                # user's prompt as "thinking" was the 2026-07-17 dishonesty).
                rid = str(rec.get("run_id") or "")
                n = int(self._cycles_by_run.get(rid, 0))
                result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
                content = str(result.get("content") or "").strip()
                reasoning = ""
                raw_reasoning = result.get("reasoning")
                if isinstance(raw_reasoning, str) and raw_reasoning.strip():
                    reasoning = raw_reasoning.strip()
                else:
                    meta0 = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
                    if isinstance(meta0.get("reasoning"), str):
                        reasoning = str(meta0.get("reasoning")).strip()
                if content or reasoning:
                    events.append(
                        {
                            "type": "cycle_result",
                            "iteration": max(1, n),
                            "content": _bounded_activity_text(content),
                            "reasoning": _bounded_activity_text(reasoning),
                            "ts": record_ts,
                        }
                    )
            elif status0 == "started" and etype == "tool_calls":
                payload0 = effect.get("payload") if isinstance(effect.get("payload"), dict) else {}
                tools: List[Dict[str, Any]] = []
                # STARTED records carry started_at; ended_at is the fallback for
                # a replayed record. Only a real ledger timestamp is forwarded.
                tool_started_ts = str(rec.get("started_at") or rec.get("ended_at") or "").strip()
                for tc in payload0.get("tool_calls") or []:
                    if not (isinstance(tc, dict) and str(tc.get("name") or "").strip()):
                        continue
                    args = tc.get("arguments")
                    try:
                        preview = str(args) if args else ""
                    except Exception:
                        preview = ""
                    if len(preview) > 120:
                        #[WARNING:TRUNCATION] bounded args preview for the activity line
                        preview = preview[:119] + "…"
                    full_args = ""
                    try:
                        full_args = _bounded_activity_text(str(args) if args else "")
                    except Exception:
                        full_args = ""
                    tool_entry: Dict[str, Any] = {
                        "name": str(tc.get("name")).strip(),
                        "arguments_preview": preview,
                        "arguments_text": full_args,
                    }
                    # Identity + timing + structured args for the live activity
                    # model: results are matched by call_id (FIFO by name when
                    # absent) and titles use the raw arguments, not their repr.
                    call_id = str(
                        tc.get("call_id") or tc.get("id") or tc.get("runtime_call_id") or ""
                    ).strip()
                    if call_id:
                        tool_entry["call_id"] = call_id
                    if tool_started_ts:
                        tool_entry["ts"] = tool_started_ts
                    if isinstance(args, (dict, str)) and args:
                        tool_entry["arguments"] = args
                    tools.append(tool_entry)
                if tools:
                    events.append({"type": "tool_started", "tools": tools})

        emit = extract_emit_event(rec)
        if emit:
            name, payload, _scope = emit
            if name == "abstract.status":
                parsed = parse_status_payload(payload)
                text = str(parsed.get("text") or "").strip()
                if text and text.lower() not in {"ready", "completed"}:
                    events.append({"type": "status", "status": text})
            elif name == "abstract.message":
                text = ""
                if isinstance(payload, str):
                    text = payload
                elif isinstance(payload, dict):
                    text = str(payload.get("text") or payload.get("message") or "")
                text = text.strip()
                if text:
                    # For now, render messages as assistant content in the tray UI.
                    events.append({"type": "assistant", "content": text, "final": False, "ts": record_ts})
            elif name == "abstract.media.image.generated" and isinstance(payload, dict):
                artifact = payload.get("image_artifact")
                if isinstance(artifact, dict) and str(artifact.get("$artifact") or "").strip():
                    prompt = str(payload.get("prompt") or "").strip()
                    meta = {"image_artifact": dict(artifact), "generated_media": dict(payload)}
                    events.append(
                        {
                            "type": "assistant",
                            "content": "Generated image" + (f": {prompt}" if prompt else ""),
                            "meta": meta,
                            "final": False,
                            "ts": record_ts,
                        }
                    )

        # A resume record means the wait it names was ANSWERED: clear the
        # live marks so the next wait on the same (stable) key re-prompts
        # instead of being deduped into a permanent stall. Seeded marks
        # stay — a terminal replay must not re-open its historical waits.
        if isinstance(rec, dict):
            eff0 = rec.get("effect") if isinstance(rec.get("effect"), dict) else {}
            if str(eff0.get("type") or "").strip().lower() == "resume":
                payload0 = eff0.get("payload") if isinstance(eff0.get("payload"), dict) else {}
                resumed_key = str(payload0.get("wait_key") or "").strip()
                if resumed_key:
                    self._live_wait_marks.pop(resumed_key, None)

        wait = extract_wait_from_record(rec)
        if wait:
            events.extend(self._wait_events(wait, step_id=record_step_id))

        for msg in tool_messages_from_record(rec or {}):
            meta = msg.get("metadata") if isinstance(msg, dict) else None
            call_id = str(meta.get("call_id") or "").strip() if isinstance(meta, dict) else ""
            if call_id:
                if call_id in self._seen_tool_call_ids:
                    continue
                self._seen_tool_call_ids.add(call_id)
            events.append({"type": "tool", "message": msg})

        out = extract_flow_end_output(rec)
        if out:
            events.append(
                {
                    "type": "assistant",
                    "content": out.get("response", ""),
                    "meta": out.get("meta"),
                    "final": True,
                    "ts": record_ts,
                }
            )

        if rec and isinstance(rec, dict):
            status = str(rec.get("status") or "").strip().lower()
            if status == "failed":
                err = str(rec.get("error") or rec.get("result", {}).get("error") or "step failed").strip()
                events.append({"type": "error", "error": err})

        return events

    def _wait_events(self, wait: WaitState, *, step_id: str = "") -> List[Dict[str, Any]]:
        """Convert a wait state into UI events.

        Dedup is per OCCURRENCE (wait_key + waiting-record step_id), never
        per key alone: the runtime reuses stable keys for repeated waits
        from the same node, and a key-only dedup swallows the second
        question forever."""
        events: List[Dict[str, Any]] = []
        wait_key = str(wait.get("wait_key") or "").strip()
        step = str(step_id or "").strip()
        reason = _coerce_wait_reason(wait.get("reason"))
        if wait_key and self._wait_already_handled(wait_key, step):
            return []

        def _mark_handled() -> None:
            if wait_key:
                self._live_wait_marks.setdefault(wait_key, set()).add(step)

        tool_calls = extract_tool_calls_from_wait(wait)
        approval_wait = is_tool_approval_wait(wait)
        if tool_calls or approval_wait:
            request = {"type": "tool_request", "tool_calls": tool_calls, "wait_key": wait_key}
            if step:
                request["step_id"] = str(step)
            events.append(request)
            _mark_handled()
            return events

        if reason == "event":
            ev_name = normalize_ui_event_name(event_name_from_wait_key(wait_key))
            if ev_name == "abstract.ask":
                prompt = str(wait.get("prompt") or "Input required:").strip()
                ask = {"type": "ask_user", "prompt": prompt, "wait_key": wait_key}
                if step:
                    ask["step_id"] = str(step)
                events.append(ask)
                _mark_handled()
                return events

        if reason == "user":
            prompt = str(wait.get("prompt") or "Input required:").strip()
            ask = {"type": "ask_user", "prompt": prompt, "wait_key": wait_key}
            if step:
                ask["step_id"] = str(step)
            events.append(ask)
            _mark_handled()

        return events
