"""R10.4: Settings → Workflow, its own page right after Models.

"Gateway default" first and selected by default; an override among the gateway's
executable workflows round-trips through the controller (preferences); "Open in
AbstractFlow" is an icon button with its tooltip, shown only when the gateway serves
AbstractFlow at /apps/flow/ (GET /api/gateway/apps), and it opens the selected workflow
through POST /api/gateway/apps/flow/open with AbstractFlow's deep link
(/?bundle=<id>&version=<v>&flow=<flow_id>, abstractflow src/utils/bundleDeepLink.ts).
Headless Qt (offscreen) + a real HTTP stub for the apps routes.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from test_settings_pages import _app, _dialog  # noqa: E402 (tests/basic is on sys.path)
from test_workflow_selector import _REPORTED, _Gateway, _controller  # noqa: E402

from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig  # noqa: E402
from abstractassistant.preferences import WORKFLOW_GATEWAY_DEFAULT  # noqa: E402


class _AppsStub:
    """GET /api/gateway/apps and POST /api/gateway/apps/flow/open, recorded."""

    def __init__(self, *, flow: Dict[str, Any] | None) -> None:
        self.flow = flow
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

            def do_GET(self):  # noqa: N802
                stub.calls.append({"method": "GET", "path": self.path})
                apps = [{"id": "code", "installed": True, "mounted": True, "running": True, "app_path": "/apps/code/"}]
                if stub.flow is not None:
                    apps.append(dict(stub.flow))
                self._send(200, {"ok": True, "apps": apps})

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                stub.calls.append({"method": "POST", "path": self.path, "body": body})
                if self.path == "/api/gateway/apps/flow/open":
                    if not (stub.flow or {}).get("running"):
                        self._send(409, {"ok": False, "reason": "not_running", "message": "Flow Editor is not running.", "hint": "Start it first (Launch)."})
                        return
                    self._send(200, {"ok": True, "open_url": "/apps/handover/abc123", "mounted": True})
                    return
                self._send(404, {"detail": "not found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


FLOW_ROW = {"id": "flow", "installed": True, "mounted": True, "running": True, "app_path": "/apps/flow/"}


def _wired(stub: _AppsStub):
    """The Settings dialog over a controller whose workflow list is the real
    service reading a fake catalog, and whose apps calls hit the HTTP stub."""
    dlg, ctl = _dialog()
    real = _controller(_Gateway(_REPORTED))
    real.gateway = GatewayClient(GatewayClientConfig(base_url=stub.url, auth_token="t", timeout_s=5.0))
    for name in ("workflow_menu", "workflow_choice", "set_workflow_choice", "flow_app", "open_workflow_in_flow_url"):
        setattr(ctl, name, getattr(real, name))
    return dlg, real


def _pump(predicate, timeout: float = 5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        _app().processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def flow_stub():
    stub = _AppsStub(flow=dict(FLOW_ROW))
    yield stub
    stub.close()


@pytest.mark.basic
def test_workflow_is_its_own_page_right_after_models(flow_stub) -> None:
    dlg, _real = _wired(flow_stub)
    keys = [dlg.nav.item(i).data(0x0100) for i in range(dlg.nav.count())]
    assert keys.index("workflow") == keys.index("models") + 1
    assert dlg.nav.item(keys.index("workflow")).text() == "Workflow"
    # The Models page no longer carries the workflow card.
    assert not hasattr(dlg.page_models, "workflow_combo")
    dlg.close()


@pytest.mark.basic
def test_gateway_default_first_and_selected_then_override_round_trips(flow_stub) -> None:
    dlg, real = _wired(flow_stub)
    dlg.show_section("workflow")
    page = dlg.page_workflow
    page.refresh()
    assert page.workflow_combo.itemText(0).startswith("Gateway default")
    assert page.workflow_combo.currentIndex() == 0
    assert page.selected_choice() == WORKFLOW_GATEWAY_DEFAULT
    # Override: applies on change (no Save button on the page).
    page.workflow_combo.setCurrentIndex(2)
    page._on_workflow_chosen(2)
    assert real.preferences.workflow["bundle_id"] == "research-agent"
    assert "Saved" in page.feedback.text()
    assert not [b for b in page.findChildren(type(page.open_flow_button)) if b.text() in ("Save", "Apply")]
    # Reopening shows the stored override selected; back to the gateway default.
    page.refresh()
    assert page.selected_choice()["bundle_id"] == "research-agent"
    page._on_workflow_chosen(0)
    assert real.preferences.workflow == WORKFLOW_GATEWAY_DEFAULT
    dlg.close()


@pytest.mark.basic
def test_a_refused_save_says_not_saved_and_keeps_the_stored_choice(flow_stub) -> None:
    dlg, real = _wired(flow_stub)
    page = dlg.page_workflow
    page.refresh()

    def refuse(_choice):
        raise RuntimeError("The preferences file is read-only")

    page.controller.set_workflow_choice = refuse
    page.workflow_combo.setCurrentIndex(2)
    page._on_workflow_chosen(2)
    assert page.feedback.text() == "Not saved. The preferences file is read-only"
    assert page.workflow_combo.currentIndex() == 0
    assert real.preferences.workflow == WORKFLOW_GATEWAY_DEFAULT
    dlg.close()


@pytest.mark.basic
def test_open_in_flow_is_an_icon_button_shown_when_flow_is_served(flow_stub, monkeypatch) -> None:
    dlg, _real = _wired(flow_stub)
    dlg.show_section("workflow")
    page = dlg.page_workflow
    page.refresh()
    assert _pump(lambda: page.flow_state is not None)
    button = page.open_flow_button
    assert button.isVisibleTo(page)
    assert button.text() == "" and not button.icon().isNull()
    assert button.toolTip() == "Open in AbstractFlow"
    opened: List[str] = []
    import abstractassistant.ui.settings.pages as pages_module

    monkeypatch.setattr(pages_module.QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toString()) or True))
    # The gateway default opens the workflow the gateway reports.
    button.click()
    assert _pump(lambda: bool(opened))
    post = [c for c in flow_stub.calls if c["method"] == "POST"][-1]
    assert post["path"] == "/api/gateway/apps/flow/open"
    assert post["body"]["origin"] == flow_stub.url
    path = urlsplit(post["body"]["path"])
    assert path.path == "/"
    assert parse_qs(path.query) == {"bundle": ["research-agent"], "version": ["1.10.0"], "flow": ["agent"]}
    assert opened == [f"{flow_stub.url}/apps/handover/abc123"]
    # A chosen workflow opens at its latest version (no version in the link).
    page.workflow_combo.setCurrentIndex(2)
    button.click()
    assert _pump(lambda: len(opened) == 2)
    post = [c for c in flow_stub.calls if c["method"] == "POST"][-1]
    assert parse_qs(urlsplit(post["body"]["path"]).query) == {"bundle": ["research-agent"], "flow": ["agent"]}
    dlg.close()


@pytest.mark.basic
def test_open_in_flow_is_hidden_when_flow_is_absent() -> None:
    stub = _AppsStub(flow=None)
    try:
        dlg, _real = _wired(stub)
        page = dlg.page_workflow
        page.refresh()
        assert _pump(lambda: page.flow_state is not None)
        assert page.flow_state == {"available": False, "running": False, "app_path": ""}
        assert not page.open_flow_button.isVisibleTo(page)
        dlg.close()
    finally:
        stub.close()
    # Installed but not served through the gateway (no /apps/flow/): hidden too.
    stub = _AppsStub(flow={"id": "flow", "installed": True, "mounted": False, "running": True, "app_path": None})
    try:
        dlg, _real = _wired(stub)
        page = dlg.page_workflow
        page.refresh()
        assert _pump(lambda: page.flow_state is not None)
        assert not page.open_flow_button.isVisibleTo(page)
        dlg.close()
    finally:
        stub.close()


@pytest.mark.basic
def test_flow_not_running_shows_the_gateway_sentence() -> None:
    stub = _AppsStub(flow={**FLOW_ROW, "running": False})
    try:
        dlg, _real = _wired(stub)
        page = dlg.page_workflow
        page.refresh()
        assert _pump(lambda: page.flow_state is not None)
        assert page.open_flow_button.isVisibleTo(page)
        assert "not running" in page.open_flow_button.toolTip()
        page.open_flow_button.click()
        assert _pump(lambda: "Could not open AbstractFlow" in page.feedback.text())
        assert page.feedback.text() == "Could not open AbstractFlow: Flow Editor is not running."
        dlg.close()
    finally:
        stub.close()
