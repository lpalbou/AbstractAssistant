"""
Pytest configuration to ensure local package imports.
"""

from pathlib import Path
import sys
import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Prefer sibling packages in the monorepo when running tests from the repo root.
REPO_ROOT = ROOT.parent
VOICE_PKG_ROOT = REPO_ROOT / "abstractvoice"
if VOICE_PKG_ROOT.exists() and str(VOICE_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(VOICE_PKG_ROOT))

from abstractassistant.config import Config
from abstractassistant.core.llm_manager import LLMManager


@pytest.fixture
def config():
    cfg = Config.default()
    cfg.gateway.url = "http://localhost:8000"
    cfg.gateway.use_gateway = True
    return cfg


@pytest.fixture
def llm_manager(config, tmp_path):
    return LLMManager(config=config, data_dir=tmp_path)
