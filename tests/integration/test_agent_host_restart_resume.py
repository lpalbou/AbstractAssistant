from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

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
        EffectType.TOOL_CALLS: make_tool_calls_handler(
            tools=tool_executor,
            artifact_store=artifact_store,
            run_store=run_store,
        ),
    }
    return Runtime(
        run_store=run_store,
        ledger_store=ledger_store,
        effect_handlers=handlers,
        artifact_store=artifact_store,
    )


def add(a: int, b: int) -> int:
    return int(a) + int(b)


@pytest.mark.integration
def test_agent_host_can_resume_waiting_run_after_restart(tmp_path: Path) -> None:
    host1 = AgentHost(
        AgentHostConfig(provider="stub", model="stub", data_dir=tmp_path),
        tools=[add],
        runtime_builder=_runtime_builder,
    )

    gen = host1.run_turn(user_text="add numbers", approve_tools=lambda _tcs: True)
    run_id = None
    for ev in gen:
        if isinstance(ev, dict) and ev.get("type") == "tool_request":
            run_id = str(ev.get("run_id") or "")
            break
    gen.close()

    assert run_id

    # "Restart": create a new host pointing at the same data dir.
    host2 = AgentHost(
        AgentHostConfig(provider="stub", model="stub", data_dir=tmp_path),
        tools=[add],
        runtime_builder=_runtime_builder,
    )

    events: list[Dict[str, Any]] = []
    final = ""
    for ev in host2.resume_run(run_id=run_id, approve_tools=lambda _tcs: True):
        assert isinstance(ev, dict)
        events.append(ev)
        if ev.get("type") == "assistant":
            final = str(ev.get("content") or "")

    assert final == "3"
    assert any(e.get("type") == "tool_request" for e in events)
    assert any(e.get("type") == "tool_result" for e in events)

    runtime_dir = tmp_path / "runtime"
    assert runtime_dir.exists()
    assert any(p.suffix == ".json" for p in runtime_dir.iterdir())
