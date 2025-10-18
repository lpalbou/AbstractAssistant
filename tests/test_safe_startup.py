#!/usr/bin/env python3
"""
Test safe startup of AbstractAssistant to verify no security issues.
"""

import sys
import subprocess
import time
import os
import signal
sys.path.insert(0, '/Users/albou/projects/abstractassistant')

def test_safe_startup():
    """Test that the app starts safely without requesting privileges."""
    print("🧪 Testing Safe Startup...")
    print("=" * 50)

    try:
        # Start the app as a subprocess
        print("🚀 Starting AbstractAssistant subprocess...")

        process = subprocess.Popen(
            [sys.executable, '-m', 'abstractassistant.cli'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # Wait a few seconds to see if it starts without issues
        print("⏳ Waiting 3 seconds for startup...")
        time.sleep(3)

        # Check if process is still running (good sign)
        if process.poll() is None:
            print("✅ Process is running successfully")

            # Try to get some output
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                # This is expected since the app should be running
                process.terminate()
                process.wait()
                stdout, stderr = process.communicate()

            print("📋 Startup Output:")
            if stdout:
                print("STDOUT:", stdout[:500])
            if stderr:
                print("STDERR:", stderr[:500])

            # Check for security-related keywords that shouldn't be there
            security_issues = [
                'lldb', 'process attach', 'pid', 'Developer Tool Access',
                'sudo', 'privileges', 'permission denied'
            ]

            combined_output = (stdout + stderr).lower()
            found_issues = [issue for issue in security_issues if issue.lower() in combined_output]

            if found_issues:
                print(f"❌ SECURITY ISSUES FOUND: {found_issues}")
                return False
            else:
                print("✅ NO SECURITY ISSUES DETECTED")

            # Check for Qt threading issues
            qt_issues = [
                'QApplication was not created in the main() thread',
                'QBasicTimer can only be used with threads started with QThread'
            ]

            found_qt_issues = [issue for issue in qt_issues if issue in stdout + stderr]

            if found_qt_issues:
                print(f"❌ QT THREADING ISSUES FOUND: {found_qt_issues}")
                return False
            else:
                print("✅ NO QT THREADING ISSUES DETECTED")

            print("🎉 SAFE STARTUP TEST PASSED!")
            return True

        else:
            print(f"❌ Process exited with code: {process.returncode}")
            stdout, stderr = process.communicate()
            print("STDOUT:", stdout)
            print("STDERR:", stderr)
            return False

    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Clean up any remaining processes
        try:
            if 'process' in locals() and process.poll() is None:
                process.terminate()
                process.wait()
        except:
            pass

if __name__ == "__main__":
    success = test_safe_startup()
    print("\n" + "=" * 50)
    if success:
        print("🎯 SAFE STARTUP VERIFIED - NO SECURITY ISSUES")
        print("✅ App can be run without special privileges")
        print("✅ No Qt threading errors")
        print("✅ No debugging process attachment")
    else:
        print("❌ STARTUP ISSUES DETECTED - NEEDS INVESTIGATION")

    sys.exit(0 if success else 1)