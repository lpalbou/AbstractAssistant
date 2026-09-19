"""Non-UI controller for the AbstractAssistant tray shell."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
import re
import threading
import time
import warnings
from typing import Any, Dict, List, Optional

from abstractassistant.config import Config, DEFAULT_GATEWAY_URL
from abstractassistant.core.tool_policy import ToolApprovalPolicy
from abstractassistant.core.gateway_voice_manager import GatewayVoiceManager
from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.gateway import GatewayClient, GatewayClientConfig, session_memory_run_id
from abstractassistant.gateway.run_input import MEDIA_OVERRIDE_INPUT_KEYS
from abstractassistant.gateway.tool_usage import (
    extract_sub_run_ids_from_record,
    extract_tool_call_details_from_ledger_items,
    extract_tool_call_details_from_scratchpad,
    ledger_record_from_item,
)
from abstractassistant.ui.gateway_worker import GatewayWorker

from .gateway_service import AssistantGatewayService, CapabilityRouteRow, WorkflowCatalogStatus, WorkflowOption
from .preferences import (
    AssistantPreferences,
    GatewayConnectionPreferences,
    GatewayConnectionStore,
    LOCAL_OVERRIDE_ROUTE_KEYS,
    PreferencesStore,
    REASONING_EFFORT_LEVELS,
    WORKSPACE_ACCESS_MODES,
    WorkflowSelection,
)


class AssistantController:
    def __init__(self, config: Optional[Config] = None, *, data_dir: Optional[Path] = None, debug: bool = False) -> None:
        self.config = config or Config.default()
        self.debug = bool(debug)
        self.data_dir = Path(data_dir).expanduser() if data_dir is not None else (Path.home() / ".abstractassistant")
        self.connection_store = GatewayConnectionStore(self.data_dir / "gateway_connection.json")
        self.connection = self._load_connection_preferences()
        self._apply_connection_to_config(self.connection)
        self.llm_manager = LLMManager(config=self.config, debug=self.debug, data_dir=self.data_dir)
        gateway = self.llm_manager.gateway_client()
        if gateway is None:
            raise RuntimeError("AbstractAssistant requires gateway mode")
        self.gateway = gateway
        self.gateway_service = AssistantGatewayService(gateway)
        self.preferences_store = PreferencesStore(Path(self.llm_manager.data_dir) / "preferences.json")
        self.preferences = self.preferences_store.load()
        self.voice_manager = GatewayVoiceManager(llm_manager=self.llm_manager, debug_mode=self.debug)
        self.voice_manager.set_voice_mode("wait")
        self.voice_manager.set_quality_preset(getattr(self.preferences, "voice_quality", "standard"))
        self.voice_manager.set_output_device(getattr(self.preferences, "audio_output_device", ""))
        self._session_auto_approve_all: set[str] = set()
        # Short-lived caches so the send path and startup don't re-fetch the
        # workflow catalog + tool inventory on the GUI thread every time
        # (each was up to a 30s blocking round trip). Invalidated explicitly on
        # connection/route/tool-preference changes; warmed by prefetch().
        # An epoch counter guards against an in-flight fetch storing a result
        # that a concurrent invalidate() (e.g. a gateway switch) already
        # obsoleted.
        self._cache_ttl_s = 20.0
        self._cache_epoch = 0
        self._workflow_cache: Optional[List[WorkflowOption]] = None
        self._workflow_cache_at = 0.0
        self._tool_inventory_cache: Optional[Dict[str, Any]] = None
        self._tool_inventory_cache_at = 0.0
        self._workspace_policy_cache: Optional[Dict[str, Any]] = None
        self._workspace_policy_cache_at = 0.0
        self._model_capabilities_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self._route_map_cache: Optional[Dict[str, CapabilityRouteRow]] = None
        self._route_map_cache_at = 0.0
        self._cache_lock = threading.RLock()
        # The gateway voice-default sync does a blocking capability-defaults
        # GET; it runs in prefetch() (off the GUI thread), not in __init__.

    def _cache_fresh(self, at: float) -> bool:
        return bool(at) and (time.monotonic() - float(at)) < self._cache_ttl_s

    def settings_caches_warm(self) -> bool:
        """True when every gateway-backed answer the Settings window reads on
        open is cached and fresh, so building it cannot block the GUI thread."""
        try:
            if self._workspace_policy_cache is None or not self._cache_fresh(self._workspace_policy_cache_at):
                return False
            if self._tool_inventory_cache is None or not self._cache_fresh(self._tool_inventory_cache_at):
                return False
            cache = getattr(self, "_route_map_cache", None)
            cache_at = float(getattr(self, "_route_map_cache_at", 0.0) or 0.0)
            return bool(cache) and self._cache_fresh(cache_at)
        except Exception:
            return False

    def warm_settings_caches(self) -> None:
        """Fetch (off the GUI thread) what the Settings window shows on open."""
        for name in ("workspace_policy", "tool_inventory"):
            try:
                getattr(self, name)()
            except Exception:
                pass
        try:
            self.route_map()
        except Exception:
            pass
        try:
            route = self.effective_chat_route() or {}
            model = str(route.get("model") or "").strip()
            if model:
                self.model_capabilities(model)
        except Exception:
            pass

    def gateway_is_local(self) -> bool:
        """Does the gateway run on this machine? Folder pickers only make sense
        then: paths are resolved on the gateway's host."""
        try:
            from urllib.parse import urlsplit

            host = str(urlsplit(str(self.connection.base_url or "")).hostname or "").strip().lower()
        except Exception:
            return False
        return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"} or host.startswith("127.")

    @staticmethod
    def _copy_inventory(inventory: Dict[str, Any]) -> Dict[str, Any]:
        # Return a defensive copy so a caller cannot mutate the cached object.
        result = dict(inventory or {})
        items = result.get("items")
        if isinstance(items, list):
            result["items"] = [dict(item) if isinstance(item, dict) else item for item in items]
        return result

    def invalidate_caches(self) -> None:
        """Drop the workflow + tool caches (call after any change that could
        move the catalog, tool inventory, or gateway connection)."""
        with self._cache_lock:
            self._cache_epoch += 1
            self._workflow_cache = None
            self._workflow_cache_at = 0.0
            self._tool_inventory_cache = None
            self._tool_inventory_cache_at = 0.0
            self._workspace_policy_cache = None
            self._workspace_policy_cache_at = 0.0
            self._model_capabilities_cache = {}
            self._route_map_cache = None
            self._route_map_cache_at = 0.0

    def prefetch(self) -> None:
        """Warm the workflow/tool/capabilities caches off the GUI thread.

        Safe to call from a background thread: pure network + cache writes,
        no Qt. Best-effort — failures leave the caches cold and the on-demand
        path fetches later.
        """
        try:
            self.workflow_options()
        except Exception:
            pass
        try:
            self.tool_inventory()
        except Exception:
            pass
        try:
            self.llm_manager.gateway_capabilities(force=True)
        except Exception:
            pass
        try:
            self._sync_gateway_voice_defaults()
        except Exception:
            pass

    @property
    def active_session_id(self) -> str:
        return str(self.llm_manager.active_session_id or "").strip()

    def session_run_id(self) -> str:
        return session_memory_run_id(self.active_session_id)

    def workflow_options(self) -> List[WorkflowOption]:
        with self._cache_lock:
            if self._workflow_cache is not None and self._cache_fresh(self._workflow_cache_at):
                return list(self._workflow_cache)
            epoch = self._cache_epoch
        options = self.gateway_service.list_workflows()
        # Never negatively-cache an empty list: list_workflows() returns [] on a
        # transient failure, and caching that would suppress runs for the TTL.
        if options:
            with self._cache_lock:
                if epoch == self._cache_epoch:
                    self._workflow_cache = list(options)
                    self._workflow_cache_at = time.monotonic()
        return list(options)

    def workflow_status(self) -> WorkflowCatalogStatus:
        return self.gateway_service.workflow_status()

    def current_workflow(self) -> Optional[WorkflowSelection]:
        options = self.workflow_options()
        if not options:
            return None
        return self._workflow_selection_from_option(options[0])

    def save_preferences(self, prefs: AssistantPreferences) -> None:
        self.preferences = prefs
        self.preferences_store.save(prefs)
        try:
            self.voice_manager.set_quality_preset(getattr(prefs, "voice_quality", "standard"))
        except Exception:
            pass
        try:
            self.voice_manager.set_output_device(getattr(prefs, "audio_output_device", ""))
        except Exception:
            pass

    def _copy_preferences(self, **updates: Any) -> AssistantPreferences:
        payload = self.preferences.to_dict()
        payload.update(updates)
        return AssistantPreferences.from_dict(payload)

    def update_preferences(self, **updates: Any) -> AssistantPreferences:
        """Persist a partial preferences change, keeping every other field.

        Every settings surface must go through here (or ``save_preferences``
        with a full object): rebuilding ``AssistantPreferences`` by hand from a
        subset of fields silently wipes the fields that were left out — the
        auto-speak header toggle used to drop the model/voice overrides that way.
        """
        prefs = self._copy_preferences(**updates)
        self.save_preferences(prefs)
        return prefs

    # ------------------------------------------------------------------ run scope

    def run_scope(self) -> Dict[str, Any]:
        """Per-run pins: reasoning effort and the workspace grant.

        The workspace root is the user's chosen folder when one is saved; else
        the folder the gateway gave this SESSION's first run (remembered by the
        worker), so every turn of a conversation works in one place; else
        nothing, and the gateway mints a folder for this run.
        """
        try:
            scope = dict(self.preferences.run_scope())
        except Exception:
            scope = {}
        if not str(scope.get("workspace_root") or "").strip():
            try:
                session_root = str(self.llm_manager.session_workspace_root() or "").strip()
            except Exception:
                session_root = ""
            if session_root:
                scope["workspace_root"] = session_root
        return scope

    def workspace_root_status(self) -> Dict[str, str]:
        """Where the next run's files go and why: {root, source} with source in
        {"local", "session", "gateway"} ("gateway" = a fresh folder per run)."""
        try:
            local_root = str(self.preferences.run_scope().get("workspace_root") or "").strip()
        except Exception:
            local_root = ""
        if local_root:
            return {"root": local_root, "source": "local"}
        try:
            session_root = str(self.llm_manager.session_workspace_root() or "").strip()
        except Exception:
            session_root = ""
        if session_root:
            return {"root": session_root, "source": "session"}
        return {"root": "", "source": "gateway"}

    def system_prompt_for_run(self, addendum: str = "") -> str:
        """The `system` pin for a run: empty (the workflow's own baked prompt
        applies) unless an addendum is needed, in which case the workflow's
        base prompt is repeated in front of it — a bare addendum on the
        `system` pin would REPLACE the assistant's persona and tool guidance."""
        extra = str(addendum or "").strip()
        if not extra:
            return ""
        try:
            from .assistant_workflow import _BASE_SYSTEM_PROMPT

            base = str(_BASE_SYSTEM_PROMPT or "").strip()
        except Exception:
            base = ""
        return f"{base}\n\n{extra}".strip() if base else extra

    def save_tool_preference(self, name: str, mode: str) -> None:
        """Set one tool's device mode (disabled|approve|ask) keeping the others."""
        tool = str(name or "").strip()
        value = str(mode or "").strip().lower()
        if not tool or value not in {"disabled", "approve", "ask"}:
            return
        current = dict(self.preferences.tool_preferences or {})
        current[tool] = value
        self.save_tool_preferences(current)

    def reasoning_levels(self) -> List[str]:
        """The reasoning-effort ladder the gateway advertises
        (``contracts.common.runs.start.thinking_control.values``), falling
        back to the contract's known list when the gateway is unreachable."""
        try:
            caps = self.llm_manager.gateway_capabilities(stale_ok=True)
            common = getattr(caps, "common", None) or {}
            control = ((common.get("runs") or {}).get("start") or {}).get("thinking_control") or {}
            values = control.get("values") if isinstance(control, dict) else None
            cleaned = [str(v).strip().lower() for v in (values or []) if str(v or "").strip()]
            if cleaned:
                return cleaned
        except Exception:
            pass
        return list(REASONING_EFFORT_LEVELS)

    def workspace_access_modes(self) -> List[str]:
        """Access modes the gateway accepts (its policy's ``allowed_access_modes``
        when advertised; the contract's known list otherwise)."""
        policy = self.workspace_policy().get("policy") or {}
        modes = policy.get("allowed_access_modes") if isinstance(policy, dict) else None
        cleaned = [str(m).strip().lower() for m in (modes or []) if str(m or "").strip()]
        return cleaned or list(WORKSPACE_ACCESS_MODES)

    def model_capabilities(self, model_name: str) -> Dict[str, Any]:
        """Gateway-side capability card for a model (``thinking_support``,
        ``reasoning_levels``, ...). Cached briefly; {} when unavailable."""
        name = str(model_name or "").strip()
        if not name:
            return {}
        with self._cache_lock:
            cached = self._model_capabilities_cache.get(name)
            if cached is not None and self._cache_fresh(cached[0]):
                return dict(cached[1])
        try:
            payload = self.gateway.discovery_model_capabilities(model_name=name)
        except Exception:
            return {}
        caps = payload.get("capabilities") if isinstance(payload, dict) else None
        result = dict(caps) if isinstance(caps, dict) else {}
        if result:
            with self._cache_lock:
                self._model_capabilities_cache[name] = (time.monotonic(), result)
        return dict(result)

    def workspace_policy(self) -> Dict[str, Any]:
        """The gateway's workspace policy as this principal sees it:
        ``{"policy": <server policy>, "self": <per-user policy>, "error": str}``.

        Read-only and best-effort: the assistant never writes gateway policy; it
        only shows what the gateway will do with the local workspace grant.
        """
        with self._cache_lock:
            if self._workspace_policy_cache is not None and self._cache_fresh(self._workspace_policy_cache_at):
                return json.loads(json.dumps(self._workspace_policy_cache))
            epoch = self._cache_epoch
        out: Dict[str, Any] = {"policy": {}, "self": {}, "error": ""}
        errors: List[str] = []
        try:
            payload = self.gateway.workspace_policy()
            policy = payload.get("policy") if isinstance(payload, dict) else None
            if isinstance(policy, dict):
                out["policy"] = dict(policy)
        except Exception as exc:
            errors.append(self.gateway_service.describe_connection_issue(exc))
        try:
            payload = self.gateway.workspace_policy_self()
            if isinstance(payload, dict):
                out["self"] = {k: v for k, v in payload.items() if k != "ok"}
        except Exception as exc:
            errors.append(self.gateway_service.describe_connection_issue(exc))
        out["error"] = "; ".join(e for e in errors if e)
        if out["policy"] or out["self"]:
            with self._cache_lock:
                if epoch == self._cache_epoch:
                    self._workspace_policy_cache = json.loads(json.dumps(out))
                    self._workspace_policy_cache_at = time.monotonic()
        return out

    def effective_chat_route(self) -> Dict[str, str]:
        """Provider/model that will serve the next chat turn and where it comes
        from: the local override when one is saved, else the gateway default."""
        override = self.route_override("output.text") or {}
        if override.get("provider") and override.get("model"):
            return {
                "provider": str(override.get("provider") or ""),
                "model": str(override.get("model") or ""),
                "source": "override",
            }
        try:
            row = self.route_map(stale_ok=True).get("output.text")
        except Exception:
            row = None
        return {
            "provider": str(getattr(row, "provider", "") or ""),
            "model": str(getattr(row, "model", "") or ""),
            "source": "gateway",
        }

    def current_connection(self) -> GatewayConnectionPreferences:
        return self.connection

    def connection_status(self) -> Dict[str, Any]:
        try:
            payload = self.gateway.gateway_me()
        except Exception as exc:
            return {"ok": False, "detail": self.gateway_service.describe_connection_issue(exc)}
        return payload if isinstance(payload, dict) else {"ok": False, "detail": "Gateway returned an invalid status payload."}

    def save_bearer_connection(self, *, base_url: str, auth_token: str) -> None:
        if str(self.connection.auth_mode or "").strip() == "session" and str(self.connection.session_id or "").strip():
            try:
                self.gateway.session_logout()
            except Exception:
                pass
        connection = GatewayConnectionPreferences(
            base_url=self._normalize_base_url(base_url),
            auth_mode="bearer",
            auth_token=str(auth_token or "").strip(),
            user_id=self.connection.user_id,
            remember_session=self.connection.remember_session,
        )
        self._save_connection(connection)

    def login_gateway_session(self, *, base_url: str, user_id: str, token: str, remember: bool = True) -> Dict[str, Any]:
        base_url_s = self._normalize_base_url(base_url)
        client = GatewayClient(GatewayClientConfig(base_url=base_url_s, timeout_s=float(self.gateway.config.timeout_s)))
        payload = client.session_login(user_id=user_id, token=token, remember=remember)
        self._save_connection(
            GatewayConnectionPreferences(
                base_url=base_url_s,
                auth_mode="session",
                auth_token="",
                user_id=str(user_id or "").strip(),
                session_id=str(client.config.session_id or "").strip(),
                csrf_token=str(client.config.csrf_token or "").strip(),
                session_expires_at=str(client.config.session_expires_at or "").strip(),
                remember_session=bool(remember),
            )
        )
        return payload

    def logout_gateway_session(self) -> None:
        if str(self.connection.auth_mode or "bearer").strip() == "session" and str(self.connection.session_id or "").strip():
            try:
                self.gateway.session_logout()
            except Exception:
                pass
        self._save_connection(
            GatewayConnectionPreferences(
                base_url=self._normalize_base_url(self.connection.base_url),
                auth_mode=self.connection.auth_mode,
                auth_token="" if self.connection.auth_mode == "session" else self.connection.auth_token,
                user_id=self.connection.user_id,
                remember_session=self.connection.remember_session,
            )
        )

    def list_sessions(self) -> List[Dict[str, str]]:
        return self.llm_manager.list_sessions()

    def session_digests(self) -> List[Dict[str, Any]]:
        """Per-chat metrics for the switcher. Reads local files only, cached by
        file identity, so it is fast enough to call on the GUI thread (42 ms for
        74 chats cold, under 2 ms warm)."""
        try:
            return list(self.llm_manager.session_digests() or [])
        except Exception:
            # Fall back to the index-only view so the switcher still lists chats.
            out: List[Dict[str, Any]] = []
            for record in self.list_sessions() or []:
                if isinstance(record, dict) and str(record.get("session_id") or "").strip():
                    out.append(
                        {
                            "session_id": str(record.get("session_id")),
                            "title": str(record.get("title") or "New session"),
                            "created_at": str(record.get("created_at") or ""),
                            "updated_at": str(record.get("updated_at") or ""),
                            "detailed": False,
                        }
                    )
            return out

    def rename_session(self, session_id: str, title: str) -> None:
        self.llm_manager.rename_session(session_id, title)

    def delete_session(self, session_id: str) -> str:
        """Delete a chat and its transcript; returns the new active session id."""
        return str(self.llm_manager.delete_session(session_id) or "")

    def create_session(self) -> str:
        return self.llm_manager.create_new_session()

    def switch_session(self, session_id: str) -> None:
        self.llm_manager.switch_session(session_id)

    def backfill_session_attachments(self) -> int:
        """Restore the active session's attachments from the runtime."""
        backfill = getattr(self.llm_manager, "backfill_attachments_from_gateway", None)
        if not callable(backfill):
            return 0
        try:
            return int(backfill() or 0)
        except Exception:
            return 0

    def session_messages(self) -> List[Dict[str, Any]]:
        return self.llm_manager.session_messages()

    def route_rows(self) -> List[CapabilityRouteRow]:
        return self.gateway_service.list_capability_routes()

    def route_map(self, *, stale_ok: bool = False) -> Dict[str, CapabilityRouteRow]:
        """Gateway capability defaults by route key.

        ``stale_ok`` serves a recent copy without a round trip (the send path
        runs on the GUI thread and only needs the effective chat route for
        display); settings surfaces call without it to see the live defaults.
        """
        cache = getattr(self, "_route_map_cache", None)
        cache_at = float(getattr(self, "_route_map_cache_at", 0.0) or 0.0)
        if stale_ok and isinstance(cache, dict) and cache and self._cache_fresh(cache_at):
            return dict(cache)
        rows = self.gateway_service.route_map()
        if rows:
            self._route_map_cache = dict(rows)
            self._route_map_cache_at = time.monotonic()
        return rows

    def route_override(self, route_key: str) -> Optional[Dict[str, Any]]:
        """Return the LOCAL override for a capability route, or None.

        These are the assistant's own per-app overrides of the gateway default.
        The gateway's global capability defaults are never read or written here.
        """
        key = str(route_key or "").strip()
        overrides = getattr(self.preferences, "route_overrides", None) or {}
        value = overrides.get(key)
        return dict(value) if isinstance(value, dict) else None

    def save_route_override(
        self,
        *,
        route_key: str,
        provider: str,
        model: str,
        base_url: str = "",
        options: Optional[Dict[str, Any]] = None,
        options_text: str = "",
    ) -> None:
        """Persist a LOCAL override for this app only.

        This never mutates the gateway's global capability default — the
        selection rides each run (chat) or voice call as a per-request override.
        """
        key = str(route_key or "").strip()
        if key not in LOCAL_OVERRIDE_ROUTE_KEYS:
            raise ValueError(f"Route {key!r} cannot be overridden locally by the assistant.")
        provider_s = str(provider or "").strip()
        model_s = str(model or "").strip()
        if not provider_s or not model_s:
            raise ValueError("A local override needs both a provider and a model.")
        parsed_options = dict(options) if isinstance(options, dict) else self._parse_options(options_text)
        entry: Dict[str, Any] = {"provider": provider_s, "model": model_s}
        base_url_s = str(base_url or "").strip()
        if base_url_s:
            entry["base_url"] = base_url_s
        if parsed_options:
            entry["options"] = parsed_options
        overrides = dict(getattr(self.preferences, "route_overrides", None) or {})
        overrides[key] = entry
        self._persist_route_overrides(overrides)

    def clear_route_override(self, *, route_key: str) -> None:
        """Drop the LOCAL override so the gateway default applies again."""
        key = str(route_key or "").strip()
        overrides = dict(getattr(self.preferences, "route_overrides", None) or {})
        if key not in overrides:
            return
        overrides.pop(key, None)
        self._persist_route_overrides(overrides)

    def _persist_route_overrides(self, overrides: Dict[str, Dict[str, Any]]) -> None:
        import dataclasses

        prefs = dataclasses.replace(self.preferences, route_overrides=overrides)
        self.preferences_store.save(prefs)
        self.preferences = prefs
        # Voice overrides are applied by the voice manager reading these prefs;
        # invalidate caches so any capability-derived UI refreshes.
        self.invalidate_caches()
        self._sync_gateway_voice_defaults()

    def provider_choices(self, *, route_key: str, base_url: str = ""):
        return self.gateway_service.provider_choices(route_key=route_key, base_url=base_url)

    def model_choices(self, *, route_key: str, provider: str, base_url: str = ""):
        return self.gateway_service.model_choices(route_key=route_key, provider=provider, base_url=base_url)

    def voice_choices(self, *, provider: str, model: str, base_url: str = ""):
        return self.gateway_service.voice_choices(provider=provider, model=model, base_url=base_url)

    def supports_tts(self) -> bool:
        return bool(self.voice_manager.supports_tts())

    def supports_stt(self) -> bool:
        return bool(self.voice_manager.supports_stt())

    def refresh_gateway_capabilities(self) -> None:
        self.llm_manager.gateway_capabilities(force=True)
        self._sync_gateway_voice_defaults()

    def refresh_gateway_client(self) -> None:
        self.invalidate_caches()
        self.llm_manager._gateway_client = None  # type: ignore[attr-defined]
        gateway = self.llm_manager.gateway_client()
        if gateway is None:
            raise RuntimeError("Gateway client is not configured")
        self.gateway = gateway
        self.gateway_service = AssistantGatewayService(gateway)
        self.refresh_gateway_capabilities()

    def build_chat_worker(
        self,
        *,
        prompt: str,
        attachments: Optional[List[str]] = None,
        system_prompt_extra: Optional[str] = None,
        append_user_message: bool = True,
    ) -> GatewayWorker:
        workflow = self.current_workflow()
        if workflow is None:
            detail = str(self.workflow_status().error or "No runnable gateway workflow is available.").strip()
            raise RuntimeError(detail)
        text_override = self.route_override("output.text")
        scope = self.run_scope()
        system_prompt = self.system_prompt_for_run(str(system_prompt_extra or ""))
        return GatewayWorker(
            llm_manager=self.llm_manager,
            user_text=prompt,
            attachments=list(attachments or []),
            system_prompt_extra=system_prompt or None,
            allowed_tools=self.allowed_tools_for_run(),
            tool_policy=self.tool_policy_for_run(),
            append_user_message=bool(append_user_message),
            bundle_id=workflow.bundle_id,
            flow_id=workflow.flow_id,
            bundle_version=workflow.bundle_version,
            registry_scope=workflow.registry_scope,
            primary_image_artifact=self.latest_image_artifact(),
            provider_override=str((text_override or {}).get("provider") or "") or None,
            model_override=str((text_override or {}).get("model") or "") or None,
            base_url_override=str((text_override or {}).get("base_url") or "") or None,
            media_overrides=self.media_route_overrides() or None,
            thinking=str(scope.get("thinking") or ""),
            workspace_root=str(scope.get("workspace_root") or ""),
            workspace_access_mode=str(scope.get("workspace_access_mode") or ""),
            workspace_allowed_paths=list(scope.get("workspace_allowed_paths") or []),
            debug=self.debug,
        )

    def media_route_overrides(self) -> Dict[str, Dict[str, Any]]:
        """Local media route overrides ({route_key: {provider, model}}) for
        this app's runs. Voice routes are excluded (they ride the TTS/STT
        calls, not the workflow input); text rides its own dedicated kwargs."""
        out: Dict[str, Dict[str, Any]] = {}
        for route_key in MEDIA_OVERRIDE_INPUT_KEYS:
            override = self.route_override(route_key)
            if isinstance(override, dict) and override.get("provider") and override.get("model"):
                out[route_key] = {
                    "provider": str(override.get("provider") or "").strip(),
                    "model": str(override.get("model") or "").strip(),
                }
        sound = self.route_override("output.sound")
        if isinstance(sound, dict) and sound.get("provider") and sound.get("model"):
            out["output.sound"] = {
                "provider": str(sound.get("provider") or "").strip(),
                "model": str(sound.get("model") or "").strip(),
            }
        return out

    def probe_reattach_candidate(self, *, stale_after_s: float = 600.0) -> Optional[Dict[str, Any]]:
        """Off-thread: decide whether the active session's last run should be
        reattached on launch. Returns {run_id, status, waiting} or None.

        Reattach when the last run is (a) still running/waiting and updated
        within `stale_after_s` (a live run to follow), or (b) terminal but its
        answer never reached the local transcript (recover a run that finished
        while the app was closed). Stale/zombie running runs are skipped so the
        UI is not wedged busy following a dead run.
        """
        run_id = str(self.last_run_id() or "").strip()
        if not run_id:
            return None
        try:
            summary = self.gateway.get_run(run_id=run_id)
        except Exception:
            return None
        if not isinstance(summary, dict):
            return None
        status = str(summary.get("status") or "").strip().lower()
        waiting = summary.get("waiting") if isinstance(summary.get("waiting"), dict) else None
        if status == "waiting":
            # A run parked on the user (approval / ask) does not refresh
            # updated_at while it waits — "quit with a pending approval, come
            # back after lunch" must still reattach, so no staleness gate here.
            return {"run_id": run_id, "status": status, "waiting": waiting}
        if status == "running":
            if self._run_updated_within(summary, stale_after_s):
                return {"run_id": run_id, "status": status, "waiting": waiting}
            return None
        if status in {"completed", "failed", "cancelled"}:
            if not self._session_has_answer_for_run(run_id):
                return {"run_id": run_id, "status": status, "waiting": None}
        return None

    @staticmethod
    def _run_updated_within(summary: Dict[str, Any], stale_after_s: float) -> bool:
        raw = str(summary.get("updated_at") or summary.get("updatedAt") or "").strip()
        if not raw:
            return True  # No timestamp: don't treat as stale.
        try:
            from datetime import datetime, timezone

            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            return age <= float(stale_after_s)
        except Exception:
            return True

    def _session_has_answer_for_run(self, run_id: str) -> bool:
        rid = str(run_id or "").strip()
        messages = self.session_messages()
        any_run_stamp = False
        for message in messages:
            if not isinstance(message, dict):
                continue
            if str(message.get("role") or "") != "assistant":
                continue
            if not str(message.get("content") or "").strip():
                continue
            meta = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
            stamp = str((meta or {}).get("run_id") or message.get("run_id") or "").strip()
            if stamp:
                any_run_stamp = True
                if stamp == rid:
                    return True
        # Only assume "seen" when NO assistant message carries a run stamp
        # (a legacy/unstamped transcript). If OTHER runs are stamped but not
        # this one, the answer for this run is genuinely missing → recover it.
        if any_run_stamp:
            return False
        return any(
            isinstance(m, dict)
            and str(m.get("role") or "") == "assistant"
            and str(m.get("content") or "").strip()
            for m in messages
        )

    def build_attach_worker(self, run_id: str) -> GatewayWorker:
        """Build a worker that follows an existing run instead of starting one.

        Reattach needs no workflow-catalog lookup: the entrypoint is only
        resolved on the start path, never on the attach path.
        """
        return GatewayWorker(
            llm_manager=self.llm_manager,
            user_text="",
            attachments=[],
            append_user_message=False,
            bundle_id="",
            flow_id="",
            registry_scope="tenant_catalog",
            attach_run_id=str(run_id or "").strip(),
            debug=self.debug,
        )

    def tool_inventory(self) -> Dict[str, Any]:
        with self._cache_lock:
            if self._tool_inventory_cache is not None and self._cache_fresh(self._tool_inventory_cache_at):
                return self._copy_inventory(self._tool_inventory_cache)
            epoch = self._cache_epoch
        result = self._compute_tool_inventory()
        # Only cache a real inventory (with items); an empty result usually
        # means the discovery call failed and must not be pinned for the TTL.
        if result.get("items"):
            with self._cache_lock:
                if epoch == self._cache_epoch:
                    self._tool_inventory_cache = result
                    self._tool_inventory_cache_at = time.monotonic()
        return self._copy_inventory(result)

    def _compute_tool_inventory(self) -> Dict[str, Any]:
        items: List[Dict[str, str]] = []
        tool_mode = ""
        note = ""
        try:
            payload = self.gateway.discovery_tools()
        except Exception as exc:
            payload = {"items": [], "error": str(exc)}
        raw_items = payload.get("items") if isinstance(payload, dict) else []
        tool_mode = str((payload or {}).get("tool_mode") or "").strip().lower() if isinstance(payload, dict) else ""
        error = str((payload or {}).get("error") or "").strip() if isinstance(payload, dict) else ""

        if isinstance(raw_items, list):
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or "").strip()
                if not name:
                    continue
                item: Dict[str, Any] = {
                    "name": name,
                    "description": str(raw.get("description") or "").strip(),
                    "toolset": str(raw.get("toolset") or raw.get("toolset_id") or raw.get("toolsetId") or "").strip().lower(),
                    "when_to_use": str(raw.get("when_to_use") or raw.get("whenToUse") or "").strip(),
                    # The gateway's own availability + risk classification. The
                    # assistant displays these; it never re-derives them.
                    "available": raw.get("enabled") is not False,
                    "approval_default": str(raw.get("approval_default") or "").strip().lower(),
                    "risk_tier": str(raw.get("risk_tier") or "").strip().lower(),
                    "tier": str(raw.get("tier") or "").strip(),
                }
                for flag in (
                    "mutating",
                    "destructive_capable",
                    "remote_write_capable",
                    "captures_environment",
                    "comms_send",
                    "standing_effect",
                    "grantable",
                ):
                    if isinstance(raw.get(flag), bool):
                        item[flag] = bool(raw.get(flag))
                if isinstance(raw.get("risk_rank"), int):
                    item["risk_rank"] = int(raw.get("risk_rank"))
                if isinstance(raw.get("parameters"), dict):
                    item["parameters"] = dict(raw.get("parameters"))
                items.append(item)

        if error:
            note = error

        # The gateway's `approval_default` is the policy of record; the local
        # ToolApprovalPolicy lists are only the fallback for a gateway that
        # predates the field (a thin client must not out-vote its server).
        policy = ToolApprovalPolicy()
        safe = set(policy.auto_approve_tools)
        require = set(policy.require_approval_tools)
        saved = dict(self.preferences.tool_preferences or {})
        enriched: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in sorted(items, key=lambda entry: (str(entry.get("toolset") or ""), str(entry.get("name") or ""))):
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            gateway_default = str(item.get("approval_default") or "").strip().lower()
            if gateway_default == "auto":
                policy_default = "approve"
            elif gateway_default == "ask":
                policy_default = "ask"
            elif name in require:
                policy_default = "ask"
            elif name in safe:
                policy_default = "approve"
            else:
                policy_default = "ask"
            if saved.get(name) in {"disabled", "approve", "ask"}:
                selected_mode = saved[name]
            else:
                selected_mode = policy_default
            enriched.append(
                {
                    **item,
                    "default_mode": policy_default,
                    "selected_mode": selected_mode,
                    "policy_default": policy_default,
                    "policy_source": "gateway" if gateway_default in {"auto", "ask"} else "local",
                }
            )
        return {"items": enriched, "tool_mode": tool_mode or "", "note": note}

    def tool_inventory_by_name(self) -> Dict[str, Dict[str, Any]]:
        """{tool_name: inventory item} for risk badges on approval cards."""
        out: Dict[str, Dict[str, Any]] = {}
        try:
            inventory = self.tool_inventory()
        except Exception:
            return out
        for item in inventory.get("items") or []:
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                out[str(item.get("name")).strip()] = dict(item)
        return out

    def save_tool_preferences(self, statuses: Dict[str, str]) -> None:
        cleaned = {
            str(name).strip(): str(mode).strip().lower()
            for name, mode in (statuses or {}).items()
            if str(name).strip() and str(mode).strip().lower() in {"disabled", "approve", "ask"}
        }
        self.save_preferences(self._copy_preferences(tool_preferences=cleaned))
        # Saved per-tool modes change the inventory's selected_mode.
        self.invalidate_caches()

    def allowed_tools_for_run(self) -> List[str]:
        inventory = self.tool_inventory()
        out: List[str] = []
        for item in inventory.get("items") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("selected_mode") or "ask").strip().lower() == "disabled":
                continue
            if item.get("available") is False:
                # Disabled on the gateway: offering it would only produce a
                # refused call. The Tools settings show it as unavailable.
                continue
            name = str(item.get("name") or "").strip()
            if name:
                out.append(name)
        return out

    # Blanket ("trust this chat") grants stop at this gateway risk rank: observe
    # (1) and act (2) qualify; outreach (3) and destroy (4) always keep asking
    # unless the user set that tool to Auto by name.
    TRUST_MAX_RISK_RANK = 2

    @staticmethod
    def _tool_risk_rank(item: Dict[str, Any]) -> int:
        try:
            from .core.tool_risk import risk_rank

            return int(risk_rank(item))
        except Exception:
            return 0

    def _tool_trustable(self, item: Dict[str, Any], ceiling: int) -> bool:
        """May this chat's grant auto-approve this tool? Only up to the tier
        the grant was made on; a tool with no tier keeps the plain grant."""
        return self._tool_risk_rank(item) <= max(0, int(ceiling))

    def tool_policy_for_run(self) -> Dict[str, List[str]]:
        inventory = self.tool_inventory()
        auto: List[str] = []
        require: List[str] = []
        trust_ceiling = self.session_trust_rank()
        for item in inventory.get("items") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            mode = str(item.get("selected_mode") or "ask").strip().lower()
            if mode == "disabled" or item.get("available") is False:
                continue
            if mode == "approve" or (trust_ceiling and self._tool_trustable(item, trust_ceiling)):
                auto.append(name)
            else:
                require.append(name)
        return {
            "auto_approve_tools": auto,
            "require_approval_tools": require,
        }

    def grant_session_tool_auto_approval(
        self, *, session_id: Optional[str] = None, max_rank: Optional[int] = None
    ) -> None:
        """Trust this chat's enabled tools up to ``max_rank``.

        The ceiling is the loudest risk tier the user actually saw when they
        granted it: approving a batch of file reads never buys blanket trust
        for a later destructive call, but granting it ON a destructive batch
        does — the sheet says so on the item they clicked.
        """
        sid = str(session_id or self.active_session_id or "").strip()
        if not sid:
            return
        self._session_auto_approve_all.add(sid)
        ranks = getattr(self, "_session_trust_rank", None)
        if not isinstance(ranks, dict):
            ranks = {}
            self._session_trust_rank = ranks
        wanted = self.TRUST_MAX_RISK_RANK if max_rank is None else int(max_rank)
        wanted = max(1, min(4, wanted))
        ranks[sid] = max(int(ranks.get(sid, 0)), wanted)

    def session_tool_auto_approval_active(self, *, session_id: Optional[str] = None) -> bool:
        sid = str(session_id or self.active_session_id or "").strip()
        return bool(sid and sid in self._session_auto_approve_all)

    def session_trust_rank(self, *, session_id: Optional[str] = None) -> int:
        """How far this chat's blanket grant reaches (0 when there is none)."""
        if not self.session_tool_auto_approval_active(session_id=session_id):
            return 0
        sid = str(session_id or self.active_session_id or "").strip()
        ranks = getattr(self, "_session_trust_rank", None)
        if isinstance(ranks, dict) and sid in ranks:
            return int(ranks[sid])
        return int(self.TRUST_MAX_RISK_RANK)

    def should_auto_approve_tool_batch(self, tool_calls: Any, *, session_id: Optional[str] = None) -> bool:
        """A per-chat trust grant auto-approves a batch only when every call is
        an enabled tool the grant may cover: a tool set to Auto by name, or one
        at or below the tier the grant was made on. A batch louder than the
        grant still asks."""
        ceiling = self.session_trust_rank(session_id=session_id)
        if not ceiling:
            return False
        if not isinstance(tool_calls, list) or not tool_calls:
            return False
        inventory = self.tool_inventory()
        by_name: Dict[str, Dict[str, Any]] = {}
        for item in inventory.get("items") or []:
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                by_name[str(item.get("name")).strip()] = item
        if not by_name:
            return False
        for call in tool_calls:
            if not isinstance(call, dict):
                return False
            name = str(call.get("name") or "").strip()
            item = by_name.get(name)
            if not name or item is None:
                return False
            mode = str(item.get("selected_mode") or "ask").strip().lower()
            if mode == "disabled" or item.get("available") is False:
                return False
            if mode != "approve" and not self._tool_trustable(item, ceiling):
                return False
        return True

    def latest_image_artifact(self) -> Optional[Dict[str, Any]]:
        for message in reversed(self.session_messages()):
            if not isinstance(message, dict):
                continue
            metadata = message.get("metadata")
            if not isinstance(metadata, dict):
                continue
            for key in ("image_artifact", "artifact", "media_artifact"):
                candidate = metadata.get(key)
                if not isinstance(candidate, dict) or not str(candidate.get("$artifact") or "").strip():
                    continue
                if key == "image_artifact" or self._artifact_is_image(candidate):
                    return dict(candidate)
            generated_media = metadata.get("generated_media")
            if isinstance(generated_media, dict):
                candidate = generated_media.get("image_artifact")
                if isinstance(candidate, dict) and str(candidate.get("$artifact") or "").strip():
                    return dict(candidate)
        return None

    def download_artifact(self, *, run_id: str, artifact: Dict[str, Any]) -> Path:
        local_path = str(artifact.get("local_path") or artifact.get("path") or "").strip()
        if local_path:
            candidate = Path(local_path).expanduser()
            if candidate.exists():
                return candidate

        artifact_id = str(artifact.get("$artifact") or artifact.get("artifact_id") or "").strip()
        if not artifact_id:
            if local_path:
                # An attachment the user picked from disk with no gateway copy:
                # there is nothing to download, the file itself is gone (a
                # screenshot dragged out of the macOS screenshot UI lives in a
                # temp folder macOS empties).
                raise FileNotFoundError(f"{Path(local_path).name} is no longer on disk")
            raise ValueError("artifact_id is required")
        # The artifact download route is scoped to the run that OWNS the
        # artifact. An uploaded attachment belongs to the session's own upload
        # run, not to the chat run that carried it, so its recorded run_id wins.
        rid = str(artifact.get("run_id") or run_id or "").strip()
        if not rid:
            raise ValueError("run_id is required")

        downloads_dir = Path(self.llm_manager.data_dir) / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        filename = self._artifact_cache_filename(artifact_id=artifact_id, artifact=artifact)
        path = downloads_dir / filename
        try:
            if path.exists() and path.stat().st_size > 0 and path.suffix:
                return path
        except Exception:
            pass

        raw, content_type = self.gateway.download_run_artifact_content(
            run_id=rid,
            artifact_id=artifact_id,
            max_bytes=50_000_000,
            timeout_s=300.0,
        )
        resolved = downloads_dir / self._artifact_cache_filename(
            artifact_id=artifact_id,
            artifact=artifact,
            content_type_override=str(content_type or "").strip(),
        )
        resolved.write_bytes(raw)
        if resolved != path and path.exists():
            try:
                path.unlink()
            except Exception:
                pass
        return resolved

    def append_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Append the user's turn; returns its message_id so a turn whose run
        never started can be withdrawn again."""
        result = self.llm_manager.append_message(role="user", content=content, metadata=metadata)
        return str(result or "")

    def merge_message_metadata(self, message_id: str, metadata: Dict[str, Any]) -> bool:
        merger = getattr(self.llm_manager, "merge_message_metadata", None)
        if not callable(merger):
            return False
        try:
            return bool(merger(message_id, metadata))
        except Exception:
            return False

    def remove_message(self, message_id: str) -> bool:
        remover = getattr(self.llm_manager, "remove_message", None)
        if not callable(remover):
            return False
        try:
            return bool(remover(message_id))
        except Exception:
            return False

    def last_run_id(self) -> Optional[str]:
        return self.llm_manager.get_last_run_id()

    def cancel_run(self, run_id: str) -> bool:
        """Submit a durable, tree-wide gateway cancel for the given run.

        Returns True when the command was accepted. The follower is stopped
        separately by interrupting the worker thread.
        """
        rid = str(run_id or "").strip()
        if not rid:
            return False
        try:
            self.gateway.submit_command(
                command={
                    "command_id": f"cancel_{int(time.time() * 1000)}",
                    "run_id": rid,
                    "type": "cancel",
                    "payload": {},
                    "client_id": "abstractassistant",
                }
            )
            return True
        except Exception as exc:
            warnings.warn(f"#FALLBACK: failed to cancel run via gateway: {exc}")
            return False

    def pause_run(self, run_id: str) -> bool:
        """Submit a durable, tree-wide gateway pause for the given run.

        Takes effect at the run's next step boundary (an in-flight LLM/tool
        call finishes first). Returns True when the command was accepted.
        """
        rid = str(run_id or "").strip()
        if not rid:
            return False
        try:
            self.gateway.submit_command(
                command={
                    "command_id": f"pause_{int(time.time() * 1000)}",
                    "run_id": rid,
                    "type": "pause",
                    "payload": {"reason": "Paused by user"},
                    "client_id": "abstractassistant",
                }
            )
            return True
        except Exception as exc:
            warnings.warn(f"#FALLBACK: failed to pause run via gateway: {exc}")
            return False

    def resume_run(self, run_id: str) -> bool:
        """Resume a previously paused run (tree-wide)."""
        rid = str(run_id or "").strip()
        if not rid:
            return False
        try:
            self.gateway.submit_command(
                command={
                    "command_id": f"resume_{int(time.time() * 1000)}",
                    "run_id": rid,
                    "type": "resume",
                    "payload": {},
                    "client_id": "abstractassistant",
                }
            )
            return True
        except Exception as exc:
            warnings.warn(f"#FALLBACK: failed to resume run via gateway: {exc}")
            return False

    def inject_guidance(self, run_id: str, guidance: str) -> bool:
        """Steer a running agent without cancelling it.

        The guidance lands in the durable inbox of the run (and its
        descendants) and folds into the agent's next reasoning cycle as a
        durable transcript message. Returns True when the command was accepted.
        """
        rid = str(run_id or "").strip()
        text = str(guidance or "").strip()
        if not rid or not text:
            return False
        try:
            self.gateway.submit_command(
                command={
                    "command_id": f"steer_{int(time.time() * 1000)}",
                    "run_id": rid,
                    "type": "inject_guidance",
                    "payload": {"guidance": text},
                    "client_id": "abstractassistant",
                }
            )
            return True
        except Exception as exc:
            warnings.warn(f"#FALLBACK: failed to inject guidance via gateway: {exc}")
            return False

    @staticmethod
    def _message_run_id_candidates(message: Dict[str, Any]) -> List[str]:
        if not isinstance(message, dict):
            return []
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        stats = metadata.get("_assistant_stats") if isinstance(metadata.get("_assistant_stats"), dict) else {}
        repl = metadata.get("_repl") if isinstance(metadata.get("_repl"), dict) else {}
        repl_stats = repl.get("stats") if isinstance(repl.get("stats"), dict) else {}
        candidates = [
            message.get("run_id"),
            metadata.get("run_id"),
            stats.get("run_id"),
            repl.get("run_id"),
            repl_stats.get("run_id"),
            metadata.get("sub_run_id"),
            stats.get("sub_run_id"),
            repl.get("sub_run_id"),
            repl_stats.get("sub_run_id"),
        ]
        out: List[str] = []
        for candidate in candidates:
            rid = str(candidate or "").strip()
            if rid and rid not in out:
                out.append(rid)
        return out

    def tool_call_details_for_run(self, *, run_id: str, include_subruns: bool = True) -> List[Dict[str, Any]]:
        root = str(run_id or "").strip()
        if not root:
            raise ValueError("run_id is required")
        pending: List[str] = [root]
        seen_runs: set[str] = set()
        seen_calls: set[str] = set()
        out: List[Dict[str, Any]] = []

        while pending:
            rid = pending.pop(0)
            if not rid or rid in seen_runs:
                continue
            seen_runs.add(rid)
            after = 0
            while True:
                page = self.gateway.get_ledger(run_id=rid, after=after, limit=2000)
                items = page.get("items") if isinstance(page, dict) else []
                if not isinstance(items, list) or not items:
                    break
                if include_subruns:
                    for item in items:
                        record = ledger_record_from_item(item)
                        for sub_run_id in extract_sub_run_ids_from_record(record):
                            if sub_run_id not in seen_runs and sub_run_id not in pending:
                                pending.append(sub_run_id)

                for call in extract_tool_call_details_from_ledger_items(items, run_id=rid):
                    # Dedupe guards against an overlapping ledger page, so it keys on
                    # the call's UNIQUE identity. It used to key on `call_id`, the
                    # model's per-response number: three calls all numbered "0" were
                    # "duplicates", and the dialog listed one tool under "tools : 3".
                    key = str(call.get("call_uid") or "").strip() or f"{rid}:{len(out)}:{call.get('name')}"
                    if key in seen_calls:
                        continue
                    seen_calls.add(key)
                    out.append(call)

                next_after_raw = page.get("next_after") if isinstance(page, dict) else None
                try:
                    next_after = int(next_after_raw)
                except Exception:
                    next_after = after + len(items)
                if next_after <= after:
                    next_after = after + len(items)
                if next_after <= after:
                    break
                after = next_after
        return out

    def tool_call_details_for_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        run_ids = self._message_run_id_candidates(message)
        scratchpad_calls = extract_tool_call_details_from_scratchpad(
            metadata.get("scratchpad"),
            run_id=run_ids[0] if run_ids else "",
        )

        errors: List[str] = []
        if run_ids:
            for run_id in run_ids:
                try:
                    calls = self.tool_call_details_for_run(run_id=run_id, include_subruns=True)
                except Exception as exc:
                    errors.append(f"{run_id}: {exc}")
                    continue
                if calls:
                    return {"tool_calls": calls, "source": "ledger", "run_ids": [run_id], "error": ""}
        elif not scratchpad_calls:
            return {"tool_calls": [], "source": "missing_run_id", "run_ids": [], "error": "No run_id is attached to this message."}

        if scratchpad_calls:
            return {
                "tool_calls": scratchpad_calls,
                "source": "scratchpad",
                "run_ids": run_ids,
                "error": "; ".join(errors),
            }
        return {"tool_calls": [], "source": "ledger", "run_ids": run_ids, "error": "; ".join(errors)}

    def submission_plan(self, *, prompt: str, attachments: Optional[List[str]] = None) -> Dict[str, Any]:
        workflow = self.current_workflow()
        plan: Dict[str, Any] = {
            "path": "workflow_chat",
            "mode": "assistant",
            "reason": "All assistant turns run through the published gateway workflow.",
            "needs_tools": False,
            "system_prompt_extra": "",
            "ready": workflow is not None,
            "detail": "",
        }
        if workflow is None:
            plan["detail"] = str(self.workflow_status().error or "No runnable assistant workflow is available.").strip()
        return plan

    def parse_options(self, options_text: str) -> Dict[str, Any]:
        return self._parse_options(options_text)

    def _load_connection_preferences(self) -> GatewayConnectionPreferences:
        gateway = getattr(self.config, "gateway", None)
        runtime = GatewayConnectionPreferences(
            base_url=self._normalize_base_url(str(getattr(gateway, "url", "") or DEFAULT_GATEWAY_URL)),
            auth_mode=str(getattr(gateway, "auth_mode", "bearer") or "bearer").strip() or "bearer",
            auth_token=str(getattr(gateway, "auth_token", "") or "").strip(),
            user_id=str(getattr(gateway, "user_id", "") or "").strip(),
            session_id=str(getattr(gateway, "session_id", "") or "").strip(),
            csrf_token=str(getattr(gateway, "csrf_token", "") or "").strip(),
            session_expires_at=str(getattr(gateway, "session_expires_at", "") or "").strip(),
        )
        if not self.connection_store.path.exists():
            return runtime

        stored = self.connection_store.load()
        runtime_has_auth = any(
            (
                runtime.auth_token,
                runtime.session_id,
                runtime.csrf_token,
                runtime.user_id,
            )
        )
        runtime_has_explicit_url = runtime.base_url != DEFAULT_GATEWAY_URL
        if not (runtime_has_auth or runtime_has_explicit_url):
            return stored

        if runtime.auth_mode == "session":
            return GatewayConnectionPreferences(
                base_url=runtime.base_url,
                auth_mode="session",
                auth_token="",
                user_id=runtime.user_id,
                session_id=runtime.session_id,
                csrf_token=runtime.csrf_token,
                session_expires_at=runtime.session_expires_at,
                remember_session=stored.remember_session,
            )

        return GatewayConnectionPreferences(
            base_url=runtime.base_url,
            auth_mode="bearer",
            auth_token=runtime.auth_token,
            user_id=stored.user_id,
            session_id="",
            csrf_token="",
            session_expires_at="",
            remember_session=stored.remember_session,
        )

    def _save_connection(self, connection: GatewayConnectionPreferences) -> None:
        self.connection = connection
        self.connection_store.save(connection)
        self._apply_connection_to_config(connection)
        self.invalidate_caches()
        self.refresh_gateway_client()

    def _apply_connection_to_config(self, connection: GatewayConnectionPreferences) -> None:
        gateway = getattr(self.config, "gateway", None)
        if gateway is None:
            return
        gateway.url = self._normalize_base_url(connection.base_url or getattr(gateway, "url", DEFAULT_GATEWAY_URL))
        gateway.auth_mode = str(connection.auth_mode or "bearer").strip() or "bearer"
        gateway.auth_token = str(connection.auth_token or "").strip()
        gateway.user_id = str(connection.user_id or "").strip()
        gateway.session_id = str(connection.session_id or "").strip()
        gateway.csrf_token = str(connection.csrf_token or "").strip()
        gateway.session_expires_at = str(connection.session_expires_at or "").strip()

    def _workflow_selection_from_option(self, option: WorkflowOption) -> WorkflowSelection:
        return WorkflowSelection(
            bundle_id=option.bundle_id,
            flow_id=option.flow_id,
            bundle_version=option.bundle_version,
            registry_scope=option.registry_scope,
        )

    def _artifact_is_image(self, artifact: Dict[str, Any]) -> bool:
        content_type = str(artifact.get("content_type") or "").strip().lower()
        modality = str(artifact.get("modality") or "").strip().lower()
        return content_type.startswith("image/") or modality == "image"

    def _artifact_cache_filename(self, *, artifact_id: str, artifact: Dict[str, Any], content_type_override: str = "") -> str:
        raw_name = str(artifact.get("filename") or "").strip()
        content_type = str(content_type_override or artifact.get("content_type") or "").strip().lower()
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(artifact_id or "").strip())[:24] or "artifact"

        suffix = Path(raw_name).suffix if raw_name else ""
        if not suffix and content_type:
            guessed = mimetypes.guess_extension(content_type, strict=False)
            if not guessed:
                guessed = {
                    "audio/wav": ".wav",
                    "audio/x-wav": ".wav",
                    "audio/mpeg": ".mp3",
                    "audio/mp3": ".mp3",
                    "audio/mp4": ".m4a",
                    "audio/x-m4a": ".m4a",
                    "audio/flac": ".flac",
                    "audio/ogg": ".ogg",
                    "video/mp4": ".mp4",
                    "video/quicktime": ".mov",
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                }.get(content_type)
            if guessed:
                suffix = guessed

        stem = Path(raw_name).stem if raw_name else safe_id
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "artifact"
        safe_suffix = re.sub(r"[^A-Za-z0-9.]+", "", suffix or "")
        if safe_suffix and not safe_suffix.startswith("."):
            safe_suffix = f".{safe_suffix}"
        return f"{safe_id}-{safe_stem}{safe_suffix}"

    def _sync_gateway_voice_defaults(self) -> None:
        """Apply the LOCAL voice/STT overrides onto the voice manager.

        Only a local override is pushed as an explicit provider/model/voice; an
        empty value means "let the gateway default resolve" (the voice manager
        already falls back to gateway capabilities when these are blank). We
        never read the gateway's global default here and pin it as if it were
        the user's choice — that would freeze a moving default and mask offline
        breakage.
        """
        tts_override = self.route_override("output.voice") or {}
        stt_override = self.route_override("input.voice") or {}
        tts_provider = str(tts_override.get("provider") or "").strip()
        tts_model = str(tts_override.get("model") or "").strip()
        tts_options = tts_override.get("options") if isinstance(tts_override.get("options"), dict) else {}
        tts_voice = str(tts_options.get("voice") or tts_options.get("profile") or "").strip()
        setattr(self.llm_manager, "current_tts_provider", tts_provider)
        setattr(self.llm_manager, "current_tts_model", tts_model)
        setattr(self.llm_manager, "current_tts_voice", tts_voice)
        setattr(self.llm_manager, "current_tts_voice_mode", "profile")
        setattr(self.llm_manager, "current_stt_model", str(stt_override.get("model") or "").strip())
        setattr(self.llm_manager, "current_stt_provider", str(stt_override.get("provider") or "").strip())

    def _normalize_base_url(self, value: str) -> str:
        return str(value or "").strip().rstrip("/") or DEFAULT_GATEWAY_URL

    def _parse_options(self, options_text: str) -> Dict[str, Any]:
        text = str(options_text or "").strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Options must be a JSON object")
        return parsed
