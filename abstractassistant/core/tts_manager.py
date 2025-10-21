"""
AbstractVoice Text-to-Speech Manager for AbstractAssistant.

This module provides TTS functionality using AbstractVoice exclusively.
"""

import threading
import time
from typing import Optional, Callable

# Import AbstractVoice (required dependency)
from abstractvoice import VoiceManager as AbstractVoiceManager


class VoiceManager:
    """AbstractVoice-only TTS manager."""
    
    def __init__(self, debug_mode: bool = False):
        """Initialize the voice manager using AbstractVoice.

        Args:
            debug_mode: Enable debug logging (AbstractVoice-compatible parameter name)
        """
        self.debug_mode = debug_mode
        self._abstractvoice_manager = None
        
        # Callbacks for speech start/end events
        self.on_speech_start = None
        self.on_speech_end = None

        try:
            self._abstractvoice_manager = AbstractVoiceManager(debug_mode=debug_mode)
            
            # Set up NEW v0.5.1 precise audio callbacks (not synthesis callbacks)
            self._abstractvoice_manager.on_audio_start = self._on_audio_start
            self._abstractvoice_manager.on_audio_end = self._on_audio_end
            
            if self.debug_mode:
                if self.debug_mode:
                    print("🔊 AbstractVoice v0.5.1 initialized with precise audio callbacks")
        except Exception as e:
            if self.debug_mode:
                if self.debug_mode:
                    print(f"❌ AbstractVoice initialization failed: {e}")
            raise RuntimeError(f"Failed to initialize AbstractVoice: {e}")
    
    def _on_audio_start(self):
        """Called when audio stream actually starts playing (v0.5.1 precise timing)."""
        if self.debug_mode:
            if self.debug_mode:
                print("🔊 Audio stream started - user can hear speech")
        if self.on_speech_start:
            self.on_speech_start()
    
    def _on_audio_end(self):
        """Called when audio stream actually ends (v0.5.1 precise timing)."""
        if self.debug_mode:
            if self.debug_mode:
                print("🔊 Audio stream ended - ready for next action")
        if self.on_speech_end:
            self.on_speech_end()
    
    def is_available(self) -> bool:
        """Check if TTS is available."""
        return True  # AbstractVoice is a required dependency, always available after construction
    
    def is_speaking(self) -> bool:
        """Check if TTS is currently speaking."""
        return self._abstractvoice_manager.is_speaking()
    
    def speak(self, text: str, speed: float = 1.0, callback: Optional[Callable] = None) -> bool:
        """Speak the given text using AbstractVoice.

        Args:
            text: Text to speak
            speed: Speech speed multiplier (AbstractVoice-compatible)
            callback: Optional callback to call when speech is complete

        Returns:
            True if speech started successfully, False otherwise
        """
        if not text.strip():
            if self.debug_mode:
                if self.debug_mode:
                    print("❌ Empty text provided to TTS")
            return False

        try:
            self._abstractvoice_manager.speak(text, speed=speed, callback=callback)
            return True
        except Exception as e:
            if self.debug_mode:
                if self.debug_mode:
                    print(f"❌ AbstractVoice speak error: {e}")
            return False
    
    def pause(self) -> bool:
        """Pause current speech.

        Returns:
            True if speech was paused successfully, False otherwise
        """
        try:
            success = self._abstractvoice_manager.pause_speaking()
            if self.debug_mode:
                if self.debug_mode:
                    print(f"🔊 AbstractVoice speech {'paused' if success else 'pause failed'}")
            return success
        except Exception as e:
            if self.debug_mode:
                if self.debug_mode:
                    print(f"❌ Error pausing AbstractVoice: {e}")
            return False

    def resume(self) -> bool:
        """Resume paused speech.

        Returns:
            True if speech was resumed successfully, False otherwise
        """
        try:
            success = self._abstractvoice_manager.resume_speaking()
            if self.debug_mode:
                if self.debug_mode:
                    print(f"🔊 AbstractVoice speech {'resumed' if success else 'resume failed'}")
            return success
        except Exception as e:
            if self.debug_mode:
                if self.debug_mode:
                    print(f"❌ Error resuming AbstractVoice: {e}")
            return False

    def is_paused(self) -> bool:
        """Check if TTS is currently paused."""
        try:
            return self._abstractvoice_manager.is_paused()
        except Exception as e:
            if self.debug_mode:
                if self.debug_mode:
                    print(f"❌ Error checking pause state: {e}")
            return False

    def get_state(self) -> str:
        """Get current TTS state.

        Returns:
            One of: 'idle', 'speaking', 'paused', 'stopped'
        """
        try:
            if self.is_paused():
                return 'paused'
            elif self.is_speaking():
                return 'speaking'
            else:
                return 'idle'
        except Exception as e:
            if self.debug_mode:
                if self.debug_mode:
                    print(f"❌ Error getting TTS state: {e}")
            return 'idle'

    def stop(self):
        """Stop current speech."""
        try:
            self._abstractvoice_manager.stop_speaking()
            if self.debug_mode:
                if self.debug_mode:
                    print("🔊 AbstractVoice speech stopped")
        except Exception as e:
            if self.debug_mode:
                if self.debug_mode:
                    print(f"❌ Error stopping AbstractVoice: {e}")

    def cleanup(self):
        """Clean up TTS resources."""
        try:
            self._abstractvoice_manager.cleanup()
            if self.debug_mode:
                if self.debug_mode:
                    print("🔊 AbstractVoice cleaned up")
        except Exception as e:
            if self.debug_mode:
                if self.debug_mode:
                    print(f"❌ Error cleaning up AbstractVoice: {e}")

    # STT (Speech-to-Text) Methods for Full Voice Mode

    def set_voice_mode(self, mode: str):
        """Set voice interaction mode.

        Args:
            mode: Voice mode ('full', 'wait', 'stop', 'ptt')
        """
        if hasattr(self._abstractvoice_manager, 'set_voice_mode'):
            try:
                self._abstractvoice_manager.set_voice_mode(mode)
                if self.debug_mode:
                    if self.debug_mode:
                        print(f"🔊 Voice mode set to: {mode}")
            except Exception as e:
                if self.debug_mode:
                    if self.debug_mode:
                        print(f"❌ Error setting voice mode: {e}")
        else:
            if self.debug_mode:
                if self.debug_mode:
                    print(f"⚠️  Voice mode setting not available, simulating mode: {mode}")

    def listen(self, on_transcription: Callable[[str], None], on_stop: Callable[[], None] = None):
        """Start listening for speech input.

        Args:
            on_transcription: Callback function for transcribed text
            on_stop: Callback function for stop command
        """
        if hasattr(self._abstractvoice_manager, 'listen'):
            try:
                self._abstractvoice_manager.listen(
                    on_transcription=on_transcription,
                    on_stop=on_stop
                )
                if self.debug_mode:
                    if self.debug_mode:
                        print("🎤 Started listening for speech")
            except Exception as e:
                if self.debug_mode:
                    if self.debug_mode:
                        print(f"❌ Error starting listening: {e}")
                raise
        else:
            if self.debug_mode:
                if self.debug_mode:
                    print("⚠️  STT listening not available in current AbstractVoice version")
            raise RuntimeError("STT listening not available")

    def stop_listening(self):
        """Stop listening for speech input."""
        if hasattr(self._abstractvoice_manager, 'stop_listening'):
            try:
                self._abstractvoice_manager.stop_listening()
                if self.debug_mode:
                    if self.debug_mode:
                        print("🎤 Stopped listening for speech")
            except Exception as e:
                if self.debug_mode:
                    if self.debug_mode:
                        print(f"❌ Error stopping listening: {e}")
        else:
            if self.debug_mode:
                if self.debug_mode:
                    print("⚠️  Stop listening not available in current AbstractVoice version")

    def is_listening(self) -> bool:
        """Check if currently listening for speech."""
        if hasattr(self._abstractvoice_manager, 'is_listening'):
            try:
                return self._abstractvoice_manager.is_listening()
            except Exception as e:
                if self.debug_mode:
                    if self.debug_mode:
                        print(f"❌ Error checking listening state: {e}")
                return False
        else:
            if self.debug_mode:
                if self.debug_mode:
                    print("⚠️  Listening state check not available")
            return False


# Alias for backward compatibility
TTSManager = VoiceManager