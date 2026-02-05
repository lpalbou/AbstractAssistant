#!/usr/bin/env python3
"""Simple test to check if the bubble window works."""

import sys
import os
from pathlib import Path

# Add the project to Python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def test_basic_imports():
    """Test basic imports."""
    try:
        from abstractassistant.config import Config
        print("✅ Config import successful")
        
        from abstractassistant.core.llm_manager import LLMManager
        print("✅ LLMManager import successful")
        
        from abstractassistant.ui.bubble_window import BubbleWindow, FallbackBubble
        print("✅ BubbleWindow imports successful")
        
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config():
    """Test configuration."""
    try:
        from abstractassistant.config import Config
        config = Config.load()
        print(f"✅ Config loaded - Provider: {config.llm.default_provider}, Model: {config.llm.default_model}")
        return config
    except Exception as e:
        print(f"❌ Config error: {e}")
        return None

def test_llm_manager(config):
    """Test LLM manager."""
    try:
        from abstractassistant.core.llm_manager import LLMManager
        llm_manager = LLMManager(config=config)
        providers = llm_manager.get_providers()
        print(f"✅ LLM Manager created - Providers: {list(providers.keys())}")
        return llm_manager
    except Exception as e:
        print(f"❌ LLM Manager error: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_bubble_creation(llm_manager, config):
    """Test bubble window creation without showing it."""
    try:
        from abstractassistant.ui.bubble_window import BubbleWindow, FallbackBubble
        
        # Test pywebview availability
        try:
            import webview
            print("✅ pywebview is available")
            
            bubble = BubbleWindow(llm_manager=llm_manager, config=config, debug=True)
            print("✅ BubbleWindow created successfully (not shown)")
            return bubble
            
        except ImportError:
            print("⚠️  pywebview not available, testing fallback...")
            bubble = FallbackBubble(llm_manager=llm_manager, config=config, debug=True)
            print("✅ FallbackBubble created successfully")
            return bubble
            
    except Exception as e:
        print(f"❌ Bubble creation error: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("🧪 Simple AbstractAssistant Test")
    print("=" * 40)
    
    if not test_basic_imports():
        return
    
    config = test_config()
    if not config:
        return
    
    llm_manager = test_llm_manager(config)
    if not llm_manager:
        return
    
    bubble = test_bubble_creation(llm_manager, config)
    if not bubble:
        return
    
    print()
    print("🎉 All basic tests passed!")
    print("The issue might be with pystray behavior on macOS.")
    print("Try clicking 'Open Chat' from the menu to test the bubble.")

if __name__ == "__main__":
    main()
