"""When one spoken utterance is over: the end of a voice turn.

Qt-free and audio-free: it is fed one voice-activity decision per microphone
frame (``push``) and says when the turn ends and why. The voice manager runs it
on the recording a press of the orb starts (``begin_hold(on_utterance_end=…)``),
so a press is ONE utterance, like the Apple Watch's orb
(``watch/apple/Sources/App/Shared/Listener.swift``):

- ``silence``      — speech was heard, then about one second of silence;
- ``no_speech``    — nothing was said for ``wait_for_speech_s`` (the watch's 5 s);
- ``max_duration`` — the longest utterance (the watch's 60 s).

Speech is the voice-activity detector's decision, the same detector the
continuous recognizer used (webrtcvad through AbstractVoice). A short burst
under ``min_speech_ms`` (a click, a cough) does not count as having spoken;
it also does not end the wait for speech, exactly as the watch's quiet timer
restarts on every loud frame.
"""

from __future__ import annotations

from typing import Optional


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
    ) -> None:
        frame = max(1, int(frame_ms))
        self.frame_ms = frame
        self._min_speech = max(1, round(int(min_speech_ms) / frame))
        self._silence = max(1, round(int(silence_ms) / frame))
        self._wait = max(1, round(float(wait_for_speech_s) * 1000 / frame))
        self._max = max(1, round(float(max_s) * 1000 / frame))
        self.heard = False
        self.ended: Optional[str] = None
        self._frames = 0
        self._speech = 0
        self._silent_after_speech = 0
        self._quiet = 0

    def push(self, is_speech: bool) -> Optional[str]:
        """One frame's decision. Returns the end reason on the frame that
        ends the turn, None otherwise (and None again after it ended)."""
        if self.ended is not None:
            return None
        self._frames += 1
        if is_speech:
            self._speech += 1
            self._quiet = 0
            self._silent_after_speech = 0
            if self._speech >= self._min_speech:
                self.heard = True
        elif self.heard:
            self._silent_after_speech += 1
        else:
            self._speech = max(0, self._speech - 1)
            self._quiet += 1
        if self.heard and self._silent_after_speech >= self._silence:
            self.ended = "silence"
        elif not self.heard and self._quiet >= self._wait:
            self.ended = "no_speech"
        elif self._frames >= self._max:
            self.ended = "max_duration"
        return self.ended


__all__ = ["END_REASONS", "UtteranceEndpoint"]
