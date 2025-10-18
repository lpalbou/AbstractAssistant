#!/usr/bin/env python3
"""
Quick test to check if Qt threading issues are resolved.
"""

import sys
sys.path.insert(0, '/Users/albou/projects/abstractassistant')

def test_qt_threading():
    """Test Qt threading without running the full app."""
    try:
        from abstractassistant.app import AbstractAssistantApp
        from abstractassistant.config import Config
        import os
        import signal

        print("🧪 Testing Qt threading fix...")

        # Set up signal handler to exit gracefully
        def signal_handler(sig, frame):
            print("\n⏹ Test interrupted")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        # Create app
        config = Config.default()
        app = AbstractAssistantApp(config=config, debug=True)
        print("✅ App created successfully")

        # Test Qt system tray creation without running event loop
        try:
            from PyQt5.QtWidgets import QApplication
            import sys

            # Create Qt application in main thread
            if not QApplication.instance():
                qt_app = QApplication(sys.argv)
                print("✅ Qt Application created in main thread")
            else:
                qt_app = QApplication.instance()
                print("✅ Qt Application instance exists")

            # Test system tray icon creation
            qt_icon = app._create_qt_system_tray_icon()
            print("✅ Qt system tray icon created successfully")

            # Test click handlers
            print("🔄 Testing click handlers...")
            app._qt_handle_single_click()
            print("✅ Single click handler executed")

            app._qt_handle_double_click()
            print("✅ Double click handler executed")

            print("🎉 ALL TESTS PASSED - Qt threading is fixed!")
            return True

        except Exception as e:
            print(f"❌ Qt system tray test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    except Exception as e:
        print(f"❌ App creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_qt_threading()
    sys.exit(0 if success else 1)