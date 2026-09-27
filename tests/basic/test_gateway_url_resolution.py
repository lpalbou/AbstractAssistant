"""Which gateway the Assistant connects to (abstractassistant.config module rule).

`DEFAULT_GATEWAY_URL` is resolved when `abstractassistant.config` is imported, so each
case runs a fresh interpreter whose `abstractgateway` is a stub package written for the
case (it shadows any real gateway installed in the test environment). No real gateway
is needed: these run in the Assistant's own CI, where abstractgateway is not installed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Dict, Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]

_PROBE = textwrap.dedent(
    """
    import json, sys
    if sys.argv[1] == "absent":
        sys.modules["abstractgateway"] = None  # an interpreter without abstractgateway
    from abstractassistant import config
    print(json.dumps({
        "default": config.DEFAULT_GATEWAY_URL,
        "resolved": config.resolve_gateway_connection()[0],
        "flag": config.resolve_gateway_connection(url_override="http://10.0.0.5:9000/")[0],
    }))
    """
)


def _stub_gateway(tmp_path: Path, first_run_source: Optional[str]) -> Path:
    pkg = tmp_path / "stub" / "abstractgateway"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    if first_run_source is not None:
        (pkg / "first_run.py").write_text(textwrap.dedent(first_run_source), encoding="utf-8")
    return pkg.parent


def _probe(
    tmp_path: Path, stub_root: Optional[Path], *, mode: str = "stub", env_url: str = ""
) -> subprocess.CompletedProcess:
    env: Dict[str, str] = {
        k: v
        for k, v in os.environ.items()
        if k not in {"ABSTRACTGATEWAY_URL", "ABSTRACTFLOW_GATEWAY_URL", "PYTHONPATH"}
    }
    env["HOME"] = str(tmp_path / "home")
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in (stub_root, ROOT) if p is not None)
    if env_url:
        env["ABSTRACTGATEWAY_URL"] = env_url
    return subprocess.run(
        [sys.executable, "-c", _PROBE, mode],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=60,
    )


def _urls(proc: subprocess.CompletedProcess) -> Dict[str, str]:
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


_GATEWAY_WITH_RULE = """
    def local_gateway(data_dir=None):
        return {"url": "http://127.0.0.1:18081/", "source": "serve_record", "serve": None}
"""


@pytest.mark.basic
def test_the_gateways_local_rule_is_the_default_and_the_flag_wins(tmp_path: Path) -> None:
    urls = _urls(_probe(tmp_path, _stub_gateway(tmp_path, _GATEWAY_WITH_RULE)))
    assert urls == {
        "default": "http://127.0.0.1:18081",
        "resolved": "http://127.0.0.1:18081",
        "flag": "http://10.0.0.5:9000",
    }


@pytest.mark.basic
def test_the_legacy_env_alias_wins_over_the_gateways_rule(tmp_path: Path) -> None:
    stub = _stub_gateway(tmp_path, _GATEWAY_WITH_RULE)
    urls = _urls(_probe(tmp_path, stub, env_url="http://10.0.0.7:8000"))
    assert urls["default"] == "http://127.0.0.1:18081"
    assert urls["resolved"] == "http://10.0.0.7:8000"


@pytest.mark.basic
def test_without_abstractgateway_the_default_is_the_builtin_url(tmp_path: Path) -> None:
    urls = _urls(_probe(tmp_path, None, mode="absent"))
    assert urls["default"] == urls["resolved"] == "http://127.0.0.1:8080"


@pytest.mark.basic
def test_a_gateway_older_than_the_rule_gives_the_builtin_url(tmp_path: Path) -> None:
    # abstractgateway 0.5.1: first_run exists, local_gateway does not.
    stub = _stub_gateway(tmp_path, "def first_run_state(data_dir):\n    return {}\n")
    urls = _urls(_probe(tmp_path, stub))
    assert urls["default"] == "http://127.0.0.1:8080"


@pytest.mark.basic
def test_a_broken_gateway_install_fails_loudly(tmp_path: Path) -> None:
    stub = _stub_gateway(tmp_path, "import abstractgateway_missing_dependency_for_test\n")
    proc = _probe(tmp_path, stub)
    assert proc.returncode != 0
    assert "abstractgateway_missing_dependency_for_test" in proc.stderr


@pytest.mark.basic
def test_an_error_inside_the_gateways_rule_fails_loudly(tmp_path: Path) -> None:
    stub = _stub_gateway(
        tmp_path,
        """
        def local_gateway(data_dir=None):
            raise PermissionError("gateway data dir unreadable (test)")
        """,
    )
    proc = _probe(tmp_path, stub)
    assert proc.returncode != 0
    assert "gateway data dir unreadable (test)" in proc.stderr


@pytest.mark.basic
def test_a_saved_sign_in_wins_over_the_gateways_rule(tmp_path: Path, monkeypatch) -> None:
    """Tier 2 over tier 3: no flag, a saved connection, a default from the gateway's rule."""
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.preferences import GatewayConnectionPreferences, GatewayConnectionStore

    from abstractassistant import controller as controller_mod

    monkeypatch.setattr(controller_mod, "DEFAULT_GATEWAY_URL", "http://127.0.0.1:18081")
    controller = object.__new__(AssistantController)
    controller.connection_store = GatewayConnectionStore(tmp_path / "gateway_connection.json")
    controller.connection_store.save(
        GatewayConnectionPreferences(
            base_url="https://saved.gateway.example", auth_mode="bearer", auth_token="saved"
        )
    )
    controller.config = Config.from_dict({"gateway": {"url": "http://127.0.0.1:18081"}})

    resolved = AssistantController._load_connection_preferences(controller)

    assert resolved.base_url == "https://saved.gateway.example"
    assert resolved.auth_token == "saved"
