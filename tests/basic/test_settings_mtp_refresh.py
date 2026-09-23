"""Choosing a model must re-ask what THAT model can do.

The operator's report (2026-09-21): with Provider = MLX and Model =
`Jundot/Qwen3.8-27B-oQ4e-mtp` — a checkpoint carrying an embedded MTP head —
the MTP depth list offered nothing but "Off", captioned
`native_mtp_backend_unavailable`, while abstractcode's web UI offered depths
2-5 for the same pair.

The gateway was right both times. `native_mtp_backend_unavailable` is what
`describe_speculation_capabilities` returns when the provider is not "mlx"
(providers/speculation.py), and the editor had probed with provider "" — the
route as it stood BEFORE the override existed. `_refresh_speculation` was
reachable from exactly one place, `_load_selected_route`, so the combo kept
the previous route's answer forever: repainting the captions on change without
re-running discovery meant the only way to see the real depths was to close
Settings and reopen it.

MTP depth and the reasoning levels are properties of the chosen provider/model,
so both are re-discovered whenever that choice changes.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_settings_routes import _StubController, _dialog, _select  # noqa: E402


def _editor(dlg):
    """The dialog is a shell; the route form lives on the models page."""
    return dlg.route_editor


def _record_refreshes(dlg):
    """Replace the two discovery calls with recorders.

    They are what the bug omitted, and both reach the network in production
    (`_refresh_speculation` off-thread, `_refresh_reasoning` through a cached
    capability card), so the assertion is on the wiring, not on a payload.
    """
    editor = _editor(dlg)
    calls: list[str] = []
    editor._refresh_speculation = lambda: calls.append("speculation")  # type: ignore[method-assign]
    editor._refresh_reasoning = lambda: calls.append("reasoning")  # type: ignore[method-assign]
    return calls


@pytest.mark.basic
def test_choosing_a_model_re_discovers_mtp_and_reasoning() -> None:
    dlg = _dialog()
    _select(dlg, "output.text")
    calls = _record_refreshes(dlg)

    dlg.provider_combo.setCurrentIndex(dlg.provider_combo.findData("lmstudio"))
    dlg.model_combo.setCurrentIndex(dlg.model_combo.findData("ornith-1.0-35b"))

    assert dlg._stub.overrides["output.text"] == {
        "provider": "lmstudio",
        "model": "ornith-1.0-35b",
    }
    # The whole bug: the override landed and nothing re-asked what it supports.
    assert "speculation" in calls, "MTP depth was not re-discovered for the new model"
    assert "reasoning" in calls, "reasoning levels were not re-discovered for the new model"


@pytest.mark.basic
def test_the_probe_uses_the_override_not_the_gateway_default() -> None:
    """`_effective_chat_route` is what the probe is handed.

    Probing the gateway default instead of this app's override is how provider
    "" reached the gateway and came back `native_mtp_backend_unavailable`.
    """
    dlg = _dialog()
    _select(dlg, "output.text")

    dlg.provider_combo.setCurrentIndex(dlg.provider_combo.findData("lmstudio"))
    dlg.model_combo.setCurrentIndex(dlg.model_combo.findData("ornith-1.0-35b"))

    route = _editor(dlg)._effective_chat_route()
    assert route["provider"] == "lmstudio"
    assert route["model"] == "ornith-1.0-35b"
    assert route["source"] == "override"


@pytest.mark.basic
def test_clearing_the_override_re_discovers_too() -> None:
    """Falling back to the gateway default is also a route change."""
    ctl = _StubController()
    ctl.overrides["output.text"] = {"provider": "lmstudio", "model": "ornith-1.0-35b"}
    dlg = _dialog(ctl)
    _select(dlg, "output.text")
    calls = _record_refreshes(dlg)

    # Item 0 of the provider list is "Gateway default" — choosing it is the reset.
    dlg.provider_combo.setCurrentIndex(0)

    assert "output.text" not in dlg._stub.overrides
    assert "speculation" in calls, "MTP depth kept the cleared override's answer"


@pytest.mark.basic
def test_a_non_chat_route_does_not_probe_mtp() -> None:
    """MTP belongs to the chat model. Changing the voice route must not ask."""
    dlg = _dialog()
    _select(dlg, "output.voice")
    calls = _record_refreshes(dlg)

    dlg.provider_combo.setCurrentIndex(dlg.provider_combo.findData("piper"))
    dlg.model_combo.setCurrentIndex(dlg.model_combo.findData("en_US-amy-medium"))

    assert dlg._stub.overrides["output.voice"]["provider"] == "piper"
    assert calls == [], "a voice route change asked for MTP capability"
