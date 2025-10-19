"""
TTS State Manager for AbstractAssistant.

Centralizes TTS state management, coordinates between VoiceManager
and UI components, and provides a single source of truth for TTS state.
"""

from typing import Optional, Callable, Any
from enum import Enum


class TTSState(Enum):
    """TTS state enumeration."""
    IDLE = "idle"
    SPEAKING = "speaking"
    PAUSED = "paused"
    DISABLED = "disabled"


class TTSStateManager:
    """Manages TTS state coordination between VoiceManager and UI components."""

    def __init__(self, voice_manager=None, debug: bool = False):
        """Initialize the TTS state manager.

        Args:
            voice_manager: VoiceManager instance
            debug: Enable debug logging
        """
        self.voice_manager = voice_manager
        self.debug = debug

        # UI component references (set externally)
        self.tts_toggle_widget = None
        self.status_label = None

        # State change callbacks
        self._state_change_callbacks = []

        # Last known state for change detection
        self._last_state = TTSState.DISABLED

    def set_voice_manager(self, voice_manager):
        """Set the voice manager instance.

        Args:
            voice_manager: VoiceManager instance
        """
        self.voice_manager = voice_manager
        if self.debug:
            print(f"🔊 TTSStateManager: Voice manager set to {type(voice_manager).__name__}")

    def set_tts_toggle_widget(self, widget):
        """Set the TTS toggle widget reference.

        Args:
            widget: TTSToggle widget instance
        """
        self.tts_toggle_widget = widget
        if self.debug:
            print("🔊 TTSStateManager: TTS toggle widget reference set")

    def set_status_label(self, label):
        """Set the status label reference.

        Args:
            label: QLabel instance for status display
        """
        self.status_label = label
        if self.debug:
            print("🔊 TTSStateManager: Status label reference set")

    def add_state_change_callback(self, callback: Callable[[TTSState], None]):
        """Add a callback to be called when TTS state changes.

        Args:
            callback: Function to call with new state
        """
        self._state_change_callbacks.append(callback)
        if self.debug:
            print(f"🔊 TTSStateManager: Added state change callback ({len(self._state_change_callbacks)} total)")

    def get_current_state(self) -> TTSState:
        """Get the current TTS state.

        Returns:
            Current TTSState
        """
        if not self.voice_manager:
            return TTSState.DISABLED

        try:
            # Get state from voice manager
            voice_state = self.voice_manager.get_state()

            # Map voice manager states to our enum
            if voice_state == 'speaking':
                return TTSState.SPEAKING
            elif voice_state == 'paused':
                return TTSState.PAUSED
            elif voice_state == 'idle':
                return TTSState.IDLE
            else:
                return TTSState.IDLE

        except Exception as e:
            if self.debug:
                print(f"❌ Error getting TTS state: {e}")
            return TTSState.DISABLED

    def update_ui_state(self, force_update: bool = False):
        """Update all UI components to reflect current TTS state.

        Args:
            force_update: Force update even if state hasn't changed
        """
        current_state = self.get_current_state()

        # Check if state has changed
        if not force_update and current_state == self._last_state:
            return

        if self.debug:
            print(f"🔊 TTSStateManager: State changed from {self._last_state.value} to {current_state.value}")

        # Update TTS toggle widget
        if self.tts_toggle_widget:
            try:
                self.tts_toggle_widget.set_tts_state(current_state.value)
            except Exception as e:
                if self.debug:
                    print(f"❌ Error updating TTS toggle widget: {e}")

        # Update status label
        if self.status_label:
            try:
                self._update_status_label(current_state)
            except Exception as e:
                if self.debug:
                    print(f"❌ Error updating status label: {e}")

        # Call state change callbacks
        for callback in self._state_change_callbacks:
            try:
                callback(current_state)
            except Exception as e:
                if self.debug:
                    print(f"❌ Error in state change callback: {e}")

        # Remember last state
        self._last_state = current_state

    def _update_status_label(self, state: TTSState):
        """Update the status label text and style.

        Args:
            state: Current TTS state
        """
        if not self.status_label:
            return

        # Import UIStyles here to avoid circular imports
        try:
            from .ui_styles import UIStyles

            status_text = {
                TTSState.IDLE: "TTS Ready",
                TTSState.SPEAKING: "Speaking...",
                TTSState.PAUSED: "TTS Paused",
                TTSState.DISABLED: "TTS Disabled"
            }

            status_style = {
                TTSState.IDLE: "ready",
                TTSState.SPEAKING: "generating",
                TTSState.PAUSED: "error",  # Use warning color for paused
                TTSState.DISABLED: "idle"
            }

            self.status_label.setText(status_text.get(state, "Unknown"))
            self.status_label.setStyleSheet(UIStyles.get_status_style(status_style.get(state, "idle")))

        except ImportError:
            # Fallback without styling
            status_text = {
                TTSState.IDLE: "TTS Ready",
                TTSState.SPEAKING: "Speaking...",
                TTSState.PAUSED: "TTS Paused",
                TTSState.DISABLED: "TTS Disabled"
            }
            self.status_label.setText(status_text.get(state, "Unknown"))

    def pause_resume_toggle(self) -> bool:
        """Toggle between pause and resume based on current state.

        Returns:
            True if operation succeeded, False otherwise
        """
        if not self.voice_manager:
            if self.debug:
                print("❌ No voice manager available for pause/resume")
            return False

        current_state = self.get_current_state()

        if current_state == TTSState.SPEAKING:
            # Pause the speech
            success = self._attempt_pause_with_retry()
            if success and self.debug:
                print("⏸ TTSStateManager: Successfully paused speech")
            return success

        elif current_state == TTSState.PAUSED:
            # Resume the speech
            success = self.voice_manager.resume()
            if success and self.debug:
                print("▶ TTSStateManager: Successfully resumed speech")
            return success

        if self.debug:
            print(f"⚠️  Cannot pause/resume from state: {current_state.value}")
        return False

    def _attempt_pause_with_retry(self, max_attempts: int = 5, delay: float = 0.1) -> bool:
        """Attempt to pause with retry logic for AbstractVoice initialization.

        Args:
            max_attempts: Maximum number of retry attempts
            delay: Delay between attempts in seconds

        Returns:
            True if pause succeeded, False otherwise
        """
        import time

        for attempt in range(max_attempts):
            try:
                if self.voice_manager.pause():
                    if self.debug:
                        print(f"⏸ TTSStateManager: Pause succeeded on attempt {attempt + 1}")
                    return True

                if self.debug:
                    print(f"⏸ TTSStateManager: Pause attempt {attempt + 1} failed, retrying...")
                time.sleep(delay)

            except Exception as e:
                if self.debug:
                    print(f"❌ TTSStateManager: Pause attempt {attempt + 1} error: {e}")
                time.sleep(delay)

        if self.debug:
            print(f"❌ TTSStateManager: Pause failed after {max_attempts} attempts")
        return False

    def stop_speech(self) -> bool:
        """Stop current speech.

        Returns:
            True if stop succeeded, False otherwise
        """
        if not self.voice_manager:
            if self.debug:
                print("❌ No voice manager available for stop")
            return False

        try:
            self.voice_manager.stop()
            if self.debug:
                print("⏹ TTSStateManager: Speech stopped")
            return True

        except Exception as e:
            if self.debug:
                print(f"❌ TTSStateManager: Error stopping speech: {e}")
            return False

    def start_speech(self, text: str, speed: float = 1.0, callback: Optional[Callable] = None) -> bool:
        """Start speech with the given text.

        Args:
            text: Text to speak
            speed: Speech speed multiplier
            callback: Optional completion callback

        Returns:
            True if speech started successfully, False otherwise
        """
        if not self.voice_manager:
            if self.debug:
                print("❌ No voice manager available for speech")
            return False

        try:
            success = self.voice_manager.speak(text, speed=speed, callback=callback)
            if success and self.debug:
                print(f"🔊 TTSStateManager: Started speech: {text[:50]}...")
            return success

        except Exception as e:
            if self.debug:
                print(f"❌ TTSStateManager: Error starting speech: {e}")
            return False

    def is_speaking(self) -> bool:
        """Check if TTS is currently speaking.

        Returns:
            True if speaking, False otherwise
        """
        return self.get_current_state() == TTSState.SPEAKING

    def is_paused(self) -> bool:
        """Check if TTS is currently paused.

        Returns:
            True if paused, False otherwise
        """
        return self.get_current_state() == TTSState.PAUSED

    def is_available(self) -> bool:
        """Check if TTS is available and ready.

        Returns:
            True if available, False otherwise
        """
        return self.get_current_state() != TTSState.DISABLED