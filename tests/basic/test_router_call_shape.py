"""Regression pin (2026-09-17): the router must not inherit the agent's tools.

`route_call` decides chat / image / voice / ... and nothing else. It sits right
after `start`, and an llm_call node inherits every same-named key of the previous
exec node's output — `start` outputs the agent's `tools` (30 of them in a real
session) and `temperature` (0.2). With no `tools` pin declared on the router, all 30
tool schemas rode into a call that also asks for structured output, and AbstractCore
serves tools+structured as TWO generations: an unstructured tool-enabled pass, then
the structured one. Measured on Qwen3.8-27B: 12-28 s per turn for a routing decision,
~4.6k prompt tokens where ~300 were meant.

Compiled through the real runtime compiler so the pin is tested at the seam where
the inheritance happens, not by reading the node dict back.
"""

from __future__ import annotations

import copy

import pytest

from abstractassistant.assistant_workflow import managed_assistant_visualflow

compile_visualflow = pytest.importorskip("abstractruntime.visualflow_compiler").compile_visualflow
RunState = pytest.importorskip("abstractruntime.core.models").RunState

# What `start` really hands the next node: the agent's knobs, by name.
_START_OUTPUT = {
    "prompt": "hi",
    "tools": ["read_file", "list_files"],
    "temperature": 0.2,
    "seed": -1,
    "provider": None,
    "model": None,
}


def _route_call_payload(flow: dict) -> dict:
    flow = copy.deepcopy(flow)
    flow.setdefault("id", "router_shape_probe")
    spec = compile_visualflow(flow)
    run = RunState.new(
        workflow_id=spec.workflow_id,
        entry_node="route_call",
        vars={"_temp": {}, "_last_output": dict(_START_OUTPUT)},
    )
    plan = spec.get_node("route_call")(run, None)
    return dict(plan.effect.payload or {})


def test_router_runs_without_tools_and_at_its_own_temperature() -> None:
    payload = _route_call_payload(managed_assistant_visualflow())
    assert payload.get("tools") == []
    assert payload["params"]["temperature"] == 0.0
    assert payload["response_schema"], "the router is a structured call"
    assert str(payload["system_prompt"]).startswith("You are routing")


def test_the_pins_are_what_shuts_the_inheritance() -> None:
    """Remove the declared pins and the agent's tools come straight back — i.e. this
    file fails if someone 'tidies' the two unused-looking inputs off the node."""
    flow = managed_assistant_visualflow()
    for node in flow["nodes"]:
        if node.get("id") != "route_call":
            continue
        data = node["data"]
        data["inputs"] = [p for p in data["inputs"] if p.get("id") not in {"tools", "temperature"}]
        defaults = dict(data.get("pinDefaults") or {})
        defaults.pop("tools", None)
        defaults.pop("temperature", None)
        data["pinDefaults"] = defaults
    payload = _route_call_payload(flow)
    assert [t.get("name") for t in payload.get("tools") or []] == ["read_file", "list_files"]
    assert payload["params"]["temperature"] == 0.2
