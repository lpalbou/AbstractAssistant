from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from abstractassistant.core.agent_host import AgentHost, AgentHostConfig
from abstractruntime import EffectType, RunState
from abstractruntime.core.runtime import EffectOutcome, Runtime
from abstractruntime.integrations.abstractcore.effect_handlers import make_tool_calls_handler


def _stub_llm_handler(run: RunState, effect, default_next_node) -> EffectOutcome:
    payload = dict(effect.payload or {})
    messages = payload.get("messages") or []
    has_tool = any(isinstance(m, dict) and m.get("role") == "tool" for m in messages)
    if not has_tool:
        return EffectOutcome.completed(
            {
                "content": "",
                "tool_calls": [{"name": "add", "arguments": {"a": 1, "b": 2}, "call_id": "c1"}],
                "finish_reason": "tool_calls",
            }
        )
    return EffectOutcome.completed({"content": "3", "tool_calls": [], "finish_reason": "stop"})


def _runtime_builder(**kwargs: Any) -> Runtime:
    run_store = kwargs["run_store"]
    ledger_store = kwargs["ledger_store"]
    artifact_store = kwargs["artifact_store"]
    tool_executor = kwargs["tool_executor"]
    handlers = {
        EffectType.LLM_CALL: _stub_llm_handler,
        EffectType.TOOL_CALLS: make_tool_calls_handler(tools=tool_executor, artifact_store=artifact_store, run_store=run_store),
    }
    return Runtime(run_store=run_store, ledger_store=ledger_store, effect_handlers=handlers, artifact_store=artifact_store)


def add(a: int, b: int) -> int:
    return int(a) + int(b)


@pytest.mark.integration
def test_agent_host_executes_tool_calls_when_approved(tmp_path: Path) -> None:
    host = AgentHost(
        AgentHostConfig(provider="stub", model="stub", data_dir=tmp_path),
        tools=[add],
        runtime_builder=_runtime_builder,
    )

    events: list[Dict[str, Any]] = []
    for ev in host.run_turn(user_text="add numbers", approve_tools=lambda _tcs: True):
        assert isinstance(ev, dict)
        events.append(ev)

    assert any(e.get("type") == "tool_request" for e in events)
    tool_result = next(e for e in events if e.get("type") == "tool_result")
    result_payload = tool_result.get("result")
    assert isinstance(result_payload, dict)
    assert result_payload.get("mode") == "executed"
    results = result_payload.get("results")
    assert isinstance(results, list) and results
    assert results[0].get("success") is True
    assert results[0].get("output") == 3

    assistant = next(e for e in events if e.get("type") == "assistant")
    assert str(assistant.get("content") or "") == "3"

    # Persistence: runtime store should have written at least one run JSON.
    runtime_dir = tmp_path / "runtime"
    assert runtime_dir.exists()
    assert any(p.suffix == ".json" for p in runtime_dir.iterdir())
    assert (tmp_path / "session.json").exists()


@pytest.mark.integration
def test_agent_host_denies_tools_and_still_completes(tmp_path: Path) -> None:
    host = AgentHost(
        AgentHostConfig(provider="stub", model="stub", data_dir=tmp_path),
        tools=[add],
        runtime_builder=_runtime_builder,
    )

    events: list[Dict[str, Any]] = []
    for ev in host.run_turn(user_text="add numbers", approve_tools=lambda _tcs: False):
        events.append(ev)

    tool_result = next(e for e in events if e.get("type") == "tool_result")
    result_payload = tool_result.get("result")
    assert isinstance(result_payload, dict)
    results = result_payload.get("results")
    assert isinstance(results, list) and results
    assert results[0].get("success") is False
    assert "Denied" in str(results[0].get("error") or "")

    assistant = next(e for e in events if e.get("type") == "assistant")
    assert str(assistant.get("content") or "") == "3"

