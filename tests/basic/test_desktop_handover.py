"""The gateway console opens the Assistant already signed in (contract A1).

The console launches ``assistant --gateway-url <url> --gateway-handover-file
<path>`` (amendment A-3: the code is never on argv, where ``ps`` shows it, nor in
the environment). The file is a 0600 JSON ``{code, base_url, expires_at}`` the
gateway wrote; the app reads it, deletes it at once, trades the code at
``POST /api/gateway/apps/desktop-handover`` for a remembered session, saves it
in ``gateway_connection.json`` and never needs the code again. A dead code
(expired, already used, file gone) becomes a banner that says what to do next.

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

    def __init__(self, *, status: int = 200, payload: dict | None = None, live_sessions: set | None = None) -> None:
        self.status = status
        self.payload = payload
        self.requests: list[dict] = []
        # Session ids /me accepts (who is still signed in on this gateway).
        self.live_sessions = set(live_sessions or ())
        self.logged_out: list[str] = []
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: D401 - silence
                return

            def _json(self, status: int, data: dict) -> None:
                raw = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):  # noqa: N802
                sid = self.headers.get("X-AbstractGateway-Session") or ""
                if self.path == "/api/gateway/me" and sid in outer.live_sessions:
                    self._json(200, {"ok": True, "principal": {"user_id": "laurent"}})
                else:
                    self._json(401, {"detail": "not signed in"})

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append({"path": self.path, "body": body, "headers": dict(self.headers)})
                if self.path == "/api/gateway/session/logout":
                    outer.logged_out.append(self.headers.get("X-AbstractGateway-Session") or "")
                    self._json(200, {"ok": True})
                    return
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


def _handover_file(tmp_path: Path, **payload) -> Path:
    path = tmp_path / "handover" / "abc.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "abstractgateway.desktop_handover.v1", **payload}), encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.mark.basic
def test_the_file_is_consumed_deleted_and_redeemed_at_its_base_url(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with _FakeGateway() as gw:
        gw.payload = _ok_payload(gw.url)
        path = _handover_file(tmp_path, code="code-9", base_url=gw.url, expires_at="2999-01-01T00:00:00Z")
        # The launch URL is a different (dead) address: the file's base_url wins.
        controller = _controller("http://127.0.0.1:9", data_dir)
        controller.redeem_desktop_handover_file(str(path), fallback_base_url="http://127.0.0.1:9")
    assert not path.exists(), "the hand-over file must be deleted once read"
    assert gw.requests[0]["body"] == {"code": "code-9"}
    stored = json.loads((data_dir / "gateway_connection.json").read_text())
    assert (stored["base_url"], stored["auth_mode"], stored["session_id"]) == (gw.url, "session", "sess-123")


@pytest.mark.basic
def test_an_expired_file_is_deleted_and_never_sent(tmp_path: Path) -> None:
    from abstractassistant.controller import DesktopHandoverError

    with _FakeGateway() as gw:
        gw.payload = _ok_payload(gw.url)
        path = _handover_file(tmp_path, code="old", base_url=gw.url, expires_at="2020-01-01T00:00:00Z")
        controller = _controller(gw.url, tmp_path / "data")
        with pytest.raises(DesktopHandoverError, match="expired"):
            controller.redeem_desktop_handover_file(str(path))
    assert not path.exists()
    assert gw.requests == []


@pytest.mark.basic
@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps({"code": "c", "base_url": "http://127.0.0.1:1", "expires_at": "2999-01-01T00:00:00Z"}),
        json.dumps({"schema": "something.else", "code": "c", "base_url": "http://x", "expires_at": "x"}),
        json.dumps({"schema": "abstractgateway.desktop_handover.v1", "code": "c"}),
    ],
)
def test_a_file_that_is_not_a_hand_over_is_refused_and_left_untouched(tmp_path: Path, content: str) -> None:
    from abstractassistant.controller import DesktopHandoverError, read_desktop_handover_file

    path = tmp_path / "thesis.json"
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(DesktopHandoverError, match="left untouched"):
        read_desktop_handover_file(str(path))
    assert path.read_text(encoding="utf-8") == content


@pytest.mark.basic
def test_never_deletes_a_file_with_the_wrong_mode_a_symlink_or_a_directory(tmp_path: Path) -> None:
    from abstractassistant.controller import DesktopHandoverError, read_desktop_handover_file

    good = {"schema": "abstractgateway.desktop_handover.v1", "code": "c", "base_url": "http://127.0.0.1:1", "expires_at": "2999-01-01T00:00:00Z"}
    loose = tmp_path / "loose.json"
    loose.write_text(json.dumps(good), encoding="utf-8")
    loose.chmod(0o644)
    target = tmp_path / "precious.json"
    target.write_text(json.dumps(good), encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    folder = tmp_path / "dir.json"
    folder.mkdir()
    for candidate in (loose, link, folder):
        with pytest.raises(DesktopHandoverError, match="left untouched"):
            read_desktop_handover_file(str(candidate))
    assert loose.exists() and link.is_symlink() and target.exists() and folder.is_dir()


@pytest.mark.basic
def test_launch_helper_turns_a_dead_hand_over_into_banner_text(tmp_path: Path) -> None:
    from abstractassistant.app import _redeem_launch_handover

    with _FakeGateway(status=410, payload={"ok": False}) as gw:
        controller = _controller(gw.url, tmp_path / "data")
        assert _redeem_launch_handover(controller, base_url=gw.url, handover_file="") == ("", "")
        # Missing file (already consumed by an earlier launch).
        gone, tone = _redeem_launch_handover(controller, base_url=gw.url, handover_file=str(tmp_path / "nope.json"))
        assert tone == "error"
        assert "is gone" in gone and "gateway console" in gone
        # Used code: the gateway answers 410.
        path = _handover_file(tmp_path, code="used", base_url=gw.url, expires_at="2999-01-01T00:00:00Z")
        text, _tone = _redeem_launch_handover(controller, base_url=gw.url, handover_file=str(path))
    assert "expired or was already used" in text and "gateway console" in text and "Settings" in text
    assert not path.exists()


@pytest.mark.basic
def test_the_code_flag_is_gone_from_the_command_line() -> None:
    """Amendment A-3: a code on argv is visible to every local user via ps."""
    help_text = cli.create_parser().format_help()
    assert "--gateway-handover-file" in help_text
    assert "--gateway-handover " not in help_text and "--gateway-handover\n" not in help_text


@pytest.mark.basic
def test_cli_keeps_gateway_url_without_a_token_and_passes_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    import abstractassistant

    called: dict = {}
    monkeypatch.setattr(abstractassistant, "launch_tray_app", lambda **kw: called.update(kw) or 0)
    monkeypatch.setattr(
        sys,
        "argv",
        ["assistant", "--gateway-url", "http://127.0.0.1:18855/", "--gateway-handover-file", "/tmp/x.json"],
    )
    assert cli.main() == 0
    assert called["config"] is not None
    assert called["config"].gateway.url == "http://127.0.0.1:18855"
    assert called["gateway_handover_file"] == "/tmp/x.json"


@pytest.mark.basic
def test_macos_entry_accepts_the_hand_over_file_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import abstractassistant.macos_entry as entry

    called: dict = {}
    monkeypatch.setattr(entry, "launch_tray_app", lambda **kw: called.update(kw) or 0)
    monkeypatch.setattr(
        sys,
        "argv",
        ["Assistant", "-psn_0_123", "--gateway-url", "http://127.0.0.1:18855", "--gateway-handover-file", "/tmp/x.json"],
    )
    assert entry.main() == 0
    assert called["config"].gateway.url == "http://127.0.0.1:18855"
    assert called["gateway_handover_file"] == "/tmp/x.json"


def _save_session(data_dir: Path, *, base_url: str, user: str, sid: str) -> None:
    from abstractassistant.preferences import GatewayConnectionPreferences, GatewayConnectionStore

    GatewayConnectionStore(data_dir / "gateway_connection.json").save(
        GatewayConnectionPreferences(
            base_url=base_url, auth_mode="session", user_id=user, session_id=sid, csrf_token="csrf-old"
        )
    )


@pytest.mark.basic
def test_a_working_session_for_the_same_gateway_is_kept_and_the_code_not_redeemed(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with _FakeGateway(live_sessions={"sess-old"}) as gw:
        gw.payload = _ok_payload(gw.url)
        _save_session(data_dir, base_url=gw.url, user="laurent", sid="sess-old")
        path = _handover_file(tmp_path, code="c1", base_url=gw.url, expires_at="2999-01-01T00:00:00Z")
        controller = _controller(gw.url, data_dir)
        connection, notice = controller.redeem_desktop_handover_file(str(path))
    assert connection.session_id == "sess-old"
    assert "Already connected" in notice and "laurent" in notice
    assert not [r for r in gw.requests if r["path"].endswith("desktop-handover")]
    assert not path.exists()


@pytest.mark.basic
def test_a_dead_session_for_the_same_gateway_is_replaced_quietly(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with _FakeGateway(live_sessions=set()) as gw:
        gw.payload = _ok_payload(gw.url)
        _save_session(data_dir, base_url=gw.url, user="laurent", sid="sess-dead")
        path = _handover_file(tmp_path, code="c1", base_url=gw.url, expires_at="2999-01-01T00:00:00Z")
        connection, notice = _controller(gw.url, data_dir).redeem_desktop_handover_file(str(path))
    assert connection.session_id == "sess-123" and notice == ""


@pytest.mark.basic
def test_a_sign_in_to_another_gateway_is_signed_out_and_announced(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with _FakeGateway(live_sessions={"sess-other"}) as old_gw, _FakeGateway() as gw:
        gw.payload = _ok_payload(gw.url)
        _save_session(data_dir, base_url=old_gw.url, user="alice", sid="sess-other")
        path = _handover_file(tmp_path, code="c1", base_url=gw.url, expires_at="2999-01-01T00:00:00Z")
        connection, notice = _controller(gw.url, data_dir).redeem_desktop_handover_file(str(path))
    assert connection.session_id == "sess-123"
    assert old_gw.logged_out == ["sess-other"]
    assert "Signed in as laurent" in notice and "alice" in notice and old_gw.url in notice and "signed out" in notice


@pytest.mark.basic
def test_a_sign_in_as_another_user_on_the_same_gateway_is_signed_out_and_announced(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with _FakeGateway(live_sessions=set()) as gw:
        gw.payload = _ok_payload(gw.url)
        _save_session(data_dir, base_url=gw.url, user="alice", sid="sess-alice")
        path = _handover_file(tmp_path, code="c1", base_url=gw.url, expires_at="2999-01-01T00:00:00Z")
        connection, notice = _controller(gw.url, data_dir).redeem_desktop_handover_file(str(path))
    assert connection.user_id == "laurent"
    assert gw.logged_out == ["sess-alice"]
    assert "was alice" in notice
