"""Minimal smoke tests for AbstractAssistant components."""

from abstractassistant.config import Config
from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.utils.icon_generator import IconGenerator


def test_llm_manager_gateway_session(tmp_path):
    """Gateway mode should store messages locally without provider calls."""
    cfg = Config.default()
    cfg.gateway.url = "http://localhost:8000"
    cfg.gateway.use_gateway = True

    manager = LLMManager(config=cfg, data_dir=tmp_path)
    assert manager.use_gateway is True

    manager.append_message(role="user", content="hello")
    messages = manager.session_messages()
    assert messages[-1]["content"] == "hello"

    manager.set_last_run_id("run_123")
    snap = manager._gateway_snapshot
    assert snap is not None
    assert snap.last_run_id == "run_123"


def test_icon_generator_smoke():
    """Icon generator should produce PIL images."""
    generator = IconGenerator()
    app_icon = generator.create_app_icon()
    status_icon = generator.create_status_icon("ready")

    assert getattr(app_icon, "size", None) is not None
    assert getattr(status_icon, "size", None) is not None
