#!/usr/bin/env python3
"""
Create macOS App Bundle for AbstractAssistant.

This script can be run after installation to create a macOS app bundle
that allows launching AbstractAssistant from the Dock.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

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
        """Generate or preserve the app icon."""
        try:
            icon_path = self.app_bundle_path / "Contents" / "Resources" / "icon.png"
            
            # Look for custom icons in multiple locations
            custom_icon_paths = [
                # Project directory bundle (development) - inside package directory
                Path(self.package_dir).parent / "AbstractAssistant.app" / "Contents" / "Resources" / "icon.png",
                # Also check if it's in the package directory itself
                Path(self.package_dir) / "AbstractAssistant.app" / "Contents" / "Resources" / "icon.png",
                # Any icon.png in the project root
                Path(self.package_dir).parent / "icon.png",
                # Any icon.png in the package directory
                Path(self.package_dir) / "icon.png",
            ]
            
            custom_icon_found = False
            
            # Try each custom icon location
            for custom_path in custom_icon_paths:
                if custom_path and custom_path.exists():
                    print(f"Using existing custom icon from {custom_path}")
                    shutil.copy2(str(custom_path), str(icon_path))
                    custom_icon_found = True
                    break
            
            # If no custom icon found, try to restore from git
            if not custom_icon_found:
                try:
                    git_icon_path = self.package_dir.parent / "AbstractAssistant.app" / "Contents" / "Resources" / "icon.png"
                    if git_icon_path.parent.parent.parent.exists():  # Check if AbstractAssistant.app exists
                        # Try to get the icon from git
                        result = subprocess.run([
                            'git', 'show', 'HEAD:AbstractAssistant.app/Contents/Resources/icon.png'
                        ], cwd=str(self.package_dir.parent), capture_output=True)
                        
                        if result.returncode == 0:
                            print("Restoring custom icon from git history")
                            with open(str(icon_path), 'wb') as f:
                                f.write(result.stdout)
                            custom_icon_found = True
                except Exception as git_error:
                    print(f"Could not restore icon from git: {git_error}")
            
            # If still no custom icon, generate one
            if not custom_icon_found:
                print("Generating new icon using IconGenerator")
                # Import the icon generator
                sys.path.insert(0, str(self.package_dir))
                from abstractassistant.utils.icon_generator import IconGenerator
                
                # Generate high-resolution icon
                generator = IconGenerator(size=512)
                icon = generator.create_app_icon('blue', animated=False)
                
                # Save as PNG
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
    <string>0.3.2</string>
    <key>CFBundleShortVersionString</key>
    <string>0.3.2</string>
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

# Set up environment paths for GUI launch (common locations)
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

# Add user-specific Python paths if they exist
if [ -d "$HOME/.pyenv/shims" ]; then
    export PATH="$HOME/.pyenv/shims:$PATH"
fi

if [ -d "$HOME/.local/bin" ]; then
    export PATH="$HOME/.local/bin:$PATH"
fi

if [ -d "/opt/anaconda3/bin" ]; then
    export PATH="/opt/anaconda3/bin:$PATH"
fi

if [ -d "$HOME/anaconda3/bin" ]; then
    export PATH="$HOME/anaconda3/bin:$PATH"
fi

# Function to find Python with abstractassistant installed
find_python_with_abstractassistant() {
    # First try pyenv's active Python (most reliable)
    if [ -x "$HOME/.pyenv/shims/python3" ]; then
        if "$HOME/.pyenv/shims/python3" -c "import abstractassistant" 2>/dev/null; then
            echo "$HOME/.pyenv/shims/python3"
            return 0
        fi
    fi
    
    # Try PATH-based search (respects current environment)
    for python_cmd in python3 python python3.13 python3.12 python3.11 python3.10 python3.9; do
        if command -v "$python_cmd" >/dev/null 2>&1; then
            if "$python_cmd" -c "import abstractassistant" 2>/dev/null; then
                echo "$python_cmd"
                return 0
            fi
        fi
    done
    
    # Try specific pyenv versions (sorted by version number, newest first)
    for version_dir in $(ls -1v "$HOME/.pyenv/versions/" 2>/dev/null | sort -V -r); do
        py="$HOME/.pyenv/versions/$version_dir/bin/python3"
        if [ -x "$py" ] && "$py" -c "import abstractassistant" 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done
    
    # Try other common locations
    for python_path in \\
        "/usr/local/bin/python3" \\
        "/opt/homebrew/bin/python3" \\
        "/usr/bin/python3" \\
        "/opt/anaconda3/bin/python" \\
        "$HOME/anaconda3/bin/python" \\
        "/usr/local/anaconda3/bin/python"; do
        
        if [ -x "$python_path" ] && "$python_path" -c "import abstractassistant" 2>/dev/null; then
            echo "$python_path"
            return 0
        fi
    done
    
    return 1
}

# Find Python with AbstractAssistant
PYTHON_EXEC=$(find_python_with_abstractassistant)

if [ -z "$PYTHON_EXEC" ]; then
    osascript -e 'display dialog "AbstractAssistant not found in any Python installation.\\n\\nPlease install it with:\\npip install abstractassistant\\n\\nOr run the create-app-bundle command after installation." with title "AbstractAssistant" buttons {"OK"} default button "OK" with icon caution'
    exit 1
fi

# Change to a neutral directory to avoid importing development versions
cd /tmp

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


def main():
    """Create macOS app bundle for AbstractAssistant."""
    try:
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
