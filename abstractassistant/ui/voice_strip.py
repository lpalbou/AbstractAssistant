"""The composer's voice strip: what the hands-free conversation is doing.

One 30 px row above the prompt so typing keeps working while the conversation
runs. Everything it shows comes from the ``VoiceConversation`` state machine
(`core/voice_conversation.py`) plus the live microphone / playback level; it
never infers a state on its own.

The strip owns its look (``VOICE_STRIP_QSS``, tokens only) and applies it to
itself, so its per-state tint is the same in the palette and in any host:
listening / speaking = positive, heard / thinking = accent, paused = neutral,
error = danger.
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from abstractassistant.icons import symbol_icon
from abstractassistant.theme import METRICS, THEME

from .styles import alpha, refresh_style


VOICE_STRIP_HEIGHT = 30

# state -> (glyph, glyph tone, default text)
_STATE_VIEW = {
    "starting": ("loader", THEME.text_muted, "Starting the microphone…"),
    "listening": ("mic", THEME.positive, "Listening…"),
    "heard": ("loader", THEME.accent, "Heard you — sending in a moment…"),
    "thinking": ("spark", THEME.accent, "Thinking… (mic paused)"),
    "speaking": ("speaker", THEME.positive, "Speaking… press Esc to stop"),
    "paused": ("mic-off", THEME.text_muted, "Microphone paused"),
    "error": ("alert", THEME.danger, "Voice conversation stopped"),
    "off": ("mic-off", THEME.text_muted, ""),
}

_METER_STATES = {"listening", "speaking", "heard"}


def _build_strip_qss() -> str:
    t, m = THEME, METRICS

    def tint(color: str, bg: float, border: float) -> str:
        return f"background: {alpha(color, bg)}; border-bottom-color: {alpha(color, border)};"

    return f"""
        QFrame#voiceStrip {{
            {tint(t.positive, 0.07, 0.18)}
            border: none;
            border-bottom: 1px solid {alpha(t.positive, 0.18)};
            border-top-left-radius: {m.radius_card}px;
            border-top-right-radius: {m.radius_card}px;
        }}
        QFrame#voiceStrip[state="starting"] {{ {tint(t.text_secondary, 0.04, 0.14)} }}
        QFrame#voiceStrip[state="heard"], QFrame#voiceStrip[state="thinking"] {{ {tint(t.accent, 0.07, 0.18)} }}
        QFrame#voiceStrip[state="paused"] {{ {tint(t.text_secondary, 0.04, 0.14)} }}
        QFrame#voiceStrip[state="error"] {{ {tint(t.danger, 0.10, 0.24)} }}
        QLabel#voiceStripStatus {{
            color: {t.text_primary};
            font-size: {m.font_caption}px;
            font-weight: 600;
            background: transparent;
            border: none;
        }}
        QLabel#voiceStripStatus[state="error"] {{ color: {t.danger_text}; }}
        QLabel#voiceStripStatus[state="paused"], QLabel#voiceStripStatus[state="starting"] {{ color: {t.text_secondary}; }}
        QLabel#voiceStripGlyph {{ background: transparent; border: none; }}
        QPushButton#voiceStripButton {{
            min-height: 22px; max-height: 22px; min-width: 22px; max-width: 22px;
            padding: 0px;
            border-radius: {m.radius_chip}px;
            border: 1px solid transparent;
            background: {t.overlay_faint};
        }}
        QPushButton#voiceStripButton:hover {{
            background: {t.overlay_hover};
            border-color: {t.border_subtle};
        }}
        QPushButton#voiceStripButton:pressed {{ background: {t.overlay_active}; }}
    """


VOICE_STRIP_QSS: str = _build_strip_qss()


class LevelMeter(QWidget):
    """Five thin bars driven by a 0..1 level (mic while listening, playback
    while speaking). Rests as five faint dots when the level is zero."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._level = 0.0
        self._active = False
        self.setFixedSize(26, 16)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_level(self, level: float) -> None:
        value = max(0.0, min(1.0, float(level or 0.0)))
        if abs(value - self._level) < 0.02:
            return
        self._level = value
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        if not self._active:
            self._level = 0.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        bars = 5
        gap = 2.0
        bar_w = (self.width() - gap * (bars - 1)) / bars
        base = QColor(THEME.positive if self._active else THEME.text_faint)
        for index in range(bars):
            # Middle bars respond first so the meter reads as a waveform.
            weight = 1.0 - abs(index - (bars - 1) / 2.0) / (bars / 2.0)
            height = 3.0 + (self.height() - 3.0) * self._level * (0.45 + 0.55 * weight)
            color = QColor(base)
            color.setAlpha(110 if self._level <= 0.02 else 230)
            painter.setBrush(color)
            x = index * (bar_w + gap)
            y = (self.height() - height) / 2.0
            painter.drawRoundedRect(QRectF(x, y, bar_w, height), 1.5, 1.5)
        painter.end()


class VoiceStrip(QFrame):
    pause_toggled = pyqtSignal()
    stop_speech_requested = pyqtSignal()
    interrupt_requested = pyqtSignal()
    end_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("voiceStrip")
        self.setFixedHeight(VOICE_STRIP_HEIGHT)
        self._state = "off"

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(8)

        self.glyph = QLabel()
        self.glyph.setObjectName("voiceStripGlyph")
        self.glyph.setFixedSize(16, 16)
        row.addWidget(self.glyph, 0, Qt.AlignVCenter)

        self.meter = LevelMeter(self)
        row.addWidget(self.meter, 0, Qt.AlignVCenter)

        self.status = QLabel("")
        self.status.setObjectName("voiceStripStatus")
        self.status.setTextFormat(Qt.PlainText)
        row.addWidget(self.status, 1, Qt.AlignVCenter)

        def _button(name: str, icon: str, tooltip: str) -> QPushButton:
            button = QPushButton()
            button.setObjectName("voiceStripButton")
            button.setProperty("action", name)
            button.setIcon(symbol_icon(icon, color=THEME.text_secondary, size=14))
            button.setIconSize(QSize(14, 14))
            button.setFixedSize(22, 22)
            button.setToolTip(tooltip)
            button.setFocusPolicy(Qt.NoFocus)
            button.setCursor(Qt.PointingHandCursor)
            row.addWidget(button, 0, Qt.AlignVCenter)
            return button

        self.pause_button = _button("pause", "pause", "Pause the microphone")
        self.pause_button.clicked.connect(self.pause_toggled.emit)
        self.stop_button = _button("stop", "stop", "Stop speaking (Esc)")
        self.stop_button.clicked.connect(self.stop_speech_requested.emit)
        self.interrupt_button = _button("interrupt", "hand", "Stop the run (⌘.)")
        self.interrupt_button.clicked.connect(self.interrupt_requested.emit)
        self.end_button = _button("end", "x", "End the voice conversation (⌘⇧V)")
        self.end_button.clicked.connect(self.end_requested.emit)

        self.setStyleSheet(VOICE_STRIP_QSS)
        self.set_state("off")

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str, text: str = "") -> None:
        normalized = str(state or "off").strip().lower()
        glyph, tone, default_text = _STATE_VIEW.get(normalized, _STATE_VIEW["off"])
        self._state = normalized
        self.setProperty("state", normalized)
        self.status.setProperty("state", normalized)
        self.glyph.setPixmap(symbol_icon(glyph, color=tone, size=16).pixmap(16, 16))
        self.status.setText(str(text or default_text))
        self.status.setToolTip(str(text or default_text))
        self.meter.set_active(normalized in _METER_STATES)
        if normalized not in _METER_STATES:
            self.meter.set_level(0.0)
        self.pause_button.setVisible(normalized in {"listening", "heard", "paused"})
        self.pause_button.setIcon(
            symbol_icon("play" if normalized == "paused" else "pause", color=THEME.text_secondary, size=14)
        )
        self.pause_button.setToolTip("Resume the microphone" if normalized == "paused" else "Pause the microphone")
        self.stop_button.setVisible(normalized == "speaking")
        self.interrupt_button.setVisible(normalized == "thinking")
        refresh_style(self)
        refresh_style(self.status)

    def set_level(self, level: float) -> None:
        self.meter.set_level(level)


__all__ = ["LevelMeter", "VoiceStrip", "VOICE_STRIP_HEIGHT", "VOICE_STRIP_QSS"]
