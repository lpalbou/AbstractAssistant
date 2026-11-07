"""Reasoning and MTP follow the SELECTED model; a failed run shows the gateway's own words.

Operator rulings 2026-11-07:

1. "MTP should only ever be selected for MTP-capable models. When changing a model from the
   dropdown, always go back to default for reasoning and MTP, in every app." The incident:
   preferences.json held speculation {native_mtp, depth 2, require_acceleration: true}, sent
   with gpt-5.6-terra through an endpoint that has no MTP, and every run was refused. The rule
   is the shared kit's (AbstractUIC ui-kit model_options.ts / speculation_select.tsx), with the
   kit's words for the same states.
2. "Runs should not fail; if they do, show the actual error." No mapping of exception names,
   no parsing of the error text: the gateway's text, word for word, never cut.

Headless (QT_QPA_PLATFORM=offscreen), stub controllers, no gateway.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abstractassistant.gateway.run_input import build_run_input_data
from abstractassistant.gateway_service import ChoiceItem
from abstractassistant.preferences import AssistantPreferences, PreferencesStore

import test_settings_pages as tsp

DEPTH_2 = {"mode": "native_mtp", "num_draft_tokens": 2, "require_acceleration": True}

MTP_CAPABLE = {"capabilities": {"thinking_support": True, "reasoning_levels": ["low", "medium", "high"]},
               "execution": {"speculation": {
                   "supported": True, "ready": True, "reason": None, "supported_depths": [1, 2, 3],
                   "effective_default": False, "requires_reload": False}}}
# What the gateway serves for an endpoint model with no MTP (abstractcore providers/speculation.py).
NO_MTP = {"capabilities": {}, "execution": {"speculation": {
    "supported": False, "ready": None, "reason": "native_mtp_backend_unavailable", "supported_depths": [],
    "message": "MTP is not available for this provider."}}}


class _Ctl(tsp._Controller):
    """Two chat models: an MLX one with MTP and an endpoint one without."""

    cards = {"mlx-mtp": MTP_CAPABLE, "gpt-5.6-terra": NO_MTP}

    def provider_choices(self, **kwargs):
        return [ChoiceItem(id="mlx", label="mlx"), ChoiceItem(id="endpoint:airelays", label="airelays")]

    def model_choices(self, *, provider="", **kwargs):
        return [ChoiceItem(id="mlx-mtp", label="mlx-mtp")] if provider == "mlx" else [
            ChoiceItem(id="gpt-5.6-terra", label="gpt-5.6-terra")]

    def route_map(self, **kwargs):
        from abstractassistant.gateway_service import CapabilityRouteRow

        return {"output.text": CapabilityRouteRow(
            key="output.text", label="Text Output", kind="output", modality="text", task="",
            provider="mlx", model="mlx-mtp", configured=True)}

    def effective_chat_route(self):
        o = self.overrides.get("output.text")
        return {"provider": o["provider"], "model": o["model"], "source": "override"} if o else {
            "provider": "mlx", "model": "mlx-mtp", "source": "gateway"}

    def model_capabilities(self, model):
        return dict(self.cards.get(model, {}).get("capabilities") or {})


def _editor(ctl):
    dlg, ctl = tsp._dialog(ctl)
    dlg.show_section("models", "output.text")
    return dlg, ctl, dlg.page_models.route_editor


def _items(combo):
    return [(combo.itemData(i), combo.itemText(i)) for i in range(combo.count())]


# --------------------------------------------------------------------------- #
# MTP depth: choices only for an MTP-capable model


@pytest.mark.basic
def test_a_model_without_mtp_offers_no_mtp_choice_and_shows_the_gateway_reason() -> None:
    dlg, ctl, editor = _editor(_Ctl())
    editor._apply_speculation_payload(editor._speculation_epoch, NO_MTP)
    combo = editor.speculation_combo
    assert _items(combo) == [(None, "Gateway default")]  # no Off, no depth
    assert not combo.isEnabled()
    assert editor.speculation_note.text() == "MTP is not available for this provider."
    # The gateway's own reason code, one click away under Technical details.
    button = editor.speculation_details_button
    assert not button.isHidden() and button.text() == "▸ Technical details"
    assert editor.speculation_detail.isHidden()
    button.click()
    assert button.text() == "▾ Technical details"
    assert not editor.speculation_detail.isHidden()
    assert editor.speculation_detail.text() == "native_mtp_backend_unavailable"
    # Enabling the form again (a route reload) never re-enables it.
    editor._set_route_editor_enabled(True)
    assert not combo.isEnabled()


@pytest.mark.basic
def test_the_kit_sentences_for_unsupported_unknown_and_checking() -> None:
    from abstractassistant.speculation import speculation_view

    unsupported = speculation_view({"execution": {"speculation": {"supported": False}}})
    assert unsupported["note"] == "This model does not support MTP." and unsupported["state"] == "unsupported"
    unknown = speculation_view({})
    assert unknown["note"] == "MTP is offered when the gateway confirms this model supports it."
    assert unknown["choices"] == [(None, "Gateway default")] and not unknown["enabled"]
    assert speculation_view({}, loading=True)["note"] == "Checking whether this model supports MTP…"
    failed = speculation_view({"error": "discovery_model_capabilities failed: HTTP 502"})
    assert failed["state"] == "unknown" and failed["detail"] == "discovery_model_capabilities failed: HTTP 502"


@pytest.mark.basic
def test_a_saved_depth_the_model_cannot_use_is_not_shown_as_chosen() -> None:
    ctl = _Ctl()
    ctl.preferences = AssistantPreferences(hotkey_enabled=False, speculation=DEPTH_2)
    dlg, ctl, editor = _editor(ctl)
    editor._apply_speculation_payload(editor._speculation_epoch, NO_MTP)
    combo = editor.speculation_combo
    assert combo.currentIndex() == 0 and combo.currentText() == "Gateway default"
    assert not any("saved" in text for _value, text in _items(combo))
    assert not combo.isEnabled()
    # A depth the card does not list is not chosen either.
    ctl.preferences = AssistantPreferences(hotkey_enabled=False, speculation={"mode": "native_mtp", "num_draft_tokens": 7})
    editor._apply_speculation_payload(editor._speculation_epoch, MTP_CAPABLE)
    assert combo.currentIndex() == 0 and combo.isEnabled()
    assert [text for _v, text in _items(combo)] == ["Gateway default (Off)", "Off", "Depth 1", "Depth 2", "Depth 3"]


# --------------------------------------------------------------------------- #
# Changing the model or provider resets reasoning and MTP, and saves that


def _with_choices(ctl):
    ctl.preferences = AssistantPreferences(hotkey_enabled=False, reasoning_effort="high", speculation=DEPTH_2)
    return ctl


@pytest.mark.basic
def test_changing_the_chat_model_resets_reasoning_and_mtp_to_the_gateway_default() -> None:
    dlg, ctl, editor = _editor(_with_choices(_Ctl()))
    editor.provider_combo.setCurrentIndex(editor.provider_combo.findData("endpoint:airelays"))
    editor.model_combo.setCurrentIndex(editor.model_combo.findData("gpt-5.6-terra"))
    assert ctl.overrides["output.text"]["model"] == "gpt-5.6-terra"
    assert ctl.preferences.reasoning_effort == ""
    assert ctl.preferences.speculation is None
    assert editor.reasoning_combo.currentData() in ("", None)
    assert editor.speculation_combo.currentIndex() == 0
    assert "speculation" not in ctl.preferences.run_scope() and ctl.preferences.run_scope()["thinking"] == ""


@pytest.mark.basic
def test_going_back_to_the_gateway_default_model_resets_them_too() -> None:
    ctl = _with_choices(_Ctl())
    ctl.overrides["output.text"] = {"provider": "mlx", "model": "mlx-mtp"}
    dlg, ctl, editor = _editor(ctl)
    editor.provider_combo.setCurrentIndex(0)  # "Gateway default"
    assert "output.text" not in ctl.overrides
    assert ctl.preferences.reasoning_effort == "" and ctl.preferences.speculation is None


@pytest.mark.basic
def test_a_voice_route_change_keeps_the_chat_models_reasoning_and_mtp() -> None:
    ctl = _with_choices(_Ctl())
    dlg, ctl = tsp._dialog(ctl)
    dlg.show_section("models", "output.voice")
    editor = dlg.page_models.route_editor
    editor.provider_combo.setCurrentIndex(1)
    assert ctl.preferences.reasoning_effort == "high" and ctl.preferences.speculation == DEPTH_2


@pytest.mark.basic
def test_a_saved_reasoning_level_the_model_does_not_list_is_not_shown_as_chosen() -> None:
    ctl = _Ctl()
    ctl.preferences = AssistantPreferences(hotkey_enabled=False, reasoning_effort="none")
    dlg, ctl, editor = _editor(ctl)  # ladder none/low/medium/high; mlx-mtp lists low, medium, high
    combo = editor.reasoning_combo
    assert combo.currentData() in ("", None)
    none = combo.model().item(combo.findData("none"))
    assert not none.isEnabled()
    assert combo.itemData(combo.findData("none"), 3) == "This model does not advertise it"  # Qt.ToolTipRole
    assert "Currently sending" not in editor._reasoning_full


# --------------------------------------------------------------------------- #
# Send time: a saved value the model cannot use is never sent


def _controller(card=None, *, route=("endpoint:airelays", "gpt-5.6-terra"), fails=False):
    from abstractassistant.controller import AssistantController

    controller = AssistantController.__new__(AssistantController)
    seen: list = []
    controller.effective_chat_route = lambda: {"provider": route[0], "model": route[1], "source": "override"}

    def execution_capabilities(provider, model):
        seen.append((provider, model))
        if fails:
            raise OSError("connection refused")
        return card

    controller.execution_capabilities = execution_capabilities
    return controller, seen


@pytest.mark.basic
def test_the_incident_a_saved_depth_is_not_sent_with_a_model_without_mtp(tmp_path) -> None:
    # The operator's file as it was: a depth with require_acceleration, reasoning high.
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"speculation": {"mode": "native_mtp", "num_draft_tokens": 2,
                                                "require_acceleration": True}, "reasoning_effort": "high"}))
    prefs = PreferencesStore(path).load()
    controller, seen = _controller(NO_MTP)
    thinking, speculation = controller.sendable_model_options(prefs.run_scope()["thinking"], prefs.run_scope()["speculation"])
    assert seen == [("endpoint:airelays", "gpt-5.6-terra")]
    assert speculation is None
    assert thinking == "high"  # the card says nothing about reasoning: unknown is not unsupported
    run = build_run_input_data(prompt="hi", thinking=thinking, speculation=speculation)
    assert "speculation" not in run["_runtime"]


@pytest.mark.basic
def test_the_send_guard_keeps_only_what_the_card_allows() -> None:
    controller, seen = _controller(MTP_CAPABLE, route=("mlx", "mlx-mtp"))
    assert controller.sendable_model_options("high", DEPTH_2) == ("high", DEPTH_2)
    assert controller.sendable_model_options("", False) == ("", False)
    assert controller.sendable_model_options("xhigh", {"mode": "native_mtp", "num_draft_tokens": 7}) == ("", None)
    no_reasoning, _ = _controller({**NO_MTP, "capabilities": {"thinking_support": False}})
    assert no_reasoning.sendable_model_options("high", False) == ("", None)  # Off is not sent either
    # Nothing set: no card is read.
    quiet, quiet_seen = _controller(MTP_CAPABLE)
    assert quiet.sendable_model_options("", None) == ("", None) and quiet_seen == []
    # The card cannot be read: no MTP, the reasoning level is kept.
    broken, _ = _controller(fails=True)
    assert broken.sendable_model_options("high", DEPTH_2) == ("high", None)
    errored, _ = _controller({"error": "Gateway runtime does not expose AbstractCore discovery helpers."})
    assert errored.sendable_model_options("low", False) == ("low", None)


@pytest.mark.basic
def test_the_worker_sends_what_the_guard_allows() -> None:
    import abstractassistant.ui.gateway_worker as worker_module

    worker = worker_module.GatewayWorker(
        llm_manager=None, user_text="hi", bundle_id="b", flow_id="f",
        thinking="high", speculation=DEPTH_2,
        model_options_guard=lambda thinking, speculation: (thinking, None),
    )
    assert worker._sendable_model_options() == ("high", None)
    broken = worker_module.GatewayWorker(
        llm_manager=None, user_text="hi", bundle_id="b", flow_id="f", thinking="high", speculation=DEPTH_2,
        model_options_guard=lambda *_: (_ for _ in ()).throw(OSError("down")),
    )
    with pytest.warns(UserWarning):
        assert broken._sendable_model_options() == ("high", None)


@pytest.mark.basic
def test_build_chat_worker_hands_the_worker_the_send_guard(monkeypatch) -> None:
    from test_run_scope_preferences import _controller_with_prefs

    captured: dict = {}
    controller = _controller_with_prefs(monkeypatch, captured, AssistantPreferences(speculation=DEPTH_2))
    controller.llm_manager = SimpleNamespace(session_workspace_root=lambda: "")
    controller.build_chat_worker(prompt="Hello")
    assert captured["model_options_guard"] == controller.sendable_model_options


# --------------------------------------------------------------------------- #
# A failed run shows the gateway's own error text


SPECULATION_ERROR = (
    "Effect failed after 3 attempts: SpeculationUnavailableError: The openai-compatible provider "
    "has no native MTP adapter (speculation.require_acceleration=True)"
)


def _palette():
    from PyQt5.QtWidgets import QApplication, QLabel

    import abstractassistant.app as app_module

    QApplication.instance() or QApplication([])
    palette = app_module.AssistantPalette.__new__(app_module.AssistantPalette)
    shown: list = []
    palette._set_status = lambda *a, **kw: None
    palette._set_history_status = lambda text="", **kw: shown.append((text, kw))
    for name in ("_refresh_tray_feedback", "_clear_run_activity", "_invalidate_session_digests",
                 "refresh_history", "_set_banner", "_discard_live_replies"):
        setattr(palette, name, lambda *a, **k: None)
    palette._feed_activity = lambda payload: None
    palette._show_thinking_indicator = lambda: False
    palette._finish_activity = lambda outcome: None
    palette._set_send_button_busy = lambda busy: None
    palette.sender = lambda: None
    palette._worker = None
    return app_module, palette, shown


@pytest.mark.basic
@pytest.mark.parametrize("reason", [SPECULATION_ERROR, "Effect failed after 3 attempts: ProviderAPIError: upstream 502"])
def test_a_failed_run_shows_the_gateways_error_word_for_word(reason) -> None:
    app_module, palette, shown = _palette()
    app_module.AssistantPalette._on_worker_event(palette, {"type": "run_error", "error": reason, "run_id": "run-1"})
    app_module.AssistantPalette._on_worker_event(palette, {"type": "status", "status": "failed"})
    palette._run_has_final_output = False
    app_module.AssistantPalette._on_worker_finished(palette)
    text, kw = shown[-1]
    assert text == f"The run failed: {reason}"
    assert kw.get("tone") == "error"


@pytest.mark.basic
def test_a_failed_run_without_a_reason_says_so() -> None:
    app_module, palette, shown = _palette()
    app_module.AssistantPalette._on_worker_event(palette, {"type": "status", "status": "failed"})
    palette._run_has_final_output = False
    app_module.AssistantPalette._on_worker_finished(palette)
    assert shown[-1][0] == "The run failed; the gateway gave no reason."


@pytest.mark.basic
def test_the_error_mapping_is_gone() -> None:
    with pytest.raises(ImportError):
        import abstractassistant.core.run_failure  # noqa: F401


@pytest.mark.basic
def test_a_long_failure_is_shown_in_full_and_opens_in_a_copyable_window() -> None:
    from PyQt5.QtCore import QEvent, QPointF, Qt
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtWidgets import QApplication

    import test_palette_smoke as smoke
    from abstractassistant.app import AssistantPalette

    app = smoke._app()
    window = AssistantPalette(controller=smoke._Controller(), debug=False)
    try:
        smoke._wait_for_bootstrap(window)
        long_reason = "The run failed: " + SPECULATION_ERROR + " " + "x" * 400
        window._set_history_status(long_reason, tone="error")
        label = window.chat_status_label
        assert label.text() == long_reason  # never cut
        # However small the window, a click opens the whole text in a window it can be copied from.
        release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(4, 4), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(label, release)
        box = window._failure_text_box
        assert box.text() == long_reason
        assert box.textInteractionFlags() & Qt.TextSelectableByMouse
        box.close()
        # Any other line is not a link.
        window._set_history_status("Ready", tone="info")
        window._failure_text_box = None
        QApplication.sendEvent(label, QMouseEvent(QEvent.MouseButtonRelease, QPointF(4, 4), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        assert window._failure_text_box is None
    finally:
        try:
            window.shutdown()
        except Exception:
            pass
        window.deleteLater()
        app.processEvents()
