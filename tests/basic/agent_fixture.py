"""A basic-agent stand-in for tests: the boundary pins of the gateway's shipped
basic-agent (abstractgateway flows/bundles/basic-agent.flow, flow 81795ea9), which
the Assistant orchestrator's chat branch runs as a subflow."""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from abstractassistant.assistant_workflow import AGENT_BUNDLE_ID, agent_subflow_from_flow, normalized_managed_visualflow
from abstractassistant.gateway_service import AssistantGatewayService

AGENT_VERSION = "0.0.5"
AGENT_ENTRY = "81795ea9"
AGENT_COPY_ID = "vf-agent-copy"

_START = [
    ("use_context", "boolean"), ("memory", "memory"), ("context", "object"), ("provider", "provider"),
    ("model", "model"), ("system", "string"), ("prompt", "string"), ("tools", "tools"),
    ("max_iterations", "number"), ("max_in_tokens", "number"), ("temperature", "number"),
    ("seed", "number"), ("resp_schema", "object"),
]
_END = [("response", "string"), ("success", "boolean"), ("meta", "object"), ("scratchpad", "object")]


def agent_flow() -> Dict[str, Any]:
    pins = lambda spec: [{"id": pid, "label": pid, "type": ptype} for pid, ptype in spec]  # noqa: E731
    return {
        "id": AGENT_ENTRY,
        "name": "Basic agent",
        "description": "Chat agent.",
        "interfaces": ["abstractcode.agent.v1"],
        "nodes": [
            {"id": "node-1", "type": "on_flow_start", "data": {"nodeType": "on_flow_start", "outputs": [{"id": "exec-out", "label": "", "type": "execution"}, *pins(_START)]}},
            {"id": "end", "type": "on_flow_end", "data": {"nodeType": "on_flow_end", "inputs": [{"id": "exec-in", "label": "", "type": "execution"}, *pins(_END)]}},
        ],
        "edges": [],
        "entryNode": "node-1",
    }


def agent_subflow():
    return agent_subflow_from_flow(flow_id=AGENT_COPY_ID, bundle_ref=f"{AGENT_BUNDLE_ID}@{AGENT_VERSION}", flow=agent_flow())


def managed_flow() -> Dict[str, Any]:
    """This build's orchestrator, calling the stored copy of basic-agent."""
    return normalized_managed_visualflow(agent_subflow())


def stored_agent_copy() -> Dict[str, Any]:
    """The copy of basic-agent the app keeps in the flow store, as it stores it."""
    payload = AssistantGatewayService._agent_copy_payload(
        agent_flow(), fid=AGENT_ENTRY, version=AGENT_VERSION, copy_ids={AGENT_ENTRY: AGENT_COPY_ID}
    )
    return {"id": AGENT_COPY_ID, **payload}


class AgentBundleMixin:
    """get_bundle / get_bundle_flow answering for basic-agent, as the gateway does."""

    def get_bundle(self, bundle_id: str) -> Dict[str, Any]:
        assert bundle_id == AGENT_BUNDLE_ID
        return {"bundle_id": AGENT_BUNDLE_ID, "bundle_version": AGENT_VERSION, "default_entrypoint": AGENT_ENTRY, "flows": [AGENT_ENTRY]}

    def get_bundle_flow(self, bundle_id: str, flow_id: str, *, bundle_version: str) -> Dict[str, Any]:
        assert (bundle_id, flow_id, bundle_version) == (AGENT_BUNDLE_ID, AGENT_ENTRY, AGENT_VERSION)
        return {"bundle_id": bundle_id, "flow_id": flow_id, "flow": copy.deepcopy(agent_flow())}


def with_agent_copy(flows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [stored_agent_copy(), *flows]
