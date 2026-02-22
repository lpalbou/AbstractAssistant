"""Gateway selection store unit tests."""

from pathlib import Path

import pytest

from abstractassistant.core.gateway_selection_store import GatewaySelection, GatewaySelectionStore


@pytest.mark.basic
def test_gateway_selection_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "gateway.json"
    store = GatewaySelectionStore(path)
    sel = GatewaySelection(bundle_id="basic-agent", flow_id="main")
    store.save(sel)

    loaded = store.load()
    assert loaded == sel
