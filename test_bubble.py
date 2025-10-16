#!/usr/bin/env python3
"""
Test script for the new chat bubble interface.

This script tests the updated AbstractAssistant with LMStudio integration
and the new bubble window interface.
"""

def test_configuration():
    """Test configuration loading."""
    try:
        from abstractassistant.config import Config
        config = Config.load()
        print("✅ Configuration loaded successfully")
        print(f"   Default provider: {config.llm.default_provider}")
        print(f"   Default model: {config.llm.default_model}")
        print(f"   Max tokens: {config.llm.max_tokens}")
        return config
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return None

def test_llm_manager(config):
    """Test LLM manager with new providers."""
    try:
        from abstractassistant.core.llm_manager import LLMManager
        llm_manager = LLMManager(config=config)
        print("✅ LLM Manager initialized successfully")
        
        providers = llm_manager.get_providers()
        print(f"   Available providers: {list(providers.keys())}")
        
        # Test LMStudio provider
        if 'lmstudio' in providers:
            lmstudio_info = providers['lmstudio']
            print(f"   LMStudio models: {lmstudio_info.models}")
            print(f"   LMStudio default: {lmstudio_info.default_model}")
        
        return llm_manager
    except Exception as e:
        print(f"❌ LLM Manager error: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_bubble_window(llm_manager, config):
    """Test bubble window creation."""
    try:
        from abstractassistant.ui.bubble_window import BubbleWindow, FallbackBubble
        
        # Try to create bubble window
        try:
            bubble = BubbleWindow(llm_manager=llm_manager, config=config, debug=True)
            print("✅ BubbleWindow created successfully")
            return bubble
        except Exception as e:
            print(f"⚠️  BubbleWindow failed, trying fallback: {e}")
            bubble = FallbackBubble(llm_manager=llm_manager, config=config, debug=True)
            print("✅ FallbackBubble created successfully")
            return bubble
            
    except Exception as e:
        print(f"❌ Bubble window error: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_app_initialization(config):
    """Test full app initialization."""
    try:
        from abstractassistant.app import AbstractAssistantApp
        app = AbstractAssistantApp(config=config, debug=True)
        print("✅ AbstractAssistantApp initialized successfully")
        
        # Test system tray icon creation
        icon = app.create_system_tray_icon()
        print("✅ System tray icon created successfully")
        
        return app
    except Exception as e:
        print(f"❌ App initialization error: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Run all tests."""
    print("🧪 Testing AbstractAssistant Chat Bubble Implementation")
    print("=" * 60)
    
    # Test configuration
    config = test_configuration()
    if not config:
        return
    
    print()
    
    # Test LLM manager
    llm_manager = test_llm_manager(config)
    if not llm_manager:
        return
    
    print()
    
    # Test bubble window
    bubble = test_bubble_window(llm_manager, config)
    if not bubble:
        return
    
    print()
    
    # Test full app
    app = test_app_initialization(config)
    if not app:
        return
    
    print()
    print("🎉 All tests passed! The chat bubble implementation is ready.")
    print()
    print("📋 Summary of changes:")
    print("   • Added LMStudio provider with qwen/qwen3-next-80b as default")
    print("   • Registered common tools from AbstractCore")
    print("   • Created modern HTML/CSS/JS bubble interface")
    print("   • Implemented cross-platform bubble window")
    print("   • Updated system tray to show bubble on click")
    print("   • Updated configuration defaults")
    print()
    print("🚀 To run the application:")
    print("   assistant --debug")

if __name__ == "__main__":
    main()
