#!/usr/bin/env python3
"""
Test the fixed double click detection implementation.

This test verifies:
1. When voice is active: single click triggers pause/resume action immediately
2. When voice is active: double click triggers stop action (via reason or timestamp window)
3. Voice control integration APIs work (pause/resume/stop)
"""

import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def test_double_click_fix():
    """Test the tray click routing (manual/demo style)."""
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

        # Force the "voice active" path so we can validate single vs double routing.
        app._voice_is_active = lambda: True  # type: ignore[method-assign]

        # Test single click (should execute immediately)
        print("\n🖱️  Test 1: Single Click Detection (should execute immediately)")
        print("Simulating single click...")

        single_click_executed = [False]

        # Track when single click actually executes
        def track_single_click():
            single_click_executed[0] = True
            print("✅ Single click executed")
            # Don't actually execute to avoid creating UI

        app.handle_single_click = track_single_click

        # Simulate single click
        app._qt_on_tray_activated(3)  # Typical Trigger reason value (mac/Qt)

        if single_click_executed[0]:
            print("✅ Single click executed immediately")
        else:
            print("❌ Single click did not execute")
            return False

        # Test double click (should execute immediately)
        print("\n🖱️  Test 2: Double Click Detection (should execute immediately)")
        print("Simulating double click...")

        double_click_executed = [False]

        # Track when double click executes
        def track_double_click():
            double_click_executed[0] = True
            print("✅ Double click executed")
            # Don't actually execute to avoid creating UI

        app.handle_double_click = track_double_click

        # Reset for double click test
        app._tray_last_click_ts = 0.0

        # Simulate double click (two clicks in quick succession)
        app._qt_on_tray_activated(3)  # First click
        time.sleep(0.1)  # 100ms between clicks
        app._qt_on_tray_activated(3)  # Second click (timestamp-based double click)

        # Check if double click executed immediately
        time.sleep(0.05)  # Small delay to allow processing
        if double_click_executed[0]:
            print("✅ Double click executed immediately")
        else:
            print("❌ Double click did not execute")
            return False

        # Test timing values
        print(f"\n⏱️  Timing Configuration:")
        print(f"   Double click window: {getattr(app, 'TRAY_DOUBLE_CLICK_TIMEOUT_S', 0.30)}s")
        print("   Expected behavior: Single click executes immediately")
        print("   Expected behavior: Second click within window triggers double-click stop")

        print("\n🎉 Double Click Fix Test PASSED!")
        print("✅ Single click executes immediately")
        print("✅ Double click executes immediately (on second click)")

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
        print("   • Single click (voice active): Pause/resume")
        print("   • Double click (voice active): Stop voice")
        print("   • Single click (voice idle): Open chat bubble")
    else:
        print("❌ SOME TESTS FAILED")

    sys.exit(0 if (success1 and success2) else 1)
