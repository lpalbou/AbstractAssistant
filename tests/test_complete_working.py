#!/usr/bin/env python3
"""
Complete working test with all features - buttons AND TTS toggle.
This combines the working button controls from test_fixed_app.py with the integration features.
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


class CompleteWorkingTest(QWidget):
    """Complete test with all working features - buttons AND toggle."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Complete Working Voice Features Test")
        self.setFixedSize(700, 500)

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
        """Set up the complete UI with buttons AND toggle."""
        layout = QVBoxLayout()

        # Title
        title = QLabel("Complete Working Voice Features Test")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "This test includes ALL working features:\n"
            "• Direct control buttons (Speak, Pause, Resume, Stop)\n"
            "• TTS Toggle with single/double click detection\n"
            "• Toast notifications with playback controls\n"
            "• Retry logic for reliable pause/resume operations"
        )
        desc.setStyleSheet("background: #f0f8ff; padding: 10px; margin: 10px; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # === DIRECT CONTROL BUTTONS (WORKING) ===
        button_section = QLabel("Direct Control Buttons:")
        button_section.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(button_section)

        button_layout = QHBoxLayout()

        self.speak_button = QPushButton("🔊 Start Speech")
        self.speak_button.clicked.connect(self.start_speech)
        self.speak_button.setStyleSheet("font-size: 12px; padding: 6px;")
        button_layout.addWidget(self.speak_button)

        self.pause_button = QPushButton("⏸ Pause")
        self.pause_button.clicked.connect(self.pause_speech)
        self.pause_button.setEnabled(False)
        self.pause_button.setStyleSheet("font-size: 12px; padding: 6px;")
        button_layout.addWidget(self.pause_button)

        self.resume_button = QPushButton("▶ Resume")
        self.resume_button.clicked.connect(self.resume_speech)
        self.resume_button.setEnabled(False)
        self.resume_button.setStyleSheet("font-size: 12px; padding: 6px;")
        button_layout.addWidget(self.resume_button)

        self.stop_button = QPushButton("⏹ Stop")
        self.stop_button.clicked.connect(self.stop_speech)
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("font-size: 12px; padding: 6px;")
        button_layout.addWidget(self.stop_button)

        layout.addLayout(button_layout)

        # === TTS TOGGLE SECTION ===
        toggle_section = QLabel("TTS Toggle (Single/Double Click):")
        toggle_section.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(toggle_section)

        toggle_layout = QHBoxLayout()
        toggle_layout.addWidget(QLabel("TTS Toggle:"))

        self.tts_toggle = TTSToggle()
        self.tts_toggle.toggled.connect(self.on_tts_toggled)
        self.tts_toggle.single_clicked.connect(self.on_tts_single_click)
        self.tts_toggle.double_clicked.connect(self.on_tts_double_click)
        toggle_layout.addWidget(self.tts_toggle)

        self.tts_status = QLabel("TTS: Disabled")
        toggle_layout.addWidget(self.tts_status)
        toggle_layout.addStretch()

        layout.addLayout(toggle_layout)

        # === TOAST SECTION ===
        toast_section = QLabel("Toast Notifications:")
        toast_section.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(toast_section)

        toast_layout = QHBoxLayout()

        self.toast_button = QPushButton("🍞 Show Toast with Controls")
        self.toast_button.clicked.connect(self.show_toast_with_controls)
        self.toast_button.setStyleSheet("font-size: 12px; padding: 6px;")
        toast_layout.addWidget(self.toast_button)

        self.ai_response_button = QPushButton("🤖 Simulate AI Response")
        self.ai_response_button.clicked.connect(self.simulate_ai_response)
        self.ai_response_button.setStyleSheet("font-size: 12px; padding: 6px;")
        toast_layout.addWidget(self.ai_response_button)

        layout.addLayout(toast_layout)

        # === STATUS DISPLAYS ===
        self.status_label = QLabel("Ready - All features available")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("background: #f0f0f0; padding: 8px; margin: 8px; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.state_label = QLabel("TTS State: idle")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet("background: #f8f8f8; padding: 6px; margin: 5px; font-size: 11px;")
        layout.addWidget(self.state_label)

        self.timing_label = QLabel("Ready to start speech")
        self.timing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timing_label.setStyleSheet("background: #fff8dc; padding: 6px; margin: 5px; font-size: 10px;")
        layout.addWidget(self.timing_label)

        # Instructions
        instructions = QLabel(
            "Test ALL features:\n"
            "• BUTTONS: Use Speak/Pause/Resume/Stop buttons for direct control\n"
            "• TOGGLE: Enable TTS toggle, then single click (pause/resume) or double click (stop+toast)\n"
            "• TOAST: Show toast notifications with built-in playback controls\n"
            "• AI RESPONSE: Simulate full AbstractAssistant workflow"
        )
        instructions.setStyleSheet("background: #ffffcc; padding: 8px; margin: 8px; font-size: 9px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.setLayout(layout)

        # Timer for real-time updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(100)

    # === DIRECT BUTTON METHODS (THESE WORK PERFECTLY) ===

    def start_speech(self):
        """Start speech with proper timing monitoring."""
        if not self.voice_manager:
            self.status_label.setText("❌ VoiceManager not available")
            return

        long_text = "This is a comprehensive test message that demonstrates all the working voice features. The speech will continue for several seconds, giving us time to test buttons, toggle controls, and toast notifications. You can pause me at any time using the direct buttons, the TTS toggle, or the toast controls."

        success = self.voice_manager.speak(long_text)
        if not success:
            self.status_label.setText("❌ Failed to start speech")
            return

        self.status_label.setText("🔊 Speech started - waiting for audio stream...")
        self.speak_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        # Monitor for when pause becomes available
        self.monitor_speech_start()

    def monitor_speech_start(self):
        """Monitor when speech actually starts and enable pause."""
        def check_speech_state():
            attempts = 0
            max_attempts = 30  # 3 seconds max wait

            while attempts < max_attempts:
                if not self.voice_manager.is_speaking():
                    return

                state = self.voice_manager.get_state()
                if state == 'speaking':
                    attempts += 1
                    time.sleep(0.1)

                    # After 2 seconds, enable pause controls
                    if attempts >= 20:  # 2 seconds
                        QTimer.singleShot(0, self.enable_pause_controls)
                        return

                time.sleep(0.1)
                attempts += 1

        monitor_thread = threading.Thread(target=check_speech_state, daemon=True)
        monitor_thread.start()

    def enable_pause_controls(self):
        """Enable pause controls when ready."""
        if self.voice_manager and self.voice_manager.is_speaking():
            self.pause_button.setEnabled(True)
            self.status_label.setText("✅ Audio stream ready - all controls available")
            self.timing_label.setText("All pause/resume controls are now active")

    def pause_speech(self):
        """Pause speech with retry logic."""
        if not self.voice_manager:
            return

        success = self._attempt_pause_with_retry()
        if success:
            self.status_label.setText("⏸ Speech paused successfully")
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(True)
        else:
            self.status_label.setText("❌ Failed to pause speech")

    def resume_speech(self):
        """Resume speech."""
        if not self.voice_manager:
            return

        success = self.voice_manager.resume()
        if success:
            self.status_label.setText("▶ Speech resumed successfully")
            self.pause_button.setEnabled(True)
            self.resume_button.setEnabled(False)
        else:
            self.status_label.setText("❌ Failed to resume speech")

    def stop_speech(self):
        """Stop speech."""
        if not self.voice_manager:
            return

        self.voice_manager.stop()
        self.status_label.setText("⏹ Speech stopped")
        self.reset_buttons()

    def reset_buttons(self):
        """Reset button states."""
        self.speak_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.timing_label.setText("Ready to start speech")

    def _attempt_pause_with_retry(self, max_attempts=5):
        """Retry logic for pause operations."""
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

    # === TTS TOGGLE METHODS ===

    def on_tts_toggled(self, enabled):
        """Handle TTS toggle."""
        self.tts_enabled = enabled
        self.tts_status.setText(f"TTS: {'Enabled' if enabled else 'Disabled'}")
        print(f"🔊 TTS {'enabled' if enabled else 'disabled'}")

        if not enabled and self.voice_manager:
            self.voice_manager.stop()

    def on_tts_single_click(self):
        """Handle single click."""
        print("🔊 TTSToggle single click detected")

        if not self.voice_manager or not self.tts_enabled:
            return

        current_state = self.voice_manager.get_state()

        if current_state == 'speaking':
            success = self._attempt_pause_with_retry()
            if success:
                print("🔊 TTS paused via toggle single click")
                self.status_label.setText("⏸ Speech paused via toggle single click")
            else:
                self.status_label.setText("❌ Toggle pause failed")
        elif current_state == 'paused':
            success = self.voice_manager.resume()
            if success:
                print("🔊 TTS resumed via toggle single click")
                self.status_label.setText("▶ Speech resumed via toggle single click")
            else:
                self.status_label.setText("❌ Toggle resume failed")

        self._update_tts_toggle_state()

    def on_tts_double_click(self):
        """Handle double click."""
        print("🔊 TTSToggle double click detected")

        if self.voice_manager:
            self.voice_manager.stop()
            self.reset_buttons()

        self.status_label.setText("⏹ Speech stopped via toggle double click")
        self.show_toast_with_controls()

    # === TOAST METHODS ===

    def show_toast_with_controls(self):
        """Show toast with playback controls."""
        test_message = "This is a toast notification with working playback controls. Use the pause/play and stop buttons in the header to control TTS playback. The retry logic ensures reliable operation."

        try:
            toast = show_toast_notification(test_message, debug=True, voice_manager=self.voice_manager)
            print("🍞 Toast with playback controls shown")
            self.status_label.setText("🍞 Toast with controls displayed")
        except Exception as e:
            print(f"❌ Failed to show toast: {e}")
            self.status_label.setText(f"❌ Toast error: {e}")

    def simulate_ai_response(self):
        """Simulate AI response."""
        if not self.tts_enabled:
            self.status_label.setText("❌ Enable TTS toggle first")
            return

        response = "This simulates a complete AbstractAssistant AI response with voice mode enabled. All pause, resume, and stop controls should work perfectly with the retry logic implemented."

        try:
            self.voice_manager.speak(response)
            self.status_label.setText("🤖 AI response started")
            self._update_tts_toggle_state()
        except Exception as e:
            self.status_label.setText(f"❌ AI response error: {e}")

    # === UTILITY METHODS ===

    def _update_tts_toggle_state(self):
        """Update TTS toggle visual state."""
        if self.voice_manager:
            try:
                current_state = self.voice_manager.get_state()
                self.tts_toggle.set_tts_state(current_state)
            except Exception as e:
                print(f"❌ Error updating toggle state: {e}")

    def update_display(self):
        """Update real-time display."""
        if self.voice_manager:
            try:
                state = self.voice_manager.get_state()
                self.state_label.setText(f"TTS State: {state}")

                # Color code
                if state == 'speaking':
                    self.state_label.setStyleSheet("background: #90EE90; padding: 6px; margin: 5px; font-size: 11px;")
                elif state == 'paused':
                    self.state_label.setStyleSheet("background: #FFD700; padding: 6px; margin: 5px; font-size: 11px;")
                elif state == 'idle':
                    self.state_label.setStyleSheet("background: #f8f8f8; padding: 6px; margin: 5px; font-size: 11px;")
                    if not self.speak_button.isEnabled():
                        self.reset_buttons()

                self._update_tts_toggle_state()

            except Exception as e:
                self.state_label.setText(f"State: Error - {e}")

    def closeEvent(self, event):
        """Cleanup."""
        if self.voice_manager:
            self.voice_manager.cleanup()
        event.accept()


def main():
    """Main function."""
    print("🧪 Starting Complete Working Voice Features Test...")

    app = QApplication(sys.argv)
    window = CompleteWorkingTest()
    window.show()

    print("✅ Complete test window shown with ALL working features:")
    print("  🔘 Direct control buttons (Speak/Pause/Resume/Stop)")
    print("  🔘 TTS toggle with single/double click detection")
    print("  🔘 Toast notifications with playback controls")
    print("  🔘 Retry logic for reliable pause/resume operations")
    print("📝 Everything should work perfectly now!")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()