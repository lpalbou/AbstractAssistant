#!/usr/bin/env python3
"""
Custom setup script for AbstractAssistant with macOS app bundle creation.
"""

import sys
import os
from pathlib import Path
from setuptools import setup, find_packages
from setuptools.command.install import install


class PostInstallCommand(install):
    """Custom install command to run post-installation tasks."""
    
    def run(self):
        """Run the standard install and then post-install tasks."""
        # Run the standard install
        install.run(self)
        
        # Run post-install tasks
        self.post_install()
    
    def post_install(self):
        """Run post-installation tasks."""
        try:
            # Import and run the macOS app bundle creation
            from setup_macos_app import create_macos_app_bundle
            
            print("\n" + "="*60)
            print("Running post-installation tasks...")
            print("="*60)
            
            # Create macOS app bundle if on macOS
            if sys.platform == "darwin":
                print("Detected macOS - creating app bundle...")
                success = create_macos_app_bundle()
                if success:
                    print("\n🎉 Installation complete!")
                    print("   AbstractAssistant is now available in your Applications folder")
                    print("   You can launch it from the Dock or Spotlight!")
                else:
                    print("\n⚠️  Installation completed, but app bundle creation failed")
                    print("   You can still use 'assistant' command from terminal")
            else:
                print("Non-macOS system detected - skipping app bundle creation")
                print("   Use 'assistant' command to launch the application")
            
            print("="*60)
            
        except Exception as e:
            print(f"\n⚠️  Post-installation task failed: {e}")
            print("   Installation completed successfully, but some features may not be available")


# Read the pyproject.toml to get package metadata
def read_pyproject_toml():
    """Read package metadata from pyproject.toml."""
    import tomli
    
    pyproject_path = Path(__file__).parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        return tomli.load(f)


if __name__ == "__main__":
    # Read metadata from pyproject.toml
    pyproject_data = read_pyproject_toml()
    project_data = pyproject_data["project"]
    
    # Setup configuration
    setup(
        name=project_data["name"],
        version=project_data["version"],
        description=project_data["description"],
        author=project_data["authors"][0]["name"],
        author_email=project_data["authors"][0]["email"],
        url=project_data["urls"]["Homepage"],
        packages=find_packages(),
        python_requires=project_data["requires-python"],
        install_requires=project_data["dependencies"],
        extras_require=project_data.get("optional-dependencies", {}),
        entry_points={
            "console_scripts": project_data["scripts"],
        },
        classifiers=project_data["classifiers"],
        keywords=project_data["keywords"],
        license=project_data["license"]["text"],
        long_description=Path("README.md").read_text(),
        long_description_content_type="text/markdown",
        cmdclass={
            'install': PostInstallCommand,
        },
    )
