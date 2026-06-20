"""Basic coverage for gateway worker completion fallbacks."""

from __future__ import annotations

import pytest

from abstractassistant.ui.gateway_worker import GatewayWorker


@pytest.mark.basic
def test_gateway_worker_materializes_empty_final_reply_into_fallback_message() -> None:
    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = None
    worker._run_activity_by_run = {"run-1": "Running (abc123): search online for Genentech roles"}

    content, meta = GatewayWorker._materialize_assistant_content(
        worker,
        run_id="run-1",
        content="",
        meta={"tool_calls": 3, "tool_results": 3},
        final=True,
    )

    assert content == "The workflow completed, but it returned no written reply."
    assert meta["kind"] == "fallback_completion"
    assert meta["empty_response"] is True
    assert meta["run_id"] == "run-1"
    assert meta["run_activity"] == "Running (abc123): search online for Genentech roles"


@pytest.mark.basic
def test_gateway_worker_allows_same_fallback_text_for_different_runs() -> None:
    class _LLMManager:
        @staticmethod
        def session_messages():
            return [
                {
                    "role": "assistant",
                    "content": "The workflow completed, but it returned no written reply.",
                    "metadata": {"kind": "fallback_completion", "run_id": "run-old"},
                }
            ]

    worker = GatewayWorker.__new__(GatewayWorker)
    super(GatewayWorker, worker).__init__()
    worker._gateway = None
    worker._llm_manager = _LLMManager()

    assert (
        GatewayWorker._should_append_assistant(
            worker,
            "The workflow completed, but it returned no written reply.",
            meta={"kind": "fallback_completion", "run_id": "run-new"},
        )
        is True
    )
    assert (
        GatewayWorker._should_append_assistant(
            worker,
            "The workflow completed, but it returned no written reply.",
            meta={"kind": "fallback_completion", "run_id": "run-old"},
        )
        is False
    )
