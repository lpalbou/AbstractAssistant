"""
Voice tool announcement formatting tests.
"""

from abstractassistant.ui.qt_bubble import QtChatBubble


class _VoiceCapture:
    def __init__(self) -> None:
        self.messages = []

    def speak(self, text: str) -> bool:
        self.messages.append(str(text or ""))
        return True


def _stub_bubble() -> QtChatBubble:
    bubble = QtChatBubble.__new__(QtChatBubble)
    bubble.tts_enabled = True
    bubble.voice_manager = _VoiceCapture()
    return bubble


def test_tool_announcement_uses_unique_tool_set() -> None:
    bubble = _stub_bubble()
    bubble._announce_tool_execution(
        [
            {"name": "fetch_url", "arguments": {"url": "https://a.example"}},
            {"name": "fetch_url", "arguments": {"url": "https://b.example"}},
            {"name": "read_file", "arguments": {"path": "/tmp/a.txt"}},
            {"name": "read_file", "arguments": {"path": "/tmp/b.txt"}},
        ]
    )
    assert bubble.voice_manager.messages == [
        "Executing 2 tools: fetch_url, read_file. Please wait."
    ]


def test_tool_announcement_single_tool_repeated_calls() -> None:
    bubble = _stub_bubble()
    bubble._announce_tool_execution(
        [
            {"name": "fetch_url", "arguments": {"url": "https://a.example"}},
            {"name": "fetch_url", "arguments": {"url": "https://b.example"}},
            {"name": "fetch_url", "arguments": {"url": "https://c.example"}},
        ]
    )
    assert bubble.voice_manager.messages == [
        "Executing 3 calls of fetch_url. Please wait."
    ]
