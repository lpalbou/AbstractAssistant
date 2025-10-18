#!/usr/bin/env python3
"""
Test script for AbstractAssistant components.

This script tests individual components without running the full GUI.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.core.llm_manager import LLMManager
from src.utils.icon_generator import IconGenerator


def test_llm_manager():
    """Test the LLM manager functionality."""
    print("Testing LLM Manager...")
    
    manager = LLMManager()
    
    # Test provider info
    providers = manager.get_providers()
    print(f"Available providers: {list(providers.keys())}")
    
    # Test model info
    models = manager.get_models("openai")
    print(f"OpenAI models: {models}")
    
    # Test status info
    status = manager.get_status_info()
    print(f"Status info: {status}")
    
    # Test simple generation (mock)
    try:
        response = manager.generate_response("Hello, test message!")
        print(f"Generated response: {response[:100]}...")
    except Exception as e:
        print(f"Generation test (expected with mock): {e}")
    
    print("LLM Manager test completed.\n")


def test_icon_generator():
    """Test the icon generator functionality."""
    print("Testing Icon Generator...")
    
    generator = IconGenerator()
    
    # Test app icon generation
    try:
        app_icon = generator.create_app_icon()
        print(f"App icon created: {app_icon.size}")
        
        # Save test icon
        app_icon.save("test_icon.png")
        print("Test icon saved as test_icon.png")
    except Exception as e:
        print(f"Icon generation error: {e}")
    
    # Test status icons
    try:
        status_icon = generator.create_status_icon("ready")
        print(f"Status icon created: {status_icon.size}")
    except Exception as e:
        print(f"Status icon error: {e}")
    
    print("Icon Generator test completed.\n")


def main():
    """Run all tests."""
    print("AbstractAssistant Component Tests")
    print("=" * 40)
    
    test_llm_manager()
    test_icon_generator()
    
    print("All tests completed!")


if __name__ == "__main__":
    main()
