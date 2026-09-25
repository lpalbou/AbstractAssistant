# AbstractAssistant source package

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .config import Config

__all__ = ["launch_tray_app"]


def launch_tray_app(
    *,
    config: "Optional[Config]" = None,
    debug: bool = False,
    data_dir: Optional[Path] = None,
    gateway_handover: str = "",
) -> int:
    """Launch the tray application.

    The GUI stack (Qt, controller, gateway service) is imported lazily inside
    this call so that `import abstractassistant` — and `assistant --help` — stay
    free of optional GUI/voice dependencies (packaging invariant).
    """
    from .app import launch_tray_app as _launch_tray_app

    return _launch_tray_app(config=config, debug=debug, data_dir=data_dir, gateway_handover=gateway_handover)
