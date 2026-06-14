"""Gateway-facing contract helpers for AbstractAssistant v2."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from .assistant_workflow import (
    ASSISTANT_INTERFACE,
    MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
    MANAGED_ASSISTANT_WORKFLOW_MARKER,
    MANAGED_ASSISTANT_WORKFLOW_NAME,
    normalized_managed_visualflow,
)


ROUTE_ORDER = [
    "input.text",
    "input.image",
    "input.video",
    "input.voice",
    "input.sound",
    "input.music",
    "output.text",
    "output.image.text_to_image",
    "output.image.image_to_image",
    "output.image.image_upscale",
    "output.video.text_to_video",
    "output.video.image_to_video",
    "output.voice",
    "output.sound",
    "output.music",
]


@dataclass(frozen=True)
class CapabilityRouteRow:
    key: str
    label: str
    kind: str
    modality: str
    task: str
    provider: str = ""
    model: str = ""
    base_url: str = ""
    options: Dict[str, Any] = field(default_factory=dict)
    configured: bool = False
    read_only: bool = False
    overrideable: bool = False
    covered_by: str = ""
    derived_from: str = ""
    source: str = ""
    package_hint: str = ""
    description: str = ""


@dataclass(frozen=True)
class WorkflowOption:
    bundle_id: str
    flow_id: str
    label: str
    registry_scope: str = "tenant_catalog"
    bundle_version: str = ""
    description: str = ""
    is_default: bool = False


@dataclass(frozen=True)
class WorkflowCatalogStatus:
    source: str = "tenant_catalog"
    error: str = ""


@dataclass(frozen=True)
class ChoiceItem:
    id: str
    label: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteCatalogSpec:
    key: str
    label: str
    description: str
    mode: str
    capability_route: str = ""
    task: str = ""
    supports_options: bool = True


ROUTE_SPECS: Dict[str, RouteCatalogSpec] = {
    "input.text": RouteCatalogSpec("input.text", "Main Chat Model", "Default text understanding and response model.", "text", capability_route="output.text"),
    "input.image": RouteCatalogSpec("input.image", "Image Understanding", "Fallback route for image input when the text model is not vision-capable.", "text", capability_route="input.image,output.text"),
    "input.video": RouteCatalogSpec("input.video", "Video Understanding", "Fallback route for video input when the text model cannot handle frames/video directly.", "text", capability_route="input.video,output.text"),
    "input.voice": RouteCatalogSpec("input.voice", "Speech To Text", "Speech transcription route for microphone and audio note input.", "stt"),
    "input.sound": RouteCatalogSpec("input.sound", "Sound Understanding", "Non-speech audio understanding route.", "text", capability_route="input.sound,output.text"),
    "input.music": RouteCatalogSpec("input.music", "Music Understanding", "Music-audio understanding route.", "text", capability_route="input.music,output.text"),
    "output.text": RouteCatalogSpec("output.text", "Text Output", "Read-only view derived from input.text.", "text", capability_route="output.text"),
    "output.image.text_to_image": RouteCatalogSpec("output.image.text_to_image", "Image Generation", "Direct text-to-image route used by the assistant's Image mode.", "vision", task="text_to_image"),
    "output.image.image_to_image": RouteCatalogSpec("output.image.image_to_image", "Image Edit", "Direct image-edit route used by Edit mode.", "vision", task="image_to_image"),
    "output.image.image_upscale": RouteCatalogSpec("output.image.image_upscale", "Image Upscale", "Direct restore/upscale route used by Upscale mode.", "vision", task="image_upscale"),
    "output.video.text_to_video": RouteCatalogSpec("output.video.text_to_video", "Video Generation", "Direct text-to-video route used by Video mode.", "vision", task="text_to_video"),
    "output.video.image_to_video": RouteCatalogSpec("output.video.image_to_video", "Image To Video", "Direct image-to-video route used by Image→Video mode.", "vision", task="image_to_video"),
    "output.voice": RouteCatalogSpec("output.voice", "Text To Speech", "Voice output for speaking assistant replies aloud.", "tts"),
    "output.sound": RouteCatalogSpec("output.sound", "Sound Generation", "Direct sound-effects generation route.", "music", task="text_to_audio"),
    "output.music": RouteCatalogSpec("output.music", "Music Generation", "Direct music generation route.", "music", task="text_to_music"),
}


def _row_sort_key(row: CapabilityRouteRow) -> int:
    try:
        return ROUTE_ORDER.index(row.key)
    except ValueError:
        return len(ROUTE_ORDER) + 1


def _clean_label(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _version_sort_key(value: str) -> tuple[int, ...]:
    text = str(value or "").strip()
    if not text:
        return (0,)
    parts: list[int] = []
    for raw in text.split("."):
        raw_s = str(raw).strip()
        if raw_s.isdigit():
            parts.append(int(raw_s))
            continue
        digits = "".join(ch for ch in raw_s if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def _choice(value: Any, *, fallback_id: str = "", fallback_label: str = "") -> Optional[ChoiceItem]:
    if isinstance(value, str):
        text = value.strip()
        return ChoiceItem(id=text, label=text) if text else None
    if not isinstance(value, dict):
        return None
    item_id = str(
        value.get("id")
        or value.get("provider")
        or value.get("name")
        or value.get("model")
        or value.get("voice_id")
        or fallback_id
        or ""
    ).strip()
    if not item_id:
        return None
    label = _clean_label(
        value.get("label")
        or value.get("display_name")
        or value.get("title")
        or value.get("model")
        or value.get("voice_id"),
        fallback_label or item_id,
    )
    return ChoiceItem(id=item_id, label=label, meta=dict(value))


def _dedupe(items: Iterable[ChoiceItem]) -> List[ChoiceItem]:
    out: List[ChoiceItem] = []
    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        out.append(item)
    return out


class AssistantGatewayService:
    def __init__(self, gateway_client: Any) -> None:
        self._gateway = gateway_client
        self._last_workflow_status = WorkflowCatalogStatus()

    def describe_connection_issue(self, exc: Exception) -> str:
        return self._describe_gateway_exception(exc)

    def list_capability_routes(self) -> List[CapabilityRouteRow]:
        payload = self._gateway.get_capability_defaults()
        routes = payload.get("routes") if isinstance(payload, dict) else None
        rows: List[CapabilityRouteRow] = []
        if isinstance(routes, list):
            for raw in routes:
                row = self._parse_route_row(raw)
                if row is not None:
                    rows.append(row)
        rows.sort(key=_row_sort_key)
        return rows

    def route_map(self) -> Dict[str, CapabilityRouteRow]:
        return {row.key: row for row in self.list_capability_routes()}

    def save_route_default(
        self,
        *,
        route_key: str,
        provider: str,
        model: str,
        base_url: str = "",
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._gateway.set_capability_default(
            route_key=route_key,
            provider=provider,
            model=model,
            base_url=base_url or None,
            options=options or {},
        )

    def clear_route_default(self, *, route_key: str) -> Dict[str, Any]:
        return self._gateway.clear_capability_default(route_key=route_key)

    def list_workflows(self) -> List[WorkflowOption]:
        try:
            options = self.ensure_catalog_workflow()
        except Exception as exc:
            detail = self._describe_gateway_exception(exc)
            self._last_workflow_status = WorkflowCatalogStatus(source="tenant_catalog", error=detail)
            return []
        resolved, error = self._resolve_runnable_workflows(options)
        if resolved:
            self._last_workflow_status = WorkflowCatalogStatus(source="tenant_catalog", error="")
            return resolved
        detail = error or self._blocking_gateway_issue() or "No published AbstractAssistant workflow is available in the gateway catalog."
        self._last_workflow_status = WorkflowCatalogStatus(source="tenant_catalog", error=detail)
        return []

    def workflow_status(self) -> WorkflowCatalogStatus:
        return self._last_workflow_status

    def ensure_catalog_workflow(self) -> List[WorkflowOption]:
        options, _error = self._catalog_workflows()
        managed_options = self._managed_catalog_options(options)
        if managed_options:
            return managed_options
        payload = normalized_managed_visualflow()
        flows = self._gateway.list_visualflows()
        target = self._find_managed_visualflow(flows)

        changed = False
        if target is None:
            created = self._gateway.create_visualflow(
                name=str(payload.get("name") or ""),
                description=str(payload.get("description") or ""),
                interfaces=list(payload.get("interfaces") or []),
                nodes=list(payload.get("nodes") or []),
                edges=list(payload.get("edges") or []),
                entry_node=str(payload.get("entryNode") or ""),
            )
            target = dict(created) if isinstance(created, dict) else None
            changed = True
        elif target is not None and self._visualflow_needs_update(target, payload):
            updated = self._gateway.update_visualflow(
                flow_id=str(target.get("id") or ""),
                name=str(payload.get("name") or ""),
                description=str(payload.get("description") or ""),
                interfaces=list(payload.get("interfaces") or []),
                nodes=list(payload.get("nodes") or []),
                edges=list(payload.get("edges") or []),
                entry_node=str(payload.get("entryNode") or ""),
            )
            target = dict(updated) if isinstance(updated, dict) else target
            changed = True

        flow_id = str((target or {}).get("id") or "").strip()
        if not flow_id:
            raise RuntimeError("Assistant workflow reconciliation returned no flow id.")

        bundle_version = self._latest_bundle_version(MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID)
        if changed or not bundle_version:
            published = self._gateway.publish_visualflow(
                flow_id=flow_id,
                bundle_id=MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                overwrite=False,
                reload_gateway=True,
            )
            bundle_version = str((published or {}).get("bundle_version") or "").strip() or bundle_version
        if not bundle_version:
            raise RuntimeError("Assistant workflow publish returned no bundle_version.")
        self._gateway.promote_workflow_catalog_bundle(
            bundle_id=MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
            bundle_version=bundle_version,
            scope="tenant_catalog",
            make_default=False,
        )
        options, error = self._catalog_workflows()
        managed_options = self._managed_catalog_options(options)
        if not managed_options:
            raise RuntimeError(error or "Gateway catalog promotion completed but the assistant workflow is still unavailable.")
        return managed_options

    def provider_choices(self, *, route_key: str, base_url: str = "") -> List[ChoiceItem]:
        spec = ROUTE_SPECS[route_key]
        if spec.mode == "text":
            payload = self._gateway.discovery_providers(include_models=False)
            items = payload.get("items") if isinstance(payload, dict) else []
            providers = [_choice(item, fallback_id=str(item.get("id") or item.get("name") or "")) for item in items or [] if isinstance(item, dict)]
            return _dedupe([item for item in providers if item is not None])
        if spec.mode == "tts":
            payload = self._gateway.voice_voices(providers_only=True, compact=True, base_url=base_url or None)
            items = self._provider_items_from_catalog(payload, preferred_keys=("items", "voices", "profiles", "tts_providers", "providers", "available_providers"))
            return _dedupe(items)
        if spec.mode == "stt":
            payload = self._gateway.audio_transcription_models(providers_only=True, base_url=base_url or None)
            items = self._provider_items_from_catalog(payload, preferred_keys=("items", "stt_providers", "providers", "available_providers"))
            return _dedupe(items)
        if spec.mode == "music":
            payload = self._gateway.audio_music_providers(task=spec.task, base_url=base_url or None)
            items = self._provider_items_from_catalog(payload, preferred_keys=("items", "music_providers", "providers", "available_providers", "provider_details"))
            return _dedupe(items)
        if spec.mode == "vision":
            payload = self._gateway.vision_provider_models(task=spec.task, providers_only=True, base_url=base_url or None)
            items = self._provider_items_from_catalog(payload, preferred_keys=("items", "providers", "available_providers", "provider_details"))
            return _dedupe(items)
        return []

    def model_choices(self, *, route_key: str, provider: str, base_url: str = "") -> List[ChoiceItem]:
        provider_s = str(provider or "").strip()
        if not provider_s:
            return []
        spec = ROUTE_SPECS[route_key]
        if spec.mode == "text":
            payload = self._gateway.discovery_provider_models(
                provider_name=provider_s,
                capability_route=spec.capability_route,
                base_url=base_url or None,
            )
            return _dedupe(self._model_items_from_catalog(payload, provider=provider_s))
        if spec.mode == "tts":
            payload = self._gateway.audio_speech_models(provider=provider_s, base_url=base_url or None)
            return _dedupe(self._model_items_from_catalog(payload, provider=provider_s))
        if spec.mode == "stt":
            payload = self._gateway.audio_transcription_models(provider=provider_s, base_url=base_url or None)
            return _dedupe(self._model_items_from_catalog(payload, provider=provider_s))
        if spec.mode == "music":
            payload = self._gateway.audio_music_models(task=spec.task, provider=provider_s, base_url=base_url or None)
            return _dedupe(self._model_items_from_catalog(payload, provider=provider_s))
        if spec.mode == "vision":
            payload = self._gateway.vision_provider_models(task=spec.task, provider=provider_s, base_url=base_url or None)
            return _dedupe(self._model_items_from_catalog(payload, provider=provider_s))
        return []

    def voice_choices(self, *, provider: str, model: str, base_url: str = "") -> List[ChoiceItem]:
        provider_s = str(provider or "").strip()
        model_s = str(model or "").strip()
        if not provider_s or not model_s:
            return []
        payload = self._gateway.voice_voices(
            provider=provider_s,
            model=model_s,
            compact=True,
            base_url=base_url or None,
        )
        items: List[ChoiceItem] = []
        for key in ("profiles", "voices", "cloned_voices", "items"):
            value = payload.get(key) if isinstance(payload, dict) else None
            if not isinstance(value, list):
                continue
            for item in value:
                choice = _choice(item)
                if choice is not None:
                    items.append(choice)
        return _dedupe(items)

    def _catalog_workflows(self) -> tuple[List[WorkflowOption], str]:
        try:
            payload = self._gateway.workflow_catalog(scope="tenant_catalog")
        except Exception as exc:
            return [], str(exc)
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return [], "Gateway workflow catalog response was invalid."
        options: List[WorkflowOption] = []
        for record in items:
            if not isinstance(record, dict):
                continue
            actions = record.get("actions")
            if isinstance(actions, dict) and actions.get("can_run") is False:
                continue
            bundle_id = str(record.get("bundle_id") or "").strip()
            bundle_version = str(record.get("bundle_version") or "").strip()
            if not bundle_id or not bundle_version:
                continue
            default_entrypoint = str(record.get("default_entrypoint") or "").strip()
            entrypoints = record.get("entrypoints") if isinstance(record.get("entrypoints"), list) else []
            for entry in entrypoints:
                if not isinstance(entry, dict):
                    continue
                interfaces = entry.get("interfaces")
                entry_interfaces = [str(item).strip() for item in interfaces if isinstance(item, str) and str(item).strip()] if isinstance(interfaces, list) else []
                if not entry_interfaces:
                    record_interfaces = record.get("interfaces")
                    if isinstance(record_interfaces, list):
                        entry_interfaces = [str(item).strip() for item in record_interfaces if isinstance(item, str) and str(item).strip()]
                if ASSISTANT_INTERFACE not in entry_interfaces:
                    continue
                flow_id = str(entry.get("flow_id") or "").strip()
                if not flow_id:
                    continue
                name = str(entry.get("name") or "").strip() or flow_id
                label = name
                options.append(
                    WorkflowOption(
                        bundle_id=bundle_id,
                        flow_id=flow_id,
                        label=label,
                        registry_scope="tenant_catalog",
                        bundle_version=bundle_version,
                        description=str(entry.get("description") or record.get("status_reason") or "").strip(),
                        is_default=bool(record.get("is_default")) and flow_id == default_entrypoint,
                    )
                )
        options.sort(key=lambda option: (_version_sort_key(option.bundle_version), option.label), reverse=True)
        return options, ""

    def _managed_catalog_options(self, options: Iterable[WorkflowOption]) -> List[WorkflowOption]:
        target = MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
        return [
            option
            for option in options
            if isinstance(option, WorkflowOption) and str(option.bundle_id or "").strip() == target
        ]

    def _resolve_runnable_workflows(self, options: List[WorkflowOption]) -> tuple[List[WorkflowOption], str]:
        if not options:
            return [], ""
        defaults = [option for option in options if bool(option.is_default)]
        if len(defaults) == 1:
            return [defaults[0]], ""
        if len(defaults) > 1:
            return [], "Gateway catalog exposes multiple default assistant workflows. Publish exactly one default assistant workflow."
        if len(options) == 1:
            return [options[0]], ""
        return [], "Gateway catalog must expose exactly one default assistant workflow for AbstractAssistant."

    def _blocking_gateway_issue(self) -> str:
        gateway_me = getattr(self._gateway, "gateway_me", None)
        if not callable(gateway_me):
            return ""
        try:
            payload = gateway_me()
        except Exception as exc:
            return self._describe_gateway_exception(exc)
        if isinstance(payload, dict) and payload.get("ok") is False:
            detail = str(payload.get("detail") or "Gateway connection failed.").strip()
            return detail
        return ""

    def _describe_gateway_exception(self, exc: Exception) -> str:
        status = int(getattr(exc, "status", 0) or 0)
        if status in {401, 403}:
            return "Gateway authentication failed. Check the bearer token or sign-in session."

        base_url = self._gateway_base_url()
        schema = self._openapi_document()
        if isinstance(schema, dict):
            paths = schema.get("paths") if isinstance(schema.get("paths"), dict) else {}
            has_gateway_routes = any(str(path).startswith("/api/gateway/") for path in paths)
            title = str((schema.get("info") or {}).get("title") or "").strip().lower()
            if not has_gateway_routes:
                if title == "openai endpoint" or "/v1/models" in paths:
                    if self._is_loopback_url(base_url):
                        return (
                            f"{base_url} is serving an OpenAI-compatible endpoint, not AbstractGateway. "
                            "Another local process is likely intercepting this port. Stop that service "
                            "or point the assistant at the real Gateway address."
                        )
                    return (
                        f"{base_url} is serving an OpenAI-compatible endpoint, not AbstractGateway. "
                        "Point the assistant at a Gateway URL that exposes /api/gateway/*."
                    )
                return (
                    f"{base_url} does not expose the AbstractGateway control-plane routes under /api/gateway/*."
                )

        detail = str(exc or "Gateway connection failed.").strip()
        return detail or "Gateway connection failed."

    def _openapi_document(self) -> Dict[str, Any]:
        fn = getattr(self._gateway, "openapi_document", None)
        if not callable(fn):
            return {}
        try:
            payload = fn()
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _gateway_base_url(self) -> str:
        config = getattr(self._gateway, "config", None)
        base_url = str(getattr(config, "base_url", "") or "").strip().rstrip("/")
        return base_url or "the configured gateway URL"

    def _latest_bundle_version(self, bundle_id: str) -> str:
        payload = self._gateway.list_bundles()
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return ""
        target = str(bundle_id or "").strip()
        versions = [
            str(item.get("bundle_version") or "").strip()
            for item in items
            if isinstance(item, dict) and str(item.get("bundle_id") or "").strip() == target and str(item.get("bundle_version") or "").strip()
        ]
        if not versions:
            return ""
        return sorted(versions, key=_version_sort_key, reverse=True)[0]

    def _find_managed_visualflow(self, flows: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(flows, list):
            return None
        for item in flows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            if name == MANAGED_ASSISTANT_WORKFLOW_NAME:
                return dict(item)
            if MANAGED_ASSISTANT_WORKFLOW_MARKER in description:
                return dict(item)
        return None

    def _visualflow_needs_update(self, current: Dict[str, Any], expected: Dict[str, Any]) -> bool:
        keys = ("name", "description", "interfaces", "nodes", "edges", "entryNode")
        current_norm = {key: current.get(key) for key in keys}
        expected_norm = {key: expected.get(key) for key in keys}
        try:
            current_text = json.dumps(current_norm, sort_keys=True, ensure_ascii=False)
            expected_text = json.dumps(expected_norm, sort_keys=True, ensure_ascii=False)
            return current_text != expected_text
        except Exception:
            return current_norm != expected_norm

    def _is_loopback_url(self, base_url: str) -> bool:
        host = str(urlparse(str(base_url or "")).hostname or "").strip().lower()
        return host in {"127.0.0.1", "localhost", "::1"}

    def _parse_route_row(self, raw: Any) -> Optional[CapabilityRouteRow]:
        if not isinstance(raw, dict):
            return None
        key = str(raw.get("key") or "").strip()
        if not key:
            return None
        spec = ROUTE_SPECS.get(key)
        parts = [part.strip() for part in key.split(".") if part.strip()]
        kind = parts[0] if len(parts) >= 1 else ""
        modality = parts[1] if len(parts) >= 2 else ""
        task = parts[2] if len(parts) >= 3 else ""
        return CapabilityRouteRow(
            key=key,
            label=str((spec.label if spec is not None else raw.get("label")) or raw.get("label") or key).strip() or key,
            kind=str(raw.get("kind") or kind).strip(),
            modality=str(raw.get("modality") or modality).strip(),
            task=task,
            provider=str(raw.get("provider") or "").strip(),
            model=str(raw.get("model") or "").strip(),
            base_url=str(raw.get("base_url") or "").strip(),
            options=dict(raw.get("options")) if isinstance(raw.get("options"), dict) else {},
            configured=bool(raw.get("configured")),
            read_only=bool(raw.get("read_only")),
            overrideable=bool(raw.get("overrideable")),
            covered_by=str(raw.get("covered_by") or "").strip(),
            derived_from=str(raw.get("derived_from") or "").strip(),
            source=str(raw.get("source") or "").strip(),
            package_hint=str(raw.get("package_hint") or "").strip(),
            description=spec.description if spec else "",
        )

    def _provider_items_from_catalog(self, payload: Dict[str, Any], *, preferred_keys: Iterable[str]) -> List[ChoiceItem]:
        items: List[ChoiceItem] = []
        for key in preferred_keys:
            value = payload.get(key) if isinstance(payload, dict) else None
            if isinstance(value, list):
                for item in value:
                    choice = _choice(item)
                    if choice is not None:
                        items.append(choice)
            elif isinstance(value, dict):
                for provider_id in value.keys():
                    choice = _choice(str(provider_id))
                    if choice is not None:
                        items.append(choice)
        return items

    def _model_items_from_catalog(self, payload: Dict[str, Any], *, provider: str) -> List[ChoiceItem]:
        items: List[ChoiceItem] = []
        if not isinstance(payload, dict):
            return items
        direct_items = payload.get("items")
        if isinstance(direct_items, list):
            for item in direct_items:
                choice = _choice(item)
                if choice is not None:
                    items.append(choice)
        for key in ("models", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    choice = _choice(item, fallback_id=str(item), fallback_label=str(item))
                    if choice is not None:
                        items.append(choice)
        for key in ("provider_models", "tts_models", "stt_models", "music_models"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    choice = _choice(item, fallback_id=str(item), fallback_label=str(item))
                    if choice is not None:
                        items.append(choice)
        for key in ("models_by_provider", "tts_models_by_provider", "stt_models_by_provider", "music_models_by_provider"):
            value = payload.get(key)
            if isinstance(value, dict):
                provider_models = value.get(provider)
                if isinstance(provider_models, list):
                    for item in provider_models:
                        choice = _choice(item, fallback_id=str(item), fallback_label=str(item))
                        if choice is not None:
                            items.append(choice)
        return items
