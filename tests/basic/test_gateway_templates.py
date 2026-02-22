"""Gateway templates unit tests."""

import pytest

from abstractassistant.gateway.templates import list_agent_entrypoints


@pytest.mark.basic
def test_list_agent_entrypoints_filters_agent_interface() -> None:
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
    assert len(out) == 1
    assert out[0]["bundle_id"] == "b1"
    assert out[0]["flow_id"] == "f1"
