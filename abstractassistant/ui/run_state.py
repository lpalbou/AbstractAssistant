"""
Run state machine for AbstractAssistant.

Centralizes run lifecycle transitions so UI + tray status stay consistent.
"""

from typing import Callable, Optional


class RunStateMachine:
    """Track run lifecycle and emit state transitions."""

    def __init__(
        self,
        *,
        on_state_change: Callable[[str], None],
        on_missing_final: Optional[Callable[[], None]] = None,
        debug: bool = False,
    ) -> None:
        self._on_state_change = on_state_change
        self._on_missing_final = on_missing_final
        self._debug = bool(debug)

        self._state = "idle"
        self._run_active = False
        self._run_has_output = False
        self._run_has_final = False
        self._pending_completion = False
        self._speaking = False
        self._missing_final_emitted = False

    @property
    def state(self) -> str:
        return str(self._state or "idle")

    def is_run_active(self) -> bool:
        return bool(self._run_active)

    def start_run(self) -> None:
        self._run_active = True
        self._run_has_output = False
        self._run_has_final = False
        self._pending_completion = False
        self._missing_final_emitted = False
        self._set_state("running")

    def mark_status(self, status: str) -> None:
        st = str(status or "").strip().lower()
        if st in {"thinking", "running", "generating", "resuming"}:
            self.mark_running()
            return
        if st in {"offline", "disconnected"}:
            self._run_active = True
            self._set_state("offline")
            return
        if st in {"reconnecting"}:
            self._run_active = True
            self._set_state("reconnecting")
            return
        if st in {"waiting", "approve"}:
            self.mark_waiting()
            return
        if st in {"executing", "executing_tools"}:
            self.mark_executing()
            return
        if st in {"completed", "ready", "done"}:
            self.mark_completed()
            return
        if st in {"error", "failed", "cancelled"}:
            self.mark_error()
            return

    def mark_running(self) -> None:
        self._run_active = True
        self._set_state("running")

    def mark_waiting(self) -> None:
        self._run_active = True
        self._set_state("waiting")

    def mark_executing(self) -> None:
        self._run_active = True
        self._set_state("executing")

    def mark_intermediate_output(self) -> None:
        self._run_has_output = True

    def mark_final_output(self) -> None:
        self._run_has_output = True
        self._run_has_final = True
        if not self._run_active and not self._speaking:
            self._finalize_completion()

    def mark_completed(self) -> None:
        self._run_active = False
        if self._speaking:
            self._set_state("speaking")
            return
        if self._run_has_final:
            self._finalize_completion()
            return
        self._pending_completion = True
        self._set_state("completed")
        self._emit_missing_final()

    def mark_error(self) -> None:
        self._run_active = False
        self._set_state("error")

    def set_speaking(self, speaking: bool) -> None:
        self._speaking = bool(speaking)
        if self._speaking:
            self._set_state("speaking")
            return
        if self._run_active:
            self._set_state("running")
            return
        if self._run_has_final or self._pending_completion:
            self._finalize_completion()

    def reset_idle(self) -> None:
        self._run_active = False
        self._run_has_output = False
        self._run_has_final = False
        self._pending_completion = False
        self._missing_final_emitted = False
        self._set_state("idle")

    def _finalize_completion(self) -> None:
        self._pending_completion = False
        self._set_state("completed")

    def _emit_missing_final(self) -> None:
        if self._missing_final_emitted:
            return
        self._missing_final_emitted = True
        if self._on_missing_final:
            try:
                self._on_missing_final()
            except Exception:
                return

    def _set_state(self, state: str) -> None:
        nxt = str(state or "").strip().lower() or "idle"
        if nxt == self._state:
            return
        self._state = nxt
        if self._debug:
            print(f"🔁 RunStateMachine: {self._state}")
        if self._on_state_change:
            try:
                self._on_state_change(self._state)
            except Exception:
                return
