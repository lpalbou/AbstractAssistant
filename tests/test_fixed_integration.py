#!/usr/bin/env python3
"""
Test the fixed AbstractAssistant integration with retry logic for pause/resume.
"""

import sys
import time
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QTimer

# Add the abstractassistant module to the path
sys.path.insert(0, '/Users/albou/projects/abstractassistant')

try:
    from abstractassistant.core.tts_manager import VoiceManager
    from abstractassistant.ui.qt_bubble import TTSToggle
    from abstractassistant.ui.toast_window import show_toast_notification
    print("✅ Successfully imported AbstractAssistant modules")
except ImportError as e:
    print(f"❌ Failed to import AbstractAssistant modules: {e}")
    sys.exit(1)


class FixedIntegrationTest(QWidget):
    """Test the fixed integration with retry logic."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fixed AbstractAssistant Integration Test")
        self.setFixedSize(600, 350)

        # Initialize voice manager
        try:
            self.voice_manager = VoiceManager(debug_mode=True)
            print("✅ VoiceManager initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize VoiceManager: {e}")
            self.voice_manager = None

        self.tts_enabled = False
        self.setup_ui()

    def setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()

        # Title
        title = QLabel("Fixed AbstractAssistant Integration Test")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "This test simulates the actual AbstractAssistant workflow with:\n"
            "• TTSToggle with single/double click detection\n"
            "• Retry logic for pause operations\n"
            "• Toast notifications with playback controls\n"
            "• Real AbstractAssistant response simulation"
        )
        desc.setStyleSheet("background: #f0f8ff; padding: 10px; margin: 10px; font-size: 10px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # TTS Toggle section
        tts_layout = QHBoxLayout()
        tts_layout.addWidget(QLabel("TTS Toggle:"))

        self.tts_toggle = TTSToggle()
        self.tts_toggle.toggled.connect(self.on_tts_toggled)
        self.tts_toggle.single_clicked.connect(self.on_tts_single_click)
        self.tts_toggle.double_clicked.connect(self.on_tts_double_click)
        tts_layout.addWidget(self.tts_toggle)

        self.tts_status = QLabel("TTS: Disabled")
        tts_layout.addWidget(self.tts_status)
        tts_layout.addStretch()

        layout.addLayout(tts_layout)

        # Simulate AI Response section
        response_layout = QHBoxLayout()

        self.response_button = QPushButton("🤖 Simulate AI Response")
        self.response_button.clicked.connect(self.simulate_ai_response)
        self.response_button.setStyleSheet("font-size: 12px; padding: 8px;")
        response_layout.addWidget(self.response_button)

        self.toast_button = QPushButton("🍞 Show Toast with Controls")
        self.toast_button.clicked.connect(self.show_toast_with_controls)
        self.toast_button.setStyleSheet("font-size: 12px; padding: 8px;")
        response_layout.addWidget(self.toast_button)

        layout.addLayout(response_layout)

        # Status display
        self.status_label = QLabel("Ready to test fixed integration")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("background: #f0f0f0; padding: 10px; margin: 10px;")
        layout.addWidget(self.status_label)

        # State display
        self.state_label = QLabel("TTS State: idle")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet("background: #f8f8f8; padding: 8px; margin: 5px;")
        layout.addWidget(self.state_label)

        # Instructions
        instructions = QLabel(
            "Test Instructions:\n"
            "1. Click 'TTS Toggle' to enable (turns blue)\n"
            "2. Click 'Simulate AI Response' to start speech (turns green)\n"
            "3. Single click toggle during speech to pause (turns orange)\n"
            "4. Single click again to resume (turns green)\n"
            "5. Double click toggle to stop and show toast\n"
            "6. Use toast controls for additional testing"
        )
        instructions.setStyleSheet("background: #ffffcc; padding: 8px; margin: 8px; font-size: 9px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.setLayout(layout)

        # Timer for real-time updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(100)  # Update every 100ms

    def on_tts_toggled(self, enabled):
        """Handle TTS toggle."""
        self.tts_enabled = enabled
        self.tts_status.setText(f"TTS: {'Enabled' if enabled else 'Disabled'}")
        print(f"🔊 TTS {'enabled' if enabled else 'disabled'}")

        if not enabled and self.voice_manager:
            self.voice_manager.stop()

    def on_tts_single_click(self):
        """Handle single click - use the same logic as QtChatBubble."""
        print("🔊 TTSToggle single click detected")

        if not self.voice_manager or not self.tts_enabled:
            return

        try:
            current_state = self.voice_manager.get_state()

            if current_state == 'speaking':
                # Use the retry logic like in the fixed QtChatBubble
                success = self._attempt_pause_with_retry()
                if success:
                    print("🔊 TTS paused via single click")
                    self.status_label.setText("⏸ Speech paused via single click")
                else:
                    print("🔊 TTS pause failed - audio stream may not be ready yet")
                    self.status_label.setText("❌ Pause failed - audio stream not ready")
            elif current_state == 'paused':
                success = self.voice_manager.resume()
                if success:
                    print("🔊 TTS resumed via single click")
                    self.status_label.setText("▶ Speech resumed via single click")
                else:
                    print("🔊 TTS resume failed")
                    self.status_label.setText("❌ Resume failed")
            else:
                print("🔊 TTS single click - no active speech to pause/resume")
                self.status_label.setText("No active speech to pause/resume")

            # Update visual state
            self._update_tts_toggle_state()

        except Exception as e:
            print(f"❌ Error handling TTS single click: {e}")

    def _attempt_pause_with_retry(self, max_attempts=5):
        """Same retry logic as in the fixed QtChatBubble."""
        import time

        for attempt in range(max_attempts):
            if not self.voice_manager.is_speaking():
                return False

            success = self.voice_manager.pause()
            if success:
                return True

            print(f"🔊 Pause attempt {attempt + 1}/{max_attempts} failed, retrying...")
            time.sleep(0.1)

        return False

    def on_tts_double_click(self):
        """Handle double click - stop and show toast."""
        print("🔊 TTSToggle double click detected - stopping and showing toast")

        if self.voice_manager:
            self.voice_manager.stop()

        self.status_label.setText("⏹ Speech stopped via double click")
        self.show_toast_with_controls()

    def simulate_ai_response(self):
        """Simulate AI response like in AbstractAssistant."""
        if not self.voice_manager or not self.tts_enabled:
            self.status_label.setText("❌ TTS not enabled")
            return

        # Simulate a typical AI response
        response = "This is a simulated AI response that demonstrates the new pause and resume functionality in AbstractAssistant. The speech will continue for several seconds, giving you time to test the pause and resume controls using the TTS toggle. You can single click to pause and resume, or double click to stop and show the toast notification."

        self.status_label.setText("🤖 AI response started")

        # Start speech like in QtChatBubble
        try:
            success = self.voice_manager.speak(response)
            if success:
                self._update_tts_toggle_state()
                print("🔊 AI response speech started")
            else:
                self.status_label.setText("❌ Failed to start speech")
        except Exception as e:
            print(f"❌ Error starting speech: {e}")
            self.status_label.setText(f"❌ Speech error: {e}")

    def show_toast_with_controls(self):
        """Show toast with playback controls."""
        test_message = "This is a toast notification with playback controls. You can use the pause/play and stop buttons in the header to control TTS playback."

        try:
            toast = show_toast_notification(test_message, debug=True, voice_manager=self.voice_manager)
            print("🍞 Toast with playback controls shown")
            self.status_label.setText("🍞 Toast with controls displayed")
        except Exception as e:
            print(f"❌ Failed to show toast: {e}")
            self.status_label.setText(f"❌ Toast error: {e}")

    def _update_tts_toggle_state(self):
        """Update TTS toggle visual state."""
        if self.voice_manager:
            try:
                current_state = self.voice_manager.get_state()
                self.tts_toggle.set_tts_state(current_state)
            except Exception as e:
                print(f"❌ Error updating TTS toggle state: {e}")

    def update_display(self):
        """Update the display with current state."""
        if self.voice_manager:
            try:
                state = self.voice_manager.get_state()
                self.state_label.setText(f"TTS State: {state}")

                # Color code the state
                if state == 'speaking':
                    self.state_label.setStyleSheet("background: #90EE90; padding: 8px; margin: 5px;")
                elif state == 'paused':
                    self.state_label.setStyleSheet("background: #FFD700; padding: 8px; margin: 5px;")
                else:
                    self.state_label.setStyleSheet("background: #f8f8f8; padding: 8px; margin: 5px;")

                # Update toggle state
                self._update_tts_toggle_state()

            except Exception as e:
                self.state_label.setText(f"State: Error - {e}")

    def closeEvent(self, event):
        """Clean up when closing."""
        if self.voice_manager:
            self.voice_manager.cleanup()
        event.accept()


def main():
    """Main function."""
    print("🧪 Starting Fixed AbstractAssistant Integration Test...")

    app = QApplication(sys.argv)
    window = FixedIntegrationTest()
    window.show()

    print("✅ Fixed integration test window shown.")
    print("📝 This version uses retry logic for pause operations.")
    print("📝 Test the TTS toggle and toast controls - they should work reliably now!")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()