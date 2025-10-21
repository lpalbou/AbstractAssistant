#!/usr/bin/env python3
"""
macOS App Bundle Generator for AbstractAssistant.

This module creates a macOS .app bundle during installation,
allowing users to launch AbstractAssistant from the Dock.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class MacOSAppBundleGenerator:
    """Generates macOS app bundles for AbstractAssistant."""
    
    def __init__(self, package_dir: Path):
        """Initialize the app bundle generator.
        
        Args:
            package_dir: Path to the abstractassistant package directory
        """
        self.package_dir = package_dir
        self.app_name = "AbstractAssistant"
        self.app_bundle_path = Path("/Applications") / f"{self.app_name}.app"
        
    def is_macos(self) -> bool:
        """Check if running on macOS."""
        return sys.platform == "darwin"
    
    def has_permissions(self) -> bool:
        """Check if we have permissions to write to /Applications."""
        try:
            test_file = Path("/Applications") / ".test_write_permission"
            test_file.touch()
            test_file.unlink()
            return True
        except (PermissionError, OSError):
            return False
    
    def create_app_bundle_structure(self) -> bool:
        """Create the basic app bundle directory structure."""
        try:
            # Create main directories
            contents_dir = self.app_bundle_path / "Contents"
            macos_dir = contents_dir / "MacOS"
            resources_dir = contents_dir / "Resources"
            
            for directory in [contents_dir, macos_dir, resources_dir]:
                directory.mkdir(parents=True, exist_ok=True)
            
            return True
        except Exception as e:
            print(f"Error creating app bundle structure: {e}")
            return False
    
    def generate_app_icon(self) -> bool:
        """Generate the app icon using the existing icon generator."""
        try:
            # Import the icon generator
            sys.path.insert(0, str(self.package_dir))
            from abstractassistant.utils.icon_generator import IconGenerator
            
            # Generate high-resolution icon
            generator = IconGenerator(size=512)
            icon = generator.create_app_icon('blue', animated=False)
            
            # Save as PNG
            icon_path = self.app_bundle_path / "Contents" / "Resources" / "icon.png"
            icon.save(str(icon_path))
            
            # Create ICNS file
            return self._create_icns_file(icon_path)
            
        except Exception as e:
            print(f"Error generating app icon: {e}")
            return False
    
    def _create_icns_file(self, png_path: Path) -> bool:
        """Create ICNS file from PNG using macOS iconutil."""
        try:
            # Create iconset directory
            iconset_dir = png_path.parent / "temp_icons.iconset"
            iconset_dir.mkdir(exist_ok=True)
            
            # Load the PNG and create different sizes
            icon = Image.open(png_path)
            sizes = [
                (16, 'icon_16x16.png'),
                (32, 'icon_16x16@2x.png'),
                (32, 'icon_32x32.png'),
                (64, 'icon_32x32@2x.png'),
                (128, 'icon_128x128.png'),
                (256, 'icon_128x128@2x.png'),
                (256, 'icon_256x256.png'),
                (512, 'icon_256x256@2x.png'),
                (512, 'icon_512x512.png'),
                (1024, 'icon_512x512@2x.png')
            ]
            
            for size, filename in sizes:
                resized = icon.resize((size, size), Image.Resampling.LANCZOS)
                resized.save(iconset_dir / filename)
            
            # Convert to ICNS
            icns_path = png_path.parent / "icon.icns"
            result = subprocess.run([
                'iconutil', '-c', 'icns', str(iconset_dir), 
                '-o', str(icns_path)
            ], capture_output=True, text=True)
            
            # Clean up
            shutil.rmtree(iconset_dir)
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"Error creating ICNS file: {e}")
            return False
    
    def create_info_plist(self) -> bool:
        """Create the Info.plist file."""
        try:
            plist_content = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>AbstractAssistant</string>
    <key>CFBundleIdentifier</key>
    <string>ai.abstractcore.abstractassistant</string>
    <key>CFBundleName</key>
    <string>AbstractAssistant</string>
    <key>CFBundleDisplayName</key>
    <string>AbstractAssistant</string>
    <key>CFBundleVersion</key>
    <string>0.2.5</string>
    <key>CFBundleShortVersionString</key>
    <string>0.2.5</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleIconFile</key>
    <string>icon.icns</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
    <key>LSUIElement</key>
    <true/>
    <key>NSAppleScriptEnabled</key>
    <false/>
    <key>CFBundleDocumentTypes</key>
    <array/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
</dict>
</plist>'''
            
            plist_path = self.app_bundle_path / "Contents" / "Info.plist"
            plist_path.write_text(plist_content)
            return True
            
        except Exception as e:
            print(f"Error creating Info.plist: {e}")
            return False
    
    def create_launch_script(self) -> bool:
        """Create the executable launch script."""
        try:
            script_content = '''#!/bin/bash

# AbstractAssistant macOS App Launcher
# This script launches the AbstractAssistant application

# Find the Python executable and package
PYTHON_EXEC="$(which python3)"
if [ -z "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="$(which python)"
fi

if [ -z "$PYTHON_EXEC" ]; then
    echo "Error: Python not found in PATH"
    exit 1
fi

# Launch the assistant
exec "$PYTHON_EXEC" -m abstractassistant.cli "$@"'''
            
            script_path = self.app_bundle_path / "Contents" / "MacOS" / "AbstractAssistant"
            script_path.write_text(script_content)
            
            # Make executable
            os.chmod(script_path, 0o755)
            return True
            
        except Exception as e:
            print(f"Error creating launch script: {e}")
            return False
    
    def generate_app_bundle(self) -> bool:
        """Generate the complete macOS app bundle."""
        if not self.is_macos():
            print("macOS app bundle generation is only available on macOS")
            return False
        
        if not self.has_permissions():
            print("Insufficient permissions to create app bundle in /Applications")
            print("Please run with sudo or manually copy the app bundle")
            return False
        
        print("Creating macOS app bundle...")
        
        # Remove existing bundle if it exists
        if self.app_bundle_path.exists():
            shutil.rmtree(self.app_bundle_path)
        
        # Create bundle structure
        if not self.create_app_bundle_structure():
            return False
        
        # Generate icon
        if not self.generate_app_icon():
            return False
        
        # Create Info.plist
        if not self.create_info_plist():
            return False
        
        # Create launch script
        if not self.create_launch_script():
            return False
        
        print(f"✅ macOS app bundle created successfully!")
        print(f"   Location: {self.app_bundle_path}")
        print(f"   You can now launch AbstractAssistant from the Dock!")
        
        return True


def create_macos_app_bundle():
    """Main function to create macOS app bundle during installation."""
    try:
        # Find the package directory
        package_dir = Path(__file__).parent
        
        generator = MacOSAppBundleGenerator(package_dir)
        return generator.generate_app_bundle()
        
    except Exception as e:
        print(f"Error creating macOS app bundle: {e}")
        return False


if __name__ == "__main__":
    success = create_macos_app_bundle()
    sys.exit(0 if success else 1)
