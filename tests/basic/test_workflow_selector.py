"""Settings → Workflow and the gateway's default agent workflow (contract D).

* The gateway reports ``default_agent_workflows["abstractassistant.agent.v1"]``
  on ``/workflow-catalog``. When it has one, the default choice ("@default")
  starts runs with ``flow_id: "@default", interface: "abstractassistant.agent.v1"``
  and the gateway resolves it at every run start.
* When it has none (``available: false`` — amendment A-4 — or an older gateway
  without the field) the built-in orchestrator runs, labelled as such.
* A workflow picked in Settings runs its latest published version; if it left
  the catalog nothing runs and the reason is shown (no silent swap).
* The app no longer promotes its managed bundle to catalog default.
"""

from __future__ import annotations

import os

import pytest

from abstractassistant.assistant_workflow import ASSISTANT_INTERFACE, MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
from abstractassistant.controller import AssistantController
from abstractassistant.gateway_service import AssistantGatewayService
from abstractassistant.preferences import (
    WORKFLOW_GATEWAY_DEFAULT,
    AssistantPreferences,
    normalize_workflow_choice,
)


def _entry(bundle_id: str, version: str, flow_id: str, name: str) -> dict:
    return {
        "bundle_id": bundle_id,
        "bundle_version": version,
        "default_entrypoint": flow_id,
        "is_default": False,
        "actions": {"can_run": True},
        "entrypoints": [{"flow_id": flow_id, "name": name, "interfaces": [ASSISTANT_INTERFACE]}],
    }


class _Gateway:
    """Only what list_workflows reads. No list_visualflows: the managed drift
    check then keeps the catalog version (no publish in these tests)."""

    def __init__(self, default: object = "absent") -> None:
        self.default = default
        self.items = [
            _entry(MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID, "0.0.3", "main", "AbstractAssistant"),
            _entry(MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID, "0.0.4", "main", "AbstractAssistant"),
            _entry("research-agent", "1.2.0", "agent", "Research agent"),
            _entry("research-agent", "1.10.0", "agent", "Research agent"),
        ]

    def workflow_catalog(self, *, scope: str = "tenant_catalog") -> dict:
        payload: dict = {"items": list(self.items)}
        if self.default != "absent":
            payload["default_agent_workflows"] = self.default
        return payload


_REPORTED = {
    ASSISTANT_INTERFACE: {
        "workflow_id": "research-agent@1.10.0:agent",
        "bundle_id": "research-agent",
        "bundle_version": "1.10.0",
        "flow_id": "agent",
        "registry_scope": "tenant_catalog",
        "name": "Research agent",
        "source": "stored",
    }
}
_NOT_SET = {
    ASSISTANT_INTERFACE: {
        "available": False,
        "reason": "no host workflow declares abstractassistant.agent.v1; the Assistant uses its built-in orchestrator",
        "source": "default",
    }
}


def _controller(gateway: _Gateway, choice=WORKFLOW_GATEWAY_DEFAULT) -> AssistantController:
    controller = object.__new__(AssistantController)
    service = AssistantGatewayService(gateway)
    controller.gateway_service = service
    controller.preferences = AssistantPreferences(hotkey_enabled=False, workflow=choice)
    controller.workflow_options = service.list_workflows  # type: ignore[method-assign]
    saved: list = []
    controller.update_preferences = lambda **kw: saved.append(kw) or setattr(  # type: ignore[method-assign]
        controller, "preferences", AssistantPreferences.from_dict({**controller.preferences.to_dict(), **kw})
    )
    controller._saved = saved  # type: ignore[attr-defined]
    return controller


@pytest.mark.basic
def test_catalog_offers_each_workflow_once_at_its_latest_version_built_in_first() -> None:
    rows = AssistantGatewayService(_Gateway()).list_workflows()
    assert [(r.bundle_id, r.bundle_version) for r in rows] == [
        (MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID, "0.0.4"),
        ("research-agent", "1.10.0"),
    ]


@pytest.mark.basic
@pytest.mark.parametrize(
    ("default", "reported", "available"),
    [("absent", False, False), ({}, True, False), (_NOT_SET, True, False), (_REPORTED, True, True)],
)
def test_the_gateway_default_is_parsed_from_the_catalog_envelope(default, reported, available) -> None:
    service = AssistantGatewayService(_Gateway(default))
    service.list_workflows()
    info = service.gateway_default_workflow()
    assert (info.reported, info.available) == (reported, available)
    if available:
        assert (info.bundle_id, info.bundle_version, info.flow_id, info.source) == ("research-agent", "1.10.0", "agent", "stored")


@pytest.mark.basic
def test_default_choice_with_a_gateway_default_sends_the_sentinel() -> None:
    selection = _controller(_Gateway(_REPORTED)).current_workflow()
    assert selection is not None
    assert selection.flow_id == "@default" and selection.is_gateway_default
    assert selection.interface == ASSISTANT_INTERFACE
    assert selection.source == "gateway_default"
    assert selection.label == "Research agent"


@pytest.mark.basic
@pytest.mark.parametrize("default", ["absent", _NOT_SET])
def test_default_choice_without_a_gateway_default_runs_the_built_in(default) -> None:
    controller = _controller(_Gateway(default))
    selection = controller.current_workflow()
    assert selection is not None
    assert (selection.bundle_id, selection.bundle_version, selection.flow_id) == (
        MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
        "0.0.4",
        "main",
    )
    assert selection.source == "built_in"
    menu = controller.workflow_menu()
    assert menu[0]["choice"] == WORKFLOW_GATEWAY_DEFAULT
    assert menu[0]["label"] == "Gateway default → Built-in orchestrator @0.0.4"
    assert controller.workflow_status().error == ""


@pytest.mark.basic
def test_menu_lists_the_gateway_default_first_then_every_workflow() -> None:
    menu = _controller(_Gateway(_REPORTED)).workflow_menu()
    assert [row["label"] for row in menu] == [
        "Gateway default → Research agent @1.10.0",
        "Built-in orchestrator @0.0.4",
        "Research agent @1.10.0 — research-agent",
    ]
    assert "source: stored" in menu[0]["detail"]
    assert menu[2]["choice"] == {"bundle_id": "research-agent", "flow_id": "agent", "registry_scope": "tenant_catalog"}


@pytest.mark.basic
def test_a_chosen_workflow_runs_its_latest_version_and_is_saved_without_one() -> None:
    controller = _controller(_Gateway(_REPORTED))
    controller.set_workflow_choice({"bundle_id": "research-agent", "flow_id": "agent", "bundle_version": "1.2.0"})
    assert controller.preferences.workflow == {"bundle_id": "research-agent", "flow_id": "agent", "registry_scope": "tenant_catalog"}
    selection = controller.current_workflow()
    assert (selection.bundle_id, selection.bundle_version, selection.flow_id, selection.source) == (
        "research-agent",
        "1.10.0",
        "agent",
        "chosen",
    )
    assert not selection.is_gateway_default


@pytest.mark.basic
def test_a_chosen_workflow_that_left_the_catalog_blocks_with_a_reason() -> None:
    controller = _controller(_Gateway(_REPORTED), choice={"bundle_id": "gone", "flow_id": "x"})
    assert controller.current_workflow() is None
    error = controller.workflow_status().error
    assert "gone:x" in error and "Settings" in error


@pytest.mark.basic
def test_workflow_choice_round_trips_through_the_preferences_file(tmp_path) -> None:
    from abstractassistant.preferences import PreferencesStore

    store = PreferencesStore(tmp_path / "preferences.json")
    assert store.load().workflow == WORKFLOW_GATEWAY_DEFAULT
    store.save(AssistantPreferences(workflow={"bundle_id": "b", "flow_id": "f"}))
    assert store.load().workflow == {"bundle_id": "b", "flow_id": "f", "registry_scope": "tenant_catalog"}
    assert normalize_workflow_choice({"bundle_id": "b"}) == WORKFLOW_GATEWAY_DEFAULT
    assert normalize_workflow_choice("anything") == WORKFLOW_GATEWAY_DEFAULT


@pytest.mark.basic
def test_start_run_sends_the_sentinel_with_its_interface_and_keeps_resolved_workflow() -> None:
    from abstractassistant.gateway import GatewayClient, GatewayClientConfig

    client = GatewayClient(GatewayClientConfig(base_url="http://127.0.0.1:1"))
    sent: list = []
    resolved = {"workflow_id": "research-agent@1.10.0:agent", "bundle_id": "research-agent", "source": "gateway_default"}
    client._request_json = lambda **kw: sent.append(kw) or {"run_id": "run-1", "resolved_workflow": resolved}  # type: ignore[method-assign]

    assert client.start_run(flow_id="@default", interface=ASSISTANT_INTERFACE, input_data={"prompt": "hi"}) == "run-1"
    body = sent[0]["body"]
    assert body["flow_id"] == "@default" and body["interface"] == ASSISTANT_INTERFACE
    assert "bundle_id" not in body and "bundle_version" not in body
    assert client.last_resolved_workflow == resolved
    with pytest.raises(ValueError, match="requires an interface"):
        client.start_run(flow_id="@default", input_data={})


@pytest.mark.basic
def test_worker_entrypoint_for_the_gateway_default() -> None:
    from abstractassistant.ui.gateway_worker import GatewayWorker

    worker = GatewayWorker.__new__(GatewayWorker)
    worker._bundle_id, worker._flow_id, worker._bundle_version = "research-agent", "@default", "1.10.0"
    worker._registry_scope, worker._interface = "tenant_catalog", ASSISTANT_INTERFACE
    assert GatewayWorker._resolve_entrypoint(worker) == {"flow_id": "@default", "interface": ASSISTANT_INTERFACE}
    worker._interface = ""
    with pytest.raises(RuntimeError):
        GatewayWorker._resolve_entrypoint(worker)


@pytest.mark.basic
def test_build_chat_worker_passes_the_interface_only_for_the_sentinel(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr("abstractassistant.controller.GatewayWorker", lambda **kw: captured.update(kw))
    controller = _controller(_Gateway(_REPORTED))
    controller.llm_manager = object()
    controller.debug = False
    for name, value in {
        "allowed_tools_for_run": [],
        "tool_policy_for_run": {},
        "latest_image_artifact": None,
        "media_route_overrides": {},
        "run_scope": {},
        "route_override": None,
        "system_prompt_for_run": "",
    }.items():
        setattr(controller, name, (lambda v: (lambda *a, **k: v))(value))
    controller.build_chat_worker(prompt="hi")
    assert (captured["flow_id"], captured["interface"]) == ("@default", ASSISTANT_INTERFACE)
    controller.set_workflow_choice({"bundle_id": "research-agent", "flow_id": "agent"})
    controller.build_chat_worker(prompt="hi")
    assert (captured["flow_id"], captured["interface"], captured["bundle_version"]) == ("agent", "", "1.10.0")


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.mark.basic
def test_settings_workflow_card_saves_the_sentinel_or_a_workflow() -> None:
    pytest.importorskip("PyQt5.QtWidgets")
    from test_settings_pages import _dialog

    dlg, ctl = _dialog()
    real = _controller(_Gateway(_REPORTED))
    ctl.workflow_menu = real.workflow_menu
    ctl.workflow_choice = real.workflow_choice
    ctl.set_workflow_choice = real.set_workflow_choice
    dlg.show_section("models")
    page = dlg.page_models
    page.refresh()
    assert page.workflow_combo.count() == 3
    assert page.workflow_combo.itemText(0).startswith("Gateway default → Research agent")
    assert page.workflow_combo.currentIndex() == 0
    page.workflow_combo.setCurrentIndex(2)
    page._on_workflow_chosen(2)
    assert real.preferences.workflow["bundle_id"] == "research-agent"
    page._on_workflow_chosen(0)
    assert real.preferences.workflow == WORKFLOW_GATEWAY_DEFAULT


@pytest.mark.basic
def test_about_shows_the_workflow_and_what_the_last_turn_ran() -> None:
    pytest.importorskip("PyQt5.QtWidgets")
    import json

    from PyQt5.QtWidgets import QApplication
    from test_settings_pages import _dialog

    dlg, ctl = _dialog()
    real = _controller(_Gateway(_REPORTED))
    ctl.current_workflow = real.current_workflow
    ctl.last_resolved_workflow = lambda: {
        "bundle_id": "research-agent",
        "bundle_version": "1.10.0",
        "flow_id": "agent",
        "name": "Research agent",
        "source": "gateway_default",
    }
    dlg.show_section("about")
    dlg.page_about.refresh()
    assert dlg.page_about.workflow_label.text() == "Gateway default → Research agent @1.10.0 (research-agent)"
    assert "the gateway default" in dlg.page_about.resolved_label.text()
    dlg.page_about._copy_diagnostics()
    diag = json.loads(QApplication.clipboard().text())
    assert diag["resolved_workflow"]["bundle_id"] == "research-agent"
