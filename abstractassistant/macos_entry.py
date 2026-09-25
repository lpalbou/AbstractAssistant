"""Frozen macOS app entrypoint for AbstractAssistant."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from pathlib import Path

from abstractassistant.config import Config, resolve_gateway_connection
from abstractassistant import launch_tray_app


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--gateway-url", type=str, default=None)
    parser.add_argument("--gateway-token", type=str, default=None)
    parser.add_argument("--gateway-handover", type=str, default=None)
    return parser


def _config_from_args(args: argparse.Namespace) -> Config:
    gateway_url, gateway_auth_token = resolve_gateway_connection(
        url_override=getattr(args, "gateway_url", None),
        auth_token_override=getattr(args, "gateway_token", None),
        require_auth_token=False,
    )
    gateway_data = {"url": gateway_url, "auth_token": gateway_auth_token}
    return Config.from_dict({"gateway": gateway_data})


def main() -> int:
    multiprocessing.freeze_support()
    os.environ.setdefault("ABSTRACTASSISTANT_SHOW_ON_LAUNCH", "1")
    args, _unknown = _parser().parse_known_args()
    try:
        config = _config_from_args(args)
    except Exception:
        config = None
    if getattr(sys, "frozen", False):
        log_dir = Path.home() / "Library" / "Logs" / "Assistant"
        os.environ.setdefault("ABSTRACTASSISTANT_TRAY_LOG_PATH", str(log_dir / "abstractassistant-launcher.log"))
        os.environ.setdefault(
            "ABSTRACTASSISTANT_TRAY_CAPTURE_PATH",
            str(log_dir / "abstractassistant-status-item.png"),
        )
    return launch_tray_app(
        config=config,
        debug=False,
        data_dir=None,
        gateway_handover=str(getattr(args, "gateway_handover", None) or ""),
    )


if __name__ == "__main__":
    raise SystemExit(main())
