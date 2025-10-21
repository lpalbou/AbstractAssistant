#!/usr/bin/env python3
"""
Create macOS App Bundle for AbstractAssistant.

This script can be run after installation to create a macOS app bundle
that allows launching AbstractAssistant from the Dock.
"""

import sys
from pathlib import Path


def main():
    """Create macOS app bundle for AbstractAssistant."""
    try:
        # Import the app bundle generator
        try:
            import setup_macos_app
            MacOSAppBundleGenerator = setup_macos_app.MacOSAppBundleGenerator
        except ImportError:
            # Fallback: try importing from abstractassistant package
            from abstractassistant.setup_macos_app import MacOSAppBundleGenerator
        
        # Find the package directory
        import abstractassistant
        package_dir = Path(abstractassistant.__file__).parent
        
        # Create the generator and build the app bundle
        generator = MacOSAppBundleGenerator(package_dir)
        
        print("🍎 Creating macOS app bundle for AbstractAssistant...")
        success = generator.generate_app_bundle()
        
        if success:
            print("\n🎉 Success!")
            print("   AbstractAssistant is now available in your Applications folder")
            print("   You can launch it from the Dock or Spotlight!")
            return 0
        else:
            print("\n❌ Failed to create app bundle")
            return 1
            
    except ImportError as e:
        print(f"❌ Error: {e}")
        print("   Make sure AbstractAssistant is properly installed")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
