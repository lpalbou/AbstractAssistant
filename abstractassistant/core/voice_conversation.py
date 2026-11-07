"""One voice turn: listen once → send → speak the reply → stop.

This is the Qt-free state machine behind the orb and the menu's "Voice
conversation". It owns no widgets and no threads: the palette marshals the
voice manager's callbacks onto the GUI thread and calls the methods below.

A press is ONE turn, like the Apple Watch's orb (0.18.2; before, the mode was a
hands-free loop that listened again after every reply, and in a quiet room the
speech-to-text model turned the silence into "Thank you." four times, each sent
as a message):

- the microphone records ONE utterance (``GatewayVoiceManager.begin_hold`` with
  ``on_utterance_end``): about one second of silence after speech ends it;
  nothing said for a few seconds ends it with nothing sent;
- pressing the orb while it listens ends the turn now: what was said is sent,
  and nothing is sent when nothing was said (``finish_listening``);
- the gateway transcribes the recording, the words are sent like typed text,
  the reply is spoken, and the turn is over (state ``off``): the microphone is
  never reopened by itself. The next press starts the next turn.

States (``VoiceConversation.state``):

- ``off``           — no turn (or the turn just ended; ``outcome`` says how).
- ``starting``      — the microphone is being opened.
- ``listening``     — the microphone records the one utterance.
- ``transcribing``  — the microphone is closed; the gateway transcribes.
- ``thinking``      — the words were sent; a run is in flight.
- ``speaking``      — the reply is being spoken.
- ``error``         — the turn stopped because something failed; ``error`` says what.

Everything the palette shows for the turn derives from ``state`` plus the
``last_transcript`` / ``error`` / ``outcome`` fields, so the UI can never claim a
state the turn is not in.
"""

from __future__ import annotations

from typing import Callable, Optional


VOICE_CONVERSATION_STATES = (
    "off",
    "starting",
    "listening",
    "transcribing",
    "thinking",
    "speaking",
    "error",
)

# How a turn ended (``VoiceConversation.outcome`` once the state is ``off``).
TURN_OUTCOMES = (
    "answered",       # the reply was spoken, or the run ended with nothing to speak
    "nothing_heard",  # no speech before the turn ended (silence, or a press)
    "not_sent",       # the transcription failed: the recording is kept (Retry / Discard)
    "failed",         # the run failed or could not start
    "handed_over",    # the words went to the message box instead of being sent
    "cancelled",      # Esc, the menu, or a press after listening
)

# Model guidance while a voice turn runs: spoken replies must be short and free
# of markup, or the TTS reads tables and headings aloud.
VOICE_CONVERSATION_SYSTEM_PROMPT = (
    "You are in a spoken voice conversation.\n"
    "- Reply as natural spoken conversation, discussion-style.\n"
    "- Keep it brief: one to three short sentences unless the user asks for detail.\n"
    "- Avoid markdown, headings, lists, tables and code unless explicitly requested.\n"
    "- Ask a short follow-up question when it genuinely helps.\n"
    "- Do not mention voice mode or these rules.\n"
)


class VoiceConversation:
    """One voice turn. See the module docstring for the states."""

    def __init__(
        self,
        *,
        voice_manager,
        on_send: Callable[[str], None],
        on_state: Optional[Callable[[str], None]] = None,
        on_level: Optional[Callable[[float], None]] = None,
        auto_send: bool = True,
    ) -> None:
        self._voice = voice_manager
        self._on_send = on_send
        self._on_state = on_state
        self._on_level = on_level
        self.auto_send = bool(auto_send)
        self.state = "off"
        self.error = ""
        self.outcome = ""
        self.last_transcript = ""
        self.turns = 0
        self._transcribe_kwargs: dict = {}

    # ------------------------------------------------------------------ helpers

    @property
    def active(self) -> bool:
        return self.state not in {"off", "error"}

    def _set_state(self, state: str, *, error: str = "") -> None:
        if state not in VOICE_CONVERSATION_STATES:
            state = "error"
        self.state = state
        self.error = str(error or "") if state == "error" else ""
        if self._on_state is not None:
            try:
                self._on_state(state)
            except Exception:
                pass

    def _call(self, name: str, *args, **kwargs):
        fn = getattr(self._voice, name, None)
        if not callable(fn):
            return None
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None

    def _finish(self, outcome: str) -> None:
        """The turn is over: the microphone is closed and stays closed."""
        self.outcome = outcome if outcome in TURN_OUTCOMES else "answered"
        self._call("cancel_hold")
        self._set_state("off")

    # ------------------------------------------------------------------ lifecycle

    def start(self, *, capture_kwargs: Optional[dict] = None, transcribe_kwargs: Optional[dict] = None) -> bool:
        """Open the microphone for one utterance. Returns False (state
        ``error``) when it cannot.

        ``capture_kwargs`` go to ``begin_hold`` (``on_audio_level``,
        ``on_utterance_end``); ``transcribe_kwargs`` to ``end_hold``
        (``on_transcription``, ``on_error``). Both carry callbacks the palette
        marshals onto the GUI thread.
        """
        if self.active:
            return True
        self.outcome = ""
        self.last_transcript = ""
        self._transcribe_kwargs = dict(transcribe_kwargs or {})
        self._set_state("starting")
        try:
            meter = getattr(self._voice, "set_audio_meter_callback", None)
            if callable(meter) and self._on_level is not None:
                meter(self._on_level)
            started = self._voice.begin_hold(**(capture_kwargs or {}))
        except Exception as exc:
            self._set_state("error", error=str(exc) or exc.__class__.__name__)
            return False
        if not started:
            self._set_state("error", error="the microphone did not start")
            return False
        self._set_state("listening")
        return True

    def detach(self) -> None:
        """Drop the UI callbacks (the palette is tearing the turn down and
        must not be re-entered by the state change ``stop`` produces)."""
        self._on_state = None
        self._on_level = None

    def stop(self, *, reason: str = "") -> None:
        """End the turn now: close the microphone (nothing recorded is sent)
        and stop any speech."""
        was = self.state
        self._call("cancel_hold")
        self._call("stop_speaking")
        meter = getattr(self._voice, "set_audio_meter_callback", None)
        if callable(meter):
            try:
                meter(None)
            except Exception:
                pass
        if reason:
            self._set_state("error", error=reason)
        else:
            if was not in {"off", "error"}:
                self.outcome = "cancelled"
            self._set_state("off")

    # ------------------------------------------------------------------ listening

    def finish_listening(self) -> bool:
        """End the listening now (the silence after speech, or a press on the
        orb). What was said is transcribed and sent; when nothing was said the
        turn ends with nothing sent. Returns True when a recording went to the
        gateway."""
        if self.state != "listening":
            return False
        heard = bool(self._call("hold_heard_speech"))
        if not heard:
            self._finish("nothing_heard")
            return False
        started = False
        try:
            started = bool(self._voice.end_hold(**self._transcribe_kwargs))
        except Exception as exc:
            self._call("cancel_hold")
            self._set_state("error", error=str(exc) or exc.__class__.__name__)
            return False
        if not started:
            # Too short to be speech: nothing goes to the gateway.
            self._finish("nothing_heard")
            return False
        self._set_state("transcribing")
        return True

    def utterance_ended(self) -> None:
        """The voice manager's endpoint fired (silence after speech, nothing
        said in time, or the longest utterance): end the listening."""
        self.finish_listening()

    def transcribed(self, text: str) -> None:
        """The gateway's transcript of the one utterance (GUI thread)."""
        if self.state != "transcribing":
            return
        utterance = " ".join(str(text or "").split()).strip()
        if not utterance:
            self._finish("nothing_heard")
            return
        self.last_transcript = utterance
        self.turns += 1
        self._set_state("thinking")
        try:
            self._on_send(utterance)
        except Exception as exc:
            self._set_state("error", error=str(exc) or exc.__class__.__name__)

    def transcription_failed(self, reason: str = "") -> None:
        """The gateway could not transcribe it: the voice manager keeps the
        recording for Retry / Discard; the turn ends with nothing sent."""
        if self.state == "transcribing":
            self._finish("not_sent")

    def hand_over(self) -> None:
        """The words were put in the message box instead of being sent (a
        draft is open, a reply is still finishing, or sending is manual)."""
        if self.active:
            self._finish("handed_over")

    # ------------------------------------------------------------------ the reply

    def run_finished(self, *, will_speak: bool) -> None:
        """The run ended. ``will_speak``: its reply is about to be spoken (the
        palette then calls ``speech_finished``); otherwise the turn is over."""
        if self.state != "thinking":
            return
        if will_speak:
            self._set_state("speaking")
            return
        self._finish("answered")

    def speech_finished(self) -> None:
        """The reply finished (or failed, or was stopped): the turn is over."""
        if self.state == "speaking":
            self._finish("answered")

    def run_failed(self, reason: str = "") -> None:
        """The run errored or could not start: the turn is over (the palette
        shows why)."""
        if self.active:
            self._finish("failed")


__all__ = [
    "TURN_OUTCOMES",
    "VOICE_CONVERSATION_STATES",
    "VOICE_CONVERSATION_SYSTEM_PROMPT",
    "VoiceConversation",
]
