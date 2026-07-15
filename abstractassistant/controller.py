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
    PreferencesStore,
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
        self._cache_lock = threading.RLock()
        # The gateway voice-default sync does a blocking capability-defaults
        # GET; it runs in prefetch() (off the GUI thread), not in __init__.

    def _cache_fresh(self, at: float) -> bool:
        return bool(at) and (time.monotonic() - float(at)) < self._cache_ttl_s

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

    def _copy_preferences(self, **updates: Any) -> AssistantPreferences:
        payload = self.preferences.to_dict()
        payload.update(updates)
        return AssistantPreferences.from_dict(payload)

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

    def create_session(self) -> str:
        return self.llm_manager.create_new_session()

    def switch_session(self, session_id: str) -> None:
        self.llm_manager.switch_session(session_id)

    def session_messages(self) -> List[Dict[str, Any]]:
        return self.llm_manager.session_messages()

    def route_rows(self) -> List[CapabilityRouteRow]:
        return self.gateway_service.list_capability_routes()

    def route_map(self) -> Dict[str, CapabilityRouteRow]:
        return self.gateway_service.route_map()

    def save_route_default(
        self,
        *,
        route_key: str,
        provider: str,
        model: str,
        base_url: str = "",
        options: Optional[Dict[str, Any]] = None,
        options_text: str = "",
    ) -> None:
        parsed_options = dict(options) if isinstance(options, dict) else self._parse_options(options_text)
        self.gateway_service.save_route_default(
            route_key=route_key,
            provider=provider,
            model=model,
            base_url=base_url,
            options=parsed_options,
        )
        self.invalidate_caches()
        self.refresh_gateway_capabilities()
        self._sync_gateway_voice_defaults()

    def clear_route_default(self, *, route_key: str) -> None:
        self.gateway_service.clear_route_default(route_key=route_key)
        self.invalidate_caches()
        self.refresh_gateway_capabilities()
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
        return GatewayWorker(
            llm_manager=self.llm_manager,
            user_text=prompt,
            attachments=list(attachments or []),
            system_prompt_extra=str(system_prompt_extra or "").strip() or None,
            allowed_tools=self.allowed_tools_for_run(),
            tool_policy=self.tool_policy_for_run(),
            append_user_message=bool(append_user_message),
            bundle_id=workflow.bundle_id,
            flow_id=workflow.flow_id,
            bundle_version=workflow.bundle_version,
            registry_scope=workflow.registry_scope,
            primary_image_artifact=self.latest_image_artifact(),
            debug=self.debug,
        )

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
                items.append(
                    {
                        "name": name,
                        "description": str(raw.get("description") or "").strip(),
                        "toolset": str(raw.get("toolset") or raw.get("toolset_id") or raw.get("toolsetId") or "").strip().lower(),
                        "when_to_use": str(raw.get("when_to_use") or raw.get("whenToUse") or "").strip(),
                    }
                )

        if error:
            note = error

        policy = ToolApprovalPolicy()
        safe = set(policy.auto_approve_tools)
        require = set(policy.require_approval_tools)
        saved = dict(self.preferences.tool_preferences or {})
        enriched: List[Dict[str, str]] = []
        seen: set[str] = set()
        for item in sorted(items, key=lambda entry: (str(entry.get("toolset") or ""), str(entry.get("name") or ""))):
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            if saved.get(name) in {"disabled", "approve", "ask"}:
                selected_mode = saved[name]
            elif name in require:
                selected_mode = "ask"
            elif name in safe:
                selected_mode = "approve"
            else:
                selected_mode = "ask"
            default_mode = "approve" if name in safe and name not in require else "ask"
            enriched.append(
                {
                    **item,
                    "default_mode": default_mode,
                    "selected_mode": selected_mode,
                    "policy_default": "ask" if name in require else ("approve" if name in safe else "ask"),
                }
            )
        return {"items": enriched, "tool_mode": tool_mode or "", "note": note}

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
            name = str(item.get("name") or "").strip()
            if name:
                out.append(name)
        return out

    def tool_policy_for_run(self) -> Dict[str, List[str]]:
        inventory = self.tool_inventory()
        auto: List[str] = []
        require: List[str] = []
        trust_enabled_for_chat = self.session_tool_auto_approval_active()
        for item in inventory.get("items") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            mode = str(item.get("selected_mode") or "ask").strip().lower()
            if mode == "disabled":
                continue
            if trust_enabled_for_chat or mode == "approve":
                auto.append(name)
            else:
                require.append(name)
        return {
            "auto_approve_tools": auto,
            "require_approval_tools": require,
        }

    def grant_session_tool_auto_approval(self, *, session_id: Optional[str] = None) -> None:
        sid = str(session_id or self.active_session_id or "").strip()
        if sid:
            self._session_auto_approve_all.add(sid)

    def session_tool_auto_approval_active(self, *, session_id: Optional[str] = None) -> bool:
        sid = str(session_id or self.active_session_id or "").strip()
        return bool(sid and sid in self._session_auto_approve_all)

    def should_auto_approve_tool_batch(self, tool_calls: Any, *, session_id: Optional[str] = None) -> bool:
        if not self.session_tool_auto_approval_active(session_id=session_id):
            return False
        if not isinstance(tool_calls, list) or not tool_calls:
            return False
        allowed = set(self.allowed_tools_for_run())
        if not allowed:
            return False
        for call in tool_calls:
            if not isinstance(call, dict):
                return False
            name = str(call.get("name") or "").strip()
            if not name or name not in allowed:
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
            raise ValueError("artifact_id is required")
        rid = str(run_id or "").strip()
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

    def append_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.llm_manager.append_message(role="user", content=content, metadata=metadata)

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
                    call_id = str(call.get("call_id") or call.get("id") or "").strip()
                    key = call_id or f"{rid}:{len(out)}:{call.get('name')}"
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
        try:
            voice_row = self.route_map().get("output.voice")
        except Exception:
            voice_row = None
        current_tts_provider = ""
        current_tts_model = ""
        current_tts_voice = ""
        current_tts_voice_mode = "profile"
        if voice_row is not None:
            current_tts_provider = str(voice_row.provider or "").strip()
            current_tts_model = str(voice_row.model or "").strip()
            current_tts_voice = str((voice_row.options or {}).get("voice") or (voice_row.options or {}).get("profile") or "").strip()
        setattr(self.llm_manager, "current_tts_provider", current_tts_provider)
        setattr(self.llm_manager, "current_tts_model", current_tts_model)
        setattr(self.llm_manager, "current_tts_voice", current_tts_voice)
        setattr(self.llm_manager, "current_tts_voice_mode", current_tts_voice_mode)

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
