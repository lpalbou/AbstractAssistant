"""Basic coverage for the gateway-native assistant v2 helpers."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from abstractassistant.config import Config
from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.core.session_index import SessionIndex
from abstractassistant.core.session_store import SessionSnapshot, SessionStore
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeyEvent, QTextCursor
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon
from abstractassistant.utils.mermaid_renderer import mermaid_block_to_data_uri
import abstractassistantv2.app as app_module

from abstractassistantv2.app import (
    AttachmentTextEdit,
    AssistantHtmlAction,
    AssistantPalette,
    HistoryScrollRequest,
    MessageCard,
    MermaidPreviewCard,
    ToolUsageDialog,
    _attachment_icon_name,
    _attachment_kind,
    _assistant_content_blocks,
    _assistant_content_with_actions,
    _assistant_footer_items,
    _assistant_footer_metrics,
    _assistant_tool_calls_for_message,
    _handle_tray_activation,
    _local_attachment_preview_items,
    _media_display_title,
    _merge_attachment_paths,
    _message_bubble_width,
    _message_media_artifacts,
    _refresh_tray_visibility,
    _session_picker_label,
    _tray_feedback_icon,
    _tool_call_summary,
    _visible_history_messages,
    _zoomed_shell_size,
)
from abstractassistantv2.controller import AssistantV2Controller
from abstractassistantv2.gateway import AssistantGatewayService
from abstractassistantv2.assistant_workflow import (
    MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
    normalized_managed_visualflow,
)
from abstractassistantv2.preferences import (
    AssistantPreferences,
    GatewayConnectionPreferences,
    GatewayConnectionStore,
    PreferencesStore,
    WorkflowSelection,
)
from abstractassistant.ui.gateway_worker import GatewayWorker


def _alpha_bbox(pixmap, *, threshold: int = 128) -> tuple[int, int, int, int] | None:
    image = pixmap.toImage()
    min_x = image.width()
    min_y = image.height()
    max_x = -1
    max_y = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > threshold:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x < 0 or max_y < 0:
        return None
    return min_x, min_y, max_x + 1, max_y + 1


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
                    "entrypoints": [
                        {
                            "flow_id": "chat",
                            "name": "Default Chat",
                            "interfaces": ["abstractassistant.agent.v1"],
                        }
                    ],
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
def test_assistant_v2_gateway_service_uses_catalog_workflows_and_voice_catalogs() -> (
    None
):
    gateway = _GatewayCatalogStub()
    service = AssistantGatewayService(gateway)

    workflows = service.list_workflows()
    routes = service.route_map()
    providers = service.provider_choices(
        route_key="output.voice", base_url="https://voices.example.test/v1"
    )
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
def test_assistant_v2_gateway_service_prefers_catalog_default_when_multiple_managed_options_exist() -> (
    None
):
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
                        "entrypoints": [
                            {
                                "flow_id": "chat",
                                "name": "Older",
                                "interfaces": ["abstractassistant.agent.v1"],
                            }
                        ],
                    },
                    {
                        "bundle_id": MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                        "bundle_version": "2026.06.12",
                        "default_entrypoint": "chat",
                        "is_default": True,
                        "actions": {"can_run": True},
                        "entrypoints": [
                            {
                                "flow_id": "chat",
                                "name": "Default",
                                "interfaces": ["abstractassistant.agent.v1"],
                            }
                        ],
                    },
                ]
            }

    service = AssistantGatewayService(_GatewayDefaultStub())

    workflows = service.list_workflows()

    assert len(workflows) == 1
    assert workflows[0].is_default is True
    assert workflows[0].bundle_version == "2026.06.12"


@pytest.mark.basic
def test_assistant_v2_gateway_service_blocks_ambiguous_catalog_without_default() -> (
    None
):
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
                        "entrypoints": [
                            {
                                "flow_id": "chat",
                                "name": "Older",
                                "interfaces": ["abstractassistant.agent.v1"],
                            }
                        ],
                    },
                    {
                        "bundle_id": MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                        "bundle_version": "2026.06.12",
                        "default_entrypoint": "chat",
                        "is_default": False,
                        "actions": {"can_run": True},
                        "entrypoints": [
                            {
                                "flow_id": "chat",
                                "name": "Newer",
                                "interfaces": ["abstractassistant.agent.v1"],
                            }
                        ],
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
        flow = {
            "id": str(kwargs["flow_id"]),
            "name": kwargs.get("name"),
            "description": kwargs.get("description"),
            "interfaces": kwargs.get("interfaces"),
            "nodes": kwargs.get("nodes"),
            "edges": kwargs.get("edges"),
            "entryNode": kwargs.get("entry_node"),
        }
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
                    {
                        "flow_id": "node-1",
                        "name": "Assistant",
                        "interfaces": ["abstractassistant.agent.v1"],
                    },
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
                    {
                        "flow_id": "node-1",
                        "name": "Assistant",
                        "interfaces": ["abstractassistant.agent.v1"],
                    },
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
def test_assistant_v2_gateway_service_reconciles_and_promotes_catalog_workflow() -> (
    None
):
    gateway = _ManagedWorkflowGatewayStub()
    service = AssistantGatewayService(gateway)

    workflows = service.ensure_catalog_workflow()

    assert gateway.created
    assert gateway.published[0]["bundle_id"] == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
    assert gateway.promoted[0]["bundle_id"] == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
    assert workflows[0].bundle_id == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
    assert workflows[0].registry_scope == "tenant_catalog"


@pytest.mark.basic
def test_assistant_v2_managed_workflow_accepts_prompt_alias_for_media_routes() -> None:
    flow = normalized_managed_visualflow()
    nodes = {str(node.get("id")): node for node in flow["nodes"]}
    edges = {str(edge.get("id")): edge for edge in flow["edges"]}

    route_break = nodes["route_break"]
    route_break_data = route_break["data"]
    assert route_break_data["breakConfig"]["selectedPaths"] == [
        "mode",
        "assistant_message",
        "media_prompt",
        "prompt",
    ]
    assert any(pin["id"] == "prompt" for pin in route_break_data["outputs"])
    assert (
        nodes["route_call"]["data"]["effectConfig"]["structured_output_fallback"]
        is True
    )

    route_media_prompt = nodes["route_media_prompt"]
    assert route_media_prompt["type"] == "coalesce"
    assert edges["route-break-media-prompt-primary"]["target"] == "route_media_prompt"
    assert edges["route-break-media-prompt-primary"]["targetHandle"] == "a"
    assert edges["route-break-media-prompt-fallback"]["target"] == "route_media_prompt"
    assert edges["route-break-media-prompt-fallback"]["targetHandle"] == "b"

    for edge_id, target in [
        ("route-break-image-prompt", "generate_image"),
        ("route-break-edit-prompt", "edit_image"),
        ("route-break-video-prompt", "generate_video"),
        ("route-break-image-to-video-prompt", "image_to_video"),
        ("route-break-music-prompt", "generate_music"),
        ("route-break-sound-prompt", "generate_sound"),
    ]:
        edge = edges[edge_id]
        assert edge["source"] == "route_media_prompt"
        assert edge["sourceHandle"] == "result"
        assert edge["target"] == target
        assert edge["targetHandle"] == "prompt"


@pytest.mark.basic
def test_mermaid_preview_card_keeps_wide_diagrams_zoomable_inline() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    data_uri = mermaid_block_to_data_uri(
        "flowchart LR\n"
        "    A[Observation] --> B[Thought (Reasoning)]\n"
        "    B --> C[Action]\n"
        "    C --> D[Observation (Feedback)]\n"
        "    D --> A\n"
    )

    assert data_uri is not None

    card = MermaidPreviewCard(
        source="flowchart LR", data_uri=data_uri, bubble_width=760
    )
    card.show()
    app.processEvents()

    initial = card._image_label.pixmap()
    assert initial is not None
    assert initial.width() == 760
    assert card._scroll.horizontalScrollBar().maximum() == 0

    initial_width = initial.width()
    card._set_zoom_multiplier(card._zoom_multiplier * 1.18)
    app.processEvents()

    zoomed = card._image_label.pixmap()
    assert zoomed is not None
    assert zoomed.width() > initial_width
    assert card._scroll.horizontalScrollBar().maximum() > 0
    card.close()


@pytest.mark.basic
def test_user_message_card_keeps_timestamp_tight_to_single_line_message() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    card = MessageCard(
        message={
            "role": "user",
            "content": "create a true detailed ReAct diagram",
            "ts": "2026-06-17T00:38:00+00:00",
        },
        message_key="user-1",
        renderer=None,
        on_open_artifact=lambda *_args, **_kwargs: None,
        build_media_preview=None,
        bubble_width=760,
    )
    card.show()
    app.processEvents()

    bubble_layout = card._bubble.layout()
    assert bubble_layout is not None
    assert bubble_layout.spacing() == 0
    stamp_layout = bubble_layout.itemAt(bubble_layout.count() - 1).layout()
    assert stamp_layout is not None
    assert stamp_layout.contentsMargins().top() == 0
    card.close()


@pytest.mark.basic
def test_assistant_v2_zoomed_shell_size_grows_by_40_percent_per_axis() -> None:
    width, height = _zoomed_shell_size(
        screen_width=2200,
        screen_height=1400,
        normal_width=520,
        normal_height=360,
    )

    assert (width, height) == (1540, 1098)


@pytest.mark.basic
def test_assistant_v2_busy_tray_feedback_icon_renders_pixmap() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    icon = _tray_feedback_icon(state="busy", frame=5, size=40)
    pixmap = icon.pixmap(40, 40)

    assert app is not None
    assert not pixmap.isNull()
    assert pixmap.width() == 40
    assert pixmap.height() == 40


@pytest.mark.basic
@pytest.mark.parametrize("state", ["idle", "busy", "complete"])
def test_assistant_v2_tray_feedback_icon_uses_large_opaque_footprint(
    state: str,
) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    icon = _tray_feedback_icon(state=state, frame=5, size=44)
    pixmap = icon.pixmap(44, 44)
    bbox = _alpha_bbox(pixmap, threshold=128)

    assert app is not None
    assert bbox is not None
    left, top, right, bottom = bbox
    assert right - left >= 38
    assert bottom - top >= 38


@pytest.mark.basic
def test_assistant_v2_session_picker_label_uses_compact_date_and_topic() -> None:
    label = _session_picker_label(
        {
            "created_at": "2026-06-21T10:14:00+00:00",
            "updated_at": "2026-06-21T10:59:00+00:00",
            "title": "Investigate why the menu bar session picker truncates valuable context",
        }
    )

    assert (
        label == "26/06/21 - Investigate why the menu bar session picker truncates val…"
    )


@pytest.mark.basic
def test_llm_manager_session_fallback_title_uses_first_user_query(
    tmp_path: Path,
) -> None:
    index = SessionIndex(tmp_path)
    record = index.create_session()
    store = SessionStore(index.data_dir_for(record.session_id) / "session.json")
    store.save(
        SessionSnapshot(
            session_id=record.session_id,
            actor_id=record.actor_id,
            messages=[
                {"role": "user", "content": "Plan the Q3 launch checklist"},
                {"role": "assistant", "content": "Sure, let's map it out."},
                {"role": "user", "content": "Also estimate the staffing risks"},
            ],
            last_run_id=None,
        )
    )
    manager = LLMManager.__new__(LLMManager)
    manager._session_index = index  # type: ignore[attr-defined]

    title = LLMManager._fallback_title_for_session(manager, record.session_id)

    assert title == "Plan the Q3 launch checklist"


@pytest.mark.basic
def test_assistant_v2_refresh_tray_visibility_reapplies_icon_and_attach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    captures: list[str] = []

    class _Tray:
        @staticmethod
        def isSystemTrayAvailable() -> bool:
            return True

        def show(self) -> None:
            events.append("show")

        def setVisible(self, visible: bool) -> None:
            events.append(f"visible:{visible}")

        def isVisible(self) -> bool:
            return True

    class _Palette:
        def attach_tray(self, _tray) -> None:
            events.append("attach")

        def _refresh_tray_feedback(self) -> None:
            events.append("refresh")

    monkeypatch.setattr(app_module, "QSystemTrayIcon", _Tray)
    monkeypatch.setattr(
        app_module, "_native_status_item_metrics", lambda: (1, (22, 22), (16, 22))
    )
    monkeypatch.setattr(
        app_module,
        "_capture_native_status_item_button_png",
        lambda reason="": captures.append(reason or "refresh") or True,
    )

    state = _refresh_tray_visibility(tray=_Tray(), palette=_Palette(), reason="test")

    assert state.qt_visible is True
    assert state.ready is True
    assert events == ["show", "visible:True", "attach", "refresh"]
    assert captures == ["test"]


@pytest.mark.basic
def test_assistant_v2_hidden_final_reply_marks_unread_and_notifies() -> None:
    class _AutoSpeak:
        def isChecked(self) -> bool:
            return False

    notifications: list[str] = []
    status_calls: list[tuple[str, str]] = []
    refresh_calls: list[str] = []
    history_calls: list[HistoryScrollRequest] = []

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._run_busy = True
    palette._run_has_final_output = False
    palette._tray_completion_unread = False
    palette.auto_speak = _AutoSpeak()
    palette.refresh_history = lambda request=None: history_calls.append(request)
    palette._history_scroll_request = lambda **kwargs: HistoryScrollRequest(**kwargs)
    palette._latest_visible_message_key = lambda role="": "assistant-1"
    palette._set_history_status = lambda text="", tone="neutral": None
    palette._set_status = lambda text, tone="neutral": status_calls.append((text, tone))
    palette._refresh_tray_feedback = lambda: refresh_calls.append("refresh")
    palette._notify_completion_ready = lambda content: notifications.append(content)
    palette.isVisible = lambda: False

    AssistantPalette._on_worker_event(
        palette,
        {
            "type": "assistant",
            "final": True,
            "content": "Rendered and ready.",
            "history_changed": False,
        },
    )

    assert palette._run_busy is False
    assert palette._run_has_final_output is True
    assert palette._tray_completion_unread is True
    assert status_calls[-1] == ("Ready", "neutral")
    assert refresh_calls == ["refresh"]
    assert notifications == ["Rendered and ready."]
    assert history_calls == []


@pytest.mark.basic
def test_assistant_v2_run_activity_event_updates_inline_status() -> None:
    status_calls: list[tuple[str, str]] = []

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._set_history_status = lambda text="", tone="neutral": status_calls.append(
        (text, tone)
    )

    AssistantPalette._on_worker_event(
        palette,
        {
            "type": "run_activity",
            "summary": "Running (abc123): search online for Genentech roles",
        },
    )

    assert status_calls == [
        ("Running (abc123): search online for Genentech roles", "busy")
    ]


@pytest.mark.basic
def test_assistant_v2_tool_event_updates_inline_status() -> None:
    status_calls: list[tuple[str, str, bool, str]] = []

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._set_history_status = (
        lambda text="", tone="neutral", rich=False, tooltip=None: status_calls.append(
            (text, tone, rich, str(tooltip or ""))
        )
    )

    AssistantPalette._on_worker_event(
        palette,
        {
            "type": "tool",
            "message": {
                "metadata": {
                    "name": "web_search",
                    "arguments": {
                        "query": "ML Engineering Director Genentech AI4DD 2026",
                        "num_results": 10,
                    },
                }
            },
        },
    )

    assert status_calls == [
        (
            '<span style="color:#63d98b; font-weight:800;">web_search</span>'
            '<span style="color:#63d98b; font-weight:800;">(</span>'
            '<span style="color:#ffc963; font-weight:400;">'
            "query=&quot;ML Engineering Director Genentech AI4DD 2026&quot;, num_results=10</span>"
            '<span style="color:#63d98b; font-weight:800;">)</span>',
            "busy",
            True,
            'web_search(query="ML Engineering Director Genentech AI4DD 2026", num_results=10)',
        )
    ]


@pytest.mark.basic
def test_assistant_v2_tool_status_budget_tracks_palette_width() -> None:
    app = QApplication.instance() or QApplication([])

    class _FakeWidget:
        def __init__(self, width: int) -> None:
            self._width = width

        def width(self) -> int:
            return self._width

        def font(self):
            return app.font()

    palette = AssistantPalette.__new__(AssistantPalette)
    palette.isMaximized = lambda: False
    palette.width = lambda: 420
    palette.chat_status_label = _FakeWidget(420)
    palette.history_card = _FakeWidget(420)
    small = AssistantPalette._tool_history_label_max_chars(palette)

    palette.isMaximized = lambda: True
    palette.width = lambda: 1100
    palette.chat_status_label = _FakeWidget(1100)
    palette.history_card = _FakeWidget(1100)
    large = AssistantPalette._tool_history_label_max_chars(palette)

    assert small < large
    assert large >= 120


@pytest.mark.basic
def test_assistant_v2_worker_finished_shows_non_durable_empty_reply_diagnostic() -> None:
    appended: list[tuple[str, dict]] = []
    history_calls: list[HistoryScrollRequest] = []
    status_calls: list[tuple[str, str]] = []
    refresh_calls: list[str] = []

    class _Controller:
        @staticmethod
        def append_assistant_message(content: str, metadata=None) -> None:
            appended.append((content, dict(metadata or {})))

        @staticmethod
        def last_run_id() -> str:
            return "run-123"

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._worker = object()
    palette._run_busy = True
    palette._run_has_final_output = False
    palette._controller = _Controller()
    palette._show_thinking_indicator = lambda: False
    palette._set_history_status = lambda text="", tone="neutral": status_calls.append(
        (text, tone)
    )
    palette.refresh_history = lambda request=None: history_calls.append(request)
    palette._history_scroll_request = lambda **kwargs: HistoryScrollRequest(**kwargs)
    palette._latest_visible_message_key = lambda role="": "assistant-fallback"
    palette._refresh_tray_feedback = lambda: refresh_calls.append("refresh")
    palette._set_status = lambda text, tone="neutral": status_calls.append(
        (f"main:{text}", tone)
    )

    AssistantPalette._on_worker_finished(palette)

    assert appended == []
    assert palette._run_has_final_output is True
    assert history_calls == []
    assert (
        "The workflow completed, but it returned no written reply.",
        "info",
    ) in status_calls
    assert ("main:Ready", "neutral") in status_calls
    assert refresh_calls == ["refresh"]


@pytest.mark.basic
def test_assistant_v2_send_button_stops_active_run() -> None:
    """While a run is active the composer button cancels it: a gateway cancel
    is submitted for the run and the follower thread is interrupted."""
    cancelled: list[str] = []
    interrupted: list[bool] = []
    status_calls: list[tuple[str, str]] = []

    class _Controller:
        @staticmethod
        def cancel_run(run_id: str) -> bool:
            cancelled.append(run_id)
            return True

        @staticmethod
        def last_run_id() -> str:
            return "run-active"

    class _Worker:
        def requestInterruption(self) -> None:  # noqa: N802 (Qt naming)
            interrupted.append(True)

    submitted: list[bool] = []
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._controller = _Controller()
    palette._worker = _Worker()
    palette._submit = lambda: submitted.append(True)
    palette._set_status = lambda text, tone="neutral": status_calls.append((text, tone))
    palette._set_history_status = lambda text="", tone="neutral": status_calls.append((text, tone))

    AssistantPalette._on_send_button_clicked(palette)

    assert submitted == []  # busy → does not start a second run
    assert cancelled == ["run-active"]
    assert interrupted == [True]


@pytest.mark.basic
def test_assistant_v2_send_button_sends_when_idle() -> None:
    submitted: list[bool] = []
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._worker = None
    palette._submit = lambda: submitted.append(True)

    AssistantPalette._on_send_button_clicked(palette)

    assert submitted == [True]


@pytest.mark.basic
def test_assistant_v2_replay_degraded_prevents_finished_fallback() -> None:
    appended: list[tuple[str, dict]] = []
    status_calls: list[tuple[str, str]] = []

    class _Controller:
        @staticmethod
        def append_assistant_message(content: str, metadata=None) -> None:
            appended.append((content, dict(metadata or {})))

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._worker = object()
    palette._run_busy = True
    palette._run_has_final_output = False
    palette._controller = _Controller()
    palette._tray_completion_unread = False
    palette._show_thinking_indicator = lambda: False
    palette._set_history_status = lambda text="", tone="neutral": status_calls.append(
        (text, tone)
    )
    palette._set_status = lambda text, tone="neutral": status_calls.append(
        (f"main:{text}", tone)
    )
    palette._refresh_tray_feedback = lambda: None
    palette.refresh_history = lambda request=None: None

    AssistantPalette._on_worker_event(
        palette,
        {
            "type": "replay_degraded",
            "message": "Gateway history replay failed: unavailable",
        },
    )
    AssistantPalette._on_worker_finished(palette)

    assert appended == []
    assert palette._run_has_final_output is True
    assert ("Gateway history replay failed: unavailable", "error") in status_calls


@pytest.mark.basic
def test_launch_tray_app_shows_palette_when_bundle_requests_visible_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class _Signal:
        def connect(self, callback) -> None:
            events.append("tray-connect")
            self.callback = callback

    class _App:
        def __init__(self, _argv) -> None:
            self.applicationStateChanged = _Signal()

        @staticmethod
        def instance():
            return None

        def setQuitOnLastWindowClosed(self, value: bool) -> None:
            events.append(f"quit:{value}")

        def setApplicationName(self, name: str) -> None:
            events.append(f"name:{name}")

        def setWindowIcon(self, _icon) -> None:
            events.append("icon")

        def quit(self) -> None:
            events.append("quit-called")

        def exec_(self) -> int:
            events.append("exec")
            return 17

    class _Palette:
        def __init__(self, **_kwargs) -> None:
            pass

        def attach_tray(self, _tray) -> None:
            events.append("attach-tray")

        def show_palette(self) -> None:
            events.append("show")

        def hide(self) -> None:
            events.append("hide")

        def _create_session(self) -> None:
            events.append("new-session")

        def _open_settings(self) -> None:
            events.append("settings")

    class _Tray:
        @staticmethod
        def isSystemTrayAvailable() -> bool:
            return True

        def __init__(self, _icon, _app) -> None:
            self.activated = _Signal()
            self._visible = False

        def setToolTip(self, _text: str) -> None:
            events.append("tooltip")

        def setIcon(self, _icon) -> None:
            events.append("tray-icon")

        def setVisible(self, visible: bool) -> None:
            self._visible = bool(visible)
            events.append(f"tray-visible:{visible}")

        def isVisible(self) -> bool:
            return self._visible

        def show(self) -> None:
            self._visible = True
            events.append("tray-show")

        def setContextMenu(self, _menu) -> None:
            events.append("tray-menu")

    class _Menu:
        def __init__(self) -> None:
            self.aboutToShow = _Signal()

        def addAction(self, _label, _callback=None):
            events.append(f"action:{_label}")
            return object()

        def hide(self) -> None:
            events.append("menu-hide")

        def addSeparator(self) -> None:
            events.append("separator")

    monkeypatch.setenv("ABSTRACTASSISTANT_SHOW_ON_LAUNCH", "1")
    monkeypatch.setattr(app_module, "QApplication", _App)
    monkeypatch.setattr(app_module, "AssistantV2Controller", lambda **kwargs: object())
    monkeypatch.setattr(app_module, "AssistantPalette", _Palette)
    monkeypatch.setattr(app_module, "QSystemTrayIcon", _Tray)
    monkeypatch.setattr(app_module, "QMenu", _Menu)
    monkeypatch.setattr(
        app_module, "_native_status_item_metrics", lambda: (1, (22, 22), (16, 22))
    )
    monkeypatch.setattr(
        app_module,
        "QTimer",
        type(
            "_Timer", (), {"singleShot": staticmethod(lambda _ms, callback: callback())}
        ),
    )
    monkeypatch.setattr(app_module, "_qt_icon", lambda: object())

    result = app_module.launch_tray_app(config=None, debug=False, data_dir=None)

    assert result == 17
    assert "show" in events
    assert "hide" not in events
    assert events.count("tray-connect") >= 2


@pytest.mark.basic
def test_launch_tray_app_waits_for_native_tray_readiness_before_visible_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    metric_values = [
        (0, (0, 0), (0, 0)),
        (0, (0, 0), (0, 0)),
        (1, (22, 22), (18, 22)),
        (1, (22, 22), (18, 22)),
    ]

    class _Signal:
        def connect(self, callback) -> None:
            self.callback = callback

    class _App:
        def __init__(self, _argv) -> None:
            self.applicationStateChanged = _Signal()

        @staticmethod
        def instance():
            return None

        def setQuitOnLastWindowClosed(self, _value: bool) -> None:
            pass

        def setApplicationName(self, _name: str) -> None:
            pass

        def setWindowIcon(self, _icon) -> None:
            pass

        def processEvents(self) -> None:
            events.append("process")

        def quit(self) -> None:
            events.append("quit")

        def exec_(self) -> int:
            return 0

    class _Palette:
        def __init__(self, **_kwargs) -> None:
            self.show_count = 0

        def attach_tray(self, _tray) -> None:
            events.append("attach-tray")

        def show_palette(self) -> None:
            self.show_count += 1
            events.append(f"show:{self.show_count}")

        def hide(self) -> None:
            events.append("hide")

        def _create_session(self) -> None:
            pass

        def _open_settings(self) -> None:
            pass

        def _set_banner(self, text: str = "", tone: str = "info") -> None:
            events.append(f"banner:{tone}:{bool(text)}")

    class _Tray:
        @staticmethod
        def isSystemTrayAvailable() -> bool:
            return True

        def __init__(self, _icon, _app) -> None:
            self.activated = _Signal()
            self._visible = False

        def setToolTip(self, _text: str) -> None:
            pass

        def setIcon(self, _icon) -> None:
            pass

        def setVisible(self, visible: bool) -> None:
            self._visible = bool(visible)

        def isVisible(self) -> bool:
            return self._visible

        def show(self) -> None:
            self._visible = True

        def setContextMenu(self, _menu) -> None:
            pass

    class _Menu:
        def __init__(self) -> None:
            self.aboutToShow = _Signal()

        def addAction(self, _label, _callback=None):
            return object()

        def hide(self) -> None:
            return None

        def addSeparator(self) -> None:
            return None

    monkeypatch.setenv("ABSTRACTASSISTANT_SHOW_ON_LAUNCH", "1")
    monkeypatch.setattr(app_module, "QApplication", _App)
    monkeypatch.setattr(app_module, "AssistantV2Controller", lambda **kwargs: object())
    monkeypatch.setattr(app_module, "AssistantPalette", _Palette)
    monkeypatch.setattr(app_module, "QSystemTrayIcon", _Tray)
    monkeypatch.setattr(app_module, "QMenu", _Menu)
    monkeypatch.setattr(
        app_module,
        "_native_status_item_metrics",
        lambda values=metric_values: values.pop(0) if len(values) > 1 else values[0],
    )
    monkeypatch.setattr(
        app_module,
        "QTimer",
        type(
            "_Timer", (), {"singleShot": staticmethod(lambda _ms, callback: callback())}
        ),
    )
    monkeypatch.setattr(app_module, "_qt_icon", lambda: object())

    app_module.launch_tray_app(config=None, debug=False, data_dir=None)

    assert "show:1" in events
    assert events.count("show:1") == 1
    assert not any(entry.startswith("banner:warn:True") for entry in events)


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
        raise AssertionError(
            "private bundle fallback must not run against a non-gateway surface"
        )


@pytest.mark.basic
def test_assistant_v2_gateway_service_blocks_private_fallback_on_wrong_surface() -> (
    None
):
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
        tool_preferences={
            "read_file": "approve",
            "execute_command": "ask",
            "edit_file": "disabled",
        },
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
def test_assistant_v2_controller_prefers_runtime_bearer_override_over_saved_connection(
    tmp_path: Path,
) -> None:
    controller = object.__new__(AssistantV2Controller)
    controller.connection_store = GatewayConnectionStore(
        tmp_path / "gateway_connection.json"
    )
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
def test_assistant_v2_controller_build_chat_worker_does_not_pass_text_route_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    assert "provider" not in captured
    assert "model" not in captured
    assert captured["bundle_id"] == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
    assert captured["registry_scope"] == "tenant_catalog"
    assert captured["attachments"] == ["/tmp/prompt.txt"]
    assert captured["allowed_tools"] == ["read_file", "web_search"]
    assert captured["tool_policy"]["require_approval_tools"] == ["execute_command"]
    assert captured["primary_image_artifact"] is None


@pytest.mark.basic
def test_assistant_v2_controller_session_tool_auto_approval_is_chat_scoped() -> None:
    controller = AssistantV2Controller.__new__(AssistantV2Controller)
    controller._session_auto_approve_all = set()
    controller.llm_manager = SimpleNamespace(active_session_id="chat-a")
    controller.tool_inventory = lambda: {  # type: ignore[method-assign]
        "items": [
            {"name": "execute_command", "selected_mode": "ask"},
            {"name": "web_search", "selected_mode": "approve"},
            {"name": "delete_file", "selected_mode": "disabled"},
        ]
    }

    assert (
        controller.should_auto_approve_tool_batch([{"name": "execute_command"}])
        is False
    )
    controller.grant_session_tool_auto_approval()

    assert (
        controller.should_auto_approve_tool_batch([{"name": "execute_command"}]) is True
    )
    assert controller.should_auto_approve_tool_batch([{"name": "delete_file"}]) is False
    assert controller.tool_policy_for_run() == {
        "auto_approve_tools": ["execute_command", "web_search"],
        "require_approval_tools": [],
    }

    controller.llm_manager.active_session_id = "chat-b"
    assert (
        controller.should_auto_approve_tool_batch([{"name": "execute_command"}])
        is False
    )


@pytest.mark.basic
def test_assistant_v2_controller_hydrates_tool_details_from_ledger_run_tree() -> None:
    class _Gateway:
        def __init__(self) -> None:
            self.ledgers = {
                "root": [
                    {
                        "status": "completed",
                        "result": {"output": {"meta": {"sub_run_id": "child"}}},
                    }
                ],
                "child": [
                    {
                        "status": "completed",
                        "effect": {
                            "type": "tool_calls",
                            "payload": {
                                "tool_calls": [
                                    {
                                        "name": f"tool_{index}",
                                        "call_id": f"c{index}",
                                        "arguments": {"index": index},
                                    }
                                    for index in range(7)
                                ]
                            },
                        },
                        "result": {
                            "results": [
                                {
                                    "call_id": f"c{index}",
                                    "success": True,
                                    "output": f"ok {index}",
                                }
                                for index in range(7)
                            ]
                        },
                    }
                ],
            }

        def get_ledger(self, *, run_id: str, after: int, limit: int) -> dict:
            items = self.ledgers.get(run_id, [])
            chunk = items[int(after) : int(after) + int(limit)]
            return {"items": chunk, "next_after": int(after) + len(chunk)}

    controller = AssistantV2Controller.__new__(AssistantV2Controller)
    controller.gateway = _Gateway()
    message = {
        "role": "assistant",
        "content": "Done.",
        "metadata": {
            "run_id": "root",
            "_assistant_stats": {
                "tool_calls": 7,
                "tool_call_details": [{"name": "stale_cached_tool", "arguments": {}}],
            },
        },
    }

    result = controller.tool_call_details_for_message(message)

    assert result["source"] == "ledger"
    assert len(result["tool_calls"]) == 7
    assert result["tool_calls"][0]["name"] == "tool_0"
    assert result["tool_calls"][0]["run_id"] == "child"


@pytest.mark.basic
def test_assistant_v2_controller_falls_back_to_scratchpad_when_ledger_missing() -> None:
    class _Gateway:
        def get_ledger(self, *, run_id: str, after: int, limit: int) -> dict:
            raise RuntimeError(f"Run {run_id} not found")

    controller = AssistantV2Controller.__new__(AssistantV2Controller)
    controller.gateway = _Gateway()
    message = {
        "role": "assistant",
        "content": "Done.",
        "metadata": {
            "run_id": "old-run",
            "_assistant_stats": {"tool_calls": 2},
            "scratchpad": {
                "cycles": [
                    {
                        "i": 1,
                        "tool_calls": [
                            {
                                "name": "fetch_url",
                                "call_id": "c1",
                                "arguments": {"url": "https://example.com"},
                            }
                        ],
                    },
                    {
                        "i": 2,
                        "tool_calls": [
                            {
                                "name": "execute_command",
                                "call_id": "c2",
                                "arguments": {"command": "pwd"},
                            }
                        ],
                    },
                ]
            },
        },
    }

    result = controller.tool_call_details_for_message(message)

    assert result["source"] == "scratchpad"
    assert [call["name"] for call in result["tool_calls"]] == [
        "fetch_url",
        "execute_command",
    ]
    assert result["tool_calls"][0]["run_id"] == "old-run"


@pytest.mark.basic
def test_assistant_v2_tool_request_auto_approval_bypasses_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approvals: list[bool] = []
    status_calls: list[tuple[str, str]] = []

    class _Controller:
        def should_auto_approve_tool_batch(self, tool_calls):
            return True

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._controller = _Controller()
    palette._worker = SimpleNamespace(
        provide_tool_approval=lambda approved: approvals.append(bool(approved))
    )
    palette._set_tool_history_status = lambda **kwargs: status_calls.append(
        (kwargs["prefix"], kwargs["name"])
    )
    palette._set_history_status = lambda *args, **kwargs: None

    def _raise_dialog(*_args, **_kwargs):
        raise AssertionError(
            "approval dialog should not open when this chat already trusts enabled tools"
        )

    monkeypatch.setattr(app_module, "ToolApprovalDialog", _raise_dialog)

    AssistantPalette._on_worker_event(
        palette,
        {
            "type": "tool_request",
            "tool_calls": [
                {"name": "execute_command", "arguments": {"command": "pwd"}}
            ],
        },
    )

    assert approvals == [True]
    assert status_calls[-1] == ("Auto-approved in this chat: ", "execute_command")


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
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 32,
                    "total_tokens": 152,
                },
            },
        },
    }

    # No tool_call_details are attached, so the files metric is omitted (it
    # cannot be derived honestly) while tools stays reported by count.
    assert _assistant_footer_items(message) == [
        "input : 120 tk",
        "output : 32 tk",
        "tools : 2",
        "1.5s",
        "gpt-4.1",
    ]


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

    assert _assistant_footer_items(message) == [
        "input : 45 tk",
        "output : 11 tk",
        "tools : 1",
        "2.0s",
    ]


@pytest.mark.basic
def test_assistant_v2_footer_tools_metric_keeps_details_and_priority() -> None:
    message = {
        "role": "assistant",
        "content": "Done.",
        "metadata": {
            "model": "gpt-5.4-mini",
            "_assistant_stats": {
                "duration_ms": 40100,
                "llm_calls": 8,
                "tool_calls": 2,
                "tool_call_details": [
                    {"name": "web_search", "arguments": {"query": "Genentech roles"}},
                    {"name": "fetch_url", "arguments": {"url": "https://example.com"}},
                ],
                "usage": {
                    "input_tokens": 110139,
                    "output_tokens": 1890,
                    "total_tokens": 112029,
                },
            },
        },
    }

    metrics = _assistant_footer_metrics(message)

    assert [metric["kind"] for metric in metrics] == [
        "tokens_in",
        "tokens_out",
        "tools",
        "files",
        "duration",
        "model",
    ]
    assert [metric["plain"] for metric in metrics] == [
        "input : 110,139 tk",
        "output : 1,890 tk",
        "tools : 2",
        "files : 0",
        "40s",
        "gpt-5.4-mini",
    ]
    tools_metric = metrics[2]
    assert tools_metric["clickable"] is True
    assert "web_search" in tools_metric["tooltip"]
    assert "Genentech roles" in tools_metric["tooltip"]
    files_metric = metrics[3]
    assert "No files were created" in files_metric["tooltip"]
    assert _assistant_tool_calls_for_message(message)[0]["name"] == "web_search"


@pytest.mark.basic
def test_assistant_v2_footer_files_metric_derives_operations_from_tool_details() -> None:
    message = {
        "role": "assistant",
        "content": "Done.",
        "metadata": {
            "_assistant_stats": {
                "tool_calls": 4,
                "tool_call_details": [
                    {
                        "name": "write_file",
                        "arguments": {"file_path": "README.md", "content": "x"},
                    },
                    {
                        "name": "execute_command",
                        "arguments": {"command": "mkdir -p docs && mv draft.md docs/draft.md"},
                    },
                    # Failed calls must not count as file activity.
                    {
                        "name": "edit_file",
                        "arguments": {"file_path": "broken.py"},
                        "success": False,
                    },
                    {"name": "web_search", "arguments": {"query": "abc"}},
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }
        },
    }

    metrics = {metric["kind"]: metric for metric in _assistant_footer_metrics(message)}

    files_metric = metrics["files"]
    assert files_metric["plain"] == "files : 3"
    assert "Created" in files_metric["tooltip"]
    assert "README.md" in files_metric["tooltip"]
    assert "docs/draft.md" in files_metric["tooltip"]
    assert "broken.py" not in files_metric["tooltip"]

    tools_metric = metrics["tools"]
    assert tools_metric["plain"] == "tools : 4"
    assert "[failed]" in tools_metric["tooltip"]


@pytest.mark.basic
def test_assistant_v2_footer_ignores_bare_workflow_meta_counts() -> None:
    """A bare workflow-meta tool count (no stats block, no details) is not
    enough to render stats: no partial/fallback footers — messages without
    recorded stats show only the model line."""
    message = {
        "role": "assistant",
        "content": "Done.",
        "metadata": {
            "provider": "endpoint:ovh-provider",
            "model": "gpt-oss-120b",
            "kind": "recovered_history_answer",
            "tool_calls": 25,
            "tool_results": 25,
        },
    }

    assert _assistant_footer_items(message) == ["endpoint:ovh-provider / gpt-oss-120b"]


@pytest.mark.basic
def test_assistant_v2_footer_zero_tools_reports_zero_files() -> None:
    message = {
        "role": "assistant",
        "content": "Done.",
        "metadata": {
            "_assistant_stats": {
                "tool_calls": 0,
                "usage": {"input_tokens": 9, "output_tokens": 3, "total_tokens": 12},
            }
        },
    }

    assert _assistant_footer_items(message) == [
        "input : 9 tk",
        "output : 3 tk",
        "tools : 0",
        "files : 0",
    ]


@pytest.mark.basic
def test_assistant_v2_tool_calls_for_message_reads_scratchpad_fallback() -> None:
    message = {
        "role": "assistant",
        "content": "Done.",
        "metadata": {
            "run_id": "old-run",
            "_assistant_stats": {"tool_calls": 1},
            "scratchpad": {
                "cycles": [
                    {
                        "i": 1,
                        "tool_calls": [
                            {
                                "name": "fetch_url",
                                "call_id": "c1",
                                "arguments": {"url": "https://example.com"},
                            }
                        ],
                    }
                ]
            },
        },
    }

    assert _assistant_tool_calls_for_message(message)[0]["name"] == "fetch_url"


@pytest.mark.basic
def test_assistant_v2_message_card_renders_clickable_tools_metric() -> None:
    app = QApplication.instance() or QApplication([])
    opened: list[str] = []
    message = {
        "role": "assistant",
        "message_id": "m_tools",
        "content": "Done.",
        "metadata": {
            "_assistant_stats": {
                "tool_calls": 1,
                "tool_call_details": [
                    {"name": "execute_command", "arguments": {"command": "pwd"}}
                ],
            }
        },
    }
    card = MessageCard(
        message=message,
        message_key="id:m_tools",
        renderer=app_module.MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *_args, **_kwargs: None,
        bubble_width=360,
        on_show_tools=lambda _message: opened.append("tools"),
    )
    card.show()
    app.processEvents()

    buttons = [
        button
        for button in card.findChildren(app_module.QPushButton)
        if button.objectName() == "metricChip"
    ]
    assert len(buttons) == 1
    assert buttons[0].property("kind") == "tools"

    buttons[0].click()
    assert opened == ["tools"]


@pytest.mark.basic
def test_assistant_v2_message_card_renders_stats_line_with_separators() -> None:
    app = QApplication.instance() or QApplication([])
    message = {
        "role": "assistant",
        "message_id": "m_stats",
        "content": "Done.",
        "metadata": {
            "_assistant_stats": {
                "tool_calls": 1,
                "tool_call_details": [
                    {"name": "write_file", "arguments": {"file_path": "a.txt"}}
                ],
                "usage": {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16},
            }
        },
    }
    expected_segments = len(_assistant_footer_metrics(message))
    assert expected_segments == 4  # input, output, tools, files

    card = MessageCard(
        message=message,
        message_key="id:m_stats",
        renderer=app_module.MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *_args, **_kwargs: None,
        bubble_width=360,
        on_show_tools=lambda _message: None,
    )
    card.show()
    app.processEvents()

    segments = [
        widget
        for widget in card.findChildren(app_module.QLabel)
        + card.findChildren(app_module.QPushButton)
        if widget.objectName() == "metricChip"
    ]
    separators = [
        widget
        for widget in card.findChildren(app_module.QLabel)
        if widget.objectName() == "metricSeparator"
    ]
    assert len(segments) == expected_segments
    assert len(separators) == expected_segments - 1
    files_labels = [
        widget for widget in segments if widget.property("kind") == "files"
    ]
    assert len(files_labels) == 1
    assert files_labels[0].text() == "files : 1"
    assert "a.txt" in files_labels[0].toolTip()


@pytest.mark.basic
def test_assistant_v2_message_card_renders_clickable_files_metric() -> None:
    app = QApplication.instance() or QApplication([])
    opened: list[str] = []
    message = {
        "role": "assistant",
        "message_id": "m_files",
        "content": "Done.",
        "metadata": {
            "_assistant_stats": {
                "tool_calls": 1,
                "tool_call_details": [
                    {"name": "write_file", "arguments": {"file_path": "a.txt", "content": "x"}}
                ],
            }
        },
    }
    card = MessageCard(
        message=message,
        message_key="id:m_files",
        renderer=app_module.MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *_args, **_kwargs: None,
        bubble_width=360,
        on_show_tools=lambda _message: opened.append("tools"),
        on_show_files=lambda _message: opened.append("files"),
    )
    card.show()
    app.processEvents()

    buttons = {
        str(button.property("kind")): button
        for button in card.findChildren(app_module.QPushButton)
        if button.objectName() == "metricChip"
    }
    assert set(buttons) == {"tools", "files"}
    buttons["files"].click()
    assert opened == ["files"]


@pytest.mark.basic
def test_assistant_v2_file_activity_dialog_renders_one_card_per_operation() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = app_module.FileActivityDialog(
        message={
            "role": "assistant",
            "content": "Done.",
            "metadata": {
                "_assistant_stats": {
                    "tool_calls": 3,
                    "tool_call_details": [
                        {
                            "name": "write_file",
                            "arguments": {"file_path": "report.md", "content": "x"},
                        },
                        {
                            "name": "execute_command",
                            "arguments": {"command": "mv draft.md docs/draft.md && rm old.log"},
                        },
                    ],
                }
            },
        }
    )
    dialog.show()
    app.processEvents()

    cards = dialog.findChildren(app_module.QFrame, "toolApprovalCallCard")
    assert len(cards) == 3  # created report.md, moved draft.md, deleted old.log

    chips = [
        str(chip.text()).strip().upper()
        for chip in dialog.findChildren(app_module.QLabel, "usageStatusChip")
    ]
    assert chips == ["CREATED", "MOVED", "DELETED"]
    hint = dialog.findChildren(app_module.QLabel, "toolApprovalHint")[0].text()
    assert "3 files affected" in hint


@pytest.mark.basic
def test_assistant_v2_file_activity_dialog_empty_state_is_honest() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = app_module.FileActivityDialog(
        message={
            "role": "assistant",
            "content": "Done.",
            "metadata": {
                "_assistant_stats": {
                    "tool_calls": 1,
                    "tool_call_details": [
                        {"name": "web_search", "arguments": {"query": "abc"}}
                    ],
                }
            },
        }
    )
    dialog.show()
    app.processEvents()

    assert not dialog.findChildren(app_module.QFrame, "toolApprovalCallCard")
    hint = dialog.findChildren(app_module.QLabel, "toolApprovalHint")[0].text()
    assert "No files were created, modified, moved or deleted" in hint


@pytest.mark.basic
def test_assistant_v2_tool_card_shows_execution_outcome_chip() -> None:
    app = QApplication.instance() or QApplication([])
    card = app_module.ToolApprovalCallCard(
        call={
            "name": "edit_file",
            "arguments": {"file_path": "broken.py", "pattern": "x"},
            "success": False,
            "error": "pattern not found",
        },
        index=0,
    )
    card.show()
    app.processEvents()

    chips = [
        str(chip.text()).strip().upper()
        for chip in card.findChildren(app_module.QLabel, "usageStatusChip")
    ]
    assert chips == ["FAILED"]
    errors = card.findChildren(app_module.QLabel, "usageCardError")
    assert len(errors) == 1
    assert "pattern not found" in errors[0].text()


@pytest.mark.basic
def test_assistant_v2_user_message_card_has_copy_button() -> None:
    app = QApplication.instance() or QApplication([])
    card = MessageCard(
        message={"role": "user", "message_id": "u1", "content": "hello there"},
        message_key="id:u1",
        renderer=app_module.MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *_args, **_kwargs: None,
        bubble_width=320,
    )
    card.show()
    app.processEvents()

    buttons = [
        button
        for button in card.findChildren(app_module.QPushButton)
        if button.objectName() == "messageActionButton"
    ]
    assert len(buttons) == 1
    assert buttons[0].toolTip() == "Copy message"
    assert buttons[0].focusPolicy() == Qt.NoFocus


@pytest.mark.basic
def test_assistant_v2_tool_usage_dialog_renders_tool_cards() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = ToolUsageDialog(
        message={
            "role": "assistant",
            "content": "Done.",
            "metadata": {
                "_assistant_stats": {
                    "tool_calls": 2,
                    "tool_call_details": [
                        {"name": "execute_command", "arguments": {"command": "pwd"}},
                        {
                            "name": "web_search",
                            "arguments": {"query": "Genentech roles"},
                        },
                    ],
                }
            },
        }
    )
    dialog.show()
    app.processEvents()

    cards = dialog.findChildren(app_module.QFrame, "toolApprovalCallCard")
    assert len(cards) == 2


@pytest.mark.basic
def test_assistant_v2_tool_usage_dialog_renders_ledger_calls_without_metadata_details() -> (
    None
):
    app = QApplication.instance() or QApplication([])
    dialog = ToolUsageDialog(
        message={
            "role": "assistant",
            "content": "Done.",
            "metadata": {"run_id": "run-7", "_assistant_stats": {"tool_calls": 7}},
        },
        tool_calls=[
            {"name": f"tool_{index}", "arguments": {"index": index}, "run_id": "run-7"}
            for index in range(7)
        ],
        source="ledger",
        run_ids=["run-7"],
    )
    dialog.show()
    app.processEvents()

    cards = dialog.findChildren(app_module.QFrame, "toolApprovalCallCard")
    assert len(cards) == 7
    assert (
        "not attached"
        not in dialog.findChildren(app_module.QLabel, "toolApprovalHint")[0].text()
    )


@pytest.mark.basic
def test_assistant_v2_show_message_tools_fetches_ledger_before_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class _Controller:
        def tool_call_details_for_message(self, message):
            assert message["metadata"]["run_id"] == "run-7"
            return {
                "tool_calls": [
                    {"name": "web_search", "arguments": {"query": "Genentech"}}
                ],
                "source": "ledger",
                "run_ids": ["run-7"],
                "error": "",
            }

    class _Dialog:
        def __init__(self, **kwargs):
            captured["dialog_init"] = kwargs

        def set_loading(self):
            captured["loading"] = True

        def update_tool_usage(self, **kwargs):
            captured["updated"] = kwargs

        def exec_(self):
            captured["executed"] = True
            return 1

    class _Signal:
        def __init__(self):
            self._callbacks = []

        def connect(self, callback):
            self._callbacks.append(callback)

        def emit(self, *args):
            for callback in list(self._callbacks):
                callback(*args)

    class _Worker:
        def __init__(self, *, controller, message, parent=None):
            self.controller = controller
            self.message = message
            self.loaded = _Signal()
            self.failed = _Signal()
            self.finished = _Signal()

        def start(self):
            self.loaded.emit(
                self.controller.tool_call_details_for_message(self.message)
            )
            self.finished.emit()

        def deleteLater(self):
            captured["worker_deleted"] = True

    monkeypatch.setattr(app_module, "ToolUsageDialog", _Dialog)
    monkeypatch.setattr(app_module, "ToolUsageLookupWorker", _Worker)

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._controller = _Controller()
    AssistantPalette._show_message_tools(
        palette,
        {
            "role": "assistant",
            "content": "Done.",
            "metadata": {"run_id": "run-7", "_assistant_stats": {"tool_calls": 1}},
        },
    )

    assert captured["dialog_init"]["source"] == "metadata"
    assert captured["loading"] is True
    assert captured["updated"]["source"] == "ledger"
    assert captured["updated"]["tool_calls"][0]["name"] == "web_search"
    assert captured["executed"] is True
    assert captured["worker_deleted"] is True


@pytest.mark.basic
def test_assistant_v2_tool_call_summary_humanizes_large_write_file_payload() -> None:
    content = "<!DOCTYPE html>\n<html><body>Hello</body></html>" * 40
    summary = _tool_call_summary(
        {
            "name": "write_file",
            "arguments": {
                "filepath": "/tmp/fantasy-comic.html",
                "content": content,
            },
        }
    )

    assert summary.name == "write_file"
    assert summary.reason == "Create or replace `/tmp/fantasy-comic.html`."
    assert summary.parameters == [
        ("filepath", "/tmp/fantasy-comic.html"),
        ("content", f"HTML content, {len(content):,} chars"),
    ]
    assert summary.raw_text.startswith("write_file\n{")
    assert '"filepath": "/tmp/fantasy-comic.html"' in summary.raw_text


@pytest.mark.basic
def test_assistant_v2_tool_call_summary_parses_json_argument_text() -> None:
    summary = _tool_call_summary(
        {"name": "execute_command", "arguments": '{"cmd":"npm test","timeout":120}'}
    )

    assert summary.name == "execute_command"
    assert summary.reason == "Run `npm test`."
    assert ("cmd", "npm test") in summary.parameters
    assert ("timeout", "120") in summary.parameters


@pytest.mark.basic
def test_assistant_v2_visible_history_messages_prioritizes_latest_user_turn_while_busy() -> (
    None
):
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
                    {
                        "local_path": "/tmp/demo.wav",
                        "filename": "demo.wav",
                        "content_type": "audio/wav",
                    }
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
    assert _message_bubble_width(1000, role="user") == 800
    assert _message_bubble_width(1000, role="assistant") == 800


@pytest.mark.basic
def test_assistant_v2_message_media_artifacts_collects_and_deduplicates_media() -> None:
    message = {
        "role": "assistant",
        "content": "Here is the diagram.",
        "metadata": {
            "image_artifact": {
                "$artifact": "img_1",
                "filename": "diagram.png",
                "content_type": "image/png",
            },
            "generated_media": {
                "image_artifact": {
                    "$artifact": "img_1",
                    "filename": "diagram.png",
                    "content_type": "image/png",
                },
                "audio_artifact": {
                    "$artifact": "aud_1",
                    "filename": "voice.wav",
                    "content_type": "audio/wav",
                },
            },
        },
    }

    artifacts = _message_media_artifacts(message)

    assert [item.get("$artifact") for item in artifacts] == ["img_1", "aud_1"]


@pytest.mark.basic
def test_assistant_v2_local_attachment_preview_items_tag_media_modalities() -> None:
    items = _local_attachment_preview_items(
        ["/tmp/example.png", "/tmp/example.mp3", "/tmp/readme.txt"]
    )

    assert items == [
        {
            "local_path": "/tmp/example.png",
            "filename": "example.png",
            "modality": "image",
        },
        {
            "local_path": "/tmp/example.mp3",
            "filename": "example.mp3",
            "modality": "audio",
        },
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
def test_assistant_v2_merge_attachment_paths_deduplicates_and_filters_non_files(
    tmp_path: Path,
) -> None:
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
def test_assistant_v2_media_display_title_hides_hash_like_audio_names(
    tmp_path: Path,
) -> None:
    path = tmp_path / "artifact.wav"
    path.write_bytes(b"RIFF0000WAVE")

    assert (
        _media_display_title(
            title="be73678943931c9e88eb1fe57dffac05", kind="audio", path=path
        )
        == "Audio"
    )
    assert (
        _media_display_title(title="briefing.wav", kind="audio", path=path)
        == "briefing.wav"
    )


@pytest.mark.basic
def test_assistant_v2_controller_artifact_cache_filename_uses_runtime_content_type_override() -> (
    None
):
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
def test_assistant_v2_capture_history_scroll_request_preserves_top_visible_message_offset() -> (
    None
):
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
    palette.history_layout = _Layout(
        [
            _Widget("user-1", 20, 120),
            _Widget("assistant-1", 160, 140),
            _Widget("assistant-2", 320, 140),
        ]
    )

    request = AssistantPalette._capture_history_scroll_request(palette)

    assert request == HistoryScrollRequest(
        mode="preserve", message_key="assistant-1", offset=22
    )


@pytest.mark.basic
def test_assistant_v2_default_history_refresh_request_uses_bottom_for_first_hydration() -> (
    None
):
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._history_cards_by_key = {}
    palette._latest_visible_message_key = lambda role="": "assistant-2"
    palette._capture_history_scroll_request = lambda: HistoryScrollRequest(
        mode="preserve",
        message_key="assistant-1",
        offset=18,
    )

    request = AssistantPalette._default_history_refresh_request(palette)

    assert request == HistoryScrollRequest(mode="bottom", message_key="", offset=0)


@pytest.mark.basic
def test_assistant_v2_commit_history_scroll_request_defers_bottom_mode_while_hidden() -> (
    None
):
    class _Timer:
        def __init__(self) -> None:
            self.stop_calls = 0

        def stop(self) -> None:
            self.stop_calls += 1

    events: list[str] = []
    request = HistoryScrollRequest(mode="bottom")

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._history_settle_timer = _Timer()
    palette._pending_history_scroll = HistoryScrollRequest()
    palette._deferred_history_scroll_on_show = HistoryScrollRequest()
    palette.isVisible = lambda: False
    palette._schedule_history_scroll_apply = lambda: events.append("schedule")

    AssistantPalette._commit_history_scroll_request(palette, request)

    assert palette._history_settle_timer.stop_calls == 1
    assert palette._pending_history_scroll == request
    assert palette._deferred_history_scroll_on_show == request
    assert events == []


@pytest.mark.basic
def test_assistant_v2_restore_deferred_history_scroll_on_show_replays_saved_request() -> (
    None
):
    events: list[HistoryScrollRequest] = []
    request = HistoryScrollRequest(mode="bottom")

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._deferred_history_scroll_on_show = request
    palette._commit_history_scroll_request = lambda value: events.append(value)

    AssistantPalette._restore_deferred_history_scroll_on_show(palette)

    assert events == [request]
    assert palette._deferred_history_scroll_on_show == HistoryScrollRequest()


@pytest.mark.basic
def test_assistant_v2_apply_history_scroll_request_anchors_message_top_and_bottom_modes() -> (
    None
):
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
def test_assistant_v2_message_voice_synthesizing_click_pauses_stream_without_history_refresh() -> (
    None
):
    class _Voice:
        def __init__(self) -> None:
            self.pause_calls = 0

        def pause(self) -> bool:
            self.pause_calls += 1
            return True

    class _Card:
        def __init__(self) -> None:
            self.states: list[str] = []

        def set_voice_state(self, state: str) -> None:
            self.states.append(state)

    voice = _Voice()
    card = _Card()
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._controller = SimpleNamespace(voice_manager=voice)
    palette._active_spoken_message_key = "id:m1"
    palette._active_spoken_message_phase = "synthesizing"
    palette._history_cards_by_key = {"id:m1": card}
    palette.refresh_history = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("history refreshed")
    )

    AssistantPalette._toggle_message_voice(
        palette, {"role": "assistant", "message_id": "m1", "content": "hello"}
    )

    assert voice.pause_calls == 1
    assert palette._active_spoken_message_phase == "paused"
    assert card.states == ["paused"]


@pytest.mark.basic
def test_assistant_v2_message_voice_pause_resume_updates_card_without_history_refresh() -> (
    None
):
    class _Voice:
        def __init__(self) -> None:
            self.pause_calls = 0
            self.resume_calls = 0

        def is_paused(self) -> bool:
            return False

        def is_speaking(self) -> bool:
            return True

        def pause(self) -> bool:
            self.pause_calls += 1
            return True

        def resume(self) -> bool:
            self.resume_calls += 1
            return True

    class _Card:
        def __init__(self) -> None:
            self.states: list[str] = []

        def set_voice_state(self, state: str) -> None:
            self.states.append(state)

    voice = _Voice()
    card = _Card()
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._controller = SimpleNamespace(voice_manager=voice)
    palette._active_spoken_message_key = "id:m1"
    palette._active_spoken_message_phase = "speaking"
    palette._history_cards_by_key = {"id:m1": card}
    palette.refresh_history = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("history refreshed")
    )

    message = {"role": "assistant", "message_id": "m1", "content": "hello"}
    AssistantPalette._toggle_message_voice(palette, message)
    assert voice.pause_calls == 1
    assert palette._active_spoken_message_phase == "paused"
    assert card.states == ["paused"]

    AssistantPalette._toggle_message_voice(palette, message)
    assert voice.resume_calls == 1
    assert palette._active_spoken_message_phase == "speaking"
    assert card.states == ["paused", "speaking"]


@pytest.mark.basic
def test_assistant_v2_message_voice_start_and_finish_do_not_rebuild_history() -> None:
    class _Voice:
        def __init__(self) -> None:
            self.stopped = 0
            self.spoken: list[str] = []

        def is_paused(self) -> bool:
            return False

        def is_speaking(self) -> bool:
            return False

        def stop_speaking(self) -> None:
            self.stopped += 1

        def speak(self, text: str, callback=None) -> bool:
            self.spoken.append(text)
            return True

    class _Card:
        def __init__(self) -> None:
            self.states: list[str] = []

        def set_voice_state(self, state: str) -> None:
            self.states.append(state)

    voice = _Voice()
    old_card = _Card()
    new_card = _Card()
    palette = AssistantPalette.__new__(AssistantPalette)
    palette._controller = SimpleNamespace(voice_manager=voice)
    palette._active_spoken_message_key = "id:old"
    palette._active_spoken_message_phase = "speaking"
    palette._history_cards_by_key = {"id:old": old_card, "id:new": new_card}
    palette.refresh_history = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("history refreshed")
    )

    message = {"role": "assistant", "message_id": "new", "content": "hello again"}
    AssistantPalette._toggle_message_voice(palette, message)
    assert voice.stopped == 1
    assert voice.spoken == ["hello again"]
    assert old_card.states == ["idle"]
    assert new_card.states == ["synthesizing"]

    AssistantPalette._on_message_speech_started(palette, "id:new")
    AssistantPalette._on_message_speech_finished(palette, "id:new")
    assert new_card.states == ["synthesizing", "speaking", "idle"]


@pytest.mark.basic
def test_assistant_v2_message_action_buttons_do_not_take_focus() -> None:
    app = QApplication.instance() or QApplication([])
    card = MessageCard(
        message={"role": "assistant", "message_id": "m1", "content": "hello"},
        message_key="id:m1",
        renderer=app_module.MarkdownRenderer(theme="friendly_grayscale"),
        on_open_artifact=lambda *_args, **_kwargs: None,
        bubble_width=320,
        on_toggle_voice=lambda _message: None,
        voice_state="idle",
    )
    card.show()
    app.processEvents()

    buttons = [
        button
        for button in card.findChildren(app_module.QPushButton)
        if button.objectName() == "messageActionButton"
    ]
    assert len(buttons) == 2
    assert all(button.focusPolicy() == Qt.NoFocus for button in buttons)


@pytest.mark.basic
def test_assistant_v2_prompt_up_down_jump_at_text_edges() -> None:
    app = QApplication.instance() or QApplication([])
    editor = AttachmentTextEdit()
    editor.resize(260, 80)
    editor.setPlainText("alpha\nbeta\ngamma")
    editor.show()
    app.processEvents()

    cursor = editor.textCursor()
    cursor.setPosition(len("alpha\nbe"))
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key_Up)
    assert 0 < editor.textCursor().position() < len("alpha\nbeta")

    cursor = editor.textCursor()
    cursor.setPosition(len("alp"))
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key_Up)
    assert editor.textCursor().position() == 0

    cursor = editor.textCursor()
    cursor.setPosition(len("alpha\nbeta\nga"))
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key_Down)
    assert editor.textCursor().position() == len("alpha\nbeta\ngamma")


@pytest.mark.basic
def test_assistant_v2_prompt_edge_navigation_accepts_keypad_modifier() -> None:
    app = QApplication.instance() or QApplication([])
    editor = AttachmentTextEdit()
    editor.setPlainText("alpha\nbeta")
    editor.show()
    app.processEvents()

    cursor = editor.textCursor()
    cursor.setPosition(len("alp"))
    editor.setTextCursor(cursor)
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.KeypadModifier)
    QApplication.sendEvent(editor, event)

    assert event.isAccepted()
    assert editor.textCursor().position() == 0


@pytest.mark.basic
def test_assistant_v2_prompt_edge_navigation_uses_displayed_wrapped_lines() -> None:
    app = QApplication.instance() or QApplication([])
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    editor = AttachmentTextEdit()
    editor.resize(260, 80)
    editor.setLineWrapMode(AttachmentTextEdit.WidgetWidth)
    editor.setPlainText(text)
    editor.show()
    app.processEvents()

    cursor = editor.textCursor()
    cursor.setPosition(3)
    editor.setTextCursor(cursor)
    probe = QTextCursor(cursor)
    assert probe.movePosition(QTextCursor.Down)
    QTest.keyClick(editor, Qt.Key_Up)
    assert editor.textCursor().position() == 0

    cursor = editor.textCursor()
    cursor.setPosition(len(text) - 5)
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key_Down)
    assert editor.textCursor().position() == len(text)


@pytest.mark.basic
def test_assistant_v2_prompt_edge_navigation_uses_visible_viewport_edges() -> None:
    app = QApplication.instance() or QApplication([])
    text = "\n".join(f"line {index}" for index in range(12))
    editor = AttachmentTextEdit()
    editor.resize(260, 38)
    editor.setFixedHeight(38)
    editor.setPlainText(text)
    editor.show()
    app.processEvents()

    def move_cursor_to_line(line: str) -> None:
        cursor = editor.textCursor()
        cursor.setPosition(text.index(line) + 2)
        editor.setTextCursor(cursor)
        app.processEvents()

    def align_cursor(edge: str) -> None:
        viewport = editor.viewport().rect()
        rect = editor.cursorRect(editor.textCursor())
        delta = (
            rect.top() - viewport.top()
            if edge == "top"
            else rect.bottom() - viewport.bottom()
        )
        bar = editor.verticalScrollBar()
        bar.setValue(bar.value() + delta)
        app.processEvents()

    move_cursor_to_line("line 6")
    align_cursor("top")
    viewport = editor.viewport().rect()
    probe = QTextCursor(editor.textCursor())
    assert probe.movePosition(QTextCursor.Up)
    assert editor.cursorRect(probe).center().y() < viewport.top()
    QTest.keyClick(editor, Qt.Key_Up)
    assert editor.textCursor().position() == 0

    move_cursor_to_line("line 6")
    align_cursor("bottom")
    viewport = editor.viewport().rect()
    probe = QTextCursor(editor.textCursor())
    assert probe.movePosition(QTextCursor.Down)
    assert editor.cursorRect(probe).center().y() > viewport.bottom()
    QTest.keyClick(editor, Qt.Key_Down)
    assert editor.textCursor().position() == len(text)


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
def test_assistant_v2_extracts_mermaid_blocks_as_dedicated_preview_segments() -> None:
    content = (
        "Intro text.\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "    A[Observe] --> B[Think]\n"
        "    B --> C[Act]\n"
        "```\n\n"
        "Outro text."
    )

    blocks, actions = _assistant_content_blocks(content)

    assert actions == []
    assert [str(block.get("kind") or "") for block in blocks] == [
        "markdown",
        "mermaid",
        "markdown",
    ]
    assert "Intro text." in str(blocks[0].get("text") or "")
    assert "flowchart LR" in str(blocks[1].get("text") or "")
    assert str(blocks[1].get("data_uri") or "").startswith("data:image/png;base64,")
    assert "Outro text." in str(blocks[2].get("text") or "")


@pytest.mark.basic
def test_assistant_v2_keeps_unsupported_mermaid_dialects_in_markdown() -> None:
    content = "```mermaid\n" "sequenceDiagram\n" "    Alice->>Bob: Hello\n" "```\n"

    blocks, actions = _assistant_content_blocks(content)

    assert actions == []
    assert len(blocks) == 1
    assert str(blocks[0].get("kind") or "") == "markdown"
    assert "sequenceDiagram" in str(blocks[0].get("text") or "")


@pytest.mark.basic
def test_assistant_v2_tray_activation_opens_palette_on_primary_click() -> None:
    events: list[str] = []

    class _Palette:
        def show_palette(self) -> None:
            events.append("show")

    class _Menu:
        def popup(self, _pos) -> None:
            events.append("menu")

    _handle_tray_activation(
        palette=_Palette(), menu=_Menu(), reason=QSystemTrayIcon.Trigger
    )

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

    _handle_tray_activation(
        palette=_Palette(), menu=_Menu(), reason=QSystemTrayIcon.Context
    )

    assert events == ["menu"]


class _GatewayWorkerStub:
    def __init__(self) -> None:
        self.start_run_calls: list[dict] = []

    def list_bundles(self) -> dict:
        raise AssertionError(
            "tenant catalog workflow selection should not resolve through private bundles"
        )

    def session_prompt_cache_prepare(self, **kwargs) -> dict:
        raise AssertionError(
            "gateway worker must not negotiate prompt cache from the desktop client"
        )

    def start_run(self, **kwargs) -> str:
        self.start_run_calls.append(dict(kwargs))
        return "run_1"

    def get_run(self, *, run_id: str) -> dict:
        return {"status": "running", "waiting": None}

    def get_run_input_data(self, *, run_id: str) -> dict:
        return {"input_data": {"prompt": "Hello from v2"}}

    def get_run_history_bundle(self, **kwargs) -> dict:
        return {"root_run_id": "run_1", "session": {"turns": []}, "ledgers": {}}


class _LLMManagerStub:
    def __init__(self, gateway: _GatewayWorkerStub) -> None:
        self._gateway = gateway
        self.active_session_id = "session-1"
        self.messages: list[dict] = []
        self.last_run_id = ""

    def gateway_client(self):
        return self._gateway

    def append_message(
        self, *, role: str, content: str, metadata=None, ts: str = ""
    ) -> None:
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
def test_gateway_worker_starts_runs_with_catalog_scope_and_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _GatewayWorkerStub()
    llm_manager = _LLMManagerStub(gateway)

    def _no_follow(
        self, *, root_run_id, on_record, should_stop, on_offline=None, on_online=None
    ) -> None:
        return None

    monkeypatch.setattr(
        "abstractassistant.ui.gateway_worker.GatewayRunController.follow_run",
        _no_follow,
    )

    worker = GatewayWorker(
        llm_manager=llm_manager,
        user_text="Hello from v2",
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
                    "messages": [],
                },
                "use_context": False,
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


@pytest.mark.basic
def test_assistant_v2_cycle_event_updates_inline_status() -> None:
    """Adapter cycle events (llm_call STARTED on the reason node) surface as a live
    'Thinking — cycle N' line (2026-07-10 run visibility)."""
    status_calls: list[tuple[str, str]] = []

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._set_history_status = lambda text="", tone="neutral": status_calls.append((text, tone))

    AssistantPalette._on_worker_event(palette, {"type": "cycle", "iteration": 3})

    assert status_calls == [("Thinking — cycle 3", "busy")]


@pytest.mark.basic
def test_assistant_v2_tool_started_event_updates_inline_status() -> None:
    """Adapter tool_started events (tool_calls STARTED, pre-execution) surface the
    launch with an args preview — previously only tool results were visible."""
    status_calls: list[tuple[str, str]] = []

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._set_history_status = lambda text="", tone="neutral": status_calls.append((text, tone))

    AssistantPalette._on_worker_event(
        palette,
        {
            "type": "tool_started",
            "tools": [{"name": "read_file", "arguments_preview": "{'file_path': 'README.md'}"}],
        },
    )

    assert status_calls == [("Tool: read_file {'file_path': 'README.md'}", "busy")]


@pytest.mark.basic
def test_assistant_v2_submit_steers_active_run_instead_of_refusing() -> None:
    """Typed text while a run is active becomes durable steering (inject_guidance),
    is echoed into the transcript, and never starts a second worker."""
    injected: list[tuple[str, str]] = []
    appended: list[tuple[str, dict]] = []
    status_calls: list[tuple[str, str]] = []
    refreshed: list[bool] = []

    class _Controller:
        @staticmethod
        def last_run_id() -> str:
            return "run-active"

        @staticmethod
        def inject_guidance(run_id: str, guidance: str) -> bool:
            injected.append((run_id, guidance))
            return True

        @staticmethod
        def append_user_message(content: str, metadata=None) -> None:
            appended.append((content, dict(metadata or {})))

    class _PromptEdit:
        def __init__(self) -> None:
            self._text = "focus on the event bus instead"
            self.cleared = False

        def toPlainText(self) -> str:  # noqa: N802 (Qt naming)
            return self._text

        def clear(self) -> None:
            self._text = ""
            self.cleared = True

    class _LiveWorker:
        @staticmethod
        def isRunning() -> bool:  # noqa: N802 (Qt naming)
            return True

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._worker = _LiveWorker()  # a run is in progress
    palette._controller = _Controller()
    palette.prompt_edit = _PromptEdit()
    palette.refresh_history = lambda request=None: refreshed.append(True)
    palette._history_scroll_request = lambda mode="bottom", **kw: None
    palette._set_status = lambda text, tone="neutral": status_calls.append((text, tone))
    palette._set_history_status = lambda text="", tone="neutral": status_calls.append((text, tone))

    AssistantPalette._submit(palette)

    assert injected == [("run-active", "focus on the event bus instead")]
    assert palette.prompt_edit.cleared is True
    assert appended and appended[0][0] == "focus on the event bus instead"
    assert appended[0][1].get("kind") == "operator_guidance"
    assert ("Steering: focus on the event bus instead", "busy") in status_calls


@pytest.mark.basic
def test_assistant_v2_controller_run_control_commands() -> None:
    """Controller pause/resume/inject_guidance submit durable gateway commands."""
    from abstractassistantv2.controller import AssistantV2Controller

    submitted: list[dict] = []

    class _Gateway:
        @staticmethod
        def submit_command(*, command: dict) -> dict:
            submitted.append(dict(command))
            return {"ok": True}

    controller = AssistantV2Controller.__new__(AssistantV2Controller)
    controller.gateway = _Gateway()

    assert controller.pause_run("r1") is True
    assert controller.resume_run("r1") is True
    assert controller.inject_guidance("r1", "check the tests too") is True
    assert controller.inject_guidance("r1", "   ") is False  # empty guidance refused
    assert controller.pause_run("") is False

    assert [c["type"] for c in submitted] == ["pause", "resume", "inject_guidance"]
    assert all(c["run_id"] == "r1" for c in submitted)
    assert submitted[2]["payload"] == {"guidance": "check the tests too"}


class _PromptEditStub:
    def __init__(self, text: str = "") -> None:
        self._text = text
        self.cleared = False

    def toPlainText(self) -> str:  # noqa: N802 (Qt naming)
        return self._text

    def clear(self) -> None:
        self._text = ""
        self.cleared = True


@pytest.mark.basic
def test_assistant_v2_submit_during_stop_teardown_queues_instead_of_steering() -> None:
    """After Stop, the follower lingers until its next SSE window. A send in that
    window must NOT steer the cancelled run (the message would vanish — the
    2026-07-10 'sent it again but never saw an answer' bug); it queues and the
    composer keeps the text."""
    steered: list[str] = []
    status_calls: list[tuple[str, str]] = []

    class _LiveWorker:
        @staticmethod
        def isRunning() -> bool:  # noqa: N802 (Qt naming)
            return True

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._worker = _LiveWorker()
    palette._cancel_requested = True  # user clicked Stop
    palette.prompt_edit = _PromptEditStub("same question again")
    palette._steer_active_run = lambda: steered.append("steered")
    palette._set_history_status = lambda text="", tone="neutral": status_calls.append((text, tone))

    AssistantPalette._submit(palette)

    assert steered == []
    assert palette._pending_submit is True
    assert palette.prompt_edit.cleared is False  # text preserved for the queued send
    assert any("will send in a moment" in text for text, _tone in status_calls)


@pytest.mark.basic
def test_assistant_v2_submit_clears_stale_finished_worker() -> None:
    """A worker whose thread already finished must not block or misroute the next
    send: the stale reference is cleared and the submit proceeds afresh."""

    class _FinishedWorker:
        @staticmethod
        def isRunning() -> bool:  # noqa: N802 (Qt naming)
            return False

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._worker = _FinishedWorker()
    palette._cancel_requested = False
    # Empty composer: the fresh-submit path returns right after the guard,
    # which is exactly the surface under test here.
    palette.prompt_edit = _PromptEditStub("")
    palette._attachments = []

    AssistantPalette._submit(palette)

    assert palette._worker is None
    assert palette._pending_submit is False


@pytest.mark.basic
def test_assistant_v2_stop_restores_send_button_and_marks_teardown() -> None:
    """Stopping hands the Send button back immediately (the user stopped on
    purpose and expects to relaunch) and marks the teardown window."""
    cancelled: list[str] = []
    busy_calls: list[bool] = []
    status_calls: list[tuple[str, str]] = []

    class _Controller:
        @staticmethod
        def cancel_run(run_id: str) -> bool:
            cancelled.append(run_id)
            return True

        @staticmethod
        def last_run_id() -> str:
            return "run-active"

    class _Worker:
        def requestInterruption(self) -> None:  # noqa: N802 (Qt naming)
            pass

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._controller = _Controller()
    palette._worker = _Worker()
    palette._set_send_button_busy = lambda busy: busy_calls.append(bool(busy))
    palette._set_status = lambda text, tone="neutral": status_calls.append((text, tone))
    palette._set_history_status = lambda text="", tone="neutral": status_calls.append((text, tone))

    AssistantPalette._cancel_active_run(palette)

    assert cancelled == ["run-active"]
    assert palette._cancel_requested is True
    assert busy_calls == [False]  # Send icon restored right away


@pytest.mark.basic
def test_assistant_v2_worker_finished_after_stop_reports_run_stopped() -> None:
    """A user-stopped run has no final answer by design: the finish banner must
    say 'Run stopped.' instead of the misleading no-written-reply diagnostic."""
    status_calls: list[tuple[str, str]] = []

    palette = AssistantPalette.__new__(AssistantPalette)
    palette._worker = object()
    palette._run_busy = True
    palette._cancel_requested = True
    palette._run_has_final_output = False
    palette._show_thinking_indicator = lambda: False
    palette._set_send_button_busy = lambda busy: None
    palette._set_history_status = lambda text="", tone="neutral": status_calls.append((text, tone))
    palette._refresh_tray_feedback = lambda: None
    palette.refresh_history = lambda request=None: None
    palette._set_status = lambda text, tone="neutral": None

    AssistantPalette._on_worker_finished(palette)

    assert palette._worker is None
    assert palette._cancel_requested is False
    assert ("Run stopped.", "info") in status_calls
