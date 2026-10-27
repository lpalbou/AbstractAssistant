"""The gateway's voice library in the desktop app (AbstractGateway 0.16.0).

- client: languages, cloned voices, voice design, cloning from a file, rename/delete, catalog
  `language`, each on its route;
- voice choices: grouped (your voices first, engine voices, shared) and labelled with the
  voice's native language; a clone is recognised on the record the gateway really emits;
- the "Create a voice" dialog: the request each tab sends (a recording's language detected unless
  chosen; the selected cloning engine sent), the creation through the controller off the Qt thread,
  the gateway's refusal shown as a sentence, and Cancel dropping a late result;
- the route editor: a voice created on another engine switches the route to that engine and selects
  it, or says plainly where it is when this list has no such engine.
"""
from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abstractassistant.gateway import client as client_mod  # noqa: E402
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig  # noqa: E402
from abstractassistant.gateway_service import ChoiceItem, _voice_choice, voice_group  # noqa: E402

pytestmark = pytest.mark.basic


def test_client_voice_library_routes(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(client_mod, "_request_json", fake_request_json)
    gw = GatewayClient(GatewayClientConfig(base_url="http://gateway", auth_token="tok"))
    gw.voice_languages(kind="cloning")
    gw.voice_clones(language="fr")
    gw.voice_design(description="a calm voice", name="Calm", language="en")
    gw.voice_clone_update("v/1", name="New")
    gw.voice_clone_delete("v1")
    gw.voice_voices(provider="qwen3-tts", language="fr", compact=True)
    seen = [(c["method"], c["url"]) for c in calls]
    assert seen[0] == ("GET", "http://gateway/api/gateway/voice/languages?kind=cloning")
    assert seen[1] == ("GET", "http://gateway/api/gateway/voice/clones?language=fr")
    assert seen[2] == ("POST", "http://gateway/api/gateway/voice/design")
    assert calls[2]["body"] == {"description": "a calm voice", "name": "Calm", "language": "en"}
    assert seen[3] == ("PATCH", "http://gateway/api/gateway/voice/clones/v%2F1") and calls[3]["body"] == {"name": "New"}
    assert seen[4] == ("DELETE", "http://gateway/api/gateway/voice/clones/v1")
    assert "language=fr" in seen[5][1]


def test_client_clones_a_recording_as_multipart(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    sent = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true, "voice_id": "c1"}'

    def fake_urlopen(req, timeout=None):
        sent["url"], sent["method"], sent["body"], sent["ctype"] = req.full_url, req.get_method(), req.data, req.headers.get("Content-type")
        return _Resp()

    monkeypatch.setattr(client_mod.urllib.request, "urlopen", fake_urlopen)
    ref = tmp_path / "me.wav"
    ref.write_bytes(b"RIFF-bytes")
    gw = GatewayClient(GatewayClientConfig(base_url="http://gateway", auth_token="tok"))
    out = gw.voice_clone_create(file_path=str(ref), name="Mine", language="fr", reference_text="Bonjour")
    assert out["voice_id"] == "c1"
    assert sent["url"] == "http://gateway/api/gateway/voice/clones" and sent["method"] == "POST"
    assert sent["ctype"].startswith("multipart/form-data")
    for part in (b'name="name"', b"Mine", b'name="language"', b"fr", b'name="reference_text"', b'filename="me.wav"', b"RIFF-bytes"):
        assert part in sent["body"]


def test_voice_choices_are_grouped_and_labelled() -> None:
    mine = {"id": "v1", "label": "My voice", "voice_kind": "clone", "language": "en", "params": {"meta": {"scope": "personal"}}}
    builtin = {"id": "fr-female-camille", "label": "Camille", "voice_kind": "clone", "tags": {"builtin": True, "language_code": "fr"}}
    library = {"id": "v2", "label": "Team voice", "kind": "clone", "params": {"meta": {"scope": "library"}}}
    preset = {"id": "aiden", "label": "Aiden", "voice_kind": "profile"}
    assert voice_group(mine) == "Your voices" and voice_group(preset) == "Engine voices"
    # The third group holds the built-in voices AND the voices the administrator shares.
    assert voice_group(builtin) == "Shared voices" and voice_group(library) == "Shared voices"
    assert _voice_choice(ChoiceItem(id="v1", label="My voice", meta=mine)).label == "My voice · English  (yours)"
    assert _voice_choice(ChoiceItem(id="c", label="Camille", meta=builtin)).label == "Camille · French  (shared)"
    assert _voice_choice(ChoiceItem(id="aiden", label="Aiden", meta=preset)).label == "Aiden"


# The record AbstractGateway's catalog really emits for a cloned voice: the AbstractVoice plugin
# lists each clone in both `voices` and `cloned_voices` (abstractcore_plugin.py), and the gateway's
# merge (`_gateway_catalog_voice_items` / `_gateway_catalog_voice_item`, routes/gateway.py at
# abstractgateway 15987aef) sets `voice_kind: "voice"` with `voice_kinds: ["voice", "clone"]` while
# the record's own `kind` stays "clone". Captured by running those gateway functions on the
# plugin's clone record (2026-10-27); verbatim.
GATEWAY_CLONE_RECORD = {
    "display_name": "My voice", "engine": "qwen3-tts", "engine_id": "qwen3-tts", "id": "a1b2c3", "kind": "clone",
    "label": "My voice", "name": "My voice",
    "params": {"engine": "qwen3-tts", "language": "en", "meta": {"engine": "qwen3-tts", "language": "en", "scope": "personal"},
               "name": "My voice", "reference_text": "Hello there.", "voice_id": "a1b2c3"},
    "profile_id": "a1b2c3", "provider": "qwen3-tts",
    "tags": {"engine": "qwen3-tts", "engine_id": "qwen3-tts", "language_code": "en", "provider": "qwen3-tts", "source": "abstractvoice_clone_store"},
    "voice_id": "a1b2c3", "voice_kind": "voice", "voice_kinds": ["voice", "clone"],
}


def test_a_clone_on_the_gateways_real_record_is_the_persons_own() -> None:
    assert voice_group(GATEWAY_CLONE_RECORD) == "Your voices"
    assert _voice_choice(ChoiceItem(id="a1b2c3", label="My voice", meta=GATEWAY_CLONE_RECORD)).label == "My voice · English  (yours)"
    shared = {**GATEWAY_CLONE_RECORD, "params": {**GATEWAY_CLONE_RECORD["params"], "meta": {"scope": "library"}}}
    assert voice_group(shared) == "Shared voices"


_APP = None


def _app():
    global _APP
    from PyQt5.QtWidgets import QApplication

    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def _wait(pred, timeout=5.0):
    app = _app()
    end = time.time() + timeout
    while time.time() < end and not pred():
        app.processEvents()
        time.sleep(0.01)
    return pred()


def test_create_voice_dialog_designs_through_the_controller() -> None:
    _app()
    from abstractassistant.ui.settings.create_voice_dialog import CreateVoiceDialog

    class Controller:
        def __init__(self):
            self.calls = []

        def design_voice(self, **kw):
            self.calls.append(("design", kw))
            return {"voice_id": "d1", "name": "Calm"}

    ctl = Controller()
    dialog = CreateVoiceDialog(ctl)
    dialog._create()  # nothing described yet: refused locally, no call
    assert "Describe the voice first" in dialog.note.text() and not ctl.calls
    dialog.description.setPlainText("A calm, warm voice")
    dialog.design_name.setText("Calm")
    assert dialog.request() == {"mode": "design", "description": "A calm, warm voice", "name": "Calm", "language": "en"}
    dialog._create()
    assert _wait(lambda: bool(dialog.result_voice))
    assert dialog.result_voice == {"voice_id": "d1", "name": "Calm", "engine": "qwen3-tts"}
    assert ctl.calls == [("design", {"description": "A calm, warm voice", "name": "Calm", "language": "en"})]


def test_a_recordings_language_is_detected_unless_chosen() -> None:
    _app()
    from abstractassistant.ui.settings.create_voice_dialog import CreateVoiceDialog

    class Controller:
        def __init__(self):
            self.calls = []

        def clone_voice(self, **kw):
            self.calls.append(kw)
            return {"voice_id": "c1", "engine": "omnivoice"}

    ctl = Controller()
    dialog = CreateVoiceDialog(ctl)
    # The description keeps a language: design needs one.
    assert dialog.design_language.currentData() == "en" and dialog.design_language.findData("") < 0
    assert dialog.clone_language.itemText(0) == "Detect from the recording" and dialog.clone_language.itemData(0) == ""
    assert dialog.clone_language.currentIndex() == 0
    dialog.tabs.setCurrentIndex(1)
    dialog.file_path.setText("/tmp/me.wav")
    assert dialog.request()["language"] is None
    dialog._create()
    assert _wait(lambda: bool(dialog.result_voice))
    assert ctl.calls[0]["language"] is None
    dialog.clone_language.setCurrentIndex(dialog.clone_language.findData("fr"))
    assert dialog.request()["language"] == "fr"


def test_the_selected_cloning_engine_is_sent_with_a_recording() -> None:
    _app()
    from abstractassistant.ui.settings.create_voice_dialog import CreateVoiceDialog

    class Controller:
        def __init__(self):
            self.calls = []

        def clone_voice(self, **kw):
            self.calls.append(kw)
            return {"voice_id": "c1", "engine": kw.get("provider") or "omnivoice"}

    for provider, sent in (("qwen3-tts", "qwen3-tts"), ("omnivoice", "omnivoice"), ("supertonic", None), ("", None)):
        ctl = Controller()
        dialog = CreateVoiceDialog(ctl, provider=provider)
        dialog.tabs.setCurrentIndex(1)
        dialog.file_path.setText("/tmp/me.wav")
        dialog._create()
        assert _wait(lambda: bool(dialog.result_voice))
        assert ctl.calls[0].get("provider") == sent, (provider, ctl.calls[0])


def test_controller_and_service_pass_the_cloning_engine_to_the_client() -> None:
    from abstractassistant.controller import AssistantController
    from abstractassistant.gateway_service import AssistantGatewayService

    class Client:
        def voice_clone_create(self, **kw):
            self.kw = kw
            return {"voice_id": "c1"}

    client = Client()
    service = AssistantGatewayService(client)
    service.clone_voice(file_path="/tmp/me.wav", provider="qwen3-tts")
    assert client.kw["provider"] == "qwen3-tts"

    class Holder:
        gateway_service = service

    AssistantController.clone_voice(Holder(), file_path="/tmp/me.wav", provider="omnivoice")  # type: ignore[arg-type]
    assert client.kw["provider"] == "omnivoice"


def test_cancel_drops_a_late_result() -> None:
    _app()
    import threading

    from abstractassistant.ui.settings.create_voice_dialog import CreateVoiceDialog

    release = threading.Event()
    done = threading.Event()

    class Controller:
        def design_voice(self, **kw):
            release.wait(5)
            done.set()
            return {"voice_id": "late", "name": "Late"}

    dialog = CreateVoiceDialog(Controller())
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog.description.setPlainText("A calm voice")
    dialog._create()
    dialog.reject()
    release.set()
    assert done.wait(5)
    _wait(lambda: False, timeout=0.3)  # let the late result reach the Qt thread
    assert not accepted and not dialog.result_voice
    assert dialog.result() == CreateVoiceDialog.Rejected


def test_create_voice_dialog_shows_the_gateways_refusal() -> None:
    _app()
    from abstractassistant.ui.settings.create_voice_dialog import CreateVoiceDialog

    class Controller:
        def clone_voice(self, **kw):
            raise RuntimeError("voice_clone_create failed: On this gateway every account shares one voice store.")

    dialog = CreateVoiceDialog(Controller())
    dialog.tabs.setCurrentIndex(1)
    dialog.file_path.setText("/tmp/me.wav")
    dialog._create()
    assert _wait(lambda: "not created" in dialog.note.text())
    assert "shares one voice store" in dialog.note.text() and not dialog.result_voice


# ------------------------------------------------------------------ the route editor


class _FakeCreateDialog:
    """Stands in for CreateVoiceDialog in the route editor: answers a created voice."""

    Accepted = 1
    Rejected = 0
    created: dict = {}
    instances: list = []

    def __init__(self, controller, parent=None, **kwargs):
        self.kwargs = kwargs
        self.result_voice = dict(type(self).created)
        self.deleted = False
        type(self).instances.append(self)

    def exec_(self):
        return self.Accepted if self.result_voice else self.Rejected

    def deleteLater(self):
        self.deleted = True


def _voice_route_dialog(monkeypatch: pytest.MonkeyPatch, created: dict):
    from test_settings_routes import _dialog, _select, _StubController  # the Settings stub of the routes suite

    from abstractassistant.ui.settings import create_voice_dialog

    class Controller(_StubController):
        def voice_choices(self, *, provider: str, model: str, base_url: str = ""):
            if provider == "piper" and model:
                return [ChoiceItem(id="v-new", label="Mine  (yours)")]
            return super().voice_choices(provider=provider, model=model, base_url=base_url)

    _FakeCreateDialog.created = created
    _FakeCreateDialog.instances = []
    monkeypatch.setattr(create_voice_dialog, "CreateVoiceDialog", _FakeCreateDialog)
    dlg = _dialog(Controller())
    _select(dlg, "output.voice")
    dlg.provider_combo.setCurrentIndex(dlg.provider_combo.findData("supertonic"))
    dlg.model_combo.setCurrentIndex(dlg.model_combo.findData("supertonic-3"))
    return dlg


def test_a_voice_created_on_another_listed_engine_switches_the_route_to_it(monkeypatch: pytest.MonkeyPatch) -> None:
    dlg = _voice_route_dialog(monkeypatch, {"voice_id": "v-new", "name": "Mine", "engine": "piper"})
    dlg.route_editor._open_create_voice()
    made = _FakeCreateDialog.instances[0]
    assert made.kwargs.get("provider") == "supertonic"  # the selected provider rides into the dialog
    assert made.deleted  # the dialog is released after use
    assert dlg.provider_combo.currentData() == "piper"
    assert dlg.model_combo.currentData() == "en_US-amy-medium"
    assert dlg.voice_combo.currentData() == "v-new"
    assert dlg._stub.overrides["output.voice"] == {"provider": "piper", "model": "en_US-amy-medium", "options": {"voice": "v-new"}}


def test_a_voice_created_on_an_unlisted_engine_is_said_plainly(monkeypatch: pytest.MonkeyPatch) -> None:
    from abstractassistant.ui.settings import route_editor

    shown = []
    monkeypatch.setattr(route_editor.QMessageBox, "information", staticmethod(lambda parent, title, text, *a, **k: shown.append((title, text))))
    dlg = _voice_route_dialog(monkeypatch, {"voice_id": "q-1", "name": "Narrator", "engine": "qwen3-tts"})
    before = dict(dlg._stub.overrides.get("output.voice") or {})
    dlg.route_editor._open_create_voice()
    assert shown and "qwen3-tts" in shown[0][1] and "Narrator" in shown[0][1]
    assert dlg.provider_combo.currentData() == "supertonic"
    assert dict(dlg._stub.overrides.get("output.voice") or {}) == before
    assert _FakeCreateDialog.instances[0].deleted


def test_a_cancelled_creation_still_releases_the_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    dlg = _voice_route_dialog(monkeypatch, {})
    dlg.route_editor._open_create_voice()
    assert _FakeCreateDialog.instances[0].deleted
