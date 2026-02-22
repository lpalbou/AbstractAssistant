"""Voice dependency tests."""

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

    from abstractassistant.core.tts_manager import VoiceManager

    assert VoiceManager.is_available()
