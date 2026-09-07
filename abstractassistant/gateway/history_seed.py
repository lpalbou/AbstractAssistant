"""Gateway history bundle → session message seed helpers.

This mirrors `abstractcode/web` history bundle seeding so the tray UI can
rehydrate durable runs after restart without losing context.
"""

from __future__ import annotations

import json
import warnings
from typing import Any, Callable, Dict, List, Optional

from .run_stats import parse_usage_summary, stats_from_history_bundle


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


def _attachment_metadata(attachments: Any) -> Optional[Dict[str, Any]]:
    """Message metadata carrying a turn's attachment refs, or None.

    Both keys are written because the transcript renderer reads either one.
    """
    items = [item for item in (attachments or []) if isinstance(item, dict)]
    if not items:
        return None
    return {"attachments": items, "media": items}


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
            # The runtime is the durable record of a turn's attachments: each
            # one is an artifact ref it can serve forever. Dropping them here
            # is why reopening an old session showed no attachments at all.
            _push_user(
                out,
                content=prompt,
                ts=ts_user,
                run_id=run_id,
                meta=_attachment_metadata(turn.get("attachments")),
            )
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
            eff = rec.get("effect") if isinstance(rec.get("effect"), dict) else {}
            eff_type = str(eff.get("type") or "").strip()
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


def _pick_textish(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _decode_artifact_payload(value: Any) -> Any:
    raw = value
    if isinstance(value, tuple) and value:
        raw = value[0]
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = bytes(raw).decode("utf-8")
        except Exception:
            text = bytes(raw).decode("utf-8", errors="replace")
    else:
        text = str(raw or "")
    if not text.strip():
        return ""
    try:
        return json.loads(text)
    except Exception:
        return text


def _terminal_output_record(bundle: Dict[str, Any], *, run_id: str) -> Optional[Dict[str, Any]]:
    rid = str(run_id or "").strip()
    if not rid:
        return None
    ledger = bundle.get("ledgers", {}).get(rid) if isinstance(bundle.get("ledgers"), dict) else None
    items = ledger.get("items") if isinstance(ledger, dict) else None
    if not isinstance(items, list):
        return None
    for item in reversed(items):
        rec = item.get("record") if isinstance(item, dict) else None
        result = rec.get("result") if isinstance(rec, dict) else None
        if isinstance(result, dict) and result.get("output") is not None:
            return rec
    return None


def _resolve_output_payload(
    output: Any,
    *,
    run_id: str,
    artifact_loader: Optional[Callable[[str, str], Any]],
) -> Any:
    if not isinstance(output, dict):
        return output
    artifact_id = output.get("$artifact") or output.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id.strip() or artifact_loader is None:
        return output
    try:
        return _decode_artifact_payload(artifact_loader(str(run_id or "").strip(), artifact_id.strip()))
    except Exception:
        return output


def _extract_response_text(value: Any) -> str:
    if isinstance(value, dict):
        return (
            _pick_textish(value.get("answer"))
            or _pick_textish(value.get("response"))
            or _pick_textish(value.get("message"))
            or _pick_textish(value.get("text"))
            or _pick_textish(value.get("content"))
        )
    return _pick_textish(value)


def recover_missing_assistant_from_history_bundle(
    bundle: Dict[str, Any],
    *,
    run_id: Optional[str] = None,
    artifact_loader: Optional[Callable[[str, str], Any]] = None,
) -> Optional[Dict[str, Any]]:
    rid = str(run_id or bundle.get("root_run_id") or "").strip()
    if not rid:
        return None

    root_rec = _terminal_output_record(bundle, run_id=rid)
    if not isinstance(root_rec, dict):
        return None
    root_result = root_rec.get("result") if isinstance(root_rec.get("result"), dict) else {}
    root_output = _resolve_output_payload(
        root_result.get("output"),
        run_id=rid,
        artifact_loader=artifact_loader,
    )
    root_text = _extract_response_text(root_output)
    root_meta = dict(root_output.get("meta")) if isinstance(root_output, dict) and isinstance(root_output.get("meta"), dict) else {}
    if root_text:
        meta = dict(root_meta)
        meta.setdefault("kind", "recovered_history_answer")
        meta.setdefault("run_id", rid)
        return {
            "role": "assistant",
            "content": root_text,
            "ts": _ts_from_record(root_rec),
            "run_id": rid,
            "metadata": meta or None,
        }

    sub_run_id = ""
    if isinstance(root_meta, dict):
        sub_run_id = str(root_meta.get("sub_run_id") or root_meta.get("subRunId") or "").strip()
    if not sub_run_id and isinstance(root_output, dict):
        scratchpad = root_output.get("scratchpad")
        if isinstance(scratchpad, dict):
            sub_run_id = str(scratchpad.get("sub_run_id") or scratchpad.get("subRunId") or "").strip()
    if not sub_run_id:
        return None

    sub_rec = _terminal_output_record(bundle, run_id=sub_run_id)
    if not isinstance(sub_rec, dict):
        return None
    sub_result = sub_rec.get("result") if isinstance(sub_rec.get("result"), dict) else {}
    sub_output_raw = sub_result.get("output")
    artifact_id = ""
    if isinstance(sub_output_raw, dict):
        artifact_id = str(sub_output_raw.get("$artifact") or sub_output_raw.get("artifact_id") or "").strip()
    sub_output = _resolve_output_payload(
        sub_output_raw,
        run_id=sub_run_id,
        artifact_loader=artifact_loader,
    )
    sub_text = _extract_response_text(sub_output)
    if not sub_text:
        return None

    meta = dict(root_meta)
    meta["kind"] = "recovered_history_answer"
    meta["run_id"] = rid
    meta["sub_run_id"] = sub_run_id
    if artifact_id:
        meta["artifact_id"] = artifact_id
    return {
        "role": "assistant",
        "content": sub_text,
        "ts": _ts_from_record(root_rec),
        "run_id": rid,
        "metadata": meta,
    }


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
    artifact_loader: Optional[Callable[[str, str], Any]] = None,
) -> List[Dict[str, Any]]:
    """Return a list of session message dicts from a history bundle."""
    if not isinstance(bundle, dict):
        warnings.warn("#REPLAY_DEGRADED: history bundle was not a dict; returning empty seed")
        return []

    from_turns = _seed_from_session_turns(bundle)
    if from_turns:
        extra_tools = _seed_tool_cards(bundle, include_tool_calls_for_run_id or "") if include_tool_calls_for_run_id else []
        out = from_turns + extra_tools
    else:
        from_tg = _seed_from_telegram_ledgers(bundle)
        extra_tools = _seed_tool_cards(bundle, include_tool_calls_for_run_id or "") if include_tool_calls_for_run_id else []
        if from_tg:
            out = from_tg + extra_tools
        else:
            root_prompt = str(bundle.get("input_data", {}).get("prompt") or bundle.get("input_data", {}).get("context", {}).get("task") or "").strip()
            if not root_prompt:
                if extra_tools:
                    out = extra_tools
                else:
                    warnings.warn("#REPLAY: history bundle had no session turns; using empty seed")
                    out = []
            else:
                out = [{"role": "user", "content": root_prompt, "ts": _now_iso(), "run_id": str(bundle.get("root_run_id") or "").strip() or None}] + extra_tools

    target_run_id = str(include_tool_calls_for_run_id or bundle.get("root_run_id") or "").strip()
    has_assistant = any(
        isinstance(msg, dict)
        and str(msg.get("role") or "") == "assistant"
        and str(msg.get("run_id") or "").strip() == target_run_id
        and str(msg.get("content") or "").strip()
        for msg in out
    )
    if not has_assistant:
        recovered = recover_missing_assistant_from_history_bundle(
            bundle,
            run_id=target_run_id or None,
            artifact_loader=artifact_loader,
        )
        if isinstance(recovered, dict):
            out.append(recovered)
    _attach_bundle_stats(out, bundle, run_id=target_run_id)
    return out


def _usage_numbers(stats: Any) -> tuple:
    """(input, output, total) from a stats dict, zeros when absent."""
    if not isinstance(stats, dict):
        return (0, 0, 0)
    usage = stats.get("usage")
    if not isinstance(usage, dict):
        usage = stats.get("tokens") if isinstance(stats.get("tokens"), dict) else {}
    parsed = parse_usage_summary(usage) or {}
    return (
        int(parsed.get("input_tokens") or 0),
        int(parsed.get("output_tokens") or 0),
        int(parsed.get("total_tokens") or 0),
    )


def _stats_are_richer(fresh: Dict[str, Any], existing: Dict[str, Any]) -> bool:
    """Only replace stored stats when the recomputed ones say strictly MORE.

    Answers folded before the run tree was walked recorded the ROOT run only:
    no tokens, no tool calls, one llm_call — while the agent subrun underneath
    had done twelve cycles and twenty tool calls. That fold was fixed forward,
    but seeding SKIPPED any message already carrying stats, so those rows were
    wrong permanently. Re-deriving heals them; comparing first is what stops a
    re-derivation from ever making a good row worse.
    """
    new_tokens, old_tokens = _usage_numbers(fresh), _usage_numbers(existing)
    try:
        new_tools = int(fresh.get("tool_calls") or 0)
        old_tools = int(existing.get("tool_calls") or 0)
    except Exception:
        new_tools = old_tools = 0
    return sum(new_tokens) > sum(old_tokens) or new_tools > old_tools


def _attach_bundle_stats(messages: List[Dict[str, Any]], bundle: Dict[str, Any], *, run_id: str) -> None:
    """Attach ledger-derived answer stats to this bundle's assistant message.

    Seeding REPLACES the local session cache, so without this the stats a live
    follower attached to the final answer would be wiped by the stats-less
    seeded copy (and recovered answers would never carry stats at all). Only
    the target run's messages are touched: other session turns keep their own
    `_repl.stats` from the gateway.

    A message that ALREADY carries stats is re-derived and kept only if the
    fresh figures are richer — see `_stats_are_richer`. Skipping those rows
    outright is what froze the old root-only folds as permanently wrong.
    """
    rid = str(run_id or "").strip()
    if not rid:
        return
    stats: Optional[Dict[str, Any]] = None
    computed = False
    for msg in messages:
        if not isinstance(msg, dict) or str(msg.get("role") or "") != "assistant":
            continue
        if str(msg.get("run_id") or "").strip() != rid:
            continue
        meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
        existing = meta.get("_assistant_stats")
        if not computed:
            computed = True
            try:
                stats = stats_from_history_bundle(bundle)
            except Exception as e:
                warnings.warn(f"#REPLAY_DEGRADED: failed to derive run stats from bundle: {e}")
                stats = None
        if not isinstance(stats, dict):
            return
        if isinstance(existing, dict) and not _stats_are_richer(stats, existing):
            # Never downgrade a row that is already at least as good.
            continue
        meta = dict(meta)
        meta["_assistant_stats"] = {"run_id": rid, **stats}
        msg["metadata"] = meta
