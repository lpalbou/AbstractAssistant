#!/usr/bin/env python3
"""
Example usage of AbstractAssistant components.

This demonstrates how to use AbstractAssistant programmatically.
"""

from abstractassistant.config import Config
from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.app import AbstractAssistantApp


def example_config_usage():
    """Example of configuration management."""
    print("=== Configuration Example ===")
    
    # Create default config
    config = Config.default()
    print(f"Default provider: {config.llm.default_provider}")
    print(f"Default model: {config.llm.default_model}")
    
    # Modify config
    config.llm.default_provider = "anthropic"
    config.llm.default_model = "claude-3-5-sonnet-20241022"
    config.ui.theme = "light"
    
    # Validate config
    if config.validate():
        print("✅ Configuration is valid")
    else:
        print("❌ Configuration validation failed")
    
    # Save config
    from pathlib import Path
    config_path = Path("example_config.toml")
    config.save_to_file(config_path)
    print(f"Config saved to: {config_path}")
    
    # Load config
    loaded_config = Config.from_file(config_path)
    print(f"Loaded provider: {loaded_config.llm.default_provider}")
    
    # Clean up
    config_path.unlink()
    print()


def example_llm_manager():
    """Example of LLM manager usage."""
    print("=== LLM Manager Example ===")
    
    # Create custom config
    config = Config.default()
    config.llm.default_provider = "openai"
    config.llm.default_model = "gpt-4o-mini"
    
    # Create LLM manager
    llm_manager = LLMManager(config=config)
    
    # Get available providers and models
    providers = llm_manager.get_providers()
    print(f"Available providers: {list(providers.keys())}")
    
    models = llm_manager.get_models("openai")
    print(f"OpenAI models: {models}")
    
    # Get status info
    status = llm_manager.get_status_info()
    print(f"Status: {status}")
    
    # Switch provider
    llm_manager.set_provider("anthropic")
    print(f"Switched to: {llm_manager.current_provider}")
    
    print()


def example_app_launch():
    """Example of launching the app programmatically."""
    print("=== App Launch Example ===")
    
    # Create custom config
    config = Config.default()
    config.ui.theme = "dark"
    config.llm.default_provider = "openai"
    config.system_tray.show_notifications = True
    
    print("Creating AbstractAssistant app...")
    print("Note: This would launch the GUI - commented out for example")
    
    # Uncomment to actually launch:
    # app = AbstractAssistantApp(config=config, debug=True)
    # app.run()
    
    print("App configuration ready!")
    print()


def main():
    """Run all examples."""
    print("🤖 AbstractAssistant Usage Examples")
    print("=" * 50)
    
    try:
        example_config_usage()
        example_llm_manager()
        example_app_launch()
        
        print("✅ All examples completed successfully!")
        
    except Exception as e:
        print(f"❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
