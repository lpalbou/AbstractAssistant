"""Basic coverage for the gateway-native assistant v2 helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from abstractassistant.config import Config
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QSystemTrayIcon

from abstractassistantv2.app import (
    AssistantHtmlAction,
    AssistantPalette,
    HistoryScrollRequest,
    _attachment_icon_name,
    _attachment_kind,
    _assistant_content_with_actions,
    _assistant_footer_items,
    _handle_tray_activation,
    _local_attachment_preview_items,
    _media_display_title,
    _merge_attachment_paths,
    _message_bubble_width,
    _message_media_artifacts,
    _visible_history_messages,
)
from abstractassistantv2.controller import AssistantV2Controller
from abstractassistantv2.gateway import AssistantGatewayService
from abstractassistantv2.assistant_workflow import MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
from abstractassistantv2.preferences import (
    AssistantPreferences,
    GatewayConnectionPreferences,
    GatewayConnectionStore,
    PreferencesStore,
    WorkflowSelection,
)
from abstractassistant.ui.gateway_worker import GatewayWorker


class _GatewayCatalogStub:
    def __init__(self) -> None:
        self.voice_model_calls: list[dict] = []
        self.visualflows: list[dict] = []

    def list_visualflows(self) -> list[dict]:
        return list(self.visualflows)

    def get_capability_defaults(self) -> dict:
        return {
            "routes": [
                {
                    "key": "input.text",
                    "kind": "input",
                    "modality": "text",
                    "label": "Text Brain",
                    "provider": "openai",
                    "model": "gpt-4.1",
                    "configured": True,
                },
                {
                    "key": "output.voice",
                    "kind": "output",
                    "modality": "voice",
                    "label": "Voice Output",
                    "provider": "openai",
                    "model": "tts-1",
                    "configured": True,
                    "options": {"voice": "coral"},
                },
            ]
        }

    def workflow_catalog(self, *, scope: str = "tenant_catalog") -> dict:
        assert scope == "tenant_catalog"
        return {
            "items": [
                {
                    "bundle_id": MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                    "bundle_version": "2026.06.12",
                    "default_entrypoint": "chat",
                    "is_default": True,
                    "actions": {"can_run": True},
                    "entrypoints": [{"flow_id": "chat", "name": "Default Chat", "interfaces": ["abstractassistant.agent.v1"]}],
                }
            ]
        }

    def voice_voices(self, **kwargs) -> dict:
        if kwargs.get("providers_only"):
            return {"providers": [{"id": "openai", "label": "OpenAI"}]}
        return {"profiles": [{"id": "coral", "label": "Coral"}]}

    def audio_speech_models(self, **kwargs) -> dict:
        self.voice_model_calls.append(dict(kwargs))
        return {"models": ["tts-1", "tts-1-hd"]}


@pytest.mark.basic
def test_assistant_v2_gateway_service_uses_catalog_workflows_and_voice_catalogs() -> None:
    gateway = _GatewayCatalogStub()
    service = AssistantGatewayService(gateway)

    workflows = service.list_workflows()
    routes = service.route_map()
    providers = service.provider_choices(route_key="output.voice", base_url="https://voices.example.test/v1")
    models = service.model_choices(
        route_key="output.voice",
        provider="openai",
        base_url="https://voices.example.test/v1",
    )
    voices = service.voice_choices(
        provider="openai",
        model="tts-1",
        base_url="https://voices.example.test/v1",
    )

    assert workflows[0].bundle_id == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
    assert workflows[0].bundle_version == "2026.06.12"
    assert workflows[0].registry_scope == "tenant_catalog"
    assert workflows[0].is_default is True
    assert routes["output.voice"].options["voice"] == "coral"
    assert [item.id for item in providers] == ["openai"]
    assert [item.id for item in models] == ["tts-1", "tts-1-hd"]
    assert [item.id for item in voices] == ["coral"]
    assert gateway.voice_model_calls[0]["base_url"] == "https://voices.example.test/v1"


@pytest.mark.basic
def test_assistant_v2_gateway_service_prefers_catalog_default_when_multiple_managed_options_exist() -> None:
    class _GatewayDefaultStub(_GatewayCatalogStub):
        def workflow_catalog(self, *, scope: str = "tenant_catalog") -> dict:
            assert scope == "tenant_catalog"
            return {
                "items": [
                    {
                        "bundle_id": MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                        "bundle_version": "2026.06.11",
                        "default_entrypoint": "chat",
                        "is_default": False,
                        "actions": {"can_run": True},
                        "entrypoints": [{"flow_id": "chat", "name": "Older", "interfaces": ["abstractassistant.agent.v1"]}],
                    },
                    {
                        "bundle_id": MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                        "bundle_version": "2026.06.12",
                        "default_entrypoint": "chat",
                        "is_default": True,
                        "actions": {"can_run": True},
                        "entrypoints": [{"flow_id": "chat", "name": "Default", "interfaces": ["abstractassistant.agent.v1"]}],
                    },
                ]
            }

    service = AssistantGatewayService(_GatewayDefaultStub())

    workflows = service.list_workflows()

    assert len(workflows) == 1
    assert workflows[0].is_default is True
    assert workflows[0].bundle_version == "2026.06.12"


@pytest.mark.basic
def test_assistant_v2_gateway_service_blocks_ambiguous_catalog_without_default() -> None:
    class _GatewayAmbiguousStub(_GatewayCatalogStub):
        def workflow_catalog(self, *, scope: str = "tenant_catalog") -> dict:
            assert scope == "tenant_catalog"
            return {
                "items": [
                    {
                        "bundle_id": MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                        "bundle_version": "2026.06.11",
                        "default_entrypoint": "chat",
                        "is_default": False,
                        "actions": {"can_run": True},
                        "entrypoints": [{"flow_id": "chat", "name": "Older", "interfaces": ["abstractassistant.agent.v1"]}],
                    },
                    {
                        "bundle_id": MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                        "bundle_version": "2026.06.12",
                        "default_entrypoint": "chat",
                        "is_default": False,
                        "actions": {"can_run": True},
                        "entrypoints": [{"flow_id": "chat", "name": "Newer", "interfaces": ["abstractassistant.agent.v1"]}],
                    },
                ]
            }

    service = AssistantGatewayService(_GatewayAmbiguousStub())

    workflows = service.list_workflows()
    status = service.workflow_status()

    assert workflows == []
    assert "exactly one default assistant workflow" in status.error


class _ManagedWorkflowGatewayStub:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.updated: list[dict] = []
        self.published: list[dict] = []
        self.promoted: list[dict] = []
        self._flows: list[dict] = []
        self._bundles: list[dict] = []
        self._catalog_items: list[dict] = []

    def list_visualflows(self) -> list[dict]:
        return list(self._flows)

    def create_visualflow(self, **kwargs) -> dict:
        flow = {"id": "vf123", **kwargs}
        self._flows = [flow]
        self.created.append(dict(kwargs))
        return flow

    def update_visualflow(self, **kwargs) -> dict:
        self.updated.append(dict(kwargs))
        flow = {"id": str(kwargs["flow_id"]), "name": kwargs.get("name"), "description": kwargs.get("description"), "interfaces": kwargs.get("interfaces"), "nodes": kwargs.get("nodes"), "edges": kwargs.get("edges"), "entryNode": kwargs.get("entry_node")}
        self._flows = [flow]
        return flow

    def publish_visualflow(self, **kwargs) -> dict:
        self.published.append(dict(kwargs))
        self._bundles = [
            {
                "bundle_id": kwargs["bundle_id"],
                "bundle_version": "0.0.0",
                "default_entrypoint": "node-1",
                "entrypoints": [
                    {"flow_id": "node-1", "name": "Assistant", "interfaces": ["abstractassistant.agent.v1"]},
                ],
            }
        ]
        return {"ok": True, "bundle_version": "0.0.0"}

    def promote_workflow_catalog_bundle(self, **kwargs) -> dict:
        self.promoted.append(dict(kwargs))
        self._catalog_items = [
            {
                "bundle_id": kwargs["bundle_id"],
                "bundle_version": kwargs["bundle_version"],
                "default_entrypoint": "node-1",
                "is_default": False,
                "actions": {"can_run": True},
                "entrypoints": [
                    {"flow_id": "node-1", "name": "Assistant", "interfaces": ["abstractassistant.agent.v1"]},
                ],
            }
        ]
        return {"ok": True}

    def workflow_catalog(self, *, scope: str = "tenant_catalog") -> dict:
        assert scope == "tenant_catalog"
        return {"items": list(self._catalog_items)}

    def list_bundles(self) -> dict:
        return {"items": list(self._bundles)}


@pytest.mark.basic
def test_assistant_v2_gateway_service_reconciles_and_promotes_catalog_workflow() -> None:
    gateway = _ManagedWorkflowGatewayStub()
    service = AssistantGatewayService(gateway)

    workflows = service.ensure_catalog_workflow()

    assert gateway.created
    assert gateway.published[0]["bundle_id"] == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
    assert gateway.promoted[0]["bundle_id"] == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
    assert workflows[0].bundle_id == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
    assert workflows[0].registry_scope == "tenant_catalog"


class _WrongGatewaySurfaceStub:
    class config:
        base_url = "http://127.0.0.1:8080"

    def list_visualflows(self) -> list[dict]:
        raise RuntimeError("list_visualflows failed: Not Found")

    def workflow_catalog(self, *, scope: str = "tenant_catalog") -> dict:
        raise RuntimeError("workflow_catalog failed: Not Found")

    def gateway_me(self) -> dict:
        raise RuntimeError("gateway_me failed: Not Found")

    def openapi_document(self) -> dict:
        return {
            "info": {"title": "OpenAI Endpoint"},
            "paths": {"/v1/models": {}},
        }

    def list_bundles(self) -> dict:
        raise AssertionError("private bundle fallback must not run against a non-gateway surface")


@pytest.mark.basic
def test_assistant_v2_gateway_service_blocks_private_fallback_on_wrong_surface() -> None:
    service = AssistantGatewayService(_WrongGatewaySurfaceStub())

    workflows = service.list_workflows()
    status = service.workflow_status()

    assert workflows == []
    assert "OpenAI-compatible endpoint" in status.error


@pytest.mark.basic
def test_assistant_v2_preferences_round_trip(tmp_path: Path) -> None:
    store = PreferencesStore(tmp_path / "preferences.json")
    prefs = AssistantPreferences(
        hotkey_enabled=True,
        hotkey_sequence="cmd+shift+space",
        auto_speak=True,
        window_width=1200,
        window_height=700,
        bottom_offset=48,
        tool_preferences={"read_file": "approve", "execute_command": "ask", "edit_file": "disabled"},
    )

    store.save(prefs)

    assert store.load() == prefs


@pytest.mark.basic
def test_assistant_v2_connection_preferences_round_trip(tmp_path: Path) -> None:
    store = GatewayConnectionStore(tmp_path / "gateway_connection.json")
    prefs = GatewayConnectionPreferences(
        base_url="https://gateway.example",
        auth_mode="session",
        user_id="alice",
        session_id="agws_test",
        csrf_token="agcsrf_test",
        session_expires_at="2026-06-12T12:00:00+00:00",
        remember_session=True,
    )

    store.save(prefs)

    assert store.load() == prefs


@pytest.mark.basic
def test_assistant_v2_controller_prefers_runtime_bearer_override_over_saved_connection(tmp_path: Path) -> None:
    controller = object.__new__(AssistantV2Controller)
    controller.connection_store = GatewayConnectionStore(tmp_path / "gateway_connection.json")
    controller.connection_store.save(
        GatewayConnectionPreferences(
            base_url="https://saved.gateway.example",
            auth_mode="bearer",
            auth_token="saved-token",
        )
    )
    controller.config = Config.from_dict(
        {
            "gateway": {
                "url": "http://127.0.0.1:8080",
                "auth_token": "cli-token",
            }
        }
    )

    resolved = AssistantV2Controller._load_connection_preferences(controller)

    assert resolved.base_url == "http://127.0.0.1:8080"
    assert resolved.auth_token == "cli-token"
    assert resolved.auth_mode == "bearer"


@pytest.mark.basic
def test_assistant_v2_controller_returns_catalog_workflow_selection() -> None:
    controller = object.__new__(AssistantV2Controller)
    controller.workflow_options = lambda: [  # type: ignore[method-assign]
        type(
            "_Workflow",
            (),
            {
                "bundle_id": MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                "flow_id": "chat",
                "bundle_version": "2026.06.12",
                "registry_scope": "tenant_catalog",
                "is_default": True,
            },
        )()
    ]

    resolved = AssistantV2Controller.current_workflow(controller)

    assert resolved == WorkflowSelection(
        bundle_id=MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
        flow_id="chat",
        bundle_version="2026.06.12",
        registry_scope="tenant_catalog",
    )


@pytest.mark.basic
def test_assistant_v2_controller_build_chat_worker_uses_gateway_text_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _WorkerCapture:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("abstractassistantv2.controller.GatewayWorker", _WorkerCapture)

    controller = object.__new__(AssistantV2Controller)
    controller.llm_manager = object()
    controller.debug = False
    controller.current_workflow = lambda: WorkflowSelection(  # type: ignore[method-assign]
        bundle_id=MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
        flow_id="chat",
        bundle_version="2026.06.12",
        registry_scope="tenant_catalog",
    )
    controller.resolve_text_route = lambda: type(  # type: ignore[method-assign]
        "_Route",
        (),
        {"provider": "ovh", "model": "gpt-oss-20b"},
    )()
    controller.allowed_tools_for_run = lambda: ["read_file", "web_search"]  # type: ignore[method-assign]
    controller.tool_policy_for_run = lambda: {  # type: ignore[method-assign]
        "auto_approve_tools": ["read_file", "web_search"],
        "require_approval_tools": ["execute_command"],
    }
    controller.latest_image_artifact = lambda: None  # type: ignore[method-assign]

    controller.build_chat_worker(prompt="Hello", attachments=["/tmp/prompt.txt"])

    assert captured["provider"] == "ovh"
    assert captured["model"] == "gpt-oss-20b"
    assert captured["bundle_id"] == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
    assert captured["registry_scope"] == "tenant_catalog"
    assert captured["attachments"] == ["/tmp/prompt.txt"]
    assert captured["allowed_tools"] == ["read_file", "web_search"]
    assert captured["tool_policy"]["require_approval_tools"] == ["execute_command"]
    assert captured["primary_image_artifact"] is None


@pytest.mark.basic
def test_assistant_v2_footer_items_use_live_assistant_stats() -> None:
    message = {
        "role": "assistant",
        "content": "Ready.",
        "metadata": {
            "provider": "openai",
            "model": "gpt-4.1",
            "_assistant_stats": {
                "duration_ms": 1530,
                "llm_calls": 1,
                "tool_calls": 2,
                "usage": {"input_tokens": 120, "output_tokens": 32, "total_tokens": 152},
            },
        },
    }

    assert _assistant_footer_items(message) == ["120 in", "32 out", "1.5s", "2 tools"]


@pytest.mark.basic
def test_assistant_v2_footer_items_parse_history_seed_repl_stats() -> None:
    message = {
        "role": "assistant",
        "content": "Done.",
        "metadata": {
            "_repl": {
                "stats": {
                    "llm_calls": 2,
                    "tool_calls": 1,
                    "tokens": {"prompt": 45, "completion": 11, "total": 56},
                    "started_at": "2026-06-13T10:00:00+00:00",
                    "ended_at": "2026-06-13T10:00:02+00:00",
                }
            }
        },
    }

    assert _assistant_footer_items(message) == ["45 in", "11 out", "2.0s", "2 calls"]


@pytest.mark.basic
def test_assistant_v2_visible_history_messages_prioritizes_latest_user_turn_while_busy() -> None:
    messages = [
        {"role": "assistant", "content": "Previous reply"},
        {"role": "user", "content": "draw me a rabbit"},
    ]

    assert _visible_history_messages(messages, busy=True) == messages


@pytest.mark.basic
def test_assistant_v2_visible_history_messages_keeps_recent_turns_when_idle() -> None:
    messages = [
        {"role": "assistant", "content": "Earlier"},
        {"role": "user", "content": "Latest question"},
        {"role": "system", "content": "ignored"},
    ]

    assert _visible_history_messages(messages, busy=False) == messages[:2]


@pytest.mark.basic
def test_assistant_v2_visible_history_messages_keeps_attachment_only_turns() -> None:
    messages = [
        {
            "role": "user",
            "content": "",
            "metadata": {
                "attachments": [
                    {"local_path": "/tmp/demo.wav", "filename": "demo.wav", "content_type": "audio/wav"}
                ]
            },
        }
    ]

    assert _visible_history_messages(messages, busy=False) == messages


@pytest.mark.basic
def test_assistant_v2_thinking_indicator_tracks_active_run() -> None:
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._run_busy = True
    palette._run_has_final_output = False

    assert AssistantPalette._show_thinking_indicator(palette) is True


@pytest.mark.basic
def test_assistant_v2_thinking_indicator_stops_after_final_output() -> None:
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._run_busy = True
    palette._run_has_final_output = True

    assert AssistantPalette._show_thinking_indicator(palette) is False


@pytest.mark.basic
def test_assistant_v2_message_bubble_width_uses_role_ratios() -> None:
    assert _message_bubble_width(1000, role="user") == 400
    assert _message_bubble_width(1000, role="assistant") == 700


@pytest.mark.basic
def test_assistant_v2_message_media_artifacts_collects_and_deduplicates_media() -> None:
    message = {
        "role": "assistant",
        "content": "Here is the diagram.",
        "metadata": {
            "image_artifact": {"$artifact": "img_1", "filename": "diagram.png", "content_type": "image/png"},
            "generated_media": {
                "image_artifact": {"$artifact": "img_1", "filename": "diagram.png", "content_type": "image/png"},
                "audio_artifact": {"$artifact": "aud_1", "filename": "voice.wav", "content_type": "audio/wav"},
            },
        },
    }

    artifacts = _message_media_artifacts(message)

    assert [item.get("$artifact") for item in artifacts] == ["img_1", "aud_1"]


@pytest.mark.basic
def test_assistant_v2_local_attachment_preview_items_tag_media_modalities() -> None:
    items = _local_attachment_preview_items(["/tmp/example.png", "/tmp/example.mp3", "/tmp/readme.txt"])

    assert items == [
        {"local_path": "/tmp/example.png", "filename": "example.png", "modality": "image"},
        {"local_path": "/tmp/example.mp3", "filename": "example.mp3", "modality": "audio"},
        {"local_path": "/tmp/readme.txt", "filename": "readme.txt"},
    ]


@pytest.mark.basic
def test_assistant_v2_attachment_kind_maps_common_file_types() -> None:
    assert _attachment_kind("/tmp/mockup.png") == "image"
    assert _attachment_kind("/tmp/voice.wav") == "audio"
    assert _attachment_kind("/tmp/demo.mov") == "video"
    assert _attachment_kind("/tmp/app.py") == "code"
    assert _attachment_kind("/tmp/report.pdf") == "document"
    assert _attachment_kind("/tmp/archive.zip") == "archive"
    assert _attachment_kind("/tmp/table.csv") == "data"
    assert _attachment_icon_name("/tmp/mockup.png") == "file-image"


@pytest.mark.basic
def test_assistant_v2_merge_attachment_paths_deduplicates_and_filters_non_files(tmp_path: Path) -> None:
    keep = tmp_path / "keep.txt"
    keep.write_text("hello")
    other = tmp_path / "other.txt"
    other.write_text("world")
    skipped_dir = tmp_path / "folder"
    skipped_dir.mkdir()

    merged = _merge_attachment_paths(
        [str(keep)],
        [str(other), str(keep), str(skipped_dir), str(tmp_path / "missing.txt")],
    )

    assert merged == [str(keep), str(other)]


@pytest.mark.basic
def test_assistant_v2_media_display_title_hides_hash_like_audio_names(tmp_path: Path) -> None:
    path = tmp_path / "artifact.wav"
    path.write_bytes(b"RIFF0000WAVE")

    assert _media_display_title(title="be73678943931c9e88eb1fe57dffac05", kind="audio", path=path) == "Audio"
    assert _media_display_title(title="briefing.wav", kind="audio", path=path) == "briefing.wav"


@pytest.mark.basic
def test_assistant_v2_controller_artifact_cache_filename_uses_runtime_content_type_override() -> None:
    controller = AssistantV2Controller.__new__(AssistantV2Controller)

    filename = AssistantV2Controller._artifact_cache_filename(
        controller,
        artifact_id="abc123",
        artifact={"filename": "", "content_type": ""},
        content_type_override="audio/wav",
    )

    assert filename.endswith(".wav")


@pytest.mark.basic
def test_assistant_v2_resize_visible_history_cards_uses_viewport_width() -> None:
    class _Viewport:
        def width(self) -> int:
            return 900

    class _Scroll:
        def viewport(self) -> _Viewport:
            return _Viewport()

    class _Card:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def sync_to_viewport_width(self, width: int) -> None:
            self.calls.append(int(width))

    class _Item:
        def __init__(self, widget) -> None:
            self._widget = widget

        def widget(self):
            return self._widget

    class _Layout:
        def __init__(self, items) -> None:
            self._items = list(items)

        def count(self) -> int:
            return len(self._items)

        def itemAt(self, index: int):
            return self._items[index]

    card = _Card()
    palette = AssistantPalette.__new__(AssistantPalette)
    palette.history_scroll = _Scroll()
    palette.history_layout = _Layout([_Item(card), _Item(object())])
    palette.width = lambda: 640

    AssistantPalette._resize_visible_history_cards(palette)

    assert card.calls == [900]


@pytest.mark.basic
def test_assistant_v2_sync_history_viewport_matches_content_height() -> None:
    class _Layout:
        def __init__(self) -> None:
            self.invalidated = 0
            self.activated = 0

        def invalidate(self) -> None:
            self.invalidated += 1

        def activate(self) -> None:
            self.activated += 1

    class _Host:
        def __init__(self) -> None:
            self.updated = 0
            self.adjusted = 0

        def updateGeometry(self) -> None:
            self.updated += 1

        def adjustSize(self) -> None:
            self.adjusted += 1

    palette = AssistantPalette.__new__(AssistantPalette)
    palette.history_host = _Host()
    palette.history_layout = _Layout()

    AssistantPalette._sync_history_viewport(palette)

    assert palette.history_layout.invalidated == 1
    assert palette.history_layout.activated == 1
    assert palette.history_host.updated == 1
    assert palette.history_host.adjusted == 1


@pytest.mark.basic
def test_assistant_v2_capture_history_scroll_request_preserves_top_visible_message_offset() -> None:
    class _Bar:
        def value(self) -> int:
            return 182

    class _Scroll:
        def verticalScrollBar(self) -> _Bar:
            return _Bar()

    class _Widget:
        def __init__(self, key: str, y: int, height: int) -> None:
            self._history_message_key = key
            self._y = y
            self._height = height

        def y(self) -> int:
            return self._y

        def height(self) -> int:
            return self._height

    class _Item:
        def __init__(self, widget) -> None:
            self._widget = widget

        def widget(self):
            return self._widget

    class _Layout:
        def __init__(self, widgets) -> None:
            self._items = [_Item(widget) for widget in widgets]

        def count(self) -> int:
            return len(self._items)

        def itemAt(self, index: int):
            return self._items[index]

    palette = AssistantPalette.__new__(AssistantPalette)
    palette.history_scroll = _Scroll()
    palette.history_layout = _Layout([
        _Widget("user-1", 20, 120),
        _Widget("assistant-1", 160, 140),
        _Widget("assistant-2", 320, 140),
    ])

    request = AssistantPalette._capture_history_scroll_request(palette)

    assert request == HistoryScrollRequest(mode="preserve", message_key="assistant-1", offset=22)


@pytest.mark.basic
def test_assistant_v2_apply_history_scroll_request_anchors_message_top_and_bottom_modes() -> None:
    class _Bar:
        def __init__(self) -> None:
            self.value = None

        def maximum(self) -> int:
            return 480

        def setValue(self, value: int) -> None:
            self.value = int(value)

    class _Scroll:
        def __init__(self, bar: _Bar) -> None:
            self._bar = bar

        def verticalScrollBar(self) -> _Bar:
            return self._bar

    class _Widget:
        def __init__(self, key: str, y: int) -> None:
            self._history_message_key = key
            self._y = y

        def geometry(self):
            class _Geometry:
                def __init__(self, top: int) -> None:
                    self._top = top

                def top(self) -> int:
                    return self._top

            return _Geometry(self._y)

    bar = _Bar()
    palette = AssistantPalette.__new__(AssistantPalette)
    palette.history_scroll = _Scroll(bar)
    palette._history_cards_by_key = {
        "assistant-1": _Widget("assistant-1", 24),
        "assistant-2": _Widget("assistant-2", 296),
    }

    AssistantPalette._apply_history_scroll_request(
        palette,
        HistoryScrollRequest(mode="message_top", message_key="assistant-2"),
    )
    assert bar.value == 296

    AssistantPalette._apply_history_scroll_request(
        palette,
        HistoryScrollRequest(mode="bottom"),
    )
    assert bar.value == 480


@pytest.mark.basic
def test_assistant_v2_event_filter_tolerates_preinit_history_events() -> None:
    events: list[str] = []
    history_host = object()

    palette = AssistantPalette.__new__(AssistantPalette)
    palette.history_host = history_host
    palette._schedule_history_scroll_apply = lambda: events.append("schedule")

    handled = AssistantPalette.eventFilter(palette, history_host, QEvent(QEvent.Show))

    assert handled is False
    assert events == ["schedule"]


@pytest.mark.basic
def test_assistant_v2_extracts_safe_html_action_blocks_from_assistant_content() -> None:
    content = """
Here is the page:

```html
<a href="data:text/html;charset=utf-8,%3Chtml%3Ehi%3C/html%3E" target="_blank">Open page</a>
```

Use the button.
""".strip()

    rendered, actions = _assistant_content_with_actions(content)

    assert rendered == "Here is the page:\n\nUse the button."
    assert actions == [
        AssistantHtmlAction(
            label="Open page",
            href="data:text/html;charset=utf-8,%3Chtml%3Ehi%3C/html%3E",
        )
    ]


@pytest.mark.basic
def test_assistant_v2_keeps_non_actionable_html_code_fences_as_code() -> None:
    content = """
```html
<div class="panel"><strong>Example only</strong></div>
```
""".strip()

    rendered, actions = _assistant_content_with_actions(content)

    assert rendered == content
    assert actions == []


@pytest.mark.basic
def test_assistant_v2_tray_activation_opens_palette_on_primary_click() -> None:
    events: list[str] = []

    class _Palette:
        def show_palette(self) -> None:
            events.append("show")

    class _Menu:
        def popup(self, _pos) -> None:
            events.append("menu")

    _handle_tray_activation(palette=_Palette(), menu=_Menu(), reason=QSystemTrayIcon.Trigger)

    assert events == ["show"]


@pytest.mark.basic
def test_assistant_v2_tray_activation_opens_menu_only_on_context_click() -> None:
    events: list[str] = []

    class _Palette:
        def show_palette(self) -> None:
            events.append("show")

    class _Menu:
        def popup(self, _pos) -> None:
            events.append("menu")

    _handle_tray_activation(palette=_Palette(), menu=_Menu(), reason=QSystemTrayIcon.Context)

    assert events == ["menu"]


class _GatewayWorkerStub:
    def __init__(self) -> None:
        self.start_run_calls: list[dict] = []

    def list_bundles(self) -> dict:
        raise AssertionError("tenant catalog workflow selection should not resolve through private bundles")

    def session_prompt_cache_prepare(self, **kwargs) -> dict:
        raise AssertionError("gateway worker must not negotiate prompt cache from the desktop client")

    def start_run(self, **kwargs) -> str:
        self.start_run_calls.append(dict(kwargs))
        return "run_1"

    def get_run(self, *, run_id: str) -> dict:
        return {"status": "running", "waiting": None}

    def get_run_input_data(self, *, run_id: str) -> dict:
        return {"input_data": {"prompt": "Hello from v2"}}


class _LLMManagerStub:
    def __init__(self, gateway: _GatewayWorkerStub) -> None:
        self._gateway = gateway
        self.active_session_id = "session-1"
        self.messages: list[dict] = []
        self.last_run_id = ""

    def gateway_client(self):
        return self._gateway

    def append_message(self, *, role: str, content: str, metadata=None, ts: str = "") -> None:
        payload = {"role": role, "content": content}
        if metadata is not None:
            payload["metadata"] = metadata
        if ts:
            payload["ts"] = ts
        self.messages.append(payload)

    def session_messages(self) -> list[dict]:
        return list(self.messages)

    def set_last_run_id(self, run_id: str) -> None:
        self.last_run_id = run_id


@pytest.mark.basic
def test_gateway_worker_starts_runs_with_catalog_scope_and_version(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _GatewayWorkerStub()
    llm_manager = _LLMManagerStub(gateway)

    def _no_follow(self, *, root_run_id, on_record, should_stop, on_offline=None, on_online=None) -> None:
        return None

    monkeypatch.setattr("abstractassistant.ui.gateway_worker.GatewayRunController.follow_run", _no_follow)

    worker = GatewayWorker(
        llm_manager=llm_manager,
        user_text="Hello from v2",
        provider="",
        model="",
        attachments=[],
        bundle_id=MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
        flow_id="chat",
        bundle_version="2026.06.12",
        registry_scope="tenant_catalog",
        debug=False,
    )

    worker.run()

    assert gateway.start_run_calls == [
        {
            "flow_id": "chat",
            "input_data": {
                "prompt": "Hello from v2",
                "context": {
                    "task": "Hello from v2",
                    "messages": [{"role": "user", "content": "Hello from v2"}],
                },
                "use_context": True,
                "_runtime": {},
                "max_iterations": 50,
                "has_primary_image_context": False,
            },
            "bundle_id": MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
            "bundle_version": "2026.06.12",
            "session_id": "session-1",
            "registry_scope": "tenant_catalog",
        }
    ]
    assert llm_manager.last_run_id == "run_1"
