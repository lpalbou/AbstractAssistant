#!/usr/bin/env python3
"""
CLI entry point for AbstractAssistant.

This module provides the command-line interface for launching AbstractAssistant.
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

from .app import AbstractAssistantApp
from .config import Config


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="assistant",
        description="AbstractAssistant - AI at your fingertips",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  assistant                    # Launch with default settings
  assistant --config custom.toml  # Use custom config file
  assistant --provider openai     # Set default provider
  assistant --model gpt-4o        # Set default model
  assistant --debug               # Enable debug mode

For more information, visit: https://github.com/yourusername/abstractassistant
        """,
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file (default: config.toml)",
        default=None,
    )
    
    parser.add_argument(
        "--provider",
        type=str,
        choices=["lmstudio", "openai", "anthropic", "ollama"],
        help="Default LLM provider",
    )
    
    parser.add_argument(
        "--model",
        type=str,
        help="Default model name",
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    parser.add_argument(
        "--listening-mode",
        type=str,
        choices=["none", "stop", "wait", "full"],
        help="Voice listening mode (none: no STT, stop: continuous listen/stop on 'STOP' keyword, wait: listen when TTS idle, full: continuous listen/interrupt on any speech)",
        default="wait",
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="AbstractAssistant 1.0.0",
    )
    
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
        # Load configuration
        config_file = find_config_file(args.config)
        if config_file:
            config = Config.from_file(config_file)
            if args.debug:
                print(f"Loaded config from: {config_file}")
        else:
            config = Config.default()
            if args.debug:
                print("Using default configuration")
        
        # Override config with CLI arguments
        if args.provider:
            config.llm.default_provider = args.provider
        if args.model:
            config.llm.default_model = args.model
        
        # Create and run the application
        app = AbstractAssistantApp(config=config, debug=args.debug, listening_mode=args.listening_mode)
        
        print("🤖 Starting AbstractAssistant...")
        print("Look for the icon in your macOS menu bar!")
        
        if args.debug:
            print("Debug mode enabled")
            print(f"Provider: {config.llm.default_provider}")
            print(f"Model: {config.llm.default_model}")
            print(f"Listening mode: {args.listening_mode}")
        
        app.run()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n👋 AbstractAssistant stopped by user")
        return 0
    except Exception as e:
        print(f"❌ Error starting AbstractAssistant: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
