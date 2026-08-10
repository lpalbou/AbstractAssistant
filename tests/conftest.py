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
# The sibling runtime tracks the sibling core (it imports symbols the released
# wheel does not carry yet). Preferring one sibling but not the other pairs a
# new runtime with an old installed core and every GUI/voice test module fails
# to import, so take abstractcore from the monorepo too when it is checked out.
CORE_PKG_ROOT = REPO_ROOT / "abstractcore"
if (CORE_PKG_ROOT / "abstractcore").is_dir() and str(CORE_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_PKG_ROOT))
