"""The built-in orchestrator never shows a fake "@0.0.0" (E2E N4).

A gateway asked to publish without a version mints "0.0.0" for the first
one; that number is not a version of ours. Labels show the real published
version, or "(built-in)" without a number when there is none.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from abstractassistant.assistant_workflow import MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID as MANAGED
from abstractassistant.gateway_service import GatewayDefaultWorkflow, WorkflowOption, workflow_version_suffix


@pytest.mark.basic
@pytest.mark.parametrize(
    "bundle_id, version, named, expected",
    [
        (MANAGED, "0.0.3", False, " @0.0.3"),
        (MANAGED, "0.0.0", False, " (built-in)"),
        (MANAGED, "", False, " (built-in)"),
        (MANAGED, "0.0.0", True, ""),
        (MANAGED, "0.0.4", True, " @0.0.4"),
        ("someone-else", "0.0.0", False, " @0.0.0"),  # a third party's version is theirs
        ("someone-else", "", False, ""),
    ],
)
def test_version_suffix(bundle_id, version, named, expected) -> None:
    assert workflow_version_suffix(bundle_id, version, named_built_in=named) == expected


def _controller(tmp_path, monkeypatch, *, options, default):
    monkeypatch.setenv("HOME", str(tmp_path))
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController

    controller = AssistantController(config=Config(), data_dir=tmp_path / "data")
    monkeypatch.setattr(controller, "workflow_options", lambda: options)
    monkeypatch.setattr(controller, "gateway_default_workflow", lambda: default)
    return controller


def _managed(version: str) -> WorkflowOption:
    return WorkflowOption(bundle_id=MANAGED, flow_id="node-1", label="Assistant", registry_scope="tenant_catalog",
                          bundle_version=version)


@pytest.mark.basic
@pytest.mark.parametrize("version, shown", [("0.0.0", ""), ("", ""), ("0.0.7", " @0.0.7")])
def test_settings_workflow_rows_never_show_a_placeholder_version(tmp_path, monkeypatch, version, shown) -> None:
    controller = _controller(tmp_path, monkeypatch, options=[_managed(version)],
                             default=GatewayDefaultWorkflow(reported=True, available=False))
    labels = [row["label"] for row in controller.workflow_menu()]
    assert labels == [f"Gateway default (Built-in orchestrator{shown})", f"Built-in orchestrator{shown}"]
    assert all("0.0.0" not in label for label in labels)


@pytest.mark.basic
def test_a_gateway_default_naming_the_built_in_shows_built_in_not_zero(tmp_path, monkeypatch) -> None:
    default = GatewayDefaultWorkflow(reported=True, available=True, bundle_id=MANAGED, bundle_version="0.0.0",
                                     flow_id="node-1", name="Assistant", source="stored")
    controller = _controller(tmp_path, monkeypatch, options=[_managed("0.0.0")], default=default)
    assert controller.workflow_menu()[0]["label"] == "Gateway default (Assistant (built-in))"


@pytest.mark.basic
def test_about_page_lines_never_show_a_placeholder_version() -> None:
    pytest.importorskip("PyQt5.QtWidgets")
    from abstractassistant.ui.settings.pages import describe_resolved_workflow, describe_workflow_selection

    built_in = SimpleNamespace(bundle_id=MANAGED, flow_id="node-1", bundle_version="0.0.0", label="", source="built_in")
    assert describe_workflow_selection(built_in) == f"Built-in orchestrator ({MANAGED}:node-1)"
    built_in.bundle_version = "0.0.5"
    assert describe_workflow_selection(built_in) == f"Built-in orchestrator @0.0.5 ({MANAGED}:node-1)"
    via_default = SimpleNamespace(bundle_id=MANAGED, flow_id="@default", bundle_version="0.0.0", label="Assistant",
                                  source="gateway_default")
    assert describe_workflow_selection(via_default) == f"Gateway default → Assistant (built-in) ({MANAGED})"
    resolved = {"bundle_id": MANAGED, "bundle_version": "0.0.0", "flow_id": "node-1", "name": "Assistant",
                "source": "gateway_default"}
    assert describe_resolved_workflow(resolved) == f"Assistant (built-in) ({MANAGED}:node-1) — the gateway default"
    resolved["bundle_version"] = "0.0.2"
    assert "Assistant @0.0.2" in describe_resolved_workflow(resolved)
