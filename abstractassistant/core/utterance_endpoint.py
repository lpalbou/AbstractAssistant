"""When one spoken utterance is over: the end of a voice turn.

Qt-free and audio-free: it is fed one voice-activity decision per microphone
frame (``push``), can be asked at any time (``poll``), and says when the turn
ends and why. The voice manager runs it on the recording a press of the orb
starts (``begin_hold(on_utterance_end=…)``), so a press is ONE utterance, like
the Apple Watch's orb (``watch/apple/Sources/App/Shared/Listener.swift``):

- ``silence``      — speech was heard, then about one second without speech;
- ``no_speech``    — nothing was said for ``wait_for_speech_s`` (the watch's 5 s);
- ``max_duration`` — the longest utterance (the watch's 60 s).

All three are WALL-CLOCK limits (the watch's own timers are), measured from the
press or from the last speech frame. A microphone that stops delivering frames
(unplugged, permission revoked, a stalled stream) still ends the turn: the voice
turn polls the endpoint on a timer, so the limits do not wait for a frame.

Speech is the voice-activity detector's decision, the same detector the
continuous recognizer used (webrtcvad through AbstractVoice). A short burst
under ``min_speech_ms`` of speech frames (a click, a cough) does not count as
having spoken; it does restart the wait for speech, exactly as the watch's quiet
timer restarts on every loud frame.

Thread-safe: frames arrive on the audio thread, polls on the GUI thread, and the
end is decided once.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional


END_REASONS = ("silence", "no_speech", "max_duration")


class UtteranceEndpoint:
    def __init__(
        self,
        *,
        frame_ms: int = 30,
        min_speech_ms: int = 300,
        silence_ms: int = 1020,
        wait_for_speech_s: float = 5.0,
        max_s: float = 60.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        frame = max(1, int(frame_ms))
        self.frame_ms = frame
        self._min_speech = max(1, round(int(min_speech_ms) / frame))
        self._silence_s = max(0.0, int(silence_ms) / 1000.0)
        self._wait_s = max(0.0, float(wait_for_speech_s))
        self._max_s = max(0.0, float(max_s))
        # Read through the module at call time, so a test can drive the clock.
        self._clock = clock or (lambda: time.monotonic())
        self._lock = threading.Lock()
        self.heard = False
        self.ended: Optional[str] = None
        self._speech = 0
        self._started = self._clock()
        self._last_speech = self._started

    def push(self, is_speech: bool) -> Optional[str]:
        """One frame's decision. Returns the end reason on the call that ends
        the turn, None otherwise (and None again after it ended)."""
        with self._lock:
            if self.ended is not None:
                return None
            now = self._clock()
            if is_speech:
                self._speech += 1
                self._last_speech = now
                if self._speech >= self._min_speech:
                    self.heard = True
            elif not self.heard:
                self._speech = max(0, self._speech - 1)
            return self._decide(now)

    def poll(self) -> Optional[str]:
        """The wall-clock limits, with or without frames. Returns the end
        reason on the call that ends the turn, None otherwise."""
        with self._lock:
            if self.ended is not None:
                return None
            return self._decide(self._clock())

    def _decide(self, now: float) -> Optional[str]:
        quiet = now - self._last_speech + 1e-9  # float sums of 30 ms must not miss the boundary
        if self.heard and quiet >= self._silence_s:
            self.ended = "silence"
        elif not self.heard and quiet >= self._wait_s:
            self.ended = "no_speech"
        elif now - self._started + 1e-9 >= self._max_s:
            self.ended = "max_duration"
        return self.ended


__all__ = ["END_REASONS", "UtteranceEndpoint"]
