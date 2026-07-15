"""Voice dependency tests.

The assistant is gateway-native: STT/TTS execute on the gateway, but local
mic capture (VoiceRecognizer) and in-process streaming playback
(NonBlockingAudioPlayer) come from abstractvoice, which is a base dependency.
"""

import pytest


@pytest.mark.basic
def test_abstractvoice_is_available() -> None:
    try:
        import abstractvoice  # noqa: F401
    except Exception as e:
        raise AssertionError(
            "AbstractVoice must be installed by default. "
            "Run `python -m pip install -e ./abstractvoice` in the monorepo."
        ) from e

    from abstractvoice.tts import NonBlockingAudioPlayer  # noqa: F401
