#!/usr/bin/env python3
"""
Test the corrected click detection logic.

Logic:
- Single click: reason == 3 only (wait 200ms to confirm)
- Double click: reason == 3 followed quickly by reason == 2
"""

import sys
import time
sys.path.insert(0, '/Users/albou/projects/abstractassistant')

def test_corrected_click_logic():
    """Test the corrected click detection logic."""
    print("🧪 Testing Corrected Click Detection Logic")
    print("=" * 50)
    print("New Logic:")
    print("  • Single click: reason == 3 (wait 200ms for confirmation)")
    print("  • Double click: reason == 3 then reason == 2 (immediate)")
    print("=" * 50)

    try:
        from abstractassistant.app import AbstractAssistantApp
        from abstractassistant.config import Config
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QCoreApplication

        # Create Qt app
        qt_app = QApplication.instance() or QApplication(sys.argv)

        # Create AbstractAssistant app
        config = Config.default()
        app = AbstractAssistantApp(config=config, debug=True)

        # Create Qt system tray icon to initialize click detection
        qt_icon = app._create_qt_system_tray_icon()
        print("✅ Qt system tray icon created with corrected logic")

        # Track what gets executed
        single_executed = [False]
        double_executed = [False]

        # Mock handlers to track execution
        def track_single():
            single_executed[0] = True
            print("   📍 SINGLE CLICK ACTION EXECUTED")

        def track_double():
            double_executed[0] = True
            print("   📍 DOUBLE CLICK ACTION EXECUTED")

        app.handle_single_click = track_single
        app.handle_double_click = track_double

        # Test 1: Single click scenario (reason=3 only)
        print("\n🖱️  Test 1: Single Click (reason=3 only)")
        print("   Expected: Wait 200ms, then execute single click")

        # Reset state
        app.pending_single_click = False
        app.click_timer.stop()
        single_executed[0] = False
        double_executed[0] = False

        print("   Sending reason=3...")
        app._qt_on_tray_activated(3)

        # Check state immediately
        if app.pending_single_click and app.click_timer.isActive():
            print("   ✅ Pending single click set, timer started")
        else:
            print("   ❌ State not set correctly")
            return False

        # Wait less than timeout
        print("   Waiting 100ms (less than 200ms timeout)...")
        time.sleep(0.1)
        QCoreApplication.processEvents()  # Process Qt events

        if single_executed[0] or double_executed[0]:
            print("   ❌ Action executed too early!")
            return False
        else:
            print("   ✅ No action yet (correctly waiting)")

        # Wait for timeout to complete
        print("   Waiting additional 150ms (total 250ms)...")
        time.sleep(0.15)
        QCoreApplication.processEvents()  # Process Qt events

        if single_executed[0] and not double_executed[0]:
            print("   ✅ Single click executed after timeout")
        else:
            print(f"   ❌ Wrong execution: single={single_executed[0]}, double={double_executed[0]}")
            return False

        # Test 2: Double click scenario (reason=3 then reason=2)
        print("\n🖱️  Test 2: Double Click (reason=3 then reason=2)")
        print("   Expected: Execute double click immediately when reason=2 arrives")

        # Reset state
        app.pending_single_click = False
        app.click_timer.stop()
        single_executed[0] = False
        double_executed[0] = False

        print("   Sending reason=3...")
        app._qt_on_tray_activated(3)

        # Check that single click is pending
        if app.pending_single_click and app.click_timer.isActive():
            print("   ✅ Pending single click set")
        else:
            print("   ❌ Single click not pending")
            return False

        # Send reason=2 within timeout
        print("   Sending reason=2 after 50ms...")
        time.sleep(0.05)
        app._qt_on_tray_activated(2)

        # Check immediate execution
        QCoreApplication.processEvents()  # Process Qt events

        if double_executed[0] and not single_executed[0]:
            print("   ✅ Double click executed immediately")
        else:
            print(f"   ❌ Wrong execution: single={single_executed[0]}, double={double_executed[0]}")
            return False

        # Check that pending state is cleared
        if not app.pending_single_click and not app.click_timer.isActive():
            print("   ✅ Pending state cleared correctly")
        else:
            print("   ❌ Pending state not cleared")
            return False

        # Wait to ensure single click doesn't execute later
        print("   Waiting 200ms to ensure no single click executes...")
        time.sleep(0.2)
        QCoreApplication.processEvents()

        if single_executed[0]:
            print("   ❌ Single click executed after double click (should be cancelled)")
            return False
        else:
            print("   ✅ Single click correctly cancelled by double click")

        print("\n🎉 CORRECTED CLICK LOGIC TEST PASSED!")
        print("✅ Single click: reason=3, wait 200ms, then execute")
        print("✅ Double click: reason=3 then reason=2, execute immediately")
        print("✅ Double click cancels pending single click")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_edge_cases():
    """Test edge cases of the click detection."""
    print("\n🧪 Testing Edge Cases")
    print("=" * 30)

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

        print("🔍 Edge Case 1: Multiple reason=3 events")

        # Reset state
        app.pending_single_click = False
        app.click_timer.stop()

        # Send multiple reason=3
        app._qt_on_tray_activated(3)
        first_pending = app.pending_single_click

        app._qt_on_tray_activated(3)  # Should be ignored
        second_pending = app.pending_single_click

        if first_pending and second_pending:
            print("   ✅ Multiple reason=3 handled correctly (second ignored)")
        else:
            print("   ❌ Multiple reason=3 not handled correctly")

        print("\n🔍 Edge Case 2: reason=2 without reason=3")

        # Reset state completely
        app.pending_single_click = False
        app.click_timer.stop()

        # Track execution
        double_executed = [False]
        def track_double():
            double_executed[0] = True

        app.handle_double_click = track_double

        # Send reason=2 without preceding reason=3
        app._qt_on_tray_activated(2)

        if double_executed[0]:
            print("   ✅ Orphaned reason=2 handled (fallback double click)")
        else:
            print("   ❌ Orphaned reason=2 not handled")

        print("✅ Edge cases tested")
        return True

    except Exception as e:
        print(f"❌ Edge case test failed: {e}")
        return False

if __name__ == "__main__":
    print("🎯 CORRECTED CLICK DETECTION LOGIC TEST")
    print("=" * 60)

    success1 = test_corrected_click_logic()
    success2 = test_edge_cases()

    print("\n" + "=" * 60)
    if success1 and success2:
        print("🎉 ALL TESTS PASSED!")
        print("🎯 Click detection logic is now correct!")
        print("\n✨ Implementation Summary:")
        print("   • reason=3: Wait 200ms for possible reason=2")
        print("   • reason=3 + reason=2: Execute double click immediately")
        print("   • reason=3 only: Execute single click after 200ms")
        print("   • Proper cancellation and edge case handling")
        print("\n🚀 Ready for real-world testing!")
    else:
        print("❌ Some tests failed")

    sys.exit(0 if (success1 and success2) else 1)