"""The served schedule fields are OPTIONAL on read (2026-10-09 operator report).

A gateway before round 16 (0.13.x) serves no ``time_zone`` / ``next_run_at`` /
``next_run_local`` / ``schedule_text`` / ``schedule_rule_text`` on its rows —
only ``next_fire_at`` — and a client that requires them fails the whole list.
``fixtures/legacy_summary/list-gateway-0.13.json`` is a COPY of that live
summary's shape. The list must read through the real client (loopback stub),
its rule reads "—" and its next run falls back to ``next_fire_at`` (UTC).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from abstractassistant.core.automations import (
    NOT_SERVED,
    control_hint,
    group_by_automation,
    next_run_text,
    served_summary,
    trigger_summary,
)
from abstractassistant.gateway.automations import AutomationsClient
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig

PAGE = json.loads((Path(__file__).parent / "fixtures" / "legacy_summary" / "list-gateway-0.13.json").read_text(encoding="utf-8"))
ROW = PAGE["items"][0]
NOW = datetime(2026, 10, 9, 16, 53, 29, tzinfo=timezone.utc)


def test_a_pre_round_16_row_reads_with_next_fire_at_and_dashes() -> None:
    s = served_summary(ROW)
    assert (s["next_run_at"], s["next_run_local"], s["time_zone"]) == (
        "2026-10-09T19:53:29.622724+00:00", "2026-10-09T19:53:29.622724+00:00", "UTC")
    assert s["schedule_rule_text"] == s["schedule_text"] == NOT_SERVED == "—"
    assert trigger_summary(s["trigger"], s) == "—"
    assert next_run_text(s, now=NOW) == "next in 3 h"
    assert "2026-10-09 19:53 UTC" in control_hint("run_now", s)
    assert "time_zone" not in ROW, "the input is not changed"
    from abstractassistant.ui.automations import _next_run_text

    assert _next_run_text(s, now=NOW) == "next 2026-10-09 19:53 UTC (in 3 h)"
    # Invalid types are as absent as missing ones; no next run served → none (never computed).
    bad = served_summary({**ROW, "time_zone": 5, "schedule_rule_text": ["x"], "next_run_local": None})
    assert (bad["time_zone"], bad["schedule_rule_text"]) == ("UTC", "—")
    none = served_summary({k: v for k, v in ROW.items() if k != "next_fire_at"})
    assert "next_run_at" not in none and none["time_zone"] == ""
    assert next_run_text(none, now=NOW) == "next —"
    # A round-16 row keeps its served values.
    r16 = served_summary({**ROW, "time_zone": "Europe/Paris", "next_run_at": ROW["next_fire_at"],
                          "next_run_local": "2026-10-09T21:53:29.622724+02:00", "schedule_rule_text": "Every 24 hours (UTC)"})
    assert trigger_summary(r16["trigger"], r16) == "Every 24 hours (UTC)"
    assert _next_run_text(r16, now=NOW) == "next 2026-10-09 21:53 Europe/Paris (in 3 h)"


class _Stub:
    """Loopback GET /api/gateway/automations[/{id}] answering the 0.13.x shape."""

    def __init__(self) -> None:
        class H(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                path = self.path.split("?", 1)[0]
                if path == "/api/gateway/automations":
                    body = PAGE
                elif path == f"/api/gateway/automations/{ROW['automation_id']}":
                    body = {"definition": {"revision": 4}, "active_revision": 4, "summary": ROW}
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"


def test_the_client_lists_and_gets_a_pre_round_16_row() -> None:
    stub = _Stub()
    try:
        client = AutomationsClient(GatewayClient(GatewayClientConfig(base_url=stub.url, auth_token="test-token", timeout_s=5.0)))
        rows = client.list_all()
        assert [(r["title"], r["time_zone"], r["schedule_rule_text"]) for r in rows] == [("Daily price watch", "UTC", "—")]
        assert group_by_automation(rows)
        detail = client.get(ROW["automation_id"])
        assert detail["summary"]["next_run_at"] == ROW["next_fire_at"]
    finally:
        stub.server.shutdown()
