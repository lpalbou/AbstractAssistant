"""
Gateway voice manager for AbstractAssistant.

TTS: gateway /voice/tts → download audio artifact → local OS playback.
STT: AbstractVoice VoiceRecognizer (mic + VAD) → GatewaySTTAdapter → gateway /audio/transcribe.
"""

from __future__ import annotations

import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import warnings
from pathlib import Path
from typing import Callable, Optional, Tuple

from abstractruntime.integrations.abstractcore.session_attachments import session_memory_owner_run_id


class GatewayVoiceManager:
    """Gateway-backed voice manager with a VoiceManager-compatible interface."""

    def __init__(self, *, llm_manager, debug_mode: bool = False) -> None:
        self._llm_manager = llm_manager
        self.debug_mode = bool(debug_mode)

        self.on_speech_start = None
        self.on_speech_end = None

        self._listening = False
        self._recognizer = None

        self._speaking = False
        self._paused = False
        self._play_proc: Optional[subprocess.Popen] = None
        # Playback readiness (pause waits until a player spawns or fails).
        self._play_ready = threading.Event()
        self._state_lock = threading.Lock()
        self._audio_meter_callback = None
        self._meter_thread: Optional[threading.Thread] = None
        self._meter_stop = threading.Event()
        self._meter_pause = threading.Event()
        self._audio_meter_warned = False
        # Voice-mode coordination with STT (mirrors AbstractVoice semantics).
        self._voice_mode = "wait"
        self._tts_gate_active = False
        self._tts_gate_lock = threading.Lock()
        self._full_mode_tts_gate_warned = False

    def _default_stt_language(self) -> Optional[str]:
        """Best-effort language hint for STT (improves accuracy vs autodetect)."""
        try:
            from abstractcore.config.manager import get_config_manager  # type: ignore

            lang = getattr(getattr(get_config_manager().config, "audio", None), "stt_language", None)
            if isinstance(lang, str) and lang.strip():
                return lang.strip()
        except Exception:
            return None
        return None

    def is_available(self) -> bool:
        """Return True if any gateway voice capability is available."""
        return bool(self.supports_tts() or self.supports_stt())

    def supports_tts(self) -> bool:
        """Return True when a local audio player is available."""
        return bool(self._audio_player_available())

    def supports_stt(self) -> bool:
        """Return True when AbstractVoice mic+VAD infrastructure is available."""
        try:
            from abstractvoice.recognition import VoiceRecognizer  # noqa: F401
            return True
        except ImportError:
            return False

    def set_voice_mode(self, mode: str) -> None:
        """Set listening profile and TTS/STT coordination mode.

        Valid modes: stop | wait | full | ptt
        """
        m = str(mode or "").strip().lower()
        if m not in ("stop", "wait", "full", "ptt"):
            return
        self._voice_mode = m
        rec = self._recognizer
        if rec is None or not hasattr(rec, "set_profile"):
            return
        try:
            rec.set_profile(m)
        except Exception:
            pass

    def _tts_gate_start(self) -> None:
        """Apply STT gating for the current voice mode while TTS plays."""
        rec = self._recognizer
        if rec is None:
            return

        with self._tts_gate_lock:
            if self._tts_gate_active:
                return
            self._tts_gate_active = True

        mode = str(getattr(self, "_voice_mode", "wait") or "").strip().lower()
        try:
            if mode == "wait":
                if hasattr(rec, "pause_listening"):
                    rec.pause_listening()
                return

            # Gateway playback can't feed far-end audio (no AEC reference), so FULL mode
            # would self-transcribe on speakers. Prefer STOP-style suppression.
            if mode == "full" and not bool(getattr(self, "_full_mode_tts_gate_warned", False)):
                warnings.warn(
                    "#FALLBACK: gateway voice mode 'full' can't provide far-end audio; suppressing transcriptions during TTS"
                )
                self._full_mode_tts_gate_warned = True

            if hasattr(rec, "pause_tts_interrupt"):
                rec.pause_tts_interrupt()
            if hasattr(rec, "pause_transcriptions"):
                rec.pause_transcriptions()
        except Exception:
            pass

    def _tts_gate_end(self) -> None:
        """Undo STT gating after TTS stops/pauses."""
        rec = self._recognizer

        with self._tts_gate_lock:
            if not self._tts_gate_active:
                return
            self._tts_gate_active = False

        if rec is None:
            return

        mode = str(getattr(self, "_voice_mode", "wait") or "").strip().lower()
        try:
            if mode == "wait":
                if hasattr(rec, "resume_listening"):
                    rec.resume_listening()
                return

            if hasattr(rec, "resume_tts_interrupt"):
                rec.resume_tts_interrupt()
            if hasattr(rec, "resume_transcriptions"):
                rec.resume_transcriptions()
        except Exception:
            pass

    def set_audio_meter_callback(self, callback: Optional[Callable[[float | list[float]], None]]) -> None:
        """Set a callback for audio meter updates (0..1 or per-band)."""
        self._audio_meter_callback = callback

    def listen(
        self,
        on_transcription: Callable[[str], None],
        on_stop: Callable[[], None] | None = None,
        on_audio_level: Callable[[float], None] | None = None,
    ) -> bool:
        """Start listening via AbstractVoice VoiceRecognizer + gateway STT."""
        if not self.supports_stt():
            raise RuntimeError("Gateway STT unavailable (microphone not available)")
        if self._listening:
            return True

        from abstractvoice.recognition import VoiceRecognizer
        from .gateway_stt_adapter import GatewaySTTAdapter

        adapter = GatewaySTTAdapter(
            gateway_client_fn=self._gateway_client,
            session_id_fn=self._session_id,
            run_id_fn=self._session_run_id,
        )
        lang = None
        try:
            lang = self._default_stt_language()
        except Exception:
            lang = None

        def _on_transcription(text: str) -> None:
            try:
                if on_transcription:
                    on_transcription(text)
            except Exception as e:
                warnings.warn(f"#FALLBACK: transcription callback error: {e}")

        def _on_stop() -> None:
            try:
                self.stop_speaking()
            except Exception:
                pass
            try:
                if on_stop:
                    on_stop()
            except Exception:
                pass

        def _on_audio_level(level: float) -> None:
            try:
                if on_audio_level is not None:
                    on_audio_level(float(level))
            except Exception:
                pass

        rec = VoiceRecognizer(
            transcription_callback=_on_transcription,
            stop_callback=_on_stop,
            debug_mode=self.debug_mode,
            stt_adapter=adapter,
            language=lang,
            audio_level_callback=_on_audio_level,
        )
        try:
            if hasattr(rec, "set_profile"):
                rec.set_profile(str(getattr(self, "_voice_mode", "wait") or "wait"))
        except Exception:
            pass

        self._recognizer = rec
        self._listening = True
        try:
            started = rec.start()
        except Exception as e:
            self._listening = False
            self._recognizer = None
            raise RuntimeError(f"VoiceRecognizer failed to start: {e}") from e
        if not started:
            self._listening = False
            self._recognizer = None
            raise RuntimeError("VoiceRecognizer failed to start")
        return True

    def stop_listening(self) -> None:
        """Stop the STT listening loop."""
        self._listening = False
        rec = self._recognizer
        if rec is not None:
            try:
                rec.stop()
            except Exception:
                pass
        self._recognizer = None

    def is_listening(self) -> bool:
        return bool(self._listening)

    def pause_listening(self) -> bool:
        """Pause microphone listening while keeping full voice mode enabled."""
        rec = self._recognizer
        if rec is None or not bool(self._listening):
            return False
        fn = getattr(rec, "pause_listening", None)
        if not callable(fn):
            warnings.warn("#FALLBACK: listening pause unsupported by recognizer")
            return False
        try:
            fn()
            return True
        except Exception as e:
            warnings.warn(f"#FALLBACK: failed to pause listening: {e}")
            return False

    def resume_listening(self) -> bool:
        """Resume microphone listening after a user pause."""
        rec = self._recognizer
        if rec is None or not bool(self._listening):
            return False
        fn = getattr(rec, "resume_listening", None)
        if not callable(fn):
            warnings.warn("#FALLBACK: listening resume unsupported by recognizer")
            return False
        try:
            fn()
            return True
        except Exception as e:
            warnings.warn(f"#FALLBACK: failed to resume listening: {e}")
            return False

    def is_listening_paused(self) -> bool:
        """Return True when microphone capture is paused."""
        rec = self._recognizer
        if rec is None:
            return False
        try:
            return bool(getattr(rec, "listening_paused", False))
        except Exception:
            return False

    def change_vad_aggressiveness(self, aggressiveness: int) -> bool:
        """Forward VAD aggressiveness change to the recognizer."""
        rec = self._recognizer
        if rec is not None and hasattr(rec, "change_vad_aggressiveness"):
            return bool(rec.change_vad_aggressiveness(aggressiveness))
        return False

    def speak(self, text: str, speed: float = 1.0, callback: Optional[Callable] = None) -> bool:
        """Speak the given text via gateway TTS."""
        _ = float(speed or 1.0)
        raw = str(text or "").strip()
        if not raw:
            return False
        if not self.supports_tts():
            warnings.warn("#FALLBACK: gateway TTS unavailable; missing local player")
            return False
        gw = None
        old_timeout = None
        try:
            gw = self._gateway_client()
            try:
                cfg = getattr(gw, "_cfg", None)
                if cfg is not None:
                    old_timeout = float(getattr(cfg, "timeout_s", 0) or 0)
                    if old_timeout and old_timeout < 120.0:
                        cfg.timeout_s = 120.0
            except Exception:
                old_timeout = None
            run_id = self._session_run_id()
            res = gw.voice_tts(run_id=run_id, text=raw, fmt="wav", request_id=str(uuid.uuid4()))
            audio = res.get("audio_artifact") if isinstance(res, dict) else None
            aid = str(audio.get("$artifact") or "").strip() if isinstance(audio, dict) else ""
            if not aid:
                raise RuntimeError("Gateway TTS response missing audio artifact")
            audio_bytes, content_type = gw.download_run_artifact_content(
                run_id=run_id,
                artifact_id=aid,
                max_bytes=25_000_000,
            )
            return self._play_audio_bytes(audio_bytes, content_type, callback=callback)
        except Exception as e:
            warnings.warn(f"#FALLBACK: gateway TTS failed: {e}")
            return False
        finally:
            try:
                cfg = getattr(gw, "_cfg", None)
                if cfg is not None and old_timeout is not None:
                    cfg.timeout_s = old_timeout
            except Exception:
                pass

    def pause(self) -> bool:
        """Pause current speech when supported by the local player."""
        with self._state_lock:
            if self._paused:
                return True
        proc = self._play_proc
        if proc is None:
            with self._state_lock:
                should_wait = bool(self._speaking)
            if should_wait:
                try:
                    self._play_ready.wait(timeout=0.35)
                except Exception:
                    pass
                proc = self._play_proc
        if not self._pause_playback_proc(proc):
            warnings.warn("#FALLBACK: gateway TTS pause not supported; no pausable playback")
            return False
        with self._state_lock:
            self._paused = True
            self._speaking = False
        self._meter_pause.set()
        # Audio is paused; resume STT for voice modes that support it.
        self._tts_gate_end()
        return True

    def resume(self) -> bool:
        """Resume current speech when supported by the local player."""
        with self._state_lock:
            if not self._paused:
                return False
        proc = self._play_proc
        if not self._resume_playback_proc(proc):
            warnings.warn("#FALLBACK: gateway TTS resume not supported; no paused playback")
            return False
        with self._state_lock:
            self._paused = False
            self._speaking = True
        self._meter_pause.clear()
        # Audio resumed; suppress STT again while speaking.
        self._tts_gate_start()
        return True

    def is_paused(self) -> bool:
        self._sync_playback_state()
        return bool(self._paused)

    def is_speaking(self) -> bool:
        self._sync_playback_state()
        return bool(self._speaking)

    def get_state(self) -> str:
        """Return current TTS state."""
        self._sync_playback_state()
        with self._state_lock:
            if self._paused:
                return "paused"
            if self._speaking:
                return "speaking"
            return "idle"

    def stop(self) -> None:
        """Stop current speech."""
        self.stop_speaking()

    def stop_speaking(self) -> None:
        """Stop any active playback."""
        self._stop_meter()
        proc = self._play_proc
        if proc is None:
            with self._state_lock:
                self._speaking = False
                self._paused = False
            try:
                self._play_ready.set()
            except Exception:
                pass
            try:
                self._meter_pause.clear()
            except Exception:
                pass
            self._emit_audio_meter(0.0)
            self._tts_gate_end()
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                except Exception:
                    proc.kill()
        except Exception:
            pass
        self._play_proc = None
        try:
            self._play_ready.set()
        except Exception:
            pass
        with self._state_lock:
            self._speaking = False
            self._paused = False
        self._emit_audio_meter(0.0)
        self._tts_gate_end()

    def _sync_playback_state(self) -> None:
        proc = self._play_proc
        if proc is None:
            return
        try:
            if proc.poll() is None:
                return
        except Exception:
            return
        self._play_proc = None
        with self._state_lock:
            self._speaking = False
            self._paused = False
        try:
            self._meter_pause.clear()
        except Exception:
            pass
        try:
            self._play_ready.set()
        except Exception:
            pass

    def cleanup(self) -> None:
        """Best-effort cleanup."""
        try:
            self.stop_listening()
        except Exception:
            pass
        try:
            self.stop_speaking()
        except Exception:
            pass

    def _play_audio_bytes(self, audio_bytes: bytes, content_type: str, *, callback: Optional[Callable]) -> bool:
        if not isinstance(audio_bytes, (bytes, bytearray)) or not audio_bytes:
            return False
        cache_dir = self._audio_cache_dir()
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        ext = ".wav"
        ctype = str(content_type or "").lower()
        if "mpeg" in ctype or "mp3" in ctype:
            ext = ".mp3"
        elif "wav" in ctype:
            ext = ".wav"
        name = f"tts_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}{ext}"
        path = cache_dir / name
        try:
            path.write_bytes(bytes(audio_bytes))
        except Exception as e:
            warnings.warn(f"#FALLBACK: failed to write TTS audio: {e}")
            return False

        self.stop_speaking()
        levels, step_s = self._extract_audio_levels(audio_bytes, content_type)
        try:
            self._meter_pause.clear()
        except Exception:
            pass
        try:
            self._play_ready.clear()
        except Exception:
            pass

        def _play() -> None:
            proc_or_cb = None
            try:
                with self._state_lock:
                    self._speaking = True
                    self._paused = False
                self._tts_gate_start()
                if self.on_speech_start:
                    self.on_speech_start()
                self._start_meter(levels, step_s)
                proc_or_cb = self._spawn_player(path)
                if isinstance(proc_or_cb, subprocess.Popen):
                    self._play_proc = proc_or_cb
                try:
                    self._play_ready.set()
                except Exception:
                    pass
                if self._play_proc is not None:
                    self._play_proc.wait()
                elif callable(proc_or_cb):
                    proc_or_cb()
                else:
                    raise RuntimeError("No audio player available")
            except Exception as e:
                warnings.warn(f"#FALLBACK: audio playback failed: {e}")
            finally:
                self._play_proc = None
                try:
                    self._play_ready.set()
                except Exception:
                    pass
                self._stop_meter()
                self._emit_audio_meter(0.0)
                with self._state_lock:
                    self._speaking = False
                    self._paused = False
                self._tts_gate_end()
                if self.on_speech_end:
                    self.on_speech_end()
                if callback:
                    try:
                        callback()
                    except Exception:
                        pass
                try:
                    if path.exists():
                        path.unlink()
                except Exception:
                    pass

        threading.Thread(target=_play, daemon=True).start()
        return True

    def _spawn_player(self, path: Path):
        if sys.platform == "darwin":
            if not shutil.which("afplay"):
                return None
            return subprocess.Popen(["afplay", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if sys.platform.startswith("win"):
            try:
                import winsound

                return lambda: winsound.PlaySound(str(path), winsound.SND_FILENAME)  # type: ignore[misc]
            except Exception:
                return None
        if shutil.which("paplay"):
            return subprocess.Popen(["paplay", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if shutil.which("aplay"):
            return subprocess.Popen(["aplay", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if shutil.which("ffplay"):
            return subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if shutil.which("mpg123"):
            return subprocess.Popen(["mpg123", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return None

    def _emit_audio_meter(self, level) -> None:
        cb = self._audio_meter_callback
        if cb is None:
            return
        try:
            cb(level)
        except Exception:
            pass

    def _start_meter(self, levels: list, step_s: float) -> None:
        self._stop_meter()
        if not self._audio_meter_callback or not levels or step_s <= 0:
            return
        self._meter_stop.clear()
        self._meter_pause.clear()

        def _run() -> None:
            for lvl in levels:
                if self._meter_stop.is_set():
                    return
                while self._meter_pause.is_set() and not self._meter_stop.is_set():
                    time.sleep(0.05)
                if self._meter_stop.is_set():
                    return
                self._emit_audio_meter(lvl)
                self._meter_stop.wait(timeout=step_s)
            self._emit_audio_meter(0.0)

        self._meter_thread = threading.Thread(target=_run, daemon=True)
        self._meter_thread.start()

    def _stop_meter(self) -> None:
        try:
            self._meter_stop.set()
        except Exception:
            pass
        try:
            self._meter_pause.clear()
        except Exception:
            pass
        self._meter_thread = None

    def _pause_playback_proc(self, proc: Optional[subprocess.Popen]) -> bool:
        if proc is None:
            return False
        try:
            if proc.poll() is not None:
                return False
        except Exception:
            return False
        sig = getattr(signal, "SIGSTOP", None)
        if sig is None:
            return False
        try:
            proc.send_signal(sig)
        except Exception:
            return False
        return True

    def _resume_playback_proc(self, proc: Optional[subprocess.Popen]) -> bool:
        if proc is None:
            return False
        try:
            if proc.poll() is not None:
                return False
        except Exception:
            return False
        sig = getattr(signal, "SIGCONT", None)
        if sig is None:
            return False
        try:
            proc.send_signal(sig)
        except Exception:
            return False
        return True

    def _extract_audio_levels(self, audio_bytes: bytes, content_type: str) -> Tuple[list, float]:
        ctype = str(content_type or "").lower()
        if "wav" not in ctype:
            if self._audio_meter_callback and not self._audio_meter_warned:
                warnings.warn("#FALLBACK: voice meter unavailable; non-wav TTS payload")
                self._audio_meter_warned = True
            return [], 0.0
        try:
            import io
            import wave
            import audioop
            try:
                import numpy as np
            except Exception:
                np = None  # type: ignore[assignment]

            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                n_frames = int(wf.getnframes())
                if n_frames <= 0:
                    return [], 0.0
                framerate = float(wf.getframerate() or 0)
                sampwidth = int(wf.getsampwidth() or 0)
                channels = int(wf.getnchannels() or 1)
                if framerate <= 0 or sampwidth <= 0:
                    return [], 0.0
                chunk_frames = max(1, int(framerate / 30))
                step_s = float(chunk_frames / framerate)

                if np is None or sampwidth not in {1, 2, 4}:
                    if self._audio_meter_callback and not self._audio_meter_warned:
                        reason = "numpy missing" if np is None else f"unsupported sample width {sampwidth}"
                        warnings.warn(f"#FALLBACK: voice meter bands unavailable; {reason}")
                        self._audio_meter_warned = True
                    max_amp = float(2 ** (8 * sampwidth - 1))
                    levels: list[float] = []
                    for _ in range(0, n_frames, chunk_frames):
                        frames = wf.readframes(chunk_frames)
                        if not frames:
                            break
                        rms = audioop.rms(frames, sampwidth)
                        level = min(1.0, max(0.0, (float(rms) / max_amp) * 2.0))
                        levels.append(level)
                    return levels, step_s

                levels: list[list[float]] = []
                max_amp = float(2 ** (8 * sampwidth - 1))
                for _ in range(0, n_frames, chunk_frames):
                    frames = wf.readframes(chunk_frames)
                    if not frames:
                        break
                    samples = self._frames_to_float32(frames, sampwidth, channels, np)
                    if samples is None or samples.size <= 0:
                        continue
                    samples = samples - float(np.mean(samples))
                    rms = float(np.sqrt(np.mean(np.square(samples))))
                    bands = self._compute_band_levels(samples, int(framerate), rms, np)
                    if bands:
                        levels.append(bands)
                    else:
                        if self._audio_meter_callback and not self._audio_meter_warned:
                            warnings.warn("#FALLBACK: voice meter bands unavailable; FFT analysis failed")
                            self._audio_meter_warned = True
                        level = min(1.0, max(0.0, (rms / max_amp) * 2.0))
                        levels.append([level] * 5)
                return levels, step_s
        except Exception:
            if self._audio_meter_callback and not self._audio_meter_warned:
                warnings.warn("#FALLBACK: voice meter unavailable; failed to decode TTS audio")
                self._audio_meter_warned = True
            return [], 0.0

    def _frames_to_float32(self, frames: bytes, sampwidth: int, channels: int, np) -> Optional["np.ndarray"]:
        if sampwidth == 1:
            data = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
            data = (data - 128.0) / 128.0
        elif sampwidth == 2:
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            data = data / 32768.0
        elif sampwidth == 4:
            data = np.frombuffer(frames, dtype=np.int32).astype(np.float32)
            data = data / 2147483648.0
        else:
            return None
        if channels > 1:
            try:
                data = data.reshape(-1, channels).mean(axis=1)
            except Exception:
                return None
        return data

    def _compute_band_levels(self, samples, sample_rate: int, rms: float, np) -> list[float]:
        """Compute log-spaced band levels for a short audio slice."""
        import math
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

    def _audio_player_available(self) -> bool:
        if sys.platform == "darwin":
            return bool(shutil.which("afplay"))
        if sys.platform.startswith("win"):
            try:
                import winsound  # noqa: F401
                return True
            except Exception:
                return False
        return bool(shutil.which("paplay") or shutil.which("aplay") or shutil.which("ffplay") or shutil.which("mpg123"))

    def _audio_cache_dir(self) -> Path:
        base = Path(getattr(self._llm_manager, "data_dir", Path.home() / ".abstractassistant"))
        return base / "gateway_audio"

    def _gateway_client(self):
        if self._llm_manager is None:
            raise RuntimeError("Gateway client not available")
        gw = self._llm_manager.gateway_client()
        if gw is None:
            raise RuntimeError("Gateway client not available")
        return gw

    def _session_id(self) -> str:
        sid = str(getattr(self._llm_manager, "active_session_id", "") or "").strip()
        if not sid:
            raise RuntimeError("gateway voice requires session_id")
        return sid

    def _session_run_id(self) -> str:
        return str(session_memory_owner_run_id(self._session_id()))
