"""Durable local preferences for AbstractAssistant.

Gateway owns provider/model/media defaults. The desktop client only persists
local UX concerns plus device-side tool gating.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from abstractassistant.speculation import normalize_speculation


def _load_speculation(value: Any) -> Any:
    """A saved MTP choice that no longer validates falls back to inheriting
    the gateway default instead of making the preferences file unloadable."""
    try:
        return normalize_speculation(value)
    except ValueError:
        return None


# "Stream replies" (R11.4): a plain switch, on by default. Streaming is
# app-specific, so every run says so explicitly — `_runtime.stream: true|false`
# — and the gateway's own default ("Streamed replies", Workflows → Settings)
# only applies to clients that do not say. Older files that saved
# "gateway_default" (the removed third choice) load as on.
STREAM_REPLIES_CHOICES = ("on", "off")
STREAM_REPLIES_DEFAULT = "on"


def normalize_stream_replies(value: Any) -> str:
    """"off" stays off; anything else (incl. a legacy "gateway_default") is on."""
    if value is False:
        return "off"
    text = str(value or "").strip().lower()
    return "off" if text == "off" else STREAM_REPLIES_DEFAULT


def stream_replies_runtime_value(value: Any) -> bool:
    """The `_runtime.stream` value for a choice: always a bool."""
    return normalize_stream_replies(value) == "on"


# Reasoning effort ladder — the gateway contract's `thinking_control.values`
# (`contracts.common.runs.start.thinking_control`). The live list is preferred
# when the gateway advertises one; this is the offline fallback and validator.
# "" (empty) always means "gateway default: send nothing".
REASONING_EFFORT_LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh")

def normalize_reasoning_effort(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in REASONING_EFFORT_LEVELS else ""


VOICE_MODES = ("wait", "full")


def _clamp_int(raw: Any, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(raw)))
    except (TypeError, ValueError):
        return default


def _clamp_float(raw: Any, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, round(float(raw), 2)))
    except (TypeError, ValueError):
        return default


#: Bumped when a layout change must retune a size a user already saved.
#: 1 (2026-09-06): heights saved before it shrink by 15%.
#: 2 (2026-09-25): the default width 500 -> 650 and screen-edge gap 18 -> 28.
#: (2026-09-27: the default gap is 12; no version bump — a saved gap is kept.)
LAYOUT_VERSION = 2

DEFAULT_WINDOW_WIDTH = 650
DEFAULT_WINDOW_HEIGHT = 286
DEFAULT_SCREEN_EDGE_GAP = 12
#: What Settings accepts. The window itself is then limited only by the screen
#: it is on (see AssistantPalette._reflow_shell / _screen_edge_gap).
WINDOW_WIDTH_RANGE = (420, 2000)
SCREEN_EDGE_GAP_RANGE = (0, 200)
#: The defaults before layout version 2. A file older than v2 that still holds
#: exactly one of these never had it changed by hand (Settings only offers the
#: value the user types), so it moves to the new default; anything else is the
#: user's choice and is kept.
_V1_DEFAULT_WINDOW_WIDTH = 500
_V1_DEFAULT_SCREEN_EDGE_GAP = 18


def _saved_layout_version(raw: Dict[str, Any]) -> int:
    try:
        return int(raw.get("layout_version") or 0)
    except (TypeError, ValueError):
        return 0


def _migrated_window_height(raw: Dict[str, Any]) -> int:
    """The saved window height, shortened once when the layout got tighter.

    Applied on read and stamped with `LAYOUT_VERSION` on write, so a height the
    user chose is adjusted exactly once — never every launch. A height typed
    into Settings afterwards is theirs and is left alone.
    """
    stored = raw.get("window_height")
    height = max(240, int(stored or DEFAULT_WINDOW_HEIGHT))
    if stored and _saved_layout_version(raw) < 1:
        height = max(240, int(round(height * 0.85)))
    return height


def _migrated_window_width(raw: Dict[str, Any]) -> int:
    """The saved width; the old default (500) becomes the new one (650) once."""
    stored = raw.get("window_width")
    if stored is None or stored == "":
        return DEFAULT_WINDOW_WIDTH
    try:
        width = int(stored)
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_WIDTH
    if _saved_layout_version(raw) < 2 and width == _V1_DEFAULT_WINDOW_WIDTH:
        return DEFAULT_WINDOW_WIDTH
    return max(WINDOW_WIDTH_RANGE[0], min(WINDOW_WIDTH_RANGE[1], width))


def _migrated_screen_edge_gap(raw: Dict[str, Any]) -> int:
    """The saved screen-edge gap. 0 is a real choice (flush with the edge) and
    stays 0; the old default (18) becomes the current default once."""
    stored = raw.get("bottom_offset")
    if stored is None or stored == "":
        return DEFAULT_SCREEN_EDGE_GAP
    try:
        gap = int(stored)
    except (TypeError, ValueError):
        return DEFAULT_SCREEN_EDGE_GAP
    if _saved_layout_version(raw) < 2 and gap == _V1_DEFAULT_SCREEN_EDGE_GAP:
        return DEFAULT_SCREEN_EDGE_GAP
    return max(SCREEN_EDGE_GAP_RANGE[0], min(SCREEN_EDGE_GAP_RANGE[1], gap))


#: The workflow choice that means "whatever the gateway's operator set as the
#: default for the assistant interface" (contract D). Persisted as this
#: sentinel, never as a copied id, so a later change on the gateway applies to
#: the next turn.
WORKFLOW_GATEWAY_DEFAULT = "@default"


def normalize_workflow_choice(raw: Any) -> Any:
    """``"@default"`` or ``{"bundle_id", "flow_id", "registry_scope"}``.

    A chosen workflow is stored WITHOUT a version: it means "the latest
    published version of that workflow", so a republish does not strand it.
    """
    if isinstance(raw, dict):
        bundle_id = str(raw.get("bundle_id") or "").strip()
        flow_id = str(raw.get("flow_id") or "").strip()
        if bundle_id and flow_id and flow_id != WORKFLOW_GATEWAY_DEFAULT:
            return {
                "bundle_id": bundle_id,
                "flow_id": flow_id,
                "registry_scope": str(raw.get("registry_scope") or "tenant_catalog").strip() or "tenant_catalog",
            }
    return WORKFLOW_GATEWAY_DEFAULT


def normalize_ui_theme(raw: Any) -> str:
    """The saved colour theme id, or the app's own theme when unknown.

    A theme that has been renamed or removed upstream must not brick the UI,
    so anything unrecognized falls back to the app's own palette.
    """
    from .ui_themes import DEFAULT_THEME_ID, THEME_SPECS

    text = str(raw or "").strip().lower()
    if text and (text == DEFAULT_THEME_ID or text in THEME_SPECS):
        return text
    return DEFAULT_THEME_ID


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
    window_width: int = DEFAULT_WINDOW_WIDTH
    # 2026-09-06: the shell was 15% taller than the content needed.
    window_height: int = DEFAULT_WINDOW_HEIGHT
    # The "Screen edge gap" setting: space kept between the window and the
    # screen edges it is anchored to (historical field name).
    bottom_offset: int = DEFAULT_SCREEN_EDGE_GAP
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
    speculation: Optional[Any] = None  # None inherits; False pins MTP off.
    # "Stream replies" switch: "on" (default) | "off", sent with every run.
    stream_replies: str = STREAM_REPLIES_DEFAULT
    # No run-workspace preference (R11): a run's private workspace is the
    # gateway's (automatic, per chat), and which other workspaces it may use
    # is chosen in the gateway — Settings → Workspace "My default workspaces"
    # (account) and "This chat" (session). A `workspace_root` left in an older
    # preferences.json is ignored, never sent.
    # Hands-free voice conversation: send each utterance automatically (off =
    # transcribe into the composer and wait for Enter) and ask the model for
    # short spoken-style replies while the conversation is on.
    voice_auto_send: bool = True
    voice_spoken_replies: bool = True
    # Microphone gating while the assistant speaks: "wait" pauses capture
    # (speakers: the assistant never transcribes itself; no barge-in), "full"
    # keeps the mic open so a spoken "stop" interrupts (headphones).
    voice_mode: str = "wait"
    # WHICH SPEAKER spoken replies come out of. "" follows the Mac's current
    # default output; otherwise a device UID (`BuiltInSpeakerDevice`,
    # `AppleUSBAudioEngine:XREAL:…`), which survives reboots and reconnections in a
    # way an index never does. A pinned device that is not connected falls back to
    # the system default AND says so — it never plays somewhere else in silence.
    audio_output_device: str = ""
    # The device's human name as it was when chosen, so Settings can show
    # "Sony WH-1000XM5 (not connected)" instead of a bare UID.
    audio_output_device_name: str = ""
    # Colour theme, shared with the framework's other clients (see ui_themes).
    ui_theme: str = "abstract-glass"
    # Reading comfort in the transcript. Sizes are px, line height is a
    # multiplier; the gaps are the space after a paragraph and between list
    # items. Defaults are the app's tuned rhythm.
    text_size: int = 13
    line_spacing: float = 1.20
    paragraph_spacing: int = 3
    bullet_spacing: int = 3
    # Which assistant workflow runs each turn: WORKFLOW_GATEWAY_DEFAULT (the
    # gateway's default for `abstractassistant.agent.v1`, or the built-in
    # orchestrator when the gateway sets none) or a chosen
    # {bundle_id, flow_id, registry_scope} from the catalog.
    workflow: Any = WORKFLOW_GATEWAY_DEFAULT
    # Bumped when a layout change should retune sizes a user already saved.
    # New objects are already current — only a STORED file without the marker
    # is migrated, and `to_dict` stamps it, so it can never compound.
    layout_version: int = LAYOUT_VERSION

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
            window_width=_migrated_window_width(raw),
            window_height=_migrated_window_height(raw),
            bottom_offset=_migrated_screen_edge_gap(raw),
            tool_preferences={
                str(name).strip(): str(mode).strip().lower()
                for name, mode in tool_preferences_raw.items()
                if str(name).strip() and str(mode).strip().lower() in {"disabled", "approve", "ask"}
            },
            route_overrides=_normalize_route_overrides(raw.get("route_overrides")),
            reasoning_effort=normalize_reasoning_effort(raw.get("reasoning_effort")),
            speculation=_load_speculation(raw.get("speculation")),
            stream_replies=normalize_stream_replies(raw.get("stream_replies")),
            voice_auto_send=bool(raw.get("voice_auto_send", True)),
            voice_spoken_replies=bool(raw.get("voice_spoken_replies", True)),
            voice_mode=normalize_voice_mode(raw.get("voice_mode")),
            audio_output_device=str(raw.get("audio_output_device") or "").strip(),
            audio_output_device_name=str(raw.get("audio_output_device_name") or "").strip(),
            ui_theme=normalize_ui_theme(raw.get("ui_theme")),
            text_size=_clamp_int(raw.get("text_size"), 13, 10, 22),
            line_spacing=_clamp_float(raw.get("line_spacing"), 1.20, 1.0, 2.2),
            paragraph_spacing=_clamp_int(raw.get("paragraph_spacing"), 3, 0, 28),
            bullet_spacing=_clamp_int(raw.get("bullet_spacing"), 3, 0, 16),
            workflow=normalize_workflow_choice(raw.get("workflow")),
            layout_version=LAYOUT_VERSION,
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
            **({"speculation": normalize_speculation(self.speculation)} if self.speculation is not None else {}),
            "stream_replies": normalize_stream_replies(self.stream_replies),
            "voice_auto_send": bool(self.voice_auto_send),
            "voice_spoken_replies": bool(self.voice_spoken_replies),
            "voice_mode": normalize_voice_mode(self.voice_mode),
            "audio_output_device": str(self.audio_output_device or "").strip(),
            "audio_output_device_name": str(self.audio_output_device_name or "").strip(),
            "ui_theme": normalize_ui_theme(self.ui_theme),
            "text_size": _clamp_int(self.text_size, 13, 10, 22),
            "line_spacing": _clamp_float(self.line_spacing, 1.20, 1.0, 2.2),
            "paragraph_spacing": _clamp_int(self.paragraph_spacing, 3, 0, 28),
            "bullet_spacing": _clamp_int(self.bullet_spacing, 3, 0, 16),
            "workflow": normalize_workflow_choice(self.workflow),
            "layout_version": LAYOUT_VERSION,
        }

    def run_scope(self) -> Dict[str, Any]:
        """The per-run pins derived from these preferences (blank = omitted)."""
        return {
            "thinking": normalize_reasoning_effort(self.reasoning_effort),
            **({"speculation": normalize_speculation(self.speculation)} if self.speculation is not None else {}),
            "stream": stream_replies_runtime_value(self.stream_replies),
        }


@dataclass(frozen=True)
class GatewayConnectionPreferences:
    # "" only for a saved file that names no gateway; the controller resolves it.
    base_url: str = ""
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
            base_url=str(raw.get("base_url") or "").strip().rstrip("/"),
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
            "base_url": str(self.base_url or "").strip().rstrip("/"),
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
    """The workflow a run starts with.

    ``flow_id == WORKFLOW_GATEWAY_DEFAULT`` (with ``interface``) asks the
    gateway to resolve its stored default at run start; the bundle fields then
    only describe what it reported (for display). ``source`` is
    ``gateway_default`` | ``built_in`` | ``chosen``.
    """

    bundle_id: str = ""
    flow_id: str = ""
    bundle_version: str = ""
    registry_scope: str = "tenant_catalog"
    interface: str = field(default="", compare=False)
    label: str = field(default="", compare=False)
    source: str = field(default="", compare=False)

    @property
    def is_gateway_default(self) -> bool:
        return self.flow_id == WORKFLOW_GATEWAY_DEFAULT

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
