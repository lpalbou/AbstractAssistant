"""
Gateway run controller for AbstractAssistant.

Encapsulates ledger replay + streaming and subworkflow follow logic.
"""

from __future__ import annotations

import time
import urllib.error
import warnings
from typing import Callable, Dict, Optional, Tuple

from .client import GatewayHttpError, GatewayStreamIdle
from .events import extract_wait_from_record
from .live_deltas import ASSISTANT_DELTA_RESET, to_ui_event


class _CallableStopSignal:
    """Adapt a ``should_stop`` callable to the client's stop-signal protocol."""

    def __init__(self, should_stop: Callable[[], bool]) -> None:
        self._should_stop = should_stop

    def is_set(self) -> bool:
        try:
            return bool(self._should_stop())
        except Exception:
            return False


class _RecordCallbackError(Exception):
    """Wraps an exception raised by the on_record callback.

    ``on_record`` runs inside ``stream_ledger``, so a callback failure surfaces
    through the same ``except`` as transport errors. Without this wrapper a
    disk/OS error escaping the callback would be misclassified as a transient
    transport error and retried past the already-advanced cursor, silently
    dropping the record. This type is never treated as transient.
    """


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
        max_transient_stream_failures: int = 5,
    ) -> None:
        """Create a runtime-ledger follower.

        ``terminal_replay_max_wait_s`` is the bounded grace window used after
        Gateway reports a terminal run status. Runtime status can become
        terminal before the final ledger row is visible to this client, so the
        controller drains ledger pages until the cursor is quiet instead of
        trusting status alone.

        ``max_transient_stream_failures`` bounds consecutive connection-level
        stream failures (gateway restart, network blip) that are retried with
        backoff before the error propagates. Runs are durable server-side, so
        giving up on the first refused connection would silently lose the
        final answer for a follower that could have resumed seconds later.
        """
        self._gateway = gateway
        self._debug = bool(debug)
        self._stream_timeout_s = max(1.0, float(stream_timeout_s))
        self._stream_idle_s = max(5.0, float(stream_idle_s))
        self._terminal_replay_max_wait_s = max(0.0, float(terminal_replay_max_wait_s))
        self._terminal_replay_interval_s = max(0.01, float(terminal_replay_interval_s))
        self._max_transient_stream_failures = max(0, int(max_transient_stream_failures))
        self._idle_warned: set[str] = set()

    @staticmethod
    def _sleep_with_stop(seconds: float, should_stop: Callable[[], bool]) -> None:
        """Sleep up to ``seconds`` while polling ``should_stop`` (cancel latency)."""
        deadline = time.monotonic() + max(0.0, float(seconds))
        while time.monotonic() < deadline:
            try:
                if should_stop():
                    return
            except Exception:
                pass
            time.sleep(min(0.25, max(0.01, deadline - time.monotonic())))

    @staticmethod
    def _is_transient_stream_error(exc: Exception) -> bool:
        """Return True for connection-level failures worth retrying."""
        if isinstance(exc, GatewayHttpError):
            status = int(getattr(exc, "status", 0) or 0)
            return status in {408, 425, 429} or status >= 500
        # urllib.error.URLError subclasses OSError; ConnectionError covers
        # refused/reset/aborted sockets during a gateway restart.
        return isinstance(exc, (urllib.error.URLError, ConnectionError, OSError))

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
        on_delta: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Tuple[int, str, bool]:
        """Stream one run's ledger until it ends or waits on a subworkflow.

        ``on_delta`` receives the live-reply events (``assistant_delta`` /
        ``assistant_delta_end`` dicts, see ``live_deltas``). They never move
        ``after``: the resume cursor only ever comes from durable rows, so a
        reconnect replays nothing twice and misses nothing — the gateway
        re-sends a snapshot of any reply still being written.
        """
        backoff_s = 1.0
        transient_failures = 0
        stop_signal = _CallableStopSignal(should_stop)
        delta_hook = self._delta_hook(run_id=run_id, on_delta=on_delta)
        open_hook = self._open_hook(run_id=run_id, on_delta=on_delta)
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
                try:
                    on_record(run_id, rec)
                except Exception as cb_exc:
                    # Do not let a record-processing failure masquerade as a
                    # transient transport error (which would retry past this
                    # record's cursor and drop it).
                    raise _RecordCallbackError(str(cb_exc)) from cb_exc
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
                    stop_signal=stop_signal,
                    timeout_s=self._stream_timeout_s,
                    max_idle_s=self._stream_idle_s,
                    on_delta=delta_hook,
                    on_open=open_hook,
                )
                transient_failures = 0
                if on_online:
                    on_online()
            except GatewayStreamIdle as e:
                # An idle timeout means the SSE connection itself succeeded, so
                # the follower is healthy again — clear any offline state that a
                # prior transient failure raised (otherwise OFFLINE sticks for
                # the rest of the run, since the stream normally exits via idle).
                transient_failures = 0
                if on_online:
                    on_online()
                if run_id not in self._idle_warned:
                    warnings.warn(f"#REPLAY: {e} for run {run_id}; polling run status")
                    self._idle_warned.add(run_id)
            except _RecordCallbackError as e:
                # A callback failure is a real (non-transport) error: re-raise
                # the original cause immediately, never retry.
                raise (e.__cause__ or e)
            except Exception as e:
                if self._debug:
                    print(f"❌ Gateway stream_ledger failed for {run_id}: {e}")
                if on_offline:
                    on_offline(str(e))
                if not self._is_transient_stream_error(e):
                    raise e
                transient_failures += 1
                if transient_failures > self._max_transient_stream_failures:
                    raise e
                warnings.warn(
                    f"#REPLAY: transient stream failure for run {run_id} "
                    f"({transient_failures}/{self._max_transient_stream_failures}); retrying"
                )
                self._sleep_with_stop(backoff_s, should_stop)
                backoff_s = min(backoff_s * 2.0, 5.0)
                continue

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

            self._sleep_with_stop(backoff_s, should_stop)
            backoff_s = min(backoff_s * 2.0, 5.0)

    def _delta_hook(
        self,
        *,
        run_id: str,
        on_delta: Optional[Callable[[Dict[str, object]], None]],
    ) -> Optional[Callable[[str, Dict[str, object]], None]]:
        """Adapt the client's raw ``(event_name, data)`` into UI events.

        A failing ``on_delta`` is reported and the stream continues: a live
        preview must never end the follow of a run whose durable rows still
        carry the reply (and it must never be retried as a transport error,
        which would reconnect in a loop).
        """
        if on_delta is None:
            return None
        warned: list[str] = []

        def _hook(event_name: str, data: Dict[str, object]) -> None:
            ev = to_ui_event(event_name, data, run_id=run_id)
            if ev is None:
                return
            try:
                on_delta(ev)
            except Exception as exc:
                if not warned:
                    warned.append(str(exc))
                    warnings.warn(f"#FALLBACK: live reply handler failed for run {run_id}: {exc}")

        return _hook

    def _open_hook(
        self,
        *,
        run_id: str,
        on_delta: Optional[Callable[[Dict[str, object]], None]],
    ) -> Optional[Callable[[], None]]:
        """Each (re)connect tells the UI to drop its live text (contract
        S-2.3): the gateway re-sends a snapshot of every reply still being
        written, and anything not re-sent has ended."""
        if on_delta is None:
            return None

        def _hook() -> None:
            try:
                on_delta({"type": ASSISTANT_DELTA_RESET, "run_id": run_id})
            except Exception as exc:
                warnings.warn(f"#FALLBACK: live reply reset failed for run {run_id}: {exc}")

        return _hook

    def follow_run(
        self,
        *,
        root_run_id: str,
        on_record: Callable[[str, Dict[str, object]], None],
        should_stop: Callable[[], bool],
        on_offline: Optional[Callable[[str], None]] = None,
        on_online: Optional[Callable[[], None]] = None,
        on_delta: Optional[Callable[[Dict[str, object]], None]] = None,
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
                on_delta=on_delta,
            )
            after_by_run[active_run_id] = after

            if sub_run_id and sub_run_id not in seen_sub_runs:
                seen_sub_runs.add(sub_run_id)
                run_stack.append(sub_run_id)
                continue

            if completed:
                run_stack.pop()
                continue
