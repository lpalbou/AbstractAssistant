"""QA 2026-10-28 (i): Settings listed every Qwen3-TTS model twice.

The gateway's speech-model catalog (AbstractGateway 0.17.0 + AbstractVoice 0.19.2) lists each model in
`items` (id = the model) and again in `provider_models` (id = "<provider>/<model>", plus `model`). The
payload below is the scratch gateway's real answer for `?provider=qwen3-tts`, trimmed.
"""

from __future__ import annotations

import pytest

from abstractassistant.gateway_service import AssistantGatewayService

MODELS = [
    "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
]


class _Gateway:
    def audio_speech_models(self, *, provider=None, base_url=None):
        return {
            "models": list(MODELS),
            "models_by_provider": {"qwen3-tts": list(MODELS)},
            "tts_models_by_provider": {"qwen3-tts": list(MODELS)},
            "provider_models": [{"provider": "qwen3-tts", "model": m, "id": f"qwen3-tts/{m}"} for m in MODELS],
            "items": [{"id": m, "label": m, "provider": "qwen3-tts"} for m in MODELS],
            "active_model": MODELS[0],
        }


@pytest.mark.basic
def test_each_voice_model_is_listed_once_by_its_model_id() -> None:
    choices = AssistantGatewayService(_Gateway()).model_choices(route_key="output.voice", provider="qwen3-tts")
    assert [c.id for c in choices] == MODELS
    assert [c.label for c in choices] == MODELS
