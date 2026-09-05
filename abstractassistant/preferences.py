"""Durable local preferences for AbstractAssistant.

Gateway owns provider/model/media defaults. The desktop client only persists
local UX concerns plus device-side tool gating.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from abstractassistant.config import DEFAULT_GATEWAY_URL


# Reasoning effort ladder — the gateway contract's `thinking_control.values`
# (`contracts.common.runs.start.thinking_control`). The live list is preferred
# when the gateway advertises one; this is the offline fallback and validator.
# "" (empty) always means "gateway default: send nothing".
REASONING_EFFORT_LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh")

# Workspace access modes accepted by the gateway
# (`routes/gateway.py::_VALID_WORKSPACE_ACCESS_MODES`). "" means server-managed:
# the run carries no mode and the gateway decides.
WORKSPACE_ACCESS_MODES = ("workspace_only", "workspace_or_allowed", "all_except_ignored")


def normalize_reasoning_effort(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in REASONING_EFFORT_LEVELS else ""


def normalize_workspace_access_mode(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in WORKSPACE_ACCESS_MODES else ""


VOICE_MODES = ("wait", "full")


def normalize_voice_mode(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in VOICE_MODES else "wait"


def normalize_workspace_path(raw: Any, *, home: Optional[Path] = None) -> str:
    """Canonical absolute path for a workspace entry, or "" when unusable.

    The gateway resolves these paths on ITS host, so a relative path is
    ambiguous and is refused here rather than sent. ``~`` expands against the
    local home (the assistant runs on the same machine as a local gateway; a
    remote gateway sees the literal absolute path, which the Workspace settings
    say plainly). Trailing slashes are dropped so ``/srv/data/`` and
    ``/srv/data`` are one entry; the root ``/`` is preserved.
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    base = Path(home) if home is not None else Path.home()
    if text == "~":
        text = str(base)
    elif text.startswith("~/"):
        text = str(base / text[2:])
    elif text.startswith("~"):
        return ""
    if not text.startswith("/"):
        return ""
    trimmed = text.rstrip("/")
    return trimmed or "/"


def _normalize_workspace_paths(raw: Any) -> List[str]:
    if isinstance(raw, str):
        items: List[Any] = [line for line in raw.splitlines()]
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        return []
    out: List[str] = []
    for item in items:
        path = normalize_workspace_path(item)
        if path and path not in out:
            out.append(path)
    return out[:32]


# Capability routes the thin client can locally override AND actually applies.
# Chat text rides the run input (top-level provider/model + _runtime); voice is
# applied per TTS/STT call in the voice manager; media routes ride dedicated
# input pins on the managed orchestrator workflow (generate_image/edit/upscale/
# video/image_to_video/music nodes accept per-run provider+model, and the sound
# node takes a full output spec) — the override reaches exactly one run and the
# gateway's own defaults are never written. 3D (output.scene3d.*) is NOT here:
# the runtime has no scene3d workflow node yet, so the assistant cannot trigger
# (or override) 3D generation — add it when that node ships.
# Embedding/rerank stay out: the assistant never issues those calls.
LOCAL_OVERRIDE_ROUTE_KEYS = (
    "output.text",
    "output.voice",
    "input.voice",
    "output.image.text_to_image",
    "output.image.image_to_image",
    "output.image.image_upscale",
    "output.video.text_to_video",
    "output.video.image_to_video",
    "output.music",
    "output.sound",
)


def _normalize_route_overrides(raw: Any) -> Dict[str, Dict[str, Any]]:
    """Coerce persisted route overrides to {route_key: {provider, model, base_url, options}}.

    An override is only kept when it carries a non-empty provider AND model —
    a half-specified override is indistinguishable from "use gateway default"
    and would silently send a broken pin.
    """
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for key, value in raw.items():
        route_key = str(key or "").strip()
        if route_key not in LOCAL_OVERRIDE_ROUTE_KEYS or not isinstance(value, dict):
            continue
        provider = str(value.get("provider") or "").strip()
        model = str(value.get("model") or "").strip()
        if not provider or not model:
            continue
        options = value.get("options")
        entry: Dict[str, Any] = {"provider": provider, "model": model}
        base_url = str(value.get("base_url") or "").strip()
        if base_url:
            entry["base_url"] = base_url
        if isinstance(options, dict) and options:
            entry["options"] = dict(options)
        out[route_key] = entry
    return out


@dataclass(frozen=True)
class AssistantPreferences:
    hotkey_enabled: bool = True
    hotkey_sequence: str = "cmd+shift+space"
    auto_speak: bool = False
    # Voice latency vs quality: "low" synthesizes faster (fewer diffusion
    # steps → quicker first audio), "high" is richer, "standard" is balanced.
    voice_quality: str = "standard"
    window_width: int = 500
    window_height: int = 336
    bottom_offset: int = 18
    tool_preferences: Dict[str, str] = field(default_factory=dict)
    # LOCAL overrides of the gateway's capability defaults, for THIS app only.
    # The gateway's global defaults are never mutated by the assistant — an
    # empty map means "use whatever the gateway resolves".
    route_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Reasoning effort for the chat model, sent as `_runtime.thinking` on every
    # run. "" = gateway default (nothing sent). AbstractCore maps a level the
    # model cannot honor onto its nearest supported level (with a warning), so
    # a stale choice degrades, never fails.
    reasoning_effort: str = ""
    # Local workspace scope for the run's tools, sent as the run-input pins
    # `workspace_root` / `workspace_access_mode` / `workspace_allowed_paths`.
    # The gateway sanitizes and may clamp them; blanks mean "server-managed".
    workspace_root: str = ""
    workspace_access_mode: str = ""
    workspace_allowed_paths: List[str] = field(default_factory=list)
    # Hands-free voice conversation: send each utterance automatically (off =
    # transcribe into the composer and wait for Enter) and ask the model for
    # short spoken-style replies while the conversation is on.
    voice_auto_send: bool = True
    voice_spoken_replies: bool = True
    # Microphone gating while the assistant speaks: "wait" pauses capture
    # (speakers: the assistant never transcribes itself; no barge-in), "full"
    # keeps the mic open so a spoken "stop" interrupts (headphones).
    voice_mode: str = "wait"

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AssistantPreferences":
        if not isinstance(raw, dict):
            return cls()
        tool_preferences_raw = raw.get("tool_preferences")
        if not isinstance(tool_preferences_raw, dict):
            tool_preferences_raw = {}
        voice_quality = str(raw.get("voice_quality") or "standard").strip().lower()
        if voice_quality not in {"low", "standard", "high"}:
            voice_quality = "standard"
        return cls(
            hotkey_enabled=bool(raw.get("hotkey_enabled", True)),
            hotkey_sequence=str(raw.get("hotkey_sequence") or "cmd+shift+space").strip() or "cmd+shift+space",
            auto_speak=bool(raw.get("auto_speak", False)),
            voice_quality=voice_quality,
            window_width=max(420, int(raw.get("window_width") or 500)),
            window_height=max(240, int(raw.get("window_height") or 336)),
            bottom_offset=max(0, int(raw.get("bottom_offset") or 18)),
            tool_preferences={
                str(name).strip(): str(mode).strip().lower()
                for name, mode in tool_preferences_raw.items()
                if str(name).strip() and str(mode).strip().lower() in {"disabled", "approve", "ask"}
            },
            route_overrides=_normalize_route_overrides(raw.get("route_overrides")),
            reasoning_effort=normalize_reasoning_effort(raw.get("reasoning_effort")),
            workspace_root=normalize_workspace_path(raw.get("workspace_root")),
            workspace_access_mode=normalize_workspace_access_mode(raw.get("workspace_access_mode")),
            workspace_allowed_paths=_normalize_workspace_paths(raw.get("workspace_allowed_paths")),
            voice_auto_send=bool(raw.get("voice_auto_send", True)),
            voice_spoken_replies=bool(raw.get("voice_spoken_replies", True)),
            voice_mode=normalize_voice_mode(raw.get("voice_mode")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hotkey_enabled": bool(self.hotkey_enabled),
            "hotkey_sequence": str(self.hotkey_sequence or "").strip() or "cmd+shift+space",
            "auto_speak": bool(self.auto_speak),
            "voice_quality": str(self.voice_quality or "standard").strip().lower() or "standard",
            "window_width": int(self.window_width),
            "window_height": int(self.window_height),
            "bottom_offset": int(self.bottom_offset),
            "tool_preferences": {
                str(name).strip(): str(mode).strip().lower()
                for name, mode in self.tool_preferences.items()
                if str(name).strip() and str(mode).strip().lower() in {"disabled", "approve", "ask"}
            },
            "route_overrides": _normalize_route_overrides(self.route_overrides),
            "reasoning_effort": normalize_reasoning_effort(self.reasoning_effort),
            "workspace_root": normalize_workspace_path(self.workspace_root),
            "workspace_access_mode": normalize_workspace_access_mode(self.workspace_access_mode),
            "workspace_allowed_paths": _normalize_workspace_paths(self.workspace_allowed_paths),
            "voice_auto_send": bool(self.voice_auto_send),
            "voice_spoken_replies": bool(self.voice_spoken_replies),
            "voice_mode": normalize_voice_mode(self.voice_mode),
        }

    def run_scope(self) -> Dict[str, Any]:
        """The per-run pins derived from these preferences (blank = omitted)."""
        return {
            "thinking": normalize_reasoning_effort(self.reasoning_effort),
            "workspace_root": normalize_workspace_path(self.workspace_root),
            "workspace_access_mode": normalize_workspace_access_mode(self.workspace_access_mode),
            "workspace_allowed_paths": _normalize_workspace_paths(self.workspace_allowed_paths),
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
