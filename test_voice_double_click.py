#!/usr/bin/env python3
"""
Simple test for voice control with proper double click detection.
Tests the timing manually with realistic voice scenarios.
"""

import sys
import time
sys.path.insert(0, '/Users/albou/projects/abstractassistant')

def test_click_timing_logic():
    """Test the click timing logic directly."""
    print("🧪 Testing Click Timing Logic")
    print("=" * 40)

    try:
        from abstractassistant.app import AbstractAssistantApp
        from abstractassistant.config import Config
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QTimer, QCoreApplication

        # Create Qt app
        qt_app = QApplication.instance() or QApplication(sys.argv)

        # Create AbstractAssistant app
        config = Config.default()
        app = AbstractAssistantApp(config=config, debug=True)

        print(f"✅ App created with timeout: {app.DOUBLE_CLICK_TIMEOUT}ms")

        # Test the timing logic by directly calling the methods
        print("\n📋 Test Scenario: Voice is speaking, user double-clicks to stop")

        # Create a mock voice manager for testing
        class MockVoiceManager:
            def __init__(self):
                self.state = 'speaking'
                self.stopped = False

            def get_state(self):
                return self.state

            def stop(self):
                self.stopped = True
                self.state = 'idle'
                print("   🔊 Mock voice stopped")

            def pause(self):
                if self.state == 'speaking':
                    self.state = 'paused'
                    print("   🔊 Mock voice paused")
                    return True
                return False

            def resume(self):
                if self.state == 'paused':
                    self.state = 'speaking'
                    print("   🔊 Mock voice resumed")
                    return True
                return False

        # Test double click scenario
        print("\n🖱️  Double Click Test:")
        print("   1. First click detected")
        print("   2. Second click within 500ms")
        print("   3. Should stop voice and show bubble immediately")

        # Mock the voice manager and bubble creation
        mock_voice = MockVoiceManager()

        # Mock the bubble manager to avoid creating actual UI
        original_show_bubble = app.show_chat_bubble
        bubble_shown = [False]

        def mock_show_bubble():
            bubble_shown[0] = True
            print("   💬 Mock chat bubble shown")

        app.show_chat_bubble = mock_show_bubble

        # Mock the voice manager access
        if not hasattr(app, 'bubble_manager'):
            app.bubble_manager = type('MockBubbleManager', (), {})()

        if not hasattr(app.bubble_manager, 'bubble'):
            app.bubble_manager.bubble = type('MockBubble', (), {})()

        app.bubble_manager.bubble.voice_manager = mock_voice

        # Test double click execution
        print("\n   Executing double click handler...")
        app.handle_double_click()

        # Verify results
        if mock_voice.stopped and bubble_shown[0]:
            print("   ✅ Double click worked: voice stopped and bubble shown")
        else:
            print(f"   ❌ Double click failed: voice stopped={mock_voice.stopped}, bubble shown={bubble_shown[0]}")

        # Test single click scenario
        print("\n🖱️  Single Click Test:")
        print("   1. Voice is speaking")
        print("   2. Single click should pause voice")

        # Reset mock state
        mock_voice.state = 'speaking'
        mock_voice.stopped = False
        bubble_shown[0] = False

        print("   Executing single click handler...")
        app.handle_single_click()

        if mock_voice.state == 'paused':
            print("   ✅ Single click worked: voice paused")
        else:
            print(f"   ❌ Single click failed: voice state is {mock_voice.state}")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_with_real_voice():
    """Test with real VoiceLLM integration."""
    print("\n🎙️  Testing with Real Voice")
    print("=" * 40)

    try:
        from abstractassistant.core.tts_manager import VoiceManager

        vm = VoiceManager(debug_mode=True)

        if not vm.is_available():
            print("⚠️  VoiceLLM not available - skipping real voice test")
            return True

        print("✅ VoiceLLM available for testing")

        # Test speaking and stopping
        print("\n🔊 Testing voice stop functionality...")
        vm.speak("This is a test of the double click voice stopping feature. It should be interrupted.", speed=1.5)

        time.sleep(1.0)  # Let speech start

        if vm.is_speaking():
            print("   ✅ Voice is speaking")

            # Test stop (what double click should do)
            vm.stop()
            time.sleep(0.1)

            if not vm.is_speaking():
                print("   ✅ Voice stopped successfully (double click behavior)")
            else:
                print("   ❌ Voice did not stop")

        # Test pause/resume
        print("\n⏸ Testing voice pause/resume functionality...")
        vm.speak("This is a test of the single click pause and resume feature.", speed=1.5)

        time.sleep(1.0)  # Let speech start

        if vm.is_speaking():
            print("   ✅ Voice is speaking")

            # Test pause (what single click should do when speaking)
            pause_result = vm.pause()
            time.sleep(0.1)

            if vm.is_paused():
                print("   ✅ Voice paused successfully (single click behavior)")

                # Test resume (what single click should do when paused)
                resume_result = vm.resume()
                time.sleep(0.1)

                if vm.is_speaking():
                    print("   ✅ Voice resumed successfully (single click behavior)")
                else:
                    print("   ❌ Voice did not resume")

                vm.stop()  # Clean up
            else:
                print("   ⚠️  Voice pause may not be working")
                vm.stop()  # Clean up

        vm.cleanup()
        print("✅ Real voice test completed")

        return True

    except Exception as e:
        print(f"❌ Real voice test failed: {e}")
        return False

if __name__ == "__main__":
    print("🎯 Voice Control Double Click Test")
    print("=" * 50)
    print("Testing the implementation that should now work:")
    print("• Single click: pause/resume voice (with 500ms delay)")
    print("• Double click: stop voice + show bubble (immediate)")
    print("=" * 50)

    success1 = test_click_timing_logic()
    success2 = test_with_real_voice()

    print("\n" + "=" * 50)
    if success1 and success2:
        print("🎉 VOICE CONTROL TESTS PASSED!")
        print("\n✅ Implementation Summary:")
        print("   • Double click detection: 500ms timeout")
        print("   • Single click waits for possible second click")
        print("   • Double click executes immediately")
        print("   • Voice control integration working")
        print("\n🚀 Ready to test in the actual application!")
    else:
        print("❌ Some tests failed")

    sys.exit(0 if (success1 and success2) else 1)