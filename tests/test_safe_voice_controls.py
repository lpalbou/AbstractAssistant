#!/usr/bin/env python3
"""
Test the safe voice control approach without system tray security risks.
This approach uses:
1. Prominent voice control panel in chat bubble when TTS is active
2. Keyboard shortcuts (Space for pause/resume, Escape for stop)
3. Enhanced TTSToggle with single/double click
4. Toast controls with retry logic
"""

if __name__ != "__main__":  # pragma: no cover
    import pytest

    pytest.skip(
        "Interactive GUI manual test; excluded from automated pytest runs.",
        allow_module_level=True,
    )

import sys
import time
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QTimer

# Add the abstractassistant module to the path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from abstractassistant.core.tts_manager import VoiceManager
    from abstractassistant.core.llm_manager import LLMManager
    from abstractassistant.ui.qt_bubble import QtChatBubble
    from abstractassistant.config import Config
    print("✅ Successfully imported AbstractAssistant modules")
except ImportError as e:
    print(f"❌ Failed to import AbstractAssistant modules: {e}")
    sys.exit(1)


class SafeVoiceControlTest(QWidget):
    """Test the safe voice control approach."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Safe Voice Control Test - No Security Risks")
        self.setFixedSize(800, 600)

        # Initialize components
        self.setup_components()
        self.setup_ui()

    def setup_components(self):
        """Initialize AbstractAssistant components."""
        try:
            # Create config
            config = Config()

            # Create LLM manager
            self.llm_manager = LLMManager(config=config, debug=True)

            # Create chat bubble with voice control
            self.chat_bubble = QtChatBubble(self.llm_manager, config=config, debug=True)

            print("✅ AbstractAssistant components initialized")

        except Exception as e:
            print(f"❌ Failed to initialize components: {e}")
            self.llm_manager = None
            self.chat_bubble = None

    def setup_ui(self):
        """Set up the test UI."""
        layout = QVBoxLayout()

        # Title
        title = QLabel("Safe Voice Control Test - No Security Risks")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "This test demonstrates safe voice control without system tray security issues:\n"
            "• Prominent voice control panel appears in chat bubble when TTS is active\n"
            "• Keyboard shortcuts: Space (pause/resume), Escape (stop)\n"
            "• TTSToggle with single/double click detection\n"
            "• Toast notifications with playback controls\n"
            "• All functionality uses existing safe UI components"
        )
        desc.setStyleSheet("background: #e6f3ff; padding: 10px; margin: 10px; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Test controls
        controls_section = QLabel("Test Controls:")
        controls_section.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(controls_section)

        controls_layout = QHBoxLayout()

        self.show_bubble_button = QPushButton("💬 Show Chat Bubble")
        self.show_bubble_button.clicked.connect(self.show_chat_bubble)
        self.show_bubble_button.setStyleSheet("font-size: 12px; padding: 8px;")
        controls_layout.addWidget(self.show_bubble_button)

        self.test_message_button = QPushButton("🔊 Send Test Message")
        self.test_message_button.clicked.connect(self.send_test_message)
        self.test_message_button.setStyleSheet("font-size: 12px; padding: 8px;")
        controls_layout.addWidget(self.test_message_button)

        self.hide_bubble_button = QPushButton("❌ Hide Bubble")
        self.hide_bubble_button.clicked.connect(self.hide_chat_bubble)
        self.hide_bubble_button.setStyleSheet("font-size: 12px; padding: 8px;")
        controls_layout.addWidget(self.hide_bubble_button)

        layout.addLayout(controls_layout)

        # Status display
        self.status_label = QLabel("Ready - Click 'Show Chat Bubble' to begin")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("background: #f0f0f0; padding: 10px; margin: 10px; font-size: 12px;")
        layout.addWidget(self.status_label)

        # Features list
        features = QLabel(
            "✅ Safe Voice Control Features:\n"
            "\n"
            "🎯 IN CHAT BUBBLE:\n"
            "• Voice control panel appears when TTS is active\n"
            "• Pause/Resume button (⏸/▶) with tooltip\n"
            "• Stop button (⏹) with tooltip\n"
            "• TTS status indicator\n"
            "• TTSToggle with color states and click detection\n"
            "\n"
            "⌨️ KEYBOARD SHORTCUTS:\n"
            "• Space bar: Pause/Resume TTS (when TTS active, input unfocused)\n"
            "• Escape key: Stop TTS (when TTS active)\n"
            "\n"
            "🍞 TOAST NOTIFICATIONS:\n"
            "• Playback control buttons in header\n"
            "• Retry logic for reliable operation\n"
            "\n"
            "🔒 SECURITY:\n"
            "• No system tray modifications\n"
            "• No system-level permissions required\n"
            "• All controls use existing safe Qt widgets"
        )
        features.setStyleSheet("background: #f0fff0; padding: 10px; margin: 10px; font-size: 10px;")
        features.setWordWrap(True)
        layout.addWidget(features)

        # Instructions
        instructions = QLabel(
            "Test Instructions:\n"
            "1. Click 'Show Chat Bubble' to open the voice-enhanced chat interface\n"
            "2. Enable TTS toggle in the chat bubble (turns blue)\n"
            "3. Click 'Send Test Message' to start TTS with a long message\n"
            "4. Watch the voice control panel appear in the chat bubble header\n"
            "5. Test the controls:\n"
            "   • Click pause button or press Space to pause\n"
            "   • Click resume button or press Space to resume\n"
            "   • Click stop button or press Escape to stop\n"
            "   • Try single/double clicking the TTS toggle\n"
            "6. All controls should work immediately and safely!"
        )
        instructions.setStyleSheet("background: #ffffcc; padding: 10px; margin: 10px; font-size: 10px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.setLayout(layout)

    def show_chat_bubble(self):
        """Show the enhanced chat bubble."""
        if self.chat_bubble:
            self.chat_bubble.show()
            self.chat_bubble.raise_()
            self.chat_bubble.activateWindow()
            self.status_label.setText("💬 Chat bubble shown - Enable TTS and send a message")
            print("💬 Chat bubble with enhanced voice controls shown")
        else:
            self.status_label.setText("❌ Chat bubble not available")

    def hide_chat_bubble(self):
        """Hide the chat bubble."""
        if self.chat_bubble:
            self.chat_bubble.hide()
            self.status_label.setText("❌ Chat bubble hidden")
            print("❌ Chat bubble hidden")

    def send_test_message(self):
        """Send a test message to trigger TTS."""
        if self.chat_bubble:
            # Simulate sending a message
            test_message = "This is a comprehensive test of the safe voice control system. The enhanced chat bubble now includes a prominent voice control panel that appears when TTS is active. You can use the pause and resume buttons, try the keyboard shortcuts with Space and Escape keys, and test the single and double click functionality on the TTS toggle. All of these controls work safely without requiring any system-level permissions."

            # Set the input text and trigger send
            self.chat_bubble.input_text.setText(test_message)
            self.chat_bubble.send_message()

            self.status_label.setText("🔊 Test message sent - Voice controls should appear")
            print("🔊 Test message sent with enhanced voice controls")
        else:
            self.status_label.setText("❌ Chat bubble not available")

    def closeEvent(self, event):
        """Cleanup when closing."""
        if self.chat_bubble:
            self.chat_bubble.close()
        event.accept()


def main():
    """Main function."""
    print("🧪 Starting Safe Voice Control Test...")

    app = QApplication(sys.argv)
    window = SafeVoiceControlTest()
    window.show()

    print("✅ Safe voice control test window shown")
    print("🔒 This approach is completely safe - no system tray modifications")
    print("📝 Features:")
    print("  • Prominent voice control panel in chat bubble")
    print("  • Keyboard shortcuts (Space/Escape)")
    print("  • Enhanced TTSToggle with click detection")
    print("  • Toast controls with retry logic")
    print("  • All controls use existing safe Qt components")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
