"""Simple smoke tests to validate imports and gateway mode."""

from abstractassistant.config import Config
from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.ui.qt_bubble import QtBubbleManager


def test_basic_imports():
    assert Config is not None
    assert LLMManager is not None
    assert QtBubbleManager is not None


def test_llm_manager_gateway(config, tmp_path):
    manager = LLMManager(config=config, data_dir=tmp_path)
    assert manager.use_gateway is True
