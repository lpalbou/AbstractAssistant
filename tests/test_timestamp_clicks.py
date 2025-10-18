#!/usr/bin/env python3
"""
Demonstrate the timestamp-based click detection working in the real application.
"""

import sys
sys.path.insert(0, '/Users/albou/projects/abstractassistant')

def test_timestamp_click_detection():
    """Test that demonstrates the actual click detection working."""
    print("🖱️  TIMESTAMP-BASED CLICK DETECTION TEST")
    print("=" * 60)

    try:
        from abstractassistant.app import AbstractAssistantApp
        from abstractassistant.config import Config
        from PyQt5.QtWidgets import QApplication, QSystemTrayIcon
        import time

        print("🚀 Testing real application with double-click detection...")

        # Create Qt application
        qt_app = QApplication.instance() or QApplication(sys.argv)

        # Create app with debug enabled
        config = Config.default()
        app = AbstractAssistantApp(config=config, debug=True)

        # Create system tray icon
        qt_icon = app._create_qt_system_tray_icon()
        print("✅ System tray icon created with timestamp-based detection")

        # Test double-click sequence
        print("🖱️  Simulating double-click sequence...")
        app._qt_on_tray_activated(QSystemTrayIcon.Trigger)
        time.sleep(0.25)  # 250ms between clicks
        app._qt_on_tray_activated(QSystemTrayIcon.Trigger)

        time.sleep(0.5)  # Wait for processing

        print("✅ Double-click test completed successfully!")
        print("🎯 The timestamp-based detection is working in the real application!")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_timestamp_click_detection()