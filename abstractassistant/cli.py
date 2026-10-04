#!/usr/bin/env python3
"""CLI entry point for AbstractAssistant.

Packaging invariant:
- `assistant --help` must not import GUI/voice stacks (optional dependencies).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _package_version() -> str:
    from ._version import __version__

    return __version__


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    prog = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "abstractassistant"
    parser = argparse.ArgumentParser(prog=prog, description="AbstractAssistant (agentic tray + CLI)")

    parser.add_argument("--version", action="version", version=f"abstractassistant {_package_version()}")
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
    parser.add_argument(
        "--gateway-handover-file",
        type=str,
        default=None,
        metavar="PATH",
        help="One-time sign-in file written by the gateway console (read, deleted, then the session is remembered)",
    )

    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Run one agentic turn in the terminal")
    run.add_argument("--prompt", type=str, required=True, help="User prompt text")
    run.add_argument(
        "--stream",
        choices=("on", "off"),
        default=None,
        help=(
            "Stream the reply while the model writes it (on) or not (off). Default: the "
            "app's 'Stream replies' switch (on unless switched off in Settings). "
            "Live text goes to stderr; the final answer is printed once on stdout."
        ),
    )

    return parser


def _build_config_from_args(args: argparse.Namespace):
    from .config import Config, resolve_gateway_connection

    gateway_url, gateway_auth_token = resolve_gateway_connection(
        url_override=getattr(args, "gateway_url", None),
        auth_token_override=getattr(args, "gateway_token", None),
        # No token is fine: the sign-in saved in gateway_connection.json (or
        # a --gateway-handover-file) supplies the session. Requiring one here
        # used to throw, and the app path swallowed it and dropped --gateway-url.
        require_auth_token=False,
    )
    gateway_data: Dict[str, Any] = {"url": gateway_url, "auth_token": gateway_auth_token}
    return Config.from_dict({"gateway": gateway_data})


SIGN_IN_HINT = (
    "The gateway needs you to sign in. Either open the Assistant from the gateway console "
    "(it signs you in), connect once in the Assistant's Settings \u2192 Connection (the "
    "sign-in is saved and reused here), or pass --gateway-token <token>."
)


def _is_auth_failure(exc: BaseException) -> bool:
    """A 401 from the gateway, directly or as the catalog's auth message."""
    if int(getattr(exc, "status", 0) or 0) == 401:
        return True
    return "authentication failed" in str(exc).lower()


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


def _stream_choice(flag: Optional[str], scope: Dict[str, Any]) -> bool:
    """`--stream on|off` wins; else the app's "Stream replies" switch (on by default)."""
    if flag == "on":
        return True
    if flag == "off":
        return False
    if flag is not None:
        raise ValueError(f"--stream must be on or off, not {flag!r}")
    value = scope.get("stream")
    return value is not False


def _gated_stream(choice: bool, *, advertised: Optional[bool], explicit: bool) -> bool:
    """`_runtime.stream` is always sent (R11.4): `true` only to a gateway that
    advertises live replies (an older runtime would stream internally with no
    live events and can lose usage accounting), `false` otherwise. A withheld
    "on" says so on stderr, whether it came from `--stream on` or the switch.
    """
    if choice is not True or advertised is True:
        return bool(choice)
    why = "does not offer live replies" if advertised is False else "could not be asked whether it offers live replies"
    source = "--stream on" if explicit else "Stream replies"
    sys.stderr.write(f"[{source} not sent: this gateway {why}; the answer is printed when it is finished]\n")
    return False


class LiveDeltaPrinter:
    """Write a streamed reply's text to ``out`` as it arrives.

    Only the content channel is printed (reasoning is never mixed into the
    reply). A reconnect snapshot re-sends the text so far: only the part not
    yet printed is written; when the snapshot no longer extends what was
    printed (the gateway trimmed the oldest text), the line restarts with the
    snapshot and says so. A call that fails or is cancelled says so, and a
    call that could not stream says why in one line. Deltas for a call whose
    durable record already arrived, or any after the final answer, are
    ignored (contract S-2.2).
    """

    def __init__(self, out) -> None:
        from .gateway.live_deltas import LiveReply

        self._out = out
        self._new_reply = LiveReply
        self._replies: Dict[str, Any] = {}
        self._printed: Dict[str, str] = {}
        self._finished: set = set()
        self.final_seen = False

    def note_record(self, rec: Dict[str, Any]) -> None:
        """Remember llm_call steps whose durable record arrived."""
        effect = rec.get("effect") if isinstance(rec.get("effect"), dict) else {}
        if str(effect.get("type") or "").strip().lower() != "llm_call":
            return
        status = str(rec.get("status") or "").strip().lower()
        if status in {"completed", "failed", "cancelled"}:
            self._finished.add(str(rec.get("step_id") or ""))

    def _write(self, text: str) -> None:
        self._out.write(text)
        self._out.flush()

    def __call__(self, ev: Dict[str, Any]) -> None:
        from .gateway.live_deltas import (
            ASSISTANT_DELTA,
            ASSISTANT_DELTA_END,
            ASSISTANT_DELTA_RESET,
            end_reason_text,
        )

        call_id = str(ev.get("call_id") or "")
        typ = ev.get("type")
        if typ == ASSISTANT_DELTA_RESET:
            # Reconnected: the gateway re-sends snapshots. What was already
            # printed stays printed; only text beyond it is written.
            self._replies.clear()
            return
        if typ == ASSISTANT_DELTA:
            if self.final_seen or call_id in self._finished:
                return
            reply = self._replies.get(call_id)
            if reply is None:
                reply = self._new_reply(run_id=str(ev.get("run_id") or ""), call_id=call_id)
                self._replies[call_id] = reply
            reply.apply_delta(ev)
            printed = self._printed.get(call_id, "")
            text = reply.content
            if text == printed:
                return
            if text.startswith(printed):
                self._write(text[len(printed):])
            else:
                self._write("\n[live text trimmed by the gateway; showing the latest part]\n" + text)
            self._printed[call_id] = text
            return
        if typ == ASSISTANT_DELTA_END:
            reason = str(ev.get("reason") or "")
            printed = self._printed.pop(call_id, None)
            self._replies.pop(call_id, None)
            if reason == "unavailable":
                if printed is not None:
                    self._write("\n")
                self._write(f"[{end_reason_text(reason, str(ev.get('detail') or ''))}]\n")
                return
            if printed is None:
                return  # a call that never streamed text: nothing on screen
            self._write("\n")
            if reason == "cancelled" and str(ev.get("detail") or "") == "reinvoked":
                self._write("[reply restarted]\n")
            elif reason != "completed":
                self._write(f"[live reply discarded: {reason}]\n")


def _run_gateway_command(args: argparse.Namespace) -> int:
    from .gateway import GatewayEventAdapter, build_run_input_data
    from .gateway.history_seed import seed_messages_from_history_bundle
    from .gateway.run_controller import GatewayRunController
    from .controller import AssistantController

    config = _build_config_from_args(args)
    launch_url = str(getattr(getattr(config, "gateway", None), "url", "") or "")
    controller = AssistantController(config=config, debug=False, data_dir=None)
    handover_file = str(getattr(args, "gateway_handover_file", None) or "").strip()
    if handover_file:
        controller.redeem_desktop_handover_file(handover_file, fallback_base_url=launch_url)
    gateway = controller.gateway
    llm_manager = controller.llm_manager
    selected_workflow = controller.current_workflow()
    if selected_workflow is None:
        detail = controller.workflow_status().error or "Gateway exposes no runnable workflows for the assistant"
        raise RuntimeError(detail)

    llm_manager.append_message(role="user", content=args.prompt)
    # The terminal turn honors the same local, persistent overrides as the
    # tray: chat model pin, media pins, reasoning effort and workspace grant.
    def _call(name: str, *call_args, default=None):
        fn = getattr(controller, name, None)
        if not callable(fn):
            return default
        try:
            return fn(*call_args)
        except Exception:
            return default

    text_override = dict(_call("route_override", "output.text", default=None) or {})
    scope = dict(_call("run_scope", default=None) or {})
    input_data = build_run_input_data(
        prompt=args.prompt,
        allowed_tools=controller.allowed_tools_for_run(),
        tool_policy=controller.tool_policy_for_run(),
        primary_image_artifact=controller.latest_image_artifact(),
        provider=str(text_override.get("provider") or ""),
        model=str(text_override.get("model") or ""),
        base_url=str(text_override.get("base_url") or ""),
        media_overrides=_call("media_route_overrides", default=None) or None,
        thinking=str(scope.get("thinking") or ""),
        speculation=scope.get("speculation"),
        stream=_gated_stream(
            _stream_choice(getattr(args, "stream", None), scope),
            advertised=_call("live_replies_advertised", default=None),
            explicit=getattr(args, "stream", None) is not None,
        ),
        workspace_root=str(scope.get("workspace_root") or ""),
    )

    if getattr(selected_workflow, "is_gateway_default", False):
        # The gateway resolves its own default for the assistant interface.
        run_id = gateway.start_run(
            flow_id=selected_workflow.flow_id,
            input_data=input_data,
            interface=selected_workflow.interface,
            session_id=llm_manager.active_session_id,
        )
    else:
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
    live_printer = LiveDeltaPrinter(sys.stderr)
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
        live_printer.note_record(rec)  # type: ignore[arg-type]
        for ev in adapter.handle_record(rec):
            if not isinstance(ev, dict):
                continue
            typ = str(ev.get("type") or "").strip()
            if typ == "assistant":
                content = str(ev.get("content") or "")
                if content.strip() and ev.get("final"):
                    final = content
                    live_printer.final_seen = True
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
        on_delta=live_printer,
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
            artifact_loader=lambda rid, aid: gateway.download_run_artifact_content(run_id=rid, artifact_id=aid),
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
            try:
                return _run_gateway_command(args)
            except Exception as exc:
                if _is_auth_failure(exc):
                    print(SIGN_IN_HINT)
                    return 2
                raise

        # app (default — tray UI)
        config = _build_config_from_args(args)

        try:
            from . import launch_tray_app
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
            gateway_handover_file=str(getattr(args, "gateway_handover_file", None) or ""),
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
