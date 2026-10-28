"""The toolbar reports saved defaults and revokes only this chat's grant."""
from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication, QPushButton

from abstractassistant.app import AssistantPalette
from abstractassistant.controller import AssistantController


def _older_gateway_caps(**_kwargs):
    """Discovery from a gateway WITHOUT the session tool policy: the in-app
    chat grant is the (explicit) local fallback these tests exercise."""
    from abstractassistant.gateway.capabilities import AssistantCapabilities

    return AssistantCapabilities.from_discovery_response({"capabilities": {}})


@pytest.mark.basic
def test_revoke_session_grant_restores_policy_and_preserves_other_chat():
    controller = AssistantController.__new__(AssistantController)
    controller._session_auto_approve_all = set()
    controller.llm_manager = SimpleNamespace(active_session_id="a", gateway_capabilities=_older_gateway_caps)
    controller.tool_inventory = lambda: {"items": [
        {"name": "read", "selected_mode": "ask"},
        {"name": "auto", "selected_mode": "approve"},
        {"name": "off", "selected_mode": "disabled"},
    ]}
    controller.grant_session_tool_auto_approval(session_id="a", max_rank=4)
    controller.grant_session_tool_auto_approval(session_id="b", max_rank=2)
    controller.revoke_session_tool_auto_approval()
    assert controller.session_trust_rank() == 0
    assert controller.session_trust_rank(session_id="b") == 2
    assert controller.tool_policy_for_run() == {
        "auto_approve_tools": ["auto"], "require_approval_tools": ["read"]}
    controller.revoke_session_tool_auto_approval()  # Idempotent.


@pytest.mark.basic
@pytest.mark.parametrize("modes,trust,label", [
    # The kit's summary words (tool_mode_editor.tsx "N tools on, M without asking").
    (["ask", "ask"], False, "Tools & permissions: 2 tools on, 0 without asking"),
    (["approve", "approve"], False, "Tools & permissions: 2 tools on, 2 without asking"),
    (["ask", "approve"], False, "Tools & permissions: 2 tools on, 1 without asking"),
    (["disabled"], False, "Tools & permissions"),
    (["ask"], True, "Session approval active"),
])
def test_indicator_renders_policy_states(modes, trust, label):
    app = QApplication.instance() or QApplication([])
    button = QPushButton()
    controller = SimpleNamespace(session_tool_auto_approval_active=lambda: trust)
    host = SimpleNamespace(tools_button=button, _controller=controller,
                           _indicator_inventory={"items": [{"selected_mode": m} for m in modes]})
    host._state = lambda name, default=None: getattr(host, name, default)
    AssistantPalette._refresh_tool_indicator(host)
    assert button.toolTip().startswith(label)
    assert button.accessibleName() == button.toolTip()
    assert not button.icon().isNull()
    button.deleteLater()
    app.processEvents()


@pytest.mark.basic
@pytest.mark.parametrize("accept", [False, True])
def test_session_reset_confirmation_captures_original_chat(accept):
    from PyQt5.QtWidgets import QWidget, QMessageBox
    app = QApplication.instance() or QApplication([])
    controller = AssistantController.__new__(AssistantController)
    controller._session_auto_approve_all = set()
    controller.llm_manager = SimpleNamespace(active_session_id="a", gateway_capabilities=_older_gateway_caps)
    controller.grant_session_tool_auto_approval(session_id="a")
    controller.grant_session_tool_auto_approval(session_id="b")
    host = QWidget()
    host._controller = controller
    host._active_session_id = lambda: controller.active_session_id
    host._clear_banner = lambda key: None
    host._refresh_tool_indicator = lambda: None
    dialogs = []
    host._show_aux_dialog = dialogs.append
    AssistantPalette._on_tools_indicator_clicked(host)
    assert len(dialogs) == 1
    assert controller.session_tool_auto_approval_active(session_id="a")
    controller.llm_manager.active_session_id = "b"
    dialogs[0].done(QMessageBox.Yes if accept else QMessageBox.Cancel)
    assert controller.session_tool_auto_approval_active(session_id="a") is (not accept)
    assert controller.session_tool_auto_approval_active(session_id="b")
    host.deleteLater()
    app.processEvents()
