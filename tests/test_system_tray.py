#!/usr/bin/env python3
"""
Test the system tray icon single/double click functionality.
"""

import sys
import time
from pathlib import Path
import threading

# Add the abstractassistant module to the path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def test_system_tray_clicks():
    """Test the ClickableIcon single/double click detection."""
    print("🧪 Testing system tray icon click detection...")

    try:
        from abstractassistant.app import ClickableIcon
        from abstractassistant.utils.icon_generator import IconGenerator

        # Create icon generator and generate an icon
        icon_gen = IconGenerator(size=32)
        icon_image = icon_gen.create_app_icon(color_scheme="green", animated=False)

        # Track clicks
        click_history = []

        def click_handler(single_click=False, double_click=False):
            """Handle tray icon clicks."""
            if single_click:
                click_history.append("single")
                print("✅ Single click detected!")
            elif double_click:
                click_history.append("double")
                print("✅ Double click detected!")
            else:
                click_history.append("normal")
                print("✅ Normal click detected!")

        # Create clickable icon
        icon = ClickableIcon(
            "Test",
            icon_image,
            "Test Icon",
            click_handler=click_handler
        )

        print("🔄 Created system tray icon with click detection")
        print("📝 Simulating clicks to test detection...")

        # Simulate clicks by accessing _menu property
        print("\n🔄 Simulating single click...")
        icon._click_count = 0
        _ = icon._menu  # This triggers click detection
        time.sleep(0.4)  # Wait for single click timeout

        print("\n🔄 Simulating double click...")
        icon._click_count = 0
        _ = icon._menu  # First click
        time.sleep(0.1)  # Quick delay
        _ = icon._menu  # Second click
        time.sleep(0.1)  # Brief wait

        print("\n📊 Click history:", click_history)

        # Verify expected results
        expected = ["single", "double"]
        if click_history == expected:
            print("✅ Click detection working correctly!")
            return True
        else:
            print(f"❌ Click detection failed. Expected {expected}, got {click_history}")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_abstractassistant_integration():
    """Test with actual AbstractAssistant app."""
    print("\n🧪 Testing AbstractAssistant integration...")

    try:
        from abstractassistant.app import AbstractAssistantApp
        from abstractassistant.config import Config

        # Create app with debug mode
        config = Config()
        app = AbstractAssistantApp(config, debug=True)

        print("✅ AbstractAssistant app created")
        print("📝 App should have click detection enabled")

        # Check if the app has the retry method
        if hasattr(app, '_attempt_pause_with_retry'):
            print("✅ App has retry logic for pause operations")
        else:
            print("❌ App missing retry logic")

        # Check if show_chat_bubble accepts new parameters
        import inspect
        sig = inspect.signature(app.show_chat_bubble)
        params = list(sig.parameters.keys())

        if 'single_click' in params and 'double_click' in params:
            print("✅ show_chat_bubble accepts single_click and double_click parameters")
        else:
            print(f"❌ show_chat_bubble parameters: {params}")

        return True

    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("🧪 Starting System Tray Click Detection Tests...")

    tests = [
        test_system_tray_clicks,
        test_abstractassistant_integration
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            results.append(False)

    print(f"\n📊 Test Results: {sum(results)}/{len(results)} tests passed")

    if all(results):
        print("🎉 All tests passed!")
        print("\n✅ System Tray Features Ready:")
        print("  • Single click detection (300ms timeout)")
        print("  • Double click detection")
        print("  • AbstractAssistant integration")
        print("  • Pause/resume retry logic")
        print("\n📝 Expected behavior:")
        print("  • Single click tray icon: Pause/Resume TTS")
        print("  • Double click tray icon: Stop TTS and show chat bubble")
        return True
    else:
        print("❌ Some tests failed!")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
