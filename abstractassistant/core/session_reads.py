"""Qt-free projection of the Gateway's account-wide conversation read ledger.

Listing never consumes content. Only an explicit, visible transcript snapshot
may enqueue immutable revisions; a failed write retains both proof and unread.
"""

from __future__ import annotations

import threading
from typing import Any

TERMINAL = {"completed", "failed", "cancelled"}


def revision(run: dict) -> tuple[str, str, str] | None:
    sid, rid = str(run.get("session_id") or ""), str(run.get("run_id") or "")
    if not sid or not rid or run.get("session_kind") not in (None, "", "chat", "discussion"):
        return None
    if run.get("role") == "controller" or (
        run.get("parent_run_id") and run.get("role") != "occurrence"
    ):
        return None
    status = str(run.get("status") or "")
    return sid, rid, status if status in TERMINAL else "request"


def _events(body: Any) -> set[tuple[str, str, str]]:
    if not isinstance(body, dict) or not isinstance(body.get("items"), list) or body.get("more"):
        raise ValueError("The gateway returned incomplete read status.")
    result = set()
    for row in body["items"]:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("sequence"), int)
            or row["sequence"] < 1
            or not row.get("event_id")
            or not row.get("at")
            or not row.get("session_id")
            or not row.get("run_id")
            or row.get("status") not in TERMINAL | {"request"}
        ):
            raise ValueError("The gateway returned invalid read status.")
        result.add((row["session_id"], row["run_id"], row["status"]))
    return result


def _wire(values: set[tuple[str, str, str]]) -> list[dict]:
    return [dict(session_id=sid, run_id=rid, status=status) for sid, rid, status in sorted(values)]


class SessionReads:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.client = None
        self.runs: list[dict] = []
        self.seen: set[tuple[str, str, str]] = set()
        self.pending: set[tuple[str, str, str]] = set()
        self.loaded = False
        self.error = ""
        self.writing = False

    def refresh(self, client, runs: list[dict]) -> None:
        with self.lock:
            if self.client is not client:
                self.client = client
                self.seen = set()
                self.pending = set()
                self.loaded = False
                self.writing = False
            self.runs = [dict(r) for r in runs if revision(r)]
            ids = sorted({r["run_id"] for r in self.runs})
        try:
            seen = set()
            for start in range(0, len(ids), 100):
                page = client.session_reads(ids[start : start + 100])
                seen.update(_events(page))
            with self.lock:
                if self.client is not client:
                    return
                current = {revision(r) for r in self.runs}
                self.seen = (self.seen | seen) & current
                self.loaded = True
                self.error = ""
            self.flush(client)
        except Exception as exc:
            with self.lock:
                if self.client is client:
                    self.error = f"Read status unavailable: {exc}"

    def facts(self, sid: str) -> dict:
        with self.lock:
            runs = [r for r in self.runs if r["session_id"] == sid]
            return {
                "unread": self.loaded and any(revision(r) not in self.seen for r in runs),
                "needs_attention": any(
                    r.get("status") == "waiting"
                    and (
                        (r.get("waiting") or {}).get("reason") == "user"
                        or r.get("wait_reason") == "user"
                    )
                    for r in runs
                ),
            }

    def snapshot(self, sid: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.runs if r["session_id"] == sid]

    def displayed(
        self, sid: str, messages: list[dict], observed: list[dict] | None = None
    ) -> list[dict]:
        """Use only revisions represented in this successfully loaded transcript."""
        with self.lock:
            out = set()
            for run in self.runs if observed is None else observed:
                value = revision(run)
                if not value or value[0] != sid:
                    continue
                role = "user" if value[2] == "request" else "assistant"
                if any(
                    m.get("role") == role
                    and str(m.get("run_id") or (m.get("metadata") or {}).get("run_id") or "")
                    == value[1]
                    for m in messages
                ):
                    out.add(value)
            return _wire(out)

    def consume(self, client, receipts: list[dict]) -> bool:
        values = {revision(r) for r in receipts}
        if None in values:
            raise ValueError("Invalid displayed read receipt")
        with self.lock:
            if self.client is not client:
                return False
            self.pending.update(values - self.seen)
        return self.flush(client)

    def flush(self, client) -> bool:
        with self.lock:
            if self.client is not client or self.writing:
                return False
            self.writing = True
        try:
            while True:
                with self.lock:
                    if self.client is not client:
                        return False
                    batch = set(sorted(self.pending)[:100])
                if not batch:
                    return True
                response = client.mark_session_reads(_wire(batch))
                confirmed = _events(response)
                if not batch <= confirmed:
                    raise ValueError("The gateway did not confirm every read receipt.")
                with self.lock:
                    if self.client is not client:
                        return False
                    self.seen.update(confirmed)
                    self.pending.difference_update(batch)
                    self.error = ""
        except Exception as exc:
            with self.lock:
                if self.client is client:
                    self.error = f"Read status could not be saved: {exc}"
            return False
        finally:
            with self.lock:
                if self.client is client:
                    self.writing = False
