"""Qt bubble gateway-selection regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from abstractassistant.core.gateway_selection_store import GatewaySelection, GatewaySelectionStore
from abstractassistant.ui.qt_bubble import QtChatBubble


class _ComboStub:
    def __init__(self, items: list[tuple[str, str]]) -> None:
        self._items = list(items)

    def count(self) -> int:
        return len(self._items)

    def itemData(self, index: int):
        return self._items[index][1]


class _ManagerStub:
    def __init__(self, path: Path) -> None:
        self.active_session_id = "sess_1"
        self._store = GatewaySelectionStore(path)
        self.set_model_calls: list[str] = []

    def gateway_selection_store(self, *, session_id=None) -> GatewaySelectionStore:
        sid = str(session_id or self.active_session_id).strip()
        assert sid == self.active_session_id
        return self._store

    def set_model(self, model: str) -> None:
        self.set_model_calls.append(str(model))


def _stub_bubble(path: Path) -> tuple[QtChatBubble, _ManagerStub]:
    manager = _ManagerStub(path)
    bubble = QtChatBubble.__new__(QtChatBubble)
    bubble.use_gateway = True
    bubble.debug = False
    bubble.current_provider = "lmstudio"
    bubble.current_model = "qwen/qwen3.5-35b-a3b"
    bubble.llm_manager = manager
    bubble.update_token_limits = lambda: None
    bubble._active_session_id = lambda: manager.active_session_id
    return bubble, manager


@pytest.mark.basic
def test_on_model_changed_persists_selected_gateway_model(tmp_path: Path) -> None:
    bubble, manager = _stub_bubble(tmp_path / "gateway.json")
    manager.gateway_selection_store().save(
        GatewaySelection(
            bundle_id="basic-agent",
            flow_id="main",
            provider="lmstudio",
            model="qwen/qwen3.5-35b-a3b",
        )
    )
    bubble.model_combo = _ComboStub(
        [
            ("qwen/qwen3.5-35b-a3b", "qwen/qwen3.5-35b-a3b"),
            ("baidu/ernie-4.5-21b-a", "baidu/ernie-4.5-21b-a"),
        ]
    )

    QtChatBubble.on_model_changed(bubble, 1)

    loaded = manager.gateway_selection_store().load()
    assert loaded is not None
    assert bubble.current_model == "baidu/ernie-4.5-21b-a"
    assert loaded.provider == "lmstudio"
    assert loaded.model == "baidu/ernie-4.5-21b-a"
    assert manager.set_model_calls == ["baidu/ernie-4.5-21b-a"]


@pytest.mark.basic
def test_on_model_changed_ignores_invalid_index_and_keeps_saved_selection(tmp_path: Path) -> None:
    bubble, manager = _stub_bubble(tmp_path / "gateway.json")
    original = GatewaySelection(
        bundle_id="basic-agent",
        flow_id="main",
        provider="lmstudio",
        model="qwen/qwen3.5-35b-a3b",
    )
    manager.gateway_selection_store().save(original)
    bubble.model_combo = _ComboStub([("qwen/qwen3.5-35b-a3b", "qwen/qwen3.5-35b-a3b")])

    QtChatBubble.on_model_changed(bubble, -1)

    assert manager.gateway_selection_store().load() == original
    assert manager.set_model_calls == []
