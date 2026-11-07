"""Round-2 review fixes: voice turn honesty, wait bookkeeping, trust doors,
run-start failure handling and the modeless question dialog."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from abstractassistant.controller import AssistantController
from abstractassistant.core.voice_conversation import VoiceConversation
from abstractassistant.ui.activity import RunActivityModel


def _older_gateway_caps(**_kwargs):
    """Discovery from a gateway WITHOUT the session tool policy: the in-app
    chat grant is the (explicit) local fallback these tests exercise."""
    from abstractassistant.gateway.capabilities import AssistantCapabilities

    return AssistantCapabilities.from_discovery_response({"capabilities": {}})


class _Voice:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def set_audio_meter_callback(self, cb) -> None:
        pass

    def begin_hold(self, **_kw) -> bool:
        self.calls.append("begin_hold")
        return True

    def cancel_hold(self) -> None:
        self.calls.append("cancel_hold")

    def stop_speaking(self) -> None:
        self.calls.append("stop_speaking")


def _conversation(**kw):
    voice = _Voice()
    sent: list[str] = []
    states: list[str] = []
    conv = VoiceConversation(voice_manager=voice, on_send=sent.append, on_state=states.append, **kw)
    assert conv.start() is True
    return conv, voice, sent, states


# The loop-era tests (mic paused while thinking and reopened after, requeue for the next
# listening window, manual Return accounting, "full" mode reopening the mic) went with the
# loop in 0.18.2: a voice turn is one utterance. See test_voice_conversation.py.


@pytest.mark.basic
def test_voice_detach_silences_state_callbacks_during_teardown() -> None:
    conv, voice, _, states = _conversation()
    conv.detach()
    conv.stop(reason="microphone lost")
    assert conv.state == "error" and conv.error == "microphone lost"
    assert "error" not in states
    assert "cancel_hold" in voice.calls and "stop_speaking" in voice.calls


@pytest.mark.basic
def test_resolve_wait_settles_the_newest_open_step_on_a_reused_key() -> None:
    model = RunActivityModel(run_id="run-1")
    model.apply_event({"type": "tool_request", "tool_calls": [{"name": "read_file"}], "wait_key": "k"})
    first = model.resolve_wait("k", "approved")
    model.apply_event({"type": "tool_request", "tool_calls": [{"name": "write_file"}], "wait_key": "k"})
    second = model.resolve_wait("k", "auto_approved")
    assert first and second and first != second
    steps = {s.step_id: s for s in model.steps}
    assert steps[first].title_plain == "Approved by you"
    assert steps[second].title_plain.startswith("Auto-approved")


@pytest.mark.basic
def test_resolve_wait_prefers_a_pending_deferred_step_and_clears_older_ones() -> None:
    model = RunActivityModel(run_id="run-1")
    model.apply_event({"type": "ask_user", "prompt": "Which file?", "wait_key": "ask"})
    deferred = model.resolve_wait("ask", "dismissed")
    assert deferred is not None
    answered = model.resolve_wait("ask", "answered")
    assert answered == deferred
    step = next(s for s in model.steps if s.step_id == answered)
    assert step.payload.get("pending") is False


def _controller(items):
    controller = AssistantController.__new__(AssistantController)
    controller._session_auto_approve_all = set()
    controller.llm_manager = SimpleNamespace(active_session_id="chat-a", gateway_capabilities=_older_gateway_caps)
    controller.tool_inventory = lambda: {"items": list(items)}  # type: ignore[method-assign]
    return controller


@pytest.mark.basic
def test_session_trust_never_covers_outreach_or_destroy_tiers() -> None:
    controller = _controller(
        [
            {"name": "read_file", "selected_mode": "ask", "risk_tier": "observe", "risk_rank": 1},
            {"name": "write_file", "selected_mode": "ask", "risk_tier": "act", "risk_rank": 2},
            {"name": "send_email", "selected_mode": "ask", "risk_tier": "outreach", "risk_rank": 3},
            {"name": "execute_command", "selected_mode": "approve", "risk_tier": "destroy", "risk_rank": 4},
            {"name": "delete_tree", "selected_mode": "ask", "risk_tier": "destroy", "risk_rank": 4},
        ]
    )
    controller.grant_session_tool_auto_approval()
    assert controller.should_auto_approve_tool_batch([{"name": "read_file"}, {"name": "write_file"}]) is True
    assert controller.should_auto_approve_tool_batch([{"name": "read_file"}, {"name": "send_email"}]) is False
    assert controller.should_auto_approve_tool_batch([{"name": "delete_tree"}]) is False
    # A tool the user set to Auto by name stays auto, whatever its tier.
    assert controller.should_auto_approve_tool_batch([{"name": "execute_command"}]) is True
    policy = controller.tool_policy_for_run()
    assert policy["auto_approve_tools"] == ["read_file", "write_file", "execute_command"]
    assert policy["require_approval_tools"] == ["send_email", "delete_tree"]


@pytest.mark.basic
def test_gateway_is_local_only_for_loopback_hosts() -> None:
    controller = AssistantController.__new__(AssistantController)
    for url, expected in (
        ("http://127.0.0.1:8080", True),
        ("http://localhost:8080", True),
        ("http://[::1]:8080", True),
        ("https://gateway.example.com", False),
        ("", False),
    ):
        controller.connection = SimpleNamespace(base_url=url)
        assert controller.gateway_is_local() is expected, url


@pytest.mark.basic
def test_chat_trust_can_be_granted_up_to_the_tier_the_user_saw() -> None:
    items = [
        {"name": "read_file", "selected_mode": "ask", "risk_tier": "observe", "risk_rank": 1},
        {"name": "send_email", "selected_mode": "ask", "risk_tier": "outreach", "risk_rank": 3},
        {"name": "delete_tree", "selected_mode": "ask", "risk_tier": "destroy", "risk_rank": 4},
    ]
    # Granted while looking at a destructive batch: the chat trusts everything
    # enabled, which is what "allow all enabled tools in this chat" says.
    controller = _controller(items)
    controller.grant_session_tool_auto_approval(max_rank=4)
    assert controller.session_trust_rank() == 4
    assert controller.should_auto_approve_tool_batch([{"name": "delete_tree"}]) is True
    assert controller.should_auto_approve_tool_batch([{"name": "send_email"}]) is True
    assert controller.tool_policy_for_run()["require_approval_tools"] == []

    # Granted on a read-only batch: the destructive call later still asks.
    controller = _controller(items)
    controller.grant_session_tool_auto_approval(max_rank=1)
    assert controller.should_auto_approve_tool_batch([{"name": "read_file"}]) is True
    assert controller.should_auto_approve_tool_batch([{"name": "delete_tree"}]) is False
    assert controller.tool_policy_for_run()["require_approval_tools"] == ["send_email", "delete_tree"]

    # A wider grant later raises the ceiling; a narrower one never lowers it.
    controller.grant_session_tool_auto_approval(max_rank=4)
    assert controller.session_trust_rank() == 4
    controller.grant_session_tool_auto_approval(max_rank=1)
    assert controller.session_trust_rank() == 4


@pytest.mark.basic
def test_trust_rank_is_per_chat_and_zero_without_a_grant() -> None:
    controller = _controller([{"name": "read_file", "selected_mode": "ask", "risk_rank": 1}])
    assert controller.session_trust_rank() == 0
    controller.grant_session_tool_auto_approval(max_rank=4)
    assert controller.session_trust_rank() == 4
    controller.llm_manager.active_session_id = "chat-b"
    assert controller.session_trust_rank() == 0
