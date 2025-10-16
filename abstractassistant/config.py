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
    default_provider: str = "openai"
    default_model: str = "gpt-4o-mini"
    max_tokens: int = 32000
    temperature: float = 0.7


@dataclass
class SystemTrayConfig:
    """System tray configuration settings."""
    icon_size: int = 64
    show_notifications: bool = True


@dataclass
class ShortcutsConfig:
    """Keyboard shortcuts configuration."""
    show_bubble: str = "cmd+shift+a"


@dataclass
class Config:
    """Main configuration class."""
    ui: UIConfig = field(default_factory=UIConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
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
        system_tray_data = data.get("system_tray", {})
        shortcuts_data = data.get("shortcuts", {})
        
        return cls(
            ui=UIConfig(
                theme=ui_data.get("theme", "dark"),
                bubble_size_ratio=ui_data.get("bubble_size_ratio", 0.167),
                auto_hide_delay=ui_data.get("auto_hide_delay", 8),
                always_on_top=ui_data.get("always_on_top", True),
            ),
            llm=LLMConfig(
                default_provider=llm_data.get("default_provider", "openai"),
                default_model=llm_data.get("default_model", "gpt-4o-mini"),
                max_tokens=llm_data.get("max_tokens", 32000),
                temperature=llm_data.get("temperature", 0.7),
            ),
            system_tray=SystemTrayConfig(
                icon_size=system_tray_data.get("icon_size", 64),
                show_notifications=system_tray_data.get("show_notifications", True),
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
            "system_tray": {
                "icon_size": self.system_tray.icon_size,
                "show_notifications": self.system_tray.show_notifications,
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
        if self.llm.default_provider not in ["openai", "anthropic", "ollama"]:
            errors.append(f"Invalid provider: {self.llm.default_provider}")
        
        if not 0.0 <= self.llm.temperature <= 2.0:
            errors.append(f"Invalid temperature: {self.llm.temperature}")
        
        if self.llm.max_tokens < 1000:
            errors.append(f"Invalid max_tokens: {self.llm.max_tokens}")
        
        # Validate system tray settings
        if not 16 <= self.system_tray.icon_size <= 128:
            errors.append(f"Invalid icon_size: {self.system_tray.icon_size}")
        
        if errors:
            for error in errors:
                print(f"Config validation error: {error}")
            return False
        
        return True
