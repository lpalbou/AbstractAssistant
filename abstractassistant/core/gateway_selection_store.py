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
    tts_voice: str = ""
    tts_voice_mode: str = ""
    tts_model: str = ""
    stt_model: str = ""
    image_provider: str = ""
    image_model: str = ""

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "flow_id": self.flow_id,
            "provider": self.provider,
            "model": self.model,
            "tts_voice": self.tts_voice,
            "tts_voice_mode": self.tts_voice_mode,
            "tts_model": self.tts_model,
            "stt_model": self.stt_model,
            "image_provider": self.image_provider,
            "image_model": self.image_model,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Optional["GatewaySelection"]:
        if not isinstance(raw, dict):
            return None
        bundle_id = str(raw.get("bundle_id") or "").strip()
        flow_id = str(raw.get("flow_id") or "").strip()
        provider = str(raw.get("provider") or "").strip()
        model = str(raw.get("model") or "").strip()
        tts_voice = str(raw.get("tts_voice") or "").strip()
        tts_voice_mode = str(raw.get("tts_voice_mode") or "").strip()
        tts_model = str(raw.get("tts_model") or "").strip()
        stt_model = str(raw.get("stt_model") or "").strip()
        image_provider = str(raw.get("image_provider") or "").strip()
        image_model = str(raw.get("image_model") or "").strip()
        if not bundle_id and not flow_id and not provider and not model and not tts_voice and not tts_voice_mode and not tts_model and not stt_model and not image_provider and not image_model:
            return None
        return cls(
            bundle_id=bundle_id,
            flow_id=flow_id,
            provider=provider,
            model=model,
            tts_voice=tts_voice,
            tts_voice_mode=tts_voice_mode,
            tts_model=tts_model,
            stt_model=stt_model,
            image_provider=image_provider,
            image_model=image_model,
        )


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
