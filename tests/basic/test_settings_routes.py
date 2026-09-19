"""Models settings — LOCAL override contract, and the shape of the control.

Two guarantees live here.

**The contract** (2026-07-18): the assistant's provider/model selection is a
LOCAL override for this app only. It is stored in preferences and sent
per-run/per-call; it must NEVER write the gateway's shared capability default.
Both truths are on screen — the gateway's own default and what THIS app pins on
top — and a route with no override never presents a fabricated provider/model
as if it were configuration (the openai/gpt-4o-transcribe incident).

**The shape** (2026-09-18, operator ask): "use the same design as abstractflow,
where the first item of the dropdown is the gateway default … no need for an
additional radio button. keep the logic and settings as simple and intuitive as
possible." So: no mode radios, no Apply, no Reset, no Reload. The first item of
the Provider list IS "Gateway default", and a choice applies when it is made.

The radio pair that this replaced could be DISABLED — and was, from the second
time Settings was opened onward. `test_the_form_survives_reopening_settings`
pins that; it is the operator's "this was greyed out and i couldn't select to
override the app settings".
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QPushButton

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

    # Flipped to False by the offline tests: every gateway read then fails the
    # way a dead network fails.
    online = True

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

    def _offline_guard(self) -> None:
        if not self.online:
            raise OSError("[Errno 8] nodename nor servname provided, or not known")

    # --- gateway defaults (read-only) ---------------------------------------
    def route_map(self):
        self._offline_guard()
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
    def provider_choices(self, *, route_key: str, base_url: str = ""):
        self._offline_guard()
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

    def model_choices(self, *, route_key: str, provider: str, base_url: str = ""):
        self._offline_guard()
        catalog = {
            "openai": ["gpt-4o-transcribe", "whisper-1"],
            "faster-whisper": ["base", "large-v3"],
            "supertonic": ["supertonic-3"],
            "piper": ["en_US-amy-medium"],
            "lmstudio": ["ornith-1.0-35b", "gemma-3-1b-it"],
            "endpoint:ovh-provider": ["Meta-Llama-3_3-70B-Instruct"],
        }
        return [ChoiceItem(id=m, label=m) for m in catalog.get(provider, [])]

    def voice_choices(self, *, provider: str, model: str, base_url: str = ""):
        self._offline_guard()
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


def _select(dlg, key: str):
    dlg.route_list.setCurrentRow(_row_index(dlg, key))


def _items(combo):
    return [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]


# ============================================================== what is listed


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


# ================================================================== the shape


@pytest.mark.basic
def test_the_first_item_of_each_list_is_the_gateway_default() -> None:
    """The abstractflow shape the operator asked for: one list, its first entry
    is the gateway's own answer."""
    dlg = _dialog()
    _select(dlg, "output.text")

    assert _items(dlg.provider_combo)[0] == ("Gateway default", "")
    assert _items(dlg.model_combo)[0] == ("Gateway default", "")
    assert dlg.reasoning_combo.itemText(0) == "Gateway default"
    assert dlg.reasoning_combo.itemData(0) == ""
    # A route with no override sits on it, and fabricates nothing.
    assert dlg.provider_combo.currentData() == ""
    assert dlg.model_combo.currentData() == ""


@pytest.mark.basic
def test_there_is_no_mode_radio_and_no_apply_reset_or_reload_button() -> None:
    """One question per route. The mode was a second question about the first."""
    dlg = _dialog()
    for gone in ("route_mode_default", "route_mode_custom", "route_mode_group",
                 "save_button", "reset_route_button", "refresh_button"):
        assert not hasattr(dlg.route_editor, gone), gone
        assert not hasattr(dlg, gone), gone
    assert dlg.route_editor.action_buttons() == []
    labels = [b.text() for b in dlg.page_models.findChildren(QPushButton)]
    assert not {"Apply", "Reset to gateway", "Reload"} & set(labels), labels


@pytest.mark.basic
def test_a_stored_override_is_selected_in_the_lists() -> None:
    ctl = _StubController()
    ctl.overrides["output.text"] = {"provider": "lmstudio", "model": "ornith-1.0-35b"}
    dlg = _dialog(ctl)
    _select(dlg, "output.text")

    assert dlg.provider_combo.currentData() == "lmstudio"
    assert dlg.model_combo.currentData() == "ornith-1.0-35b"
    state = dlg.route_state.text()
    # Both truths on screen: the moving gateway default and the local pin.
    assert "Gateway default: endpoint:ovh-provider / Meta-Llama-3_3-70B-Instruct" in state
    assert "This app: lmstudio / ornith-1.0-35b (local override)" in state


# =============================================================== choosing


@pytest.mark.basic
def test_choosing_a_model_applies_it_at_once_and_never_writes_the_gateway() -> None:
    dlg = _dialog()
    _select(dlg, "output.text")

    dlg.provider_combo.setCurrentIndex(dlg.provider_combo.findData("lmstudio"))
    dlg.model_combo.setCurrentIndex(dlg.model_combo.findData("ornith-1.0-35b"))

    # No Apply was pressed. There is none.
    assert dlg._stub.overrides["output.text"] == {
        "provider": "lmstudio",
        "model": "ornith-1.0-35b",
    }
    assert dlg._stub.gateway_writes == []
    assert "lmstudio / ornith-1.0-35b" in dlg.route_feedback.text()


@pytest.mark.basic
def test_choosing_gateway_default_is_the_reset() -> None:
    ctl = _StubController()
    ctl.overrides["output.voice"] = {"provider": "piper", "model": "en_US-amy-medium"}
    dlg = _dialog(ctl)
    _select(dlg, "output.voice")
    assert dlg.provider_combo.currentData() == "piper"

    dlg.provider_combo.setCurrentIndex(0)  # "Gateway default"

    assert "output.voice" not in ctl.overrides
    assert ctl.gateway_writes == []
    assert "gateway default" in dlg.route_feedback.text().lower()
    assert "This app: using the gateway default" in dlg.route_state.text()


@pytest.mark.basic
def test_a_provider_without_a_model_stores_nothing_and_says_what_is_missing() -> None:
    """A half-pin is dropped by the override channel, so storing one would
    show a pin on screen that never rides a request."""
    dlg = _dialog()
    _select(dlg, "output.text")

    dlg.provider_combo.setCurrentIndex(dlg.provider_combo.findData("lmstudio"))

    assert "output.text" not in dlg._stub.overrides
    assert dlg.model_combo.itemText(0) == "Choose a model…"
    assert "choose a model" in dlg.route_feedback.text().lower()
    assert "This app: using the gateway default" in dlg.route_state.text()


@pytest.mark.basic
def test_changing_the_provider_of_an_existing_override_drops_the_stale_model() -> None:
    ctl = _StubController()
    ctl.overrides["output.text"] = {"provider": "lmstudio", "model": "ornith-1.0-35b"}
    dlg = _dialog(ctl)
    _select(dlg, "output.text")

    dlg.provider_combo.setCurrentIndex(dlg.provider_combo.findData("endpoint:ovh-provider"))

    # ornith-1.0-35b does not exist on the new provider: the override goes away
    # rather than pinning a model the provider cannot serve.
    assert "output.text" not in ctl.overrides
    dlg.model_combo.setCurrentIndex(dlg.model_combo.findData("Meta-Llama-3_3-70B-Instruct"))
    assert ctl.overrides["output.text"] == {
        "provider": "endpoint:ovh-provider",
        "model": "Meta-Llama-3_3-70B-Instruct",
    }


@pytest.mark.basic
def test_the_voice_choice_rides_the_override_options() -> None:
    dlg = _dialog()
    _select(dlg, "output.voice")
    dlg.provider_combo.setCurrentIndex(dlg.provider_combo.findData("supertonic"))
    dlg.model_combo.setCurrentIndex(dlg.model_combo.findData("supertonic-3"))
    assert dlg.voice_combo.itemText(0) == "Engine default voice"

    dlg.voice_combo.setCurrentIndex(dlg.voice_combo.findData("M1"))

    assert dlg._stub.overrides["output.voice"]["options"] == {"voice": "M1"}


# ====================================== the greying the operator ran into


@pytest.mark.basic
def test_the_form_survives_reopening_settings() -> None:
    """THE BUG. Operator: "this was greyed out and i couldn't select to
    override the app settings."

    `refresh()` clears the route list, which emits currentRowChanged(-1), which
    disables the form — and nothing turned it back on. app.py caches the
    Settings dialog and calls refresh() on every reopen (app.py:_show_settings),
    so from the SECOND open onward the whole page was dead. Applying a choice or
    pressing Reload did it too. Nothing to do with being offline; that is only
    when the operator noticed.
    """
    dlg = _dialog()
    for _ in range(3):
        dlg.refresh()  # what reopening Settings does
        _select(dlg, "output.text")
        assert dlg.provider_combo.isEnabled()
        assert dlg.model_combo.isEnabled()
        assert dlg.reasoning_combo.isEnabled()

    # Still operable, not just enabled-looking.
    dlg.provider_combo.setCurrentIndex(dlg.provider_combo.findData("lmstudio"))
    dlg.model_combo.setCurrentIndex(dlg.model_combo.findData("gemma-3-1b-it"))
    assert dlg._stub.overrides["output.text"]["model"] == "gemma-3-1b-it"


# ===================================================== a gateway that is away


@pytest.mark.basic
def test_nothing_is_disabled_when_the_gateway_cannot_be_reached() -> None:
    """On a train with no network, "Gateway default" needs no gateway — and
    the list must say why it is short instead of looking empty and broken."""
    ctl = _StubController()
    ctl.online = False
    dlg = _dialog(ctl)
    _select(dlg, "output.text")

    assert dlg.provider_combo.isEnabled()
    assert dlg.model_combo.isEnabled()
    assert _items(dlg.provider_combo) == [("Gateway default", "")]
    feedback = dlg.route_feedback.text().lower()
    assert "no providers to list" in feedback and "retry" in feedback
    # And it must not claim the gateway has no default — it was never asked.
    assert "could not be read" in dlg.route_state.text()
    assert "not configured" not in dlg.route_state.text()


@pytest.mark.basic
def test_an_empty_list_refetches_itself_when_it_is_opened() -> None:
    """What replaced the Reload button: the list retries on open, but only
    while it has nothing to offer."""
    ctl = _StubController()
    ctl.online = False
    dlg = _dialog(ctl)
    _select(dlg, "output.text")
    assert dlg.provider_combo.count() == 1

    ctl.online = True
    dlg.provider_combo.showPopup()
    dlg.provider_combo.hidePopup()

    assert [data for _text, data in _items(dlg.provider_combo)] == ["", "lmstudio", "endpoint:ovh-provider"]
    assert dlg.route_feedback.text() == ""
    # The gateway's own defaults were recovered too, not just the catalog.
    assert "Gateway default: endpoint:ovh-provider" in dlg.route_state.text()

    # A healthy list is left alone: opening it does not re-fetch.
    calls = {"n": 0}
    original = ctl.provider_choices

    def _counted(**kwargs):
        calls["n"] += 1
        return original(**kwargs)

    ctl.provider_choices = _counted  # type: ignore[assignment]
    dlg.provider_combo.showPopup()
    dlg.provider_combo.hidePopup()
    assert calls["n"] == 0


@pytest.mark.basic
def test_walking_the_route_list_writes_nothing() -> None:
    """Apply-on-change must not fire while the page is loading a route — every
    combo is repopulated on the way in, and each of those is an index change."""
    ctl = _StubController()
    ctl.overrides["output.text"] = {"provider": "lmstudio", "model": "ornith-1.0-35b"}
    dlg = _dialog(ctl)
    saved = []
    dlg.route_editor.changed.connect(lambda: saved.append(1))

    for key in ("output.text", "output.voice", "input.voice", "output.music", "output.text"):
        _select(dlg, key)

    assert ctl.overrides == {"output.text": {"provider": "lmstudio", "model": "ornith-1.0-35b"}}
    assert saved == [], "browsing is not a change"


@pytest.mark.basic
def test_opening_settings_costs_two_gateway_reads_not_seven() -> None:
    """Every one of these is a synchronous urlopen on the GUI thread, and the
    client's timeout is 30 s — so the count IS the freeze when the gateway is
    away (measured on HEAD against a black-hole host: 61 s for one refresh).

    Two defects made it seven. `refresh()` called `_load_selected_route`
    explicitly after `setCurrentRow`, believing row 0 would not re-emit — it
    does, because `clear()` had already moved the row to -1 — so every catalog
    fetch was paid twice. And the reasoning caption asked the controller for
    the effective chat route, which re-reads the capability defaults and does
    not cache a failure; the editor already holds both facts.
    """
    calls: list[str] = []

    class _Counting(_StubController):
        def route_map(self):
            calls.append("route_map")
            return super().route_map()

        def provider_choices(self, **kwargs):
            calls.append("provider_choices")
            return super().provider_choices(**kwargs)

        def model_choices(self, **kwargs):
            calls.append("model_choices")
            return super().model_choices(**kwargs)

        def effective_chat_route(self):  # pragma: no cover - must not be reached
            calls.append("effective_chat_route")
            return {"provider": "", "model": "", "source": "gateway"}

    dlg = _dialog(_Counting())
    assert calls == ["route_map", "provider_choices"], calls

    calls.clear()
    dlg.refresh()  # reopening Settings
    assert calls == ["route_map", "provider_choices"], calls


@pytest.mark.basic
def test_a_saved_choice_the_catalog_no_longer_lists_stays_selected() -> None:
    """Unreachable gateway must not silently discard a stored override."""
    ctl = _StubController()
    ctl.overrides["output.text"] = {"provider": "lmstudio", "model": "ornith-1.0-35b"}
    ctl.online = False
    dlg = _dialog(ctl)
    _select(dlg, "output.text")

    assert dlg.provider_combo.currentData() == "lmstudio"
    assert dlg.model_combo.currentData() == "ornith-1.0-35b"
    assert "(saved)" in dlg.provider_combo.currentText()
    assert ctl.overrides["output.text"] == {"provider": "lmstudio", "model": "ornith-1.0-35b"}
