#!/usr/bin/env python3
"""CLI entry point for AbstractAssistant.

Packaging invariant:
- `assistant --help` must not import GUI/voice stacks (optional dependencies).
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    prog = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "abstractassistant"
    parser = argparse.ArgumentParser(prog=prog, description="AbstractAssistant (agentic tray + CLI)")
    
    parser.add_argument("--version", action="version", version="abstractassistant (agentic) v1")
    parser.add_argument(
        "--gateway-url",
        type=str,
        default=None,
        help="Optional AbstractGateway base URL override",
    )
    parser.add_argument(
        "--gateway-token",
        type=str,
        default=None,
        help="Optional AbstractGateway bearer token override",
    )

    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Run one agentic turn in the terminal")
    run.add_argument("--prompt", type=str, required=True, help="User prompt text")
    
    return parser


def _build_config_from_args(args: argparse.Namespace):
    from .config import Config, resolve_gateway_connection

    gateway_url, gateway_auth_token = resolve_gateway_connection(
        url_override=getattr(args, "gateway_url", None),
        auth_token_override=getattr(args, "gateway_token", None),
        require_auth_token=True,
    )
    gateway_data: Dict[str, Any] = {"url": gateway_url, "auth_token": gateway_auth_token}
    return Config.from_dict({"gateway": gateway_data})


def _format_tool_arguments(arguments: Any) -> str:
    return str(arguments if arguments is not None else "")


def _approve_tool_batch(tool_calls: List[Dict[str, Any]]) -> bool:
    print("\nTool approval required:")
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        name = str(tc.get("name") or "").strip() or "<unknown>"
        arguments = _format_tool_arguments(tc.get("arguments"))
        print(f"- {name}({arguments})")
    ans = input("Approve this batch? [y/N] ").strip().lower()
    return ans in {"y", "yes"}


def _import_v2_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name not in {"abstractassistantv2", name}:
            raise
        repo_root = Path(__file__).resolve().parent.parent
        repo_root_s = str(repo_root)
        if repo_root_s not in sys.path:
            sys.path.insert(0, repo_root_s)
        return importlib.import_module(name)


def _run_gateway_command(args: argparse.Namespace) -> int:
    from .gateway import GatewayEventAdapter, build_run_input_data
    from .gateway.history_seed import seed_messages_from_history_bundle
    from .gateway.run_controller import GatewayRunController
    AssistantV2Controller = _import_v2_module("abstractassistantv2.controller").AssistantV2Controller

    config = _build_config_from_args(args)
    controller = AssistantV2Controller(config=config, debug=False, data_dir=None)
    gateway = controller.gateway
    llm_manager = controller.llm_manager
    selected_workflow = controller.current_workflow()
    if selected_workflow is None:
        detail = controller.workflow_status().error or "Gateway exposes no runnable workflows for the assistant"
        raise RuntimeError(detail)

    llm_manager.append_message(role="user", content=args.prompt)
    provider, model = controller.chat_defaults()
    input_data = build_run_input_data(
        prompt=args.prompt,
        provider=provider,
        model=model,
        messages=llm_manager.session_messages(),
        allowed_tools=controller.allowed_tools_for_run(),
        tool_policy=controller.tool_policy_for_run(),
        primary_image_artifact=controller.latest_image_artifact(),
    )

    run_id = gateway.start_run(
        flow_id=selected_workflow.flow_id,
        input_data=input_data,
        bundle_id=selected_workflow.bundle_id,
        bundle_version=selected_workflow.bundle_version or None,
        session_id=llm_manager.active_session_id,
        registry_scope=selected_workflow.registry_scope or None,
    )
    llm_manager.set_last_run_id(run_id)

    adapter = GatewayEventAdapter()
    controller = GatewayRunController(gateway=gateway, debug=False)
    final = ""

    def _submit_resume(*, active_run_id: str, wait_key: str, payload: Dict[str, Any]) -> None:
        gateway.submit_command(
            command={
                "command_id": f"resume_{int(time.time() * 1000)}",
                "run_id": str(active_run_id),
                "type": "resume",
                "payload": {"wait_key": wait_key, "payload": payload},
                "client_id": "abstractassistant-cli",
            }
        )

    def _on_record(active_run_id: str, rec: Dict[str, object]) -> None:
        nonlocal final
        for ev in adapter.handle_record(rec):
            if not isinstance(ev, dict):
                continue
            typ = str(ev.get("type") or "").strip()
            if typ == "assistant":
                content = str(ev.get("content") or "")
                if content.strip() and ev.get("final"):
                    final = content
                continue
            if typ == "tool_request":
                wait_key = str(ev.get("wait_key") or "").strip()
                if not wait_key:
                    continue
                tool_calls = ev.get("tool_calls")
                approved = _approve_tool_batch(tool_calls if isinstance(tool_calls, list) else [])
                payload: Dict[str, Any] = {"approved": approved}
                if not approved:
                    payload["reason"] = "Denied by user"
                _submit_resume(active_run_id=active_run_id, wait_key=wait_key, payload=payload)
                continue
            if typ == "ask_user":
                wait_key = str(ev.get("wait_key") or "").strip()
                if not wait_key:
                    continue
                prompt = str(ev.get("prompt") or "Input required:").strip() or "Input required:"
                response = input(f"\n{prompt}\n> ").strip()
                _submit_resume(active_run_id=active_run_id, wait_key=wait_key, payload={"response": response})
                continue
            if typ == "error":
                raise RuntimeError(str(ev.get("error") or "Gateway run failed"))

    controller.follow_run(
        root_run_id=run_id,
        on_record=_on_record,
        should_stop=lambda: False,
    )

    status = str(controller.get_run_status(run_id=run_id) or "").strip().lower()
    if status in {"failed", "cancelled"} and not final:
        raise RuntimeError(f"Gateway run ended with status '{status}'")

    try:
        bundle = gateway.get_run_history_bundle(
            run_id=run_id,
            include_subruns=True,
            include_session=True,
            session_turn_limit=200,
            ledger_mode="tail",
            ledger_max_items=2000,
        )
        messages = seed_messages_from_history_bundle(
            bundle,
            include_tool_calls_for_run_id=run_id,
        )
        if messages:
            llm_manager.replace_gateway_messages(messages, last_run_id=run_id)
            if not final:
                for msg in reversed(messages):
                    if not isinstance(msg, dict):
                        continue
                    if str(msg.get("role") or "") != "assistant":
                        continue
                    content = str(msg.get("content") or "")
                    if content.strip():
                        final = content
                        break
    except Exception:
        pass

    print(final)
    return 0


def main() -> int:
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        command = args.command or "app"

        if command == "run":
            return _run_gateway_command(args)

        # app (default — tray UI)
        try:
            config = _build_config_from_args(args)
        except Exception:
            config = None

        try:
            launch_tray_app = _import_v2_module("abstractassistantv2").launch_tray_app
        except Exception as e:
            print("AbstractAssistant tray mode requires GUI dependencies.")
            print('Install (tray): pip install -U "abstractassistant"')
            print('From source (editable): pip install -e ".[dev]"')
            print(f"Import error: {e}")
            return 2

        return launch_tray_app(
            config=config,
            debug=False,
            data_dir=None,
        )
        
    except KeyboardInterrupt:
        print("\n👋 AbstractAssistant stopped by user")
        return 0
    except ValueError as e:
        print(str(e))
        return 2
    except Exception as e:
        print(f"❌ Error starting AbstractAssistant: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
