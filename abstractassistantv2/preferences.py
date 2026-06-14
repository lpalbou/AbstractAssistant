"""Durable local preferences for AbstractAssistant v2.

Gateway owns provider/model/media defaults. The desktop client only persists
local UX concerns plus device-side tool gating.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from abstractassistant.config import DEFAULT_GATEWAY_URL


@dataclass(frozen=True)
class AssistantPreferences:
    hotkey_enabled: bool = True
    hotkey_sequence: str = "cmd+shift+space"
    auto_speak: bool = False
    window_width: int = 500
    window_height: int = 336
    bottom_offset: int = 18
    tool_preferences: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AssistantPreferences":
        if not isinstance(raw, dict):
            return cls()
        tool_preferences_raw = raw.get("tool_preferences")
        if not isinstance(tool_preferences_raw, dict):
            tool_preferences_raw = {}
        return cls(
            hotkey_enabled=bool(raw.get("hotkey_enabled", True)),
            hotkey_sequence=str(raw.get("hotkey_sequence") or "cmd+shift+space").strip() or "cmd+shift+space",
            auto_speak=bool(raw.get("auto_speak", False)),
            window_width=max(420, int(raw.get("window_width") or 500)),
            window_height=max(240, int(raw.get("window_height") or 336)),
            bottom_offset=max(0, int(raw.get("bottom_offset") or 18)),
            tool_preferences={
                str(name).strip(): str(mode).strip().lower()
                for name, mode in tool_preferences_raw.items()
                if str(name).strip() and str(mode).strip().lower() in {"disabled", "approve", "ask"}
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hotkey_enabled": bool(self.hotkey_enabled),
            "hotkey_sequence": str(self.hotkey_sequence or "").strip() or "cmd+shift+space",
            "auto_speak": bool(self.auto_speak),
            "window_width": int(self.window_width),
            "window_height": int(self.window_height),
            "bottom_offset": int(self.bottom_offset),
            "tool_preferences": {
                str(name).strip(): str(mode).strip().lower()
                for name, mode in self.tool_preferences.items()
                if str(name).strip() and str(mode).strip().lower() in {"disabled", "approve", "ask"}
            },
        }


@dataclass(frozen=True)
class GatewayConnectionPreferences:
    base_url: str = DEFAULT_GATEWAY_URL
    auth_mode: str = "bearer"
    auth_token: str = ""
    user_id: str = ""
    session_id: str = ""
    csrf_token: str = ""
    session_expires_at: str = ""
    remember_session: bool = True

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "GatewayConnectionPreferences":
        if not isinstance(raw, dict):
            return cls()
        auth_mode = str(raw.get("auth_mode") or "bearer").strip().lower() or "bearer"
        if auth_mode not in {"bearer", "session"}:
            auth_mode = "bearer"
        return cls(
            base_url=str(raw.get("base_url") or DEFAULT_GATEWAY_URL).strip().rstrip("/") or DEFAULT_GATEWAY_URL,
            auth_mode=auth_mode,
            auth_token=str(raw.get("auth_token") or "").strip(),
            user_id=str(raw.get("user_id") or "").strip(),
            session_id=str(raw.get("session_id") or "").strip(),
            csrf_token=str(raw.get("csrf_token") or "").strip(),
            session_expires_at=str(raw.get("session_expires_at") or "").strip(),
            remember_session=bool(raw.get("remember_session", True)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_url": str(self.base_url or "").strip().rstrip("/") or DEFAULT_GATEWAY_URL,
            "auth_mode": str(self.auth_mode or "bearer").strip() or "bearer",
            "auth_token": str(self.auth_token or "").strip(),
            "user_id": str(self.user_id or "").strip(),
            "session_id": str(self.session_id or "").strip(),
            "csrf_token": str(self.csrf_token or "").strip(),
            "session_expires_at": str(self.session_expires_at or "").strip(),
            "remember_session": bool(self.remember_session),
        }


@dataclass(frozen=True)
class WorkflowSelection:
    bundle_id: str = ""
    flow_id: str = ""
    bundle_version: str = ""
    registry_scope: str = "tenant_catalog"

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> Optional["WorkflowSelection"]:
        if not isinstance(raw, dict):
            return None
        bundle_id = str(raw.get("bundle_id") or "").strip()
        flow_id = str(raw.get("flow_id") or "").strip()
        bundle_version = str(raw.get("bundle_version") or "").strip()
        registry_scope = str(raw.get("registry_scope") or "tenant_catalog").strip() or "tenant_catalog"
        if not bundle_id and not flow_id and not bundle_version:
            return None
        return cls(
            bundle_id=bundle_id,
            flow_id=flow_id,
            bundle_version=bundle_version,
            registry_scope=registry_scope,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "flow_id": self.flow_id,
            "bundle_version": self.bundle_version,
            "registry_scope": self.registry_scope,
        }


class JsonStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def _read(self) -> Optional[Dict[str, Any]]:
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return raw if isinstance(raw, dict) else None

    def _write(self, payload: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self._path)
        try:
            self._path.chmod(0o600)
        except Exception:
            pass


class PreferencesStore(JsonStore):
    def load(self) -> AssistantPreferences:
        return AssistantPreferences.from_dict(self._read() or {})

    def save(self, prefs: AssistantPreferences) -> None:
        self._write(prefs.to_dict())


class GatewayConnectionStore(JsonStore):
    def load(self) -> GatewayConnectionPreferences:
        return GatewayConnectionPreferences.from_dict(self._read() or {})

    def save(self, connection: GatewayConnectionPreferences) -> None:
        self._write(connection.to_dict())
