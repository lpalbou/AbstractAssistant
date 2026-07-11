"""Per-run answer statistics folded from runtime ledger records.

One fold, three consumers:

- ``GatewayWorker`` observes records live while following a run tree and
  attaches the aggregate to the final assistant message.
- History seeding derives the same aggregate from a run's history bundle
  (root + sub-run ledgers), so recovered/replayed answers carry stats too.
- The UI reads the resulting ``_assistant_stats`` metadata block.

Stats must aggregate across the WHOLE followed run tree: agent workflows
execute their llm_call/tool_calls effects in sub-runs while the final answer
event fires on the root run.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .tool_usage import extract_tool_call_details_from_record, ledger_record_from_item


def parse_iso_ms(raw: Any) -> Optional[int]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    return int(dt.timestamp() * 1000)


def parse_usage_summary(value: Any) -> Optional[Dict[str, int]]:
    if not isinstance(value, dict):
        return None

    def _num(*keys: str) -> Optional[int]:
        for key in keys:
            try:
                raw = value.get(key)
            except Exception:
                raw = None
            if raw in {None, ""}:
                continue
            try:
                return max(0, int(raw))
            except Exception:
                continue
        return None

    input_tokens = _num("input_tokens", "prompt_tokens", "prompt", "input", "in")
    output_tokens = _num("output_tokens", "completion_tokens", "completion", "output", "out")
    total_tokens = _num("total_tokens", "total")
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
    parsed = {
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }
    if parsed["input_tokens"] == 0 and parsed["output_tokens"] == 0 and parsed["total_tokens"] == 0:
        return None
    return parsed


def compact_tool_call_for_ui(
    call: Dict[str, Any],
    *,
    max_text_chars: int = 500,
    max_items: int = 24,
) -> Dict[str, Any]:
    """Bound a tool-call dict for storage in message metadata."""

    def _compact(value: Any) -> Any:
        if isinstance(value, str):
            text = value
            if len(text) <= max_text_chars:
                return text
            return f"{text[: max(0, max_text_chars - 3)]}..."
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            items = list(value.items())
            for key, item in items[:max_items]:
                out[str(key)] = _compact(item)
            if len(items) > max_items:
                out["_omitted_keys"] = len(items) - max_items
            return out
        if isinstance(value, list):
            out = [_compact(item) for item in value[:max_items]]
            if len(value) > max_items:
                out.append(f"... {len(value) - max_items} more")
            return out
        return value

    compacted = {
        "name": str(call.get("name") or "").strip(),
        "arguments": _compact(call.get("arguments")),
    }
    call_id = str(call.get("call_id") or call.get("id") or "").strip()
    if call_id:
        compacted["call_id"] = call_id
    # Preserve execution outcome: downstream stats (e.g. file activity) must be
    # able to exclude failed calls after the details are persisted/replayed.
    if isinstance(call.get("success"), bool):
        compacted["success"] = bool(call.get("success"))
    error = str(call.get("error") or "").strip()
    if error:
        compacted["error"] = _compact(error)
    return compacted


def _new_bucket() -> Dict[str, Any]:
    return {
        "duration_ms": 0,
        "llm_calls": 0,
        "tool_calls": 0,
        "tool_call_details": [],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "_min_ms": None,
        "_max_ms": None,
    }


def observe_record(stats_by_run: Dict[str, Dict[str, Any]], *, run_id: str, rec: Dict[str, Any]) -> None:
    """Fold one ledger record into the per-run stats buckets."""
    rid = str(run_id or "").strip()
    if not rid or not isinstance(rec, dict):
        return
    stats = stats_by_run.setdefault(rid, _new_bucket())
    started_ms = parse_iso_ms(rec.get("started_at"))
    ended_ms = parse_iso_ms(rec.get("ended_at"))
    # Fold both bounds so the duration is the true wall-clock span of observed
    # work, not just the distance between record completion times.
    for at_ms in (started_ms, ended_ms):
        if at_ms is None:
            continue
        min_ms = stats.get("_min_ms")
        max_ms = stats.get("_max_ms")
        stats["_min_ms"] = at_ms if min_ms is None else min(min_ms, at_ms)
        stats["_max_ms"] = at_ms if max_ms is None else max(max_ms, at_ms)
    if stats.get("_min_ms") is not None and stats.get("_max_ms") is not None:
        stats["duration_ms"] = max(0, int(stats["_max_ms"]) - int(stats["_min_ms"]))

    if str(rec.get("status") or "").strip().lower() != "completed":
        return
    effect = rec.get("effect") if isinstance(rec.get("effect"), dict) else {}
    effect_type = str(effect.get("type") or "").strip()
    result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
    if effect_type == "llm_call":
        stats["llm_calls"] = int(stats.get("llm_calls") or 0) + 1
        usage = result.get("usage") or result.get("token_usage") or result.get("tokens")
        if not isinstance(usage, dict):
            output = result.get("output")
            if isinstance(output, dict):
                usage = output.get("usage") or output.get("token_usage") or output.get("tokens")
        parsed = parse_usage_summary(usage)
        if parsed is not None:
            bucket = stats["usage"]
            bucket["input_tokens"] += parsed["input_tokens"]
            bucket["output_tokens"] += parsed["output_tokens"]
            bucket["total_tokens"] += parsed["total_tokens"] or (parsed["input_tokens"] + parsed["output_tokens"])
    elif effect_type == "tool_calls":
        calls = extract_tool_call_details_from_record(rec, run_id=rid)
        if calls:
            stats["tool_calls"] = int(stats.get("tool_calls") or 0) + len(calls)
            details = stats.setdefault("tool_call_details", [])
            if isinstance(details, list):
                details.extend(compact_tool_call_for_ui(dict(call)) for call in calls)


def aggregate_run_stats(
    stats_by_run: Dict[str, Dict[str, Any]],
    *,
    run_ids: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Sum per-run buckets into one answer-level stats block.

    Duration is the wall-clock span across all observed records (root and
    sub-runs overlap in time, so summing per-run durations would double
    count waiting time).
    """
    selected: List[Dict[str, Any]] = []
    if run_ids is None:
        selected = [bucket for bucket in stats_by_run.values() if isinstance(bucket, dict)]
    else:
        for rid in run_ids:
            bucket = stats_by_run.get(str(rid or "").strip())
            if isinstance(bucket, dict):
                selected.append(bucket)
    if not selected:
        return None

    out = _new_bucket()
    for bucket in selected:
        out["llm_calls"] += int(bucket.get("llm_calls") or 0)
        out["tool_calls"] += int(bucket.get("tool_calls") or 0)
        details = bucket.get("tool_call_details")
        if isinstance(details, list):
            out["tool_call_details"].extend(dict(call) for call in details if isinstance(call, dict))
        usage = bucket.get("usage") if isinstance(bucket.get("usage"), dict) else {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            try:
                out["usage"][key] += max(0, int(usage.get(key) or 0))
            except Exception:
                continue
        for bound_key, fold in (("_min_ms", min), ("_max_ms", max)):
            value = bucket.get(bound_key)
            if value is None:
                continue
            current = out[bound_key]
            out[bound_key] = value if current is None else fold(current, value)
    if out["_min_ms"] is not None and out["_max_ms"] is not None:
        out["duration_ms"] = max(0, int(out["_max_ms"]) - int(out["_min_ms"]))

    return {
        "duration_ms": int(out.get("duration_ms") or 0),
        "llm_calls": int(out.get("llm_calls") or 0),
        "tool_calls": int(out.get("tool_calls") or 0),
        "tool_call_details": list(out.get("tool_call_details") or []),
        "usage": dict(out.get("usage") or {}),
    }


def stats_from_history_bundle(bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fold every ledger in a run history bundle (root + sub-runs) into one
    answer-level stats block. Returns None when the bundle carries no ledgers."""
    if not isinstance(bundle, dict):
        return None
    ledgers = bundle.get("ledgers")
    if not isinstance(ledgers, dict) or not ledgers:
        return None
    stats_by_run: Dict[str, Dict[str, Any]] = {}
    for run_id, ledger in ledgers.items():
        items = ledger.get("items") if isinstance(ledger, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            rec = ledger_record_from_item(item)
            if rec:
                observe_record(stats_by_run, run_id=str(run_id), rec=rec)
    return aggregate_run_stats(stats_by_run)


def bundle_run_ids(bundle: Dict[str, Any]) -> List[str]:
    """All run ids covered by a history bundle (root first)."""
    if not isinstance(bundle, dict):
        return []
    out: List[str] = []
    root = str(bundle.get("root_run_id") or "").strip()
    if root:
        out.append(root)
    ledgers = bundle.get("ledgers")
    if isinstance(ledgers, dict):
        for rid in ledgers.keys():
            text = str(rid or "").strip()
            if text and text not in out:
                out.append(text)
    return out


__all__ = [
    "aggregate_run_stats",
    "bundle_run_ids",
    "compact_tool_call_for_ui",
    "observe_record",
    "parse_iso_ms",
    "parse_usage_summary",
    "stats_from_history_bundle",
]
