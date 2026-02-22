"""
Gateway ledger and wait types used by the thin-client adapter.

These are intentionally minimal and JSON-shaped to match the gateway contract.
"""

from typing import Any, Dict, List, TypedDict


class ToolCall(TypedDict, total=False):
    """Serialized tool call shape (name + arguments + optional call_id)."""

    name: str
    arguments: Any
    call_id: str


class WaitState(TypedDict, total=False):
    """Serialized wait state from the runtime."""

    reason: str
    wait_key: str
    prompt: str
    choices: List[str]
    allow_free_text: bool
    until: str
    details: Dict[str, Any]


class StepRecord(TypedDict, total=False):
    """Single ledger record for a run step."""

    run_id: str
    step_id: str
    status: str
    effect: Dict[str, Any]
    result: Dict[str, Any]
    error: str


class LedgerStreamEvent(TypedDict, total=False):
    """SSE event payload for ledger streaming."""

    cursor: int
    record: StepRecord
