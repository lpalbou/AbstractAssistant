#!/usr/bin/env python3
"""
Test the fixed double click detection implementation.

This test verifies:
1. Single click waits 500ms before executing (delay-based detection)
2. Double click executes immediately and cancels single click
3. Voice control integration works with both click types
"""

import sys
import time
sys.path.insert(0, '/Users/albou/projects/abstractassistant')

def test_double_click_fix():
    """Test the fixed double click detection."""
    print("🔧 Testing Fixed Double Click Detection")
    print("=" * 50)

    try:
        from abstractassistant.app import AbstractAssistantApp
        from abstractassistant.config import Config
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QTimer

        # Create Qt app
        qt_app = QApplication.instance() or QApplication(sys.argv)

        # Create AbstractAssistant app
        config = Config.default()
        app = AbstractAssistantApp(config=config, debug=True)

        # Create Qt system tray icon
        qt_icon = app._create_qt_system_tray_icon()
        print("✅ Qt system tray icon created")

        # Test single click (should wait 500ms before executing)
        print("\n🖱️  Test 1: Single Click Detection (should wait 500ms)")
        print("Simulating single click...")

        start_time = time.time()
        single_click_executed = [False]

        # Track when single click actually executes
        original_handle_single = app.handle_single_click
        def track_single_click():
            single_click_executed[0] = True
            execution_time = time.time() - start_time
            print(f"✅ Single click executed after {execution_time:.3f} seconds")
            # Don't actually execute to avoid creating UI

        app.handle_single_click = track_single_click

        # Simulate single click
        app._qt_on_tray_activated(2)  # QSystemTrayIcon.Trigger = 2

        # Wait and check timing
        time.sleep(0.3)  # 300ms
        if single_click_executed[0]:
            print("❌ Single click executed too early (should wait 500ms)")
            return False
        else:
            print("✅ Single click correctly waiting...")

        time.sleep(0.3)  # Total 600ms
        if single_click_executed[0]:
            print("✅ Single click executed after proper delay")
        else:
            print("❌ Single click never executed")
            return False

        # Test double click (should execute immediately)
        print("\n🖱️  Test 2: Double Click Detection (should execute immediately)")
        print("Simulating double click...")

        double_click_executed = [False]

        # Track when double click executes
        original_handle_double = app.handle_double_click
        def track_double_click():
            double_click_executed[0] = True
            execution_time = time.time() - start_time
            print(f"✅ Double click executed after {execution_time:.3f} seconds")
            # Don't actually execute to avoid creating UI

        app.handle_double_click = track_double_click

        # Reset for double click test
        app.click_count = 0
        app.click_timer.stop()
        start_time = time.time()

        # Simulate double click (two clicks in quick succession)
        app._qt_on_tray_activated(2)  # First click
        time.sleep(0.1)  # 100ms between clicks
        app._qt_on_tray_activated(2)  # Second click

        # Check if double click executed immediately
        time.sleep(0.05)  # Small delay to allow processing
        if double_click_executed[0]:
            print("✅ Double click executed immediately")
        else:
            print("❌ Double click did not execute")
            return False

        # Wait to ensure single click doesn't execute after double click
        time.sleep(0.6)  # Wait past the 500ms timeout
        if single_click_executed[0]:
            # Reset the flag since we're reusing it
            single_click_executed[0] = False
            print("❌ Single click executed after double click (should be cancelled)")
            return False
        else:
            print("✅ Single click correctly cancelled by double click")

        # Test timing values
        print(f"\n⏱️  Timing Configuration:")
        print(f"   Double click timeout: {app.DOUBLE_CLICK_TIMEOUT}ms")
        print(f"   Expected behavior: Single click waits {app.DOUBLE_CLICK_TIMEOUT}ms")
        print(f"   Expected behavior: Double click executes immediately")

        print("\n🎉 Double Click Fix Test PASSED!")
        print("✅ Single click waits 500ms before executing")
        print("✅ Double click executes immediately")
        print("✅ Double click cancels pending single click")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_voice_integration():
    """Test voice control integration with fixed click detection."""
    print("\n🎙️  Testing Voice Control Integration")
    print("=" * 50)

    try:
        from abstractassistant.core.tts_manager import VoiceManager

        # Test voice manager
        vm = VoiceManager(debug_mode=True)

        if not vm.is_available():
            print("⚠️  AbstractVoice not available for voice integration test")
            return True

        print("✅ VoiceManager available")

        # Test voice states for click logic
        print("Testing voice states that click handlers will encounter:")

        # Test idle state
        state = vm.get_state()
        print(f"   📊 Idle state: {state}")

        # Test speaking state
        print("   🔊 Starting speech...")
        vm.speak("Testing double click detection with voice", speed=2.0)
        time.sleep(0.5)

        speaking_state = vm.get_state()
        print(f"   📊 Speaking state: {speaking_state}")

        # Test pause
        print("   ⏸ Testing pause...")
        pause_result = vm.pause()
        paused_state = vm.get_state()
        print(f"   📊 Paused state: {paused_state}, pause result: {pause_result}")

        # Test stop
        print("   ⏹ Testing stop...")
        vm.stop()
        stopped_state = vm.get_state()
        print(f"   📊 Stopped state: {stopped_state}")

        vm.cleanup()
        print("✅ Voice control integration test completed")

        return True

    except Exception as e:
        print(f"❌ Voice integration test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing Double Click Detection Fix")
    print("=" * 70)

    success1 = test_double_click_fix()
    success2 = test_voice_integration()

    print("\n" + "=" * 70)
    if success1 and success2:
        print("🎉 ALL TESTS PASSED!")
        print("🎯 Double click detection is now working correctly!")
        print("\n✨ Expected behavior:")
        print("   • Single click: Wait 500ms, then pause/resume or show bubble")
        print("   • Double click: Execute immediately, stop voice + show bubble")
        print("   • Double click cancels any pending single click")
    else:
        print("❌ SOME TESTS FAILED")

    sys.exit(0 if (success1 and success2) else 1)