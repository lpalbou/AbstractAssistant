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
from .templates import select_agent_template, list_agent_entrypoints
from .capabilities import (
    AGENT_INTERFACE_PREFERENCE,
    AssistantCapabilities,
    get_cached_assistant_capabilities,
)
from .session_cache import merge_prompt_cache_runtime_hint, prepare_session_prompt_cache
from .generated_media import (
    ImageGenerationIntent,
    build_generated_image_assistant_message,
    choose_generated_image_format,
    parse_image_generation_intent,
    session_memory_run_id,
)

__all__ = [
    "GatewayClient",
    "GatewayClientConfig",
    "GatewayHttpError",
    "GatewayEventAdapter",
    "build_run_input_data",
    "select_agent_template",
    "list_agent_entrypoints",
    "AGENT_INTERFACE_PREFERENCE",
    "AssistantCapabilities",
    "get_cached_assistant_capabilities",
    "merge_prompt_cache_runtime_hint",
    "prepare_session_prompt_cache",
    "ImageGenerationIntent",
    "build_generated_image_assistant_message",
    "choose_generated_image_format",
    "parse_image_generation_intent",
    "session_memory_run_id",
    "extract_emit_event",
    "extract_flow_end_output",
    "extract_wait_from_record",
    "extract_tool_calls_from_wait",
    "normalize_ui_event_name",
    "parse_status_payload",
]
