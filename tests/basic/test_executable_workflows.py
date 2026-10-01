"""The workflow list is the gateway's ``executable_for`` answer (operator 2026-10-01).

Which workflows the Assistant offers is decided by the GATEWAY: the admin's
availability rules for shared workflows plus the person's own, filtered to the
assistant interface — ``GET /api/gateway/bundles?executable_for=abstractassistant.agent.v1``.
The app adds no "show all" path and no interface filter of its own; a gateway
that ignores the parameter is reported, never listed.
"""

from __future__ import annotations

import pytest

from abstractassistant.gateway import client as client_mod
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig
from abstractassistant.gateway_service import (
    ASSISTANT_INTERFACE,
    MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
    AssistantGatewayService,
    executable_contract_problem,
)


def _item(bundle_id: str, version: str, flow_id: str, name: str, interfaces=None, owner="gateway") -> dict:
    return {
        "bundle_id": bundle_id,
        "bundle_version": version,
        "registry_scope": "private",
        "owner": {"kind": owner, "user_id": None if owner == "gateway" else "u1"},
        "shipped": owner == "gateway",
        "entrypoints": [{"flow_id": flow_id, "name": name, "interfaces": interfaces or [ASSISTANT_INTERFACE]}],
    }


class _Gateway:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.asked: list[str] = []

    def executable_bundles(self, interface: str) -> dict:
        self.asked.append(interface)
        return self.payload


def _ok(items: list[dict]) -> dict:
    return {"executable_for": ASSISTANT_INTERFACE, "items": items, "default_agent_workflows": {}}


@pytest.mark.basic
def test_client_asks_bundles_with_executable_for(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(client_mod, "_request_json", lambda **kw: calls.append(kw) or {"items": []})
    gw = GatewayClient(GatewayClientConfig(base_url="http://gateway", auth_token="tok"))
    gw.executable_bundles(ASSISTANT_INTERFACE)
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == "http://gateway/api/gateway/bundles?executable_for=abstractassistant.agent.v1"
    with pytest.raises(ValueError):
        gw.executable_bundles("")


@pytest.mark.basic
def test_the_list_is_exactly_the_gateways_answer() -> None:
    gateway = _Gateway(
        _ok(
            [
                _item(MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID, "0.0.4", "main", "AbstractAssistant"),
                _item("research-agent", "1.10.0", "agent", "Research agent", [ASSISTANT_INTERFACE, "abstractcode.agent.v1"]),
                _item("my-agent", "0.1.0", "m", "My agent", owner="user"),
            ]
        )
    )
    service = AssistantGatewayService(gateway)
    options, error = service._catalog_workflows()
    assert error == ""
    assert gateway.asked == [ASSISTANT_INTERFACE]
    assert sorted((o.bundle_id, o.flow_id, o.registry_scope) for o in options) == [
        (MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID, "main", "private"),
        ("my-agent", "m", "private"),
        ("research-agent", "agent", "private"),
    ]


@pytest.mark.basic
@pytest.mark.parametrize(
    ("payload", "needle"),
    [
        # A bundle without the interface never appears: its presence means the
        # gateway ignored executable_for, which is reported instead of listed.
        (_ok([_item("prompt-only", "1.0.0", "p", "Prompt", ["chat"])]), "does not declare abstractassistant.agent.v1"),
        ({"items": [_item("a", "1", "f", "A")]}, "does not filter workflows per app"),
        ({**_ok([]), "executable_for": "abstractcode.agent.v1"}, "not abstractassistant.agent.v1"),
        (_ok([{**_item("a", "1", "f", "A"), "owner": None}]), "owner missing"),
        (_ok([{k: v for k, v in _item("a", "1", "f", "A").items() if k != "shipped"}]), "shipped missing"),
        ([], "not a JSON object"),
    ],
)
def test_a_gateway_that_breaks_the_contract_is_reported_not_listed(payload, needle) -> None:
    assert needle in executable_contract_problem(payload, ASSISTANT_INTERFACE)
    options, error = AssistantGatewayService(_Gateway(payload))._catalog_workflows()
    assert options == []
    assert needle in error


@pytest.mark.basic
def test_no_show_all_and_no_client_side_interface_filter_in_the_service() -> None:
    import inspect

    import abstractassistant.gateway_service as svc

    source = inspect.getsource(svc.AssistantGatewayService._catalog_workflows)
    assert "executable_bundles(ASSISTANT_INTERFACE)" in source
    assert "workflow_catalog(" not in source
    assert "ASSISTANT_INTERFACE not in" not in source
