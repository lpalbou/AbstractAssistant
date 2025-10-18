"""
Provider Manager for AbstractAssistant.

Handles provider discovery, model loading, and provider configuration
using AbstractCore's provider discovery system.
"""

from typing import List, Dict, Tuple, Optional
from abstractcore import create_llm
from abstractcore.providers import (
    list_available_providers,
    get_available_models_for_provider,
    get_all_providers_with_models
)


class ProviderManager:
    """Manages provider discovery and model loading for AbstractAssistant."""

    # Provider display names mapping
    PROVIDER_DISPLAY_NAMES = {
        'openai': 'OpenAI',
        'anthropic': 'Anthropic',
        'ollama': 'Ollama',
        'lmstudio': 'LMStudio',
        'mlx': 'MLX',
        'huggingface': 'HuggingFace',
        'mock': 'Mock'
    }

    # Default models for provider instantiation
    PROVIDER_DEFAULT_MODELS = {
        'openai': 'gpt-4o-mini',
        'anthropic': 'claude-3-5-haiku-20241022',
        'ollama': 'qwen3:4b-instruct-2507-q4_K_M',
        'lmstudio': 'qwen/qwen3-next-80b',
        'mlx': 'mlx-community/Qwen3-4B-4bit',
        'huggingface': 'microsoft/DialoGPT-medium'
    }

    # Fallback models for when discovery fails
    FALLBACK_MODELS = {
        'lmstudio': ['qwen/qwen3-next-80b', 'qwen/qwen3-coder-30b', 'qwen/qwen3-4b-2507'],
        'ollama': ['qwen3:4b-instruct', 'llama3.2:3b', 'mistral:7b'],
        'openai': ['gpt-4o-mini', 'gpt-4o', 'gpt-3.5-turbo'],
        'anthropic': ['claude-3-5-haiku-20241022', 'claude-3-5-sonnet-20241022'],
        'mlx': ['mlx-community/Qwen3-4B-4bit', 'mlx-community/Qwen3-4B-Instruct-2507-4bit'],
        'huggingface': ['microsoft/DialoGPT-medium', 'microsoft/DialoGPT-large']
    }

    def __init__(self, debug: bool = False):
        """Initialize the provider manager.

        Args:
            debug: Enable debug logging
        """
        self.debug = debug

    def get_available_providers(self, exclude_mock: bool = True) -> List[Tuple[str, str]]:
        """Get list of available providers with display names.

        Args:
            exclude_mock: Whether to exclude the mock provider

        Returns:
            List of (display_name, provider_key) tuples
        """
        try:
            # Use AbstractCore's provider discovery system
            available_providers = list_available_providers()

            if self.debug:
                print(f"🔍 Provider discovery found {len(available_providers)} available providers: {available_providers}")

            providers = []

            for provider_name in available_providers:
                # Exclude mock provider if requested
                if exclude_mock and provider_name == 'mock':
                    if self.debug:
                        print(f"    ⏭️  Skipping mock provider")
                    continue

                display_name = self.PROVIDER_DISPLAY_NAMES.get(provider_name, provider_name.title())
                providers.append((display_name, provider_name))

                if self.debug:
                    print(f"    ✅ Available: {display_name} ({provider_name})")

            if self.debug:
                print(f"🔍 Total providers available: {len(providers)}")

            return providers

        except Exception as e:
            if self.debug:
                print(f"❌ Error loading providers: {e}")
                import traceback
                traceback.print_exc()

            # Fallback: return lmstudio as default
            return [("LMStudio (Local)", "lmstudio")]

    def get_preferred_provider(self, available_providers: List[Tuple[str, str]],
                             preferred: str = 'lmstudio') -> Optional[Tuple[str, str]]:
        """Get preferred provider from available list.

        Args:
            available_providers: List of (display_name, provider_key) tuples
            preferred: Preferred provider key

        Returns:
            (display_name, provider_key) tuple or None if not found
        """
        for display_name, provider_key in available_providers:
            if provider_key == preferred:
                if self.debug:
                    print(f"✅ Found preferred provider: {display_name} ({provider_key})")
                return (display_name, provider_key)

        if self.debug:
            print(f"⚠️  Preferred provider '{preferred}' not found")
        return None

    def get_models_for_provider(self, provider: str) -> List[str]:
        """Get available models for a provider with 3-tier fallback strategy.

        Args:
            provider: Provider key

        Returns:
            List of model names
        """
        # Strategy 1: Try provider instantiation and list_available_models()
        try:
            if self.debug:
                print(f"🔍 Strategy 1: Trying provider instantiation for {provider}")

            default_model = self.PROVIDER_DEFAULT_MODELS.get(provider, 'default-model')
            provider_llm = create_llm(provider, model=default_model)
            models = provider_llm.list_available_models()

            if self.debug:
                print(f"📋 Strategy 1 success: Loaded {len(models)} models for {provider}")

            return models

        except Exception as e:
            if self.debug:
                print(f"❌ Strategy 1 failed for '{provider}': {e}")

        # Strategy 2: Try AbstractCore's registry method
        try:
            if self.debug:
                print(f"🔍 Strategy 2: Trying registry method for {provider}")

            models = get_available_models_for_provider(provider)

            if self.debug:
                print(f"📋 Strategy 2 success: Loaded {len(models)} models from registry")

            return models

        except Exception as e:
            if self.debug:
                print(f"❌ Strategy 2 failed: {e}")

        # Strategy 3: Use fallback models
        if self.debug:
            print(f"🔍 Strategy 3: Using fallback models for {provider}")

        fallback_models = self.FALLBACK_MODELS.get(provider, ['default-model'])

        if self.debug:
            print(f"📋 Strategy 3: Using {len(fallback_models)} fallback models")

        return fallback_models

    def create_model_display_name(self, model: str, max_length: int = 25) -> str:
        """Create a user-friendly display name for a model.

        Args:
            model: Full model name
            max_length: Maximum display name length

        Returns:
            Formatted display name
        """
        # Extract the last part of the model name (after /)
        display_name = model.split('/')[-1] if '/' in model else model

        # Truncate if too long
        if len(display_name) > max_length:
            display_name = display_name[:max_length-3] + "..."

        return display_name

    def get_preferred_model(self, models: List[str],
                          preferred: str = 'qwen/qwen3-next-80b',
                          current: Optional[str] = None) -> Optional[str]:
        """Get preferred model from available list.

        Args:
            models: List of available models
            preferred: Preferred model name
            current: Current model name (fallback option)

        Returns:
            Model name or None if not found
        """
        # Try preferred model first
        if preferred in models:
            if self.debug:
                print(f"✅ Found preferred model: {preferred}")
            return preferred

        # Try current model as fallback
        if current and current in models:
            if self.debug:
                print(f"✅ Found current model: {current}")
            return current

        # Use first available model
        if models:
            if self.debug:
                print(f"🔄 Using first available model: {models[0]}")
            return models[0]

        if self.debug:
            print("❌ No models available")
        return None

    def get_comprehensive_provider_info(self) -> List[Dict]:
        """Get comprehensive provider information using AbstractCore's registry.

        Returns:
            List of provider information dictionaries
        """
        try:
            return get_all_providers_with_models()
        except Exception as e:
            if self.debug:
                print(f"❌ Error getting comprehensive provider info: {e}")
            return []