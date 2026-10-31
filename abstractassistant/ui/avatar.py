"""Qt presentation of AbstractAvatar frames; generation belongs to the shared library."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtGui import QColor, QImage, QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from ..theme import THEME


INSTALL_HINT = "Install AbstractAssistant's avatar extra to enable procedural avatars."
_STATES = {"ready", "thinking", "working", "listening", "speaking", "waiting", "error"}


@dataclass(frozen=True)
class AvatarPresentation:
    state: str = "ready"
    level: float = 0.0


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
            return AvatarPresentation(state, audio_level(level))
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


class ActivityAvatar(QWidget):
    """One bounded native handle, owned and clocked only while this widget is visible."""

    FRAME_SIZE = 96

    def __init__(self, state: Callable[[], AvatarPresentation], parent: Optional[QWidget] = None,
                 *, renderer_factory: Optional[Callable[..., Any]] = None) -> None:
        super().__init__(parent)
        self.setObjectName("activityAvatar")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(self.FRAME_SIZE)
        self._state_provider = state
        self._factory = renderer_factory
        self._renderer = None
        self._enabled = False
        self._animated = True
        self._style = "halo"
        self._error = ""
        self._last_frame = None
        self._last_draw_at = 0.0
        self._gaze = (0.0, 0.0)
        self._gaze_at = 0.0
        self._started = time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
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
            renderer = factory(width=self.FRAME_SIZE, height=self.FRAME_SIZE)
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
        self._image.setText("Avatar unavailable\nEnable it after installing the avatar extra.")
        self._image.setToolTip(self._error)
        self._image.setAccessibleName(self._error)

    def refresh(self) -> None:
        if not self._enabled or not self.isVisible() or not self._ensure_renderer():
            self._timer.stop()
            return
        try:
            current = self._state_provider()
            if current.state not in _STATES:
                raise ValueError(f"Unknown avatar state: {current.state}")
            animated = self._animated and current.state != "error"
            interval = 500 if current.state == "ready" else 167 if current.state == "waiting" else 84
            if animated:
                if self._timer.interval() != interval:
                    self._timer.setInterval(interval)
                if not self._timer.isActive():
                    self._timer.start()
            else:
                self._timer.stop()
            now = time.monotonic()
            if (animated and self._last_frame is not None
                    and self._last_frame[:2] == (self._style, current.state)
                    and now - self._last_draw_at < interval / 1000):
                return  # Meter and pointer events cannot bypass the host frame budget.
            seconds = (now - self._started) % 86400 if animated else 0.0
            gaze = self._gaze if (animated and current.state == "ready"
                                  and time.monotonic() - self._gaze_at < 2) else (0.0, 0.0)
            level = audio_level(current.level) if animated else 0.0
            key = (self._style, current.state, level, seconds, gaze)
            if key == self._last_frame:
                return
            pixels = self._renderer.render(style=self._style, state=current.state,
                                           level=level, time=seconds,
                                           gaze=gaze, transparent=True)
            if len(pixels) != self.FRAME_SIZE * self.FRAME_SIZE * 4:
                raise ValueError("The avatar renderer returned an invalid frame size.")
            image = QImage(pixels, self.FRAME_SIZE, self.FRAME_SIZE,
                           self.FRAME_SIZE * 4, QImage.Format_RGBA8888).copy()
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
        if watched is self._image and self._animated and self._enabled:
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
