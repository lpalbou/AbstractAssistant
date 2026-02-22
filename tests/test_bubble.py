"""Smoke tests for the Qt bubble integration."""

from abstractassistant.app import AbstractAssistantApp
from abstractassistant.ui.qt_bubble import QtBubbleManager


def test_configuration(config):
    assert config.gateway.use_gateway is True


def test_llm_manager(llm_manager):
    assert llm_manager.use_gateway is True


def test_qt_bubble_importable():
    assert QtBubbleManager is not None


def test_app_initialization(config, tmp_path):
    app = AbstractAssistantApp(config=config, debug=False, data_dir=tmp_path)
    assert app is not None
