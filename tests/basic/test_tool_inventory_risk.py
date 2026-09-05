"""Tool inventory: the gateway's availability + risk classification is the
policy of record; the assistant displays it and never out-votes it."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from abstractassistant.controller import AssistantController
from abstractassistant.core.tool_risk import describe_tool_risk, risk_rank


def _controller(items, *, saved=None) -> AssistantController:
    c = object.__new__(AssistantController)
    c._cache_ttl_s = 20.0
    c._cache_epoch = 0
    c._tool_inventory_cache = None
    c._tool_inventory_cache_at = 0.0
    c._cache_lock = threading.RLock()
    c.gateway = SimpleNamespace(discovery_tools=lambda: {"items": items, "tool_mode": "approval"})
    c.preferences = SimpleNamespace(tool_preferences=dict(saved or {}))
    c.session_tool_auto_approval_active = lambda **_: False  # type: ignore[method-assign]
    return c


_LIVE_SHAPE = [
    {"name": "read_file", "toolset": "files", "enabled": True, "approval_default": "auto", "risk_tier": "observe", "risk_rank": 1, "mutating": False},
    {"name": "fetch_url", "toolset": "web", "enabled": True, "approval_default": "ask", "risk_tier": "act", "risk_rank": 2, "remote_write_capable": True},
    {"name": "execute_command", "toolset": "system", "enabled": True, "approval_default": "ask", "risk_tier": "destroy", "risk_rank": 4, "mutating": True, "destructive_capable": True},
    {"name": "send_email", "toolset": "comms.email", "enabled": False, "approval_default": "ask", "risk_tier": "outreach", "risk_rank": 3, "comms_send": True, "remote_write_capable": True},
]


@pytest.mark.basic
def test_gateway_approval_default_beats_the_local_fallback_lists() -> None:
    c = _controller(_LIVE_SHAPE)
    by_name = {item["name"]: item for item in c.tool_inventory()["items"]}

    # Local ToolApprovalPolicy lists say fetch_url and send_email are safe to
    # auto-approve; the gateway classifies both as ask -> the gateway wins.
    assert by_name["fetch_url"]["selected_mode"] == "ask"
    assert by_name["fetch_url"]["policy_source"] == "gateway"
    assert by_name["send_email"]["selected_mode"] == "ask"
    assert by_name["read_file"]["selected_mode"] == "approve"
    assert by_name["execute_command"]["selected_mode"] == "ask"
    # Risk metadata rides through untouched for the UI.
    assert by_name["execute_command"]["risk_tier"] == "destroy"
    assert by_name["execute_command"]["destructive_capable"] is True
    assert by_name["send_email"]["available"] is False


@pytest.mark.basic
def test_local_fallback_applies_only_when_the_gateway_omits_approval_default() -> None:
    legacy = [
        {"name": "read_file", "toolset": "files"},
        {"name": "write_file", "toolset": "files"},
        {"name": "brand_new_tool", "toolset": "misc"},
    ]
    by_name = {item["name"]: item for item in _controller(legacy).tool_inventory()["items"]}
    assert by_name["read_file"]["selected_mode"] == "approve"
    assert by_name["read_file"]["policy_source"] == "local"
    assert by_name["write_file"]["selected_mode"] == "ask"
    assert by_name["brand_new_tool"]["selected_mode"] == "ask"  # unknown -> ask, never auto
    assert by_name["read_file"]["available"] is True  # no `enabled` field -> assumed available


@pytest.mark.basic
def test_saved_device_preference_still_wins_over_the_gateway_default() -> None:
    c = _controller(_LIVE_SHAPE, saved={"fetch_url": "approve", "read_file": "disabled"})
    by_name = {item["name"]: item for item in c.tool_inventory()["items"]}
    assert by_name["fetch_url"]["selected_mode"] == "approve"
    assert by_name["fetch_url"]["policy_default"] == "ask"  # the default is still reported honestly
    assert by_name["read_file"]["selected_mode"] == "disabled"


@pytest.mark.basic
def test_gateway_disabled_tools_never_ride_a_run() -> None:
    c = _controller(_LIVE_SHAPE, saved={"send_email": "approve"})
    assert "send_email" not in c.allowed_tools_for_run()
    policy = c.tool_policy_for_run()
    assert "send_email" not in policy["auto_approve_tools"]
    assert "send_email" not in policy["require_approval_tools"]
    assert c.allowed_tools_for_run() == ["read_file", "execute_command", "fetch_url"]
    assert c.tool_inventory_by_name()["fetch_url"]["risk_tier"] == "act"


@pytest.mark.basic
def test_describe_tool_risk_turns_gateway_flags_into_one_honest_sentence() -> None:
    destroy = describe_tool_risk(_LIVE_SHAPE[2])
    assert destroy["label"] == "Destructive"
    assert destroy["tone"] == "destroy"
    assert destroy["rank"] == 4
    assert "can delete or overwrite" in destroy["facts"]
    assert destroy["sentence"].startswith("Destructive; can delete or overwrite")
    assert destroy["sentence"].endswith("asks before running it by default.")

    outreach = describe_tool_risk(_LIVE_SHAPE[3])
    assert outreach["label"] == "Reaches outside"
    assert "sends messages on your behalf" in outreach["facts"]

    observe = describe_tool_risk(_LIVE_SHAPE[0])
    assert observe["facts"] == ["read-only"]
    assert observe["sentence"] == "Reads only; read-only — the gateway runs it without asking by default."

    unknown = describe_tool_risk({"name": "mystery"})
    assert unknown["label"] == "Risk not classified"
    assert unknown["tone"] == "unknown"
    assert unknown["sentence"] == ""
    assert risk_rank(None) == 0
