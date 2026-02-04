#!/usr/bin/env python3
"""CLI entry point for AbstractAssistant.

Packaging invariant:
- `assistant --help` must not import GUI/voice stacks (optional dependencies).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(prog="assistant", description="AbstractAssistant (agentic tray + CLI)")
    
    parser.add_argument("--version", action="version", version="abstractassistant (agentic) v1")
    
    parser.add_argument("--config", type=str, default=None, help="Path to config.toml (optional)")
    parser.add_argument("--provider", type=str, default=None, help="LLM provider id (e.g. ollama, lmstudio, openai)")
    parser.add_argument("--model", type=str, default=None, help="Model name/id for the provider")
    parser.add_argument("--agent", type=str, default=None, choices=["react", "codeact", "memact"], help="Agent kind")
    parser.add_argument("--data-dir", type=str, default=None, help="Assistant data dir (runtime stores + session)")
    parser.add_argument("--workspace-root", type=str, default=None, help="Workspace root for filesystem-ish tools")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    sub = parser.add_subparsers(dest="command")
    
    tray = sub.add_parser("tray", help="Run the macOS tray app (requires [lite] extra)")
    tray.add_argument(
        "--listening-mode",
        type=str,
        choices=["none", "stop", "wait", "full", "ptt"],
        default="wait",
        help="Voice listening mode (requires [full] extra for STT/TTS)",
    )

    run = sub.add_parser("run", help="Run one agentic turn in the terminal")
    run.add_argument("--prompt", type=str, required=True, help="User prompt text")
    run.add_argument("--approve-all-tools", action="store_true", help="Auto-approve all tool calls (dangerous)")
    
    return parser


def find_config_file(config_path: Optional[str] = None) -> Optional[Path]:
    """Find the configuration file."""
    if config_path:
        config_file = Path(config_path)
        if config_file.exists():
            return config_file
        else:
            print(f"Warning: Config file '{config_path}' not found.")
            return None
    
    # Look for config.toml in current directory, then package directory
    current_dir = Path.cwd()
    package_dir = Path(__file__).parent.parent
    
    for directory in [current_dir, package_dir]:
        config_file = directory / "config.toml"
        if config_file.exists():
            return config_file
    
    return None


def main() -> int:
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        command = args.command or "tray"

        if command == "run":
            from .core.agent_host import AgentHost, AgentHostConfig

            provider = str(args.provider or "ollama")
            model = str(args.model or "qwen3:4b-instruct")
            agent_kind = str(args.agent or "react")
            data_dir = Path(args.data_dir).expanduser() if args.data_dir else (Path.home() / ".abstractassistant")

            host = AgentHost(
                AgentHostConfig(
                    provider=provider,
                    model=model,
                    agent_kind=agent_kind,
                    data_dir=data_dir,
                    workspace_root=args.workspace_root,
                )
            )

            def _approve(tool_calls):
                if args.approve_all_tools:
                    return True
                # Prompt for dangerous/unknown batches; safe-only batches auto-approve.
                if not host.tool_policy.requires_approval(tool_calls):
                    return True
                print("\nTool approval required:")
                for tc in tool_calls:
                    name = tc.get("name")
                    arguments = tc.get("arguments")
                    print(f"- {name}({arguments})")
                ans = input("Approve this batch? [y/N] ").strip().lower()
                return ans in {"y", "yes"}

            def _ask_user(wait):
                prompt = str(getattr(wait, "prompt", "") or "Input required:")
                return input(f"\n{prompt}\n> ").strip()

            final = ""
            for ev in host.run_turn(user_text=args.prompt, approve_tools=_approve, ask_user=_ask_user):
                typ = ev.get("type")
                if typ == "assistant":
                    final = str(ev.get("content") or "")
                if typ == "error":
                    raise RuntimeError(str(ev.get("error") or "error"))
            print(final)
            return 0

        # tray (default)
        try:
            from .config import Config  # lightweight

            config_file = find_config_file(args.config)
            config = Config.from_file(config_file) if config_file else Config.default()
            if args.provider:
                config.llm.default_provider = str(args.provider)
            if args.model:
                config.llm.default_model = str(args.model)
        except Exception:
            config = None

        try:
            from .app import AbstractAssistantApp
        except Exception as e:
            print("AbstractAssistant tray mode requires GUI dependencies.")
            print("Install: pip install 'abstractassistant[lite]'")
            if args.debug:
                print(f"Import error: {e}")
            return 2

        app = AbstractAssistantApp(
            config=config,
            debug=bool(args.debug),
            listening_mode=str(getattr(args, "listening_mode", "wait")),
        )
        app.run()
        return 0
        
    except KeyboardInterrupt:
        print("\n👋 AbstractAssistant stopped by user")
        return 0
    except Exception as e:
        print(f"❌ Error starting AbstractAssistant: {e}")
        if getattr(args, "debug", False):
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
