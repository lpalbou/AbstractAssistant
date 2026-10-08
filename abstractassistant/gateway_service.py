"""Gateway-facing contract helpers for AbstractAssistant."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import warnings
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from .assistant_workflow import (
    ASSISTANT_INTERFACE,
    MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
    MANAGED_ASSISTANT_WORKFLOW_MARKER,
    MANAGED_ASSISTANT_WORKFLOW_NAME,
    MANAGED_ASSISTANT_WORKFLOW_REVISION,
    managed_workflow_revision_of,
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
    # The gateway's served one-line hint for this route (AbstractCore `route_hint.sentence`,
    # e.g. speech input on Apple silicon: mlx-whisper runs the model on the GPU). Shown
    # verbatim; never computed or applied here.
    hint: str = ""


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
class GatewayDefaultWorkflow:
    """What the gateway reports as its default workflow for the assistant
    interface (contract D, ``default_agent_workflows`` on /workflow-catalog).

    ``reported`` is False when the gateway's envelope has no
    ``default_agent_workflows`` at all (a gateway older than contract D);
    ``available`` is False when it has one but no default for this interface —
    the assistant then runs its built-in orchestrator (amendment A-4).
    """

    reported: bool = False
    available: bool = False
    workflow_id: str = ""
    bundle_id: str = ""
    bundle_version: str = ""
    flow_id: str = ""
    registry_scope: str = ""
    name: str = ""
    source: str = ""
    reason: str = ""


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


def _next_patch_version(known_versions: Iterable[str]) -> str:
    """Next patch after the highest known version ('' when none are known —
    the gateway then mints its own first version)."""
    candidates = [str(v or "").strip() for v in known_versions]
    candidates = [v for v in candidates if v]
    if not candidates:
        return ""
    highest = max(candidates, key=_version_sort_key)
    parts = highest.split(".")
    last = parts[-1].strip()
    digits = "".join(ch for ch in last if ch.isdigit())
    if not digits:
        return f"{highest}.1"
    bumped = str(int(digits) + 1)
    parts[-1] = last.replace(digits, bumped, 1) if last != digits else bumped
    return ".".join(parts)


# A gateway that is asked to publish WITHOUT a version mints "0.0.0" for the
# first one; for the app's own orchestrator that number means "no version of
# ours", so it is never shown (E2E N4) and never requested.
FIRST_MANAGED_WORKFLOW_VERSION = "0.0.1"
_PLACEHOLDER_VERSIONS = frozenset({"", "0.0.0"})


def executable_contract_problem(payload: Any, interface: str) -> str:
    """Why ``payload`` is not a ``GET /bundles?executable_for=<interface>``
    answer, or "" when it is. Mirrors the kit's parseExecutableWorkflows():
    the echo, ``owner``/``shipped`` on every item, and every listed entrypoint
    declaring the interface (otherwise the gateway ignored the parameter)."""
    if not isinstance(payload, dict):
        return "The gateway's workflow list was not a JSON object."
    echoed = str(payload.get("executable_for") or "").strip()
    if echoed != interface:
        if echoed:
            return f"The gateway listed workflows for {echoed}, not {interface}."
        return "This gateway does not filter workflows per app (no executable_for in its answer): update the gateway."
    items = payload.get("items")
    if not isinstance(items, list):
        return "The gateway's workflow list has no items."
    for record in items:
        if not isinstance(record, dict) or not str(record.get("bundle_id") or "").strip():
            return "The gateway listed a workflow without a bundle id."
        bundle_id = str(record.get("bundle_id")).strip()
        owner = record.get("owner")
        if not isinstance(owner, dict) or owner.get("kind") not in ("gateway", "user"):
            return f"The gateway did not say who owns {bundle_id} (owner missing): update the gateway."
        if not isinstance(record.get("shipped"), bool):
            return f"The gateway did not say whether {bundle_id} ships with it (shipped missing): update the gateway."
        for entry in record.get("entrypoints") or []:
            if not isinstance(entry, dict):
                return f"The gateway listed an invalid entrypoint for {bundle_id}."
            interfaces = entry.get("interfaces") if isinstance(entry.get("interfaces"), list) else []
            if interface not in [str(i).strip() for i in interfaces]:
                flow_id = str(entry.get("flow_id") or "").strip()
                return f"The gateway offered {bundle_id}:{flow_id}, which does not declare {interface}: update the gateway."
    return ""


def workflow_version_suffix(bundle_id: str, version: str, *, named_built_in: bool = False) -> str:
    """The version part of a workflow label: `` @1.2.3`` for a real version.

    The built-in orchestrator without a real published version (none yet, or
    the gateway's placeholder ``0.0.0``) reads `` (built-in)`` — or nothing
    when the label already says "Built-in orchestrator" — never a fake number.
    """
    text = str(version or "").strip()
    managed = str(bundle_id or "").strip() == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID
    if managed and text in _PLACEHOLDER_VERSIONS:
        return "" if named_built_in else " (built-in)"
    return f" @{text}" if text else ""


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
        # Definition-drift reconciliation runs at most once per process: the
        # comparison needs a visualflow fetch, and a store that rewrites flows
        # on save must not cause a publish loop (each reconcile mints a new
        # bundle patch version).
        self._managed_flow_reconciled = False
        self._gateway_default = GatewayDefaultWorkflow()
        self._last_catalog_options: List[WorkflowOption] = []

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
            # Keeps the built-in orchestrator published; the selector then
            # offers EVERY assistant-interface workflow of the catalog it read.
            self.ensure_catalog_workflow()
            options = list(self._last_catalog_options)
        except Exception as exc:
            detail = self._describe_gateway_exception(exc)
            self._last_workflow_status = WorkflowCatalogStatus(source="tenant_catalog", error=detail)
            # Publishing the built-in failed, but the catalog was read: its
            # other workflows (and the gateway default) stay usable, and the
            # controller names this error if nothing else can run.
            return self._runnable_workflows(list(self._last_catalog_options))
        resolved = self._runnable_workflows(options)
        if resolved:
            self._last_workflow_status = WorkflowCatalogStatus(source="tenant_catalog", error="")
            return resolved
        detail = self._blocking_gateway_issue() or "No published AbstractAssistant workflow is available in the gateway catalog."
        self._last_workflow_status = WorkflowCatalogStatus(source="tenant_catalog", error=detail)
        return []

    def workflow_status(self) -> WorkflowCatalogStatus:
        return self._last_workflow_status

    def gateway_default_workflow(self) -> GatewayDefaultWorkflow:
        """The gateway's default for the assistant interface, as last read
        with the catalog (``list_workflows`` refreshes it)."""
        return self._gateway_default

    @staticmethod
    def is_managed_option(option: Any) -> bool:
        return str(getattr(option, "bundle_id", "") or "").strip() == MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID

    def ensure_catalog_workflow(self) -> List[WorkflowOption]:
        options, _error = self._catalog_workflows()
        managed_options = self._managed_catalog_options(options)
        if managed_options and self._managed_flow_reconciled:
            return managed_options
        if managed_options:
            # The catalog serves a managed workflow, but its DEFINITION may be
            # older than this app build (the old short-circuit here silently
            # froze the published flow forever — pin/edge changes shipped in
            # the app never reached the gateway). Reconcile once per process:
            # compare the stored visualflow against this build's definition
            # and republish + promote when they differ. A MISSING stored flow
            # is recreated (it is this app's own managed artifact and the
            # source for every future publish; live case: the 2026-07-17
            # principal-split left catalogs serving bundles whose source flow
            # no longer exists in the current principal's store) — after the
            # one recreate the store compares clean, so this cannot loop.
            self._managed_flow_reconciled = True
            try:
                payload = normalized_managed_visualflow()
                flows = self._gateway.list_visualflows()
                target = self._find_managed_visualflow(flows)
                if target is not None and self._stored_workflow_is_newer(target):
                    return managed_options
                if target is not None and not self._visualflow_needs_update(target, payload):
                    # Stored flow is current. One crash shape remains: a
                    # publish landed in the bundle registry but the promote
                    # never reached the catalog — recover by promoting the
                    # newer registry version.
                    registry_version = self._latest_bundle_version(MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID)
                    catalog_versions = [
                        str(getattr(option, "bundle_version", "") or "") for option in managed_options
                    ]
                    catalog_max = max(catalog_versions, key=_version_sort_key) if catalog_versions else ""
                    if registry_version and _version_sort_key(registry_version) > _version_sort_key(catalog_max):
                        self._gateway.promote_workflow_catalog_bundle(
                            bundle_id=MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                            bundle_version=registry_version,
                            scope="tenant_catalog",
                            make_default=False,
                        )
                        options, error = self._catalog_workflows()
                        refreshed = self._managed_catalog_options(options)
                        if refreshed:
                            return refreshed
                    return managed_options
            except Exception as exc:
                warnings.warn(f"#FALLBACK: managed workflow drift check failed; keeping catalog version: {exc}")
                return managed_options
            # Definition drifted or the stored flow is missing: fall through
            # to the create/update + publish + promote path below.
        payload = normalized_managed_visualflow()
        flows = self._gateway.list_visualflows()
        target = self._find_managed_visualflow(flows)
        self._managed_flow_reconciled = True

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
            # The gateway auto-bumps from ITS bundle registry only — which can
            # lag the tenant CATALOG (live case: the registry lost the 0.0.1
            # artifact while the catalog still records 0.0.1 with its sha, so
            # an auto-bumped publish re-minted 0.0.1 and the promote refused
            # "already exists with a different sha256"). Bump from every
            # version we can SEE: registry + catalog.
            known_versions = [bundle_version] + [
                str(getattr(option, "bundle_version", "") or "")
                for option in self._managed_catalog_options(options)
            ]
            # Always an explicit version: left to the gateway, the first one
            # is minted as the placeholder "0.0.0".
            next_version = _next_patch_version(known_versions) or FIRST_MANAGED_WORKFLOW_VERSION
            published = self._gateway.publish_visualflow(
                flow_id=flow_id,
                bundle_id=MANAGED_ASSISTANT_WORKFLOW_BUNDLE_ID,
                bundle_version=next_version or None,
                overwrite=False,
                reload_gateway=True,
            )
            bundle_version = str((published or {}).get("bundle_version") or "").strip() or next_version or bundle_version
        if not bundle_version:
            raise RuntimeError("Assistant workflow publish returned no bundle_version.")
        # make_default=False (2026-09-25): WHICH workflow is the default is
        # the gateway operator's setting (`agents.default_workflow`), never
        # something this app claims on launch. The app still publishes its
        # built-in orchestrator so it exists, and runs its LATEST version
        # (see `_runnable_workflows`), so no default flag is needed for that.
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
        """The workflows this app can run for the signed-in person, as the
        GATEWAY lists them: ``GET /bundles?executable_for=abstractassistant.agent.v1``
        (operator 2026-10-01 — the admin decides what is available to users,
        users also see their own; no client-side "show all" or interface filter).
        A gateway that does not honour the contract is an error, never a list."""
        # Never serve a previous read's options when this one fails.
        self._last_catalog_options = []
        try:
            payload = self._gateway.executable_bundles(ASSISTANT_INTERFACE)
        except Exception as exc:
            return [], str(exc)
        problem = executable_contract_problem(payload, ASSISTANT_INTERFACE)
        if problem:
            return [], problem
        self._gateway_default = self._parse_gateway_default(payload)
        options: List[WorkflowOption] = []
        self._last_catalog_options = options
        for record in payload["items"]:
            bundle_id = str(record.get("bundle_id") or "").strip()
            bundle_version = str(record.get("bundle_version") or "").strip()
            if not bundle_id or not bundle_version:
                continue
            for entry in record.get("entrypoints") or []:
                flow_id = str(entry.get("flow_id") or "").strip()
                if not flow_id:
                    continue
                name = str(entry.get("name") or "").strip() or flow_id
                options.append(
                    WorkflowOption(
                        bundle_id=bundle_id,
                        flow_id=flow_id,
                        label=name,
                        registry_scope=str(record.get("registry_scope") or "private").strip() or "private",
                        bundle_version=bundle_version,
                        description=str(entry.get("description") or record.get("description") or "").strip(),
                        is_default=bool(entry.get("is_agent_default")),
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

    @staticmethod
    def _parse_gateway_default(payload: Any) -> GatewayDefaultWorkflow:
        if not isinstance(payload, dict) or "default_agent_workflows" not in payload:
            return GatewayDefaultWorkflow(reported=False)
        table = payload.get("default_agent_workflows")
        entry = table.get(ASSISTANT_INTERFACE) if isinstance(table, dict) else None
        if not isinstance(entry, dict):
            # The gateway lists interfaces it cannot resolve, with the reason,
            # in a separate map (amendment A-4).
            missing = payload.get("default_agent_workflows_unavailable")
            why = missing.get(ASSISTANT_INTERFACE) if isinstance(missing, dict) else None
            why = why if isinstance(why, dict) else {}
            return GatewayDefaultWorkflow(
                reported=True,
                available=False,
                source=str(why.get("source") or "").strip(),
                reason=str(why.get("reason") or "").strip(),
            )
        bundle_id = str(entry.get("bundle_id") or "").strip()
        flow_id = str(entry.get("flow_id") or "").strip()
        available = entry.get("available")
        is_available = bool(bundle_id and flow_id) and available is not False
        return GatewayDefaultWorkflow(
            reported=True,
            available=is_available,
            workflow_id=str(entry.get("workflow_id") or "").strip(),
            bundle_id=bundle_id,
            bundle_version=str(entry.get("bundle_version") or "").strip(),
            flow_id=flow_id,
            registry_scope=str(entry.get("registry_scope") or "").strip(),
            name=str(entry.get("name") or "").strip(),
            # Shown verbatim (flag / stored / env / default — amendment A-4).
            source=str(entry.get("source") or "").strip(),
            reason=str(entry.get("reason") or "").strip(),
        )

    def _runnable_workflows(self, options: List[WorkflowOption]) -> List[WorkflowOption]:
        """Every assistant-interface workflow, ONE row per (bundle, flow) at its
        latest version: the built-in orchestrator first, then the rest by name.

        The catalog keeps every published version; the selector offers each
        workflow once and a run uses its newest version. (Until 2026-09-25 this
        insisted on exactly one catalog default, which the app then claimed
        for itself on every republish.)
        """
        latest: Dict[tuple, WorkflowOption] = {}
        for option in options:
            key = (option.bundle_id, option.flow_id)
            known = latest.get(key)
            if known is None or _version_sort_key(option.bundle_version) > _version_sort_key(known.bundle_version):
                latest[key] = option
        rows = list(latest.values())
        rows.sort(key=lambda o: (0 if self.is_managed_option(o) else 1, o.label.lower(), o.bundle_id, o.flow_id))
        return rows

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

    def _stored_workflow_is_newer(self, stored: Dict[str, Any]) -> bool:
        """True when the gateway already serves a NEWER managed workflow than this build.

        Never downgrade it: see `MANAGED_ASSISTANT_WORKFLOW_REVISION` for the measured
        cost of two builds each "correcting" the other. The newer workflow is a superset
        of what this build knows how to drive, so it is simply used.
        """
        stored_revision = managed_workflow_revision_of(stored)
        if stored_revision <= MANAGED_ASSISTANT_WORKFLOW_REVISION:
            return False
        warnings.warn(
            f"#FALLBACK: the gateway serves a newer AbstractAssistant workflow (revision "
            f"{stored_revision}) than this build ships ({MANAGED_ASSISTANT_WORKFLOW_REVISION}); "
            f"using it as it is instead of republishing an older one."
        )
        return True

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
            hint=str((raw.get("route_hint") or {}).get("sentence") or "").strip()
            if isinstance(raw.get("route_hint"), dict)
            else "",
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
