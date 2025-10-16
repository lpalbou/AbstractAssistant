#!/usr/bin/env python3
"""
AbstractAssistant - A sleek system tray LLM interface for macOS

This is a legacy entry point. Use 'assistant' command or 'python -m abstractassistant.cli' instead.
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from abstractassistant.cli import main

if __name__ == "__main__":
    sys.exit(main())
