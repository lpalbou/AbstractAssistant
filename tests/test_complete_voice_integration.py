#!/usr/bin/env python3
"""
Comprehensive test script for AbstractAssistant voice control integration.

Tests the complete implementation including:
- Enhanced system tray click detection
- Voice control logic (single/double click)
- Provider/model management
- TTS state management
- AbstractCore session management
"""

import sys
import time
from pathlib import Path
import threading
from pathlib import Path

# Add the abstractassistant module to the path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_enhanced_click_detection():
    """Test the enhanced click detection functionality."""
    print("🧪 Testing Enhanced Click Detection...")

    try:
        from abstractassistant.app import EnhancedClickableIcon
        from PIL import Image

        # Create a simple test image
        test_image = Image.new('RGB', (32, 32), color='green')

        click_events = []

        def single_click_handler():
            click_events.append('single')
            print("✅ Single click detected")

        def double_click_handler():
            click_events.append('double')
            print("✅ Double click detected")

        # Create enhanced icon
        icon = EnhancedClickableIcon(
            "Test",
            test_image,
            "Test Icon",
            single_click_handler=single_click_handler,
            double_click_handler=double_click_handler,
            debug=True
        )

        # Simulate clicks by calling _handle_click_timing directly
        print("🔄 Simulating single click...")
        icon._handle_click_timing()
        time.sleep(0.4)  # Wait for single click timeout

        print("🔄 Simulating double click...")
        icon._handle_click_timing()
        icon._handle_click_timing()
        time.sleep(0.1)

        # Verify results
        if 'single' in click_events and 'double' in click_events:
            print("✅ Enhanced click detection test PASSED")
            return True
        else:
            print(f"❌ Enhanced click detection test FAILED: {click_events}")
            return False

    except Exception as e:
        print(f"❌ Enhanced click detection test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_provider_manager():
    """Test the ProviderManager functionality."""
    print("\n🧪 Testing ProviderManager...")

    try:
        from abstractassistant.ui.provider_manager import ProviderManager

        pm = ProviderManager(debug=True)

        # Test provider discovery
        providers = pm.get_available_providers(exclude_mock=True)
        print(f"📋 Found {len(providers)} providers: {[p[0] for p in providers]}")

        if not providers:
            print("⚠️  No providers found, but test continues...")
            return True

        # Test preferred provider selection
        preferred = pm.get_preferred_provider(providers, 'lmstudio')
        if preferred:
            print(f"✅ Preferred provider found: {preferred[0]} ({preferred[1]})")
        else:
            print("⚠️  Preferred provider not found, using first available")

        # Test model discovery for first provider
        provider_key = providers[0][1]
        models = pm.get_models_for_provider(provider_key)
        print(f"📋 Found {len(models)} models for {provider_key}")

        if models:
            # Test model display name creation
            display_name = pm.create_model_display_name(models[0], max_length=25)
            print(f"✅ Model display name: '{display_name}' from '{models[0]}'")

            # Test preferred model selection
            preferred_model = pm.get_preferred_model(models, 'qwen/qwen3-next-80b')
            print(f"✅ Model selection result: {preferred_model}")

        print("✅ ProviderManager test PASSED")
        return True

    except Exception as e:
        print(f"❌ ProviderManager test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tts_state_manager():
    """Test the TTSStateManager functionality."""
    print("\n🧪 Testing TTSStateManager...")

    try:
        from abstractassistant.ui.tts_state_manager import TTSStateManager, TTSState

        # Create state manager without voice manager (test offline mode)
        tsm = TTSStateManager(debug=True)

        # Test state without voice manager
        state = tsm.get_current_state()
        print(f"📊 Initial state (no voice manager): {state}")

        if state != TTSState.DISABLED:
            print(f"❌ Expected DISABLED state, got {state}")
            return False

        # Test availability check
        available = tsm.is_available()
        print(f"📊 TTS available: {available}")

        if available:
            print("❌ Expected TTS unavailable without voice manager")
            return False

        # Test callback system
        callback_calls = []

        def state_change_callback(new_state):
            callback_calls.append(new_state)
            print(f"📞 State change callback: {new_state}")

        tsm.add_state_change_callback(state_change_callback)

        # Force UI update (should trigger callback)
        tsm.update_ui_state(force_update=True)

        if TTSState.DISABLED not in callback_calls:
            print(f"❌ Callback not called correctly: {callback_calls}")
            return False

        print("✅ TTSStateManager test PASSED")
        return True

    except Exception as e:
        print(f"❌ TTSStateManager test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_voice_manager_integration():
    """Test VoiceManager integration with debug_voice_manager.py patterns."""
    print("\n🧪 Testing VoiceManager Integration...")

    try:
        from abstractassistant.core.tts_manager import VoiceManager

        # Test VoiceManager initialization
        vm = VoiceManager(debug_mode=True)
        print("✅ VoiceManager initialized successfully")

        # Test availability
        available = vm.is_available()
        print(f"📊 VoiceManager available: {available}")

        if not available:
            print("⚠️  VoiceManager not available, skipping speech tests")
            return True

        # Test state queries
        speaking = vm.is_speaking()
        paused = vm.is_paused()
        state = vm.get_state()
        print(f"📊 Initial state - Speaking: {speaking}, Paused: {paused}, State: {state}")

        # Test short speech
        print("🔊 Testing short speech...")
        success = vm.speak("Testing voice integration", speed=1.5)
        print(f"🔊 Speech start: {'success' if success else 'failed'}")

        if success:
            time.sleep(0.5)  # Let speech start

            # Test pause
            print("⏸ Testing pause...")
            pause_success = vm.pause()
            print(f"⏸ Pause: {'success' if pause_success else 'failed'}")

            if pause_success:
                time.sleep(0.2)

                # Test resume
                print("▶ Testing resume...")
                resume_success = vm.resume()
                print(f"▶ Resume: {'success' if resume_success else 'failed'}")

                time.sleep(0.3)

            # Test stop
            print("⏹ Testing stop...")
            vm.stop()
            print("⏹ Stop completed")

        # Cleanup
        vm.cleanup()
        print("🧹 VoiceManager cleanup completed")

        print("✅ VoiceManager integration test PASSED")
        return True

    except Exception as e:
        print(f"❌ VoiceManager integration test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_abstractcore_integration():
    """Test AbstractCore LLM integration."""
    print("\n🧪 Testing AbstractCore Integration...")

    try:
        from abstractassistant.core.llm_manager import LLMManager
        from abstractassistant.config import Config

        # Create LLM manager
        config = Config.default()
        llm_manager = LLMManager(config=config, debug=True)
        print("✅ LLMManager initialized successfully")

        # Test provider discovery
        providers = llm_manager.get_providers()
        print(f"📋 AbstractCore found {len(providers)} providers")

        if providers:
            # Test model discovery
            first_provider = providers[0]['name']
            models = llm_manager.get_models(first_provider)
            print(f"📋 Found {len(models)} models for {first_provider}")

        # Test session creation
        llm_manager.create_new_session(tts_mode=False)
        print("✅ AbstractCore session created")

        # Test token usage
        token_usage = llm_manager.get_token_usage()
        print(f"📊 Token usage: {token_usage.current_session}/{token_usage.max_context}")

        # Test status info
        status = llm_manager.get_status_info()
        print(f"📊 Status info: {status}")

        print("✅ AbstractCore integration test PASSED")
        return True

    except Exception as e:
        print(f"❌ AbstractCore integration test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_app_voice_control_logic():
    """Test the app's voice control logic."""
    print("\n🧪 Testing App Voice Control Logic...")

    try:
        from abstractassistant.app import AbstractAssistantApp
        from abstractassistant.config import Config

        # Create app instance
        config = Config.default()
        app = AbstractAssistantApp(config=config, debug=True)
        print("✅ AbstractAssistantApp initialized")

        # Test single click handler (without actual bubble creation)
        print("🔄 Testing single click handler...")
        app.handle_single_click()
        print("✅ Single click handler executed without error")

        # Test double click handler
        print("🔄 Testing double click handler...")
        app.handle_double_click()
        print("✅ Double click handler executed without error")

        print("✅ App voice control logic test PASSED")
        return True

    except Exception as e:
        print(f"❌ App voice control logic test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ui_styles():
    """Test UI styles functionality."""
    print("\n🧪 Testing UI Styles...")

    try:
        from abstractassistant.ui.ui_styles import UIStyles

        # Test button styles
        primary_style = UIStyles.get_button_style('primary')
        print(f"✅ Primary button style: {len(primary_style)} characters")

        # Test status styles
        ready_style = UIStyles.get_status_style('ready')
        print(f"✅ Ready status style: {len(ready_style)} characters")

        # Test voice styles
        speaking_style = UIStyles.get_voice_style('speaking')
        print(f"✅ Speaking voice style: {len(speaking_style)} characters")

        # Test color constants
        colors = UIStyles.COLORS
        print(f"✅ Color palette: {len(colors)} colors defined")

        print("✅ UI Styles test PASSED")
        return True

    except Exception as e:
        print(f"❌ UI Styles test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_integration_test():
    """Run a complete integration test."""
    print("\n🧪 Running Integration Test...")

    try:
        # This would be a more complex test that creates actual UI components
        # For now, just test that imports work together
        from abstractassistant.app import AbstractAssistantApp, EnhancedClickableIcon
        from abstractassistant.ui.provider_manager import ProviderManager
        from abstractassistant.ui.ui_styles import UIStyles
        from abstractassistant.ui.tts_state_manager import TTSStateManager
        from abstractassistant.core.llm_manager import LLMManager
        from abstractassistant.core.tts_manager import VoiceManager

        print("✅ All imports successful")
        print("✅ Integration test PASSED")
        return True

    except Exception as e:
        print(f"❌ Integration test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("🚀 Starting Comprehensive AbstractAssistant Voice Integration Tests")
    print("=" * 70)

    tests = [
        ("Enhanced Click Detection", test_enhanced_click_detection),
        ("ProviderManager", test_provider_manager),
        ("TTSStateManager", test_tts_state_manager),
        ("VoiceManager Integration", test_voice_manager_integration),
        ("AbstractCore Integration", test_abstractcore_integration),
        ("App Voice Control Logic", test_app_voice_control_logic),
        ("UI Styles", test_ui_styles),
        ("Integration Test", run_integration_test),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n{'=' * 70}")
        result = test_func()
        results.append((test_name, result))

    # Summary
    print(f"\n{'=' * 70}")
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 70)

    passed = 0
    failed = 0

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:<40} {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print("=" * 70)
    print(f"Total: {len(results)} tests, {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 ALL TESTS PASSED! Implementation is ready.")
    else:
        print(f"⚠️  {failed} tests failed. Check the output above for details.")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
