"""Which gateway the Assistant connects to (the rule in abstractassistant.config).

1. `--gateway-url` (or its env alias); 2. the saved sign-in; 3. the gateway's own
`local_gateway()` rule, or without it the local gateway pointer file
`~/.abstractframework/gateway.json` (root backlog 0943); 4. http://127.0.0.1:8080. Tier 3
is consulted only when tiers 1 and 2 do not apply.

The pointer cases run the shared 0943 case table `fixtures/gateway_pointer/cases.json`, a
byte-identical copy of abstractuic's `ui-kit/scripts/fixtures/gateway_pointer/` (pinned by
`CHECKSUMS.sha256`), under a scratch HOME.

The tier 3-4 cases run a fresh interpreter whose `abstractgateway` is a stub package
written for the case (it shadows any real gateway installed in the test environment), so
they run in the Assistant's own CI, where abstractgateway is not installed. The tier 1-2
cases drive the controller's resolution with `default_gateway_url` replaced.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Dict, Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
POINTERS = Path(__file__).parent / "fixtures" / "gateway_pointer"

_PROBE = textwrap.dedent(
    """
    import json, sys
    if sys.argv[1] == "absent":
        sys.modules["abstractgateway"] = None  # an interpreter without abstractgateway
    from abstractassistant import config
    out = {
        "launch": list(config.resolve_gateway_connection()),
        "flag": list(config.resolve_gateway_connection(url_override="http://10.0.0.5:9000/")),
    }
    if sys.argv[2] == "default":
        out["default"] = config.default_gateway_url()
    print(json.dumps(out))
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
    tmp_path: Path,
    stub_root: Optional[Path],
    *,
    mode: str = "stub",
    ask_default: bool = True,
    env_url: str = "",
    pointer: str = "",
    probe: str = _PROBE,
) -> subprocess.CompletedProcess:
    env: Dict[str, str] = {
        k: v
        for k, v in os.environ.items()
        if k not in {"ABSTRACTGATEWAY_URL", "ABSTRACTFLOW_GATEWAY_URL", "PYTHONPATH"}
    }
    env["HOME"] = str(tmp_path / "home")
    env["USERPROFILE"] = env["HOME"]
    if pointer:
        _write_pointer(tmp_path / "home", pointer)
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in (stub_root, ROOT) if p is not None)
    if env_url:
        env["ABSTRACTGATEWAY_URL"] = env_url
    return subprocess.run(
        [sys.executable, "-c", probe, mode, "default" if ask_default else "no-default"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=60,
    )


def _write_pointer(home: Path, fixture: str) -> Path:
    target = home / ".abstractframework" / "gateway.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((POINTERS / fixture).read_bytes())
    target.chmod(0o600)
    return target


def _result(proc: subprocess.CompletedProcess) -> Dict[str, object]:
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


_GATEWAY_WITH_RULE = """
    def local_gateway(data_dir=None):
        return {"url": "http://127.0.0.1:18081/", "source": "serve_record", "serve": None}
"""

_GATEWAY_WITH_FAILING_RULE = """
    def local_gateway(data_dir=None):
        raise PermissionError("gateway data dir unreadable (test)")
"""


# --- tiers 3-4: default_gateway_url() -------------------------------------------------


@pytest.mark.basic
def test_the_gateways_local_rule_is_the_default(tmp_path: Path) -> None:
    out = _result(_probe(tmp_path, _stub_gateway(tmp_path, _GATEWAY_WITH_RULE)))
    assert out["default"] == "http://127.0.0.1:18081"
    assert out["launch"] == ["", ""]  # no flag, no env: the launch names no URL
    assert out["flag"] == ["http://10.0.0.5:9000", ""]


@pytest.mark.basic
def test_the_legacy_env_alias_is_a_launch_url(tmp_path: Path) -> None:
    stub = _stub_gateway(tmp_path, _GATEWAY_WITH_RULE)
    out = _result(_probe(tmp_path, stub, env_url="http://10.0.0.7:8000/"))
    assert out["launch"] == ["http://10.0.0.7:8000", ""]


@pytest.mark.basic
def test_without_abstractgateway_the_default_is_the_builtin_url(tmp_path: Path) -> None:
    out = _result(_probe(tmp_path, None, mode="absent"))
    assert out["default"] == "http://127.0.0.1:8080"


@pytest.mark.basic
def test_a_gateway_older_than_the_rule_gives_the_builtin_url(tmp_path: Path) -> None:
    # abstractgateway 0.5.1: first_run exists, local_gateway does not.
    stub = _stub_gateway(tmp_path, "def first_run_state(data_dir):\n    return {}\n")
    out = _result(_probe(tmp_path, stub))
    assert out["default"] == "http://127.0.0.1:8080"


@pytest.mark.basic
def test_a_broken_gateway_install_fails_loudly_when_the_rule_is_needed(tmp_path: Path) -> None:
    stub = _stub_gateway(tmp_path, "import abstractgateway_missing_dependency_for_test\n")
    proc = _probe(tmp_path, stub)
    assert proc.returncode != 0
    assert "abstractgateway_missing_dependency_for_test" in proc.stderr


@pytest.mark.basic
def test_an_error_inside_the_gateways_rule_fails_loudly_when_the_rule_is_needed(tmp_path: Path) -> None:
    proc = _probe(tmp_path, _stub_gateway(tmp_path, _GATEWAY_WITH_FAILING_RULE))
    assert proc.returncode != 0
    assert "gateway data dir unreadable (test)" in proc.stderr


@pytest.mark.basic
def test_importing_config_never_consults_the_gateway(tmp_path: Path) -> None:
    """A failing rule cannot block a launch that names its gateway: nothing at import
    (or in resolving the launch's flag) touches the gateway package."""
    for source in (_GATEWAY_WITH_FAILING_RULE, "import abstractgateway_missing_dependency_for_test\n"):
        case = tmp_path / str(abs(hash(source)))
        case.mkdir()
        out = _result(_probe(case, _stub_gateway(case, source), ask_default=False))
        assert out["flag"] == ["http://10.0.0.5:9000", ""]


# --- tier 3 without the gateway: the local gateway pointer file (0943) --------------


POINTER_FILES = ("cases.json", "malformed.json", "non_loopback.json", "valid.json", "wrong_schema.json")
POINTER_CASES = json.loads((POINTERS / "cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.basic
def test_the_pointer_fixtures_are_the_shared_set() -> None:
    """Byte-identical to abstractuic's canonical set: every file listed, every hash equal."""
    listed = dict(reversed(line.split(None, 1)) for line in (POINTERS / "CHECKSUMS.sha256").read_text().splitlines() if line.strip())
    assert set(listed) == set(POINTER_FILES) == {p.name for p in POINTERS.glob("*.json")}
    for name in POINTER_FILES:
        assert hashlib.sha256((POINTERS / name).read_bytes()).hexdigest() == listed[name], f"{name} drifted"
    assert {c["name"] for c in POINTER_CASES} == {"valid", "non_loopback", "wrong_schema", "malformed", "missing"}


@pytest.mark.basic
@pytest.mark.parametrize("case", POINTER_CASES, ids=[c["name"] for c in POINTER_CASES])
def test_the_shared_pointer_cases_without_abstractgateway(tmp_path: Path, case) -> None:
    """The frozen .app's case (runs in CI, where abstractgateway is not installed): no flag,
    env or saved sign-in; the URL and whether ONE warning is shown come from the shared table."""
    if case["file"] is not None:
        assert (POINTERS / case["file"]).is_file()  # a deleted fixture fails here, not silently
    proc = _probe(tmp_path, None, mode="absent", pointer=case["file"] or "")
    assert _result(proc)["default"] == case["expect"]
    assert proc.stderr.count("Ignoring the local gateway pointer") == (1 if case["warn"] else 0), proc.stderr
    if not case["warn"]:
        assert proc.stderr.strip() == ""


@pytest.mark.basic
def test_a_gateway_older_than_the_rule_reads_the_pointer_file(tmp_path: Path) -> None:
    stub = _stub_gateway(tmp_path, "def first_run_state(data_dir):\n    return {}\n")
    assert _result(_probe(tmp_path, stub, pointer="valid.json"))["default"] == "http://127.0.0.1:8081"


@pytest.mark.basic
def test_the_gateways_rule_stays_authoritative_over_the_pointer_file(tmp_path: Path) -> None:
    # Python clients keep local_gateway(); the pointer is read only without it.
    _write_pointer(tmp_path / "home", "valid.json").write_text(
        json.dumps({"schema": 1, "url": "http://127.0.0.1:19999"}), encoding="utf-8"
    )
    out = _result(_probe(tmp_path, _stub_gateway(tmp_path, _GATEWAY_WITH_RULE)))
    assert out["default"] == "http://127.0.0.1:18081"


@pytest.mark.basic
@pytest.mark.parametrize(
    "document, expected",
    [
        ({"schema": 1, "url": "http://127.0.0.1:18081/"}, "http://127.0.0.1:18081"),
        ({"schema": 1, "url": "http://localhost:18082"}, "http://localhost:18082"),
        ({"schema": 1, "url": "http://[::1]:18083"}, "http://[::1]:18083"),
        ({"schema": True, "url": "http://127.0.0.1:18081"}, ""),  # bool is not schema 1
        ({"schema": 1, "url": "http://127.0.0.1.evil.example:80"}, ""),
        ({"schema": 1, "url": "http://user@10.0.0.5:8080"}, ""),
        ({"schema": 1, "url": "file:///127.0.0.1"}, ""),
        ({"schema": 1, "url": "http://127.0.0.1:notaport"}, ""),
        ({"schema": 1, "url": "HTTP://LOCALHOST:18084"}, "http://localhost:18084"),
        ({"schema": 1, "url": "https://127.0.0.1:443"}, "https://127.0.0.1"),
        ({"schema": 1, "url": "http://127.0.0.1:18081/api"}, ""),  # nothing after the port
        ({"schema": 1, "url": "http://127.0.0.1:18081/?x=1"}, ""),
        ({"schema": 1, "url": "http://127.0.0.1:18081#frag"}, ""),
        ({"schema": 1, "url": "http://u:p@127.0.0.1:18081"}, ""),  # no user info
        ({"schema": 1, "url": "http://u@127.0.0.1:18081"}, ""),
        ({"schema": 1}, ""),
        ([1, 2], ""),
    ],
)
def test_the_pointer_reader_accepts_only_a_loopback_url(tmp_path: Path, document, expected) -> None:
    from abstractassistant.config import read_gateway_pointer

    path = tmp_path / "gateway.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert read_gateway_pointer(path) == expected


@pytest.mark.basic
@pytest.mark.skipif(not hasattr(os, "getuid"), reason="file ownership is a POSIX rule")
def test_a_pointer_file_owned_by_another_user_is_refused(tmp_path: Path, monkeypatch, caplog) -> None:
    from abstractassistant import config

    path = _write_pointer(tmp_path, "valid.json")
    assert config.read_gateway_pointer(path) == "http://127.0.0.1:8081"
    monkeypatch.setattr(config.os, "getuid", lambda: path.stat().st_uid + 1)
    with caplog.at_level("WARNING", logger="abstractassistant.config"):
        assert config.read_gateway_pointer(path) == ""
    assert "not by this user" in caplog.text


@pytest.mark.basic
@pytest.mark.skipif(not hasattr(os, "getuid"), reason="file modes are a POSIX rule")
@pytest.mark.parametrize("mode", [0o664, 0o646, 0o666])
def test_a_pointer_file_others_can_write_is_refused(tmp_path: Path, caplog, mode: int) -> None:
    """The kit reader's rule (app-server gateway_pointer.js): no group/world write bit."""
    from abstractassistant import config

    path = _write_pointer(tmp_path, "valid.json")
    path.chmod(0o644)
    assert config.read_gateway_pointer(path) == "http://127.0.0.1:8081"
    path.chmod(mode)
    with caplog.at_level("WARNING", logger="abstractassistant.config"):
        assert config.read_gateway_pointer(path) == ""
    assert "other users can write it" in caplog.text


@pytest.mark.basic
def test_a_symlinked_pointer_file_is_refused(tmp_path: Path, caplog) -> None:
    from abstractassistant import config

    real = _write_pointer(tmp_path / "elsewhere", "valid.json")
    link = tmp_path / "gateway.json"
    link.symlink_to(real)
    assert config.read_gateway_pointer(real) == "http://127.0.0.1:8081"
    with caplog.at_level("WARNING", logger="abstractassistant.config"):
        assert config.read_gateway_pointer(link) == ""
    assert "not a regular file" in caplog.text


@pytest.mark.basic
def test_a_directory_at_the_pointer_path_is_refused(tmp_path: Path, caplog) -> None:
    from abstractassistant import config

    (tmp_path / "gateway.json").mkdir()
    with caplog.at_level("WARNING", logger="abstractassistant.config"):
        assert config.read_gateway_pointer(tmp_path / "gateway.json") == ""
    assert caplog.text.count("Ignoring the local gateway pointer") == 1


@pytest.mark.basic
def test_a_fifo_at_the_pointer_path_is_refused_without_blocking(tmp_path: Path, caplog) -> None:
    from abstractassistant import config

    fifo = tmp_path / "gateway.json"
    os.mkfifo(fifo, 0o600)
    # No writer ever opens it: a blocking open would hang the launch here.
    with caplog.at_level("WARNING", logger="abstractassistant.config"):
        assert config.read_gateway_pointer(fifo) == ""
    assert "not a regular file" in caplog.text


@pytest.mark.basic
def test_an_oversized_pointer_file_is_refused(tmp_path: Path, caplog) -> None:
    from abstractassistant import config

    big = tmp_path / "gateway.json"
    big.write_text(json.dumps({"schema": 1, "url": "http://127.0.0.1:8081", "pad": "x" * config.GATEWAY_POINTER_MAX_BYTES}))
    big.chmod(0o600)
    with caplog.at_level("WARNING", logger="abstractassistant.config"):
        assert config.read_gateway_pointer(big) == ""
    assert "larger than" in caplog.text


@pytest.mark.basic
def test_deeply_nested_json_is_refused_not_raised(tmp_path: Path, caplog) -> None:
    from abstractassistant import config

    deep = tmp_path / "gateway.json"
    deep.write_text("[" * 50_000)
    deep.chmod(0o600)
    with caplog.at_level("WARNING", logger="abstractassistant.config"):
        assert config.read_gateway_pointer(deep) == ""
    assert "not JSON" in caplog.text


@pytest.mark.basic
def test_the_pointer_path_is_under_the_users_home(tmp_path: Path, monkeypatch) -> None:
    from abstractassistant.config import gateway_pointer_path

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert gateway_pointer_path() == tmp_path / ".abstractframework" / "gateway.json"


_CONTROLLER_PROBE = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    sys.modules["abstractgateway"] = None  # the frozen .app: no gateway in this Python
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.preferences import GatewayConnectionPreferences, GatewayConnectionStore
    controller = object.__new__(AssistantController)
    controller.connection_store = GatewayConnectionStore(Path.home() / "gateway_connection.json")
    if sys.argv[1] != "none":
        controller.connection_store.save(GatewayConnectionPreferences(
            base_url=sys.argv[1], auth_mode="session", session_id="s1", user_id="me"))
    controller.config = Config.from_dict({"gateway": {"url": ""}})
    resolved = AssistantController._load_connection_preferences(controller)
    print(json.dumps({"url": resolved.base_url, "session": resolved.session_id}))
    """
)


@pytest.mark.basic
@pytest.mark.parametrize(
    "saved, expected",
    [
        ("none", "http://127.0.0.1:8081"),  # first launch: the pointer fills the sign-in field
        ("http://127.0.0.1:8080", "http://127.0.0.1:8081"),  # the old default is re-pointed
        ("https://saved.gateway.example", "https://saved.gateway.example"),  # a chosen URL is kept
    ],
)
def test_the_frozen_app_follows_the_pointer_file(tmp_path: Path, saved: str, expected: str) -> None:
    """End to end in a fresh interpreter without abstractgateway (CI-runnable)."""
    proc = _probe(tmp_path, None, mode=saved, pointer="valid.json", probe=_CONTROLLER_PROBE)
    out = _result(proc)
    assert out["url"] == expected
    assert out["session"] == ("" if saved == "none" else "s1")


# --- tiers 1-2: the controller --------------------------------------------------------


def _controller(tmp_path: Path, monkeypatch, *, launch_url: str, saved=None, rule=None):
    from abstractassistant import controller as controller_mod
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.preferences import GatewayConnectionStore

    calls = []

    def fake_rule() -> str:
        calls.append(1)
        if rule is None:
            raise AssertionError("the gateway rule was consulted although a higher tier applies")
        return rule

    monkeypatch.setattr(controller_mod, "default_gateway_url", fake_rule)
    monkeypatch.delenv("ABSTRACTGATEWAY_URL", raising=False)
    monkeypatch.delenv("ABSTRACTFLOW_GATEWAY_URL", raising=False)
    controller = object.__new__(AssistantController)
    controller.connection_store = GatewayConnectionStore(tmp_path / "gateway_connection.json")
    if saved is not None:
        controller.connection_store.save(saved)
    controller.config = Config.from_dict({"gateway": {"url": launch_url}})
    return AssistantController._load_connection_preferences(controller), calls


def _saved(url: str):
    from abstractassistant.preferences import GatewayConnectionPreferences

    return GatewayConnectionPreferences(base_url=url, auth_mode="session", session_id="s1", user_id="me")


@pytest.mark.basic
def test_a_flag_equal_to_the_discovered_url_beats_a_different_saved_sign_in(tmp_path, monkeypatch) -> None:
    resolved, calls = _controller(
        tmp_path,
        monkeypatch,
        launch_url="http://127.0.0.1:18081",
        saved=_saved("https://saved.gateway.example"),
        rule="http://127.0.0.1:18081",
    )
    assert resolved.base_url == "http://127.0.0.1:18081"
    assert calls == []


@pytest.mark.basic
def test_a_flag_never_consults_the_gateway_rule(tmp_path, monkeypatch) -> None:
    resolved, _ = _controller(tmp_path, monkeypatch, launch_url="http://10.0.0.5:9000")
    assert resolved.base_url == "http://10.0.0.5:9000"


@pytest.mark.basic
def test_a_saved_sign_in_wins_over_the_rule_without_consulting_it(tmp_path, monkeypatch) -> None:
    resolved, _ = _controller(tmp_path, monkeypatch, launch_url="", saved=_saved("https://saved.gateway.example"))
    assert resolved.base_url == "https://saved.gateway.example"
    assert resolved.session_id == "s1"


@pytest.mark.basic
def test_neither_flag_nor_sign_in_uses_the_rule(tmp_path, monkeypatch) -> None:
    resolved, calls = _controller(tmp_path, monkeypatch, launch_url="", rule="http://127.0.0.1:18081")
    assert resolved.base_url == "http://127.0.0.1:18081"
    assert calls == [1]


@pytest.mark.basic
def test_a_sign_in_saved_against_the_builtin_url_follows_the_moved_gateway(tmp_path, monkeypatch) -> None:
    resolved, _ = _controller(
        tmp_path, monkeypatch, launch_url="", saved=_saved("http://127.0.0.1:8080"), rule="http://127.0.0.1:18081"
    )
    assert resolved.base_url == "http://127.0.0.1:18081"
    assert resolved.session_id == "s1"
