"""
Gateway-first thin-client scaffolding for AbstractAssistant.

This package mirrors the `abstractcode/web` gateway client contract in Python
so the tray UI can render runs via ledger replay + SSE streaming.
"""

from .client import GatewayClient, GatewayClientConfig, GatewayHttpError
from .events import (
    extract_emit_event,
    extract_flow_end_output,
    extract_wait_from_record,
    extract_tool_calls_from_wait,
    normalize_ui_event_name,
    parse_status_payload,
)
from .adapter import GatewayEventAdapter
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
    "GatewayEventAdapter",
    "build_run_input_data",
    "AssistantCapabilities",
    "get_cached_assistant_capabilities",
    "session_memory_run_id",
    "extract_emit_event",
    "extract_flow_end_output",
    "extract_wait_from_record",
    "extract_tool_calls_from_wait",
    "normalize_ui_event_name",
    "parse_status_payload",
]
