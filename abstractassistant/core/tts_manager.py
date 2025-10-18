"""
VoiceLLM Text-to-Speech Manager for AbstractAssistant.

This module provides TTS functionality using VoiceLLM exclusively.
"""

import threading
import time
from typing import Optional, Callable

# Import VoiceLLM
try:
    from voicellm import VoiceManager as VoiceLLMManager
    VOICELLM_AVAILABLE = True
except ImportError as e:
    VOICELLM_AVAILABLE = False
    VoiceLLMManager = None
    print(f"❌ VoiceLLM not available: {e}")


class VoiceManager:
    """VoiceLLM-only TTS manager."""
    
    def __init__(self, debug_mode: bool = False):
        """Initialize the voice manager using VoiceLLM.
        
        Args:
            debug_mode: Enable debug logging (VoiceLLM-compatible parameter name)
        """
        self.debug_mode = debug_mode
        self._voicellm_manager = None
        
        if not VOICELLM_AVAILABLE:
            raise RuntimeError("VoiceLLM is not available. Please install VoiceLLM and its dependencies.")
        
        try:
            self._voicellm_manager = VoiceLLMManager(debug_mode=debug_mode)
            if self.debug_mode:
                print("🔊 VoiceLLM initialized successfully")
        except Exception as e:
            if self.debug_mode:
                print(f"❌ VoiceLLM initialization failed: {e}")
            raise RuntimeError(f"Failed to initialize VoiceLLM: {e}")
    
    def is_available(self) -> bool:
        """Check if TTS is available."""
        return self._voicellm_manager is not None
    
    def is_speaking(self) -> bool:
        """Check if TTS is currently speaking."""
        if self._voicellm_manager:
            return self._voicellm_manager.is_speaking()
        return False
    
    def speak(self, text: str, speed: float = 1.0, callback: Optional[Callable] = None) -> bool:
        """Speak the given text using VoiceLLM.
        
        Args:
            text: Text to speak
            speed: Speech speed multiplier (VoiceLLM-compatible)
            callback: Optional callback to call when speech is complete
            
        Returns:
            True if speech started successfully, False otherwise
        """
        if not self.is_available():
            if self.debug_mode:
                print("❌ VoiceLLM not available")
            return False
        
        if not text.strip():
            if self.debug_mode:
                print("❌ Empty text provided to TTS")
            return False
        
        try:
            self._voicellm_manager.speak(text, speed=speed, callback=callback)
            return True
        except Exception as e:
            if self.debug_mode:
                print(f"❌ VoiceLLM speak error: {e}")
            return False
    
    def pause(self) -> bool:
        """Pause current speech.

        Returns:
            True if speech was paused successfully, False otherwise
        """
        if self._voicellm_manager:
            try:
                success = self._voicellm_manager.pause_speaking()
                if self.debug_mode:
                    print(f"🔊 VoiceLLM speech {'paused' if success else 'pause failed'}")
                return success
            except Exception as e:
                if self.debug_mode:
                    print(f"❌ Error pausing VoiceLLM: {e}")
                return False
        return False

    def resume(self) -> bool:
        """Resume paused speech.

        Returns:
            True if speech was resumed successfully, False otherwise
        """
        if self._voicellm_manager:
            try:
                success = self._voicellm_manager.resume_speaking()
                if self.debug_mode:
                    print(f"🔊 VoiceLLM speech {'resumed' if success else 'resume failed'}")
                return success
            except Exception as e:
                if self.debug_mode:
                    print(f"❌ Error resuming VoiceLLM: {e}")
                return False
        return False

    def is_paused(self) -> bool:
        """Check if TTS is currently paused."""
        if self._voicellm_manager:
            try:
                return self._voicellm_manager.is_paused()
            except Exception as e:
                if self.debug_mode:
                    print(f"❌ Error checking pause state: {e}")
                return False
        return False

    def get_state(self) -> str:
        """Get current TTS state.

        Returns:
            One of: 'idle', 'speaking', 'paused', 'stopped'
        """
        if not self._voicellm_manager:
            return 'idle'

        try:
            if self.is_paused():
                return 'paused'
            elif self.is_speaking():
                return 'speaking'
            else:
                return 'idle'
        except Exception as e:
            if self.debug_mode:
                print(f"❌ Error getting TTS state: {e}")
            return 'idle'

    def stop(self):
        """Stop current speech."""
        if self._voicellm_manager:
            try:
                self._voicellm_manager.stop_speaking()
                if self.debug_mode:
                    print("🔊 VoiceLLM speech stopped")
            except Exception as e:
                if self.debug_mode:
                    print(f"❌ Error stopping VoiceLLM: {e}")
    
    def cleanup(self):
        """Clean up TTS resources."""
        if self._voicellm_manager:
            try:
                self._voicellm_manager.cleanup()
                if self.debug_mode:
                    print("🔊 VoiceLLM cleaned up")
            except Exception as e:
                if self.debug_mode:
                    print(f"❌ Error cleaning up VoiceLLM: {e}")


# Alias for backward compatibility
TTSManager = VoiceManager