"""
Gateway selection store for AbstractAssistant.

Persists per-session bundle/flow selection for gateway runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class GatewaySelection:
    bundle_id: str = ""
    flow_id: str = ""
    provider: str = ""
    model: str = ""

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "flow_id": self.flow_id,
            "provider": self.provider,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Optional["GatewaySelection"]:
        if not isinstance(raw, dict):
            return None
        bundle_id = str(raw.get("bundle_id") or "").strip()
        flow_id = str(raw.get("flow_id") or "").strip()
        provider = str(raw.get("provider") or "").strip()
        model = str(raw.get("model") or "").strip()
        if not bundle_id and not flow_id and not provider and not model:
            return None
        return cls(bundle_id=bundle_id, flow_id=flow_id, provider=provider, model=model)


class GatewaySelectionStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Optional[GatewaySelection]:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return GatewaySelection.from_dict(data)

    def save(self, selection: GatewaySelection) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(selection.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self._path)
