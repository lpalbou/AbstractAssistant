"""
Runtime configuration for AbstractAssistant.

Tray mode is gateway-first and resolves gateway connection settings from launch
flags (with their legacy environment aliases). File-based `config.toml` loading
is intentionally unsupported.

Which gateway the app connects to, first match wins:

1. `--gateway-url` (legacy alias: `ABSTRACTGATEWAY_URL` / `ABSTRACTFLOW_GATEWAY_URL`);
2. the sign-in saved in Settings -> Connection (`gateway_connection.json`);
3. this computer's gateway, by the gateway's own `local_gateway()` rule, when an
   abstractgateway that provides it (0.6.0 or later) is installed in the same
   Python as the Assistant;
4. `BUILTIN_GATEWAY_URL` (http://127.0.0.1:8080).

Tier 1 is `resolve_gateway_connection()` (its `url` is empty when no flag or
env value was given), tier 2 is applied by the controller, and tiers 3-4 are
`default_gateway_url()`: consulted only when neither tier 1 nor tier 2 applies,
then cached for the process.
"""

from __future__ import annotations

import functools
import importlib
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, NamedTuple, Optional

BUILTIN_GATEWAY_URL = "http://127.0.0.1:8080"

_GATEWAY_MODULES = frozenset({"abstractgateway", "abstractgateway.first_run"})


def _gateway_local_rule() -> Optional[Callable[[], Mapping[str, Any]]]:
    """The gateway's `local_gateway()` rule, or None when this Python has none.

    None means exactly one of two things: abstractgateway is not installed next
    to the Assistant (the Assistant's own install, the frozen macOS app), or the
    installed gateway predates the rule (abstractgateway < 0.6.0 has no
    `first_run.local_gateway`). Any other failure to import an installed
    gateway (a missing dependency of the gateway, a syntax error) is raised.
    """
    try:
        first_run = importlib.import_module("abstractgateway.first_run")
    except ModuleNotFoundError as exc:
        if exc.name in _GATEWAY_MODULES:
            return None
        raise
    return getattr(first_run, "local_gateway", None)


def _local_gateway_url() -> str:
    """Tiers 3-4 of the module rule: this computer's gateway, else the built-in URL.

    The gateway's rule reads its data directory's records (the running gateway,
    a pinned OS service, the stored Network setting port), so an installer that
    moved the gateway off a busy 8080 is followed. Errors raised by the rule
    itself propagate: they belong to the gateway's install, not to this app.
    """
    rule = _gateway_local_rule()
    if rule is None:
        return BUILTIN_GATEWAY_URL
    return str(rule()["url"]).strip().rstrip("/")


@functools.lru_cache(maxsize=1)
def default_gateway_url() -> str:
    """Tiers 3-4, looked up on first use and then fixed for the process.

    Call it only when no `--gateway-url` (or env alias) and no saved sign-in
    applies: a failing gateway rule must not block a launch that names its
    gateway."""
    return _local_gateway_url()


def _env_first(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return ""


def _gateway_url_from_env() -> str:
    """The gateway URL named by the legacy env alias of `--gateway-url`, or ""."""
    return _env_first("ABSTRACTGATEWAY_URL", "ABSTRACTFLOW_GATEWAY_URL").rstrip("/")


def _gateway_auth_token_from_env() -> str:
    """Return the shared gateway auth token from the environment."""
    return _env_first("ABSTRACTGATEWAY_AUTH_TOKEN", "ABSTRACTFLOW_GATEWAY_AUTH_TOKEN")


class GatewayConnection(NamedTuple):
    """Tier 1 of the module rule: what the launch named.

    `url` is "" when neither `--gateway-url` nor its env alias was given; the
    controller then applies the saved sign-in, else `default_gateway_url()`."""

    url: str
    auth_token: str

    @property
    def url_given(self) -> bool:
        return bool(self.url)


def resolve_gateway_connection(
    *,
    url_override: str | None = None,
    auth_token_override: str | None = None,
    require_auth_token: bool = False,
) -> GatewayConnection:
    """Resolve the launch's gateway URL/token: CLI overrides first, then environment."""
    gateway_url = str(url_override or "").strip().rstrip("/") or _gateway_url_from_env()
    gateway_auth_token = str(auth_token_override or "").strip() or _gateway_auth_token_from_env()
    if require_auth_token and not gateway_auth_token:
        raise ValueError(
            "AbstractAssistant requires gateway authentication. "
            "Export ABSTRACTGATEWAY_AUTH_TOKEN or pass --gateway-token <token>."
        )
    return GatewayConnection(url=gateway_url, auth_token=gateway_auth_token)


@dataclass
class UIConfig:
    """UI configuration settings."""

    theme: str = "dark"
    bubble_size_ratio: float = 0.167
    auto_hide_delay: int = 8
    always_on_top: bool = True


@dataclass
class GatewayConfig:
    """Gateway configuration settings (the assistant is gateway-native).

    `url` is the URL the launch named ("" = none: the controller resolves it
    from the saved sign-in or `default_gateway_url()` and writes it back)."""

    url: str = field(default_factory=_gateway_url_from_env)
    auth_token: str = field(default_factory=_gateway_auth_token_from_env)
    auth_mode: str = "bearer"
    user_id: str = ""
    session_id: str = ""
    csrf_token: str = ""
    session_expires_at: str = ""
    bundle_id: str = ""
    flow_id: str = ""


@dataclass
class SystemTrayConfig:
    """System tray configuration settings."""

    icon_size: int = 64
    show_notifications: bool = True
    animation_fps: int = 30


@dataclass
class ShortcutsConfig:
    """Keyboard shortcuts configuration."""

    show_bubble: str = "cmd+shift+a"


@dataclass
class Config:
    """Main runtime configuration."""

    ui: UIConfig = field(default_factory=UIConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    system_tray: SystemTrayConfig = field(default_factory=SystemTrayConfig)
    shortcuts: ShortcutsConfig = field(default_factory=ShortcutsConfig)

    @classmethod
    def default(cls) -> "Config":
        """Create the default runtime configuration."""
        return cls.from_dict({})

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Create configuration from a dictionary."""
        ui_data = data.get("ui", {})
        gateway_data = data.get("gateway", {})
        system_tray_data = data.get("system_tray", {})
        animation_fps_raw = system_tray_data.get("animation_fps", 30)
        animation_fps = 30
        try:
            animation_fps = int(animation_fps_raw)
        except Exception:
            print(f"#FALLBACK: invalid system_tray.animation_fps={animation_fps_raw}; using 30")
            animation_fps = 30
        if animation_fps < 10:
            print(f"#FALLBACK: system_tray.animation_fps={animation_fps} too low; using 10")
            animation_fps = 10
        if animation_fps > 30:
            print(f"#FALLBACK: system_tray.animation_fps={animation_fps} too high; using 30")
            animation_fps = 30
        shortcuts_data = data.get("shortcuts", {})

        env_gateway_url = _env_first("ABSTRACTGATEWAY_URL", "ABSTRACTFLOW_GATEWAY_URL")
        configured_gateway_url = str(gateway_data.get("url", "") or "").strip()
        gateway_url, gateway_auth_token = resolve_gateway_connection(
            url_override=configured_gateway_url or env_gateway_url,
            auth_token_override=str(gateway_data.get("auth_token", "") or "").strip() or None,
        )
        return cls(
            ui=UIConfig(
                theme=ui_data.get("theme", "dark"),
                bubble_size_ratio=ui_data.get("bubble_size_ratio", 0.167),
                auto_hide_delay=ui_data.get("auto_hide_delay", 8),
                always_on_top=ui_data.get("always_on_top", True),
            ),
            gateway=GatewayConfig(
                url=gateway_url,
                auth_token=gateway_auth_token,
                auth_mode=str(gateway_data.get("auth_mode", "bearer") or "bearer").strip() or "bearer",
                user_id=str(gateway_data.get("user_id", "") or "").strip(),
                session_id=str(gateway_data.get("session_id", "") or "").strip(),
                csrf_token=str(gateway_data.get("csrf_token", "") or "").strip(),
                session_expires_at=str(gateway_data.get("session_expires_at", "") or "").strip(),
                bundle_id=str(gateway_data.get("bundle_id", "") or ""),
                flow_id=str(gateway_data.get("flow_id", "") or ""),
            ),
            system_tray=SystemTrayConfig(
                icon_size=system_tray_data.get("icon_size", 64),
                show_notifications=system_tray_data.get("show_notifications", True),
                animation_fps=animation_fps,
            ),
            shortcuts=ShortcutsConfig(
                show_bubble=shortcuts_data.get("show_bubble", "cmd+shift+a"),
            ),
        )

    def to_dict(self, *, redact_secrets: bool = True) -> Dict[str, Any]:
        """Convert configuration to a dictionary."""
        auth_token = str(self.gateway.auth_token or "")
        if redact_secrets and auth_token:
            auth_token = "<redacted>"
        session_id = str(self.gateway.session_id or "")
        csrf_token = str(self.gateway.csrf_token or "")
        if redact_secrets and session_id:
            session_id = "<redacted>"
        if redact_secrets and csrf_token:
            csrf_token = "<redacted>"
        return {
            "ui": {
                "theme": self.ui.theme,
                "bubble_size_ratio": self.ui.bubble_size_ratio,
                "auto_hide_delay": self.ui.auto_hide_delay,
                "always_on_top": self.ui.always_on_top,
            },
            "gateway": {
                "url": self.gateway.url,
                "auth_token": auth_token,
                "auth_mode": self.gateway.auth_mode,
                "user_id": self.gateway.user_id,
                "session_id": session_id,
                "csrf_token": csrf_token,
                "session_expires_at": self.gateway.session_expires_at,
                "bundle_id": self.gateway.bundle_id,
                "flow_id": self.gateway.flow_id,
            },
            "system_tray": {
                "icon_size": self.system_tray.icon_size,
                "show_notifications": self.system_tray.show_notifications,
                "animation_fps": self.system_tray.animation_fps,
            },
            "shortcuts": {
                "show_bubble": self.shortcuts.show_bubble,
            },
        }

    def validate(self) -> bool:
        """Validate configuration values."""
        errors = []

        if self.ui.theme not in ["dark", "light", "system"]:
            errors.append(f"Invalid theme: {self.ui.theme}")

        if not 0.1 <= self.ui.bubble_size_ratio <= 0.5:
            errors.append(f"Invalid bubble_size_ratio: {self.ui.bubble_size_ratio}")

        if self.ui.auto_hide_delay < 0:
            errors.append(f"Invalid auto_hide_delay: {self.ui.auto_hide_delay}")

        if str(self.gateway.auth_mode or "bearer").strip() not in {"bearer", "session"}:
            errors.append(f"Invalid gateway auth_mode: {self.gateway.auth_mode}")

        if not 16 <= self.system_tray.icon_size <= 128:
            errors.append(f"Invalid icon_size: {self.system_tray.icon_size}")

        if not 10 <= int(self.system_tray.animation_fps) <= 30:
            errors.append(f"Invalid animation_fps: {self.system_tray.animation_fps} (expected 10-30)")

        if errors:
            for error in errors:
                print(f"Config validation error: {error}")
            return False

        return True
