"""
Runtime configuration for AbstractAssistant.

Tray mode is gateway-first and resolves gateway connection settings from the
environment. File-based `config.toml` loading is intentionally unsupported.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


DEFAULT_GATEWAY_URL = "http://127.0.0.1:8080"


def _env_first(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return ""


def _gateway_url_from_env() -> str:
    """Return the configured gateway URL, or the local default."""
    return _env_first("ABSTRACTGATEWAY_URL", "ABSTRACTFLOW_GATEWAY_URL") or DEFAULT_GATEWAY_URL


def _gateway_auth_token_from_env() -> str:
    """Return the shared gateway auth token from the environment."""
    return _env_first("ABSTRACTGATEWAY_AUTH_TOKEN", "ABSTRACTFLOW_GATEWAY_AUTH_TOKEN")


def resolve_gateway_connection(
    *,
    url_override: str | None = None,
    auth_token_override: str | None = None,
    require_auth_token: bool = False,
) -> Tuple[str, str]:
    """Resolve gateway URL/token using CLI overrides first, then environment."""
    gateway_url = str(url_override or "").strip().rstrip("/") or _gateway_url_from_env()
    gateway_auth_token = str(auth_token_override or "").strip() or _gateway_auth_token_from_env()
    if require_auth_token and not gateway_auth_token:
        raise ValueError(
            "AbstractAssistant requires gateway authentication. "
            "Export ABSTRACTGATEWAY_AUTH_TOKEN or pass --gateway-token <token>."
        )
    return gateway_url or DEFAULT_GATEWAY_URL, gateway_auth_token


@dataclass
class UIConfig:
    """UI configuration settings."""

    theme: str = "dark"
    bubble_size_ratio: float = 0.167
    auto_hide_delay: int = 8
    always_on_top: bool = True


@dataclass
class LLMConfig:
    """Local-mode configuration settings."""

    default_provider: str = ""
    default_model: str = ""
    max_tokens: int = 32000
    temperature: float = 0.7


@dataclass
class GatewayConfig:
    """Gateway configuration settings (thin-client mode)."""

    url: str = field(default_factory=_gateway_url_from_env)
    auth_token: str = field(default_factory=_gateway_auth_token_from_env)
    auth_mode: str = "bearer"
    user_id: str = ""
    session_id: str = ""
    csrf_token: str = ""
    session_expires_at: str = ""
    use_gateway: bool = True
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
    llm: LLMConfig = field(default_factory=LLMConfig)
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
        llm_data = data.get("llm", {})
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
        raw_use_gateway = gateway_data.get("use_gateway", True)
        use_gateway = bool(raw_use_gateway)
        if isinstance(raw_use_gateway, str):
            raw = raw_use_gateway.strip().lower()
            if raw in {"true", "1", "yes", "y"}:
                use_gateway = True
            elif raw in {"false", "0", "no", "n"}:
                use_gateway = False
        if (env_gateway_url or configured_gateway_url) and not use_gateway:
            print("#FALLBACK: gateway.url is set but use_gateway=false; enabling gateway mode")
            use_gateway = True
        return cls(
            ui=UIConfig(
                theme=ui_data.get("theme", "dark"),
                bubble_size_ratio=ui_data.get("bubble_size_ratio", 0.167),
                auto_hide_delay=ui_data.get("auto_hide_delay", 8),
                always_on_top=ui_data.get("always_on_top", True),
            ),
            llm=LLMConfig(
                default_provider=str(llm_data.get("default_provider", "") or "").strip(),
                default_model=str(llm_data.get("default_model", "") or "").strip(),
                max_tokens=llm_data.get("max_tokens", 32000),
                temperature=llm_data.get("temperature", 0.7),
            ),
            gateway=GatewayConfig(
                url=gateway_url or DEFAULT_GATEWAY_URL,
                auth_token=gateway_auth_token,
                auth_mode=str(gateway_data.get("auth_mode", "bearer") or "bearer").strip() or "bearer",
                user_id=str(gateway_data.get("user_id", "") or "").strip(),
                session_id=str(gateway_data.get("session_id", "") or "").strip(),
                csrf_token=str(gateway_data.get("csrf_token", "") or "").strip(),
                session_expires_at=str(gateway_data.get("session_expires_at", "") or "").strip(),
                use_gateway=use_gateway,
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
            "llm": {
                "default_provider": self.llm.default_provider,
                "default_model": self.llm.default_model,
                "max_tokens": self.llm.max_tokens,
                "temperature": self.llm.temperature,
            },
            "gateway": {
                "url": self.gateway.url,
                "auth_token": auth_token,
                "auth_mode": self.gateway.auth_mode,
                "user_id": self.gateway.user_id,
                "session_id": session_id,
                "csrf_token": csrf_token,
                "session_expires_at": self.gateway.session_expires_at,
                "use_gateway": self.gateway.use_gateway,
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

        if not 0.0 <= self.llm.temperature <= 2.0:
            errors.append(f"Invalid temperature: {self.llm.temperature}")

        if self.llm.max_tokens < 1000:
            errors.append(f"Invalid max_tokens: {self.llm.max_tokens}")

        if self.gateway.use_gateway and not str(self.gateway.url or "").strip():
            errors.append("Gateway URL is required when use_gateway=true")

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
