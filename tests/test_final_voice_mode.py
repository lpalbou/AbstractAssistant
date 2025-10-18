#!/usr/bin/env python3
"""
Final test of the complete voice mode implementation with system tray integration.
This simulates the exact workflow a user would experience.
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
    from abstractassistant.app import ClickableIcon
    from abstractassistant.utils.icon_generator import IconGenerator
    print("✅ Successfully imported AbstractAssistant modules")
except ImportError as e:
    print(f"❌ Failed to import AbstractAssistant modules: {e}")
    sys.exit(1)


class FinalVoiceModeTest(QWidget):
    """Final test simulating the complete user experience."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Final Voice Mode Test - System Tray Integration")
        self.setFixedSize(700, 600)

        # Initialize voice manager
        try:
            self.voice_manager = VoiceManager(debug_mode=True)
            print("✅ VoiceManager initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize VoiceManager: {e}")
            self.voice_manager = None

        # Create system tray icon
        self.tray_icon = None
        self.create_tray_icon()

        self.setup_ui()

    def create_tray_icon(self):
        """Create a test system tray icon with click detection."""
        try:
            # Create icon generator and generate an icon
            icon_gen = IconGenerator(size=32)
            icon_image = icon_gen.create_app_icon(color_scheme="green", animated=False)

            # Create clickable icon with our click handler
            self.tray_icon = ClickableIcon(
                "VoiceModeTest",
                icon_image,
                "Voice Mode Test - Single click: pause/resume, Double click: stop+show",
                click_handler=self.handle_tray_click
            )

            print("✅ System tray icon created with click detection")

        except Exception as e:
            print(f"❌ Failed to create tray icon: {e}")

    def handle_tray_click(self, single_click=False, double_click=False):
        """Handle system tray icon clicks - exactly like AbstractAssistant."""
        try:
            click_type = "single" if single_click else "double" if double_click else "normal"
            print(f"🔄 Tray icon clicked - {click_type} click")

            # Handle single click - pause/resume TTS
            if single_click and self.voice_manager:
                current_state = self.voice_manager.get_state()

                if current_state == 'speaking':
                    # Pause the speech using retry logic
                    success = self._attempt_pause_with_retry()
                    if success:
                        print("🔊 TTS paused via system tray single click")
                        self.status_label.setText("⏸ TTS paused via system tray single click")
                    else:
                        print("🔊 TTS pause failed via system tray single click")
                        self.status_label.setText("❌ TTS pause failed")
                elif current_state == 'paused':
                    # Resume the speech
                    success = self.voice_manager.resume()
                    if success:
                        print("🔊 TTS resumed via system tray single click")
                        self.status_label.setText("▶ TTS resumed via system tray single click")
                    else:
                        print("🔊 TTS resume failed via system tray single click")
                        self.status_label.setText("❌ TTS resume failed")
                else:
                    print("🔊 System tray single click - no active speech to pause/resume")
                    self.status_label.setText("No active speech to pause/resume")

                return  # Don't show window on single click

            # Handle double click or normal click - stop TTS and show window
            if self.voice_manager and self.voice_manager.is_speaking():
                print("🔊 TTS is speaking, stopping voice...")
                self.voice_manager.stop()
                self.status_label.setText("⏹ TTS stopped via system tray double click")

            # Show window (simulate showing chat bubble)
            print("💬 Showing chat window (simulated)")
            self.show()
            self.raise_()
            self.activateWindow()

        except Exception as e:
            print(f"❌ Tray click handler error: {e}")

    def _attempt_pause_with_retry(self, max_attempts=5):
        """Retry logic for pause operations."""
        import time

        for attempt in range(max_attempts):
            if not self.voice_manager.is_speaking():
                return False

            success = self.voice_manager.pause()
            if success:
                return True

            print(f"🔊 System tray pause attempt {attempt + 1}/{max_attempts} failed, retrying...")
            time.sleep(0.1)

        return False

    def setup_ui(self):
        """Set up the test UI."""
        layout = QVBoxLayout()

        # Title
        title = QLabel("Final Voice Mode Test - System Tray Integration")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "This test simulates the EXACT user experience in AbstractAssistant:\n"
            "• System tray icon with single/double click detection\n"
            "• Single click: Pause/Resume TTS (if active)\n"
            "• Double click: Stop TTS and show chat window\n"
            "• Same retry logic and timing as the real application"
        )
        desc.setStyleSheet("background: #e6f3ff; padding: 10px; margin: 10px; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Test controls
        controls_section = QLabel("Test Controls:")
        controls_section.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(controls_section)

        controls_layout = QHBoxLayout()

        self.start_speech_button = QPushButton("🔊 Start AI Response Speech")
        self.start_speech_button.clicked.connect(self.start_ai_speech)
        self.start_speech_button.setStyleSheet("font-size: 12px; padding: 8px;")
        controls_layout.addWidget(self.start_speech_button)

        self.simulate_single_click_button = QPushButton("👆 Simulate Single Click")
        self.simulate_single_click_button.clicked.connect(self.simulate_single_click)
        self.simulate_single_click_button.setStyleSheet("font-size: 12px; padding: 8px;")
        controls_layout.addWidget(self.simulate_single_click_button)

        self.simulate_double_click_button = QPushButton("👆👆 Simulate Double Click")
        self.simulate_double_click_button.clicked.connect(self.simulate_double_click)
        self.simulate_double_click_button.setStyleSheet("font-size: 12px; padding: 8px;")
        controls_layout.addWidget(self.simulate_double_click_button)

        layout.addLayout(controls_layout)

        # Status display
        self.status_label = QLabel("Ready - Start speech then test tray icon clicks")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("background: #f0f0f0; padding: 10px; margin: 10px; font-size: 12px;")
        layout.addWidget(self.status_label)

        # State display
        self.state_label = QLabel("TTS State: idle")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet("background: #f8f8f8; padding: 8px; margin: 5px; font-size: 11px;")
        layout.addWidget(self.state_label)

        # Instructions
        instructions = QLabel(
            "Test Instructions:\n"
            "1. Click 'Start AI Response Speech' to begin TTS\n"
            "2. While speaking, click 'Simulate Single Click' to pause (should work immediately)\n"
            "3. Click 'Simulate Single Click' again to resume\n"
            "4. Click 'Simulate Double Click' to stop and show this window\n"
            "\n"
            "This exactly simulates clicking the system tray icon in AbstractAssistant!"
        )
        instructions.setStyleSheet("background: #ffffcc; padding: 10px; margin: 10px; font-size: 10px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # System info
        system_info = QLabel(
            "System Tray Icon Info:\n"
            f"• Created: {self.tray_icon is not None}\n"
            f"• Has click handler: {hasattr(self.tray_icon, 'click_handler') if self.tray_icon else False}\n"
            f"• Voice manager available: {self.voice_manager is not None}"
        )
        system_info.setStyleSheet("background: #f0fff0; padding: 8px; margin: 8px; font-size: 9px;")
        layout.addWidget(system_info)

        self.setLayout(layout)

        # Timer for real-time updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(100)

    def start_ai_speech(self):
        """Start AI response speech."""
        if not self.voice_manager:
            self.status_label.setText("❌ VoiceManager not available")
            return

        # Simulate a typical AI response
        ai_response = "This is a simulated AI response demonstrating the complete voice mode functionality in AbstractAssistant. The system tray icon should now respond to single clicks for pause and resume operations, and double clicks for stopping speech and showing the chat bubble. You can test this by using the simulation buttons above, which exactly replicate the tray icon click behavior."

        try:
            success = self.voice_manager.speak(ai_response)
            if success:
                self.status_label.setText("🔊 AI response speech started - try tray icon clicks!")
                print("🔊 AI response speech started")
            else:
                self.status_label.setText("❌ Failed to start speech")
        except Exception as e:
            print(f"❌ Error starting speech: {e}")
            self.status_label.setText(f"❌ Speech error: {e}")

    def simulate_single_click(self):
        """Simulate single click on system tray icon."""
        print("👆 Simulating single click on system tray icon...")
        if self.tray_icon:
            self.handle_tray_click(single_click=True)
        else:
            self.status_label.setText("❌ No tray icon to click")

    def simulate_double_click(self):
        """Simulate double click on system tray icon."""
        print("👆👆 Simulating double click on system tray icon...")
        if self.tray_icon:
            self.handle_tray_click(double_click=True)
        else:
            self.status_label.setText("❌ No tray icon to click")

    def update_display(self):
        """Update real-time display."""
        if self.voice_manager:
            try:
                state = self.voice_manager.get_state()
                self.state_label.setText(f"TTS State: {state}")

                # Color code
                if state == 'speaking':
                    self.state_label.setStyleSheet("background: #90EE90; padding: 8px; margin: 5px; font-size: 11px;")
                elif state == 'paused':
                    self.state_label.setStyleSheet("background: #FFD700; padding: 8px; margin: 5px; font-size: 11px;")
                else:
                    self.state_label.setStyleSheet("background: #f8f8f8; padding: 8px; margin: 5px; font-size: 11px;")

            except Exception as e:
                self.state_label.setText(f"State: Error - {e}")

    def closeEvent(self, event):
        """Cleanup."""
        if self.voice_manager:
            self.voice_manager.cleanup()
        event.accept()


def main():
    """Main function."""
    print("🧪 Starting Final Voice Mode Test...")

    app = QApplication(sys.argv)
    window = FinalVoiceModeTest()
    window.show()

    print("✅ Final test window shown")
    print("📝 This test simulates the EXACT AbstractAssistant user experience:")
    print("  • System tray icon with single/double click detection")
    print("  • Single click: Pause/Resume TTS")
    print("  • Double click: Stop TTS and show chat")
    print("  • Same retry logic and timing as real app")
    print("🎯 Test the simulation buttons to verify everything works!")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()