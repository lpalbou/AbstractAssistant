"""Router control messages must never become the chat agent's conversation."""
import copy
import pytest

from agent_fixture import agent_subflow
from abstractassistant.assistant_workflow import managed_assistant_visualflow, _BASE_SYSTEM_PROMPT
from abstractruntime import Runtime, InMemoryRunStore, InMemoryLedgerStore, WorkflowRegistry
from abstractruntime.core.models import EffectType
from abstractruntime.core.runtime import EffectOutcome
from abstractruntime.integrations.abstractcore.effect_handlers import make_llm_call_handler
from abstractruntime.visualflow_compiler import compile_visualflow


class RouterTransport:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return {"content": '{"mode":"chat","assistant_message":"","media_prompt":""}',
                "data": {"mode": "chat", "assistant_message": "", "media_prompt": ""},
                "tool_calls": [], "usage": {}}


@pytest.mark.parametrize("selection", [{}, {"tools": [], "system": "Ordinary chat system", "resp_schema": None},
    {"tools": ["read_file"], "system": "Ordinary chat system", "resp_schema": {"type": "object", "properties": {"answer": {"type": "string"}}}}])
def test_chat_subflow_never_receives_router_context_or_configuration(selection):
    transport = RouterTransport()
    children = []
    def child(run, effect, next_node):
        children.append(copy.deepcopy(effect.payload))
        return EffectOutcome.completed({"output": {"response": "Ordinary answer", "success": True}})
    graph = managed_assistant_visualflow(agent_subflow())
    graph["id"] = "router-context-isolation"
    spec = compile_visualflow(graph)
    registry = WorkflowRegistry(); registry.register(spec)
    runtime = Runtime(run_store=InMemoryRunStore(), ledger_store=InMemoryLedgerStore(), workflow_registry=registry,
        effect_handlers={EffectType.LLM_CALL: make_llm_call_handler(llm=transport), EffectType.START_SUBWORKFLOW: child})
    history = [{"role": "user", "content": "Earlier ordinary question"}, {"role": "assistant", "content": "Earlier ordinary answer"}]
    run_id = runtime.start(workflow=spec, vars={"prompt": "Explain a theatre scene", "context": {"messages": copy.deepcopy(history)},
        **selection})
    runtime.tick(workflow=spec, run_id=run_id, max_steps=80)
    state = runtime.get_state(run_id)
    assert children, state.error
    assert state.vars["context"]["messages"] == history
    assert not transport.calls[0].get("messages"), "router must not read conversational context"
    inputs = children[0]["vars"]
    assert inputs["context"]["messages"] == history
    assert inputs["system"] == selection.get("system", _BASE_SYSTEM_PROMPT)
    assert inputs.get("resp_schema") == selection.get("resp_schema")
    assert inputs["tools"] == selection.get("tools", ["edit_file", "analyze_code", "execute_command", "fetch_url", "list_files", "read_file", "search_files", "web_search", "write_file"])
    assert inputs["prompt"] == "Explain a theatre scene"
