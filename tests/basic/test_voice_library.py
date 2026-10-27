"""The gateway's voice library in the desktop app (AbstractGateway 0.16.0).

- client: languages, cloned voices, voice design, cloning from a file, rename/delete, catalog
  `language`, each on its route;
- voice choices: grouped (your voices first, engine voices, built-in) and labelled with the
  voice's native language;
- the "Create a voice" dialog: the request each tab sends, and the creation through the controller
  off the Qt thread, with the gateway's refusal shown as a sentence.
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
    preset = {"id": "aiden", "label": "Aiden", "voice_kind": "profile"}
    assert voice_group(mine) == "Your voices" and voice_group(builtin) == "Built-in voices" and voice_group(preset) == "Engine voices"
    assert _voice_choice(ChoiceItem(id="v1", label="My voice", meta=mine)).label == "My voice · English  (yours)"
    assert _voice_choice(ChoiceItem(id="c", label="Camille", meta=builtin)).label == "Camille · French  (built-in)"
    assert _voice_choice(ChoiceItem(id="aiden", label="Aiden", meta=preset)).label == "Aiden"


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
