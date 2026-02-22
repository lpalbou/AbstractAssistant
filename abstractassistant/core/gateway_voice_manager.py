"""
Gateway voice manager for AbstractAssistant.

Provides TTS/STT via AbstractGateway with local OS playback/recording.
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

    def __init__(self, *, llm_manager, debug_mode: bool = False, chunk_s: float = 4.0) -> None:
        self._llm_manager = llm_manager
        self.debug_mode = bool(debug_mode)
        self._chunk_s = max(1.0, float(chunk_s))

        self.on_speech_start = None
        self.on_speech_end = None

        self._listening = False
        self._listen_thread: Optional[threading.Thread] = None
        self._listen_stop = threading.Event()

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

    def is_available(self) -> bool:
        """Return True if any gateway voice capability is available."""
        return bool(self.supports_tts() or self.supports_stt())

    def supports_tts(self) -> bool:
        """Return True when a local audio player is available."""
        return bool(self._audio_player_available())

    def supports_stt(self) -> bool:
        """Return True when a local audio recorder is available."""
        return bool(self._audio_recorder_available())

    def set_voice_mode(self, mode: str) -> None:
        """No-op for gateway voice (kept for interface parity)."""
        _ = str(mode or "")

    def set_audio_meter_callback(self, callback: Optional[Callable[[float | list[float]], None]]) -> None:
        """Set a callback for audio meter updates (0..1 or per-band)."""
        self._audio_meter_callback = callback

    def listen(self, on_transcription: Callable[[str], None], on_stop: Callable[[], None] | None = None) -> bool:
        """Start the STT listening loop on a background thread."""
        if not self.supports_stt():
            warnings.warn("#FALLBACK: gateway STT unavailable; missing local recorder")
            raise RuntimeError("Gateway STT unavailable")
        if self._listening:
            return True
        self._listening = True
        self._listen_stop.clear()
        self._listen_thread = threading.Thread(
            target=self._listen_loop,
            args=(on_transcription, on_stop),
            daemon=True,
        )
        self._listen_thread.start()
        return True

    def stop_listening(self) -> None:
        """Stop the STT listening loop."""
        self._listening = False
        self._listen_stop.set()

    def is_listening(self) -> bool:
        return bool(self._listening)

    def speak(self, text: str, speed: float = 1.0, callback: Optional[Callable] = None) -> bool:
        """Speak the given text via gateway TTS."""
        _ = float(speed or 1.0)
        raw = str(text or "").strip()
        if not raw:
            return False
        if not self.supports_tts():
            warnings.warn("#FALLBACK: gateway TTS unavailable; missing local player")
            return False
        try:
            gw = self._gateway_client()
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

    def _listen_loop(self, on_transcription: Callable[[str], None], on_stop: Optional[Callable[[], None]]) -> None:
        while self._listening and not self._listen_stop.is_set():
            try:
                path = self._record_audio_chunk(self._chunk_s)
                if path is None:
                    time.sleep(0.2)
                    continue
                text = self._transcribe_audio_file(path)
                if not text:
                    continue
                normalized = text.strip().lower()
                if normalized in {"stop", "stop listening", "stop voice", "stop voice mode"}:
                    if on_stop is not None:
                        on_stop()
                    continue
                on_transcription(text)
            except Exception as e:
                warnings.warn(f"#FALLBACK: gateway STT failed: {e}")
                time.sleep(0.4)

    def _record_audio_chunk(self, duration_s: float) -> Optional[Path]:
        if duration_s <= 0:
            return None
        if not self._audio_recorder_available():
            raise RuntimeError("No audio recorder available for gateway STT")

        path = self._audio_cache_dir() / f"stt_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.wav"
        cmd = self._record_command(path, duration_s)
        if not cmd:
            raise RuntimeError("Gateway STT recording not supported on this platform")

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            warnings.warn(f"#FALLBACK: recording failed: {e}")
            return None

        try:
            if path.exists() and path.stat().st_size > 512:
                return path
        except Exception:
            return None
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        return None

    def _transcribe_audio_file(self, path: Path) -> str:
        gw = self._gateway_client()
        run_id = self._session_run_id()
        sid = self._session_id()
        timeout_prev = None
        try:
            cfg = getattr(gw, "_cfg", None)
            if cfg is not None:
                timeout_prev = float(getattr(cfg, "timeout_s", 0) or 0)
                if timeout_prev and timeout_prev < 120.0:
                    cfg.timeout_s = 120.0
        except Exception:
            timeout_prev = None
        try:
            attachment = gw.attachments_upload(
                session_id=sid,
                file_path=str(path),
                filename=path.name,
                content_type="audio/wav",
            )
            audio_ref = attachment
            if isinstance(attachment, dict) and isinstance(attachment.get("attachment"), dict):
                audio_ref = attachment.get("attachment")
            if not isinstance(audio_ref, dict) or not str(audio_ref.get("$artifact") or "").strip():
                raise RuntimeError("audio_transcribe requires an artifact ref dict")
            res = gw.audio_transcribe(run_id=run_id, audio_artifact=audio_ref, request_id=str(uuid.uuid4()))
            return str(res.get("text") or "").strip() if isinstance(res, dict) else ""
        finally:
            try:
                cfg = getattr(gw, "_cfg", None)
                if cfg is not None and timeout_prev is not None:
                    cfg.timeout_s = timeout_prev
            except Exception:
                pass
            try:
                if path.exists():
                    path.unlink()
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
                if isinstance(proc_or_cb, subprocess.Popen):
                    proc_or_cb.wait()
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

    def _sleep_meter(self, duration_s: float) -> None:
        remaining = max(0.0, float(duration_s))
        while remaining > 0:
            if self._meter_stop.is_set():
                return
            if self._meter_pause.is_set():
                time.sleep(0.05)
                continue
            chunk = min(0.05, remaining)
            time.sleep(chunk)
            remaining -= chunk

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
                self._sleep_meter(step_s)
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

    def _audio_recorder_available(self) -> bool:
        if sys.platform == "darwin":
            return bool(shutil.which("afrecord"))
        if sys.platform.startswith("linux"):
            return bool(shutil.which("arecord") or shutil.which("ffmpeg"))
        return False

    def _record_command(self, path: Path, duration_s: float) -> Tuple[str, ...] | None:
        duration = str(max(1, float(duration_s)))
        if sys.platform == "darwin":
            return (
                "afrecord",
                "-q",
                "-d",
                duration,
                "-f",
                "WAVE",
                "-r",
                "16000",
                "-c",
                "1",
                str(path),
            )
        if sys.platform.startswith("linux") and shutil.which("arecord"):
            return ("arecord", "-q", "-t", "wav", "-d", duration, "-r", "16000", "-c", "1", str(path))
        if sys.platform.startswith("linux") and shutil.which("ffmpeg"):
            return ("ffmpeg", "-y", "-f", "alsa", "-i", "default", "-t", duration, "-ac", "1", "-ar", "16000", str(path))
        return None

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
