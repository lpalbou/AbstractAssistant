"""Qt presentation of AbstractAvatar frames; generation belongs to the shared library."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from PyQt5.QtCore import QEvent, Qt, QTimer, QRectF, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPen, QPixmap, QPainter
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from ..theme import THEME


INSTALL_HINT = "AbstractAvatar ships with AbstractAssistant: reinstall AbstractAssistant to restore it."
_STATES = {"ready", "thinking", "working", "listening", "speaking", "waiting", "error"}


@dataclass(frozen=True)
class AvatarPresentation:
    state: str = "ready"
    level: float = 0.0
    bands: tuple[float, ...] | None = None


def audio_level(value: Any) -> float:
    """The renderer consumes a bounded scalar, including hosts with band meters."""
    if isinstance(value, (list, tuple)):
        values = [audio_level(item) for item in value[:32]]
        return max(values, default=0.0)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return min(1.0, max(0.0, number)) if math.isfinite(number) else 0.0


def presentation(*, error: bool = False, speaking: bool = False, listening: bool = False,
                 waiting: bool = False, working: bool = False, thinking: bool = False,
                 level: Any = 0.0) -> AvatarPresentation:
    for state, active in (("error", error), ("speaking", speaking), ("listening", listening),
                          ("waiting", waiting), ("working", working), ("thinking", thinking)):
        if active:
            return AvatarPresentation(state, audio_level(level),
                                      tuple(audio_level(v) for v in level) if isinstance(level, (list, tuple)) and len(level) == 8 else None)
    return AvatarPresentation()


def available_styles() -> tuple[list[dict[str, str]], str]:
    """Read the authoritative catalog, or return a visible installation error."""
    try:
        from abstractavatar import catalog

        rows = catalog()
        clean = [{"id": str(row["id"]), "name": str(row["name"]),
                  "description": str(row.get("description", ""))} for row in rows]
        if not clean:
            raise ValueError("The avatar catalog is empty.")
        return clean, ""
    except Exception as exc:
        return [], f"Avatars unavailable. {INSTALL_HINT} ({exc})"


def looks_at_pointer(style: str) -> bool:
    """Whether the design moves its eyes with a gaze (catalog `gaze`, AbstractAvatar 0.1.1).

    Only designs with eyes follow the pointer; for the others a gaze changes nothing in the frame,
    so the widget never sends one (and never redraws for a pointer move)."""
    from abstractavatar import catalog

    return any(str(row["id"]) == style and row["gaze"] == "eyes" for row in catalog())


class ActivityAvatar(QWidget):
    """One bounded native handle, owned and clocked only while this widget is visible."""

    failed = pyqtSignal()

    FRAME_SIZE = 96
    FRAME_INTERVAL_MS = 33  # Smooth 30 fps for every visible animated state.

    def __init__(self, state: Callable[[], AvatarPresentation], parent: Optional[QWidget] = None,
                 *, renderer_factory: Optional[Callable[..., Any]] = None, frame_size: int = 96) -> None:
        super().__init__(parent)
        self.FRAME_SIZE = max(32, int(frame_size))
        self._pixel_ratio = max(1.0, self.devicePixelRatioF())
        self._render_size = round(self.FRAME_SIZE * self._pixel_ratio)
        self.setObjectName("activityAvatar")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(self.FRAME_SIZE)
        self._state_provider = state
        self._factory = renderer_factory
        self._renderer = None
        self._enabled = False
        self._animated = True
        self._style = "watch-hover"
        self._error = ""
        self._last_frame = None
        self._last_draw_at = 0.0
        self._gaze = (0.0, 0.0)
        self._gaze_at = 0.0
        self._looks = False
        self._started = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._on_frame)
        self._image = QLabel(self)
        self._image.setAlignment(Qt.AlignCenter)
        self._image.setWordWrap(True)
        self._image.setTextFormat(Qt.PlainText)
        self._image.setObjectName("avatarFrame")
        self._image.setAccessibleName("Assistant avatar")
        self._image.setMouseTracking(True)
        self._image.installEventFilter(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._image)
        self.hide()

    @property
    def error(self) -> str:
        return self._error

    def configure(self, *, enabled: bool, style: str, animated: bool) -> None:
        changed = self._style != style
        self._enabled = bool(enabled)
        self._style = str(style)
        self._animated = bool(animated)
        if changed or not self._enabled:
            self.release()
        self._error = ""
        self._last_frame = None
        try:
            self._looks = self._enabled and looks_at_pointer(self._style)
        except Exception:
            # No catalog means no renderer either: the frame reports the missing install.
            self._looks = False
        self.setVisible(self._enabled)
        if self._enabled:
            self.refresh()

    def _ensure_renderer(self) -> bool:
        if self._renderer is not None:
            return True
        if self._error:
            return False
        try:
            factory = self._factory
            if factory is None:
                from abstractavatar import Renderer

                factory = Renderer
            renderer = factory(width=self._render_size, height=self._render_size)
            self._renderer = renderer
            def rgb(token):
                color = QColor(token)
                return color.red(), color.green(), color.blue()

            renderer.set_palette(warm=rgb(THEME.warning), eye=rgb(THEME.danger),
                                 dim=rgb(THEME.text_muted), ground=(*rgb(THEME.surface_sunken), 0))
            # Capture only the native owner, not the widget: QObject teardown must
            # release its handle even when no closeEvent is delivered.
            self.destroyed.connect(renderer.close)
            return True
        except Exception as exc:
            self._fail(exc)
            return False

    def _fail(self, error: Exception) -> None:
        self._error = f"Avatars unavailable. {INSTALL_HINT} ({error})"
        self.release()
        self._image.clear()
        self._image.setText("Avatar unavailable\nReinstall AbstractAssistant to restore it.")
        self._image.setToolTip(self._error)
        self._image.setAccessibleName(self._error)
        self.failed.emit()

    def _on_frame(self) -> None:
        # Timer delivery can jitter around its deadline. Never discard a scheduled frame:
        # applying the meter-event throttle here can halve the animation's frame rate.
        self.refresh(scheduled=True)

    def refresh(self, *, scheduled: bool = False) -> None:
        if not self._enabled or not self.isVisible() or not self._ensure_renderer():
            self._timer.stop()
            return
        try:
            current = self._state_provider()
            if current.state not in _STATES:
                raise ValueError(f"Unknown avatar state: {current.state}")
            animated = self._animated and current.state != "error"
            interval = self.FRAME_INTERVAL_MS
            if animated:
                if self._timer.interval() != interval:
                    self._timer.setInterval(interval)
                if not self._timer.isActive():
                    self._timer.start()
            else:
                self._timer.stop()
            now = time.monotonic()
            if (animated and not scheduled and self._last_frame is not None
                    and self._last_frame[:2] == (self._style, current.state)
                    and now - self._last_draw_at < interval / 1000):
                return  # Meter and pointer events cannot bypass the host frame budget.
            seconds = (now - self._started) % 86400 if animated else 0.0
            gaze = self._gaze if (animated and current.state == "ready"
                                  and time.monotonic() - self._gaze_at < 2) else (0.0, 0.0)
            level = audio_level(current.level) if animated else 0.0
            key = (self._style, current.state, level, seconds, gaze, current.bands)
            if key == self._last_frame:
                return
            pixels = self._renderer.render(style=self._style, state=current.state,
                                           level=level, time=seconds,
                                           gaze=gaze, transparent=True, bands=current.bands if animated else None)
            if len(pixels) != self._render_size * self._render_size * 4:
                raise ValueError("The avatar renderer returned an invalid frame size.")
            image = QImage(pixels, self._render_size, self._render_size,
                           self._render_size * 4, QImage.Format_RGBA8888).copy()
            image.setDevicePixelRatio(self._pixel_ratio)
            self._image.setPixmap(QPixmap.fromImage(image))
            label = f"Assistant avatar — {current.state.capitalize()}"
            self._image.setAccessibleName(label)
            self._image.setToolTip(f"{self._style} · {current.state.capitalize()}")
            self._last_frame = key
            self._last_draw_at = now
        except Exception as exc:
            self._fail(exc)

    def release(self) -> None:
        self._timer.stop()
        self._last_frame = None
        self._gaze = (0.0, 0.0)
        self._gaze_at = 0.0
        renderer, self._renderer = self._renderer, None
        if renderer is not None:
            try:
                self.destroyed.disconnect(renderer.close)
            except (TypeError, RuntimeError):
                pass
            renderer.close()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.release()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def restyle(self) -> None:
        self.release()
        self._last_frame = None
        self.refresh()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self._image and self._animated and self._enabled and self._looks:
            if event.type() == QEvent.MouseMove:
                half = self.FRAME_SIZE / 2
                self._gaze = (max(-1.0, min(1.0, (event.pos().x() - self._image.width() / 2) / half)),
                              max(-1.0, min(1.0, (event.pos().y() - half) / half)))
                self._gaze_at = time.monotonic()
                self.refresh()
            elif event.type() == QEvent.Leave:
                self._gaze = (0.0, 0.0)
                self._gaze_at = 0.0
                self.refresh()
        return super().eventFilter(watched, event)


class AvatarVoiceButton(QPushButton):
    """One voice action with an animated, state-driven avatar as its face."""

    def __init__(self, state: Callable[[], AvatarPresentation], parent=None):
        super().__init__(parent)
        self.setObjectName("avatarVoiceButton")
        self.setFixedSize(84, 96)
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.avatar = ActivityAvatar(state, self, frame_size=60)
        self.avatar.setFixedWidth(60)
        self.avatar.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.fallback = QLabel(self)
        self.fallback.setObjectName("avatarVoiceFallback")
        self.fallback.setAlignment(Qt.AlignCenter)
        self.fallback.setFixedSize(60, 60)
        self.fallback.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.caption = QLabel("Talk", self)
        self.caption.setObjectName("avatarVoiceCaption")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # Reserve equal space above/below the image: the orb itself stays
        # centered while a state label can appear above without moving it.
        self.avatar.move(12, 18)
        self.fallback.move(12, 18)
        self.caption.setFixedHeight(18)
        self.avatar.failed.connect(self.update_presentation)
        self.update_presentation()

    def update_presentation(self) -> None:
        from ..icons import symbol_icon

        use_avatar = self.avatar._enabled and not self.avatar.error
        self.avatar.setVisible(use_avatar)
        self.fallback.setVisible(not use_avatar)
        if not use_avatar:
            self.fallback.setPixmap(symbol_icon("audio-lines", color=THEME.text_primary, size=24).pixmap(24, 24))
        state = self.avatar._state_provider().state.capitalize()
        label = {"Listening": "Listening", "Speaking": "Speaking", "Thinking": "Thinking", "Working": "Thinking"}.get(state, "")
        self.caption.setText(label)
        self.caption.setFixedWidth(min(84, self.caption.sizeHint().width() + 8))
        self.caption.move((self.width() - self.caption.width()) // 2, 0)
        self.caption.setVisible(bool(label))
        # One name; the checked state (a voice conversation or dictation is on) and the
        # description say the rest (operator rule: toggles show state, never swap verbs).
        self.setAccessibleName("Voice")
        self.setAccessibleDescription(f"Assistant: {state}. {self.toolTip()} {self.avatar.error}".strip())

    # The floating orb's own backdrop, so the orb and its state label read over
    # any window behind the palette (a white web page, a dark desktop) in every
    # theme. In a light theme the card surface is itself near white, so the panel
    # is the card surface pulled toward the theme's ink (a tone that differs from
    # white, and from black in a dark theme) with a hairline edge in that ink.
    # It stays lighter than the composer panel beside it, inside the button's own
    # rect only (it never covers the composer), with the radius of the button's
    # keyboard-focus outline.
    BACKDROP_OPACITY = 0.82
    BACKDROP_INK_MIX = 0.14
    BACKDROP_EDGE_ALPHA = 0.34
    BACKDROP_RADIUS = 24.0

    @staticmethod
    def _token_rgb(token: str, fallback: tuple) -> tuple:
        from ..retint import parse_color

        parsed = parse_color(str(token or ""))
        return tuple(int(v) for v in parsed[0]) if parsed else fallback

    def backdrop_color(self) -> QColor:
        surface = self._token_rgb(THEME.surface_card, self._token_rgb(THEME.surface_raised, (16, 22, 31)))
        ink = self._token_rgb(THEME.text_primary, (237, 242, 248))
        mix = self.BACKDROP_INK_MIX
        color = QColor(*(round(s * (1 - mix) + i * mix) for s, i in zip(surface, ink)))
        color.setAlphaF(self.BACKDROP_OPACITY)
        return color

    def backdrop_edge_color(self) -> QColor:
        color = QColor(*self._token_rgb(THEME.text_primary, (237, 242, 248)))
        color.setAlphaF(self.BACKDROP_EDGE_ALPHA)
        return color

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(self.backdrop_edge_color(), 1.0))
        painter.setBrush(self.backdrop_color())
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                                self.BACKDROP_RADIUS, self.BACKDROP_RADIUS)
        painter.end()
        super().paintEvent(event)
        # macOS uses window alpha for native hit testing; the backdrop makes the
        # whole button opaque enough, so a wire avatar's transparent centre does
        # not send clicks to the window below.

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._set_keyboard_focus(event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason))
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._set_keyboard_focus(False)
        super().focusOutEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._set_keyboard_focus(False)
        super().mousePressEvent(event)

    def _set_keyboard_focus(self, visible: bool) -> None:
        self.setProperty("keyboardFocus", "true" if visible else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.avatar._looks and self.avatar._animated:
            point = self.avatar.mapFrom(self, event.pos())
            half = self.avatar.FRAME_SIZE / 2
            self.avatar._gaze = (max(-1.0, min(1.0, (point.x() - half) / half)),
                                 max(-1.0, min(1.0, (point.y() - half) / half)))
            self.avatar._gaze_at = time.monotonic()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.avatar._gaze = (0.0, 0.0)
        self.avatar._gaze_at = 0.0
        super().leaveEvent(event)
