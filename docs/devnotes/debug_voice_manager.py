#!/usr/bin/env python3
"""
Debug script to compare VoiceManager implementations.
"""

import sys
import time

# Add the abstractassistant module to the path
sys.path.insert(0, '/Users/albou/projects/abstractassistant')

def test_direct_abstractvoice():
    """Test AbstractVoice directly to see if it works."""
    print("🧪 Testing AbstractVoice directly...")

    try:
        from abstractvoice import VoiceManager as AbstractVoiceManager

        vm = AbstractVoiceManager(debug_mode=True)
        print("✅ AbstractVoice VoiceManager initialized directly")

        # Test speech
        vm.speak("Testing AbstractVoice directly for pause and resume functionality.")
        time.sleep(1.5)  # Wait for speech to start

        if vm.is_speaking():
            print("🔊 Speech is active, testing pause...")
            success = vm.pause_speaking()
            print(f"⏸ Direct AbstractVoice pause: {'Success' if success else 'Failed'}")

            if success:
                time.sleep(1)
                print("🔊 Testing resume...")
                success = vm.resume_speaking()
                print(f"▶ Direct AbstractVoice resume: {'Success' if success else 'Failed'}")

                time.sleep(1)
                vm.stop_speaking()
                print("⏹ Direct AbstractVoice stopped")

        vm.cleanup()
        return True

    except Exception as e:
        print(f"❌ Direct AbstractVoice test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_wrapped_voicemanager():
    """Test AbstractAssistant's VoiceManager wrapper."""
    print("\n🧪 Testing AbstractAssistant VoiceManager wrapper...")

    try:
        from abstractassistant.core.tts_manager import VoiceManager

        vm = VoiceManager(debug_mode=True)
        print("✅ AbstractAssistant VoiceManager initialized")

        # Check internal AbstractVoice manager
        print(f"📝 Internal _abstractvoice_manager type: {type(vm._abstractvoice_manager)}")
        print(f"📝 Has pause_speaking method: {hasattr(vm._abstractvoice_manager, 'pause_speaking') if vm._abstractvoice_manager else 'No manager'}")
        print(f"📝 Has resume_speaking method: {hasattr(vm._abstractvoice_manager, 'resume_speaking') if vm._abstractvoice_manager else 'No manager'}")
        print(f"📝 Has is_paused method: {hasattr(vm._abstractvoice_manager, 'is_paused') if vm._abstractvoice_manager else 'No manager'}")

        # Test speech
        success = vm.speak("Testing AbstractAssistant VoiceManager wrapper for pause and resume.")
        print(f"🔊 Speak: {'Success' if success else 'Failed'}")

        if success:
            time.sleep(1.5)  # Wait for speech to start

            print(f"📝 Current state: {vm.get_state()}")
            print(f"📝 Is speaking: {vm.is_speaking()}")

            if vm.is_speaking():
                print("🔊 Speech is active, testing pause...")
                success = vm.pause()
                print(f"⏸ Wrapped pause: {'Success' if success else 'Failed'}")

                if success:
                    time.sleep(0.5)
                    print(f"📝 State after pause: {vm.get_state()}")
                    print(f"📝 Is paused: {vm.is_paused()}")

                    time.sleep(1)
                    print("🔊 Testing resume...")
                    success = vm.resume()
                    print(f"▶ Wrapped resume: {'Success' if success else 'Failed'}")

                    if success:
                        time.sleep(0.5)
                        print(f"📝 State after resume: {vm.get_state()}")

                    time.sleep(1)
                    vm.stop()
                    print("⏹ Wrapped stop executed")
            else:
                print("❌ Speech was not active when we tried to pause")

        vm.cleanup()
        return True

    except Exception as e:
        print(f"❌ Wrapped VoiceManager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_method_comparison():
    """Compare methods between direct AbstractVoice and wrapper."""
    print("\n🧪 Comparing methods...")

    try:
        from abstractvoice import VoiceManager as AbstractVoiceManager
        from abstractassistant.core.tts_manager import VoiceManager

        # Direct AbstractVoice
        direct_vm = AbstractVoiceManager(debug_mode=True)
        print("📝 Direct AbstractVoice methods:")
        methods = [attr for attr in dir(direct_vm) if not attr.startswith('_')]
        for method in sorted(methods):
            if 'speak' in method.lower() or 'pause' in method.lower() or 'resume' in method.lower():
                print(f"  - {method}")

        # Wrapper
        wrapped_vm = VoiceManager(debug_mode=True)
        print("📝 AbstractAssistant VoiceManager methods:")
        methods = [attr for attr in dir(wrapped_vm) if not attr.startswith('_')]
        for method in sorted(methods):
            if 'speak' in method.lower() or 'pause' in method.lower() or 'resume' in method.lower():
                print(f"  - {method}")

        # Test if methods exist on internal manager
        internal = wrapped_vm._abstractvoice_manager
        if internal:
            print("📝 Internal AbstractVoice manager methods:")
            methods = [attr for attr in dir(internal) if not attr.startswith('_')]
            for method in sorted(methods):
                if 'speak' in method.lower() or 'pause' in method.lower() or 'resume' in method.lower():
                    print(f"  - {method}")

        direct_vm.cleanup()
        wrapped_vm.cleanup()

        return True

    except Exception as e:
        print(f"❌ Method comparison failed: {e}")
        return False


def main():
    """Run debug tests."""
    print("🐛 Starting VoiceManager Debug Session...")

    tests = [
        test_direct_abstractvoice,
        test_wrapped_voicemanager,
        test_method_comparison
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            results.append(False)

    print(f"\n📊 Debug Results: {sum(results)}/{len(results)} tests passed")

    if not all(results):
        print("🐛 Found issues! Check the output above for details.")
    else:
        print("✅ All debug tests passed - issue may be elsewhere.")


if __name__ == "__main__":
    main()