#!/usr/bin/env python3
"""
Installation script for AbstractAssistant with automatic macOS app bundle creation.

This script provides an enhanced installation experience for macOS users,
automatically creating a Dock-accessible app bundle.
"""

import sys
import subprocess
import os
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"   Error: {e.stderr}")
        return False


def install_abstractassistant():
    """Install AbstractAssistant with enhanced macOS support."""
    print("🚀 Installing AbstractAssistant...")
    print("="*60)
    
    # Check if we're on macOS
    if sys.platform != "darwin":
        print("⚠️  This enhanced installer is designed for macOS")
        print("   Installing standard package...")
        return run_command("pip install abstractassistant", "Standard installation")
    
    # Check if pip is available
    if not run_command("pip --version", "Checking pip availability"):
        print("❌ pip is not available. Please install pip first.")
        return False
    
    # Install the package
    if not run_command("pip install abstractassistant", "Installing AbstractAssistant"):
        return False
    
    # Create macOS app bundle
    print("\n🍎 Creating macOS app bundle...")
    try:
        # Import the app bundle generator
        import abstractassistant.setup_macos_app as setup_macos
        
        # Create the app bundle
        package_dir = Path(abstractassistant.__file__).parent
        generator = setup_macos.MacOSAppBundleGenerator(package_dir)
        
        if generator.generate_app_bundle():
            print("\n🎉 Installation complete!")
            print("="*60)
            print("✅ AbstractAssistant installed successfully")
            print("✅ macOS app bundle created")
            print("✅ Available in Applications folder")
            print("✅ Can be launched from Dock or Spotlight")
            print("\n🚀 You can now:")
            print("   • Click the AbstractAssistant icon in your Dock")
            print("   • Search for 'AbstractAssistant' in Spotlight")
            print("   • Use 'assistant' command in Terminal")
            print("="*60)
            return True
        else:
            print("\n⚠️  Installation completed, but app bundle creation failed")
            print("   You can still use 'assistant' command from terminal")
            return True
            
    except Exception as e:
        print(f"\n⚠️  App bundle creation failed: {e}")
        print("   Installation completed successfully")
        print("   You can still use 'assistant' command from terminal")
        return True


def main():
    """Main installation function."""
    print("AbstractAssistant Enhanced Installer")
    print("===================================")
    
    success = install_abstractassistant()
    
    if success:
        print("\n🎉 Installation completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Installation failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
