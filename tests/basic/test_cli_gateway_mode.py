"""CLI gateway-mode contract tests."""

from __future__ import annotations

import sys
import types

import pytest

from abstractassistant import cli
from abstractassistant.cli import create_parser


@pytest.mark.basic
def test_run_parser_allows_gateway_defaults_without_extra_run_flags() -> None:
    args = create_parser().parse_args(["run", "--prompt", "Hello"])

    assert args.command == "run"
    assert args.prompt == "Hello"
    assert args.gateway_url is None
    assert args.gateway_token is None


@pytest.mark.basic
def test_run_parser_accepts_gateway_override_flags() -> None:
    args = create_parser().parse_args(
        [
            "--gateway-url",
            "http://127.0.0.1:9090",
            "--gateway-token",
            "secret-token",
            "run",
            "--prompt",
            "Hello",
        ]
    )

    assert args.gateway_url == "http://127.0.0.1:9090"
    assert args.gateway_token == "secret-token"


@pytest.mark.basic
def test_cli_default_app_launches_v2_tray_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}
    fake_module = types.ModuleType("abstractassistantv2")

    def _launch_tray_app(**kwargs):
        called.update(kwargs)
        return 41

    fake_module.launch_tray_app = _launch_tray_app  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "abstractassistantv2", fake_module)
    monkeypatch.setattr(sys, "argv", ["assistant"])

    result = cli.main()

    assert result == 41
    assert called["debug"] is False
    assert called["data_dir"] is None


@pytest.mark.basic
def test_run_command_uses_catalog_workflow_without_client_prompt_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Gateway:
        def __init__(self) -> None:
            self.start_run_calls: list[dict] = []

        def session_prompt_cache_prepare(self, **kwargs) -> dict:
            raise AssertionError("assistant CLI must not negotiate prompt cache from the desktop client")

        def start_run(self, **kwargs) -> str:
            self.start_run_calls.append(dict(kwargs))
            return "run-1"

        def get_run_history_bundle(self, **kwargs) -> dict:
            raise RuntimeError("history unavailable in unit test")

    class _LLMManager:
        def __init__(self, gateway: _Gateway) -> None:
            self._gateway = gateway
            self.active_session_id = "session-1"
            self.messages: list[dict] = []
            self.last_run_id = ""

        def append_message(self, *, role: str, content: str) -> None:
            self.messages.append({"role": role, "content": content})

        def session_messages(self) -> list[dict]:
            return list(self.messages)

        def set_last_run_id(self, run_id: str) -> None:
            self.last_run_id = run_id

    gateway = _Gateway()

    class _Workflow:
        bundle_id = "abstractassistant-orchestrator"
        flow_id = "chat"
        bundle_version = "2026.06.12"
        registry_scope = "tenant_catalog"

    class _Controller:
        def __init__(self, **kwargs) -> None:
            self.gateway = gateway
            self.llm_manager = _LLMManager(gateway)

        def current_workflow(self):
            return _Workflow()

        def workflow_status(self):
            return type("_Status", (), {"error": ""})()

        def chat_defaults(self):
            return ("endpoint:ovh-provider", "gpt-oss-20b")

        def allowed_tools_for_run(self):
            return ["web_search"]

        def tool_policy_for_run(self):
            return {"auto_approve_tools": ["web_search"]}

        def latest_image_artifact(self):
            return None

    class _RunController:
        def __init__(self, gateway, debug: bool = False) -> None:
            self._gateway = gateway

        def follow_run(self, *, root_run_id, on_record, should_stop) -> None:
            return None

        def get_run_status(self, *, run_id: str) -> str:
            return "completed"

    run_controller_module = __import__("abstractassistant.gateway.run_controller", fromlist=["GatewayRunController"])
    monkeypatch.setattr(run_controller_module, "GatewayRunController", _RunController)
    monkeypatch.setattr(cli, "_build_config_from_args", lambda args: object())
    monkeypatch.setattr(
        cli,
        "_import_v2_module",
        lambda name: types.SimpleNamespace(AssistantV2Controller=_Controller),
    )

    args = create_parser().parse_args(["run", "--prompt", "search internet for today news"])
    result = cli._run_gateway_command(args)

    assert result == 0
    assert gateway.start_run_calls == [
        {
            "flow_id": "chat",
            "input_data": {
                "prompt": "search internet for today news",
                "context": {
                    "task": "search internet for today news",
                    "messages": [{"role": "user", "content": "search internet for today news"}],
                },
                "use_context": True,
                    "_runtime": {
                        "provider": "endpoint:ovh-provider",
                        "model": "gpt-oss-20b",
                        "allowed_tools": ["web_search"],
                        "tool_policy": {
                            "auto_approve_tools": ["web_search"],
                            "require_approval_tools": [],
                        },
                    },
                    "max_iterations": 50,
                    "has_primary_image_context": False,
                    "provider": "endpoint:ovh-provider",
                    "model": "gpt-oss-20b",
                    "tools": ["web_search"],
                },
                "bundle_id": "abstractassistant-orchestrator",
            "bundle_version": "2026.06.12",
            "session_id": "session-1",
            "registry_scope": "tenant_catalog",
        }
    ]
