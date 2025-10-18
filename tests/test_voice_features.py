#!/usr/bin/env python3
"""
Test script for the new voice mode features in AbstractAssistant.

This script tests:
1. Pause/resume functionality in VoiceManager
2. Single/double click detection in TTSToggle
3. Playback controls in Toast window
"""

import sys
import time
import threading
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


class VoiceTestWindow(QWidget):
    """Test window for voice features."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AbstractAssistant Voice Features Test")
        self.setFixedSize(400, 300)

        # Initialize voice manager
        try:
            self.voice_manager = VoiceManager(debug_mode=True)
            print("✅ VoiceManager initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize VoiceManager: {e}")
            self.voice_manager = None

        self.setup_ui()
        self.test_voice_manager()

    def setup_ui(self):
        """Set up the test UI."""
        layout = QVBoxLayout()

        # Title
        title = QLabel("Voice Features Test")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        # VoiceManager test section
        vm_section = QLabel("VoiceManager Tests:")
        vm_section.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(vm_section)

        vm_layout = QHBoxLayout()

        speak_btn = QPushButton("Speak Test Message")
        speak_btn.clicked.connect(self.test_speak)
        vm_layout.addWidget(speak_btn)

        pause_btn = QPushButton("Pause")
        pause_btn.clicked.connect(self.test_pause)
        vm_layout.addWidget(pause_btn)

        resume_btn = QPushButton("Resume")
        resume_btn.clicked.connect(self.test_resume)
        vm_layout.addWidget(resume_btn)

        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(self.test_stop)
        vm_layout.addWidget(stop_btn)

        layout.addLayout(vm_layout)

        # State display
        self.state_label = QLabel("State: idle")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet("background: #f0f0f0; padding: 5px; margin: 5px;")
        layout.addWidget(self.state_label)

        # TTSToggle test section
        toggle_section = QLabel("TTSToggle Tests:")
        toggle_section.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(toggle_section)

        toggle_layout = QHBoxLayout()

        self.tts_toggle = TTSToggle()
        self.tts_toggle.toggled.connect(self.on_tts_toggled)
        self.tts_toggle.single_clicked.connect(self.on_single_click)
        self.tts_toggle.double_clicked.connect(self.on_double_click)
        toggle_layout.addWidget(QLabel("TTS Toggle:"))
        toggle_layout.addWidget(self.tts_toggle)
        toggle_layout.addStretch()

        layout.addLayout(toggle_layout)

        # Instructions
        instructions = QLabel(
            "Instructions:\n"
            "• Click 'Speak Test Message' to start TTS\n"
            "• Use Pause/Resume/Stop buttons to test controls\n"
            "• Single click TTS toggle when speaking to pause/resume\n"
            "• Double click TTS toggle to stop and show toast\n"
            "• Toast notifications will have playback controls"
        )
        instructions.setStyleSheet("background: #ffffcc; padding: 10px; margin: 10px; font-size: 10px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Toast test button
        toast_btn = QPushButton("Show Toast with Playback Controls")
        toast_btn.clicked.connect(self.test_toast)
        layout.addWidget(toast_btn)

        self.setLayout(layout)

        # Update state timer
        self.state_timer = QTimer()
        self.state_timer.timeout.connect(self.update_state)
        self.state_timer.start(100)  # Update every 100ms

    def test_voice_manager(self):
        """Test VoiceManager basic functionality."""
        if not self.voice_manager:
            return

        print("🧪 Testing VoiceManager methods...")

        # Test state when idle
        state = self.voice_manager.get_state()
        print(f"  Initial state: {state}")

        # Test is_speaking when idle
        speaking = self.voice_manager.is_speaking()
        print(f"  Is speaking (idle): {speaking}")

        # Test is_paused when idle
        paused = self.voice_manager.is_paused()
        print(f"  Is paused (idle): {paused}")

    def test_speak(self):
        """Test speech functionality."""
        if not self.voice_manager:
            print("❌ VoiceManager not available")
            return

        test_message = "This is a test message for the new VoiceLLM pause and resume functionality. You can pause me anytime and resume from the exact position."
        success = self.voice_manager.speak(test_message)
        print(f"🔊 Speak test: {'Success' if success else 'Failed'}")

    def test_pause(self):
        """Test pause functionality."""
        if not self.voice_manager:
            return

        success = self.voice_manager.pause()
        print(f"⏸ Pause test: {'Success' if success else 'Failed'}")

    def test_resume(self):
        """Test resume functionality."""
        if not self.voice_manager:
            return

        success = self.voice_manager.resume()
        print(f"▶ Resume test: {'Success' if success else 'Failed'}")

    def test_stop(self):
        """Test stop functionality."""
        if not self.voice_manager:
            return

        self.voice_manager.stop()
        print("⏹ Stop test executed")

    def test_toast(self):
        """Test toast notification with playback controls."""
        test_message = "This is a test toast notification with TTS playback controls. You can pause, resume, and stop using the buttons in the header."

        try:
            toast = show_toast_notification(test_message, debug=True, voice_manager=self.voice_manager)
            print("🍞 Toast with playback controls created")
        except Exception as e:
            print(f"❌ Failed to create toast: {e}")

    def update_state(self):
        """Update the state display."""
        if self.voice_manager:
            try:
                state = self.voice_manager.get_state()
                self.state_label.setText(f"State: {state}")

                # Update TTS toggle state
                self.tts_toggle.set_tts_state(state)

                # Color code the state
                if state == 'speaking':
                    self.state_label.setStyleSheet("background: #90EE90; padding: 5px; margin: 5px;")  # Light green
                elif state == 'paused':
                    self.state_label.setStyleSheet("background: #FFD700; padding: 5px; margin: 5px;")  # Gold
                else:
                    self.state_label.setStyleSheet("background: #f0f0f0; padding: 5px; margin: 5px;")  # Light gray

            except Exception as e:
                self.state_label.setText(f"State: Error - {e}")
                self.state_label.setStyleSheet("background: #FFB6C1; padding: 5px; margin: 5px;")  # Light pink

    def on_tts_toggled(self, enabled):
        """Handle TTS toggle state change."""
        print(f"🔊 TTS toggled: {enabled}")

    def on_single_click(self):
        """Handle single click on TTS toggle."""
        print("🔊 TTSToggle single click detected")
        # Simulate the same logic as in QtChatBubble
        if self.voice_manager:
            current_state = self.voice_manager.get_state()
            if current_state == 'speaking':
                self.voice_manager.pause()
            elif current_state == 'paused':
                self.voice_manager.resume()

    def on_double_click(self):
        """Handle double click on TTS toggle."""
        print("🔊 TTSToggle double click detected - stopping and showing toast")
        if self.voice_manager:
            self.voice_manager.stop()

        # Show a toast notification
        self.test_toast()

    def closeEvent(self, event):
        """Clean up when closing."""
        if self.voice_manager:
            self.voice_manager.cleanup()
        event.accept()


def main():
    """Main function to run the test."""
    print("🧪 Starting AbstractAssistant Voice Features Test...")

    app = QApplication(sys.argv)

    # Set application style
    app.setStyle('Fusion')

    window = VoiceTestWindow()
    window.show()

    print("✅ Test window shown. Test the voice features!")
    print("📝 Expected behavior:")
    print("  - Single click TTS toggle when speaking: pause/resume")
    print("  - Double click TTS toggle: stop TTS and show toast")
    print("  - Toast notifications have pause/play and stop buttons")
    print("  - All controls provide immediate response (~20ms)")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()