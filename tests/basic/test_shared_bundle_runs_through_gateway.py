"""A SHARED workflow started from the Assistant resolves and runs (C3F / adversary A26).

The Assistant's Settings → Workflow list is ``GET /bundles?executable_for=abstractassistant.agent.v1``
and each row carries ``registry_scope: "private"``. On a multi-user gateway ``private`` is
the signed-in principal's OWN bundle registry, which loads the admin's shared flows dir
read-only next to the principal's own ``<data>/users/<tenant>/<user>/flows``: so a shared
(gateway-owned) bundle started with ``registry_scope="private"`` resolves from the shared dir.

This drives the REAL gateway app (abstractgateway, hosted user auth ON, a non-admin user)
through the Assistant's own code path: ``GatewayClient.executable_bundles`` →
``AssistantGatewayService._catalog_workflows`` (contract-checked) → ``GatewayClient.start_run``
with the row's ``bundle_id``/``bundle_version``/``flow_id``/``registry_scope`` (what the chat
worker sends, ``ui/gateway_worker.py``). The client's HTTP function is routed into the
in-process app (``fastapi.testclient``); nothing else is stubbed.

It needs the gateway importable (the framework's integration environment); the Assistant's
own CI has no gateway and skips it with that reason.
"""

from __future__ import annotations

import io
import json
import time
import urllib.parse
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi.testclient", reason="needs the gateway's test client (fastapi)")
# Only the package here: the app reads its security settings when imported, so it is
# imported inside the fixture, after the environment below is set.
pytest.importorskip("abstractgateway", reason="needs abstractgateway importable")

from fastapi.testclient import TestClient  # noqa: E402

from abstractassistant.gateway import client as client_mod  # noqa: E402
from abstractassistant.gateway.client import GatewayClient, GatewayClientConfig, GatewayHttpError  # noqa: E402
from abstractassistant.gateway_service import ASSISTANT_INTERFACE, AssistantGatewayService  # noqa: E402

SHARED_ID = "shared-assistant-agent"
ADMIN = {"Authorization": "Bearer admin-token"}


def _node(node_id: str, node_type: str, **extra) -> dict:
    data = {"nodeType": node_type, "label": node_type}
    data.update(extra)
    return {"id": node_id, "type": node_type, "position": {"x": 0, "y": 0}, "data": data}


def _edge(s: str, sh: str, t: str, th: str, i: str) -> dict:
    return {"id": i, "source": s, "sourceHandle": sh, "target": t, "targetHandle": th}


def _write_shared_bundle(shared: Path) -> None:
    flow = {
        "id": "agent",
        "name": "Shared assistant agent",
        "interfaces": [ASSISTANT_INTERFACE],
        "nodes": [
            _node("start", "on_flow_start", outputs=[{"id": "exec-out", "label": "", "type": "execution"}, {"id": "prompt", "label": "Prompt", "type": "string"}]),
            _node("result", "code", codeBody="return {'answer': 'shared bundle ran'}"),
            _node("end", "on_flow_end"),
        ],
        "edges": [
            _edge("start", "exec-out", "result", "exec-in", "e1"),
            _edge("result", "exec-out", "end", "exec-in", "e2"),
            _edge("result", "output", "end", "result", "e3"),
        ],
        "entryNode": "start",
    }
    manifest = {
        "bundle_format_version": "1", "bundle_id": SHARED_ID, "bundle_version": "1.0.0",
        "created_at": "2026-10-01T00:00:00+00:00", "default_entrypoint": "agent",
        "entrypoints": [{"flow_id": "agent", "name": "Shared assistant agent", "interfaces": [ASSISTANT_INTERFACE]}],
        "flows": {"agent": "flows/agent.json"}, "artifacts": {}, "assets": {},
    }
    shared.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("flows/agent.json", json.dumps(flow))
    (shared / f"{SHARED_ID}@1.0.0.flow").write_bytes(buf.getvalue())


@pytest.fixture()
def gateway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    shared = tmp_path / "bundles"
    _write_shared_bundle(shared)
    data = tmp_path / "data"
    for key, value in {
        "ABSTRACTGATEWAY_DATA_DIR": str(data),
        "ABSTRACTGATEWAY_FLOWS_DIR": str(shared),
        "ABSTRACTGATEWAY_WORKFLOW_SOURCE": "bundle",
        "ABSTRACTGATEWAY_AUTH_TOKEN": "admin-token",
        "ABSTRACTGATEWAY_USERS_FILE": str(tmp_path / "users.json"),
        "ABSTRACTGATEWAY_SESSIONS_FILE": str(tmp_path / "sessions.json"),
        "ABSTRACTGATEWAY_USER_AUTH": "1",
        "ABSTRACTGATEWAY_ALLOWED_ORIGINS": "*",
        "ABSTRACTGATEWAY_POLL_S": "0.05",
    }.items():
        monkeypatch.setenv(key, value)
    from abstractgateway.service import reset_gateway_boot_state
    from abstractgateway.users import GatewayUserRegistry

    reset_gateway_boot_state()
    _rec, alice_token = GatewayUserRegistry().create_user(user_id="alice", roles=["user"], runtime_id="alice")
    from abstractgateway.app import app

    with TestClient(app) as http:

        def request_json(*, method, url, headers, body=None, timeout_s, label):
            parts = urllib.parse.urlsplit(url)
            path = parts.path + (f"?{parts.query}" if parts.query else "")
            res = http.request(method.upper(), path, headers=dict(headers), json=body)
            if res.status_code >= 400:
                raise GatewayHttpError(f"{label}: {res.text}", status=res.status_code, body_text=res.text)
            return res.json() if res.content else {}

        monkeypatch.setattr(client_mod, "_request_json", request_json)
        yield {"http": http, "alice": GatewayClient(GatewayClientConfig(base_url="http://testserver", auth_token=alice_token))}


@pytest.mark.basic
def test_a_shared_bundle_listed_for_the_assistant_runs_with_registry_scope_private(gateway) -> None:
    gw = gateway["alice"]
    raw = gw.executable_bundles(ASSISTANT_INTERFACE)
    row = next(it for it in raw["items"] if it["bundle_id"] == SHARED_ID)
    assert row["owner"] == {"kind": "gateway", "user_id": None}, "the bundle is SHARED (gateway-owned), not alice's"

    options, error = AssistantGatewayService(gw)._catalog_workflows()
    assert error == ""
    option = next(o for o in options if o.bundle_id == SHARED_ID)
    assert option.registry_scope == "private"

    # Exactly what the chat worker sends for a chosen workflow.
    run_id = gw.start_run(
        flow_id=option.flow_id,
        bundle_id=option.bundle_id,
        bundle_version=option.bundle_version,
        registry_scope=option.registry_scope,
        input_data={"prompt": "hello from the Assistant"},
    )
    deadline = time.monotonic() + 30
    status = ""
    while time.monotonic() < deadline:
        run = gw.get_run(run_id)
        status = str(run.get("status") or "")
        if status in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.1)
    assert status == "completed", run
    assert SHARED_ID in str(run.get("workflow_id") or ""), run


@pytest.mark.basic
def test_the_same_shared_bundle_made_unavailable_is_not_listed_and_refused_at_start(gateway) -> None:
    http, gw = gateway["http"], gateway["alice"]
    res = http.put(f"/api/gateway/admin/workflows/{SHARED_ID}/availability", headers=ADMIN, json={"available": False})
    assert res.status_code == 200, res.text
    options, error = AssistantGatewayService(gw)._catalog_workflows()
    assert error == "" and all(o.bundle_id != SHARED_ID for o in options)
    with pytest.raises(GatewayHttpError) as refused:
        gw.start_run(flow_id="agent", bundle_id=SHARED_ID, bundle_version="1.0.0", registry_scope="private", input_data={"prompt": "x"})
    assert refused.value.status == 403
    assert "isn't available to users on this gateway" in str(refused.value)
