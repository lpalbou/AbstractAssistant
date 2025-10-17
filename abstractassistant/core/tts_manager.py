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