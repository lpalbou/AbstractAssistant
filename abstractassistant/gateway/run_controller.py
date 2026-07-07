"""
Gateway run controller for AbstractAssistant.

Encapsulates ledger replay + streaming and subworkflow follow logic.
"""

from __future__ import annotations

import time
import warnings
from typing import Callable, Dict, Optional, Tuple

from .client import GatewayStreamIdle
from .events import extract_wait_from_record


class GatewayRunController:
    """Gateway ledger replay/streaming controller (no UI dependencies)."""

    TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

    def __init__(
        self,
        *,
        gateway,
        debug: bool = False,
        stream_timeout_s: float = 15.0,
        stream_idle_s: float = 30.0,
        terminal_replay_max_wait_s: float = 2.0,
        terminal_replay_interval_s: float = 0.1,
    ) -> None:
        """Create a runtime-ledger follower.

        ``terminal_replay_max_wait_s`` is the bounded grace window used after
        Gateway reports a terminal run status. Runtime status can become
        terminal before the final ledger row is visible to this client, so the
        controller drains ledger pages until the cursor is quiet instead of
        trusting status alone.
        """
        self._gateway = gateway
        self._debug = bool(debug)
        self._stream_timeout_s = max(1.0, float(stream_timeout_s))
        self._stream_idle_s = max(5.0, float(stream_idle_s))
        self._terminal_replay_max_wait_s = max(0.0, float(terminal_replay_max_wait_s))
        self._terminal_replay_interval_s = max(0.01, float(terminal_replay_interval_s))
        self._idle_warned: set[str] = set()

    def get_run_status(self, *, run_id: str) -> str:
        try:
            info = self._gateway.get_run(run_id=run_id)
            if isinstance(info, dict):
                return str(info.get("status") or "").strip().lower()
        except Exception:
            return ""
        return ""

    def extract_subworkflow_run_id(self, rec: Dict[str, object]) -> str:
        wait = extract_wait_from_record(rec)
        if not isinstance(wait, dict):
            return ""
        reason = str(wait.get("reason") or "").strip().lower()
        if reason != "subworkflow":
            return ""
        details = wait.get("details")
        if isinstance(details, dict):
            sub_run_id = str(details.get("sub_run_id") or "").strip()
            if sub_run_id:
                return sub_run_id
        wait_key = str(wait.get("wait_key") or "").strip()
        if wait_key.startswith("subworkflow:"):
            return str(wait_key.split(":", 1)[1] or "").strip()
        return ""

    def replay_ledger(
        self,
        *,
        run_id: str,
        after: int,
        on_record: Callable[[str, Dict[str, object]], None],
    ) -> Tuple[int, str]:
        page = self._gateway.get_ledger(run_id=run_id, after=after, limit=2000)
        items = page.get("items") if isinstance(page, dict) else []
        next_after = int(page.get("next_after") or after)
        sub_run_id = ""
        if isinstance(items, list):
            for rec in items:
                if not isinstance(rec, dict):
                    continue
                on_record(run_id, rec)
                candidate = self.extract_subworkflow_run_id(rec)
                if candidate:
                    # Prefer the most recent subworkflow wait in this batch.
                    sub_run_id = candidate
        return next_after, sub_run_id

    def replay_ledger_until_quiet(
        self,
        *,
        run_id: str,
        after: int,
        on_record: Callable[[str, Dict[str, object]], None],
        max_wait_s: Optional[float] = None,
        interval_s: Optional[float] = None,
        quiet_passes: int = 2,
    ) -> Tuple[int, str]:
        """Replay a run ledger until no new rows appear on consecutive polls.

        This is the terminal-drain primitive. It exists because Gateway status
        and Runtime ledger visibility are separate observations; a terminal
        status is not sufficient proof that this client has replayed the final
        answer row.
        """
        wait_s = self._terminal_replay_max_wait_s if max_wait_s is None else float(max_wait_s)
        interval = self._terminal_replay_interval_s if interval_s is None else float(interval_s)
        deadline = time.monotonic() + max(0.0, wait_s)
        sleep_s = max(0.01, interval)
        required_quiet = max(1, int(quiet_passes))
        quiet_count = 0
        latest_sub_run_id = ""

        while True:
            before = int(after)
            after, sub_run_id = self.replay_ledger(run_id=run_id, after=after, on_record=on_record)
            if sub_run_id:
                latest_sub_run_id = sub_run_id
            if int(after) > before:
                quiet_count = 0
            else:
                quiet_count += 1
            if quiet_count >= required_quiet:
                return after, latest_sub_run_id
            if time.monotonic() >= deadline:
                return after, latest_sub_run_id
            time.sleep(sleep_s)

    def replay_terminal_ledger(
        self,
        *,
        run_id: str,
        after: int,
        on_record: Callable[[str, Dict[str, object]], None],
    ) -> Tuple[int, str]:
        """Drain final ledger rows before any caller treats a run as terminal."""
        return self.replay_ledger_until_quiet(run_id=run_id, after=after, on_record=on_record)

    def stream_run(
        self,
        *,
        run_id: str,
        after: int,
        seen_sub_runs: set[str],
        on_record: Callable[[str, Dict[str, object]], None],
        should_stop: Callable[[], bool],
        on_offline: Optional[Callable[[str], None]] = None,
        on_online: Optional[Callable[[], None]] = None,
    ) -> Tuple[int, str, bool]:
        backoff_s = 1.0
        while True:
            if should_stop():
                return after, "", False
            sub_run_id = ""

            def _on_step(ev: Dict[str, object]) -> Optional[bool]:
                nonlocal after, sub_run_id
                if not isinstance(ev, dict):
                    return True
                cursor = ev.get("cursor")
                if isinstance(cursor, int):
                    after = max(after, int(cursor))
                rec = ev.get("record")
                if not isinstance(rec, dict):
                    return True
                on_record(run_id, rec)
                if not sub_run_id:
                    candidate = self.extract_subworkflow_run_id(rec)
                    if candidate and candidate not in seen_sub_runs:
                        sub_run_id = candidate
                        return False
                return True

            try:
                self._gateway.stream_ledger(
                    run_id=run_id,
                    after=after,
                    on_step=_on_step,
                    timeout_s=self._stream_timeout_s,
                    max_idle_s=self._stream_idle_s,
                )
                if on_online:
                    on_online()
            except GatewayStreamIdle as e:
                if run_id not in self._idle_warned:
                    warnings.warn(f"#REPLAY: {e} for run {run_id}; polling run status")
                    self._idle_warned.add(run_id)
            except Exception as e:
                if self._debug:
                    print(f"❌ Gateway stream_ledger failed for {run_id}: {e}")
                if on_offline:
                    on_offline(str(e))
                raise e

            if sub_run_id:
                return after, sub_run_id, False

            status = self.get_run_status(run_id=run_id)
            if status in self.TERMINAL_STATUSES:
                after, sub_run_id = self.replay_terminal_ledger(
                    run_id=run_id,
                    after=after,
                    on_record=on_record,
                )
                if sub_run_id and sub_run_id not in seen_sub_runs:
                    return after, sub_run_id, False
                return after, "", True

            time.sleep(backoff_s)
            backoff_s = min(backoff_s * 2.0, 5.0)

    def follow_run(
        self,
        *,
        root_run_id: str,
        on_record: Callable[[str, Dict[str, object]], None],
        should_stop: Callable[[], bool],
        on_offline: Optional[Callable[[str], None]] = None,
        on_online: Optional[Callable[[], None]] = None,
    ) -> None:
        run_stack = [root_run_id]
        after_by_run: Dict[str, int] = {}
        seen_sub_runs: set[str] = set()

        while run_stack:
            if should_stop():
                break
            active_run_id = run_stack[-1]
            after = int(after_by_run.get(active_run_id, 0))

            after, sub_run_id = self.replay_ledger(run_id=active_run_id, after=after, on_record=on_record)
            after_by_run[active_run_id] = after

            if sub_run_id and sub_run_id not in seen_sub_runs:
                seen_sub_runs.add(sub_run_id)
                run_stack.append(sub_run_id)
                continue

            after, sub_run_id, completed = self.stream_run(
                run_id=active_run_id,
                after=after,
                seen_sub_runs=seen_sub_runs,
                on_record=on_record,
                should_stop=should_stop,
                on_offline=on_offline,
                on_online=on_online,
            )
            after_by_run[active_run_id] = after

            if sub_run_id and sub_run_id not in seen_sub_runs:
                seen_sub_runs.add(sub_run_id)
                run_stack.append(sub_run_id)
                continue

            if completed:
                run_stack.pop()
                continue
