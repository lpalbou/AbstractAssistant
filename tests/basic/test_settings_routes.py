"""Models & Voice settings tab — LOCAL override contract (never a gateway mutation).

Regression suite for the 2026-07-18 rewrite: the assistant's provider/model
selection is a LOCAL override for this app only. It is stored in preferences and
sent per-run/per-call; it must NEVER write the gateway's shared capability
default. The editor shows two honest lines — the gateway's own default and what
THIS app pins on top — and offers a "Reset to gateway" affordance.

It also keeps the earlier honesty guarantee: a route with no local override must
NEVER present a fabricated provider/model selection as if it were configuration
(the openai/gpt-4o-transcribe incident).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from abstractassistant.gateway_service import CapabilityRouteRow, ChoiceItem


_APP = None


def _app() -> QApplication:
    # Keep a module-level reference: an unreferenced QApplication is
    # garbage-collected and widget construction aborts.
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class _StubController:
    """Just enough controller for the SettingsDialog to build.

    The gateway defaults are fixed (read-only from the dialog's perspective);
    local overrides live in an in-memory dict that the override save/clear
    methods mutate — exactly the preferences-backed shape, minus disk I/O.
    """

    class _Prefs:
        hotkey_enabled = True
        hotkey_sequence = "cmd+shift+space"
        auto_speak = True
        voice_quality = "standard"
        window_width = 560
        window_height = 336
        bottom_offset = 0
        tool_preferences: dict = {}

    def __init__(self) -> None:
        self.preferences = self._Prefs()
        self.overrides: dict = {}
        # Guards that the gateway-mutating API is NEVER reached from the dialog.
        self.gateway_writes: list = []

    class _Conn:
        base_url = "http://127.0.0.1:8080"
        auth_mode = "bearer"
        auth_token = "token"
        user_id = "admin"
        remember_session = False

    def current_connection(self):
        return self._Conn()

    def connection_status(self):
        return {"ok": True, "detail": "connected"}

    # --- gateway defaults (read-only) ---------------------------------------
    def route_map(self):
        return {
            "output.text": CapabilityRouteRow(
                key="output.text",
                label="Text Output",
                kind="output",
                modality="text",
                task="",
                provider="endpoint:ovh-provider",
                model="Meta-Llama-3_3-70B-Instruct",
                configured=True,
                source="abstractcore.gateway_runtime",
            ),
            "output.voice": CapabilityRouteRow(
                key="output.voice",
                label="Text To Speech",
                kind="output",
                modality="voice",
                task="tts",
                provider="supertonic",
                model="supertonic-3",
                options={"voice": "M3"},
                configured=True,
                source="abstractcore.gateway_runtime",
            ),
            "input.voice": CapabilityRouteRow(
                key="input.voice",
                label="Speech To Text",
                kind="input",
                modality="voice",
                task="stt",
                provider="faster-whisper",
                model="large-v3",
                configured=True,
                source="abstractcore.gateway_runtime",
            ),
        }

    # --- local overrides (read/write, preferences-backed in production) -----
    def route_override(self, route_key: str):
        value = self.overrides.get(str(route_key or "").strip())
        return dict(value) if isinstance(value, dict) else None

    def save_route_override(self, *, route_key, provider, model, base_url="", options=None):
        entry = {"provider": provider, "model": model}
        if base_url:
            entry["base_url"] = base_url
        if options:
            entry["options"] = dict(options)
        self.overrides[route_key] = entry

    def clear_route_override(self, *, route_key):
        self.overrides.pop(route_key, None)

    # A dialog that ever calls these has regressed to mutating the gateway.
    def save_route_default(self, **kwargs):  # pragma: no cover - guard
        self.gateway_writes.append(("save", dict(kwargs)))
        raise AssertionError("dialog must not write the gateway default")

    def clear_route_default(self, **kwargs):  # pragma: no cover - guard
        self.gateway_writes.append(("clear", dict(kwargs)))
        raise AssertionError("dialog must not clear the gateway default")

    # --- catalogs -----------------------------------------------------------
    @staticmethod
    def provider_choices(*, route_key: str, base_url: str = ""):
        if route_key == "input.voice":
            return [
                ChoiceItem(id="openai", label="openai"),
                ChoiceItem(id="faster-whisper", label="faster-whisper"),
            ]
        if route_key == "output.voice":
            return [
                ChoiceItem(id="supertonic", label="supertonic"),
                ChoiceItem(id="piper", label="piper"),
            ]
        return [
            ChoiceItem(id="lmstudio", label="lmstudio"),
            ChoiceItem(id="endpoint:ovh-provider", label="ovh-provider"),
        ]

    @staticmethod
    def model_choices(*, route_key: str, provider: str, base_url: str = ""):
        catalog = {
            "openai": ["gpt-4o-transcribe", "whisper-1"],
            "faster-whisper": ["base", "large-v3"],
            "supertonic": ["supertonic-3"],
            "piper": ["en_US-amy-medium"],
            "lmstudio": ["ornith-1.0-35b", "gemma-3-1b-it"],
            "endpoint:ovh-provider": ["Meta-Llama-3_3-70B-Instruct"],
        }
        return [ChoiceItem(id=m, label=m) for m in catalog.get(provider, [])]

    @staticmethod
    def voice_choices(*, provider: str, model: str, base_url: str = ""):
        if provider == "supertonic":
            return [ChoiceItem(id="M1", label="M1"), ChoiceItem(id="M3", label="M3")]
        return []

    @staticmethod
    def parse_options(text: str):
        import json

        try:
            parsed = json.loads(text or "{}")
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def save_preferences(prefs):
        return None


def _dialog(controller: _StubController | None = None):
    _app()
    from abstractassistant.app import SettingsDialog

    ctl = controller or _StubController()
    dlg = SettingsDialog(controller=ctl, apply_hotkey=lambda *a, **k: None, parent=None)
    dlg._stub = ctl  # type: ignore[attr-defined]
    return dlg


def _row_index(dlg, key: str) -> int:
    for idx, row in enumerate(dlg._route_rows):
        if row.key == key:
            return idx
    raise AssertionError(f"route {key} not listed")


@pytest.mark.basic
def test_only_overrideable_routes_are_listed() -> None:
    dlg = _dialog()
    keys = {row.key for row in dlg._route_rows}
    # The thin client offers every route it actually drives + can honor as a
    # per-run local override (maintainer ruling 2026-07-28: all modalities the
    # framework serves are overrideable in-app; the gateway default is never
    # written). Media overrides ride the managed workflow's input pins.
    assert keys == {
        "output.text",
        "output.voice",
        "input.voice",
        "output.image.text_to_image",
        "output.image.image_to_image",
        "output.image.image_upscale",
        "output.video.text_to_video",
        "output.video.image_to_video",
        "output.music",
        "output.sound",
    }
    # 3D stays absent: the runtime has no scene3d workflow node yet, so the
    # assistant cannot trigger (or honor an override for) 3D generation.
    assert not any(k.startswith("output.scene3d") for k in keys)
    # Embedding/rerank stay absent: the assistant never issues those calls.
    assert not any(k.startswith(("embedding.", "rerank.")) for k in keys)


@pytest.mark.basic
def test_route_without_local_override_shows_default_mode_no_fabrication() -> None:
    dlg = _dialog()
    dlg.route_list.setCurrentRow(_row_index(dlg, "input.voice"))

    # No local override -> default mode, placeholder combos, disabled pickers.
    assert dlg.route_mode_default.isChecked()
    assert dlg.provider_combo.currentData() == ""
    assert dlg.model_combo.currentData() == ""
    assert not dlg.provider_combo.isEnabled()
    # The state line shows the gateway default AND that this app follows it.
    state = dlg.route_state.text().lower()
    assert "gateway default: faster-whisper / large-v3" in state
    assert "this app: using the gateway default" in state


@pytest.mark.basic
def test_route_with_local_override_shows_override_mode_and_values() -> None:
    ctl = _StubController()
    ctl.overrides["output.text"] = {"provider": "lmstudio", "model": "ornith-1.0-35b"}
    dlg = _dialog(ctl)
    dlg.route_list.setCurrentRow(_row_index(dlg, "output.text"))

    assert dlg.route_mode_custom.isChecked()
    assert dlg.provider_combo.currentData() == "lmstudio"
    assert dlg.model_combo.currentData() == "ornith-1.0-35b"
    assert dlg.provider_combo.isEnabled()
    state = dlg.route_state.text()
    # Both truths on screen: the moving gateway default and the local pin.
    assert "Gateway default: endpoint:ovh-provider / Meta-Llama-3_3-70B-Instruct" in state
    assert "This app: lmstudio / ornith-1.0-35b (local override)" in state


@pytest.mark.basic
def test_override_apply_stores_local_only_never_gateway() -> None:
    dlg = _dialog()
    dlg.route_list.setCurrentRow(_row_index(dlg, "output.text"))
    dlg.route_mode_custom.setChecked(True)
    dlg.provider_combo.setCurrentIndex(dlg.provider_combo.findData("lmstudio"))
    dlg._refresh_models_for_provider()
    dlg.model_combo.setCurrentIndex(dlg.model_combo.findData("ornith-1.0-35b"))

    dlg._save_route()

    assert dlg._stub.overrides["output.text"] == {
        "provider": "lmstudio",
        "model": "ornith-1.0-35b",
    }
    # The gateway-mutating API must never have been touched.
    assert dlg._stub.gateway_writes == []


@pytest.mark.basic
def test_override_apply_without_selection_refuses_inline() -> None:
    dlg = _dialog()
    dlg.route_list.setCurrentRow(_row_index(dlg, "output.text"))
    dlg.route_mode_custom.setChecked(True)

    dlg._save_route()

    assert "output.text" not in dlg._stub.overrides
    assert "choose a provider" in dlg.route_feedback.text().lower()


@pytest.mark.basic
def test_reset_to_gateway_clears_local_override() -> None:
    ctl = _StubController()
    ctl.overrides["output.voice"] = {"provider": "piper", "model": "en_US-amy-medium"}
    dlg = _dialog(ctl)
    dlg.route_list.setCurrentRow(_row_index(dlg, "output.voice"))
    assert dlg.route_mode_custom.isChecked()

    dlg._reset_route_to_gateway()

    assert "output.voice" not in dlg._stub.overrides
    assert dlg._stub.gateway_writes == []
    assert "gateway default" in dlg.route_feedback.text().lower()


@pytest.mark.basic
def test_default_mode_apply_clears_override_without_gateway_write() -> None:
    ctl = _StubController()
    ctl.overrides["output.text"] = {"provider": "lmstudio", "model": "ornith-1.0-35b"}
    dlg = _dialog(ctl)
    dlg.route_list.setCurrentRow(_row_index(dlg, "output.text"))
    dlg.route_mode_default.setChecked(True)

    dlg._save_route()

    assert "output.text" not in dlg._stub.overrides
    assert dlg._stub.gateway_writes == []


@pytest.mark.basic
def test_default_mode_apply_on_unoverridden_route_is_a_noop() -> None:
    dlg = _dialog()
    dlg.route_list.setCurrentRow(_row_index(dlg, "input.voice"))  # no override

    dlg._save_route()

    assert dlg._stub.overrides == {}
    assert "already using" in dlg.route_feedback.text().lower()


@pytest.mark.basic
def test_reset_button_disabled_without_override() -> None:
    dlg = _dialog()
    dlg.route_list.setCurrentRow(_row_index(dlg, "input.voice"))  # no override
    assert not dlg.reset_route_button.isEnabled()

    ctl = _StubController()
    ctl.overrides["output.voice"] = {"provider": "piper", "model": "en_US-amy-medium"}
    dlg2 = _dialog(ctl)
    dlg2.route_list.setCurrentRow(_row_index(dlg2, "output.voice"))
    assert dlg2.reset_route_button.isEnabled()
