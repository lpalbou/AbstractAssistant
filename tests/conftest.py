"""
Pytest configuration to ensure local package imports.
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Prefer sibling packages in the monorepo when running tests from the repo root.
REPO_ROOT = ROOT.parent
VOICE_PKG_ROOT = REPO_ROOT / "abstractvoice"
if VOICE_PKG_ROOT.exists() and str(VOICE_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(VOICE_PKG_ROOT))
RUNTIME_SRC_ROOT = REPO_ROOT / "abstractruntime" / "src"
if RUNTIME_SRC_ROOT.exists() and str(RUNTIME_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC_ROOT))
