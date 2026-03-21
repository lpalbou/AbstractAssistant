"""Qt bubble token-limit regression tests."""

from __future__ import annotations

import warnings

import pytest

from abstractassistant.ui.qt_bubble import QtChatBubble


class _GatewayStub:
    def __init__(self) -> None:
        self.calls = 0

    def discovery_model_capabilities(self, *, model_name: str):
        self.calls += 1
        raise AssertionError(f"unexpected model capability lookup for {model_name!r}")


class _ManagerStub:
    def __init__(self, gateway: _GatewayStub) -> None:
        self._gateway = gateway
        self.llm = None

    def gateway_client(self) -> _GatewayStub:
        return self._gateway


class _TokenLabelStub:
    def __init__(self) -> None:
        self.text = ""
        self.tooltip = ""

    def setToolTip(self, text: str) -> None:
        self.tooltip = str(text)

    def setText(self, text: str) -> None:
        self.text = str(text)


def _stub_bubble() -> tuple[QtChatBubble, _GatewayStub]:
    gateway = _GatewayStub()
    bubble = QtChatBubble.__new__(QtChatBubble)
    bubble.use_gateway = True
    bubble.current_model = ""
    bubble.llm_manager = _ManagerStub(gateway)
    bubble._gateway_cache = {}
    bubble._gateway_cache_ttl_s = 60.0
    bubble.token_label = _TokenLabelStub()
    bubble.debug = False
    bubble.max_tokens = 0
    bubble.token_count = 0
    bubble.update_token_display = lambda: None
    return bubble, gateway


@pytest.mark.basic
def test_update_token_limits_skips_gateway_lookup_when_model_not_selected() -> None:
    bubble, gateway = _stub_bubble()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bubble.update_token_limits()

    assert gateway.calls == 0
    assert bubble.max_tokens == 128000
    assert "selection_pending" in bubble.token_label.tooltip
    assert not any("model_name is required" in str(w.message) for w in caught)
