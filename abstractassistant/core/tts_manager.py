"""
AbstractVoice Text-to-Speech Manager for AbstractAssistant.

This module provides TTS functionality using AbstractVoice exclusively.
"""

import threading
import time
from typing import Optional, Callable
import warnings

# Import AbstractVoice (required dependency)
try:
    from abstractvoice import VoiceManager as AbstractVoiceManager
    _ABSTRACTVOICE_AVAILABLE = True
    _ABSTRACTVOICE_ERROR = ""
except Exception as e:
    AbstractVoiceManager = None  # type: ignore[assignment]
    _ABSTRACTVOICE_AVAILABLE = False
    _ABSTRACTVOICE_ERROR = str(e)


class VoiceManager:
    """AbstractVoice-only TTS manager."""

    @staticmethod
    def is_available() -> bool:
        """Return True if AbstractVoice is installed and importable."""
        return bool(_ABSTRACTVOICE_AVAILABLE)
    
    def __init__(self, debug_mode: bool = False):
        """Initialize the voice manager using AbstractVoice.

        Args:
            debug_mode: Enable debug logging (AbstractVoice-compatible parameter name)
        """
        self.debug_mode = debug_mode
        self._abstractvoice_manager = None
        self._audio_meter_callback = None
        self._audio_chunk_hooked = False
        self._audio_chunk_player = None
        self._audio_chunk_prev = None
        self._audio_meter_warned = False
        self._audio_meter_band_warned = False
        
        # Callbacks for speech start/end events
        self.on_speech_start = None
        self.on_speech_end = None

        if not _ABSTRACTVOICE_AVAILABLE:
            warnings.warn(
                "#FALLBACK: AbstractVoice is not installed; TTS is disabled. "
                "Install with `pip install abstractvoice` or reinstall `abstractassistant`."
            )
            raise RuntimeError(f"AbstractVoice unavailable: {_ABSTRACTVOICE_ERROR}")

        try:
            self._abstractvoice_manager = AbstractVoiceManager(debug_mode=debug_mode)
            
            # Set up NEW v0.5.1 precise audio callbacks (not synthesis callbacks)
            self._abstractvoice_manager.on_audio_start = self._on_audio_start
            self._abstractvoice_manager.on_audio_end = self._on_audio_end
            self._wire_audio_chunk_meter()
            
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
        self._emit_audio_meter(0.0)

    def set_audio_meter_callback(self, callback: Optional[Callable[[float | list[float]], None]]) -> None:
        """Set a callback for audio meter updates (0..1 or per-band)."""
        self._audio_meter_callback = callback
        self._wire_audio_chunk_meter()

    def _wire_audio_chunk_meter(self) -> None:
        """Attach to the underlying audio player for meter updates."""
        mgr = self._abstractvoice_manager
        if mgr is None:
            return
        tts_engine = getattr(mgr, "tts_engine", None)
        audio_player = getattr(tts_engine, "audio_player", None) if tts_engine is not None else None
        if audio_player is None:
            if self._audio_meter_callback and not self._audio_meter_warned:
                warnings.warn("#FALLBACK: voice meter unavailable; audio player missing")
                self._audio_meter_warned = True
            return
        if self._audio_chunk_hooked and self._audio_chunk_player is audio_player:
            return

        prev = getattr(audio_player, "on_audio_chunk", None)

        def _on_chunk(chunk, sample_rate: int) -> None:
            if callable(prev):
                try:
                    prev(chunk, sample_rate)
                except Exception:
                    pass
            self._emit_audio_meter_from_chunk(chunk, sample_rate)

        audio_player.on_audio_chunk = _on_chunk
        self._audio_chunk_hooked = True
        self._audio_chunk_player = audio_player
        self._audio_chunk_prev = prev

    def _emit_audio_meter_from_chunk(self, chunk, sample_rate: int | None = None) -> None:
        cb = self._audio_meter_callback
        if cb is None:
            return
        try:
            import numpy as np

            arr = np.asarray(chunk, dtype=np.float32)
            if arr.size <= 0:
                return
            if arr.ndim > 1:
                arr = np.mean(arr, axis=1)
            if arr.size <= 0:
                return
            arr = arr - float(np.mean(arr))
            rms = float(np.sqrt(np.mean(np.square(arr))))
            level = min(1.0, max(0.0, rms * 3.0))
            bands = []
            if sample_rate and sample_rate > 0:
                bands = self._compute_band_levels(arr, int(sample_rate), rms)
            else:
                if self._audio_meter_callback and not self._audio_meter_band_warned:
                    warnings.warn("#FALLBACK: voice meter bands unavailable; missing sample rate")
                    self._audio_meter_band_warned = True
            if bands:
                cb(bands)
            else:
                if sample_rate and sample_rate > 0 and self._audio_meter_callback and not self._audio_meter_band_warned:
                    warnings.warn("#FALLBACK: voice meter bands unavailable; FFT analysis failed")
                    self._audio_meter_band_warned = True
                cb(level)
        except Exception:
            pass

    def _emit_audio_meter(self, level) -> None:
        cb = self._audio_meter_callback
        if cb is None:
            return
        try:
            cb(level)
        except Exception:
            pass

    def _compute_band_levels(self, samples, sample_rate: int, rms: float) -> list[float]:
        """Compute log-spaced band levels for a short audio slice."""
        try:
            import numpy as np
            import math
        except Exception:
            return []
        if sample_rate <= 0 or samples is None:
            return []
        n = int(min(len(samples), 2048))
        if n <= 8:
            return []
        window = np.hanning(n)
        slice_samples = samples[-n:] * window
        spectrum = np.fft.rfft(slice_samples)
        power = np.abs(spectrum) ** 2
        freqs = np.fft.rfftfreq(n, d=1.0 / float(sample_rate))
        nyquist = max(1.0, float(sample_rate) / 2.0)
        low = 80.0
        high = min(6000.0, nyquist)
        if high <= low:
            return []
        band_count = 5
        ratio = (high / low) ** (1.0 / band_count)
        edges = [low * (ratio ** i) for i in range(band_count + 1)]
        total = float(np.sqrt(np.mean(power))) if power.size else 0.0
        if total <= 0.0:
            return []
        levels: list[float] = []
        for i in range(band_count):
            lo = edges[i]
            hi = edges[i + 1]
            mask = (freqs >= lo) & (freqs < hi)
            if not np.any(mask):
                levels.append(0.0)
                continue
            band_power = float(np.sqrt(np.mean(power[mask])))
            levels.append(band_power / total)
        max_level = max(levels) if levels else 0.0
        if max_level <= 0.0:
            return []
        amp = min(1.0, max(0.0, rms * 3.0))
        shaped = [math.sqrt(min(1.0, max(0.0, lvl / max_level))) for lvl in levels]
        return [min(1.0, lvl * (0.4 + 0.6 * amp)) for lvl in shaped]
    
    def supports_tts(self) -> bool:
        """Return True when TTS is supported."""
        return True

    def supports_stt(self) -> bool:
        """Return True when STT is supported by the installed AbstractVoice."""
        return bool(hasattr(self._abstractvoice_manager, "listen"))
    
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
            self._emit_audio_meter(0.0)
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
                started = self._abstractvoice_manager.listen(
                    on_transcription=on_transcription,
                    on_stop=on_stop
                )
                if self.debug_mode:
                    if self.debug_mode:
                        print(f"🎤 Started listening for speech (started={bool(started)})")
                if not started:
                    raise RuntimeError("Voice listening failed to start (no exception was raised).")
                return bool(started)
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

    def stop_speaking(self):
        """Stop current speech (compat alias used by the Qt UI)."""
        return self.stop()

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

    def pause_listening(self) -> bool:
        """Pause STT listening while keeping voice mode active."""
        fn = getattr(self._abstractvoice_manager, "pause_listening", None)
        if not callable(fn):
            warnings.warn("#FALLBACK: listening pause unsupported by voice backend")
            return False
        try:
            fn()
            return True
        except Exception as e:
            warnings.warn(f"#FALLBACK: failed to pause listening: {e}")
            return False

    def resume_listening(self) -> bool:
        """Resume STT listening after pause."""
        fn = getattr(self._abstractvoice_manager, "resume_listening", None)
        if not callable(fn):
            warnings.warn("#FALLBACK: listening resume unsupported by voice backend")
            return False
        try:
            fn()
            return True
        except Exception as e:
            warnings.warn(f"#FALLBACK: failed to resume listening: {e}")
            return False

    def is_listening_paused(self) -> bool:
        """Return True when STT listening is paused."""
        try:
            return bool(getattr(self._abstractvoice_manager, "listening_paused", False))
        except Exception:
            return False


# Alias for backward compatibility
TTSManager = VoiceManager
