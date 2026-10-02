"""Automation inputs without chat selections must still expose the agent's tools."""

import pytest

from abstractassistant.assistant_workflow import managed_assistant_visualflow

rt = pytest.importorskip("abstractruntime")
compile_visualflow = pytest.importorskip("abstractruntime.visualflow_compiler").compile_visualflow


@pytest.mark.parametrize(
    "inputs, expected",
    [
        ({}, None),
        ({"tools": []}, []),
        ({"tools": ["web_search"]}, ["web_search"]),
        ({"_runtime": {"allowed_tools": []}}, []),
        ({"_runtime": {"allowed_tools": ["web_search"]}}, ["web_search"]),
    ],
)
def test_compiled_default_tools_respect_explicit_inputs_and_parent_ceiling(inputs, expected):
    flow = managed_assistant_visualflow()
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

    # Execute the actual child-start boundary: it intersects the workflow's
    # selected tools with the caller's explicit runtime ceiling.
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
    tools = children[0].vars["_runtime"]["allowed_tools"]
    if expected is None:
        assert {"web_search", "fetch_url", "read_file"} <= set(tools)
        assert "send_email" not in tools  # Host-owned optional capability.
    else:
        assert tools == expected
