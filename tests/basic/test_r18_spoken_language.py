"""Round 18: the spoken language is the ACCOUNT's preference, read and written on the gateway.

GET /api/gateway/accounts/me/preferences serves a ``spoken_language`` block
``{value, label, help, choices: [{value, label}]}`` (abstractgateway.spoken_language); PUT
``{"spoken_language": "fr"}`` stores it; an unknown code is a 400 ``preference_refused`` whose
``message`` is the voice layer's sentence. The Assistant keeps no copy and no list of its own:
Settings → Voice shows the served row and the voice strip names the served label.
The real GatewayClient talks to a real HTTP stub of the two routes.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from test_settings_pages import _dialog  # noqa: E402 (tests/basic is on sys.path)
from test_workflow_selector import _REPORTED, _Gateway, _controller  # noqa: E402

from abstractassistant.controller import AssistantController, spoken_language_label  # noqa: E402
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig, GatewayHttpError  # noqa: E402

HELP = (
    "The language spoken to the microphone. Auto lets the speech engine detect it; naming it skips "
    "detection, so short phrases and mixed-language speech transcribe reliably and a little faster."
)
CHOICES = [
    {"value": "auto", "label": "Auto (detected)"},
    {"value": "en", "label": "English"},
    {"value": "fr", "label": "French"},
    {"value": "de", "label": "German"},
]
REFUSAL = (
    "spoken_language = 'xx' refused: not a language the speech engines support. "
    "Choose auto or one of: de, en, fr."
)


def _block(value: str = "auto") -> Dict[str, Any]:
    return {"value": value, "label": "Spoken language", "help": HELP, "choices": [dict(c) for c in CHOICES]}


class _PrefsStub:
    """GET/PUT /api/gateway/accounts/me/preferences with the round-18 answer shape."""

    def __init__(self, *, serve_block: bool = True) -> None:
        self.value = "auto"
        self.serve_block = serve_block
        self.calls: List[Dict[str, Any]] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):  # noqa: D401
                return

            def _send(self, status: int, body: Dict[str, Any]) -> None:
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _route(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}") if length else None
                stub.calls.append({"method": method, "path": self.path, "body": body})
                if self.path != "/api/gateway/accounts/me/preferences":
                    self._send(404, {"detail": "Not Found"})
                    return
                if method == "PUT" and "spoken_language" in (body or {}):
                    value = (body or {}).get("spoken_language")
                    value = "auto" if value in (None, "") else str(value)
                    if value not in {c["value"] for c in CHOICES}:
                        self._send(400, {"detail": {"reason": "preference_refused", "key": "spoken_language", "message": REFUSAL}})
                        return
                    stub.value = value
                self._send(200, stub.answer())

            def do_GET(self):  # noqa: N802
                self._route("GET")

            def do_PUT(self):  # noqa: N802
                self._route("PUT")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def answer(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "ok": True,
            "account": "default:alice",
            "can_edit": True,
            "preferences": {"default_workflow": {}, "time_zone": None, "spoken_language": self.value},
            "apps": [],
        }
        if self.serve_block:
            out["spoken_language"] = _block(self.value)
        return out

    def puts(self) -> List[Any]:
        return [c["body"] for c in self.calls if c["method"] == "PUT"]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub():
    s = _PrefsStub()
    yield s
    s.close()


def _real(stub: _PrefsStub) -> AssistantController:
    ctl = _controller(_Gateway(_REPORTED))
    ctl.gateway = GatewayClient(GatewayClientConfig(base_url=stub.url, auth_token="t", timeout_s=5.0))
    ctl._cache_ttl_s = 20.0
    return ctl


# ------------------------------------------------------------------ controller


@pytest.mark.basic
def test_the_controller_reads_the_served_block(stub) -> None:
    ctl = _real(stub)
    block = ctl.account_spoken_language()
    assert block == _block("auto")
    assert ctl.spoken_language_label() == "Auto (detected)"
    assert [c["method"] for c in stub.calls] == ["GET"]


@pytest.mark.basic
def test_the_controller_puts_the_choice_and_keeps_the_answer(stub) -> None:
    ctl = _real(stub)
    ctl.account_spoken_language()
    block = ctl.set_spoken_language("fr")
    assert stub.puts() == [{"spoken_language": "fr"}], "ONE PUT, the code only"
    assert block["value"] == "fr"
    # The PUT's answer is the cached truth: no second GET to read it back.
    gets_before = sum(1 for c in stub.calls if c["method"] == "GET")
    assert ctl.account_spoken_language()["value"] == "fr"
    assert ctl.spoken_language_label() == "French"
    assert sum(1 for c in stub.calls if c["method"] == "GET") == gets_before


@pytest.mark.basic
def test_a_refusal_raises_with_the_gateways_sentence_and_keeps_nothing(stub) -> None:
    from abstractassistant.ui.settings.pages import _gateway_sentence

    ctl = _real(stub)
    ctl.account_spoken_language()
    with pytest.raises(GatewayHttpError) as info:
        ctl.set_spoken_language("xx")
    assert info.value.status == 400
    assert _gateway_sentence(info.value) == REFUSAL
    assert ctl.account_spoken_language()["value"] == "auto", "nothing kept locally"


@pytest.mark.basic
def test_no_block_reads_as_none() -> None:
    s = _PrefsStub(serve_block=False)
    try:
        ctl = _real(s)
        assert ctl.account_spoken_language() is None
        assert ctl.spoken_language_label() == ""
    finally:
        s.close()


@pytest.mark.basic
def test_the_label_helper_names_only_a_served_choice() -> None:
    assert spoken_language_label(_block("de")) == "German"
    assert spoken_language_label(None) == ""
    assert spoken_language_label({"value": "xx", "choices": CHOICES}) == ""


# ------------------------------------------------------------ Settings → Voice


class _LangController:
    """The two controller methods the Voice page uses, over a served block."""

    def __init__(self, value: str = "auto") -> None:
        self.block = _block(value)
        self.puts: List[str] = []
        self.refuse = ""

    def account_spoken_language(self):
        return dict(self.block)

    def set_spoken_language(self, value):
        self.puts.append(value)
        if self.refuse:
            raise GatewayHttpError(
                "refused", status=400,
                body_text=json.dumps({"detail": {"reason": "preference_refused", "key": "spoken_language", "message": self.refuse}}),
            )
        self.block = _block(value)
        return dict(self.block)


def _voice_page(lang):
    dlg, ctl = _dialog()
    if lang is None:
        ctl.account_spoken_language = lambda: None
    else:
        ctl.account_spoken_language = lang.account_spoken_language
        ctl.set_spoken_language = lang.set_spoken_language
    page = dlg.page_voice
    page.refresh()
    return dlg, page


@pytest.mark.basic
def test_the_voice_page_shows_the_served_row() -> None:
    lang = _LangController("de")
    dlg, page = _voice_page(lang)
    combo = page.spoken_language_combo
    assert page.spoken_language_row.label_widget.text() == "Spoken language"
    assert [combo.itemText(i) for i in range(combo.count())] == [c["label"] for c in CHOICES]
    assert [combo.itemData(i) for i in range(combo.count())] == [c["value"] for c in CHOICES]
    assert combo.currentText() == "German" and combo.isEnabled()
    assert page.spoken_language_help.text() == HELP
    assert page.spoken_language_help.property("tone") == ""
    dlg.close()


@pytest.mark.basic
def test_picking_french_puts_fr_once_and_says_saved() -> None:
    lang = _LangController("auto")
    dlg, page = _voice_page(lang)
    combo = page.spoken_language_combo
    index = combo.findText("French")
    combo.setCurrentIndex(index)
    combo.activated.emit(index)
    assert lang.puts == ["fr"], "ONE PUT with the served value"
    assert page.feedback.text() == "Saved."
    assert combo.currentText() == "French"
    # Re-picking the stored value sends nothing.
    combo.activated.emit(index)
    assert lang.puts == ["fr"]
    dlg.close()


@pytest.mark.basic
def test_a_refusal_says_not_saved_and_keeps_the_shown_value() -> None:
    lang = _LangController("en")
    dlg, page = _voice_page(lang)
    lang.refuse = REFUSAL
    combo = page.spoken_language_combo
    index = combo.findText("German")
    combo.setCurrentIndex(index)
    combo.activated.emit(index)
    assert lang.puts == ["de"]
    assert page.feedback.text() == f"Not saved. {REFUSAL}"
    assert page.feedback.property("tone") == "error"
    assert combo.currentText() == "English", "the stored value stays shown"
    dlg.close()


@pytest.mark.basic
def test_no_block_disables_the_row_and_says_so_in_the_error_tone() -> None:
    from abstractassistant.ui.settings.pages import SPOKEN_LANGUAGE_NOT_SERVED

    dlg, page = _voice_page(None)
    assert SPOKEN_LANGUAGE_NOT_SERVED == "The gateway's account preferences answer has no spoken_language block."
    combo = page.spoken_language_combo
    assert not combo.isEnabled() and combo.count() == 0
    assert page.spoken_language_help.text() == SPOKEN_LANGUAGE_NOT_SERVED
    assert page.spoken_language_help.property("tone") == "error"
    assert page.spoken_language_row.isVisibleTo(page), "never a hidden row"
    dlg.close()


# ------------------------------------------------------------------ voice strip


@pytest.mark.basic
def test_the_voice_strip_names_the_served_label() -> None:
    from abstractassistant.ui.voice_strip import VoiceStrip

    strip = VoiceStrip()
    assert strip.language.isHidden() and strip.language.text() == ""
    strip.set_spoken_language("Auto (detected)")
    assert strip.language.text() == "Spoken language: Auto (detected)"
    assert strip.language.toolTip() == "Spoken language: Auto (detected)"
    assert not strip.language.isHidden()
    strip.set_spoken_language("")
    assert strip.language.isHidden() and strip.language.text() == ""


@pytest.mark.basic
def test_the_strip_label_follows_a_settings_change(stub) -> None:
    """Decision: the strip re-reads the controller when a voice input opens; a PUT from
    Settings is the controller's cached answer, so the next open shows the new label."""
    ctl = _real(stub)
    assert ctl.spoken_language_label() == "Auto (detected)"
    ctl.set_spoken_language("fr")
    from abstractassistant.ui.voice_strip import VoiceStrip

    strip = VoiceStrip()
    strip.set_spoken_language(ctl.spoken_language_label())
    assert strip.language.text() == "Spoken language: French"
