"""
Configuration management for AbstractAssistant.

Handles loading and managing TOML configuration files with proper defaults
and validation.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w


@dataclass
class UIConfig:
    """UI configuration settings."""
    theme: str = "dark"
    bubble_size_ratio: float = 0.167
    auto_hide_delay: int = 8
    always_on_top: bool = True


@dataclass
class LLMConfig:
    """LLM configuration settings."""
    default_provider: str = "lmstudio"
    default_model: str = "qwen/qwen3-next-80b"
    max_tokens: int = 32000
    temperature: float = 0.7


@dataclass
class GatewayConfig:
    """Gateway configuration settings (thin-client mode)."""

    url: str = ""
    auth_token: str = ""
    use_gateway: bool = False
    bundle_id: str = "basic-agent"
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
    """Main configuration class."""
    ui: UIConfig = field(default_factory=UIConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    system_tray: SystemTrayConfig = field(default_factory=SystemTrayConfig)
    shortcuts: ShortcutsConfig = field(default_factory=ShortcutsConfig)
    
    @classmethod
    def default(cls) -> "Config":
        """Create a default configuration."""
        return cls()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Create configuration from dictionary."""
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
        
        gateway_url = str(gateway_data.get("url", "") or "")
        raw_use_gateway = gateway_data.get("use_gateway", False)
        use_gateway = bool(raw_use_gateway)
        if isinstance(raw_use_gateway, str):
            raw = raw_use_gateway.strip().lower()
            if raw in {"true", "1", "yes", "y"}:
                use_gateway = True
            elif raw in {"false", "0", "no", "n"}:
                use_gateway = False
        if gateway_url.strip() and not use_gateway:
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
                default_provider=llm_data.get("default_provider", "lmstudio"),
                default_model=llm_data.get("default_model", "qwen/qwen3-next-80b"),
                max_tokens=llm_data.get("max_tokens", 32000),
                temperature=llm_data.get("temperature", 0.7),
            ),
            gateway=GatewayConfig(
                url=gateway_url,
                auth_token=gateway_data.get("auth_token", ""),
                use_gateway=use_gateway,
                bundle_id=gateway_data.get("bundle_id", "basic-agent"),
                flow_id=gateway_data.get("flow_id", ""),
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
    
    @classmethod
    def from_file(cls, config_path: Path) -> "Config":
        """Load configuration from TOML file."""
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print(f"Warning: Failed to load config from {config_path}: {e}")
            print("Using default configuration.")
            return cls.default()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
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
                "auth_token": self.gateway.auth_token,
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
    
    def save_to_file(self, config_path: Path) -> None:
        """Save configuration to TOML file."""
        try:
            with open(config_path, "wb") as f:
                tomli_w.dump(self.to_dict(), f)
        except Exception as e:
            print(f"Warning: Failed to save config to {config_path}: {e}")
    
    def validate(self) -> bool:
        """Validate configuration values."""
        errors = []
        
        # Validate UI settings
        if self.ui.theme not in ["dark", "light", "system"]:
            errors.append(f"Invalid theme: {self.ui.theme}")
        
        if not 0.1 <= self.ui.bubble_size_ratio <= 0.5:
            errors.append(f"Invalid bubble_size_ratio: {self.ui.bubble_size_ratio}")
        
        if self.ui.auto_hide_delay < 0:
            errors.append(f"Invalid auto_hide_delay: {self.ui.auto_hide_delay}")
        
        # Validate LLM settings
        # Provider validation is handled by AbstractCore's provider discovery system
        # No need to hardcode valid providers here
        
        if not 0.0 <= self.llm.temperature <= 2.0:
            errors.append(f"Invalid temperature: {self.llm.temperature}")
        
        if self.llm.max_tokens < 1000:
            errors.append(f"Invalid max_tokens: {self.llm.max_tokens}")

        # Validate gateway settings
        if self.gateway.use_gateway and not str(self.gateway.url or "").strip():
            errors.append("Gateway URL is required when use_gateway=true")
        
        # Validate system tray settings
        if not 16 <= self.system_tray.icon_size <= 128:
            errors.append(f"Invalid icon_size: {self.system_tray.icon_size}")

        if not 10 <= int(self.system_tray.animation_fps) <= 30:
            errors.append(f"Invalid animation_fps: {self.system_tray.animation_fps} (expected 10-30)")
        
        if errors:
            for error in errors:
                print(f"Config validation error: {error}")
            return False
        
        return True
