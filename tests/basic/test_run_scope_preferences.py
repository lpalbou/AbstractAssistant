"""Run scope preferences: reasoning effort + reply streaming + voice options.

These are LOCAL, PERSISTENT overrides of gateway defaults (the gateway stays
the source of truth for what is configurable): they live in preferences.json
and ride each run as input pins. Blank means "gateway default: send nothing" —
except streaming, which is app-specific and always explicit (R11.4). No
workspace preference: the gateway holds the account and chat workspaces (R11).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from abstractassistant.controller import AssistantController
from abstractassistant.gateway.run_input import build_run_input_data
from abstractassistant.preferences import (
    REASONING_EFFORT_LEVELS,
    AssistantPreferences,
    PreferencesStore,
    WorkflowSelection,
    normalize_workspace_path,
)


@pytest.mark.basic
def test_preferences_round_trip_keeps_run_scope_and_voice_fields(tmp_path: Path) -> None:
    store = PreferencesStore(tmp_path / "preferences.json")
    prefs = AssistantPreferences(
        reasoning_effort="high",
        stream_replies="off",
        voice_auto_send=False,
        voice_spoken_replies=False,
    )

    store.save(prefs)
    loaded = store.load()

    assert loaded == prefs
    assert loaded.run_scope() == {
        "thinking": "high",
        "stream": False,
    }


@pytest.mark.basic
def test_preferences_defaults_mean_gateway_defaults() -> None:
    prefs = AssistantPreferences.from_dict({})
    assert prefs.reasoning_effort == ""
    assert not hasattr(prefs, "workspace_root")  # R11: no run-workspace preference
    assert prefs.voice_auto_send is True
    assert prefs.voice_spoken_replies is True
    assert prefs.run_scope() == {
        "thinking": "",
        "stream": True,  # "Stream replies" is on by default and always sent
    }


@pytest.mark.basic
def test_preferences_normalize_reasoning_and_mode_against_the_contract() -> None:
    assert AssistantPreferences.from_dict({"reasoning_effort": "HIGH"}).reasoning_effort == "high"
    assert AssistantPreferences.from_dict({"reasoning_effort": "turbo"}).reasoning_effort == ""
    # Round 9: no access modes and no local allowed-folder list (the account's gateway policy decides).
    assert not hasattr(AssistantPreferences.from_dict({"workspace_access_mode": "workspace_only"}), "workspace_access_mode")
    assert not hasattr(AssistantPreferences(), "workspace_allowed_paths")
    assert set(REASONING_EFFORT_LEVELS) == {"none", "minimal", "low", "medium", "high", "xhigh"}


@pytest.mark.basic
def test_workspace_paths_are_canonical_absolute_and_deduplicated(tmp_path: Path) -> None:
    home = tmp_path / "home"
    assert normalize_workspace_path("~", home=home) == str(home)
    assert normalize_workspace_path("~/docs/", home=home) == str(home / "docs")
    assert normalize_workspace_path("~other/docs", home=home) == ""  # another user's home is unknown
    assert normalize_workspace_path("relative/path", home=home) == ""  # ambiguous on the gateway host
    assert normalize_workspace_path("/srv/data///", home=home) == "/srv/data"
    assert normalize_workspace_path("/", home=home) == "/"
    assert normalize_workspace_path("   ", home=home) == ""

    # An older preferences.json that saved a run workspace: ignored, never sent.
    prefs = AssistantPreferences.from_dict({"workspace_root": "/Users/me/site"})
    assert "workspace_root" not in prefs.to_dict() and "workspace_root" not in prefs.run_scope()


@pytest.mark.basic
def test_build_run_input_rides_thinking_on_the_runtime_lane_only() -> None:
    payload = build_run_input_data(prompt="hi", thinking="medium")
    assert payload["_runtime"]["thinking"] == "medium"
    # The documented inheritance lane is _runtime; a top-level pin would need
    # a flow input the orchestrator does not declare.
    assert "thinking" not in payload

    blank = build_run_input_data(prompt="hi", thinking="")
    assert "thinking" not in blank["_runtime"]


@pytest.mark.basic
def test_build_run_input_rides_workspace_scope_as_top_level_pins() -> None:
    payload = build_run_input_data(prompt="hi", workspace_root="/Users/me/site")
    assert payload["workspace_root"] == "/Users/me/site"
    # Round 9: no access mode, no per-run folder list (the account's gateway policy applies).
    assert "workspace_access_mode" not in payload and "workspace_allowed_paths" not in payload

    blank = build_run_input_data(prompt="hi")
    assert "workspace_root" not in blank
    assert "workspace_access_mode" not in blank
    assert "workspace_allowed_paths" not in blank


def _controller_with_prefs(monkeypatch: pytest.MonkeyPatch, captured: dict, prefs: AssistantPreferences) -> AssistantController:
    class _WorkerCapture:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("abstractassistant.controller.GatewayWorker", _WorkerCapture)
    controller = object.__new__(AssistantController)
    controller.llm_manager = object()
    controller.debug = False
    controller.preferences = prefs
    controller.current_workflow = lambda: WorkflowSelection(  # type: ignore[method-assign]
        bundle_id="abstractassistant-orchestrator", flow_id="chat", bundle_version="1", registry_scope="tenant_catalog"
    )
    controller.allowed_tools_for_run = lambda: []  # type: ignore[method-assign]
    controller.tool_policy_for_run = lambda: {}  # type: ignore[method-assign]
    controller.latest_image_artifact = lambda: None  # type: ignore[method-assign]
    controller.route_override = lambda key: None  # type: ignore[method-assign]
    return controller


@pytest.mark.basic
def test_controller_build_chat_worker_passes_run_scope_from_preferences(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    prefs = AssistantPreferences(
        reasoning_effort="xhigh",
        speculation=False,
    )
    controller = _controller_with_prefs(monkeypatch, captured, prefs)
    controller.llm_manager = SimpleNamespace(session_workspace_root=lambda: "/gw/workspaces/session-abc")

    controller.build_chat_worker(prompt="Hello")

    assert captured["thinking"] == "xhigh"
    assert captured["speculation"] is False
    # The chat's own private workspace (the gateway's), never a device path.
    assert captured["workspace_root"] == "/gw/workspaces/session-abc"
    assert "workspace_access_mode" not in captured and "workspace_allowed_paths" not in captured


@pytest.mark.basic
def test_controller_build_chat_worker_sends_nothing_for_gateway_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    controller = _controller_with_prefs(monkeypatch, captured, AssistantPreferences())

    controller.build_chat_worker(prompt="Hello")

    assert captured["thinking"] == ""
    assert captured["workspace_root"] == ""
    assert "workspace_access_mode" not in captured and "workspace_allowed_paths" not in captured


@pytest.mark.basic
def test_controller_update_preferences_keeps_untouched_fields(tmp_path: Path) -> None:
    """A partial save (the header auto-speak toggle, a single settings row) must
    never wipe the fields it did not name — the overrides in particular."""
    controller = object.__new__(AssistantController)
    controller.preferences_store = PreferencesStore(tmp_path / "preferences.json")
    controller.preferences = AssistantPreferences(
        route_overrides={"output.text": {"provider": "lmstudio", "model": "qwen3"}},
        reasoning_effort="low",
        stream_replies="off",
        tool_preferences={"read_file": "approve"},
    )
    controller.voice_manager = SimpleNamespace(set_quality_preset=lambda preset: None)

    updated = controller.update_preferences(auto_speak=True)

    assert updated.auto_speak is True
    assert updated.route_overrides == {"output.text": {"provider": "lmstudio", "model": "qwen3"}}
    assert updated.reasoning_effort == "low"
    assert updated.stream_replies == "off"
    assert updated.tool_preferences == {"read_file": "approve"}
    assert controller.preferences_store.load() == updated


@pytest.mark.basic
def test_controller_reasoning_levels_prefer_the_live_contract() -> None:
    controller = object.__new__(AssistantController)
    caps = SimpleNamespace(
        common={"runs": {"start": {"thinking_control": {"values": ["none", "low", "high"]}}}}
    )
    controller.llm_manager = SimpleNamespace(gateway_capabilities=lambda **kw: caps)
    assert controller.reasoning_levels() == ["none", "low", "high"]

    # Unreachable gateway -> the contract's known ladder, never an empty dial.
    controller.llm_manager = SimpleNamespace(gateway_capabilities=lambda **kw: (_ for _ in ()).throw(RuntimeError("down")))
    assert controller.reasoning_levels() == list(REASONING_EFFORT_LEVELS)


@pytest.mark.basic
def test_controller_workspace_policy_is_tolerant() -> None:
    controller = object.__new__(AssistantController)
    controller._cache_ttl_s = 20.0
    controller._cache_epoch = 0
    controller._workspace_policy_cache = None
    controller._workspace_policy_cache_at = 0.0
    import threading

    controller._cache_lock = threading.RLock()
    controller.llm_manager = SimpleNamespace(active_session_id="session-1")
    controller.gateway = SimpleNamespace(
        workspace_account_policy=lambda account="me": (_ for _ in ()).throw(RuntimeError("403 forbidden")),
        session_workspaces=lambda sid: {"ok": True, "policy": {"configured": False}},  # an older shape
    )
    controller.gateway_service = SimpleNamespace(describe_connection_issue=lambda exc: str(exc))

    out = controller.workspace_policy()

    assert out["account"]["state"] is None
    assert "403" in out["account"]["error"]
    assert out["session"]["state"] is None and out["session"]["session_id"] == "session-1"
    assert "round-11 workspace model" in out["session"]["error"]
    assert not hasattr(controller, "workspace_access_modes")
