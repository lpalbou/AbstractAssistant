"""
Gateway voice manager for AbstractAssistant.

TTS: gateway /voice/tts/stream when advertised, otherwise gateway /voice/tts → local playback.
STT: AbstractVoice VoiceRecognizer (mic + VAD) → GatewaySTTAdapter → gateway /audio/transcribe.
"""

from __future__ import annotations

import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import warnings
import os
import io
import base64
from pathlib import Path
from typing import Callable, Optional, Tuple

from abstractruntime.integrations.abstractcore.session_attachments import session_memory_owner_run_id

from ..gateway import get_cached_assistant_capabilities


class GatewayVoiceManager:
    """Gateway-backed voice manager with a VoiceManager-compatible interface."""

    def __init__(self, *, llm_manager, debug_mode: bool = False) -> None:
        self._llm_manager = llm_manager
        self.debug_mode = bool(debug_mode)

        self.on_speech_start = None
        self.on_speech_end = None
        # Visible failure channel. `warnings.warn` is invisible in a GUI: on
        # 2026-08-02 a speaker click on a 3,549-char reply spent 0.5 s having
        # its pinned model rejected (404), 120 s timing out the retried stream
        # and 120 s timing out the artifact lane, emitted three #FALLBACK
        # warnings nobody could see, and told the user NOTHING — the card just
        # went back to idle. Every abort now travels this callback so the UI
        # can say why. Fires at most once per speak() dispatch.
        self.on_speech_error: Optional[Callable[[str], None]] = None
        self._speech_failure_causes: list[str] = []
        self._speech_failure_reported = False

        self._listening = False
        self._recognizer = None

        self._speaking = False
        self._paused = False
        self._play_proc: Optional[subprocess.Popen] = None
        self._inprocess_player = None
        # "" = follow the system default output (see set_output_device).
        self._output_device_spec = ""
        self._playback_backend = "none"
        self._stream_id = ""
        self._stream_active = False
        self._stream_pause_gate: Optional[threading.Event] = None
        self._stream_stop_gate: Optional[threading.Event] = None
        # Server-side TTS child run id for the active stream (captured from the
        # stream's opening event). Stopping a stream must CANCEL this run on
        # the gateway, not just abandon the local read: an abandoned stream
        # keeps synthesizing under the gateway's per-voice lock, so the next
        # speak() queues behind its full remaining synthesis — the head-of-line
        # stall that turns impatient re-clicks into minutes of dead spinner
        # (2026-07-28 adversarial audit).
        self._stream_child_run_id = ""
        # Serializes speak() dispatch (stop previous generation + mint the new
        # one atomically) so two rapid speak() calls cannot interleave and
        # leave an unstoppable generation behind.
        self._dispatch_lock = threading.Lock()
        self._stream_fallback_warned = False
        # Reasons the streaming lane was declined outright, warned once each.
        self._stream_lane_declined_reasons: set[str] = set()
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
        # Voice latency vs quality: "low"|"standard"|"high" → gateway TTS
        # quality_preset (fewer diffusion steps = faster first audio). Empty
        # means "don't send it" (gateway default).
        self._quality_preset = ""
        self._quality_preset_warned = False

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
        """Return True when Gateway TTS and a local audio player are available."""
        return bool(self._gateway_tts_available() and self._audio_player_available())

    def output_device_label(self) -> str:
        """Name of the device speech will actually play on.

        NOT `sd.query_devices(kind="output")`: PortAudio resolves "the default" once,
        at initialization, so in a long-running app that answer is the default from
        launch — it kept naming the built-in speakers after the user had switched to
        AR glasses. This resolves the CHOSEN device, or the system's live default when
        none is pinned (see abstractvoice.tts.audio_devices).
        """
        try:
            from abstractvoice.tts.audio_devices import describe_device_spec

            return describe_device_spec(self.output_device_spec() or None)
        except Exception:
            pass
        try:
            import sounddevice as sd  # type: ignore

            info = sd.query_devices(kind="output")
            if isinstance(info, dict):
                return str(info.get("name") or "").strip()
            return str(getattr(info, "name", "") or "").strip()
        except Exception:
            return ""

    def output_volume_state(self) -> tuple[Optional[int], Optional[bool]]:
        """(volume 0-100, muted) of the system output, best effort.

        The 2026-07-28 three-way audit cleared every software layer while the
        machine's output volume sat at 6/100 — playback at that level is
        indistinguishable from a hang. None/None when the platform offers no
        cheap query (non-macOS, or osascript unavailable)."""
        if sys.platform != "darwin":
            return None, None
        try:
            proc = subprocess.run(
                ["osascript", "-e", "get volume settings"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            text = str(proc.stdout or "")
            volume: Optional[int] = None
            muted: Optional[bool] = None
            match = re.search(r"output volume:\s*(\d+)", text)
            if match:
                volume = max(0, min(100, int(match.group(1))))
            match = re.search(r"output muted:\s*(true|false)", text)
            if match:
                muted = match.group(1) == "true"
            return volume, muted
        except Exception:
            return None, None

    def supports_stt(self) -> bool:
        """Return True when Gateway STT and local mic/VAD infrastructure are available."""
        if not self._gateway_stt_available():
            return False
        if not self._stt_upload_content_type():
            return False
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

    def _can_refresh_audio_devices(self) -> bool:
        """Whether PortAudio may be re-initialized right now.

        `_listening` alone is NOT a sufficient gate: `stop_listening()` clears it BEFORE
        `rec.stop()` closes the microphone stream, so a refresh inside that window
        invalidates a live InputStream (PaErrorCode -9988, measured). The recognizer
        object survives until after the stream is closed, so it closes the window.
        """
        if bool(getattr(self, "_listening", False)):
            return False
        return getattr(self, "_recognizer", None) is None

    def set_output_device(self, spec: Optional[str]) -> None:
        """Choose the speaker for spoken replies. ""/None follows the system default.

        Applies to the live player immediately, so a choice made in Settings is
        audible on the next sentence rather than after a restart.
        """
        value = str(spec or "").strip()
        self._output_device_spec = value
        player = self._inprocess_player
        if player is not None:
            try:
                player.set_output_device(value or None)
            except Exception:
                pass

    def output_device_spec(self) -> str:
        return str(getattr(self, "_output_device_spec", "") or "")

    def available_output_devices(self) -> list:
        """Every output device the system can see right now (for the picker)."""
        try:
            from abstractvoice.tts.audio_devices import list_output_devices

            return list(list_output_devices())
        except Exception:
            return []

    def play_test_tone(self, spec: Optional[str] = None, *, seconds: float = 0.6) -> str:
        """Play a short tone on `spec` (default: the configured device).

        Returns "" on success or a sentence naming what went wrong. This is the only
        honest answer to "which speaker will my replies come out of": the device the
        stream actually opens on, proven by hearing it.
        """
        try:
            import numpy as np

            from abstractvoice.tts import NonBlockingAudioPlayer
        except Exception as exc:
            return f"Audio playback is unavailable ({self._exception_reason(exc)})."

        target = spec if spec is not None else self.output_device_spec()
        problems: list[str] = []
        player = NonBlockingAudioPlayer(sample_rate=48000, debug_mode=self.debug_mode)
        player.on_output_device_problem = problems.append
        try:
            player.set_output_device(str(target or "").strip() or None)
            player.start_stream()
            duration = max(0.2, min(2.0, float(seconds)))
            t = np.linspace(0, duration, int(48000 * duration), endpoint=False)
            envelope = np.minimum(1.0, np.minimum(t * 40, (duration - t) * 40))
            tone = (0.18 * np.sin(2 * np.pi * 660 * t) * envelope).astype(np.float32)
            player.play_audio(tone, sample_rate=48000)
            time.sleep(duration + 0.25)
        except Exception as exc:
            return problems[0] if problems else f"Could not play on this device ({self._exception_reason(exc)})."
        finally:
            try:
                player.stop_stream()
            except Exception:
                pass
        return problems[0] if problems else ""

    def set_quality_preset(self, preset: str) -> None:
        """Set the TTS quality/latency preset (low|standard|high)."""
        value = str(preset or "").strip().lower()
        self._quality_preset = value if value in {"low", "standard", "high"} else ""

    def _resolved_quality_preset(self) -> Optional[str]:
        """Return the preset to send, gated on advertised gateway support."""
        preset = str(getattr(self, "_quality_preset", "") or "").strip().lower()
        if not preset:
            return None
        try:
            controls = self._assistant_capabilities().tts().get("controls")
            supported = bool(
                isinstance(controls, dict)
                and isinstance(controls.get("quality_preset"), dict)
                and controls["quality_preset"].get("supported")
            )
        except Exception:
            supported = False
        if not supported:
            if not self._quality_preset_warned:
                self._quality_preset_warned = True
                warnings.warn("#FALLBACK: gateway does not advertise TTS quality_preset; ignoring voice-quality preference")
            return None
        return preset

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
            content_type_fn=self._stt_upload_content_type,
            max_upload_bytes_fn=self._stt_max_upload_bytes,
            stt_model_fn=self._selected_stt_model,
            stt_provider_fn=self._selected_stt_provider,
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

    def _start_stream_control(self) -> Tuple[str, threading.Event, threading.Event]:
        pause_gate = threading.Event()
        pause_gate.set()
        stop_gate = threading.Event()
        stream_id = uuid.uuid4().hex
        with self._state_lock:
            self._stream_id = stream_id
            self._stream_active = True
            self._stream_pause_gate = pause_gate
            self._stream_stop_gate = stop_gate
            self._stream_child_run_id = ""
            self._paused = False
        return stream_id, pause_gate, stop_gate

    def _record_stream_child_run(self, stream_id: str, child_run_id: str) -> None:
        """Remember the gateway TTS child run id for the active stream so a
        stop can cancel server-side synthesis (only if it is still current)."""
        child = str(child_run_id or "").strip()
        if not child:
            return
        with self._state_lock:
            if str(self._stream_id or "") == str(stream_id or ""):
                self._stream_child_run_id = child

    def _cancel_stream_run_async(self, child_run_id: str) -> None:
        """Best-effort server-side cancel of an abandoned/superseded TTS run.

        Fire-and-forget on a daemon thread: stop_speaking() runs on the GUI
        thread too, so the network call must never block it.

        This is the correct client ACTION (tell the server to stop the run we
        abandoned) but is NOT sufficient on its own: live-verified 2026-07-28
        that `cancel_run` flips the run's status to cancelled quickly yet does
        NOT stop the in-flight TTS synthesis feeder or release the gateway's
        per-voice lock — the abandoned synthesis runs to completion and the
        next speak still queues behind it. Freeing the lock requires the
        server-side fix (gateway disconnect/cancel must trigger the runtime
        synthesis cancel_event; per-segment lock granularity). Filed with the
        gateway. Kept here because it is forward-compatible (it becomes the
        actual mitigation the moment the server honors cancel) and it already
        stops zombie runs from lingering in the run store."""
        child = str(child_run_id or "").strip()
        if not child:
            return

        def _worker() -> None:
            try:
                gw = self._gateway_client()
                if gw is not None and hasattr(gw, "cancel_run"):
                    gw.cancel_run(run_id=child, reason="assistant: TTS stopped/superseded")
            except Exception:
                pass

        try:
            threading.Thread(target=_worker, name="gateway-tts-cancel", daemon=True).start()
        except Exception:
            pass

    def _stop_stream_control(self) -> None:
        with self._state_lock:
            pause_gate = self._stream_pause_gate
            stop_gate = self._stream_stop_gate
            child_run_id = str(self._stream_child_run_id or "")
            self._stream_id = ""
            self._stream_active = False
            self._stream_pause_gate = None
            self._stream_stop_gate = None
            self._stream_child_run_id = ""
        if stop_gate is not None:
            try:
                stop_gate.set()
            except Exception:
                pass
        if pause_gate is not None:
            try:
                pause_gate.set()
            except Exception:
                pass
        # Cancel the abandoned server stream so it stops synthesizing and
        # releases the per-voice lock (the head-of-line-blocking fix).
        self._cancel_stream_run_async(child_run_id)

    def _clear_stream_control(self, stream_id: str) -> bool:
        with self._state_lock:
            if str(self._stream_id or "") != str(stream_id or ""):
                return False
            self._stream_id = ""
            self._stream_active = False
            self._stream_pause_gate = None
            self._stream_stop_gate = None
            self._stream_child_run_id = ""
            return True

    def _wait_for_stream_resume(self, pause_gate: threading.Event, stop_gate: threading.Event) -> bool:
        while not stop_gate.is_set():
            try:
                if pause_gate.wait(timeout=0.05):
                    return True
            except Exception:
                return False
        return False

    def _speak_gateway_stream(
        self,
        *,
        gw,
        run_id: str,
        text: str,
        provider: Optional[str],
        voice: Optional[str],
        profile: Optional[str],
        fmt: str,
        request_id: str,
        model: Optional[str],
        callback: Optional[Callable],
        stream_id: str,
        pause_gate: threading.Event,
        stop_gate: threading.Event,
    ) -> Optional[bool]:
        """Try the gateway streaming TTS leg for an already-minted generation.

        Returns None when streaming is unavailable (caller falls back to the
        artifact leg with the same generation gates); otherwise runs the
        stream inline on the caller's worker thread and returns its outcome.
        """
        # Every `return None` below concedes the whole-message artifact lane
        # for the rest of this speak(). That is the operator-visible symptom
        # ("it computes the full voice instead of streaming"), so it is said
        # once per process rather than inferred from silence.
        def _no_stream_lane(reason: str) -> None:
            # Deduped per REASON, not globally: a one-shot flag shared with the
            # missing-player warning would hide a later, different cause.
            seen = getattr(self, "_stream_lane_declined_reasons", None)
            if seen is None:
                seen = set()
                self._stream_lane_declined_reasons = seen
            if reason not in seen:
                seen.add(reason)
                warnings.warn(
                    f"#FALLBACK: not using the gateway TTS streaming lane ({reason}); "
                    "falling back to single-shot artifact TTS — for a long answer nothing "
                    "is audible until the whole message has been synthesized"
                )
            return None

        if not self._gateway_tts_streaming_available():
            return _no_stream_lane("the gateway does not advertise streaming TTS")
        if str(fmt or "").strip().lower() not in {"wav", "wave"}:
            return _no_stream_lane(f"the negotiated audio format is {fmt!r}, and only wav can be streamed")
        stream_fn = getattr(gw, "voice_tts_stream", None)
        if not callable(stream_fn):
            return _no_stream_lane("this gateway client exposes no voice_tts_stream")
        if self._ensure_inprocess_audio_player() is None:
            # Streaming IS advertised by the gateway but we cannot consume it:
            # this silently degrades first-audio latency from seconds to the
            # whole-message synthesis time, so say it loudly (once).
            if not self._stream_fallback_warned:
                self._stream_fallback_warned = True
                warnings.warn(
                    "#FALLBACK: gateway streaming TTS is advertised but the in-process "
                    "audio player is unavailable (sounddevice missing — install "
                    "'abstractassistant[voice]'); falling back to single-shot artifact "
                    "TTS (slow first audio for long texts)"
                )
            return None

        return self._run_gateway_stream_playback(
            stream_id=stream_id,
            pause_gate=pause_gate,
            stop_gate=stop_gate,
            gw=gw,
            stream_fn=stream_fn,
            run_id=run_id,
            text=text,
            provider=provider,
            voice=voice,
            profile=profile,
            request_id=request_id,
            model=model,
            callback=callback,
        )

    def _run_gateway_stream_playback(
        self,
        *,
        stream_id: str,
        pause_gate: threading.Event,
        stop_gate: threading.Event,
        gw,
        stream_fn,
        run_id: str,
        text: str,
        provider: Optional[str],
        voice: Optional[str],
        profile: Optional[str],
        request_id: str,
        model: Optional[str],
        callback: Optional[Callable],
        allow_unpinned_retry: bool = True,
    ) -> bool:
        audio_started = False
        stream_opened = False
        player = None
        playback_drained = threading.Event()
        queued_audio_s = 0.0
        # Exactly-once completion accounting: True when a terminal signal
        # (callback + on_speech_end) was fired or ownership was handed to a
        # playback lifecycle that fires it. Cancelled/failed paths that reach
        # the finally block without ownership fire the completion there —
        # a swallowed completion leaves the UI stuck on "speaking".
        completion_owned = False
        pinned = any(str(p or "").strip() for p in (provider, voice, profile, model))

        def _retry_stream_unpinned(reason: str) -> Optional[bool]:
            """Re-run the stream leg with every pin dropped (pre-audio only).

            A pin the stream route cannot resolve (see `_selected_tts_model`)
            fails the WHOLE stream leg before a single sample, and the artifact
            lane then synthesizes the entire message before any sound. One
            unpinned retry costs a round trip and keeps first audio in the
            ~1 s range; it runs only when pins were actually sent, only before
            any audio played, and only once per speak().
            """
            nonlocal completion_owned
            if not allow_unpinned_retry or not pinned or stop_gate.is_set():
                return None
            warnings.warn(
                f"#FALLBACK: gateway TTS stream rejected the request pins "
                f"(provider={provider!r} model={model!r} voice={voice!r} profile={profile!r}): "
                f"{reason}; retrying the stream with gateway defaults"
            )
            result = self._run_gateway_stream_playback(
                stream_id=stream_id,
                pause_gate=pause_gate,
                stop_gate=stop_gate,
                gw=gw,
                stream_fn=stream_fn,
                run_id=run_id,
                text=text,
                provider=None,
                voice=None,
                profile=None,
                # A fresh request id: the rejected attempt already burned this
                # one server-side, and an idempotency-keyed gateway would hand
                # back the same rejection.
                request_id=str(uuid.uuid4()),
                model=None,
                callback=callback,
                allow_unpinned_retry=False,
            )
            # The nested leg always settles completion (its own finally fires
            # it when nothing else did), so this frame must not fire it again.
            completion_owned = True
            return bool(result)

        def _artifact_fallback(reason: str = "", *, retry_unpinned: bool = False) -> bool:
            nonlocal completion_owned
            # Keep the streaming cause even when the artifact lane later fails
            # for its own reason: "the stream was rejected AND the fallback
            # timed out" is the sentence the user needs.
            self._note_speech_failure(reason)
            if stop_gate.is_set():
                return False
            if retry_unpinned:
                retried = _retry_stream_unpinned(reason or "stream produced no audio")
                if retried is not None:
                    return retried
            # Loud by design: this is the silent degradation the operator sees
            # as "it computes the whole voice instead of streaming" — the
            # artifact lane cannot emit a sample before the LAST one is
            # synthesized (measured 2026-08-02: 17.5 s for 1,000 chars).
            warnings.warn(
                f"#FALLBACK: gateway TTS streaming produced no audio "
                f"({reason or 'unknown reason'}); using single-shot artifact synthesis for "
                f"{len(str(text or ''))} chars — nothing is audible until the whole message "
                "has been synthesized"
            )
            try:
                handed = self._speak_gateway_artifact(
                    gw=gw,
                    run_id=run_id,
                    text=text,
                    provider=provider,
                    voice=voice,
                    profile=profile,
                    fmt=self._preferred_tts_format(),
                    request_id=request_id,
                    model=model,
                    callback=callback,
                    stream_id=stream_id,
                    pause_gate=pause_gate,
                    stop_gate=stop_gate,
                )
            except Exception as e:
                detail = self._exception_reason(e)
                warnings.warn(f"#FALLBACK: gateway artifact TTS failed after streaming fallback: {detail}")
                self._note_speech_failure(f"the single-shot fallback failed too ({detail})")
                return False
            if handed:
                completion_owned = True
                return handed
            if not stop_gate.is_set():
                self._note_speech_failure(
                    "the single-shot fallback produced no playable audio"
                )
            return handed

        try:
            events = stream_fn(
                run_id=run_id,
                text=text,
                provider=provider,
                voice=voice,
                profile=profile,
                fmt="wav",
                request_id=request_id,
                model=model,
                quality_preset=getattr(self, "_active_quality_preset", None),
                timeout_s=120.0,
            )
            event_iter = iter(events)
            while not stop_gate.is_set():
                if not self._wait_for_stream_resume(pause_gate, stop_gate):
                    return False
                try:
                    event = next(event_iter)
                except StopIteration:
                    break
                if not self._wait_for_stream_resume(pause_gate, stop_gate):
                    return False
                if not isinstance(event, dict):
                    continue
                # Capture the server-side child run id as soon as any event
                # carries it, so a stop can cancel synthesis server-side.
                child = event.get("child_run_id")
                if isinstance(child, str) and child.strip():
                    self._record_stream_child_run(stream_id, child)
                event_type = str(event.get("type") or "").strip().lower()
                if event_type in {"runtime_start", "start"}:
                    stream_opened = True
                    continue
                if event_type == "audio":
                    raw = event.get("audio_b64")
                    if not isinstance(raw, str) or not raw.strip():
                        if audio_started:
                            # Mid-stream empty chunk: abort without a fallback
                            # (replaying delivered audio would duplicate it) —
                            # but never silently (2026-07-28 audit: this was a
                            # warning-free abort, invisible in any triage).
                            warnings.warn(
                                "#FALLBACK: gateway TTS stream sent an empty audio chunk mid-stream; stopping playback"
                            )
                            # Partial playback: the user heard the beginning and
                            # then it stopped. Say so — silence after a few
                            # seconds of speech reads as "it gave up on me".
                            self._report_speech_failure(
                                "the gateway stopped sending audio part-way through; "
                                "only the beginning of the message was spoken"
                            )
                            return False
                        return _artifact_fallback("first audio chunk was empty")
                    audio_bytes = base64.b64decode("".join(raw.strip().split()), validate=True)
                    if not audio_started:
                        if not self._begin_stream_playback():
                            return _artifact_fallback("stream playback could not start")
                        player = self._ensure_inprocess_audio_player()
                        if player is None:
                            return _artifact_fallback("in-process audio player unavailable")
                        self._configure_stream_playback_callbacks(player, playback_drained)
                        audio_started = True
                    if not self._wait_for_stream_resume(pause_gate, stop_gate):
                        return False
                    duration_s = self._queue_stream_wav_chunk(audio_bytes, playback_drained=playback_drained)
                    if duration_s is None:
                        return False
                    queued_audio_s += max(0.0, float(duration_s))
                    continue
                if event_type == "done":
                    if audio_started:
                        self._wait_for_stream_playback_drain(
                            player,
                            playback_drained,
                            timeout_s=max(5.0, queued_audio_s + 10.0),
                        )
                        completion_owned = self._finish_stream_playback(callback=callback, stream_id=stream_id)
                        return True
                    return _artifact_fallback("stream finished without sending any audio")
                if event_type in {"error", "cancelled"}:
                    if audio_started:
                        completion_owned = self._finish_stream_playback(callback=callback, stream_id=stream_id)
                        if not stop_gate.is_set():
                            detail = str(
                                event.get("error") or event.get("message") or event_type
                            ).strip()
                            self._report_speech_failure(
                                f"the gateway ended the speech stream part-way through "
                                f"({detail[:200] or event_type}); only part of the message was spoken"
                            )
                        return False
                    # Pre-audio server rejection: this is where an unresolvable
                    # pin lands (a 404 on the pinned model), so retry unpinned
                    # before conceding the whole-message artifact lane.
                    detail = str(event.get("error") or event.get("message") or event_type).strip()
                    return _artifact_fallback(
                        f"stream reported {event_type}: {detail[:200]}",
                        retry_unpinned=True,
                    )
            if stop_gate.is_set():
                return False
            if audio_started:
                self._wait_for_stream_playback_drain(
                    player,
                    playback_drained,
                    timeout_s=max(5.0, queued_audio_s + 10.0),
                )
                completion_owned = self._finish_stream_playback(callback=callback, stream_id=stream_id)
                return False
            return _artifact_fallback("stream ended without sending any audio")
        except Exception as e:
            detail = self._exception_reason(e)
            if audio_started:
                completion_owned = self._finish_stream_playback(callback=callback, stream_id=stream_id)
                warnings.warn(f"#FALLBACK: gateway streaming TTS failed after audio started: {detail}")
                if not stop_gate.is_set():
                    self._report_speech_failure(
                        f"the speech stream broke part-way through ({detail}); "
                        "only part of the message was spoken"
                    )
                return False
            return _artifact_fallback(f"stream transport failed: {detail}", retry_unpinned=True)
        finally:
            self._clear_stream_control(stream_id)
            if not completion_owned:
                # Terminal for this leg with nothing playing: the choke point
                # reports the recorded cause unless the user asked us to stop.
                self._fire_speech_completion(callback, cancelled=stop_gate.is_set())

    def speak(self, text: str, speed: float = 1.0, callback: Optional[Callable] = None) -> bool:
        """Speak the given text via gateway TTS (asynchronous dispatch).

        Returns True when the request was accepted and dispatched to a worker
        thread; the terminal outcome (played, failed, or cancelled) is
        signalled exactly once via `callback` and `on_speech_end`. Returns
        False only for immediate refusals (empty text, TTS unsupported).

        Synthesis + artifact download can take tens of seconds for long
        texts, and speak() is routinely called from the Qt GUI thread — the
        network work must never run on the caller's thread (2026-07-15
        speaker-button freeze fix).
        """
        _ = float(speed or 1.0)
        raw = str(text or "").strip()
        self._begin_speech_failure_tracking()
        if not raw:
            self._report_speech_failure(
                "there is nothing to read aloud in this message (no spoken text "
                "remains once markdown, code and links are removed)"
            )
            return False
        if not self.supports_tts():
            # Capability cache is prefetched at startup; this check stays
            # synchronous so callers get an immediate, honest refusal — and it
            # names WHICH side is missing (an unavailable gateway route and a
            # missing local audio backend need opposite user actions).
            self._report_speech_failure(self._tts_unsupported_reason())
            return False
        threading.Thread(
            target=self._speak_dispatch,
            kwargs={"text": raw, "callback": callback},
            daemon=True,
            name="gateway-tts-dispatch",
        ).start()
        return True

    def _speak_dispatch(self, *, text: str, callback: Optional[Callable]) -> None:
        """Worker-thread body: stop previous speech, then stream-or-artifact."""
        stream_id = ""
        try:
            with self._dispatch_lock:
                self.stop_speaking()
                # stop_speaking() muted the SUPERSEDED generation's reporting;
                # this dispatch owns the channel from here on.
                self._begin_speech_failure_tracking()
                stream_id, pause_gate, stop_gate = self._start_stream_control()
                # Resolve once per dispatch; speaks are single-active
                # (stop_speaking above), so a per-instance value is race-free.
                self._active_quality_preset = self._resolved_quality_preset()
            gw = self._gateway_client()
            run_id = self._session_run_id()
            selected_provider = self._selected_tts_provider()
            selected_voice = self._selected_tts_voice()
            selected_voice_mode = self._selected_tts_voice_mode()
            selected_model = self._selected_tts_model()
            preferred_format = self._preferred_tts_format()
            request_id = str(uuid.uuid4())
            common = {
                "gw": gw,
                "run_id": run_id,
                "text": text,
                "provider": selected_provider,
                "voice": selected_voice if selected_voice_mode == "clone" else None,
                "profile": selected_voice if selected_voice_mode != "clone" else None,
                "fmt": preferred_format,
                "request_id": request_id,
                "model": selected_model,
                "callback": callback,
                "stream_id": stream_id,
                "pause_gate": pause_gate,
                "stop_gate": stop_gate,
            }
            stream_result = self._speak_gateway_stream(**common)
            if stream_result is not None:
                # The stream leg owns completion accounting (including its
                # own artifact fallback).
                return
            handed = self._speak_gateway_artifact(**common)
            if not handed:
                self._clear_stream_control(stream_id)
                self._fire_speech_completion(
                    callback,
                    reason="the gateway returned speech audio but it could not be played locally",
                    cancelled=stop_gate.is_set(),
                )
        except Exception as e:
            detail = self._exception_reason(e)
            warnings.warn(f"#FALLBACK: gateway TTS failed: {detail}")
            if stream_id:
                self._clear_stream_control(stream_id)
            self._fire_speech_completion(
                callback,
                reason=self._speech_failure_reason
                or f"the gateway speech request failed ({detail})",
            )

    @staticmethod
    def _exception_reason(exc: BaseException) -> str:
        """Human-readable one-liner for an exception, never empty.

        `str(TimeoutError())` is the empty string — the exact case that made
        the live 2026-08-02 failure report say nothing at all."""
        text = str(exc or "").strip()
        return f"{type(exc).__name__}: {text}" if text else type(exc).__name__

    def _tts_unsupported_reason(self) -> str:
        """Why supports_tts() said no, in the user's terms."""
        if not self._audio_player_available():
            return (
                "this machine has no audio output backend for speech "
                "(install 'abstractassistant[voice]' for in-process playback)"
            )
        error = ""
        try:
            error = str(getattr(self._assistant_capabilities(), "error", "") or "").strip()
        except Exception:
            error = ""
        if error:
            return f"the gateway could not be reached to check speech support ({error[:200]})"
        return (
            "the gateway does not currently offer text-to-speech "
            "(check the gateway's voice route in Settings)"
        )

    def _speak_gateway_artifact(
        self,
        *,
        gw,
        run_id: str,
        text: str,
        provider: Optional[str],
        voice: Optional[str],
        profile: Optional[str],
        fmt: str,
        request_id: str,
        model: Optional[str],
        callback: Optional[Callable],
        stream_id: str,
        pause_gate: threading.Event,
        stop_gate: threading.Event,
    ) -> bool:
        """Single-shot artifact leg for an already-minted speech generation.

        Returns True when playback was started (the playback lifecycle then
        owns the completion callback); False when the generation was
        cancelled/paused-then-stopped or playback could not start.
        """
        res = gw.voice_tts(
            run_id=run_id,
            text=text,
            provider=provider,
            voice=voice,
            profile=profile,
            fmt=fmt,
            request_id=request_id,
            model=model,
            quality_preset=getattr(self, "_active_quality_preset", None),
            timeout_s=120.0,
        )
        if stop_gate.is_set():
            return False
        audio = res.get("audio_artifact") if isinstance(res, dict) else None
        aid = str(audio.get("$artifact") or "").strip() if isinstance(audio, dict) else ""
        if not aid:
            raise RuntimeError("Gateway TTS response missing audio artifact")
        audio_bytes, content_type = gw.download_run_artifact_content(
            run_id=run_id,
            artifact_id=aid,
            max_bytes=25_000_000,
            timeout_s=120.0,
        )
        if stop_gate.is_set():
            return False
        # Honor a pause issued while synthesizing (the UI exposes pause during
        # the "synthesizing" phase): hold playback until resumed; a stop
        # cancels without playing.
        if not self._wait_for_stream_resume(pause_gate, stop_gate):
            return False
        # Playback phase: release generation control so pause()/resume()/stop
        # use the external-process / in-process player paths (SIGSTOP etc.)
        # exactly as before.
        self._clear_stream_control(stream_id)
        return self._play_audio_bytes(audio_bytes, content_type, callback=callback)

    def _begin_speech_failure_tracking(self) -> None:
        """Arm the per-dispatch failure accounting (one report per speak())."""
        self._speech_failure_causes = []
        self._speech_failure_reported = False

    def _note_speech_failure(self, reason: str) -> None:
        """Record a cause seen in this dispatch, in the order it happened.

        Branches that abort deep in the stream/artifact legs know the real
        cause; the terminal `_fire_speech_completion` is what the UI observes.
        The CHAIN matters: "the pinned voice model was rejected, then the
        fallback timed out" tells the user what to change, while either half
        alone points at the wrong thing.
        """
        text = str(reason or "").strip()
        if not text:
            return
        causes = self._speech_failure_causes
        if not isinstance(causes, list):
            causes = []
            self._speech_failure_causes = causes
        if causes and causes[-1] == text[:300]:
            return
        if len(causes) < 4:
            causes.append(text[:300])

    @property
    def _speech_failure_reason(self) -> str:
        causes = self._speech_failure_causes
        if not isinstance(causes, list) or not causes:
            return ""
        return "; then ".join(causes)

    def _report_speech_failure(self, reason: str) -> None:
        """Surface a speech failure to the UI, exactly once per dispatch.

        A GUI cannot see `warnings.warn`; without this the user's only signal
        for a failed speak() is the card flipping back to idle, which reads as
        "the button does nothing" (2026-08-02 live reproduction)."""
        if self._speech_failure_reported:
            return
        self._speech_failure_reported = True
        text = str(reason or "").strip() or "speech failed for an unknown reason"
        warnings.warn(f"#FALLBACK: gateway TTS did not play: {text}")
        cb = self.on_speech_error
        if cb is None:
            return
        try:
            cb(text)
        except Exception:
            pass

    def _fire_speech_completion(
        self,
        callback: Optional[Callable],
        *,
        reason: str = "",
        cancelled: bool = False,
    ) -> None:
        """Signal the terminal outcome of a dispatched speak() exactly once.

        Fired for failures and cancellations that never reached (or never
        finished) playback: both UIs rely on the completion callback /
        on_speech_end to reset their voice state — a swallowed completion
        leaves a message card stuck on "speaking" or full-voice mode wedged
        in PROCESSING.

        This is the ONLY funnel for a dispatch that ends without playing (the
        playback lifecycles fire their own on_speech_end), so it is also where
        the "never fail silently" invariant is enforced: anything but a
        user-requested cancel reports a cause first.
        """
        if not cancelled:
            self._report_speech_failure(reason or self._speech_failure_reason)
        try:
            if self.on_speech_end:
                self.on_speech_end()
        except Exception:
            pass
        if callback:
            try:
                callback()
            except Exception:
                pass

    def pause(self) -> bool:
        """Pause current speech when supported by the local player."""
        with self._state_lock:
            if self._paused:
                return True
            stream_active = bool(self._stream_active)
            stream_pause_gate = self._stream_pause_gate
            if stream_active and stream_pause_gate is not None:
                self._paused = True
                self._speaking = False
            else:
                stream_pause_gate = None
        if stream_pause_gate is not None:
            try:
                stream_pause_gate.clear()
            except Exception:
                pass
            player = self._inprocess_player
            if self._playback_backend == "inprocess" and player is not None:
                try:
                    player.pause()
                except Exception:
                    pass
            try:
                self._meter_pause.set()
            except Exception:
                pass
            self._tts_gate_end()
            return True
        player = self._inprocess_player
        if self._playback_backend == "inprocess" and player is not None:
            try:
                if bool(player.pause()):
                    with self._state_lock:
                        self._paused = True
                        self._speaking = False
                    self._tts_gate_end()
                    return True
            except Exception:
                pass
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
            stream_active = bool(self._stream_active)
            stream_pause_gate = self._stream_pause_gate
        if stream_active and stream_pause_gate is not None:
            try:
                stream_pause_gate.set()
            except Exception:
                pass
            player = self._inprocess_player
            if self._playback_backend == "inprocess" and player is not None:
                try:
                    player.resume()
                except Exception:
                    pass
            with self._state_lock:
                self._paused = False
                self._speaking = True
            try:
                self._meter_pause.clear()
            except Exception:
                pass
            self._tts_gate_start()
            return True
        player = self._inprocess_player
        if self._playback_backend == "inprocess" and player is not None:
            try:
                if bool(player.resume()):
                    with self._state_lock:
                        self._paused = False
                        self._speaking = True
                    self._tts_gate_start()
                    return True
            except Exception:
                pass
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
        # A stop is an ANSWER, not a failure: silence the outgoing generation's
        # failure report so a superseded speak() cannot raise an error banner
        # for a run the user (or the next speak) deliberately ended. The next
        # dispatch re-arms tracking after this call.
        self._speech_failure_reported = True
        self._stop_stream_control()
        self._stop_meter()
        player = self._inprocess_player
        if self._playback_backend == "inprocess" and player is not None:
            try:
                player.stop_stream()
            except Exception:
                pass
            self._play_proc = None
            self._playback_backend = "none"
            try:
                self._play_ready.set()
            except Exception:
                pass
            with self._state_lock:
                self._speaking = False
                self._paused = False
            try:
                self._meter_pause.clear()
            except Exception:
                pass
            self._emit_audio_meter(0.0)
            self._tts_gate_end()
            return
        proc = self._play_proc
        if proc is None:
            with self._state_lock:
                self._speaking = False
                self._paused = False
            self._playback_backend = "none"
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
        self._playback_backend = "none"
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
        player = self._inprocess_player
        if self._playback_backend == "inprocess" and player is not None:
            with self._state_lock:
                if self._paused:
                    return
            try:
                active = bool(getattr(player, "is_playing", False))
            except Exception:
                active = False
            if active:
                return
            with self._state_lock:
                if self._stream_active:
                    return
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
            return
        proc = self._play_proc
        if proc is None:
            with self._state_lock:
                if self._stream_active:
                    return
            return
        try:
            if proc.poll() is None:
                return
        except Exception:
            return
        self._play_proc = None
        self._playback_backend = "none"
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
            self._note_speech_failure(
                "the gateway returned an empty speech artifact (no audio to play)"
            )
            return False
        if "wav" in str(content_type or "").lower():
            try:
                if self._play_audio_bytes_inprocess(audio_bytes, callback=callback):
                    return True
            except Exception as e:
                detail = self._exception_reason(e)
                warnings.warn(f"#FALLBACK: in-process gateway audio playback failed: {detail}")
                self._note_speech_failure(f"local audio playback failed ({detail})")
        # The external player (`afplay` and friends) always plays on the SYSTEM default
        # and takes no device argument, so a chosen device cannot be honoured here. It is
        # still better than silence — but the user picked a device, so they are told.
        if self.output_device_spec():
            self._note_speech_failure(
                "this reply is playing on the system default output: the fallback player "
                "cannot use the audio device you selected"
            )
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
            detail = self._exception_reason(e)
            warnings.warn(f"#FALLBACK: failed to write TTS audio: {detail}")
            self._note_speech_failure(
                f"the speech audio could not be written to disk for playback ({detail})"
            )
            return False

        self.stop_speaking()
        # Full-file level extraction decodes the whole WAV and runs an FFT per
        # 33ms slice — only pay for it when something consumes the meter.
        levels: list = []
        step_s = 0.0
        if self._audio_meter_callback is not None:
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
                self._playback_backend = "external"
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
                detail = self._exception_reason(e)
                warnings.warn(f"#FALLBACK: audio playback failed: {detail}")
                # This thread owns its own completion signalling, so the
                # `_fire_speech_completion` choke point never sees it: report
                # here or the card silently returns to idle mid-sentence.
                self._report_speech_failure(f"audio playback failed ({detail})")
            finally:
                self._play_proc = None
                self._playback_backend = "none"
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

    def _play_audio_bytes_inprocess(self, audio_bytes: bytes, *, callback: Optional[Callable]) -> bool:
        player = self._ensure_inprocess_audio_player()
        if player is None:
            return False
        decoded = self._decode_wav_audio_bytes(audio_bytes)
        if decoded is None:
            return False
        samples, sample_rate = decoded
        self.stop_speaking()
        try:
            self._meter_pause.clear()
        except Exception:
            pass
        try:
            self._play_ready.set()
        except Exception:
            pass
        with self._state_lock:
            self._speaking = True
            self._paused = False
        self._playback_backend = "inprocess"
        self._tts_gate_start()

        def _on_audio_start() -> None:
            try:
                if self.on_speech_start:
                    self.on_speech_start()
            except Exception:
                pass

        def _on_audio_end() -> None:
            self._emit_audio_meter(0.0)
            with self._state_lock:
                self._speaking = False
                self._paused = False
            self._playback_backend = "none"
            self._tts_gate_end()
            try:
                if self.on_speech_end:
                    self.on_speech_end()
            except Exception:
                pass
            if callback:
                try:
                    callback()
                except Exception:
                    pass

        player.on_audio_start = _on_audio_start
        player.on_audio_end = _on_audio_end
        player.playback_complete_callback = None
        player.play_audio(samples, sample_rate=sample_rate)
        return True

    def _begin_stream_playback(self) -> bool:
        player = self._ensure_inprocess_audio_player()
        if player is None:
            return False
        pause_gate = self._stream_pause_gate
        paused = bool(pause_gate is not None and not pause_gate.is_set())
        try:
            if paused:
                self._meter_pause.set()
            else:
                self._meter_pause.clear()
            self._play_ready.set()
        except Exception:
            pass
        with self._state_lock:
            self._speaking = not paused
            self._paused = paused
        self._playback_backend = "inprocess"
        if not paused:
            self._tts_gate_start()
        return True

    def _finish_stream_playback(self, *, callback: Optional[Callable], stream_id: str = "") -> bool:
        """Finish stream playback; returns True when this call fired completion.

        Returns False when the generation was already superseded/stopped (the
        id guard) — the caller then still owes a completion signal.
        """
        if stream_id:
            with self._state_lock:
                if str(self._stream_id or "") != str(stream_id or ""):
                    return False
        self._stop_meter()
        self._emit_audio_meter(0.0)
        with self._state_lock:
            self._speaking = False
            self._paused = False
        self._playback_backend = "none"
        self._tts_gate_end()
        try:
            if self.on_speech_end:
                self.on_speech_end()
        except Exception:
            pass
        if callback:
            try:
                callback()
            except Exception:
                pass
        # Report that THIS call fired completion so the caller's finally block
        # does not fire it a second time (the exactly-once `completion_owned`
        # contract). Returning None here silently double-fired on_speech_end +
        # callback via the stream finally.
        return True

    def _configure_stream_playback_callbacks(self, player, playback_drained: threading.Event) -> None:
        speech_start_emitted = threading.Event()

        def _on_audio_start() -> None:
            if speech_start_emitted.is_set():
                return
            speech_start_emitted.set()
            try:
                if self.on_speech_start:
                    self.on_speech_start()
            except Exception:
                pass

        def _on_audio_end() -> None:
            playback_drained.set()

        player.on_audio_start = _on_audio_start
        player.on_audio_end = _on_audio_end
        player.playback_complete_callback = None

    def _queue_stream_wav_chunk(self, audio_bytes: bytes, *, playback_drained: threading.Event) -> Optional[float]:
        player = self._ensure_inprocess_audio_player()
        if player is None:
            warnings.warn("#FALLBACK: in-process audio player vanished mid-stream; stopping playback")
            self._note_speech_failure(
                "the local audio player disappeared while speaking; playback stopped"
            )
            return None
        decoded = self._decode_wav_audio_bytes(audio_bytes)
        if decoded is None:
            # None aborts the stream leg: say why (2026-07-28 audit found this
            # abort chain produced no diagnostic anywhere).
            warnings.warn("#FALLBACK: gateway TTS chunk was not decodable WAV; stopping playback")
            self._note_speech_failure(
                "the gateway sent audio this app could not decode (not playable WAV); playback stopped"
            )
            return None
        samples, sample_rate = decoded
        playback_drained.clear()
        player.play_audio(samples, sample_rate=sample_rate)
        try:
            duration = float(len(samples)) / float(sample_rate) if sample_rate else 0.0
        except Exception:
            duration = 0.0
        return duration

    def _wait_for_stream_playback_drain(self, player, playback_drained: threading.Event, *, timeout_s: float) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout_s or 0.0))
        while time.monotonic() < deadline:
            if playback_drained.is_set() or self._stream_playback_idle(player):
                return True
            time.sleep(0.03)
        return bool(playback_drained.is_set() or self._stream_playback_idle(player))

    def _stream_playback_idle(self, player) -> bool:
        with self._state_lock:
            if self._paused:
                return False
        if player is None:
            return True
        try:
            if bool(getattr(player, "is_playing", False)):
                return False
        except Exception:
            return False
        try:
            q = getattr(player, "audio_queue", None)
            if q is not None and not bool(q.empty()):
                return False
        except Exception:
            return False
        try:
            current = getattr(player, "current_audio", None)
            if current is None:
                return True
            pos = int(getattr(player, "current_position", 0) or 0)
            return bool(pos >= len(current))
        except Exception:
            return False

    def _ensure_inprocess_audio_player(self):
        if self._inprocess_player is not None:
            return self._inprocess_player
        if not self._supports_inprocess_audio_player():
            return None
        try:
            from abstractvoice.tts import NonBlockingAudioPlayer
        except Exception:
            return None
        player = NonBlockingAudioPlayer(
            debug_mode=self.debug_mode,
            output_device=self.output_device_spec() or None,
        )
        # A wrong speaker used to be silent in every sense: the player fell back to
        # another device without a word, so "I hear nothing" had no explanation
        # anywhere. Route that into the same failure channel the rest of speech uses.
        player.on_output_device_problem = self._note_speech_failure
        # Refreshing the device list restarts PortAudio, which invalidates EVERY open
        # stream in this process — a live microphone included.
        player.allow_device_refresh = self._can_refresh_audio_devices
        prev = getattr(player, "on_audio_chunk", None)

        def _on_chunk(chunk, sample_rate: int) -> None:
            if callable(prev):
                try:
                    prev(chunk, sample_rate)
                except Exception:
                    pass
            self._emit_audio_meter_from_chunk(chunk, sample_rate)

        player.on_audio_chunk = _on_chunk
        self._inprocess_player = player
        return player

    def _supports_inprocess_audio_player(self) -> bool:
        try:
            from abstractvoice.tts import NonBlockingAudioPlayer  # noqa: F401
            import sounddevice  # noqa: F401
            return True
        except Exception:
            return False

    def _decode_wav_audio_bytes(self, audio_bytes: bytes):
        try:
            import wave
            import numpy as np
        except Exception:
            return None
        try:
            with wave.open(io.BytesIO(bytes(audio_bytes)), "rb") as wf:
                sample_rate = int(wf.getframerate() or 0)
                channels = int(wf.getnchannels() or 1)
                sampwidth = int(wf.getsampwidth() or 0)
                frames = wf.readframes(int(wf.getnframes() or 0))
        except Exception:
            return None
        if sample_rate <= 0 or not frames:
            return None
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
        return data.reshape(-1), sample_rate

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
                # `np` is a required argument: without it every call raised
                # TypeError into the swallow below, so this meter had never
                # produced a single reading (193 chunks, 193 exceptions, in a
                # live measurement) and anything drawing it stayed frozen.
                bands = self._compute_band_levels(arr, int(sample_rate), rms, np)
            if bands:
                cb(bands)
            else:
                cb(level)
        except Exception as e:
            if not self._audio_meter_warned:
                self._audio_meter_warned = True
                warnings.warn(f"#FALLBACK: audio meter unavailable: {e!r}")

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
        # Fresh per-generation events (captured in the closure): clearing the
        # shared stop event here could revive an old thread that had not yet
        # observed the stop flag, leaving two meters emitting concurrently.
        stop_ev = threading.Event()
        pause_ev = threading.Event()
        self._meter_stop = stop_ev
        self._meter_pause = pause_ev

        def _run() -> None:
            for lvl in levels:
                if stop_ev.is_set():
                    return
                while pause_ev.is_set() and not stop_ev.is_set():
                    time.sleep(0.05)
                if stop_ev.is_set():
                    return
                self._emit_audio_meter(lvl)
                stop_ev.wait(timeout=step_s)
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
        if self._supports_inprocess_audio_player():
            return True
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

    def _assistant_capabilities(self):
        try:
            fn = getattr(self._llm_manager, "gateway_capabilities", None)
            if callable(fn):
                try:
                    caps = fn(stale_ok=True)
                except TypeError:
                    caps = fn()
                if caps is not None:
                    return caps
        except Exception:
            pass
        return get_cached_assistant_capabilities(self._gateway_client(), stale_ok=True)

    def _gateway_tts_available(self) -> bool:
        try:
            return bool(self._assistant_capabilities().tts_available())
        except Exception:
            return False

    def _gateway_tts_streaming_available(self) -> bool:
        try:
            return bool(self._assistant_capabilities().tts_streaming_available())
        except Exception:
            return False

    def _gateway_stt_available(self) -> bool:
        try:
            return bool(self._assistant_capabilities().stt_available())
        except Exception:
            return False

    def available_tts_voices(self) -> list[dict]:
        voices: list[dict] = []
        seen: set[str] = set()
        try:
            catalog = self._gateway_client().voice_voices()
            if isinstance(catalog, dict):
                for key in ("profiles", "voices", "cloned_voices"):
                    values = catalog.get(key)
                    if isinstance(values, list):
                        for item in values:
                            if not isinstance(item, dict):
                                continue
                            voice_id = ""
                            for id_key in ("qualified_id", "id", "profile_id", "voice_id", "name"):
                                value = item.get(id_key)
                                if isinstance(value, str) and value.strip():
                                    voice_id = value.strip()
                                    break
                            if not voice_id or voice_id in seen:
                                continue
                            seen.add(voice_id)
                            voices.append(item)
        except Exception:
            voices = []
        if voices:
            return voices
        try:
            return self._assistant_capabilities().tts_voices()
        except Exception:
            return []

    def _preferred_tts_format(self) -> str:
        if sys.platform == "darwin" and self._supports_inprocess_audio_player():
            return "wav"
        try:
            return str(self._assistant_capabilities().preferred_tts_format() or "wav")
        except Exception:
            return "wav"

    def _selected_tts_voice(self) -> Optional[str]:
        selected = str(getattr(self._llm_manager, "current_tts_voice", "") or "").strip()
        if selected:
            return selected
        try:
            return self._assistant_capabilities().selected_tts_voice()
        except Exception:
            preferred = str(
                os.getenv("ABSTRACTASSISTANT_GATEWAY_TTS_VOICE")
                or os.getenv("ABSTRACTASSISTANT_TTS_VOICE")
                or ""
            ).strip()
            return preferred or None

    def _selected_tts_voice_mode(self) -> str:
        selected = str(getattr(self._llm_manager, "current_tts_voice_mode", "") or "").strip().lower()
        if selected in {"clone", "profile"}:
            return selected
        return "profile"

    def _selected_tts_model(self) -> Optional[str]:
        """Explicit TTS model pin, or None to let the gateway resolve its own.

        NEVER echo the gateway's advertised `active_model` back as a pin. It is
        the gateway's own default — not the user's choice — and re-sending it
        WITHOUT a matching provider is a half-pin the stream route rejects:
        measured live 2026-08-02 against the running gateway,
        `model="supertonic-3"` with no provider makes /voice/tts/stream answer
        `error: audio/speech failed (404): The model supertonic-3 does not
        exist or you do not have access to it` after ~0.4 s and before any
        audio, which drops the client onto the whole-artifact lane — the entire
        message is synthesized server-side before one sample plays (TTFV 17.5 s
        for 1,000 chars, minutes for a long answer). The same request with no
        model pin streams first audio in ~1 s.

        This mirrors the pair rule the preferences layer already enforces for
        route overrides (provider AND model, never half) and the controller's
        own rule: "we never read the gateway's global default here and pin it
        as if it were the user's choice".
        """
        selected = str(getattr(self._llm_manager, "current_tts_model", "") or "").strip()
        if selected:
            return selected
        preferred = str(
            os.getenv("ABSTRACTASSISTANT_GATEWAY_TTS_MODEL")
            or os.getenv("ABSTRACTASSISTANT_TTS_MODEL")
            or ""
        ).strip()
        return preferred or None

    def _selected_tts_provider(self) -> Optional[str]:
        selected = str(getattr(self._llm_manager, "current_tts_provider", "") or "").strip()
        if selected:
            return selected
        preferred = str(
            os.getenv("ABSTRACTASSISTANT_GATEWAY_TTS_PROVIDER")
            or os.getenv("ABSTRACTASSISTANT_TTS_PROVIDER")
            or ""
        ).strip()
        return preferred or None

    def _selected_stt_model(self) -> Optional[str]:
        """Explicit STT model pin, or None to let the gateway resolve its own.

        Same rule as `_selected_tts_model`: the gateway's advertised
        `active_model` is the gateway's default, not the user's choice, and
        echoing it back without its provider is a half-pin. A model is pinned
        only when the user's `input.voice` override or an env var chose one.
        """
        selected = str(getattr(self._llm_manager, "current_stt_model", "") or "").strip()
        if selected:
            return selected
        preferred = str(
            os.getenv("ABSTRACTASSISTANT_GATEWAY_STT_MODEL")
            or os.getenv("ABSTRACTASSISTANT_STT_MODEL")
            or ""
        ).strip()
        return preferred or None

    def _selected_stt_provider(self) -> Optional[str]:
        # Local STT override provider only; empty lets the gateway resolve the
        # provider from its input.voice default (the transcribe endpoint accepts
        # an optional provider, applied to the STT output spec server-side).
        selected = str(getattr(self._llm_manager, "current_stt_provider", "") or "").strip()
        if selected:
            return selected
        preferred = str(
            os.getenv("ABSTRACTASSISTANT_GATEWAY_STT_PROVIDER")
            or os.getenv("ABSTRACTASSISTANT_STT_PROVIDER")
            or ""
        ).strip()
        return preferred or None

    def _stt_upload_content_type(self) -> str:
        try:
            return str(self._assistant_capabilities().stt_upload_content_type_for_wav() or "")
        except Exception:
            return ""

    def _stt_max_upload_bytes(self) -> int:
        try:
            return int(self._assistant_capabilities().stt_max_upload_bytes())
        except Exception:
            return 0

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
