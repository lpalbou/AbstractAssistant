"""Hands-free voice conversation: the listen → send → speak → listen loop.

This is the Qt-free state machine behind the palette's "Voice conversation"
mode. It owns no widgets and no threads: the palette marshals recognizer
callbacks onto the GUI thread and calls the methods below; a `schedule`
callable (a QTimer wrapper in the app, a manual scheduler in tests) provides
the short debounce that merges closely spaced utterances into one turn.

States (``VoiceConversation.state``):

- ``off``       — not running.
- ``starting``  — microphone + gateway STT are being brought up.
- ``listening`` — mic open, waiting for speech.
- ``heard``     — an utterance was transcribed; more may follow within the
                  debounce window before it is sent as one prompt.
- ``thinking``  — the prompt was sent; a run is in flight.
- ``speaking``  — the reply is being spoken (the microphone is paused by the
                  voice manager's ``wait`` gate so the assistant never
                  transcribes itself).
- ``paused``    — the user muted the microphone without leaving the mode.
- ``error``     — the loop stopped because something failed; ``error`` says what.

Everything the palette shows for the mode derives from ``state`` plus the
``last_transcript`` / ``error`` fields, so the UI can never claim a state the
loop is not in.
"""

from __future__ import annotations

from typing import Callable, List, Optional


VOICE_CONVERSATION_STATES = (
    "off",
    "starting",
    "listening",
    "heard",
    "thinking",
    "speaking",
    "paused",
    "error",
)

# Model guidance while the conversation is on: spoken replies must be short
# and free of markup, or the TTS reads tables and headings aloud.
VOICE_CONVERSATION_SYSTEM_PROMPT = (
    "You are in a spoken voice conversation.\n"
    "- Reply as natural spoken conversation, discussion-style.\n"
    "- Keep it brief: one to three short sentences unless the user asks for detail.\n"
    "- Avoid markdown, headings, lists, tables and code unless explicitly requested.\n"
    "- Ask a short follow-up question when it genuinely helps.\n"
    "- Do not mention voice mode or these rules.\n"
)


class VoiceConversation:
    """The hands-free loop. See the module docstring for the states."""

    def __init__(
        self,
        *,
        voice_manager,
        on_send: Callable[[str], None],
        on_state: Optional[Callable[[str], None]] = None,
        on_level: Optional[Callable[[float], None]] = None,
        schedule: Optional[Callable[[float, Callable[[], None]], None]] = None,
        debounce_s: float = 0.8,
        auto_send: bool = True,
        voice_mode: str = "wait",
    ) -> None:
        self._voice = voice_manager
        self._on_send = on_send
        self._on_state = on_state
        self._on_level = on_level
        self._schedule = schedule
        self._debounce_s = max(0.0, float(debounce_s))
        self.auto_send = bool(auto_send)
        # "wait": the mic pauses while the reply plays (speakers, no barge-in).
        # "full": the mic stays open so the spoken "stop" interrupts (headphones).
        self.voice_mode = "full" if str(voice_mode or "").strip().lower() == "full" else "wait"
        self.state = "off"
        self.error = ""
        self.last_transcript = ""
        self.turns = 0
        self._pending: List[str] = []
        self._queued: List[str] = []
        self._flush_token = 0
        self._speak_pending = False

    # ------------------------------------------------------------------ helpers

    @property
    def active(self) -> bool:
        return self.state not in {"off", "error"}

    def pending_text(self) -> str:
        return " ".join(part for part in self._pending if part).strip()

    def queued_text(self) -> str:
        return " ".join(part for part in self._queued if part).strip()

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

    # ------------------------------------------------------------------ lifecycle

    def start(self, *, listen_kwargs: Optional[dict] = None) -> bool:
        """Open the microphone. Returns False (state ``error``) when it cannot."""
        if self.active:
            return True
        self._pending = []
        self._queued = []
        self._speak_pending = False
        self._set_state("starting")
        try:
            setter = getattr(self._voice, "set_voice_mode", None)
            if callable(setter):
                # `wait`: the recognizer is paused while the reply plays, so
                # the assistant never transcribes its own voice on speakers.
                setter(self.voice_mode)
            meter = getattr(self._voice, "set_audio_meter_callback", None)
            if callable(meter) and self._on_level is not None:
                meter(self._on_level)
            started = self._voice.listen(**(listen_kwargs or {}))
        except Exception as exc:
            self._set_state("error", error=str(exc) or exc.__class__.__name__)
            return False
        if not started:
            self._set_state("error", error="the microphone did not start")
            return False
        self._set_state("listening")
        return True

    def detach(self) -> None:
        """Drop the UI callbacks (the palette is tearing the mode down and
        must not be re-entered by the state change ``stop`` produces)."""
        self._on_state = None
        self._on_level = None

    def stop(self, *, reason: str = "") -> None:
        """Leave the mode: close the microphone and stop any speech."""
        self._flush_token += 1
        self._pending = []
        self._queued = []
        self._speak_pending = False
        for name in ("stop_listening", "stop_speaking"):
            fn = getattr(self._voice, name, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        meter = getattr(self._voice, "set_audio_meter_callback", None)
        if callable(meter):
            try:
                meter(None)
            except Exception:
                pass
        if reason:
            self._set_state("error", error=reason)
        else:
            self._set_state("off")

    def pause(self) -> bool:
        """Mute the microphone without leaving the mode."""
        if self.state not in {"listening", "heard"}:
            return False
        fn = getattr(self._voice, "pause_listening", None)
        ok = bool(fn()) if callable(fn) else False
        if ok:
            self._flush_token += 1
            self._set_state("paused")
        return ok

    def resume(self) -> bool:
        if self.state != "paused":
            return False
        fn = getattr(self._voice, "resume_listening", None)
        ok = bool(fn()) if callable(fn) else False
        if ok:
            self._set_state("listening")
            self._flush_queued()
        return ok

    # ------------------------------------------------------------------ events

    def heard(self, text: str) -> None:
        """A transcription arrived (call on the GUI thread)."""
        utterance = " ".join(str(text or "").split()).strip()
        if not utterance or not self.active:
            return
        self.last_transcript = utterance
        if self.state in {"thinking", "speaking"}:
            # The user kept talking while the assistant works: keep it for the
            # next turn instead of steering a run with a half sentence.
            self._queued.append(utterance)
            return
        if self.state == "paused":
            return
        self._pending.append(utterance)
        self._set_state("heard")
        if not self.auto_send:
            return
        self._flush_token += 1
        token = self._flush_token
        if self._schedule is None or self._debounce_s <= 0:
            self._flush(token)
            return
        self._schedule(self._debounce_s, lambda: self._flush(token))

    def send_now(self) -> str:
        """Send whatever was heard so far (the composer's Enter in manual mode)."""
        self._flush_token += 1
        return self._flush(self._flush_token)

    def _flush(self, token: int) -> str:
        if token != self._flush_token or not self.active:
            return ""
        text = self.pending_text()
        self._pending = []
        if not text or self.state not in {"heard", "listening"}:
            return ""
        self.turns += 1
        self._enter_thinking()
        try:
            self._on_send(text)
        except Exception as exc:
            self._set_state("error", error=str(exc) or exc.__class__.__name__)
            return ""
        return text

    def _enter_thinking(self) -> None:
        """The run is working: mute the microphone so side talk is never
        transcribed or queued behind the user's back (the strip says
        "mic paused" — this is what makes that true)."""
        self._set_state("thinking")
        fn = getattr(self._voice, "pause_listening", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def _enter_listening(self) -> None:
        fn = getattr(self._voice, "resume_listening", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
        self._set_state("listening")

    def mark_sent(self) -> str:
        """The user sent the pending words themselves (manual mode, Return):
        account for the turn without re-sending it."""
        if not self.active:
            return ""
        text = self.pending_text()
        self._flush_token += 1
        self._pending = []
        if self.state in {"heard", "listening", "speaking", "paused"}:
            self._speak_pending = False
            self.turns += 1
            self._enter_thinking()
        return text

    def requeue(self, text: str) -> None:
        """A turn could not be sent right now (a run is still finishing):
        keep it for the next listening window instead of steering."""
        utterance = " ".join(str(text or "").split()).strip()
        if utterance and self.active:
            self._queued.append(utterance)
            if self.state != "thinking":
                self._enter_thinking()

    def run_finished(self, *, will_speak: bool) -> None:
        """The run ended. ``will_speak`` is True when a reply is about to be
        spoken (the palette then calls ``speech_started``/``speech_finished``)."""
        if not self.active:
            return
        if will_speak:
            self._speak_pending = True
            # The voice manager's own gate keeps the mic closed while the
            # reply plays in `wait` mode; `full` mode reopens it for barge-in.
            if self.voice_mode == "full":
                fn = getattr(self._voice, "resume_listening", None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
            self._set_state("speaking")
            return
        self._speak_pending = False
        self._enter_listening()
        self._flush_queued()

    def speech_started(self) -> None:
        if self.active and self.state != "paused":
            self._speak_pending = False
            self._set_state("speaking")

    def speech_finished(self) -> None:
        """The reply finished (or failed) playing: listen again."""
        if not self.active or self.state != "speaking":
            return
        self._speak_pending = False
        self._enter_listening()
        self._flush_queued()

    def run_failed(self, reason: str = "") -> None:
        """The run errored: stay in the mode, say so, and keep listening."""
        if not self.active:
            return
        self._enter_listening()
        self._flush_queued()

    def _flush_queued(self) -> None:
        if not self._queued or self.state != "listening":
            return
        self._pending = list(self._queued)
        self._queued = []
        self._set_state("heard")
        if self.auto_send:
            self._flush_token += 1
            self._flush(self._flush_token)


__all__ = [
    "VOICE_CONVERSATION_STATES",
    "VOICE_CONVERSATION_SYSTEM_PROMPT",
    "VoiceConversation",
]
