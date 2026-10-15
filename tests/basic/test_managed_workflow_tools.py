"""Automation inputs without chat selections must still expose the agent's tools, within the caller's ceiling."""

import pytest

from agent_fixture import agent_subflow  # tests/basic is on sys.path
from abstractassistant.assistant_workflow import managed_assistant_visualflow

rt = pytest.importorskip("abstractruntime")
compile_visualflow = pytest.importorskip("abstractruntime.visualflow_compiler").compile_visualflow


@pytest.mark.parametrize(
    "inputs, tools, ceiling",
    [
        ({}, None, None),
        ({"tools": []}, [], None),
        ({"tools": ["web_search"]}, ["web_search"], None),
        ({"_runtime": {"allowed_tools": []}}, None, []),
        ({"_runtime": {"allowed_tools": ["web_search"]}}, None, ["web_search"]),
    ],
)
def test_the_agent_subflow_gets_the_tools_and_the_callers_ceiling(inputs, tools, ceiling):
    """Chat runs basic-agent as a subflow: the orchestrator hands it the caller's
    tools (or this workflow's baseline when the caller sends none), and the
    caller's explicit runtime ceiling reaches the child run, where basic-agent's
    agent node intersects the two."""
    flow = managed_assistant_visualflow(agent_subflow())
    flow["id"] = "assistant_tools_probe"
    spec = compile_visualflow(flow)
    parent = rt.RunState.new(
        workflow_id=spec.workflow_id, entry_node="start",
        vars={"prompt": "Find current prices", "provider": "test", "model": "test", **inputs},
    )
    spec.get_node("start")(parent, None)
    # The router must remain untooled even when the start now has defaults.
    router = spec.get_node("route_call")(parent, None)
    assert router.effect.payload["tools"] == []
    agent = spec.get_node("assistant_agent")(parent, None)
    assert agent.effect.payload["workflow_id"] == agent_subflow().flow_id

    child = rt.WorkflowSpec(
        workflow_id=agent.effect.payload["workflow_id"], entry_node="done",
        nodes={"done": lambda run, ctx: rt.StepPlan(node_id="done", complete_output={})},
    )
    registry = rt.WorkflowRegistry()
    registry.register(child)
    store = rt.InMemoryRunStore()
    store.save(parent)
    runtime = rt.Runtime(run_store=store, ledger_store=rt.InMemoryLedgerStore(), workflow_registry=registry)
    outcome = runtime._handle_start_subworkflow(parent, agent.effect, None)
    assert outcome.status != "failed", outcome.error
    children = store.list_children(parent_run_id=parent.run_id)
    assert len(children) == 1
    if tools is None:
        assert {"web_search", "fetch_url", "read_file"} <= set(children[0].vars["tools"])
        assert "send_email" not in children[0].vars["tools"]  # Host-owned optional capability.
    else:
        assert children[0].vars["tools"] == tools
    if ceiling is None:
        assert "allowed_tools" not in (children[0].vars.get("_runtime") or {})
    else:
        assert children[0].vars["_runtime"]["allowed_tools"] == ceiling
