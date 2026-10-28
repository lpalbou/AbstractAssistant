"""
Gateway-first thin-client scaffolding for AbstractAssistant.

This package mirrors the `abstractcode/web` gateway client contract in Python
so the tray UI can render runs from the gateway's replay view (`replay_view`).
"""

from .client import GatewayClient, GatewayClientConfig, GatewayHttpError
from .run_input import build_run_input_data
from .capabilities import (
    AssistantCapabilities,
    get_cached_assistant_capabilities,
)
from .generated_media import session_memory_run_id

__all__ = [
    "GatewayClient",
    "GatewayClientConfig",
    "GatewayHttpError",
    "build_run_input_data",
    "AssistantCapabilities",
    "get_cached_assistant_capabilities",
    "session_memory_run_id",
]
