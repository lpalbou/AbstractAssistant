"""Helpers for reconstructing executed tool calls from runtime ledgers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set


def ledger_record_from_item(item: Any) -> Dict[str, Any]:
    """Normalize raw ledger pages and history-bundle ledger items."""
    if not isinstance(item, dict):
        return {}
    record = item.get("record")
    if isinstance(record, dict):
        return record
    return item


def extract_sub_run_ids_from_record(record: Dict[str, Any]) -> List[str]:
    """Find child run ids referenced by a ledger record."""
    found: List[str] = []
    seen: Set[str] = set()

    def _add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            found.append(text)

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key) in {"sub_run_id", "subRunId"}:
                    _add(item)
                    continue
                if str(key) == "wait_key":
                    text = str(item or "").strip()
                    if text.startswith("subworkflow:"):
                        _add(text.split(":", 1)[1])
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(record)
    return found


def extract_tool_call_details_from_record(record: Dict[str, Any], *, run_id: str = "") -> List[Dict[str, Any]]:
    """Return the executed tool calls from a completed tool_calls ledger record."""
    if not isinstance(record, dict):
        return []
    if str(record.get("status") or "").strip().lower() != "completed":
        return []
    effect = record.get("effect")
    if not isinstance(effect, dict) or str(effect.get("type") or "").strip() != "tool_calls":
        return []
    payload = effect.get("payload") if isinstance(effect.get("payload"), dict) else {}
    calls = payload.get("tool_calls")
    if not isinstance(calls, list):
        return []

    results = record.get("result", {}).get("results") if isinstance(record.get("result"), dict) else None
    results = results if isinstance(results, list) else []
    by_call_id: Dict[str, Dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        cid = str(result.get("call_id") or result.get("id") or "").strip()
        if cid:
            by_call_id[cid] = result

    out: List[Dict[str, Any]] = []
    rid = str(run_id or record.get("run_id") or "").strip()
    for index, call in enumerate(calls):
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "").strip()
        if not name:
            continue
        detail = dict(call)
        detail.setdefault("name", name)
        call_id = str(call.get("call_id") or call.get("id") or call.get("runtime_call_id") or "").strip()
        if call_id:
            detail["call_id"] = call_id
        if rid:
            detail["run_id"] = rid
        detail["ledger_index"] = index

        result = by_call_id.get(call_id) if call_id else None
        if isinstance(result, dict):
            if "success" in result:
                detail["success"] = bool(result.get("success"))
            error = str(result.get("error") or "").strip()
            if error:
                detail["error"] = error
        out.append(detail)
    return out


def extract_tool_call_details_from_ledger_items(items: Iterable[Any], *, run_id: str = "") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in items:
        record = ledger_record_from_item(item)
        if record:
            out.extend(extract_tool_call_details_from_record(record, run_id=run_id))
    return out


def extract_tool_call_details_from_scratchpad(scratchpad: Any, *, run_id: str = "") -> List[Dict[str, Any]]:
    """Fallback extraction from persisted agent scratchpad cycles."""
    if not isinstance(scratchpad, dict):
        return []
    cycles = scratchpad.get("cycles")
    if not isinstance(cycles, list):
        return []
    rid = str(run_id or "").strip()
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for cycle_index, cycle in enumerate(cycles):
        if not isinstance(cycle, dict):
            continue
        calls = cycle.get("tool_calls")
        if not isinstance(calls, list):
            continue
        for call_index, call in enumerate(calls):
            if not isinstance(call, dict):
                continue
            name = str(call.get("name") or "").strip()
            if not name:
                continue
            detail = dict(call)
            detail.setdefault("name", name)
            call_id = str(call.get("call_id") or call.get("id") or call.get("runtime_call_id") or "").strip()
            if call_id:
                detail["call_id"] = call_id
            if rid:
                detail["run_id"] = rid
            detail["scratchpad_cycle"] = cycle.get("i", cycle_index)
            detail["scratchpad_index"] = call_index
            key = call_id or f"{cycle_index}:{call_index}:{name}"
            if key in seen:
                continue
            seen.add(key)
            out.append(detail)
    return out
