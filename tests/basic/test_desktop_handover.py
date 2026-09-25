"""The gateway console opens the Assistant already signed in (contract A1).

The console launches ``assistant --gateway-url <url> --gateway-handover <code>``
with nothing gateway-related in the environment. The app trades the one-time
code at ``POST /api/gateway/apps/desktop-handover`` for a remembered session,
saves it in ``gateway_connection.json`` and never needs the code again. A dead
code (expired, already used) becomes a banner that says what to do next.

Before this, ``--gateway-url`` without ``--gateway-token`` was silently dropped:
``cli.py`` built its config with ``require_auth_token=True`` and the app path
swallowed the exception.
"""

from __future__ import annotations

import json
import stat
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from abstractassistant import cli


class _FakeGateway:
    """Loopback HTTP server answering the handover route (and nothing else)."""

    def __init__(self, *, status: int = 200, payload: dict | None = None) -> None:
        self.status = status
        self.payload = payload
        self.requests: list[dict] = []
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: D401 - silence
                return

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append({"path": self.path, "body": body, "headers": dict(self.headers)})
                if self.path != "/api/gateway/apps/desktop-handover":
                    self.send_response(404)
                    self.end_headers()
                    return
                data = json.dumps(outer.payload or {}).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def _ok_payload(url: str) -> dict:
    return {
        "base_url": url,
        "session_id": "sess-123",
        "csrf_token": "csrf-456",
        "user_id": "laurent",
        "expires_at": "2026-10-25T00:00:00Z",
    }


def _controller(url: str, data_dir: Path):
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController

    return AssistantController(config=Config.from_dict({"gateway": {"url": url}}), data_dir=data_dir)


@pytest.mark.basic
def test_client_redeems_the_code_and_switches_to_session_auth() -> None:
    from abstractassistant.gateway import GatewayClient, GatewayClientConfig

    with _FakeGateway() as gw:
        gw.payload = _ok_payload(gw.url)
        client = GatewayClient(GatewayClientConfig(base_url=gw.url))
        client.redeem_desktop_handover("code-1")
    assert gw.requests[0]["body"] == {"code": "code-1"}
    assert "Authorization" not in gw.requests[0]["headers"]
    cfg = client.config
    assert (cfg.auth_mode, cfg.session_id, cfg.csrf_token, cfg.user_id) == ("session", "sess-123", "csrf-456", "laurent")


@pytest.mark.basic
def test_client_refuses_a_success_without_a_session() -> None:
    from abstractassistant.gateway import GatewayClient, GatewayClientConfig

    with _FakeGateway(payload={"ok": True}) as gw:
        client = GatewayClient(GatewayClientConfig(base_url=gw.url))
        with pytest.raises(RuntimeError, match="without a session"):
            client.redeem_desktop_handover("code-1")


@pytest.mark.basic
def test_controller_persists_the_redeemed_session(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with _FakeGateway() as gw:
        gw.payload = _ok_payload(gw.url)
        controller = _controller(gw.url, data_dir)
        controller.redeem_desktop_handover(base_url=gw.url, code="code-1")

    stored_path = data_dir / "gateway_connection.json"
    stored = json.loads(stored_path.read_text())
    assert stored["base_url"] == gw.url
    assert stored["auth_mode"] == "session"
    assert stored["remember_session"] is True
    assert stored["session_id"] == "sess-123"
    assert stored["csrf_token"] == "csrf-456"
    assert stored["user_id"] == "laurent"
    assert stored["auth_token"] == ""
    assert stat.S_IMODE(stored_path.stat().st_mode) == 0o600
    # The live client uses the session at once (no restart needed).
    assert controller.gateway.config.session_id == "sess-123"
    assert controller.gateway.config.auth_mode == "session"


@pytest.mark.basic
def test_next_launch_with_only_gateway_url_keeps_the_saved_session(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with _FakeGateway() as gw:
        gw.payload = _ok_payload(gw.url)
        _controller(gw.url, data_dir).redeem_desktop_handover(base_url=gw.url, code="code-1")
        # Relaunched by the console WITHOUT a code (or by hand with --gateway-url).
        again = _controller(gw.url, data_dir)
    assert again.connection.auth_mode == "session"
    assert again.connection.session_id == "sess-123"


@pytest.mark.basic
@pytest.mark.parametrize(
    ("status", "needle"),
    [(410, "expired or was already used"), (403, "gateway's own machine"), (404, "newer AbstractGateway")],
)
def test_a_refused_code_is_a_sentence_the_user_can_act_on(tmp_path: Path, status: int, needle: str) -> None:
    from abstractassistant.controller import DesktopHandoverError

    with _FakeGateway(status=status, payload={"ok": False, "message": "no"}) as gw:
        controller = _controller(gw.url, tmp_path / "data")
        with pytest.raises(DesktopHandoverError) as info:
            controller.redeem_desktop_handover(base_url=gw.url, code="dead")
    text = str(info.value)
    assert needle in text
    assert "gateway console" in text and "Settings" in text
    assert not (tmp_path / "data" / "gateway_connection.json").exists()


@pytest.mark.basic
def test_launch_helper_turns_a_dead_code_into_banner_text(tmp_path: Path) -> None:
    from abstractassistant.app import _redeem_launch_handover

    with _FakeGateway(status=410, payload={"ok": False}) as gw:
        controller = _controller(gw.url, tmp_path / "data")
        assert _redeem_launch_handover(controller, base_url=gw.url, code="") == ""
        text = _redeem_launch_handover(controller, base_url=gw.url, code="dead")
    assert "expired" in text and "gateway console" in text


@pytest.mark.basic
def test_cli_keeps_gateway_url_without_a_token_and_passes_the_code(monkeypatch: pytest.MonkeyPatch) -> None:
    import abstractassistant

    called: dict = {}
    monkeypatch.setattr(abstractassistant, "launch_tray_app", lambda **kw: called.update(kw) or 0)
    monkeypatch.setattr(
        sys, "argv", ["assistant", "--gateway-url", "http://127.0.0.1:18855/", "--gateway-handover", "abc"]
    )
    assert cli.main() == 0
    assert called["config"] is not None
    assert called["config"].gateway.url == "http://127.0.0.1:18855"
    assert called["gateway_handover"] == "abc"


@pytest.mark.basic
def test_macos_entry_accepts_the_handover_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import abstractassistant.macos_entry as entry

    called: dict = {}
    monkeypatch.setattr(entry, "launch_tray_app", lambda **kw: called.update(kw) or 0)
    monkeypatch.setattr(
        sys,
        "argv",
        ["Assistant", "-psn_0_123", "--gateway-url", "http://127.0.0.1:18855", "--gateway-handover", "abc"],
    )
    assert entry.main() == 0
    assert called["config"].gateway.url == "http://127.0.0.1:18855"
    assert called["gateway_handover"] == "abc"
