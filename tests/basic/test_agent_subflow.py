"""Operator 2026-10-11: the orchestrator's chat branch runs basic-agent (the
framework's agent workflow) as a subflow, not a second agent inlined in it.

A subflow is packed into the bundle it is published with, from the gateway's flow
store, so the app keeps a copy of basic-agent's flows there and the chat branch
calls the copy."""

from __future__ import annotations

import copy

import pytest

from agent_fixture import AGENT_COPY_ID, AGENT_ENTRY, AGENT_VERSION, AgentBundleMixin, agent_flow  # tests/basic is on sys.path
from abstractassistant.assistant_workflow import AGENT_BUNDLE_ID, managed_assistant_visualflow
from abstractassistant.gateway_service import AssistantGatewayService
from agent_fixture import agent_subflow


class _Store(AgentBundleMixin):
    """basic-agent with two flows (the entry calls a status subflow), as shipped."""

    version = AGENT_VERSION

    def __init__(self) -> None:
        self.flows: list[dict] = []
        self.created: list[dict] = []
        self.updated: list[dict] = []
        status = {"id": "15f19f7f", "name": "ac-update-status", "nodes": [{"id": "n", "type": "on_flow_start", "data": {"nodeType": "on_flow_start", "outputs": []}}], "edges": [], "entryNode": "n"}
        entry = agent_flow()
        entry["nodes"].append({"id": "node-4", "type": "subflow", "data": {"nodeType": "subflow", "subflowId": "15f19f7f"}})
        self.sources = {AGENT_ENTRY: entry, "15f19f7f": status}

    def get_bundle(self, bundle_id: str) -> dict:
        assert bundle_id == AGENT_BUNDLE_ID
        return {"bundle_version": self.version, "default_entrypoint": AGENT_ENTRY, "flows": sorted(self.sources)}

    def get_bundle_flow(self, bundle_id: str, flow_id: str, *, bundle_version: str) -> dict:
        assert bundle_version == self.version
        return {"flow": copy.deepcopy(self.sources[flow_id])}

    def list_visualflows(self) -> list[dict]:
        return copy.deepcopy(self.flows)

    def create_visualflow(self, **kwargs) -> dict:
        flow = {"id": f"copy-{len(self.created) + 1}", "name": kwargs["name"], "description": kwargs.get("description", "")}
        self.flows.append(flow)
        self.created.append(kwargs)
        return dict(flow)

    def update_visualflow(self, **kwargs) -> dict:
        self.updated.append(kwargs)
        flow = {"id": kwargs["flow_id"], "name": kwargs["name"], "description": kwargs["description"], "interfaces": kwargs["interfaces"],
                "nodes": kwargs["nodes"], "edges": kwargs["edges"], "entryNode": kwargs["entry_node"]}
        self.flows = [f for f in self.flows if f["id"] != flow["id"]] + [flow]
        return flow


def test_the_chat_branch_is_a_subflow_running_the_copy_of_basic_agent() -> None:
    flow = managed_assistant_visualflow(agent_subflow())
    node = next(n for n in flow["nodes"] if n["id"] == "assistant_agent")
    assert node["type"] == "subflow" and node["data"]["subflowId"] == AGENT_COPY_ID
    assert not [n for n in flow["nodes"] if n["type"] == "agent"], "no second agent inlined in the orchestrator"
    assert flow["description"].endswith(f"agent={AGENT_BUNDLE_ID}@{AGENT_VERSION}")
    # Every edge into / out of the subflow lands on a pin basic-agent has.
    pins_in = {p["id"] for p in node["data"]["inputs"]}
    pins_out = {p["id"] for p in node["data"]["outputs"]}
    for edge in flow["edges"]:
        if edge["target"] == "assistant_agent":
            assert edge["targetHandle"] in pins_in, edge
        if edge["source"] == "assistant_agent":
            assert edge["sourceHandle"] in pins_out, edge


def test_basic_agent_is_copied_with_its_subflows_and_kept_in_step() -> None:
    gw = _Store()
    agent = AssistantGatewayService(gw)._ensure_agent_copies()
    assert len(gw.created) == 2
    copies = {f["id"]: f for f in gw.flows}
    entry_copy = copies[agent.flow_id]
    # The entry copy calls the COPY of its status subflow, never the bundle-local id.
    status_copy_id = next(f["id"] for f in gw.flows if f["id"] != agent.flow_id)
    assert next(n for n in entry_copy["nodes"] if n["id"] == "node-4")["data"]["subflowId"] == status_copy_id
    assert all(f["interfaces"] == [] for f in gw.flows), "a copy is a subflow, never a second agent in the lists"
    assert agent.bundle_ref == f"{AGENT_BUNDLE_ID}@{AGENT_VERSION}"

    # Same basic-agent: nothing is written again.
    gw.created.clear(); gw.updated.clear()
    assert AssistantGatewayService(gw)._ensure_agent_copies().flow_id == agent.flow_id
    assert gw.created == [] and gw.updated == []

    # A new basic-agent version: the same copies are updated in place, and the
    # orchestrator's description changes, so the app republishes it.
    gw.version = "0.0.6"
    gw.sources[AGENT_ENTRY]["name"] = "Basic agent v6"
    newer = AssistantGatewayService(gw)._ensure_agent_copies()
    assert gw.created == [] and newer.flow_id == agent.flow_id and gw.updated
    assert managed_assistant_visualflow(newer)["description"] != managed_assistant_visualflow(agent)["description"]


def test_no_basic_agent_means_no_orchestrator_never_an_inlined_stand_in() -> None:
    class _NoAgent(_Store):
        def get_bundle(self, bundle_id: str) -> dict:
            return {"bundle_version": "", "default_entrypoint": None, "flows": []}

    with pytest.raises(RuntimeError, match="basic-agent bundle has no usable entrypoint"):
        AssistantGatewayService(_NoAgent())._ensure_agent_copies()


def test_basic_agent_without_a_wired_pin_is_refused() -> None:
    flow = agent_flow()
    start = flow["nodes"][0]
    start["data"]["outputs"] = [p for p in start["data"]["outputs"] if p["id"] != "prompt"]
    from abstractassistant.assistant_workflow import agent_subflow_from_flow

    with pytest.raises(ValueError, match="lacks the pins the Assistant orchestrator wires: prompt"):
        agent_subflow_from_flow(flow_id="x", bundle_ref="basic-agent@9", flow=flow)


def test_every_connection_joins_pins_of_the_same_type() -> None:
    """The editor draws a connection only between compatible pins; a string start
    pin wired to a provider_image input was 'kept but not drawn' (12 of them)."""
    flow = managed_assistant_visualflow(agent_subflow())
    pins = {}
    for node in flow["nodes"]:
        for side in ("inputs", "outputs"):
            for pin in node["data"].get(side) or []:
                pins[(node["id"], side, pin["id"])] = pin["type"]
    media = {"generate_image", "edit_image", "upscale_image", "generate_video", "image_to_video", "generate_music"}
    checked = 0
    for edge in flow["edges"]:
        if edge["source"] != "start" or edge["target"] not in media:
            continue
        if not (edge["targetHandle"].endswith("_provider") or edge["targetHandle"].endswith("_model")):
            continue
        assert pins[("start", "outputs", edge["sourceHandle"])] == pins[(edge["target"], "inputs", edge["targetHandle"])], edge
        checked += 1
    assert checked == 12


def test_every_end_carries_response_success_and_meta() -> None:
    """The Assistant interface requires them on every On Flow End: chat, each media
    branch and the 'need a source image' answer alike."""
    flow = managed_assistant_visualflow(agent_subflow())
    ends = [n for n in flow["nodes"] if n["data"]["nodeType"] == "on_flow_end"]
    assert len(ends) == 10
    for end in ends:
        assert {"response", "success", "meta"} <= {p["id"] for p in end["data"]["inputs"]}, end["id"]

