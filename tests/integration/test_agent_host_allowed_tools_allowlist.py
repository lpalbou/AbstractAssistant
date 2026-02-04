from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from abstractassistant.core.agent_host import AgentHost, AgentHostConfig
from abstractcore.tools import tool
from abstractruntime import EffectType, RunState
from abstractruntime.core.runtime import EffectOutcome, Runtime
from abstractruntime.integrations.abstractcore.effect_handlers import make_tool_calls_handler


@tool(name="add", description="Add two integers")
def add(a: int, b: int) -> int:
    return int(a) + int(b)


def _stub_llm_handler(run: RunState, effect, default_next_node) -> EffectOutcome:
    payload = dict(effect.payload or {})
    tools_raw = payload.get("tools") or []
    tool_names = {str(t.get("name") or "") for t in tools_raw if isinstance(t, dict)}

    messages = payload.get("messages") or []
    has_tool = any(isinstance(m, dict) and m.get("role") == "tool" for m in messages)

    # Only call "add" when it is present in the tool schema list sent to the model.
    if "add" not in tool_names:
        return EffectOutcome.completed({"content": "no-tool", "tool_calls": [], "finish_reason": "stop"})

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


@pytest.mark.integration
def test_agent_host_allowed_tools_allows_tool_when_in_allowlist(tmp_path: Path) -> None:
    host = AgentHost(
        AgentHostConfig(provider="stub", model="stub", data_dir=tmp_path),
        tools=[add],
        runtime_builder=_runtime_builder,
    )

    events: list[Dict[str, Any]] = []
    for ev in host.run_turn(user_text="add numbers", approve_tools=lambda _tcs: True, allowed_tools=["add"]):
        events.append(ev)

    assert any(e.get("type") == "tool_request" for e in events)
    assert any(e.get("type") == "tool_result" for e in events)
    assistant = next(e for e in events if e.get("type") == "assistant")
    assert str(assistant.get("content") or "") == "3"


@pytest.mark.integration
def test_agent_host_allowed_tools_blocks_tool_when_not_allowed(tmp_path: Path) -> None:
    host = AgentHost(
        AgentHostConfig(provider="stub", model="stub", data_dir=tmp_path),
        tools=[add],
        runtime_builder=_runtime_builder,
    )

    events: list[Dict[str, Any]] = []
    for ev in host.run_turn(user_text="add numbers", approve_tools=lambda _tcs: True, allowed_tools=[]):
        events.append(ev)

    assert not any(e.get("type") == "tool_request" for e in events)
    assistant = next(e for e in events if e.get("type") == "assistant")
    assert str(assistant.get("content") or "") == "no-tool"

