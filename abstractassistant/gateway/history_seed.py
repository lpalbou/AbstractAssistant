"""Gateway history bundle → session message seed helpers.

This mirrors `abstractcode/web` history bundle seeding so the tray UI can
rehydrate durable runs after restart without losing context.
"""

from __future__ import annotations

import json
import warnings
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    try:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return ""


def _ts_from_record(rec: Any) -> str:
    ended = str(rec.get("ended_at") or "").strip() if isinstance(rec, dict) else ""
    started = str(rec.get("started_at") or "").strip() if isinstance(rec, dict) else ""
    return ended or started or _now_iso()


def _push_user(out: List[Dict[str, Any]], *, content: str, ts: str, run_id: Optional[str] = None, meta: Any = None) -> None:
    text = str(content or "")
    if not text.strip():
        return
    msg: Dict[str, Any] = {"role": "user", "content": text, "ts": str(ts or _now_iso())}
    if run_id:
        msg["run_id"] = run_id
    if meta is not None:
        msg["metadata"] = meta
    out.append(msg)


def _push_assistant(out: List[Dict[str, Any]], *, content: str, ts: str, run_id: Optional[str] = None, meta: Any = None) -> None:
    text = str(content or "")
    if not text.strip():
        return
    msg: Dict[str, Any] = {"role": "assistant", "content": text, "ts": str(ts or _now_iso())}
    if run_id:
        msg["run_id"] = run_id
    if meta is not None:
        msg["metadata"] = meta
    out.append(msg)


def _seed_from_session_turns(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    turns = bundle.get("session", {}).get("turns") if isinstance(bundle.get("session"), dict) else None
    if not isinstance(turns, list) or not turns:
        return []
    out: List[Dict[str, Any]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        run_id = str(turn.get("run_id") or "").strip() or None
        ts_user = str(turn.get("created_at") or turn.get("updated_at") or "").strip() or _now_iso()
        ts_asst = str(turn.get("updated_at") or turn.get("created_at") or "").strip() or _now_iso()
        prompt = str(turn.get("prompt") or "")
        answer = str(turn.get("answer") or "")
        answer_meta = turn.get("answer_meta")
        stats = turn.get("stats")
        if prompt.strip():
            _push_user(out, content=prompt, ts=ts_user, run_id=run_id)
        if answer.strip():
            meta: Dict[str, Any] = {"_repl": {}}
            if isinstance(answer_meta, dict):
                meta["_repl"].update(answer_meta)
            if stats is not None:
                meta["_repl"]["stats"] = stats
            _push_assistant(out, content=answer, ts=ts_asst, run_id=run_id, meta=meta)
    return out


def _extract_telegram_from_resume_payload(obj: Any) -> Optional[Dict[str, Any]]:
    try:
        telegram = obj.get("effect", {}).get("payload", {}).get("payload", {}).get("payload", {}).get("telegram")
        if not isinstance(telegram, dict):
            return None
        text = str(telegram.get("text") or "").strip()
        if not text:
            return None
        attachments = obj.get("effect", {}).get("payload", {}).get("payload", {}).get("payload", {}).get("attachments")
        meta = {"_kind": "telegram_in", "telegram": dict(telegram)}
        if isinstance(attachments, list):
            meta["attachments"] = attachments
        return {"text": text, "meta": meta}
    except Exception:
        return None


def _extract_telegram_out_from_tool_calls_record(obj: Any) -> List[str]:
    out: List[str] = []
    try:
        eff = obj.get("effect") if isinstance(obj, dict) else None
        if not isinstance(eff, dict) or str(eff.get("type") or "") != "tool_calls":
            return out
        status = str(obj.get("status") or "").strip().lower()
        if status != "completed":
            return out
        results = obj.get("result", {}).get("results") if isinstance(obj.get("result"), dict) else None
        if not isinstance(results, list) or not results:
            return out
        payload = eff.get("payload") if isinstance(eff.get("payload"), dict) else {}
        tool_calls = payload.get("tool_calls")
        if not isinstance(tool_calls, list):
            return out
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            name = str(tc.get("name") or "").strip()
            if name != "send_telegram_message":
                continue
            args = tc.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            text = str((args or {}).get("text") or "").strip() if isinstance(args, dict) else ""
            if text:
                out.append(text)
    except Exception:
        return out
    return out


def _seed_from_telegram_ledgers(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    ledgers = bundle.get("ledgers")
    if not isinstance(ledgers, dict):
        return []
    events: List[Dict[str, Any]] = []
    for run_id, ledger in ledgers.items():
        items = ledger.get("items") if isinstance(ledger, dict) else None
        if not isinstance(items, list):
            continue
        for it in items:
            rec = it.get("record") if isinstance(it, dict) else None
            if not isinstance(rec, dict):
                continue
            eff_type = str(rec.get("effect", {}).get("type") or "").strip()
            if eff_type == "resume":
                hit = _extract_telegram_from_resume_payload(rec)
                if hit:
                    events.append(
                        {
                            "ts": _ts_from_record(rec),
                            "kind": "in",
                            "text": hit["text"],
                            "run_id": str(run_id),
                            "meta": hit.get("meta"),
                        }
                    )
            if eff_type == "tool_calls":
                outs = _extract_telegram_out_from_tool_calls_record(rec)
                for text in outs:
                    events.append(
                        {
                            "ts": _ts_from_record(rec),
                            "kind": "out",
                            "text": text,
                            "run_id": str(run_id),
                            "meta": {"_kind": "telegram_out"},
                        }
                    )
    if not events:
        return []
    events.sort(key=lambda e: str(e.get("ts") or ""))
    out: List[Dict[str, Any]] = []
    for ev in events:
        if ev.get("kind") == "in":
            _push_user(out, content=ev.get("text", ""), ts=str(ev.get("ts") or ""), run_id=ev.get("run_id"), meta=ev.get("meta"))
        else:
            _push_assistant(out, content=ev.get("text", ""), ts=str(ev.get("ts") or ""), run_id=ev.get("run_id"), meta=ev.get("meta"))
    return out


def _truncate_output(text: str, *, limit: int = 8000) -> str:
    raw = str(text or "")
    if len(raw) <= int(limit):
        return raw
    return f"{raw[: int(limit)]}\n#TRUNCATION: tool output preview exceeded {limit} chars"


def _extract_artifacts_from_output(obj: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []

    def _walk(val: Any) -> None:
        if isinstance(val, dict):
            if "$artifact" in val and isinstance(val.get("$artifact"), str) and str(val.get("$artifact")).strip():
                entry = {"artifact_id": str(val.get("$artifact")).strip()}
                if isinstance(val.get("filename"), str) and str(val.get("filename")).strip():
                    entry["filename"] = str(val.get("filename")).strip()
                if isinstance(val.get("content_type"), str) and str(val.get("content_type")).strip():
                    entry["content_type"] = str(val.get("content_type")).strip()
                out.append(entry)
            for v in val.values():
                _walk(v)
        elif isinstance(val, list):
            for item in val:
                _walk(item)

    _walk(obj)
    return out


def tool_messages_from_record(rec: Dict[str, Any], *, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Convert a tool_calls ledger record into tool message dicts."""
    if not isinstance(rec, dict):
        return []
    eff = rec.get("effect")
    if not isinstance(eff, dict) or str(eff.get("type") or "") != "tool_calls":
        return []
    status = str(rec.get("status") or "").strip().lower()
    if status != "completed":
        return []

    payload = eff.get("payload") if isinstance(eff.get("payload"), dict) else {}
    tool_calls = payload.get("tool_calls")
    results = rec.get("result", {}).get("results") if isinstance(rec.get("result"), dict) else None
    if not isinstance(tool_calls, list):
        return []
    results = results if isinstance(results, list) else []
    by_call_id: Dict[str, Any] = {}
    for res in results:
        if not isinstance(res, dict):
            continue
        cid = str(res.get("call_id") or res.get("id") or "").strip()
        if cid:
            by_call_id[cid] = res

    out: List[Dict[str, Any]] = []
    rid = str(run_id or rec.get("run_id") or "").strip() or None
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        name = str(tc.get("name") or "").strip()
        if not name:
            continue
        if name in {"send_telegram_message", "send_telegram_artifact"}:
            continue
        call_id = str(tc.get("call_id") or tc.get("id") or tc.get("runtime_call_id") or "").strip()
        args = tc.get("arguments")
        res = by_call_id.get(call_id) if call_id else None
        success = bool(res.get("success")) if isinstance(res, dict) and "success" in res else None
        error = str(res.get("error") or "").strip() if isinstance(res, dict) else ""
        output = res.get("output") if isinstance(res, dict) else None
        artifacts = _extract_artifacts_from_output(output) if output is not None else []
        try:
            if output is None:
                output_preview = ""
            elif isinstance(output, str):
                output_preview = output
            else:
                output_preview = json.dumps(output, indent=2, ensure_ascii=False)
        except Exception:
            output_preview = ""
        output_preview = _truncate_output(output_preview)
        meta = {
            "name": name,
            "call_id": call_id or None,
            "success": success,
            "error": error or None,
            "arguments": args,
            "output_preview": output_preview,
        }
        if artifacts:
            meta["artifacts"] = artifacts
        if rid:
            meta["run_id"] = rid
        msg: Dict[str, Any] = {
            "role": "tool",
            "content": output_preview,
            "ts": _ts_from_record(rec),
            "metadata": meta,
        }
        if rid:
            msg["run_id"] = rid
        out.append(msg)
    return out


def _seed_tool_cards(bundle: Dict[str, Any], run_id: str) -> List[Dict[str, Any]]:
    rid = str(run_id or "").strip()
    if not rid:
        return []
    ledger = bundle.get("ledgers", {}).get(rid) if isinstance(bundle.get("ledgers"), dict) else None
    items = ledger.get("items") if isinstance(ledger, dict) else None
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for it in items:
        rec = it.get("record") if isinstance(it, dict) else None
        if not isinstance(rec, dict):
            continue
        out.extend(tool_messages_from_record(rec, run_id=rid))
    return out


def seed_messages_from_history_bundle(
    bundle: Dict[str, Any],
    *,
    include_tool_calls_for_run_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return a list of session message dicts from a history bundle."""
    if not isinstance(bundle, dict):
        warnings.warn("#FALLBACK: history bundle was not a dict; returning empty seed")
        return []

    from_turns = _seed_from_session_turns(bundle)
    if from_turns:
        extra_tools = _seed_tool_cards(bundle, include_tool_calls_for_run_id or "") if include_tool_calls_for_run_id else []
        return from_turns + extra_tools

    from_tg = _seed_from_telegram_ledgers(bundle)
    extra_tools = _seed_tool_cards(bundle, include_tool_calls_for_run_id or "") if include_tool_calls_for_run_id else []
    if from_tg:
        return from_tg + extra_tools

    root_prompt = str(bundle.get("input_data", {}).get("prompt") or bundle.get("input_data", {}).get("context", {}).get("task") or "").strip()
    if not root_prompt:
        if extra_tools:
            return extra_tools
        warnings.warn("#FALLBACK: history bundle had no session turns; using empty seed")
        return []
    return [{"role": "user", "content": root_prompt, "ts": _now_iso(), "run_id": str(bundle.get("root_run_id") or "").strip() or None}] + extra_tools
