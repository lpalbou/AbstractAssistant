"""
Provider manager for AbstractAssistant local mode.

Provider and model inventory comes from AbstractCore discovery. This module does
not hardcode preferred providers or fallback model lists.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from abstractcore.providers import (
    get_all_providers_with_models,
    get_available_models_for_provider,
    list_available_providers,
)


def _display_name(provider_name: str) -> str:
    return str(provider_name or "").replace("_", " ").strip().title() or str(provider_name or "")


class ProviderManager:
    """Manage provider discovery and model listing for local mode."""

    def __init__(self, debug: bool = False):
        self.debug = bool(debug)

    def get_available_providers(self, exclude_mock: bool = True) -> List[Tuple[str, str]]:
        """Return discovered providers as ``(display_name, provider_key)`` tuples."""
        providers: List[Tuple[str, str]] = []

        try:
            info_list = get_all_providers_with_models()
        except Exception as e:
            if self.debug:
                print(f"❌ Error loading provider metadata: {e}")
            info_list = []

        if isinstance(info_list, list):
            for info in info_list:
                if not isinstance(info, dict):
                    continue
                provider_name = str(info.get("name") or "").strip()
                if not provider_name:
                    continue
                if exclude_mock and provider_name == "mock":
                    continue
                display_name = str(info.get("display_name") or "").strip() or _display_name(provider_name)
                providers.append((display_name, provider_name))

        if providers:
            if self.debug:
                print(f"🔍 Provider discovery found {len(providers)} providers: {[p for _, p in providers]}")
            return providers

        try:
            provider_names = list_available_providers()
        except Exception as e:
            if self.debug:
                print(f"❌ Error loading providers: {e}")
            return []

        for provider_name in provider_names:
            if exclude_mock and provider_name == "mock":
                continue
            providers.append((_display_name(provider_name), provider_name))

        if self.debug:
            print(f"🔍 Provider discovery found {len(providers)} providers: {[p for _, p in providers]}")
        return providers

    def get_preferred_provider(
        self,
        available_providers: List[Tuple[str, str]],
        preferred: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """Return the preferred provider if present, otherwise the first available."""
        preferred_key = str(preferred or "").strip()
        if preferred_key:
            for display_name, provider_key in available_providers:
                if provider_key == preferred_key:
                    return (display_name, provider_key)
        return available_providers[0] if available_providers else None

    def get_models_for_provider(self, provider: str) -> List[str]:
        """Return discovered models for a provider."""
        provider_key = str(provider or "").strip()
        if not provider_key:
            return []

        try:
            models = get_available_models_for_provider(provider_key)
        except Exception as e:
            if self.debug:
                print(f"❌ Error loading models for {provider_key}: {e}")
            models = []

        out: List[str] = []
        for model in models or []:
            model_name = str(model or "").strip()
            if model_name:
                out.append(model_name)
        return out

    def create_model_display_name(self, model: str, max_length: int = 25) -> str:
        """Create a user-friendly display name for a model."""
        display_name = str(model or "")
        if len(display_name) > max_length:
            display_name = display_name[: max_length - 3] + "..."
        return display_name

    def get_preferred_model(
        self,
        models: List[str],
        preferred: Optional[str] = None,
        current: Optional[str] = None,
    ) -> Optional[str]:
        """Return the preferred model if present, otherwise the first available."""
        current_name = str(current or "").strip()
        if current_name and current_name in models:
            return current_name
        preferred_name = str(preferred or "").strip()
        if preferred_name and preferred_name in models:
            return preferred_name
        return models[0] if models else None

    def get_comprehensive_provider_info(self) -> List[Dict]:
        """Return provider metadata from AbstractCore's registry."""
        try:
            return get_all_providers_with_models()
        except Exception as e:
            if self.debug:
                print(f"❌ Error getting comprehensive provider info: {e}")
            return []
