"""R14.2: Settings → Workflow reads and writes the GATEWAY account preference.

GET/PUT /api/gateway/accounts/me/preferences (gateway 0.13.1+): `default_workflow`
{"abstractassistant.agent.v1": null | "bundle:flow" | "catalog:bundle:flow"}; null = the gateway's
per-app default. The real GatewayClient talks to a real HTTP stub of those two routes.

- A device-local choice in preferences.json is uploaded ONCE when the gateway supports the
  route (and the account has no choice yet), then the device key is removed from the file and
  never read again on that gateway.
- An account that already has a choice (made elsewhere) keeps it; the device key still goes.
- A gateway without the route (404, older than 0.13.1) keeps the device choice and the old
  sentence "Saved on this device — applies from the next turn."
- The page saves to the account ("Saved for your account …"), shows "Gateway default (<name>)"
  verbatim from the gateway, and a refusal says "Not saved." + the gateway's sentence.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from test_settings_pages import _dialog  # noqa: E402 (tests/basic is on sys.path)
from test_workflow_selector import _REPORTED, _Gateway, _controller  # noqa: E402

from abstractassistant.controller import AssistantController  # noqa: E402
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig  # noqa: E402
from abstractassistant.preferences import (  # noqa: E402
    WORKFLOW_GATEWAY_DEFAULT,
    AssistantPreferences,
    PreferencesStore,
    workflow_choice_from_value,
    workflow_value_from_choice,
)

IFACE = "abstractassistant.agent.v1"
CHOICES = ["research-agent:agent", "abstractassistant-orchestrator:main"]


class _PrefsStub:
    """GET/PUT /api/gateway/accounts/me/preferences with the gateway's answer shape (or 404)."""

    def __init__(self, *, supported: bool = True, value: Optional[str] = None) -> None:
        self.supported = supported
        self.value = value
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
                if self.path != "/api/gateway/accounts/me/preferences" or not stub.supported:
                    self._send(404, {"detail": "Not Found"})
                    return
                if method == "PUT":
                    value = (body or {}).get("default_workflow", {}).get(IFACE)
                    if value is not None and value not in CHOICES:
                        self._send(400, {"detail": {"reason": "preference_refused", "key": "default_workflow",
                                                    "message": f"default_workflow.{IFACE} = {value!r} refused: workflow bundle 'gone' is not on this gateway."}})
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
        return {
            "ok": True,
            "account": "default:alice",
            "can_edit": True,
            "preferences": {"default_workflow": {IFACE: self.value, "abstractcode.agent.v1": None}},
            "declared": {"default_workflow": {"label": "Default workflow", "help": "…"}},
            "apps": [
                {
                    "interface": IFACE,
                    "label": "Assistant",
                    "value": self.value,
                    "state": "set" if self.value else "default",
                    "reason": None,
                    "gateway_default": {"available": True, "name": "Research agent", "value": "research-agent:agent", "workflow_id": "research-agent@1.10.0:agent", "reason": None},
                    "gateway_default_label": "Gateway default (Research agent)",
                    "choices": [{"value": v, "label": v.split(":")[0]} for v in CHOICES],
                }
            ],
        }

    def puts(self) -> List[Any]:
        return [c["body"] for c in self.calls if c["method"] == "PUT"]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _real(stub: _PrefsStub, tmp_path: Path, device_choice: Any) -> AssistantController:
    """The real controller methods over a fake catalog, the real client on the stub, and a REAL
    preferences.json (so the removal of the device key is read back from the file)."""
    ctl = _controller(_Gateway(_REPORTED), choice=device_choice)
    ctl.gateway = GatewayClient(GatewayClientConfig(base_url=stub.url, auth_token="t", timeout_s=5.0))
    store = PreferencesStore(tmp_path / "preferences.json")
    store.save(ctl.preferences)
    ctl.preferences_store = store
    ctl.update_preferences = AssistantController.update_preferences.__get__(ctl)  # type: ignore[method-assign]
    ctl._cache_ttl_s = 20.0
    return ctl


def _file(tmp_path: Path) -> Dict[str, Any]:
    return json.loads((tmp_path / "preferences.json").read_text())


@pytest.fixture
def stub():
    s = _PrefsStub()
    yield s
    s.close()


DEVICE = {"bundle_id": "research-agent", "flow_id": "agent", "registry_scope": "private"}


@pytest.mark.basic
def test_value_round_trip() -> None:
    assert workflow_value_from_choice(WORKFLOW_GATEWAY_DEFAULT) is None
    assert workflow_value_from_choice(DEVICE) == "research-agent:agent"
    cat = {"bundle_id": "x", "flow_id": "y", "registry_scope": "tenant_catalog"}
    assert workflow_value_from_choice(cat) == "catalog:x:y"
    assert workflow_choice_from_value("catalog:x:y") == cat
    assert workflow_choice_from_value("research-agent@1.2.0:agent") == DEVICE
    assert workflow_choice_from_value(None) == WORKFLOW_GATEWAY_DEFAULT


@pytest.mark.basic
def test_a_device_choice_is_uploaded_once_then_removed_from_the_file(stub, tmp_path) -> None:
    ctl = _real(stub, tmp_path, DEVICE)
    assert _file(tmp_path)["workflow"] == DEVICE, "precondition: the old device choice is in preferences.json"
    assert ctl.workflow_choice() == DEVICE
    assert stub.puts() == [{"default_workflow": {IFACE: "research-agent:agent"}}], "uploaded once"
    assert stub.value == "research-agent:agent"
    assert "workflow" not in _file(tmp_path), "the device key is removed"
    # Never again: fresh reads, a new controller over the same file, the same gateway.
    ctl.account_preferences(fresh=True)
    ctl2 = _controller(_Gateway(_REPORTED), choice=PreferencesStore(tmp_path / "preferences.json").load().workflow)
    ctl2.gateway = ctl.gateway
    assert ctl2.workflow_choice() == DEVICE, "the account's choice, read from the gateway"
    assert len(stub.puts()) == 1
    # The file's absence of a key is the gateway default for a later older gateway too.
    assert AssistantPreferences.from_dict(_file(tmp_path)).workflow == WORKFLOW_GATEWAY_DEFAULT


@pytest.mark.basic
def test_an_account_choice_made_elsewhere_wins_and_the_device_key_still_goes(tmp_path) -> None:
    stub = _PrefsStub(value="abstractassistant-orchestrator:main")
    try:
        ctl = _real(stub, tmp_path, DEVICE)
        assert ctl.workflow_choice() == {"bundle_id": "abstractassistant-orchestrator", "flow_id": "main", "registry_scope": "private"}
        assert stub.puts() == [], "nothing uploaded over the account's own choice"
        assert "workflow" not in _file(tmp_path)
    finally:
        stub.close()


@pytest.mark.basic
def test_a_refused_upload_drops_the_device_key_and_follows_the_gateway_default(stub, tmp_path) -> None:
    ctl = _real(stub, tmp_path, {"bundle_id": "gone", "flow_id": "agent", "registry_scope": "private"})
    assert ctl.workflow_choice() == WORKFLOW_GATEWAY_DEFAULT
    assert len(stub.puts()) == 1 and stub.value is None
    assert "workflow" not in _file(tmp_path)


@pytest.mark.basic
def test_an_older_gateway_keeps_the_device_choice(tmp_path) -> None:
    stub = _PrefsStub(supported=False)
    try:
        ctl = _real(stub, tmp_path, DEVICE)
        assert ctl.workflow_choice() == DEVICE
        assert ctl.workflow_choice_storage() == "device"
        assert ctl.set_workflow_choice(WORKFLOW_GATEWAY_DEFAULT) == "device"
        assert stub.puts() == []
        assert ctl.preferences.workflow == WORKFLOW_GATEWAY_DEFAULT
        assert ctl.set_workflow_choice(DEVICE) == "device"
        assert _file(tmp_path)["workflow"] == DEVICE, "still in preferences.json"
        # The 404 is remembered: every turn's workflow_choice() does not ask the old gateway again.
        for _ in range(5):
            ctl.workflow_choice()
        gets = [c for c in stub.calls if c["method"] == "GET"]
        assert len(gets) == 1, gets
    finally:
        stub.close()


@pytest.mark.basic
def test_settings_page_saves_to_the_account_with_the_gateway_label(stub, tmp_path) -> None:
    dlg, ctl = _dialog()
    real = _real(stub, tmp_path, WORKFLOW_GATEWAY_DEFAULT)
    for name in ("workflow_menu", "workflow_choice", "set_workflow_choice", "flow_app", "open_workflow_in_flow_url"):
        setattr(ctl, name, getattr(real, name))
    page = dlg.page_workflow
    page.refresh()
    assert page.workflow_combo.itemText(0) == "Gateway default (Research agent)", "verbatim from the gateway"
    assert page.selected_choice() == WORKFLOW_GATEWAY_DEFAULT
    index = next(i for i in range(page.workflow_combo.count()) if page._workflow_rows[i]["choice"] != WORKFLOW_GATEWAY_DEFAULT
                 and page._workflow_rows[i]["choice"]["bundle_id"] == "research-agent")
    page.workflow_combo.setCurrentIndex(index)
    page._on_workflow_chosen(index)
    assert stub.value == "research-agent:agent"
    assert page.feedback.text() == "Saved for your account — applies from the next turn, in every app."
    assert "workflow" not in _file(tmp_path), "never written to the device"
    page.refresh()
    assert page.selected_choice()["bundle_id"] == "research-agent"
    # A refusal: "Not saved." + the gateway's sentence; the stored choice stays.
    real.preferences = AssistantPreferences(hotkey_enabled=False)
    page._workflow_rows.append({"choice": {"bundle_id": "gone", "flow_id": "agent", "registry_scope": "private"}, "label": "gone", "detail": ""})
    page.workflow_combo.addItem("gone")
    page._on_workflow_chosen(page.workflow_combo.count() - 1)
    assert page.feedback.text() == (
        f"Not saved. default_workflow.{IFACE} = 'gone:agent' refused: workflow bundle 'gone' is not on this gateway."
    ), page.feedback.text()
    assert stub.value == "research-agent:agent"
    page._on_workflow_chosen(0)
    assert stub.value is None, "Gateway default stores null"
    dlg.close()
