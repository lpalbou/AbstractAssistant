"""Regression pin (2026-09-17): two builds of the app must not fight over the workflow.

The app reconciles its managed workflow at launch — if the gateway's stored copy differs
from this build's, it republishes and promotes it as the catalog default. Nothing ordered
the two, so an OLDER build "fixed the drift" by DOWNGRADING a newer workflow, and the newer
build put it back on its next launch. Measured in the gateway audit log: the installed app
(Sep 7 build) and the source tree flipped the default four times in 17 minutes.

Each flip is expensive far beyond the app: the gateway rebuilds its whole host on
publish/promote, which reloads a 15 GB model on its event loop — 40-60 s during which
`/api/health` goes unanswered — and replaces the provider object that holds every
in-process prompt cache. "Relaunching the assistant lost my cache" was literally true.

A build now publishes only when its revision is >= the stored one.
"""

from __future__ import annotations

import copy

import pytest

from abstractassistant import assistant_workflow as wf
from abstractassistant.gateway_service import AssistantGatewayService
from test_assistant_palette import _ManagedWorkflowGatewayStub  # sibling test module (rootdir-prepended)


def _service_with_published_workflow():
    gateway = _ManagedWorkflowGatewayStub()
    AssistantGatewayService(gateway).ensure_catalog_workflow()  # first launch: create + publish
    assert len(gateway.published) == 1
    return gateway


def _relaunch(gateway) -> None:
    AssistantGatewayService(gateway).ensure_catalog_workflow()  # a new process reconciles again


def test_the_workflow_declares_its_revision() -> None:
    flow = wf.normalized_managed_visualflow()
    assert wf.managed_workflow_revision_of(flow) == wf.MANAGED_ASSISTANT_WORKFLOW_REVISION >= 2
    assert wf.MANAGED_ASSISTANT_WORKFLOW_MARKER in flow["description"]
    # A workflow published before revisions existed declares none: that is revision 1.
    assert wf.managed_workflow_revision_of({"description": wf.MANAGED_ASSISTANT_WORKFLOW_MARKER}) == 1
    assert wf.managed_workflow_revision_of(None) == 1


def test_an_unchanged_workflow_is_never_republished() -> None:
    gateway = _service_with_published_workflow()
    _relaunch(gateway)
    _relaunch(gateway)
    assert len(gateway.published) == 1 and gateway.updated == []


def test_a_build_never_downgrades_a_newer_stored_workflow() -> None:
    gateway = _service_with_published_workflow()
    newer = copy.deepcopy(gateway._flows[0])
    newer["description"] = newer["description"].replace(
        f"workflow-revision={wf.MANAGED_ASSISTANT_WORKFLOW_REVISION}",
        f"workflow-revision={wf.MANAGED_ASSISTANT_WORKFLOW_REVISION + 1}",
    )
    newer["nodes"] = list(newer["nodes"])[:-1]  # and it genuinely differs from this build's
    gateway._flows = [newer]

    with pytest.warns(UserWarning, match="newer AbstractAssistant workflow"):
        workflows = AssistantGatewayService(gateway).ensure_catalog_workflow()

    assert workflows, "the newer workflow is USED, not refused"
    assert len(gateway.published) == 1 and gateway.updated == [] and len(gateway.promoted) == 1
    assert gateway._flows == [newer]


def test_an_older_stored_workflow_is_upgraded_once() -> None:
    gateway = _service_with_published_workflow()
    older = copy.deepcopy(gateway._flows[0])
    older["description"] = older["description"].split(";workflow-revision=")[0]  # pre-revision build
    gateway._flows = [older]

    _relaunch(gateway)
    assert len(gateway.updated) == 1 and len(gateway.published) == 2
    _relaunch(gateway)
    assert len(gateway.updated) == 1 and len(gateway.published) == 2  # and it settles


def test_toolless_revision_two_is_upgraded_once() -> None:
    gateway = _service_with_published_workflow()
    older = copy.deepcopy(gateway._flows[0])
    older["description"] = older["description"].replace(
        f"workflow-revision={wf.MANAGED_ASSISTANT_WORKFLOW_REVISION}", "workflow-revision=2"
    )
    start = next(node for node in older["nodes"] if node["id"] == "start")
    start["data"]["pinDefaults"].pop("tools")
    gateway._flows = [older]

    _relaunch(gateway)
    upgraded = next(node for node in gateway._flows[0]["nodes"] if node["id"] == "start")
    assert "web_search" in upgraded["data"]["pinDefaults"]["tools"]
    assert len(gateway.updated) == 1 and len(gateway.published) == 2
    _relaunch(gateway)
    assert len(gateway.updated) == 1 and len(gateway.published) == 2
