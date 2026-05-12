"""Gateway templates unit tests."""

import pytest

from abstractassistant.gateway.templates import list_agent_entrypoints, select_agent_template


@pytest.mark.basic
def test_list_agent_entrypoints_lists_all_with_agent_first() -> None:
    bundles = {
        "items": [
            {
                "bundle_id": "b1",
                "entrypoints": [
                    {"flow_id": "f1", "interfaces": ["abstractcode.agent.v1"], "name": "Agent"},
                    {"flow_id": "f2", "interfaces": ["other.interface"], "name": "Other"},
                ],
            }
        ]
    }
    out = list_agent_entrypoints(bundles_response=bundles)
    assert len(out) == 2
    assert out[0]["bundle_id"] == "b1"
    assert out[0]["flow_id"] == "f1"
    assert out[1]["bundle_id"] == "b1"
    assert out[1]["flow_id"] == "f2"


@pytest.mark.basic
def test_list_agent_entrypoints_prefers_assistant_interfaces() -> None:
    bundles = {
        "items": [
            {
                "bundle_id": "legacy",
                "entrypoints": [
                    {"flow_id": "code", "interfaces": ["abstractcode.agent.v1"], "name": "Code Agent"},
                ],
            },
            {
                "bundle_id": "assistant",
                "entrypoints": [
                    {"flow_id": "native", "interfaces": ["abstractassistant.agent.v1"], "name": "Native Agent"},
                ],
            },
            {
                "bundle_id": "shared",
                "entrypoints": [
                    {"flow_id": "generic", "interfaces": ["abstract.agent.v1"], "name": "Generic Agent"},
                ],
            },
        ]
    }

    out = list_agent_entrypoints(bundles_response=bundles)

    assert [x["agent_interface"] for x in out] == [
        "abstractassistant.agent.v1",
        "abstract.agent.v1",
        "abstractcode.agent.v1",
    ]


@pytest.mark.basic
def test_select_agent_template_prefers_gateway_default_entrypoint() -> None:
    bundles = {
        "default_bundle_id": "b2",
        "items": [
            {
                "bundle_id": "b1",
                "default_entrypoint": "f1",
                "entrypoints": [
                    {"flow_id": "f1", "interfaces": ["abstractcode.agent.v1"], "name": "Agent 1"},
                ],
            },
            {
                "bundle_id": "b2",
                "default_entrypoint": "f2",
                "entrypoints": [
                    {"flow_id": "f2", "interfaces": ["abstractcode.agent.v1"], "name": "Agent 2"},
                ],
            },
        ],
    }

    selected = select_agent_template(bundles_response=bundles, bundle_id="", flow_id="")

    assert selected == {"bundle_id": "b2", "flow_id": "f2"}


@pytest.mark.basic
def test_select_agent_template_prefers_assistant_native_over_gateway_default_legacy() -> None:
    bundles = {
        "default_bundle_id": "legacy",
        "items": [
            {
                "bundle_id": "legacy",
                "default_entrypoint": "code",
                "entrypoints": [
                    {"flow_id": "code", "interfaces": ["abstractcode.agent.v1"], "name": "Legacy"},
                ],
            },
            {
                "bundle_id": "native",
                "default_entrypoint": "assistant",
                "entrypoints": [
                    {"flow_id": "assistant", "interfaces": ["abstractassistant.agent.v1"], "name": "Native"},
                ],
            },
        ],
    }

    selected = select_agent_template(bundles_response=bundles, bundle_id="", flow_id="")

    assert selected == {"bundle_id": "native", "flow_id": "assistant"}


@pytest.mark.basic
def test_select_agent_template_reports_missing_agent_entrypoints_with_gateway_hint() -> None:
    with pytest.raises(RuntimeError, match="ABSTRACTGATEWAY_FLOWS_DIR"):
        select_agent_template(bundles_response={"items": []}, bundle_id="", flow_id="")
