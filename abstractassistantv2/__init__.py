"""Gateway-native assistant v2.

This package keeps the new tray/query-bar architecture separate from the
legacy Qt bubble so the migration stays reversible while the new controller,
settings, and media flows stabilize.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from abstractassistant.config import Config


def launch_tray_app(*, config: Optional[Config] = None, debug: bool = False, data_dir: Optional[Path] = None) -> int:
    from .app import launch_tray_app as _launch_tray_app

    return _launch_tray_app(config=config, debug=debug, data_dir=data_dir)


__all__ = ["launch_tray_app"]
