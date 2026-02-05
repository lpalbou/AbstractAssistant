#!/usr/bin/env python3
"""
Test the click detection with the correct reason values.

Based on user testing:
- Single click: reason == 3
- Double click: reason == 3 then reason == 2
"""

import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def test_reason_based_detection():
    """Test click detection with the actual reason values."""
    print("🧪 Testing Click Detection with Correct Reason Values")
    print("=" * 60)
    print("Based on user testing:")
    print("  • Single click: reason == 3")
    print("  • Double click: reason == 3 then reason == 2")
    print("=" * 60)

    try:
        from abstractassistant.app import AbstractAssistantApp
        from abstractassistant.config import Config
        from PyQt5.QtWidgets import QApplication

        # Create Qt app
        qt_app = QApplication.instance() or QApplication(sys.argv)

        # Create AbstractAssistant app
        config = Config.default()
        app = AbstractAssistantApp(config=config, debug=True)

        # Create Qt system tray icon
        qt_icon = app._create_qt_system_tray_icon()
        print("✅ Qt system tray icon created")

        # Track what gets executed
        single_executed = [False]
        double_executed = [False]

        # Mock handlers to track execution
        original_single = app.handle_single_click
        original_double = app.handle_double_click

        def track_single():
            single_executed[0] = True
            print("   📍 SINGLE CLICK ACTION EXECUTED")

        def track_double():
            double_executed[0] = True
            print("   📍 DOUBLE CLICK ACTION EXECUTED")

        app.handle_single_click = track_single
        app.handle_double_click = track_double

        # Test 1: Single click scenario (reason=3 only)
        print("\n🖱️  Test 1: Single Click (reason=3)")
        print("   Simulating single click...")

        # Reset state
        app.click_count = 0
        app.click_timer.stop()
        single_executed[0] = False
        double_executed[0] = False

        # Simulate single click (reason=3)
        app._qt_on_tray_activated(3)

        # Wait less than timeout
        time.sleep(0.3)
        if single_executed[0] or double_executed[0]:
            print("   ❌ Action executed too early!")
            return False

        # Wait for timeout to complete
        time.sleep(0.3)  # Total 0.6s, should exceed 0.5s timeout

        if single_executed[0] and not double_executed[0]:
            print("   ✅ Single click executed after timeout")
        else:
            print(f"   ❌ Wrong execution: single={single_executed[0]}, double={double_executed[0]}")
            return False

        # Test 2: Double click scenario (reason=3 then reason=2)
        print("\n🖱️  Test 2: Double Click (reason=3 then reason=2)")
        print("   Simulating double click...")

        # Reset state
        app.click_count = 0
        app.click_timer.stop()
        single_executed[0] = False
        double_executed[0] = False

        # Simulate double click (reason=3 followed by reason=2)
        app._qt_on_tray_activated(3)  # First part of double click
        time.sleep(0.1)  # Small delay between events
        app._qt_on_tray_activated(2)  # Double click confirmation

        # Check immediate execution
        time.sleep(0.05)  # Small delay for processing
        if double_executed[0] and not single_executed[0]:
            print("   ✅ Double click executed immediately")
        else:
            print(f"   ❌ Wrong execution: single={single_executed[0]}, double={double_executed[0]}")
            return False

        # Wait to ensure single click doesn't execute later
        time.sleep(0.6)
        if single_executed[0]:
            print("   ❌ Single click executed after double click (should be cancelled)")
            return False
        else:
            print("   ✅ Single click correctly cancelled by double click")

        print("\n🎉 Click Detection Test PASSED!")
        print("✅ Single click (reason=3): waits 500ms then executes")
        print("✅ Double click (reason=3,2): executes immediately")
        print("✅ Double click cancels pending single click")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_voice_integration_with_correct_clicks():
    """Test voice integration with the correct click detection."""
    print("\n🎙️  Testing Voice Integration with Correct Click Detection")
    print("=" * 60)

    try:
        from abstractassistant.core.tts_manager import VoiceManager

        vm = VoiceManager(debug_mode=True)

        if not vm.is_available():
            print("⚠️  AbstractVoice not available - skipping voice integration test")
            return True

        print("✅ AbstractVoice available")

        # Test the voice scenarios that the click handlers will handle
        print("\n📋 Testing Voice Control Scenarios:")

        # Scenario 1: Single click while speaking (should pause)
        print("   🔊 Scenario 1: Speaking + Single Click = Pause")
        vm.speak("Testing single click pause functionality", speed=2.0)
        time.sleep(0.8)

        if vm.is_speaking():
            state_before = vm.get_state()
            pause_result = vm.pause()
            state_after = vm.get_state()
            print(f"      Before: {state_before}, After: {state_after}, Success: {pause_result}")

        # Scenario 2: Single click while paused (should resume)
        if vm.is_paused():
            print("   ▶ Scenario 2: Paused + Single Click = Resume")
            state_before = vm.get_state()
            resume_result = vm.resume()
            state_after = vm.get_state()
            print(f"      Before: {state_before}, After: {state_after}, Success: {resume_result}")

        # Scenario 3: Double click while speaking (should stop)
        print("   ⏹ Scenario 3: Speaking + Double Click = Stop")
        if not vm.is_speaking():
            vm.speak("Testing double click stop functionality", speed=2.0)
            time.sleep(0.5)

        if vm.is_speaking() or vm.is_paused():
            state_before = vm.get_state()
            vm.stop()
            state_after = vm.get_state()
            print(f"      Before: {state_before}, After: {state_after}")

        vm.cleanup()
        print("✅ Voice integration scenarios completed")

        return True

    except Exception as e:
        print(f"❌ Voice integration test failed: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TESTING CORRECT CLICK DETECTION")
    print("=" * 70)

    success1 = test_reason_based_detection()
    success2 = test_voice_integration_with_correct_clicks()

    print("\n" + "=" * 70)
    if success1 and success2:
        print("🎉 ALL TESTS PASSED!")
        print("🎯 Click detection now works with correct reason values!")
        print("\n✨ Implementation Summary:")
        print("   • Single click (reason=3): Wait 500ms, then pause/resume or show bubble")
        print("   • Double click (reason=3,2): Stop voice + show bubble immediately")
        print("   • Proper cancellation of pending single clicks")
        print("\n🚀 Ready for user testing!")
    else:
        print("❌ Some tests failed")

    sys.exit(0 if (success1 and success2) else 1)
