"""
Qt-based chat bubble for AbstractAssistant.

A simple, modern chat bubble using PyQt5/PySide2 that opens near the system tray.
"""

import sys
import threading
import time
import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

# Import AbstractVoice-compatible TTS manager (required dependency)
from ..core.agent_host import AgentHost

try:
    # Voice backend (AbstractVoice; installed with `abstractassistant`).
    from ..core.tts_manager import VoiceManager  # type: ignore

    TTS_AVAILABLE = True
except Exception:
    VoiceManager = None  # type: ignore[assignment]
    TTS_AVAILABLE = False

# Import our new manager classes (required dependencies)
from .provider_manager import ProviderManager
from .ui_styles import UIStyles
from .tts_state_manager import TTSStateManager, TTSState
from .history_dialog import iPhoneMessagesDialog

# Provider/model managers are package-local.
MANAGERS_AVAILABLE = True

try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QTextEdit, QPushButton, QComboBox, QLabel, QFrame,
        QFileDialog, QMessageBox, QInputDialog, QCheckBox, QDialog, QMenu,
        QLineEdit, QScrollArea, QSizePolicy, QButtonGroup
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot, QRect, QMetaObject, QEvent
    from PyQt5.QtGui import QFont, QPalette, QColor
    from PyQt5.QtCore import QPoint
    QT_AVAILABLE = "PyQt5"
except ImportError:
    try:
        from PySide2.QtWidgets import (
            QApplication, QWidget, QVBoxLayout, QHBoxLayout,
            QTextEdit, QPushButton, QComboBox, QLabel, QFrame,
            QFileDialog, QMessageBox, QInputDialog, QCheckBox, QDialog, QMenu,
            QLineEdit, QScrollArea, QSizePolicy, QButtonGroup
        )
        from PySide2.QtCore import Qt, QTimer, Signal as pyqtSignal, QThread, Slot as pyqtSlot, QMetaObject, QEvent
        from PySide2.QtGui import QFont, QPalette, QColor
        from PySide2.QtCore import QPoint
        QT_AVAILABLE = "PySide2"
    except ImportError:
        try:
            from PyQt6.QtWidgets import (
                QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                QTextEdit, QPushButton, QComboBox, QLabel, QFrame,
                QFileDialog, QMessageBox, QInputDialog, QCheckBox, QDialog, QMenu,
                QLineEdit, QScrollArea, QSizePolicy, QButtonGroup
            )
            from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot, QEvent
            from PyQt6.QtGui import QFont, QPalette, QColor
            from PyQt6.QtCore import QPoint
            QT_AVAILABLE = "PyQt6"
        except ImportError:
            QT_AVAILABLE = None


class TTSToggle(QPushButton):
    """TTS toggle button with speaker icon (simple on/off)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 24)
        self.setToolTip("Speaker (TTS)")
        self.setCheckable(True)
        self._tts_state = "idle"  # 'idle', 'speaking', 'paused'
        try:
            self.toggled.connect(lambda _=False: self._update_appearance())
        except Exception:
            pass
        self._update_appearance()

    def is_enabled(self) -> bool:
        return bool(self.isChecked())

    def set_enabled(self, enabled: bool):
        self.setChecked(bool(enabled))
        self._update_appearance()

    def set_tts_state(self, state: str):
        state_norm = str(state or "").strip().lower()
        if state_norm not in {"idle", "speaking", "paused"}:
            state_norm = "idle"
        if self._tts_state != state_norm:
            self._tts_state = state_norm
            self._update_appearance()

    def get_tts_state(self) -> str:
        return str(self._tts_state or "idle")

    def _update_appearance(self):
        enabled = bool(self.isChecked())
        state = "idle" if not enabled else str(self._tts_state or "idle")

        # Set icon text based on state
        if not enabled:
            icon = "🔇"  # Muted speaker when disabled
            bg_color = "rgba(255, 255, 255, 0.06)"
            text_color = "rgba(255, 255, 255, 0.7)"
        elif state == "speaking":
            icon = "🔊"  # Loud speaker when speaking
            bg_color = "rgba(0, 170, 0, 0.8)"  # Green
            text_color = "#ffffff"
        elif state == "paused":
            icon = "⏸️"  # Pause when paused
            bg_color = "rgba(255, 136, 0, 0.8)"  # Orange
            text_color = "#ffffff"
        else:
            icon = "🔉"  # Medium speaker when idle but enabled
            bg_color = "rgba(0, 102, 204, 0.8)"  # Blue
            text_color = "#ffffff"

        self.setText(icon)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                border: none;
                border-radius: 12px;
                font-size: 12px;
                color: {text_color};
                font-family: -apple-system, system-ui, sans-serif;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {bg_color.replace('0.8', '1.0') if '0.8' in bg_color else bg_color};
            }}
            QPushButton:pressed {{
                background: {bg_color.replace('0.8', '0.6') if '0.8' in bg_color else bg_color};
            }}
        """)


class FullVoiceToggle(QPushButton):
    """Full Voice Mode toggle button with microphone icon."""

    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 24)  # Slightly wider for button
        self.setToolTip("Full Voice Mode: Continuous listening with speech-to-text and text-to-speech")
        self._enabled = False
        self._listening_state = 'idle'  # 'idle', 'listening', 'processing'
        self.setCheckable(True)
        self.clicked.connect(self._on_clicked)
        self._update_appearance()

    def is_enabled(self) -> bool:
        """Check if Full Voice Mode is enabled."""
        return self._enabled

    def _on_clicked(self):
        """Handle button click."""
        self._enabled = self.isChecked()
        self.toggled.emit(self._enabled)
        self._update_appearance()

    def set_enabled(self, enabled: bool):
        """Set Full Voice Mode enabled state."""
        if self._enabled != enabled:
            self._enabled = enabled
            self.setChecked(enabled)
            self._update_appearance()
            if not enabled:
                self.toggled.emit(enabled)

    def set_listening_state(self, state: str):
        """Set listening state for visual feedback.

        Args:
            state: One of 'idle', 'listening', 'processing'
        """
        if self._listening_state != state:
            self._listening_state = state
            self._update_appearance()

    def get_listening_state(self) -> str:
        """Get current listening state."""
        return self._listening_state


    def _update_appearance(self):
        """Update button appearance based on state."""
        # Set icon text based on state
        if not self._enabled:
            icon = "🎤"  # Microphone when disabled
            bg_color = "rgba(255, 255, 255, 0.06)"
            text_color = "rgba(255, 255, 255, 0.7)"
        elif self._listening_state == 'listening':
            icon = "🔴"  # Red circle when actively listening
            bg_color = "rgba(255, 107, 53, 0.8)"  # Orange
            text_color = "#ffffff"
        elif self._listening_state == 'processing':
            icon = "⚡"  # Lightning when processing
            bg_color = "rgba(255, 165, 0, 0.8)"  # Yellow
            text_color = "#ffffff"
        else:
            icon = "🎙️"  # Studio microphone when enabled but idle
            bg_color = "rgba(0, 122, 204, 0.8)"  # Blue
            text_color = "#ffffff"

        self.setText(icon)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                border: none;
                border-radius: 12px;
                font-size: 12px;
                color: {text_color};
                font-family: -apple-system, system-ui, sans-serif;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {bg_color.replace('0.8', '1.0') if '0.8' in bg_color else bg_color};
            }}
            QPushButton:pressed {{
                background: {bg_color.replace('0.8', '0.6') if '0.8' in bg_color else bg_color};
            }}
        """)




class _SessionRow(QFrame):
    def __init__(
        self,
        *,
        session_id: str,
        short_date: str,
        title: str,
        msg_count: int,
        file_count: int,
        tool_count: int,
        is_active: bool,
        on_select: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._session_id = str(session_id or "")
        self._on_select = on_select

        self.setObjectName("sessionRowActive" if is_active else "sessionRow")

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        date_label = QLabel(str(short_date or ""))
        date_label.setFixedWidth(92)
        try:
            date_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        except Exception:
            try:
                date_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # type: ignore[attr-defined]
            except Exception:
                pass
        date_label.setObjectName("sessionRowDate")
        row.addWidget(date_label)

        title_label = QLabel(str(title or "New session"))
        title_label.setObjectName("sessionRowTitle")
        title_label.setWordWrap(False)
        row.addWidget(title_label, 1)

        def _stat(value: int) -> QLabel:
            lbl = QLabel(str(int(value)))
            lbl.setFixedWidth(52)
            try:
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            except Exception:
                try:
                    lbl.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
                except Exception:
                    pass
            lbl.setObjectName("sessionRowStat")
            return lbl

        row.addWidget(_stat(msg_count))
        row.addWidget(_stat(file_count))
        row.addWidget(_stat(tool_count))

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                if callable(self._on_select):
                    self._on_select(self._session_id)
        except Exception:
            pass
        try:
            super().mousePressEvent(event)
        except Exception:
            pass


class SessionsDialog(QDialog):
    def __init__(self, *, parent: QWidget, bubble: "QtChatBubble"):
        super().__init__(parent)
        self._bubble = bubble

        self.setWindowTitle("Sessions")
        self.setModal(True)
        self.resize(640, 460)

        palette = QApplication.instance().palette() if QApplication.instance() else self.palette()
        is_dark = palette.window().color().lightness() < 128
        window_bg = palette.window().color().name()
        text = palette.text().color()
        accent = palette.highlight().color()

        def rgba(color: QColor, alpha: float) -> str:
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

        overlay = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.06)"
        overlay_hover = "rgba(255, 255, 255, 0.12)" if is_dark else "rgba(0, 0, 0, 0.10)"
        overlay_pressed = "rgba(255, 255, 255, 0.06)" if is_dark else "rgba(0, 0, 0, 0.04)"
        text_primary = rgba(text, 0.92)
        text_secondary = rgba(text, 0.70)
        text_muted = rgba(text, 0.55 if is_dark else 0.50)
        accent_hex = accent.name()

        self.setStyleSheet(
            f"""
            QDialog {{
                background: {window_bg};
                color: {text_primary};
                border-radius: 14px;
            }}

            QFrame#sessionRow {{
                background: {overlay};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }}
            QFrame#sessionRow:hover {{
                background: {overlay_hover};
            }}
            QFrame#sessionRowActive {{
                background: rgba(0, 122, 255, 0.18);
                border: 1px solid rgba(0, 122, 255, 0.35);
                border-radius: 10px;
            }}

            QLabel#sessionRowDate {{
                font-size: 11px;
                color: {text_muted};
            }}
            QLabel#sessionRowTitle {{
                font-size: 12px;
                font-weight: 600;
                color: {text_primary};
            }}
            QLabel#sessionRowStat {{
                font-size: 11px;
                color: {text_secondary};
            }}

            QPushButton#sessionsPill {{
                background: {overlay_pressed};
                border: none;
                border-radius: 11px;
                font-size: 11px;
                font-weight: 700;
                color: {text_primary};
                padding: 0 12px;
                min-height: 26px;
            }}
            QPushButton#sessionsPill:hover {{
                background: {overlay_hover};
            }}
            QPushButton#sessionsPill:pressed {{
                background: {overlay_pressed};
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)

        header = QLabel("SESSIONS")
        header.setStyleSheet(f"QLabel {{ color: {accent_hex}; font-size: 11px; font-weight: 800; }}")
        header_row.addWidget(header)
        header_row.addStretch()

        new_btn = QPushButton("New session")
        new_btn.setObjectName("sessionsPill")
        new_btn.clicked.connect(self._on_new_session)
        header_row.addWidget(new_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("sessionsPill")
        close_btn.clicked.connect(self.reject)
        header_row.addWidget(close_btn)

        layout.addLayout(header_row)

        subtitle = QLabel("Date | Title | #Msgs | #Files | #Tools")
        subtitle.setStyleSheet(f"QLabel {{ font-size: 12px; color: {text_secondary}; }}")
        layout.addWidget(subtitle)

        col = QFrame()
        col.setStyleSheet("QFrame { background: transparent; border: none; }")
        col_row = QHBoxLayout(col)
        col_row.setContentsMargins(12, 0, 12, 0)
        col_row.setSpacing(10)

        def _hdr(text: str, width: int, align_center: bool = False) -> QLabel:
            lbl = QLabel(text)
            lbl.setFixedWidth(width)
            try:
                if align_center:
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            except Exception:
                pass
            lbl.setStyleSheet(f"QLabel {{ font-size: 10px; font-weight: 800; color: {text_muted}; }}")
            return lbl

        col_row.addWidget(_hdr("DATE", 92, False))
        title_hdr = QLabel("TITLE")
        title_hdr.setStyleSheet(f"QLabel {{ font-size: 10px; font-weight: 800; color: {text_muted}; }}")
        col_row.addWidget(title_hdr, 1)
        col_row.addWidget(_hdr("MSGS", 52, True))
        col_row.addWidget(_hdr("FILES", 52, True))
        col_row.addWidget(_hdr("TOOLS", 52, True))
        layout.addWidget(col)

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        try:
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        except Exception:
            try:
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore[attr-defined]
            except Exception:
                pass
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(self._rows_container)
        layout.addWidget(scroll, 1)

        self.refresh()

    def _on_new_session(self):
        try:
            self._bubble._start_new_session()
        except Exception:
            pass
        self.refresh()

    def _on_select(self, session_id: str) -> None:
        bubble = self._bubble
        if getattr(bubble, "_is_run_in_progress", lambda: False)():
            QMessageBox.information(self, "Session switch", "Please wait for the current response to finish.")
            return
        try:
            bubble._switch_session_via_combo(str(session_id or "").strip())
        except Exception:
            pass
        self.accept()

    @staticmethod
    def _tool_name_from_message(message: Dict[str, Any]) -> str:
        meta = message.get("metadata")
        if isinstance(meta, dict):
            name = meta.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        import re

        content = str(message.get("content") or "")
        match = re.match(r"\\s*\\[([^\\]]+)\\]:", content)
        if match:
            return str(match.group(1) or "").strip()
        return ""

    @staticmethod
    def _extract_file_paths(text: str) -> List[str]:
        import re

        raw = str(text or "")
        candidates: List[str] = []
        candidates.extend(re.findall(r"file://[^\\s)\\]\"'<>]+", raw))
        candidates.extend(re.findall(r"[A-Za-z]:\\\\[^\\s\"'<>]+", raw))
        candidates.extend(re.findall(r"(?:~|/)[^\\s\"'<>]+", raw))

        out: List[str] = []
        for p in candidates:
            cleaned = str(p).strip().rstrip(").,;]\"'")
            if cleaned:
                out.append(cleaned)

        seen: set[str] = set()
        deduped: List[str] = []
        for p in out:
            if p in seen:
                continue
            seen.add(p)
            deduped.append(p)
        return deduped

    def _session_stats(self, session_id: str) -> Dict[str, int]:
        bubble = self._bubble
        llm = getattr(bubble, "llm_manager", None)
        if llm is None:
            return {"msgs": 0, "files": 0, "tools": 0}

        data_dir = None
        try:
            idx = getattr(llm, "_session_index", None)
            if idx is None and hasattr(llm, "data_dir"):
                from ..core.session_index import SessionIndex

                idx = SessionIndex(Path(getattr(llm, "data_dir")))
            if idx is not None and hasattr(idx, "data_dir_for"):
                data_dir = idx.data_dir_for(str(session_id))
        except Exception:
            data_dir = None

        if data_dir is None:
            try:
                data_dir = Path(getattr(llm, "data_dir"))
            except Exception:
                data_dir = None
        if data_dir is None:
            return {"msgs": 0, "files": 0, "tools": 0}

        try:
            from ..core.session_store import SessionStore

            snap = SessionStore(Path(data_dir) / "session.json").load()
        except Exception:
            snap = None

        messages = list(getattr(snap, "messages", []) or []) if snap is not None else []
        msg_count = 0
        tool_msgs: List[Dict[str, Any]] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "").strip()
            if role == "tool":
                tool_msgs.append(m)
            elif role in {"user", "assistant"}:
                msg_count += 1

        tool_count = len(tool_msgs)
        files: set[str] = set()
        for m in tool_msgs:
            name = self._tool_name_from_message(m)
            if name != "open_attachment":
                continue
            for p in self._extract_file_paths(str(m.get("content") or "")):
                files.add(p)

        return {"msgs": int(msg_count), "files": int(len(files)), "tools": int(tool_count)}

    @staticmethod
    def _short_date(stamp: str) -> str:
        raw = str(stamp or "").strip()
        if not raw:
            return ""
        try:
            dt = datetime.fromisoformat(raw)
            return dt.astimezone().strftime("%b %d %H:%M")
        except Exception:
            return raw[:16]

    def refresh(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        llm = getattr(self._bubble, "llm_manager", None)
        sessions: List[Dict[str, Any]] = []
        if llm is not None and hasattr(llm, "list_sessions"):
            try:
                sessions = list(llm.list_sessions() or [])
            except Exception:
                sessions = []

        active_id = str(getattr(llm, "active_session_id", "") or "").strip() if llm is not None else ""

        def _key(rec: Dict[str, Any]) -> str:
            u = str(rec.get("updated_at") or "").strip()
            c = str(rec.get("created_at") or "").strip()
            return u or c

        sessions = [s for s in sessions if isinstance(s, dict)]
        sessions.sort(key=_key, reverse=True)

        if not sessions:
            empty = QLabel("No sessions found.")
            empty.setStyleSheet("QLabel { color: rgba(255,255,255,0.65); font-size: 12px; }")
            self._rows_layout.addWidget(empty)
            self._rows_layout.addStretch()
            return

        for rec in sessions:
            sid = str(rec.get("session_id") or "").strip()
            if not sid:
                continue
            title = str(rec.get("title") or "New session").strip() or "New session"
            short_date = self._short_date(str(rec.get("updated_at") or rec.get("created_at") or ""))
            stats = self._session_stats(sid)
            row = _SessionRow(
                session_id=sid,
                short_date=short_date,
                title=title,
                msg_count=int(stats.get("msgs", 0)),
                file_count=int(stats.get("files", 0)),
                tool_count=int(stats.get("tools", 0)),
                is_active=bool(active_id and sid == active_id),
                on_select=self._on_select,
                parent=self._rows_container,
            )
            self._rows_layout.addWidget(row)

        self._rows_layout.addStretch()


class ToolSelectorDialog(QDialog):
    """Tool allowlist editor (All tools vs Custom allowlist)."""

    def __init__(
        self,
        *,
        parent: Optional[QWidget] = None,
        tools: List[Dict[str, str]],
        enabled: set[str],
        safe_preset: set[str],
        require_approval: set[str],
        session_auto_approve: Optional[set[str]] = None,
        session_force_ask: Optional[set[str]] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Tools")
        self.setModal(True)

        self._tools = [t for t in list(tools) if isinstance(t, dict)]
        self._safe_preset = set(safe_preset)
        self._require_approval = set(require_approval)
        self._session_auto_approve = set(session_auto_approve or set())
        self._session_force_ask = set(session_force_ask or set())

        # Keep the tool order stable.
        self._all_names = [
            str(t.get("name") or "").strip()
            for t in self._tools
            if isinstance(t.get("name"), str) and str(t.get("name") or "").strip()
        ]
        self._all_names_set = set(self._all_names)

        self._mode: str = "all" if set(enabled) == self._all_names_set else "custom"
        self._custom_selected: set[str] = set(enabled)
        if self._mode == "all":
            self._custom_selected = set(self._all_names_set)

        palette = QApplication.instance().palette() if QApplication.instance() else self.palette()
        is_dark = palette.window().color().lightness() < 128
        window_bg = palette.window().color().name()
        base_bg = palette.base().color().name()
        mid = palette.mid().color()
        mid_hex = mid.name()
        text = palette.text().color()
        accent = palette.highlight().color()

        def rgba(color: QColor, alpha: float) -> str:
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

        overlay = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.06)"
        overlay_hover = "rgba(255, 255, 255, 0.12)" if is_dark else "rgba(0, 0, 0, 0.10)"
        overlay_pressed = "rgba(255, 255, 255, 0.06)" if is_dark else "rgba(0, 0, 0, 0.04)"
        text_primary = rgba(text, 0.92)
        text_secondary = rgba(text, 0.70)
        text_muted = rgba(text, 0.55 if is_dark else 0.50)
        accent_hex = accent.name()
        accent_hover = accent.lighter(115).name()
        accent_pressed = accent.darker(115).name()
        accent_border = rgba(accent, 0.28)
        danger = QColor(255, 59, 48)
        danger_border = rgba(danger, 0.45)
        tool_name_color = "#22c55e" if is_dark else "#16a34a"
        indicator_border = rgba(text, 0.38 if is_dark else 0.30)

        self._suppress_checkbox_updates: bool = False

        self.setStyleSheet(
            f"""
            QDialog {{
                background: {window_bg};
                color: {text_primary};
                border-radius: 14px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QLabel("TOOLS")
        header.setStyleSheet(
            f"""
            QLabel {{
                color: {accent_hex};
                font-size: 11px;
                font-weight: 700;
            }}
            """
        )
        layout.addWidget(header)

        subtitle = QLabel("Default is all tools. Switch to a custom allowlist only when needed.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"QLabel {{ font-size: 12px; color: {text_secondary}; }}")
        layout.addWidget(subtitle)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)

        seg_frame = QFrame()
        seg_frame.setStyleSheet(
            f"""
            QFrame {{
                background: {overlay_pressed};
                border: 1px solid {mid_hex};
                border-radius: 14px;
            }}
            """
        )
        seg_layout = QHBoxLayout(seg_frame)
        seg_layout.setContentsMargins(2, 2, 2, 2)
        seg_layout.setSpacing(2)

        self.all_mode_btn = QPushButton("All tools")
        self.custom_mode_btn = QPushButton("Custom allowlist")
        for b in (self.all_mode_btn, self.custom_mode_btn):
            b.setCheckable(True)
            try:
                b.setAutoExclusive(True)
            except Exception:
                pass
            b.setFixedHeight(28)
            b.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-radius: 12px;
                    padding: 0 12px;
                    font-size: 12px;
                    font-weight: 600;
                    color: {text_secondary};
                }}
                QPushButton:hover {{ background: {overlay_hover}; color: {text_primary}; }}
                QPushButton:checked {{ background: {base_bg}; color: {text_primary}; }}
                """
            )
        self.all_mode_btn.setChecked(self._mode == "all")
        self.custom_mode_btn.setChecked(self._mode == "custom")

        seg_layout.addWidget(self.all_mode_btn)
        seg_layout.addWidget(self.custom_mode_btn)
        controls_row.addWidget(seg_frame)

        self.count_pill = QLabel("")
        self.count_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_pill.setFixedHeight(28)
        self.count_pill.setMinimumWidth(160)
        self.count_pill.setStyleSheet(
            f"""
            QLabel {{
                background: {overlay};
                border: 1px solid {mid_hex};
                border-radius: 14px;
                font-size: 11px;
                font-weight: 600;
                color: {text_secondary};
                padding: 0 12px;
            }}
            """
        )
        controls_row.addWidget(self.count_pill)

        bulk_btn_qss = f"""
            QPushButton {{
                background: {overlay};
                border: 1px solid {mid_hex};
                border-radius: 14px;
                padding: 0 12px;
                font-size: 11px;
                font-weight: 700;
                color: {text_secondary};
            }}
            QPushButton:hover {{
                background: {overlay_hover};
                border: 1px solid {accent_hex};
                color: {text_primary};
            }}
            QPushButton:pressed {{
                background: {overlay_pressed};
            }}
        """

        controls_row.addStretch()
        select_all_btn = QPushButton("Select all")
        select_all_btn.setFixedHeight(28)
        select_all_btn.setStyleSheet(bulk_btn_qss)
        controls_row.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select none")
        select_none_btn.setFixedHeight(28)
        select_none_btn.setStyleSheet(bulk_btn_qss)
        controls_row.addWidget(select_none_btn)
        layout.addLayout(controls_row)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter tools…")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setFixedHeight(34)
        self.filter_input.setStyleSheet(
            f"""
            QLineEdit {{
                background: {overlay_pressed};
                border: 1px solid {mid_hex};
                border-radius: 10px;
                padding: 0 12px;
                font-size: 12px;
                color: {text_primary};
            }}
            QLineEdit:focus {{
                border: 1px solid {accent_hex};
                background: {overlay_hover};
            }}
            """
        )
        layout.addWidget(self.filter_input)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        layout.addWidget(scroll, 1)

        list_root = QWidget()
        list_layout = QVBoxLayout(list_root)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)
        scroll.setWidget(list_root)

        self._rows: Dict[str, Dict[str, Any]] = {}

        def _badge(text_value: str, *, fg: str, bg: str, border: str) -> QLabel:
            lab = QLabel(text_value)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setFixedHeight(18)
            lab.setStyleSheet(
                f"""
                QLabel {{
                    color: {fg};
                    background: {bg};
                    border: 1px solid {border};
                    border-radius: 9px;
                    padding: 0 8px;
                    font-size: 10px;
                    font-weight: 700;
                }}
                """
            )
            return lab

        def _current_selected() -> set[str]:
            return {n for n, info in self._rows.items() if info["checkbox"].isChecked()}

        def _on_checkbox_changed(_: str) -> None:
            if getattr(self, "_suppress_checkbox_updates", False):
                return

            selected = _current_selected()

            # In "All tools" mode, any manual uncheck means the user is starting
            # a custom allowlist. Flip to custom and keep current selection.
            if self._mode == "all" and selected != self._all_names_set:
                self._custom_selected = set(selected)
                _set_mode("custom")
                return

            if self._mode == "custom":
                self._custom_selected = set(selected)

            self._update_counts()

        for info in self._tools:
            name = str(info.get("name") or "").strip()
            if not name:
                continue
            desc = str(info.get("description") or "").strip()

            row = QFrame()
            row.setObjectName("toolRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(10)

            cb = QPushButton("✓")
            cb.setCheckable(True)
            cb.setChecked(name in self._custom_selected)
            cb.setFixedSize(22, 22)
            try:
                cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            except Exception:
                try:
                    cb.setFocusPolicy(Qt.NoFocus)  # type: ignore[attr-defined]
                except Exception:
                    pass
            try:
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
            except Exception:
                try:
                    cb.setCursor(Qt.PointingHandCursor)  # type: ignore[attr-defined]
                except Exception:
                    pass
            cb.setStyleSheet(
                f"""
                QPushButton {{
                    background: {overlay_pressed};
                    border: 1px solid {indicator_border};
                    border-radius: 6px;
                    padding: 0px;
                    color: transparent;
                    font-size: 14px;
                    font-weight: 900;
                    text-align: center;
                }}
                QPushButton:hover {{
                    background: {overlay_hover};
                    border: 1px solid {accent_hex};
                }}
                QPushButton:checked {{
                    background: {accent_hex};
                    border: 1px solid {accent_hover};
                    color: #ffffff;
                }}
                QPushButton:checked:hover {{
                    background: {accent_hover};
                    border: 1px solid {accent_hover};
                }}
                QPushButton:checked:pressed {{
                    background: {accent_pressed};
                    border: 1px solid {accent_pressed};
                }}
                """
            )
            cb.toggled.connect(lambda _checked=False, n=name: _on_checkbox_changed(n))
            row_layout.addWidget(cb, 0, Qt.AlignmentFlag.AlignTop)

            text_col = QWidget()
            text_col_layout = QVBoxLayout(text_col)
            text_col_layout.setContentsMargins(6, 0, 0, 0)
            text_col_layout.setSpacing(4)

            meta_row = QHBoxLayout()
            meta_row.setContentsMargins(0, 0, 0, 0)
            meta_row.setSpacing(8)

            name_label = QLabel(name.upper())
            name_label.setStyleSheet(
                f"""
                QLabel {{
                    color: {tool_name_color};
	                font-size: 12px;
                    font-weight: 800;
                    font-family: "SF Mono", "Monaco", "Menlo", "Consolas", monospace;
                }}
                """
            )
            meta_row.addWidget(name_label)

            if name in self._require_approval:
                meta_row.addWidget(
                    _badge("APPROVAL", fg="#ffffff", bg=danger_border, border=danger_border)
                )

            meta_row.addStretch()
            text_col_layout.addLayout(meta_row)

            if desc:
                desc_label = QLabel(desc)
                desc_label.setWordWrap(True)
                desc_label.setStyleSheet(f"QLabel {{ color: {text_muted}; font-size: 11px; }}")
                text_col_layout.addWidget(desc_label)

            row_layout.addWidget(text_col, 1)

            approval_combo = QComboBox()
            approval_combo.addItems(["Approve", "Ask"])
            approval_combo.setFixedHeight(28)
            approval_combo.setMinimumWidth(110)
            approval_combo.setStyleSheet(
                f"""
                QComboBox {{
                    background: {overlay_pressed};
                    border: 1px solid {mid_hex};
                    border-radius: 10px;
                    padding: 0 10px;
                    font-size: 12px;
                    font-weight: 700;
                    color: {text_primary};
                }}
                QComboBox:hover {{
                    background: {overlay_hover};
                    border: 1px solid {accent_hex};
                }}
                QComboBox:focus {{
                    border: 1px solid {accent_hex};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 18px;
                }}
                """
            )

            if name in self._session_force_ask:
                approval_combo.setCurrentText("Ask")
            elif name in self._session_auto_approve:
                approval_combo.setCurrentText("Approve")
            elif name in self._require_approval:
                approval_combo.setCurrentText("Ask")
            elif name in self._safe_preset:
                approval_combo.setCurrentText("Approve")
            else:
                approval_combo.setCurrentText("Ask")

            row_layout.addWidget(approval_combo, 0, Qt.AlignmentFlag.AlignTop)

            border_color = danger_border if name in self._require_approval else accent_border
            row.setStyleSheet(
                f"""
                QFrame#toolRow {{
                    background: {overlay_pressed};
                    border: 1px solid {border_color};
                    border-radius: 12px;
                }}
                """
            )

            list_layout.addWidget(row)
            self._rows[name] = {"row": row, "checkbox": cb, "approval_combo": approval_combo, "desc": desc}

        list_layout.addStretch(1)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch()

        cancel_btn = QPushButton("Cancel")
        save_btn = QPushButton("Save")
        for b in (cancel_btn, save_btn):
            b.setFixedHeight(34)
            b.setStyleSheet(
                f"""
                QPushButton {{
                    background: {overlay};
                    border: 1px solid {mid_hex};
                    border-radius: 12px;
                    padding: 0 16px;
                    font-size: 12px;
                    font-weight: 700;
                    color: {text_primary};
                }}
                QPushButton:hover {{ background: {overlay_hover}; border: 1px solid {accent_hex}; }}
                QPushButton:pressed {{ background: {overlay_pressed}; }}
                """
            )
        save_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {accent_hex};
                border: 1px solid {accent_hover};
                border-radius: 12px;
                padding: 0 16px;
                font-size: 12px;
                font-weight: 800;
                color: #ffffff;
            }}
            QPushButton:hover {{ background: {accent_hover}; border: 1px solid {accent_hover}; }}
            QPushButton:pressed {{ background: {accent_pressed}; }}
            """
        )

        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self.accept)
        footer.addWidget(cancel_btn)
        footer.addWidget(save_btn)
        layout.addLayout(footer)

        def _set_mode(mode: str) -> None:
            mode = "all" if mode == "all" else "custom"
            self._mode = mode
            self.all_mode_btn.setChecked(self._mode == "all")
            self.custom_mode_btn.setChecked(self._mode == "custom")
            self._suppress_checkbox_updates = True
            try:
                if self._mode == "all":
                    self._custom_selected = set(self._all_names_set)
                    for _, info in self._rows.items():
                        info["checkbox"].setEnabled(True)
                        info["checkbox"].setChecked(True)
                else:
                    for n, info in self._rows.items():
                        info["checkbox"].setEnabled(True)
                        info["checkbox"].setChecked(n in self._custom_selected)
            finally:
                self._suppress_checkbox_updates = False

            self._update_counts()

        self.all_mode_btn.clicked.connect(lambda _=False: _set_mode("all"))
        self.custom_mode_btn.clicked.connect(lambda _=False: _set_mode("custom"))

        select_all_btn.clicked.connect(lambda _=False: _set_mode("all"))

        def _select_none() -> None:
            self._custom_selected = set()
            _set_mode("custom")

        select_none_btn.clicked.connect(lambda _=False: _select_none())

        def _apply_filter() -> None:
            q = (self.filter_input.text() or "").strip().lower()
            for n, info in self._rows.items():
                if not q:
                    info["row"].setVisible(True)
                    continue
                hay = f"{n}\n{info.get('desc','')}".lower()
                info["row"].setVisible(q in hay)

        self.filter_input.textChanged.connect(lambda _=None: _apply_filter())

        self.resize(720, 560)
        _set_mode(self._mode)
        _apply_filter()
        self._update_counts()

    def _update_counts(self) -> None:
        total = len(self._all_names)
        if self._mode == "all":
            selected = total
        else:
            selected = len({n for n, info in self._rows.items() if info["checkbox"].isChecked()})
        self.count_pill.setText(f"✓ {selected} of {total} selected")

    def selected_tools(self) -> List[str]:
        if self._mode == "all":
            return list(self._all_names)
        return sorted([n for n, info in self._rows.items() if info["checkbox"].isChecked()])

    def selected_approval_modes(self) -> Dict[str, str]:
        """Return per-tool approval mode: 'approve' or 'ask'."""
        modes: Dict[str, str] = {}
        for name, info in self._rows.items():
            combo = info.get("approval_combo")
            if combo is None:
                continue
            try:
                txt = str(combo.currentText() or "").strip().lower()
            except Exception:
                txt = ""
            modes[name] = "approve" if txt == "approve" else "ask"
        return modes


class LLMWorker(QThread):
    """Worker thread for LLM processing."""

    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, llm_manager, message, provider, model, media=None, debug: bool = False):
        super().__init__()
        self.llm_manager = llm_manager
        self.message = message
        self.provider = provider
        self.model = model
        self.media = media or []
        self.debug = bool(debug)

    def run(self):
        """Run LLM processing in background."""
        try:
            # Use LLMManager session for context persistence with optional media files
            response = self.llm_manager.generate_response(
                self.message,
                self.provider,
                self.model,
                media=self.media if self.media else None
            )

            # Response is already a string from LLMManager
            response_text = str(response)

            self.response_ready.emit(response_text)

        except Exception as e:
            if self.debug:
                print(f"❌ LLM Error: {e}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))


class AgentWorker(QThread):
    """Worker thread that drives an AgentHost turn (tick/resume loop)."""

    event_emitted = pyqtSignal(object)  # dict payloads
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        *,
        agent_host: AgentHost,
        user_text: str,
        provider: str,
        model: str,
        attachments: Optional[List[str]] = None,
        system_prompt_extra: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        debug: bool = False,
    ):
        super().__init__()
        self._agent_host = agent_host
        self._user_text = str(user_text or "")
        self._provider = str(provider or "")
        self._model = str(model or "")
        self._attachments = list(attachments or [])
        self._system_prompt_extra = str(system_prompt_extra) if system_prompt_extra else None
        self._allowed_tools = list(allowed_tools) if allowed_tools is not None else None
        self._debug = bool(debug)

        self._tool_approval_event = threading.Event()
        self._tool_approval_decision: Optional[bool] = None
        self._ask_user_event = threading.Event()
        self._ask_user_response: Optional[str] = None

    def provide_tool_approval(self, approved: bool) -> None:
        self._tool_approval_decision = bool(approved)
        self._tool_approval_event.set()

    def provide_user_response(self, response: str) -> None:
        self._ask_user_response = str(response or "")
        self._ask_user_event.set()

    def run(self) -> None:
        try:
            def _approve(_tool_calls):
                return bool(self._tool_approval_decision)

            def _ask_user(_wait):
                return str(self._ask_user_response or "")

            gen = self._agent_host.run_turn(
                user_text=self._user_text,
                attachments=self._attachments if self._attachments else None,
                provider=self._provider,
                model=self._model,
                system_prompt_extra=self._system_prompt_extra,
                allowed_tools=self._allowed_tools,
                approve_tools=_approve,
                ask_user=_ask_user,
            )

            while True:
                try:
                    ev = next(gen)
                except StopIteration:
                    return

                self.event_emitted.emit(ev)

                typ = ev.get("type") if isinstance(ev, dict) else None
                if typ == "tool_request":
                    tool_calls = ev.get("tool_calls")
                    if isinstance(tool_calls, list) and not self._agent_host.tool_policy.requires_approval(tool_calls):
                        # Safe/read-only tool batch: auto-approve (no UI prompt required).
                        self._tool_approval_decision = True
                        continue
                    self._tool_approval_decision = None
                    self._tool_approval_event.clear()
                    self._tool_approval_event.wait()
                    if self._tool_approval_decision is None:
                        self._tool_approval_decision = False
                    continue

                if typ == "ask_user":
                    self._ask_user_response = None
                    self._ask_user_event.clear()
                    self._ask_user_event.wait()
                    if self._ask_user_response is None:
                        self._ask_user_response = ""
                    continue

        except Exception as e:
            if self._debug:
                import traceback

                traceback.print_exc()
            self.error_occurred.emit(str(e))


class _MessageInputRow(QWidget):
    """
    Two-column message input row with a strict-square (1:1) 3-button action column.

    Design goals (per UX requirements):
    - The action buttons fill the *full* vertical space of the input row (up to the card border)
    - Buttons remain perfectly square while scaling with available height
    - Exactly 1px vertical spacing between the 3 buttons
    - The text input ends exactly where the action column begins (two columns)
    """

    def __init__(
        self,
        *,
        parent: Optional[QWidget] = None,
        h_spacing_px: int = 2,
        v_spacing_px: int = 1,
        min_button_px: int = 22,
        min_text_width_px: int = 140,
    ) -> None:
        super().__init__(parent)
        self._h_spacing_px = max(0, int(h_spacing_px))
        self._v_spacing_px = max(0, int(v_spacing_px))
        self._min_button_px = max(12, int(min_button_px))
        self._min_text_width_px = max(40, int(min_text_width_px))

        self.input_text = QTextEdit(self)
        self.attach_button = QPushButton("📎", self)
        self.tools_button = QPushButton("🛠", self)
        self.send_button = QPushButton("→", self)
        self._voice_mode: bool = False

        # Keep focus/navigation sane.
        for b in (self.attach_button, self.tools_button, self.send_button):
            try:
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            except Exception:
                pass

    def set_voice_mode(self, enabled: bool) -> None:
        """
        In voice mode we keep the action column, but hide the Send button because
        end-of-sentence detection effectively acts as "send".
        """
        enabled = bool(enabled)
        if self._voice_mode == enabled:
            return
        self._voice_mode = enabled
        try:
            self.send_button.setVisible(not enabled)
            self.send_button.setEnabled(not enabled)
        except Exception:
            pass
        self.updateGeometry()
        self.update()

    def _set_button_font_px(self, px: int) -> None:
        px = max(10, int(px))
        try:
            for b in (self.attach_button, self.tools_button, self.send_button):
                f = b.font() if hasattr(b, "font") else QFont()
                try:
                    f.setPixelSize(px)
                except Exception:
                    # Fallback: point size if pixel sizing isn't available.
                    f.setPointSize(max(9, px // 2))
                b.setFont(f)
        except Exception:
            pass

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
        except Exception:
            pass

        w = int(self.width())
        h = int(self.height())
        if w <= 0 or h <= 0:
            return

        # Compute a square button size that uses as much vertical space as possible.
        # With N buttons and (N-1) gaps:
        #   used_h = N*btn + (N-1)*v_spacing  <= h
        action_buttons = (self.attach_button, self.tools_button) if self._voice_mode else (self.attach_button, self.tools_button, self.send_button)
        n = max(1, len(action_buttons))
        btn_from_h = (h - ((n - 1) * self._v_spacing_px)) // n
        btn = max(self._min_button_px, btn_from_h)

        # Ensure the column also fits horizontally (keep a minimum text width).
        max_btn_from_w = w - self._min_text_width_px - self._h_spacing_px
        if max_btn_from_w <= 0:
            max_btn_from_w = self._min_button_px
        btn = max(self._min_button_px, min(btn, max_btn_from_w))

        input_w = max(10, w - btn - self._h_spacing_px)
        col_x = input_w + self._h_spacing_px

        # Place the text input to fill the available height.
        self.input_text.setGeometry(0, 0, input_w, h)

        # Place the square buttons stacked on the right with strict spacing.
        # We anchor to the top to keep the tiny leftover (0-2px) at the bottom.
        used_h = (n * btn) + ((n - 1) * self._v_spacing_px)
        top = 0
        if used_h < h:
            # If there's slack (usually 0-2px), split it so borders look even.
            top = (h - used_h) // 2

        for i, b in enumerate(action_buttons):
            y = top + i * (btn + self._v_spacing_px)
            b.setGeometry(col_x, y, btn, btn)

        # Scale icon glyphs with the square size.
        self._set_button_font_px(int(btn * 0.55))


class QtChatBubble(QWidget):
    """Modern Qt-based chat bubble."""
    
    def __init__(self, llm_manager, config=None, debug=False, listening_mode="wait"):
        super().__init__()
        self.llm_manager = llm_manager
        self.config = config
        self.debug = debug
        self.listening_mode = listening_mode
        self._theme: Dict[str, Any] = {}
        
        # State - default to LMStudio with qwen/qwen3-next-80b
        self.current_provider = 'lmstudio'  # Default to LMStudio
        self.current_model = 'qwen/qwen3-next-80b'  # Default to qwen/qwen3-next-80b
        self.token_count = 0
        self.max_tokens = 128000
        
        # Message history for session management
        self.message_history: List[Dict] = []
        self._session_auto_approve_tools: set[str] = set()
        self._session_force_ask_tools: set[str] = set()
        self._session_auto_approve_tools_by_session: Dict[str, set[str]] = {}
        self._session_force_ask_tools_by_session: Dict[str, set[str]] = {}
        self._voice_busy: bool = False
        # STT callbacks arrive from a non-Qt thread. Use a small queue and drain it
        # on the Qt main thread to avoid calling Qt APIs from the mic thread.
        self._voice_transcription_queue = deque()
        self._voice_transcription_queue_lock = threading.Lock()
        # Full Voice Mode lifecycle: treat "running" as separate from the toggle state so
        # late callbacks cannot keep the UI in LISTENING after a user-initiated stop.
        self._full_voice_running: bool = False

        # History dialog instance for toggle behavior
        self.history_dialog = None

        # Attached files for media handling (AbstractCore 2.4.5+)
        self.attached_files: List[str] = []
        
        # Track file attachments per message for history display
        self.message_file_attachments: Dict[int, List[str]] = {}

        # Tool selection (external tools): controls the per-run allowlist passed to AbstractAgent.
        self._available_external_tools: List[Dict[str, str]] = []
        self._enabled_external_tools: set[str] = set()
        self._enabled_external_tools_user_set: bool = False
        self._safe_external_tools: set[str] = set()
        self._require_approval_tools: set[str] = set()
        self._refresh_tool_inventory()
        
        # Initialize new manager classes
        self.provider_manager = None
        self.tts_state_manager = None
        if MANAGERS_AVAILABLE:
            try:
                self.provider_manager = ProviderManager(debug=debug)
                self.tts_state_manager = TTSStateManager(debug=debug)
                if self.debug:
                    print("✅ Manager classes initialized")
            except Exception as e:
                if self.debug:
                    print(f"❌ Failed to initialize manager classes: {e}")

        # TTS functionality (AbstractVoice-compatible)
        self.voice_manager = None
        self.tts_enabled = False
        if TTS_AVAILABLE:
            try:
                self.voice_manager = VoiceManager(debug_mode=debug)
                # Connect voice manager to TTS state manager
                if self.tts_state_manager:
                    self.tts_state_manager.set_voice_manager(self.voice_manager)
                if self.debug:
                    print("🔊 VoiceManager initialized")
            except Exception as e:
                if self.debug:
                    print(f"❌ Failed to initialize VoiceManager: {e}")
        
        # Callbacks
        self.response_callback = None
        self.error_callback = None
        self.status_callback = None  # New callback for status updates
        
        # Worker thread
        self.worker = None
        
        self.setup_ui()
        self.setup_styling()
        self.load_providers()

        # Bootstrap UI state from the durable active session (tokens/history).
        try:
            if self.llm_manager and hasattr(self.llm_manager, "refresh"):
                self.llm_manager.refresh()
        except Exception:
            pass
        try:
            self._update_message_history_from_session()
            self._update_token_count_from_session()
            self._reload_session_combo()
        except Exception:
            pass
        
        if self.debug:
            print("✅ QtChatBubble initialized")
    
    def set_response_callback(self, callback):
        """Set response callback."""
        self.response_callback = callback
    
    def set_error_callback(self, callback):
        """Set error callback."""
        self.error_callback = callback
    
    def set_status_callback(self, callback):
        """Set status callback."""
        self.status_callback = callback
        if self.debug:
            print("✅ Status callback set in QtChatBubble")
    
    def set_app_quit_callback(self, callback):
        """Set app quit callback."""
        self.app_quit_callback = callback
    
    def setup_ui(self):
        """Set up the modern user interface with SOTA UX practices."""
        self.setWindowTitle("AbstractAssistant")
        self.setObjectName("AbstractAssistantBubble")
        try:
            attr = getattr(Qt, "WA_StyledBackground", None)
            if attr is None and hasattr(Qt, "WidgetAttribute"):
                attr = Qt.WidgetAttribute.WA_StyledBackground
            if attr is not None:
                self.setAttribute(attr, True)
        except Exception:
            pass
        try:
            attr = getattr(Qt, "WA_TranslucentBackground", None)
            if attr is None and hasattr(Qt, "WidgetAttribute"):
                attr = Qt.WidgetAttribute.WA_TranslucentBackground
            if attr is not None:
                self.setAttribute(attr, True)
        except Exception:
            pass
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        try:
            # Keep the window fully opaque; transparency is handled by painting an
            # alpha-blended "glass" background in paintEvent().
            self.setWindowOpacity(1.0)
        except Exception:
            pass
        
        # Set optimal size for modern chat interface.
        # Keep the default lightweight and compact: ~15% narrower than the previous 630px.
        # Initial size - will be adjusted dynamically based on file attachments
        self.base_width = 536
        self.base_height = 196
        self.setFixedSize(self.base_width, self.base_height)
        self._window_corner_radius = 12
        self.position_near_tray()
        
        # Window structure:
        # - Top-level widget stays transparent (for rounded corners via translucent backing).
        # - A single child frame paints the "glass" background and border.
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.window_frame = QFrame(self)
        self.window_frame.setObjectName("windowFrame")
        try:
            expanding = QSizePolicy.Policy.Expanding
        except Exception:
            expanding = getattr(QSizePolicy, "Expanding", None)
        try:
            if expanding is not None:
                self.window_frame.setSizePolicy(expanding, expanding)
        except Exception:
            pass
        try:
            attr = getattr(Qt, "WA_StyledBackground", None)
            if attr is None and hasattr(Qt, "WidgetAttribute"):
                attr = Qt.WidgetAttribute.WA_StyledBackground
            if attr is not None:
                self.window_frame.setAttribute(attr, True)
        except Exception:
            pass

        outer_layout.addWidget(self.window_frame)

        # Main layout with minimal spacing (inside the glass frame)
        layout = QVBoxLayout(self.window_frame)
        layout.setContentsMargins(8, 4, 8, 8)  # Strict minimum margins
        layout.setSpacing(4)  # Minimal spacing
        
        # Simple header like Cursor
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(0)

        # Stable 3-cluster navbar (left / center / right). This avoids first-show layout
        # compression and ensures the header always uses the full available width.
        left_cluster = QWidget()
        left_row = QHBoxLayout(left_cluster)
        left_row.setContentsMargins(0, 0, 0, 0)
        left_row.setSpacing(10)
        
        # Close button (minimal)
        self.close_button = QPushButton("⨯")  # Better close icon - geometric multiplication symbol
        self.close_button.setFixedSize(24, 24)  # Increased from 18x18 to 24x24 for better visibility
        self.close_button.setToolTip("Quit")
        self.close_button.clicked.connect(self.close_app)
        self.close_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                border: none;
                border-radius: 12px;
                font-size: 14px;
                font-weight: 600;
                color: rgba(255, 255, 255, 0.9);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
            QPushButton:hover {
                background: rgba(255, 60, 60, 0.8);
	                color: #ffffff;
	            }
	        """)
        left_row.addWidget(self.close_button)

        # Internal session selector model (hidden; sessions are managed via the Sessions badge dialog).
        self.session_combo = QComboBox()
        self.session_combo.setFixedHeight(22)
        self.session_combo.setMinimumWidth(160)
        self.session_combo.setToolTip("Select a session")
        self.session_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 6px;
                font-size: 10px;
                color: rgba(255, 255, 255, 0.8);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                padding: 0 10px;
            }
            QComboBox:hover {
                background: rgba(255, 255, 255, 0.12);
                color: rgba(255, 255, 255, 0.9);
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        try:
            self.session_combo.view().setMinimumWidth(420)
        except Exception:
            pass
        self.session_combo.currentIndexChanged.connect(self._on_session_combo_changed)
        try:
            self.session_combo.setVisible(False)
        except Exception:
            pass

        # Sessions badge (opens a full session list).
        self.sessions_button = QPushButton("Sessions")
        self.sessions_button.setFixedHeight(22)
        self.sessions_button.setFixedWidth(86)
        self.sessions_button.setToolTip("Sessions")
        self.sessions_button.clicked.connect(self.open_sessions_dialog)
        self.sessions_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 11px;
                font-size: 10px;
                color: rgba(255, 255, 255, 0.8);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                padding: 0 10px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
                color: rgba(255, 255, 255, 0.95);
            }
        """)
        left_row.addWidget(self.sessions_button)

        # Session controls: New / Clear / Import / Export.
        header_icon_qss = """
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 11px;
                font-size: 13px;
                color: rgba(255, 255, 255, 0.75);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
                color: rgba(255, 255, 255, 0.95);
            }
        """

        self.new_session_button = QPushButton("＋")
        self.new_session_button.setFixedSize(28, 22)
        self.new_session_button.setToolTip("New session")
        self.new_session_button.clicked.connect(self._start_new_session)
        self.new_session_button.setStyleSheet(header_icon_qss)
        left_row.addWidget(self.new_session_button)

        self.clear_session_button = QPushButton("🗑")
        self.clear_session_button.setFixedSize(28, 22)
        self.clear_session_button.setToolTip("Clear this session")
        self.clear_session_button.clicked.connect(self.clear_active_session_contents)
        self.clear_session_button.setStyleSheet(header_icon_qss)
        left_row.addWidget(self.clear_session_button)

        self.import_session_button = QPushButton("⤓")
        self.import_session_button.setFixedSize(28, 22)
        self.import_session_button.setToolTip("Import session from file")
        self.import_session_button.clicked.connect(self.load_session)
        self.import_session_button.setStyleSheet(header_icon_qss)
        left_row.addWidget(self.import_session_button)

        self.export_session_button = QPushButton("⤒")
        self.export_session_button.setFixedSize(28, 22)
        self.export_session_button.setToolTip("Export current session to file")
        self.export_session_button.clicked.connect(self.save_session)
        self.export_session_button.setStyleSheet(header_icon_qss)
        left_row.addWidget(self.export_session_button)

        # Messages/history button (user-facing transcript).
        self.history_button = QPushButton("💬")
        self.history_button.setFixedSize(28, 22)
        self.history_button.setToolTip("Messages")
        self.history_button.clicked.connect(self.show_history)
        self.history_button.setStyleSheet(header_icon_qss)
        
        # Voice controls (always visible; disabled when voice backend is unavailable).
        self.tts_toggle = TTSToggle()
        self.tts_toggle.toggled.connect(self.on_tts_toggled)
        self.full_voice_toggle = FullVoiceToggle()
        self.full_voice_toggle.toggled.connect(self.on_full_voice_toggled)

        voice_available = bool(self.voice_manager and self.voice_manager.is_available())
        if not voice_available:
            tooltip = "Voice unavailable. Install `abstractassistant` (AbstractVoice) and restart."
            try:
                self.tts_toggle.setEnabled(False)
                self.tts_toggle.setToolTip(tooltip)
            except Exception:
                pass
            try:
                self.full_voice_toggle.setEnabled(False)
                self.full_voice_toggle.setToolTip(tooltip)
            except Exception:
                pass

        # Status (Cursor-style, enlarged to show full text including "Processing")
        self.status_label = QLabel("READY")
        self.status_label.setFixedHeight(24)
        self.status_label.setMinimumWidth(92)
        self.status_label.setMaximumWidth(120)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                background: #22c55e;
                border: none;
                border-radius: 12px;
                font-size: 10px;
                font-weight: 600;
                color: #ffffff;
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
        """)
        self.status_label.setToolTip("Status")

        center_cluster = QWidget()
        center_row = QHBoxLayout(center_cluster)
        center_row.setContentsMargins(0, 0, 0, 0)
        center_row.setSpacing(0)
        center_row.addWidget(self.history_button)

        right_cluster = QWidget()
        right_row = QHBoxLayout(right_cluster)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(10)
        right_row.addWidget(self.tts_toggle)
        right_row.addWidget(self.full_voice_toggle)
        right_row.addWidget(self.status_label)

        try:
            fixed = QSizePolicy.Policy.Fixed
        except Exception:
            fixed = getattr(QSizePolicy, "Fixed", None)
        try:
            if fixed is not None:
                left_cluster.setSizePolicy(fixed, fixed)
                center_cluster.setSizePolicy(fixed, fixed)
                right_cluster.setSizePolicy(fixed, fixed)
        except Exception:
            pass

        header_layout.addWidget(left_cluster)
        header_layout.addStretch(1)
        header_layout.addWidget(center_cluster)
        header_layout.addStretch(1)
        header_layout.addWidget(right_cluster)
        
        layout.addLayout(header_layout)
        
        # Input section with modern card design
        self.input_container = QFrame()
        self.input_container.setObjectName("inputContainer")
        self.input_container.setStyleSheet("""
            QFrame {
                background: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        input_layout = QVBoxLayout(self.input_container)
        # Keep this tight so the right-side action column visually reaches the card border.
        input_layout.setContentsMargins(2, 2, 2, 2)
        input_layout.setSpacing(2)

        # Deterministic manual-geometry input row (no layout race on first show).
        self._input_row = _MessageInputRow(parent=self.input_container, h_spacing_px=2, v_spacing_px=1)
        self._input_row.setMinimumHeight(86)
        input_layout.addWidget(self._input_row, 1)

        # Expose the child widgets on the bubble for the rest of the codebase.
        self.input_text = self._input_row.input_text
        self.attach_button = self._input_row.attach_button
        self.tools_button = self._input_row.tools_button
        self.send_button = self._input_row.send_button

        self.input_text.setPlaceholderText("Ask me anything... (Shift+Enter to send)")
        try:
            self.input_text.installEventFilter(self)
        except Exception:
            pass

        # Wiring
        self.attach_button.clicked.connect(self.attach_files)
        self.attach_button.setToolTip("Attach files (images, documents, audio, video)")
        self.tools_button.clicked.connect(self.open_tool_selector)
        self.tools_button.setToolTip("Tools")
        self.send_button.clicked.connect(self.send_message)

        # Styling (theme methods will override these too; these are safe defaults for first paint)
        self.attach_button.setStyleSheet(
            """
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid #404040;
                border-radius: 4px;
                color: rgba(255, 255, 255, 0.75);
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid #0066cc;
                color: rgba(255, 255, 255, 0.95);
            }
            QPushButton:pressed { background: rgba(255, 255, 255, 0.06); }
            """
        )
        self.tools_button.setStyleSheet(
            """
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid #404040;
                border-radius: 4px;
                color: rgba(255, 255, 255, 0.75);
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid #7c3aed;
                color: rgba(255, 255, 255, 0.95);
            }
            QPushButton:pressed { background: rgba(255, 255, 255, 0.06); }
            """
        )
        self.send_button.setStyleSheet(
            """
            QPushButton {
                background: #0066cc;
                border: 1px solid #0080ff;
                border-radius: 4px;
                font-weight: 700;
                color: #ffffff;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover { background: #0080ff; border: 1px solid #0099ff; }
            QPushButton:pressed { background: #0052a3; }
            QPushButton:disabled {
                background: #404040;
                color: #666666;
                border: 1px solid #333333;
            }
            """
        )
        self._update_tools_button_state()

        # Attached files display area (initially hidden)
        self.attached_files_container = QFrame()
        self.attached_files_container.setObjectName("attachedFilesContainer")
        self.attached_files_container.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid #404040;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        self.attached_files_layout = QHBoxLayout(self.attached_files_container)
        self.attached_files_layout.setContentsMargins(2, 2, 2, 2)
        self.attached_files_layout.setSpacing(2)
        self.attached_files_container.hide()  # Initially hidden
        input_layout.addWidget(self.attached_files_container)
        layout.addWidget(self.input_container)
        
        # Bottom controls - Cursor style (minimal, clean)
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(8, 2, 8, 2)
        controls_layout.setSpacing(4)
        
        # Provider dropdown (rounded, clean)
        self.provider_combo = QComboBox()
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        self.provider_combo.setFixedHeight(28)
        self.provider_combo.setMinimumWidth(100)
        self.provider_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 14px;
                padding: 0 8px;
                font-size: 11px;
                color: rgba(255, 255, 255, 0.9);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
            QComboBox:hover {
                background: rgba(255, 255, 255, 0.12);
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
                width: 0px;
            }
        """)
        controls_layout.addWidget(self.provider_combo)
        
        # Model dropdown (rounded, clean)
        self.model_combo = QComboBox()
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        self.model_combo.setFixedHeight(28)
        self.model_combo.setMinimumWidth(140)
        self.model_combo.view().setMinimumWidth(380)  # Wider dropdown to show full model names
        self.model_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 14px;
                padding: 0 8px;
                font-size: 11px;
                color: rgba(255, 255, 255, 0.9);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
            QComboBox:hover {
                background: rgba(255, 255, 255, 0.12);
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
                width: 0px;
            }
        """)
        controls_layout.addWidget(self.model_combo)
        
        controls_layout.addStretch()
        
        # Token counter (minimal)
        self.token_label = QLabel("0 / 128k")
        self.token_label.setFixedHeight(28)  # Match provider and model dropdown height
        self.token_label.setMinimumWidth(104)  # Increased by 30% (80 * 1.3 = 104)
        self.token_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.token_label.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 14px;
                font-size: 12px;
                color: rgba(255, 255, 255, 0.6);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
        """)
        controls_layout.addWidget(self.token_label)
        
        # Add a simple chat display area between header and input
        # No chat display in main bubble - messages only appear in History dialog
        
        layout.addLayout(controls_layout)
        
        # Setup keyboard shortcuts for voice control
        self.setup_keyboard_shortcuts()

        # Focus on input
        self.input_text.setFocus()

        # Enter key handling
        self.input_text.keyPressEvent = self.handle_key_press

        # Populate session selector (durable multi-session).
        try:
            self._reload_session_combo(select_session_id=getattr(self.llm_manager, "active_session_id", None))
        except Exception:
            pass

        # Make the first show match subsequent show/hide cycles (avoid layout settling later).
        try:
            self.ensurePolished()
            if hasattr(self, "window_frame") and self.window_frame:
                self.window_frame.ensurePolished()
            if self.layout() is not None:
                self.layout().activate()
            if hasattr(self, "window_frame") and self.window_frame and self.window_frame.layout() is not None:
                self.window_frame.layout().activate()
            self.updateGeometry()
        except Exception:
            pass

    def _compute_theme(self) -> Dict[str, Any]:
        palette = QApplication.instance().palette() if QApplication.instance() else self.palette()
        window = palette.window().color()
        base = palette.base().color()
        mid = palette.mid().color()
        text = palette.text().color()
        accent = palette.highlight().color()

        is_dark = window.lightness() < 128

        def rgba(color: QColor, alpha: float) -> str:
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

        overlay = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.06)"
        overlay_hover = "rgba(255, 255, 255, 0.12)" if is_dark else "rgba(0, 0, 0, 0.10)"
        overlay_pressed = "rgba(255, 255, 255, 0.06)" if is_dark else "rgba(0, 0, 0, 0.04)"

        focus_bg = base.lighter(112) if is_dark else base.darker(102)
        accent_hover = accent.lighter(115)
        accent_pressed = accent.darker(115)

        # Single source of truth for window translucency ("glass").
        # Keep it readable and consistent across the app. (No global window opacity.)
        glass_alpha = 0.92 if is_dark else 0.86
        glass_bg = rgba(window, glass_alpha)
        glass_border = rgba(QColor(255, 255, 255), 0.18) if is_dark else rgba(QColor(0, 0, 0), 0.12)
        composer_bg = rgba(QColor(0, 0, 0), 0.22) if is_dark else rgba(QColor(255, 255, 255), 0.52)

        return {
            "is_dark": is_dark,
            "window_bg": window.name(),
            "glass_bg": glass_bg,
            "glass_border": glass_border,
            "composer_bg": composer_bg,
            "surface_bg": base.name(),
            "surface_focus_bg": focus_bg.name(),
            "border": mid.name(),
            "text_primary": rgba(text, 0.9),
            "text_secondary": rgba(text, 0.72),
            "text_muted": rgba(text, 0.55 if is_dark else 0.5),
            "accent": accent.name(),
            "accent_hover": accent_hover.name(),
            "accent_pressed": accent_pressed.name(),
            "accent_rgba_12": rgba(accent, 0.12),
            "accent_rgba_20": rgba(accent, 0.20),
            "accent_rgba_35": rgba(accent, 0.35),
            "overlay": overlay,
            "overlay_hover": overlay_hover,
            "overlay_pressed": overlay_pressed,
        }

    def _apply_theme(self) -> None:
        t = self._theme or self._compute_theme()

        input_focused = False
        try:
            input_focused = bool(getattr(self, "input_text", None) and self.input_text.hasFocus())
        except Exception:
            input_focused = False
        input_border = t["accent"] if input_focused else t["border"]

        # Window
        self.setStyleSheet(
            f"""
            QWidget#AbstractAssistantBubble {{
                background: transparent;
                border: none;
                color: {t['text_primary']};
            }}
            QFrame#windowFrame {{
                background: {t['glass_bg']};
                border: 1px solid {t['glass_border']};
                border-radius: 12px;
            }}
            """
        )

        # Input container + text input
        if hasattr(self, "input_container"):
            self.input_container.setStyleSheet(
                f"""
                QFrame#inputContainer {{
                    background: {t['composer_bg']};
                    border: 1px solid {input_border};
                    border-radius: 6px;
                    padding: 4px;
                }}
                """
            )
        if hasattr(self, "input_text"):
            self.input_text.setStyleSheet(
                f"""
                QTextEdit {{
                    background: transparent;
                    border: none;
                    padding: 4px 8px;
                    font-size: 14px;
                    font-weight: 400;
                    color: {t['text_primary']};
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                    selection-background-color: {t['accent']};
                    line-height: 1.4;
                }}

                QTextEdit:focus {{
                    background: transparent;
                }}

                QTextEdit::placeholder {{
                    color: {t['text_muted']};
                }}
                """
            )

        # Header controls
        pill_qss = f"""
            background: {t['overlay_pressed']};
            border: none;
            border-radius: 11px;
            font-size: 10px;
            color: {t['text_secondary']};
            font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            padding: 0 10px;
        """
        pill_hover = f"background: {t['overlay_hover']}; color: {t['text_primary']};"

        if hasattr(self, "session_combo"):
            self.session_combo.setStyleSheet(
                f"""
                QComboBox {{ {pill_qss} }}
                QComboBox:hover {{ {pill_hover} }}
                QComboBox::drop-down {{ border: none; }}
                """
            )

        if hasattr(self, "sessions_button"):
            self.sessions_button.setStyleSheet(
                f"""
                QPushButton {{ {pill_qss} }}
                QPushButton:hover {{ {pill_hover} }}
                """
            )

        if hasattr(self, "more_button"):
            self.more_button.setStyleSheet(
                f"""
                QPushButton {{
                    background: {t['overlay_pressed']};
                    border: none;
                    border-radius: 11px;
                    font-size: 16px;
                    color: {t['text_secondary']};
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    background: {t['overlay_hover']};
                    color: {t['text_primary']};
                }}
                """
            )

        icon_btn_qss = f"""
            QPushButton {{
                background: {t['overlay_pressed']};
                border: none;
                border-radius: 11px;
                font-size: 13px;
                color: {t['text_secondary']};
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                padding: 0px;
            }}
            QPushButton:hover {{
                background: {t['overlay_hover']};
                color: {t['text_primary']};
            }}
        """

        for attr in (
            "history_button",
            "new_session_button",
            "clear_session_button",
            "import_session_button",
            "export_session_button",
        ):
            if hasattr(self, attr):
                try:
                    getattr(self, attr).setStyleSheet(icon_btn_qss)
                except Exception:
                    pass

        if hasattr(self, "close_button"):
            self.close_button.setStyleSheet(
                f"""
                QPushButton {{
                    background: {t['overlay_hover']};
                    border: none;
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: 600;
                    color: {t['text_primary']};
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                }}
                QPushButton:hover {{
                    background: rgba(255, 60, 60, 0.85);
                    color: #ffffff;
                }}
                QPushButton:pressed {{
                    background: rgba(255, 60, 60, 0.65);
                }}
                """
            )

        # Input action buttons (stretch to fill vertical space)
        icon_btn_qss = f"""
	            QPushButton {{
	                background: {t['overlay']};
	                border: 1px solid {t['border']};
	                border-radius: 4px;
	                color: {t['text_secondary']};
	                text-align: center;
	                padding: 0px;
	                margin: 0px;
	            }}
            QPushButton:hover {{
                background: {t['overlay_hover']};
                border: 1px solid {t['accent']};
                color: {t['text_primary']};
            }}
            QPushButton:pressed {{
                background: {t['overlay_pressed']};
            }}
        """
        if hasattr(self, "attach_button"):
            self.attach_button.setStyleSheet(icon_btn_qss)

        # tools_button style is handled via _update_tools_button_state()

        if hasattr(self, "send_button"):
            self.send_button.setStyleSheet(
                f"""
	                QPushButton {{
	                    background: {t['accent']};
	                    border: 1px solid {t['accent_hover']};
	                    border-radius: 4px;
	                    font-weight: bold;
	                    color: #ffffff;
	                    text-align: center;
	                    padding: 0px;
	                    margin: 0px;
	                }}
                QPushButton:hover {{
                    background: {t['accent_hover']};
                    border: 1px solid {t['accent_hover']};
                }}
                QPushButton:pressed {{
                    background: {t['accent_pressed']};
                }}
                QPushButton:disabled {{
                    background: {t['overlay_pressed']};
                    color: {t['text_muted']};
                    border: 1px solid {t['border']};
                }}
                """
            )

        # Bottom controls
        if hasattr(self, "provider_combo"):
            self.provider_combo.setStyleSheet(
                f"""
                QComboBox {{
                    background: {t['overlay']};
                    border: none;
                    border-radius: 14px;
                    padding: 0 8px;
                    font-size: 11px;
                    color: {t['text_primary']};
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                }}
                QComboBox:hover {{ background: {t['overlay_hover']}; }}
                QComboBox::drop-down {{ border: none; width: 20px; }}
                QComboBox::down-arrow {{ image: none; border: none; width: 0px; }}
                """
            )

        if hasattr(self, "model_combo"):
            self.model_combo.setStyleSheet(
                f"""
                QComboBox {{
                    background: {t['overlay']};
                    border: none;
                    border-radius: 14px;
                    padding: 0 8px;
                    font-size: 11px;
                    color: {t['text_primary']};
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                }}
                QComboBox:hover {{ background: {t['overlay_hover']}; }}
                QComboBox::drop-down {{ border: none; width: 20px; }}
                QComboBox::down-arrow {{ image: none; border: none; width: 0px; }}
                """
            )

        if hasattr(self, "token_label"):
            self.token_label.setStyleSheet(
                f"""
                QLabel {{
                    background: {t['overlay_pressed']};
                    border: none;
                    border-radius: 14px;
                    font-size: 12px;
                    color: {t['text_muted']};
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                }}
                """
            )

        # Attached files container
        if hasattr(self, "attached_files_container"):
            self.attached_files_container.setStyleSheet(
                f"""
                QFrame#attachedFilesContainer {{
                    background: {t['overlay_pressed']};
                    border: 1px solid {t['border']};
                    border-radius: 6px;
                    padding: 4px;
                }}
                """
            )

    def eventFilter(self, obj, event):
        try:
            if obj is getattr(self, "input_text", None):
                etype = event.type()
                focus_in = getattr(QEvent, "FocusIn", None)
                focus_out = getattr(QEvent, "FocusOut", None)
                if focus_in is None and hasattr(QEvent, "Type"):
                    focus_in = QEvent.Type.FocusIn
                    focus_out = QEvent.Type.FocusOut
                if etype in {focus_in, focus_out}:
                    try:
                        self._apply_theme()
                    except Exception:
                        pass
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        try:
            etype = event.type()
            palette_change = getattr(QEvent, "PaletteChange", None)
            app_palette_change = getattr(QEvent, "ApplicationPaletteChange", None)
            if palette_change is None and hasattr(QEvent, "Type"):
                palette_change = QEvent.Type.PaletteChange
                app_palette_change = QEvent.Type.ApplicationPaletteChange
            if etype in {palette_change, app_palette_change}:
                self._theme = self._compute_theme()
                self._apply_theme()
                try:
                    self._update_tools_button_state()
                except Exception:
                    pass
        except Exception:
            pass
        super().changeEvent(event)

    def setup_styling(self):
        """Apply a system-aware theme (follows OS light/dark)."""
        self._theme = self._compute_theme()
        self._apply_theme()
        try:
            self._update_tools_button_state()
        except Exception:
            pass
    
    def position_near_tray(self):
        """Position the bubble near the system tray."""
        # Get screen geometry
        screen = QApplication.primaryScreen().geometry()
        
        # Position at the right corner with no gap
        x = screen.width() - self.width()  # 0px from right edge - touching the corner
        y = 50
        
        self.move(x, y)
        
        if self.debug:
            if self.debug:
                print(f"Positioned bubble at ({x}, {y})")
    
    def load_providers(self):
        """Load available providers using ProviderManager."""
        try:
            # Clear and populate provider combo
            self.provider_combo.clear()

            if self.provider_manager:
                # Use new ProviderManager
                available_providers = self.provider_manager.get_available_providers(exclude_mock=True)

                if self.debug:
                    if self.debug:
                        print(f"🔍 ProviderManager found {len(available_providers)} available providers")

                # Add providers to dropdown
                for display_name, provider_key in available_providers:
                    self.provider_combo.addItem(display_name, provider_key)
                    if self.debug:
                        if self.debug:
                            print(f"    ✅ Added: {display_name} ({provider_key})")

                # Set preferred provider
                preferred = self.provider_manager.get_preferred_provider(available_providers, 'lmstudio')
                if preferred:
                    display_name, provider_key = preferred
                    # Find and set the preferred provider
                    for i in range(self.provider_combo.count()):
                        if self.provider_combo.itemData(i) == provider_key:
                            self.provider_combo.setCurrentIndex(i)
                            self.current_provider = provider_key
                            break
                elif self.provider_combo.count() > 0:
                    # Use first available
                    self.current_provider = self.provider_combo.itemData(0)
                    self.provider_combo.setCurrentIndex(0)

            else:
                # Fallback: use old discovery method
                from abstractcore.providers import list_available_providers
                available_providers = list_available_providers()

                provider_display_names = {
                    'openai': 'OpenAI', 'anthropic': 'Anthropic', 'ollama': 'Ollama',
                    'lmstudio': 'LMStudio', 'mlx': 'MLX', 'huggingface': 'HuggingFace'
                }

                for provider_name in available_providers:
                    if provider_name != 'mock':  # Exclude mock
                        display_name = provider_display_names.get(provider_name, provider_name.title())
                        self.provider_combo.addItem(display_name, provider_name)

                self.current_provider = 'lmstudio' if 'lmstudio' in available_providers else (
                    available_providers[0] if available_providers else 'lmstudio'
                )

            if self.debug:
                if self.debug:
                    print(f"🔍 Final selected provider: {self.current_provider}")

            # Load models for current provider
            self.update_models()

        except Exception as e:
            if self.debug:
                if self.debug:
                    print(f"❌ Error loading providers: {e}")
                import traceback
                traceback.print_exc()

            # Final fallback
            if self.provider_combo.count() == 0:
                self.provider_combo.addItem("LMStudio (Local)", "lmstudio")
                self.current_provider = "lmstudio"
                if self.debug:
                    if self.debug:
                        print("🔄 Using fallback provider list")
    
    def update_models(self):
        """Update model dropdown using ProviderManager."""
        try:
            self.model_combo.clear()

            if self.provider_manager:
                # Use ProviderManager with 3-tier fallback strategy
                models = self.provider_manager.get_models_for_provider(self.current_provider)

                if self.debug:
                    if self.debug:
                        print(f"📋 ProviderManager loaded {len(models)} models for {self.current_provider}")

                # Add models to dropdown with display names
                for model in models:
                    display_name = self.provider_manager.create_model_display_name(model, max_length=55)
                    self.model_combo.addItem(display_name, model)

                # Set preferred model
                preferred_model = self.provider_manager.get_preferred_model(
                    models,
                    preferred='qwen/qwen3-next-80b',
                    current=self.current_model
                )

                if preferred_model:
                    # Find and set the preferred model
                    for i in range(self.model_combo.count()):
                        if self.model_combo.itemData(i) == preferred_model:
                            self.model_combo.setCurrentIndex(i)
                            self.current_model = preferred_model
                            break
                elif self.model_combo.count() > 0:
                    # Use first available
                    self.current_model = self.model_combo.itemData(0)
                    self.model_combo.setCurrentIndex(0)

            else:
                # Fallback: use old method
                from abstractcore.providers import get_available_models_for_provider
                models = get_available_models_for_provider(self.current_provider)

                for model in models:
                    # Use full model name (preserving provider prefix)
                    display_name = model
                    if len(display_name) > 55:
                        display_name = display_name[:52] + "..."
                    self.model_combo.addItem(display_name, model)

                if self.model_combo.count() > 0:
                    self.current_model = self.model_combo.itemData(0)
                    self.model_combo.setCurrentIndex(0)

            if self.debug:
                if self.debug:
                    print(f"✅ Final selected model: {self.current_model}")

            self.update_token_limits()

        except Exception as e:
            if self.debug:
                if self.debug:
                    print(f"❌ Error updating models: {e}")
                import traceback
                traceback.print_exc()

            # Final fallback: add default model
            if self.model_combo.count() == 0:
                self.model_combo.addItem("Default Model", "default-model")
                self.current_model = "default-model"
                self.model_combo.setCurrentIndex(0)
                if self.debug:
                    if self.debug:
                        print(f"🔄 Using final fallback model: {self.current_model}")
    
    def update_token_limits(self):
        """Update token limits using AbstractCore's built-in detection."""
        max_tokens = None
        source = None

        # Preferred: AbstractCore model capabilities (model_capabilities.json).
        try:
            from abstractcore.architectures.detection import get_model_capabilities

            caps = get_model_capabilities(str(self.current_model or ""))
            mt = caps.get("max_tokens") if isinstance(caps, dict) else None
            if isinstance(mt, int) and mt > 0:
                max_tokens = int(mt)
                source = "abstractcore:model_capabilities"
        except Exception:
            max_tokens = None

        # Fallback: provider instance (best-effort; may be lazy/unavailable).
        if max_tokens is None:
            try:
                llm = getattr(self.llm_manager, "llm", None)
                mt = getattr(llm, "max_tokens", None)
                if isinstance(mt, int) and mt > 0:
                    max_tokens = int(mt)
                    source = "provider"
            except Exception:
                max_tokens = None

        # Final fallback: keep UI stable even for unknown models.
        if max_tokens is None:
            max_tokens = 128000
            source = "fallback"

        self.max_tokens = int(max_tokens)

        try:
            self.token_label.setToolTip(f"Max context: {self.max_tokens} tokens ({source})")
        except Exception:
            pass

        if self.debug:
            print(f"📊 Token limit: {self.max_tokens} ({source})")
            
        self.update_token_display()
    
    def update_token_display(self):
        """Update token count display."""
        max_display = f"{self.max_tokens // 1000}k" if self.max_tokens >= 1000 else str(self.max_tokens)
        current_display = f"{int(self.token_count)}" if self.token_count < 1000 else f"{int(self.token_count // 1000)}k"
        self.token_label.setText(f"{current_display} / {max_display}")
    
    def handle_key_press(self, event):
        """Handle key press events in text input."""
#        print(f"🔄 Key pressed: {event.key()}, modifiers: {event.modifiers()}")
        
        # Check for Enter/Return key
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # Shift+Enter should add a new line
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Allow default behavior (new line)
                QTextEdit.keyPressEvent(self.input_text, event)
                return
            # Plain Enter should send message
            else:
                self.send_message()
                return
        
        # Call original keyPressEvent for all other keys
        QTextEdit.keyPressEvent(self.input_text, event)
    
    def on_provider_changed(self, provider_name):
        """Handle provider change."""
        # Find provider key by display name
        for i in range(self.provider_combo.count()):
            if self.provider_combo.itemText(i) == provider_name:
                self.current_provider = self.provider_combo.itemData(i)
                break
        
        self.update_models()
        
        if self.debug:
            if self.debug:
                print(f"Provider changed to: {self.current_provider}")
    
    def on_model_changed(self, model_name):
        """Handle model change."""
        # Find model key by display name
        for i in range(self.model_combo.count()):
            if self.model_combo.itemText(i) == model_name:
                self.current_model = self.model_combo.itemData(i)
                break
        
        self.update_token_limits()
        
        if self.debug:
            print(f"Model changed to: {self.current_model}")
    

    def _refresh_tool_inventory(self) -> None:
        """Refresh the list of available tools and keep the enabled set consistent."""
        host = getattr(self.llm_manager, "agent_host", None)
        tool_infos: List[Dict[str, str]] = []
        safe: set[str] = set()
        require: set[str] = set()

        if host is not None:
            try:
                policy = getattr(host, "tool_policy", None)
                safe = set(getattr(policy, "auto_approve_tools", set()) or set())
                require = set(getattr(policy, "require_approval_tools", set()) or set())
            except Exception:
                safe = set()
                require = set()

            try:
                for t in getattr(host, "tools", []) or []:
                    td = getattr(t, "_tool_definition", None)
                    name = getattr(td, "name", None) or getattr(t, "__name__", None)
                    if not isinstance(name, str) or not name.strip():
                        continue
                    desc = ""
                    try:
                        desc = str(getattr(td, "description", "") or "") if td is not None else ""
                    except Exception:
                        desc = ""
                    tool_infos.append({"name": name.strip(), "description": desc.strip()})
            except Exception:
                tool_infos = []

        available_names = {info.get("name", "") for info in tool_infos if isinstance(info, dict) and info.get("name")}
        available_names = {n for n in available_names if isinstance(n, str) and n.strip()}

        safe = set(safe) & set(available_names)
        require = set(require) & set(available_names)

        def _sort_key(info: Dict[str, str]) -> tuple[int, str]:
            name = str(info.get("name") or "")
            if name in safe:
                return (0, name)
            if name in require:
                return (1, name)
            return (2, name)

        self._available_external_tools = sorted(tool_infos, key=_sort_key)
        self._safe_external_tools = set(safe)
        self._require_approval_tools = set(require)

        if not self._enabled_external_tools and not getattr(self, "_enabled_external_tools_user_set", False):
            self._enabled_external_tools = set(available_names)
        else:
            self._enabled_external_tools &= set(available_names)

        # Keep per-session approval overrides aligned to the tool inventory.
        try:
            self._session_auto_approve_tools &= set(available_names)
            self._session_force_ask_tools &= set(available_names)
            self._session_auto_approve_tools -= set(self._session_force_ask_tools)
            self._save_tool_prefs_for_session()
        except Exception:
            pass

        self._update_tools_button_state()

    def _update_tools_button_state(self) -> None:
        """Update the tools button tooltip/style based on current selection."""
        btn = getattr(self, "tools_button", None)
        if btn is None:
            return
        t = self._theme or self._compute_theme()

        total = len(self._available_external_tools or [])
        enabled = len(self._enabled_external_tools or set())
        safe_enabled = len((self._enabled_external_tools or set()) & (self._safe_external_tools or set()))
        approval_enabled = len((self._enabled_external_tools or set()) & (self._require_approval_tools or set()))

        if total <= 0:
            btn.setEnabled(False)
            btn.setToolTip("Tools: none available")
            return

        btn.setEnabled(True)
        btn.setToolTip(f"Tools enabled: {enabled}/{total} (safe: {safe_enabled}, approval: {approval_enabled})")

        if enabled == 0:
            border = t["border"]
            bg = t["overlay_pressed"]
            fg = t["text_muted"]
        elif enabled < total:
            border = t["accent"]
            bg = t["accent_rgba_12"]
            fg = t["text_primary"]
        else:
            border = t["border"]
            bg = t["overlay"]
            fg = t["text_secondary"]

        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border};
	                border-radius: 4px;
                color: {fg};
                text-align: center;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{
                background: {t['overlay_hover']};
                border: 1px solid {t['accent']};
                color: {t['text_primary']};
            }}
            QPushButton:pressed {{
                background: {t['overlay_pressed']};
            }}
        """)

    def open_tool_selector(self) -> None:
        """Open the tool selector dialog (controls per-run tool allowlist)."""
        self._refresh_tool_inventory()
        if not self._available_external_tools:
            QMessageBox.information(self, "Tools", "No tools are available in this configuration.")
            return

        dlg = ToolSelectorDialog(
            parent=self,
            tools=list(self._available_external_tools),
            enabled=set(self._enabled_external_tools),
            safe_preset=set(self._safe_external_tools),
            require_approval=set(self._require_approval_tools),
            session_auto_approve=set(self._session_auto_approve_tools),
            session_force_ask=set(self._session_force_ask_tools),
        )
        result = dlg.exec()
        accepted_code = getattr(QDialog, "Accepted", 1)
        if result != accepted_code:
            return

        self._enabled_external_tools = set(dlg.selected_tools())
        self._enabled_external_tools_user_set = True
        modes = dlg.selected_approval_modes()
        self._session_auto_approve_tools = {n for n, m in modes.items() if m == "approve"}
        self._session_force_ask_tools = {n for n, m in modes.items() if m == "ask"}

        # Prefer "Ask" when both are present.
        self._session_auto_approve_tools -= set(self._session_force_ask_tools)

        self._save_tool_prefs_for_session()
        self._update_tools_button_state()

    def attach_files(self):
        """Open file dialog to attach files (AbstractCore 2.4.5+ media handling)."""
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        # Keep filters aligned with AbstractCore's supported formats (fallback list is conservative).
        audio_exts = ["wav", "mp3", "m4a", "ogg", "flac", "aac", "webm"]
        video_exts = ["mp4", "mov", "mkv", "webm", "avi", "wmv", "m4v"]
        try:
            from abstractcore.media.auto_handler import AutoMediaHandler  # type: ignore

            formats = AutoMediaHandler().get_supported_formats()
            if isinstance(formats, dict):
                aud = formats.get("audio")
                vid = formats.get("video")
                if isinstance(aud, list) and aud:
                    audio_exts = [str(x).lstrip(".").lower() for x in aud if isinstance(x, str) and str(x).strip()]
                if isinstance(vid, list) and vid:
                    video_exts = [str(x).lstrip(".").lower() for x in vid if isinstance(x, str) and str(x).strip()]
        except Exception:
            pass

        audio_patterns = " ".join(f"*.{ext}" for ext in sorted(set(audio_exts)))
        video_patterns = " ".join(f"*.{ext}" for ext in sorted(set(video_exts)))
        file_dialog.setNameFilter(
            "All supported files (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff "
            "*.pdf *.docx *.xlsx *.pptx *.txt *.md *.csv *.tsv *.json "
            f"{audio_patterns} {video_patterns});;"
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff);;"
            "Documents (*.pdf *.docx *.xlsx *.pptx *.txt *.md);;"
            "Data files (*.csv *.tsv *.json);;"
            f"Audio ({audio_patterns});;"
            f"Video ({video_patterns});;"
            "All files (*.*)"
        )

        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            for file_path in selected_files:
                if file_path not in self.attached_files:
                    self.attached_files.append(file_path)
                    if self.debug:
                        if self.debug:
                            print(f"📎 Attached file: {file_path}")

            self.update_attached_files_display()

    def update_attached_files_display(self):
        """Update the visual display of attached files."""
        t = self._theme or self._compute_theme()
        # Clear existing file chips
        while self.attached_files_layout.count():
            child = self.attached_files_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self.attached_files:
            self.attached_files_container.hide()
            self._adjust_window_size_for_attachments()
            return

        # Show container and add file chips
        self.attached_files_container.show()

        for file_path in self.attached_files:
            import os
            file_name = os.path.basename(file_path)

            # Create file chip
            file_chip = QFrame()
            file_chip.setStyleSheet(
                f"""
                QFrame {{
                    background: {t['accent_rgba_20']};
                    border: 1px solid {t['accent_rgba_35']};
                    border-radius: 6px;
                    padding: 1px 4px;
                }}
                """
            )

            chip_layout = QHBoxLayout(file_chip)
            chip_layout.setContentsMargins(2, 1, 2, 1)
            chip_layout.setSpacing(2)

            # File icon based on type
            ext = os.path.splitext(file_name)[1].lower()
            if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff']:
                icon = "🖼️"
            elif ext == '.pdf':
                icon = "📄"
            elif ext in ['.docx', '.doc']:
                icon = "📝"
            elif ext in ['.xlsx', '.xls']:
                icon = "📊"
            elif ext in ['.pptx', '.ppt']:
                icon = "📊"
            elif ext in ['.csv', '.tsv']:
                icon = "📋"
            elif ext in ['.wav']:
                icon = "🔊"
            else:
                icon = "📎"

            file_label = QLabel(f"{icon} {file_name[:20]}{'...' if len(file_name) > 20 else ''}")
            file_label.setStyleSheet(
                f"background: transparent; border: none; color: {t['text_primary']}; font-size: 8px;"
            )
            chip_layout.addWidget(file_label)

            # Remove button
            remove_btn = QPushButton("✕")
            remove_btn.setFixedSize(12, 12)
            remove_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {t['text_muted']};
                    font-size: 8px;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    color: rgba(255, 60, 60, 0.9);
                }}
                """
            )
            remove_btn.clicked.connect(lambda checked, fp=file_path: self.remove_attached_file(fp))
            chip_layout.addWidget(remove_btn)

            self.attached_files_layout.addWidget(file_chip)

        self.attached_files_layout.addStretch()
        
        # Adjust window size to accommodate file attachments
        self._adjust_window_size_for_attachments()

    def _adjust_window_size_for_attachments(self):
        """Dynamically adjust window size based on file attachments presence."""
        # In full voice mode, the UI is compact and voice-only; don't resize for attachments.
        try:
            if hasattr(self, "full_voice_toggle") and self.full_voice_toggle and self.full_voice_toggle.is_enabled():
                return
        except Exception:
            pass
        try:
            if hasattr(self, "input_container") and self.input_container and not self.input_container.isVisible():
                return
        except Exception:
            pass

        attachment_height = 28  # Height needed for file attachment container (reduced for compact chips)
        
        if self.attached_files and self.attached_files_container.isVisible():
            # Files are attached - expand window
            new_height = self.base_height + attachment_height
            if self.debug:
                print(f"📏 Expanding window for attachments: {self.base_height} -> {new_height}")
        else:
            # No files attached - use base size
            new_height = self.base_height
            if self.debug:
                print(f"📏 Contracting window (no attachments): -> {new_height}")
        
        # Apply new size
        self.setFixedSize(self.base_width, new_height)
        
        # Reposition to maintain alignment with system tray
        self.position_near_tray()

    def remove_attached_file(self, file_path):
        """Remove a file from the attached files list."""
        if file_path in self.attached_files:
            self.attached_files.remove(file_path)
            if self.debug:
                if self.debug:
                    print(f"🗑️ Removed attached file: {file_path}")
            self.update_attached_files_display()

    def send_message(self):
        """Send message to LLM with optional media attachments."""
        message = self.input_text.toPlainText().strip()
        if not message:
            return

        if self.debug:
            print(f"💬 Sending message: '{message[:50]}...' to {self.current_provider}/{self.current_model}")
            if self.attached_files:
                print(f"📎 With {len(self.attached_files)} attached file(s)")

        # 1. Clear input immediately
        self.input_text.clear()

        # 2. Capture attached files for sending (but keep them attached)
        media_files = self.attached_files.copy()
        
        # 3. Store file attachments for this message in our tracking dict
        # We'll use the message count as a simple key
        if media_files:
            message_index = len(self.message_history)  # Current message index before adding
            self.message_file_attachments[message_index] = media_files.copy()
            if self.debug:
                print(f"📎 Storing {len(media_files)} file(s) for message index {message_index}")

        # Note: We no longer clear attached_files here - they persist for reuse

        # 4. Update UI for sending state
        self.send_button.setEnabled(False)
        self.send_button.setText("⏳")
        self._set_session_controls_enabled(False)
        self.status_label.setText("generating")
        self.status_label.setObjectName("status_generating")
        self.status_label.setStyleSheet("""
            QLabel {
                background: rgba(250, 179, 135, 0.2);
                border: 1px solid rgba(250, 179, 135, 0.3);
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #fab387;
            }
        """)

        # Notify main app about status change (for icon animation)
        if self.status_callback:
            self.status_callback("generating")

        if self.debug:
            print("🔄 QtChatBubble: UI updated, creating worker thread...")

        # 5. Start worker thread to send request with optional media files
        system_prompt_extra = None
        if self._is_voice_mode_active():
            system_prompt_extra = (
                "You are in voice mode.\n"
                "- Keep responses concise and conversational.\n"
                "- Avoid markdown and heavy formatting.\n"
            )

        host = getattr(self.llm_manager, "agent_host", None)
        if host is not None:
            self.worker = AgentWorker(
                agent_host=host,
                user_text=message,
                provider=self.current_provider,
                model=self.current_model,
                attachments=media_files if media_files else None,
                system_prompt_extra=system_prompt_extra,
                allowed_tools=sorted(self._enabled_external_tools),
                debug=bool(self.debug),
            )
            self.worker.event_emitted.connect(self.on_agent_event)
            self.worker.error_occurred.connect(self.on_error_occurred)
        else:
            self.worker = LLMWorker(
                self.llm_manager,
                message,
                self.current_provider,
                self.current_model,
                media=media_files if media_files else None,
                debug=bool(self.debug),
            )
            self.worker.response_ready.connect(self.on_response_ready)
            self.worker.error_occurred.connect(self.on_error_occurred)

        if self.debug:
            print("🔄 QtChatBubble: Starting worker thread...")
        self.worker.start()

        if self.debug:
            print("🔄 QtChatBubble: Worker thread started, hiding bubble...")
        # Hide bubble after sending (like the original design), except in voice mode
        # where the bubble is a persistent control surface.
        if not self._is_voice_mode_active():
            QTimer.singleShot(500, self.hide)

    def _voice_underlying_manager(self):
        """Return the underlying AbstractVoice manager (when available)."""
        vm = getattr(self, "voice_manager", None)
        if vm is None:
            return None
        underlying = getattr(vm, "_abstractvoice_manager", None)
        return underlying if underlying is not None else vm

    def _voice_recognizer(self):
        """Best-effort access to the active microphone recognizer."""
        mgr = self._voice_underlying_manager()
        if mgr is None:
            return None
        return getattr(mgr, "voice_recognizer", None)

    def _tune_voice_recognizer_for_conversation(self) -> None:
        """Make full voice mode responsive (short utterances + faster endpointing)."""
        mode = str(getattr(self, "listening_mode", "") or "").strip().lower()
        if mode == "ptt":
            return

        rec = self._voice_recognizer()
        if rec is None:
            return
        try:
            set_profile = getattr(rec, "set_profile", None)
            if callable(set_profile):
                # Use the "full" profile for tighter VAD thresholds (faster silence->send).
                set_profile("full")
        except Exception:
            pass

    def _schedule_voice_listen_watchdog(self, delay_ms: int = 1200) -> None:
        """Detect common mic-capture failures (e.g., missing macOS mic permission)."""
        try:
            self._voice_watchdog_attempts = 0
        except Exception:
            pass
        try:
            QTimer.singleShot(int(delay_ms), self._voice_listen_watchdog_check)
        except Exception:
            pass

    def _abort_full_voice_mode_with_error(self, title: str, message: str) -> None:
        try:
            self.stop_full_voice_mode()
        except Exception:
            pass
        try:
            if hasattr(self, "full_voice_toggle") and self.full_voice_toggle:
                self.full_voice_toggle.set_enabled(False)
        except Exception:
            pass
        try:
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        try:
            QMessageBox.critical(self, str(title or "Voice error"), str(message or "Voice mode failed."))
        except Exception:
            pass

    def _voice_listen_watchdog_check(self) -> None:
        if not self._is_full_voice_running():
            return

        try:
            self._voice_watchdog_attempts = int(getattr(self, "_voice_watchdog_attempts", 0) or 0) + 1
        except Exception:
            self._voice_watchdog_attempts = 1

        rec = self._voice_recognizer()
        thread_alive = None
        stream_active = None

        if rec is not None:
            try:
                is_running = getattr(rec, "is_running", None)
                if isinstance(is_running, bool) and not is_running:
                    thread_alive = False
            except Exception:
                pass

            try:
                thread = getattr(rec, "thread", None)
                if thread is not None and hasattr(thread, "is_alive"):
                    thread_alive = bool(thread.is_alive())
            except Exception:
                pass

            try:
                stream = getattr(rec, "stream", None)
                if stream is not None and hasattr(stream, "active"):
                    stream_active = bool(getattr(stream, "active"))
                elif stream is None:
                    stream_active = False
            except Exception:
                pass

        healthy = bool(rec is not None) and (thread_alive is not False) and (stream_active is not False)
        if healthy:
            return

        # Retry a couple times to avoid false positives during cold start.
        if int(getattr(self, "_voice_watchdog_attempts", 1)) < 3:
            try:
                QTimer.singleShot(900, self._voice_listen_watchdog_check)
            except Exception:
                pass
            return

        self._abort_full_voice_mode_with_error(
            "Microphone not working",
            "Full voice mode couldn't access your microphone.\n\n"
            "Fix:\n"
            "1) macOS System Settings → Privacy & Security → Microphone\n"
            "2) Enable access for AbstractAssistant\n"
            "3) Restart AbstractAssistant\n\n"
            "If you started the app from Terminal, you can re-run with `--debug` to see the capture error.",
        )

    @pyqtSlot(object)
    def on_agent_event(self, event):
        """Handle AgentHost events emitted by AgentWorker."""
        if not isinstance(event, dict):
            return

        typ = event.get("type")
        if typ == "status":
            status = str(event.get("status") or "")
            self._set_agent_status(status)
            return

        if typ == "tool_request":
            self._handle_tool_request(event)
            return

        if typ == "ask_user":
            self._handle_ask_user(event)
            return

        if typ == "assistant":
            try:
                if hasattr(self.llm_manager, "refresh"):
                    self.llm_manager.refresh()
            except Exception:
                pass
            self.on_response_ready(str(event.get("content") or ""))
            return

        if typ == "error":
            self.on_error_occurred(str(event.get("error") or "error"))
            return

    def _set_agent_status(self, status: str) -> None:
        st = str(status or "").strip().lower()
        if st in {"thinking", "running"}:
            self.status_label.setText("thinking")
            if self.status_callback:
                self.status_callback("thinking")
            return
        if st in {"executing_tools", "executing"}:
            self.status_label.setText("executing")
            if self.status_callback:
                self.status_callback("executing")
            return
        if st in {"ready", "completed"}:
            self.status_label.setText("ready")
            if self.status_callback:
                self.status_callback("ready")
            return

    def _handle_tool_request(self, event: Dict) -> None:
        """Prompt user for tool approval when required."""
        tool_calls = event.get("tool_calls")
        if not isinstance(tool_calls, list):
            tool_calls = []

        host = getattr(self.llm_manager, "agent_host", None)
        requires = True
        policy = None
        try:
            if host is not None:
                policy = getattr(host, "tool_policy", None)
                requires = bool(policy.requires_approval(tool_calls))
        except Exception:
            requires = True

        tool_names: List[str] = []
        missing_name = False
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            name = str(tc.get("name") or "").strip()
            if not name:
                missing_name = True
                continue
            tool_names.append(name)

        if missing_name:
            requires = True

        # Session-level "Ask" overrides safe defaults.
        try:
            if any(n in self._session_force_ask_tools for n in tool_names):
                requires = True
        except Exception:
            pass

        # Session-level allowlist can bypass approval prompts.
        try:
            if tool_names and all(n in self._session_auto_approve_tools for n in tool_names):
                requires = False
        except Exception:
            pass

        if not requires:
            if self.debug:
                print("✅ Auto-approving safe tool batch (no prompt).")
            if self.status_callback:
                self.status_callback("executing")
            if isinstance(self.worker, AgentWorker):
                self.worker.provide_tool_approval(True)
            return

        # Bring UI forward for interactive approvals.
        try:
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

        self.status_label.setText("approve")
        if self.status_callback:
            self.status_callback("thinking")

        # Format tool calls for display.
        lines: List[str] = []
        for i, tc in enumerate(tool_calls):
            if not isinstance(tc, dict):
                continue
            name = str(tc.get("name") or f"tool_{i}")
            args = tc.get("arguments")
            try:
                args_txt = json.dumps(args, ensure_ascii=False, indent=2)
            except Exception:
                args_txt = str(args)
            lines.append(f"{name}({args_txt})")
        details = "\n\n".join(lines).strip()
        if len(details) > 8000:
            details = details[:8000] + "\n…(truncated)…"

        box = QMessageBox(self)
        box.setWindowTitle("Tool approval required")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("The assistant wants to run tools that may affect your system or workspace.")
        box.setInformativeText("Review the tool calls and approve or deny this batch.")
        box.setDetailedText(details)

        allow_box = QCheckBox("Always allow these tools for this session")
        box.setCheckBox(allow_box)

        approve_btn = box.addButton("Approve", QMessageBox.ButtonRole.AcceptRole)
        deny_btn = box.addButton("Deny", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(deny_btn)

        box.exec()
        clicked = box.clickedButton()
        approved = clicked == approve_btn

        if approved and allow_box.isChecked() and host is not None:
            try:
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    name = str(tc.get("name") or "").strip()
                    if not name:
                        continue
                    self._session_auto_approve_tools.add(name)
                    try:
                        self._session_force_ask_tools.discard(name)
                    except Exception:
                        pass
                self._save_tool_prefs_for_session()
            except Exception:
                pass

        if isinstance(self.worker, AgentWorker):
            self.worker.provide_tool_approval(bool(approved))

    def _handle_ask_user(self, event: Dict) -> None:
        """Prompt user for input required by the run."""
        prompt = str(event.get("prompt") or "Input required:")

        try:
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

        text, ok = QInputDialog.getText(self, "Assistant needs input", prompt)
        response = str(text) if ok else ""
        if isinstance(self.worker, AgentWorker):
            self.worker.provide_user_response(response)
    
    @pyqtSlot(str)
    def on_response_ready(self, response):
        """Handle LLM response."""
        if self.debug:
            print(f"✅ QtChatBubble: on_response_ready called with response: {response[:100]}...")
        
        self.send_button.setEnabled(True)
        self.send_button.setText("→")
        self._set_session_controls_enabled(True)
        self.status_label.setText("ready")
        self.status_label.setObjectName("status_ready")
        self.status_label.setStyleSheet("""
            QLabel {
                background: rgba(166, 227, 161, 0.2);
                border: 1px solid rgba(166, 227, 161, 0.3);
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #a6e3a1;
            }
        """)
        
        # Notify main app about status change (for icon animation)
        if self.status_callback:
            self.status_callback("ready")
        
        # Get updated message history from AbstractCore session
        self._update_message_history_from_session()

        # Update token count from AbstractCore
        self._update_token_count_from_session()

        # Refresh sessions list (recency ordering).
        try:
            self._reload_session_combo()
        except Exception:
            pass

        # Best-effort: auto-title the active session for the dropdown.
        try:
            if self.llm_manager and hasattr(self.llm_manager, "update_active_session_title_async"):
                self.llm_manager.update_active_session_title_async(
                    provider=self.current_provider,
                    model=self.current_model,
                    on_done=lambda _sid, _title: QMetaObject.invokeMethod(
                        self, "_refresh_session_combo_ui", Qt.QueuedConnection
                    ),
                )
        except Exception:
            pass
        
        # Handle TTS if enabled (AbstractVoice integration)
        if self.tts_enabled and self.voice_manager and self.voice_manager.is_available():
            if self.debug:
                if self.debug:
                    print("🔊 TTS enabled, speaking response...")
            
            # Don't show toast when TTS is enabled
            try:
                # Clean response for voice synthesis
                clean_response = self._clean_response_for_voice(response)
                
                # Set up callbacks to detect when speech actually starts/ends
                # Use QMetaObject.invokeMethod to ensure callbacks run on main thread
                def on_speech_start():
                    if self.debug:
                        print("🔊 QtChatBubble: Speech actually started (background thread)")
                    # Schedule status update on main thread
                    QMetaObject.invokeMethod(self, "_on_speech_started_main_thread", Qt.QueuedConnection)
                
                def on_speech_end():
                    if self.debug:
                        print("🔊 QtChatBubble: Speech ended (background thread)")
                    # Schedule completion handling on main thread
                    QMetaObject.invokeMethod(self, "_on_speech_ended_main_thread", Qt.QueuedConnection)
                
                # Set the callbacks on the voice manager
                self.voice_manager.on_speech_start = on_speech_start
                self.voice_manager.on_speech_end = on_speech_end
                
                # Speak the cleaned response using AbstractVoice-compatible interface
                # Note: We don't set "speaking" status here anymore - we wait for the callback
                started = bool(self.voice_manager.speak(clean_response))
                if not started:
                    raise RuntimeError("TTS speak() returned False")

                # Update toggle state to 'speaking'
                self._update_tts_toggle_state()
                
                # Store response for callback when TTS completes
                self._pending_response = response
                # In speaker mode, don't auto-open the Messages window.

            except Exception as e:
                if self.debug:
                    if self.debug:
                        print(f"❌ TTS error: {e}")
                # Show chat history as fallback - only if voice mode is OFF
                QTimer.singleShot(100, self._show_history_if_voice_mode_off)
                if self._is_full_voice_running():
                    self._voice_busy = False
                    try:
                        try:
                            if hasattr(self, "full_voice_toggle") and self.full_voice_toggle:
                                self.full_voice_toggle.set_listening_state("listening")
                        except Exception:
                            pass
                        self.update_status("LISTENING")
                    except Exception:
                        pass
        else:
            # Show chat history instead of toast when TTS is disabled - only if voice mode is OFF
            self._show_history_if_voice_mode_off()
        
        # Handle status transitions based on TTS mode
        tts_will_handle = self.tts_enabled and self.voice_manager and self.voice_manager.is_available()
        if self.debug:
            print(f"🔍 QtChatBubble: TTS decision - tts_enabled={self.tts_enabled}, voice_manager={self.voice_manager is not None}, is_available={self.voice_manager.is_available() if self.voice_manager else False}")
            print(f"🔍 QtChatBubble: TTS will handle callbacks: {tts_will_handle}")
        
        if not tts_will_handle:
            # Non-TTS path: Go directly to ready mode
            if self.debug:
                print(f"🔄 QtChatBubble: Non-TTS path - going to ready mode immediately")
            if self.response_callback:
                self.response_callback(response)
            if self.status_callback:
                self.status_callback("ready")
            if self._is_full_voice_running():
                self._voice_busy = False
                try:
                    self.update_status("LISTENING")
                except Exception:
                    pass
        else:
            # TTS path: Stay in thinking mode until audio actually starts
            if self.debug:
                print(f"🔊 QtChatBubble: TTS path - staying in thinking mode until audio starts")
                print(f"🔊 QtChatBubble: v0.5.1 callbacks will handle status transitions")
            # DON'T call response_callback or set "ready" status here!
            # The v0.5.1 callbacks will handle everything
    
    def on_tts_toggled(self, enabled: bool):
        """Handle TTS toggle state change."""
        self.tts_enabled = enabled
        if self.debug:
            if self.debug:
                print(f"🔊 TTS {'enabled' if enabled else 'disabled'}")

        # Stop any current speech when disabling
        if not enabled and self.voice_manager:
            try:
                self.voice_manager.stop()
                self._update_tts_toggle_state()
                
                # Manually trigger status update to "ready" since v0.5.1 callback won't fire
                # when we manually stop the audio
                if self.status_callback:
                    if self.debug:
                        print("🔊 QtChatBubble: TTS disabled, setting ready status")
                    self.status_callback("ready")
                    
            except Exception as e:
                if self.debug:
                    if self.debug:
                        print(f"❌ Error stopping TTS: {e}")
        elif enabled:
            # When enabling TTS, reset the toggle to the idle visual state.
            try:
                if hasattr(self, "tts_toggle") and self.tts_toggle:
                    self.tts_toggle.set_tts_state("idle")
            except Exception:
                pass

        # Update LLM session mode while preserving chat history
        if self.llm_manager:
            try:
                self.llm_manager.update_session_mode(tts_mode=enabled)
                if self.debug:
                    if self.debug:
                        print(f"🔄 LLM session mode updated for {'TTS' if enabled else 'normal'} mode (history preserved)")
            except Exception as e:
                if self.debug:
                    if self.debug:
                        print(f"❌ Error updating LLM session: {e}")

    def on_tts_single_click(self):
        """Handle single click on TTS toggle - pause/resume functionality."""
        if not self.voice_manager or not self.tts_enabled:
            return

        try:
            current_state = self.voice_manager.get_state()

            if current_state == 'speaking':
                # Pause the speech - may need multiple attempts if audio stream just started
                success = self._attempt_pause_with_retry()
                if success and self.debug:
                    if self.debug:
                        print("🔊 TTS paused via single click")
                elif self.debug:
                    if self.debug:
                        print("🔊 TTS pause failed - audio stream may not be ready yet")
            elif current_state == 'paused':
                # Resume the speech
                success = self.voice_manager.resume()
                if success and self.debug:
                    if self.debug:
                        print("🔊 TTS resumed via single click")
                elif self.debug:
                    if self.debug:
                        print("🔊 TTS resume failed")
            else:
                # If idle, do nothing or could show a message
                if self.debug:
                    if self.debug:
                        print("🔊 TTS single click - no active speech to pause/resume")

            # Update visual state
            self._update_tts_toggle_state()

        except Exception as e:
            if self.debug:
                if self.debug:
                    print(f"❌ Error handling TTS single click: {e}")

    def _attempt_pause_with_retry(self, max_attempts=5):
        """Attempt to pause with retry logic for timing issues.

        Args:
            max_attempts: Maximum number of pause attempts

        Returns:
            bool: True if pause succeeded, False otherwise
        """
        import time

        for attempt in range(max_attempts):
            if not self.voice_manager.is_speaking():
                # Speech ended while we were trying to pause
                return False

            success = self.voice_manager.pause()
            if success:
                return True

            if self.debug:
                if self.debug:
                    print(f"🔊 Pause attempt {attempt + 1}/{max_attempts} failed, retrying...")

            # Short delay before retry
            time.sleep(0.1)

        return False

    def on_tts_double_click(self):
        """Handle double click on TTS toggle - stop TTS and open chat bubble."""
        if self.debug:
            if self.debug:
                print("🔊 TTS double click - stopping speech and showing chat")

        # Prevent double-free errors by checking if objects are still valid
        try:
            # Stop any current speech with proper error handling
            if hasattr(self, 'voice_manager') and self.voice_manager and self.tts_enabled:
                try:
                    # Check if voice manager is still valid before calling methods
                    if hasattr(self.voice_manager, 'stop'):
                        self.voice_manager.stop()

                    # Safely update TTS toggle state
                    if hasattr(self, '_update_tts_toggle_state'):
                        self._update_tts_toggle_state()
                    
                    # Manually trigger status update to "ready" since v0.5.1 callback won't fire
                    # when we manually stop the audio
                    if hasattr(self, 'status_callback') and self.status_callback:
                        if self.debug:
                            print("🔊 QtChatBubble: Manually stopped TTS, setting ready status")
                        self.status_callback("ready")

                except Exception as e:
                    if self.debug:
                        if self.debug:
                            print(f"❌ Error stopping TTS on double click: {e}")

            # Show the chat bubble with safety checks
            if hasattr(self, 'show') and not self.isVisible():
                self.show()
            if hasattr(self, 'raise_'):
                self.raise_()
            if hasattr(self, 'activateWindow'):
                self.activateWindow()

        except Exception as e:
            if self.debug:
                print(f"❌ Critical error in on_tts_double_click: {e}")
            # Prevent crash - just show the bubble without TTS operations
            try:
                self.show()
            except:
                pass

    def on_full_voice_toggled(self, enabled: bool):
        """Handle Full Voice Mode toggle state change (always apply on Qt main thread)."""
        try:
            QTimer.singleShot(0, lambda e=bool(enabled): self._apply_full_voice_toggled(e))
        except Exception:
            self._apply_full_voice_toggled(bool(enabled))

    def _apply_full_voice_toggled(self, enabled: bool) -> None:
        if self.debug:
            print(f"🎙️  Full Voice Mode {'enabled' if enabled else 'disabled'}")

        if enabled:
            self.start_full_voice_mode()
        else:
            self.stop_full_voice_mode()

    def start_full_voice_mode(self):
        """Start Full Voice Mode - continuous listening with STT + TTS."""
        try:
            # Ensure voice manager is available
            if not self.voice_manager or not self.voice_manager.is_available():
                if self.debug:
                    print("❌ Voice manager not available for Full Voice Mode")
                self.full_voice_toggle.set_enabled(False)
                return

            if self.debug:
                if self.debug:
                    print("🚀 Starting Full Voice Mode...")

            # Keep the normal interface visible, but switch input actions to voice mode
            # (attach + tools remain usable; send is hidden).
            self.hide_text_ui()
            try:
                self._set_session_controls_enabled(False)
            except Exception:
                pass
            try:
                if self.history_dialog and self.history_dialog.isVisible():
                    self.history_dialog.hide()
                    self._update_history_button_appearance(False)
            except Exception:
                pass

            # Enable TTS automatically
            if not self.tts_enabled:
                self.tts_toggle.set_enabled(True)

            # Set up voice mode based on CLI parameter
            self.voice_manager.set_voice_mode(self.listening_mode)

            # Update LLM session mode for voice-optimized responses (preserve history)
            if self.llm_manager:
                self.llm_manager.update_session_mode(tts_mode=True)

            # Mark running before starting the underlying loop so late UI updates can be gated.
            self._full_voice_running = True
            try:
                # Invalidate any prior start attempts.
                self._voice_start_token = time.monotonic_ns()
            except Exception:
                self._voice_start_token = int(time.time() * 1000)

            try:
                # We're warming up the voice backend; show a "starting" state immediately.
                self.full_voice_toggle.set_listening_state("processing")
            except Exception:
                pass
            self.update_status("PROCESSING")

            # Start listening (can be slow on first run due to model init); do it off the UI thread.
            threading.Thread(
                target=self._start_full_voice_listen_background,
                args=(self._voice_start_token,),
                daemon=True,
            ).start()

            if self.debug:
                if self.debug:
                    print("✅ Full Voice Mode started successfully")

        except Exception as e:
            if self.debug:
                if self.debug:
                    print(f"❌ Error starting Full Voice Mode: {e}")
                import traceback
                traceback.print_exc()

            # Reset toggle state on error
            self._full_voice_running = False
            self.full_voice_toggle.set_enabled(False)
            self.show_text_ui()

    def _start_full_voice_listen_background(self, token: int) -> None:
        """Start the STT listening loop off the UI thread (may initialize heavy models)."""
        ok = False
        err: str | None = None
        try:
            started = self.voice_manager.listen(
                on_transcription=self.handle_voice_input,
                on_stop=self.handle_voice_stop,
            )
            ok = bool(started)
            if not ok:
                raise RuntimeError("Voice backend did not start listening.")
        except Exception as e:
            ok = False
            err = str(e)

        try:
            self._voice_start_result = {"token": int(token), "ok": bool(ok), "error": err}
        except Exception:
            pass

        try:
            QMetaObject.invokeMethod(self, "_finish_full_voice_listen_start_main_thread", Qt.QueuedConnection)
        except Exception:
            # Best-effort: if we can't hop back to the UI thread, give up silently.
            pass

    @pyqtSlot()
    def _finish_full_voice_listen_start_main_thread(self) -> None:
        """Finalize voice-mode startup on the Qt main thread."""
        try:
            res = getattr(self, "_voice_start_result", None) or {}
            token = int(res.get("token") or 0)
            ok = bool(res.get("ok"))
            err = str(res.get("error") or "").strip() or None
        except Exception:
            token = 0
            ok = False
            err = "unknown error"

        # Ignore stale results (user toggled voice mode off/on).
        try:
            current = int(getattr(self, "_voice_start_token", 0) or 0)
        except Exception:
            current = 0
        if int(current) != int(token):
            # If voice mode was stopped while the backend was starting, ensure we
            # don't leave a late-started recognizer running in the background.
            if not bool(getattr(self, "_full_voice_running", False)):
                try:
                    if self.voice_manager:
                        self.voice_manager.stop_listening()
                except Exception:
                    pass
            return

        if not ok:
            self._abort_full_voice_mode_with_error(
                "Voice mode failed",
                "Full voice mode couldn't start listening.\n\n"
                f"Error: {err or 'unknown'}\n\n"
                "If this persists, run the tray app with `--debug` for details.",
            )
            return

        # If the user already turned it off, stop listening and don't update UI.
        if not bool(getattr(self, "_full_voice_running", False)):
            try:
                if self.voice_manager:
                    self.voice_manager.stop_listening()
            except Exception:
                pass
            return

        # Make conversation snappy (short utterances + quicker silence endpointing).
        self._tune_voice_recognizer_for_conversation()
        # Catch common mic failures (permissions / device errors) quickly.
        self._schedule_voice_listen_watchdog()

        # Sanity check: ensure STT backend looks initialized (model loaded).
        try:
            rec = self._voice_recognizer()
            if rec is None:
                raise RuntimeError("Voice recognizer is not initialized")
            stt = getattr(rec, "stt_adapter", None)
            if stt is not None and hasattr(stt, "is_available") and not bool(stt.is_available()):
                raise RuntimeError("STT model not available (not loaded)")
        except Exception as e:
            self._abort_full_voice_mode_with_error(
                "Speech-to-text not ready",
                "Full voice mode started, but speech-to-text isn't ready.\n\n"
                f"Error: {e}\n\n"
                "Fix:\n"
                "1) Ensure `abstractassistant` is installed\n"
                "2) Restart AbstractAssistant\n"
                "3) If needed, re-install dependencies in a clean venv\n",
            )
            return

        try:
            self.full_voice_toggle.set_listening_state("listening")
        except Exception:
            pass
        self.update_status("LISTENING")

        # Ensure TTS playback updates UI state even for the activation greeting.
        try:
            def _speech_start() -> None:
                try:
                    QMetaObject.invokeMethod(self, "_on_speech_started_main_thread", Qt.QueuedConnection)
                except Exception:
                    pass

            def _speech_end() -> None:
                try:
                    QMetaObject.invokeMethod(self, "_on_speech_ended_main_thread", Qt.QueuedConnection)
                except Exception:
                    pass

            if self.voice_manager:
                self.voice_manager.on_speech_start = _speech_start
                self.voice_manager.on_speech_end = _speech_end
        except Exception:
            pass

        # Greet the user (non-blocking, avoid freezing the Qt event loop during synthesis).
        def _greet() -> None:
            try:
                if not bool(getattr(self, "_full_voice_running", False)):
                    return
                if self.voice_manager:
                    self.voice_manager.speak("Full voice mode activated. I'm listening...")
            except Exception:
                pass

        threading.Thread(target=_greet, daemon=True).start()

    def _is_full_voice_running(self) -> bool:
        """Centralized guard for any 'LISTENING' UI updates from async callbacks."""
        try:
            return bool(self._full_voice_running) and bool(self.full_voice_toggle.is_enabled())
        except Exception:
            return bool(getattr(self, "_full_voice_running", False))

    def stop_full_voice_mode(self):
        """Stop Full Voice Mode and return to normal text mode."""
        # IMPORTANT: make this robust. Even if voice backend stop throws, the UI must restore.
        if self.debug:
            if self.debug:
                print("🛑 Stopping Full Voice Mode...")

        # Gate all future async 'LISTENING' updates immediately.
        self._full_voice_running = False
        try:
            # Invalidate any in-flight start attempt.
            self._voice_start_token = 0
        except Exception:
            pass
        self._voice_busy = False

        # 1) Stop listening/speaking (best-effort, never block UI restore)
        if self.voice_manager:
            try:
                # Detach callbacks to avoid late status flips after shutdown.
                try:
                    self.voice_manager.on_speech_start = None
                    self.voice_manager.on_speech_end = None
                except Exception:
                    pass
                self.voice_manager.stop_listening()
            except Exception as e:
                if self.debug:
                    print(f"❌ Error stopping listening: {e}")
            try:
                self.voice_manager.stop_speaking()
            except Exception as e:
                if self.debug:
                    print(f"❌ Error stopping speaking: {e}")

        # 2) Turn off the speaker toggle (TTS) when leaving voice mode (as requested)
        try:
            if hasattr(self, "tts_toggle") and self.tts_toggle:
                self.tts_toggle.set_enabled(False)
            self.tts_enabled = False
        except Exception:
            pass

        try:
            if hasattr(self, "full_voice_toggle") and self.full_voice_toggle:
                self.full_voice_toggle.set_listening_state("idle")
        except Exception:
            pass

        # 3) Restore normal UI (Send visible again)
        try:
            self.show_text_ui()
        except Exception:
            pass

        # If no run is currently in progress, restore the send affordance immediately.
        try:
            if not self._is_run_in_progress():
                if getattr(self, "send_button", None) is not None:
                    self.send_button.setEnabled(True)
                    self.send_button.setText("→")
                self._set_session_controls_enabled(True)
        except Exception:
            pass

        # 4) Status back to Ready (green) + tray icon ready
        try:
            self.update_status("READY")
        except Exception:
            pass
        try:
            if self.status_callback:
                self.status_callback("ready")
        except Exception:
            pass

        if self.debug:
            if self.debug:
                print("✅ Full Voice Mode stopped")

    def handle_voice_input(self, transcribed_text: str):
        """Handle speech-to-text input.

        IMPORTANT: This callback is invoked from the microphone recognizer thread.
        Do not touch Qt widgets here; enqueue and dispatch to the Qt main thread.
        """
        # Ignore any late STT callbacks after the user stopped voice mode.
        if not bool(getattr(self, "_full_voice_running", False)):
            return

        text = str(transcribed_text or "").strip()
        if not text:
            return

        if self.debug:
            print(f"👤 Voice input: {text}")

        # Enqueue + drain on main thread (QTimer.singleShot is not reliable from non-Qt threads).
        try:
            with self._voice_transcription_queue_lock:
                self._voice_transcription_queue.append(text)
        except Exception:
            # Best-effort fallback (single latest transcription).
            try:
                self._pending_voice_transcription = text
            except Exception:
                return

        try:
            QMetaObject.invokeMethod(self, "_drain_voice_transcriptions", Qt.QueuedConnection)
        except Exception:
            # Best-effort fallback: if invokeMethod fails, don't crash the mic thread.
            pass

    @pyqtSlot()
    def _drain_voice_transcriptions(self) -> None:
        """Drain queued voice transcriptions on the Qt main thread."""
        if not self._is_full_voice_running():
            try:
                with self._voice_transcription_queue_lock:
                    self._voice_transcription_queue.clear()
            except Exception:
                pass
            try:
                if hasattr(self, "_pending_voice_transcription"):
                    self._pending_voice_transcription = None
            except Exception:
                pass
            return

        text: str | None = None
        try:
            with self._voice_transcription_queue_lock:
                while self._voice_transcription_queue:
                    text = self._voice_transcription_queue.pop()
                self._voice_transcription_queue.clear()
        except Exception:
            try:
                text = str(getattr(self, "_pending_voice_transcription", "") or "").strip() or None
                self._pending_voice_transcription = None
            except Exception:
                text = None

        if text:
            self._handle_voice_input_main_thread(str(text))

    def _handle_voice_input_main_thread(self, transcribed_text: str) -> None:
        """Execute a voice input turn on the Qt main thread."""
        if not self._is_full_voice_running():
            self._voice_busy = False
            return

        if self._voice_busy:
            if self.debug:
                print("🎙️  Ignoring transcription while busy")
            return

        self._voice_busy = True
        try:
            try:
                if hasattr(self, "full_voice_toggle") and self.full_voice_toggle:
                    self.full_voice_toggle.set_listening_state("processing")
            except Exception:
                pass
            self.update_status("PROCESSING")

            # Route through the same agentic sending path as typed input.
            try:
                self.input_text.setPlainText(str(transcribed_text or ""))
            except Exception:
                pass
            self.send_message()
        except Exception as e:
            self._voice_busy = False
            if self.debug:
                print(f"❌ Error handling voice input: {e}")
            try:
                if self._is_full_voice_running():
                    self.update_status("LISTENING")
            except Exception:
                pass

    def handle_voice_stop(self):
        """Handle when user says 'stop' to exit Full Voice Mode (thread-safe)."""
        if not bool(getattr(self, "_full_voice_running", False)):
            return
        if self.debug:
            print("🛑 User said 'stop' - exiting Full Voice Mode")

        try:
            QMetaObject.invokeMethod(self, "_handle_voice_stop_main_thread", Qt.QueuedConnection)
        except Exception:
            pass

    @pyqtSlot()
    def _handle_voice_stop_main_thread(self) -> None:
        """Exit voice mode due to stop phrase (Qt main thread)."""
        try:
            self.stop_full_voice_mode()
        except Exception:
            pass
        try:
            if hasattr(self, "full_voice_toggle") and self.full_voice_toggle:
                self.full_voice_toggle.blockSignals(True)
                try:
                    self.full_voice_toggle.set_enabled(False)
                finally:
                    self.full_voice_toggle.blockSignals(False)
        except Exception:
            pass

    def hide_text_ui(self):
        """Enter Full Voice Mode UI (no typing, voice-only)."""
        self._set_voice_ui_mode(True)

    def show_text_ui(self):
        """Exit Full Voice Mode UI (restore typing)."""
        self._set_voice_ui_mode(False)

    def _set_voice_ui_mode(self, enabled: bool) -> None:
        """
        Centralized UI state switch for voice mode.

        Requirements:
        - In voice mode, it's a pure spoken conversation: no typing, no Messages window.
        """
        enabled = bool(enabled)
        try:
            if hasattr(self, "input_container") and self.input_container:
                if enabled:
                    self.input_container.hide()
                else:
                    self.input_container.show()
        except Exception:
            pass

        # Toggle the action column behavior (keep internal state consistent).
        try:
            if hasattr(self, "_input_row") and self._input_row:
                self._input_row.set_voice_mode(enabled)
        except Exception:
            pass

        # No typing controls in voice mode.
        try:
            if hasattr(self, "send_button") and self.send_button:
                self.send_button.setVisible(not enabled)
                self.send_button.setEnabled(not enabled)
        except Exception:
            pass
        try:
            if hasattr(self, "input_text") and self.input_text:
                self.input_text.setEnabled(not enabled)
        except Exception:
            pass

        # Compact window in voice mode; restore after.
        try:
            if enabled:
                self.setFixedSize(self.base_width, 120)
            else:
                self._adjust_window_size_for_attachments()
        except Exception:
            pass

    def update_status(self, status_text: str):
        """Update the status label with the given text."""
        if hasattr(self, 'status_label'):
            self.status_label.setText(status_text.upper())

            # Update status label style based on status
            if status_text.lower() in ['ready', 'idle']:
                color = "#22c55e"  # Green
            elif status_text.lower() in ['listening']:
                color = "#ff6b35"  # Orange
            elif status_text.lower() in ['processing', 'generating']:
                color = "#ffa500"  # Yellow
            elif status_text.lower() in ['error']:
                color = "#ff3b30"  # Red
            else:
                color = "#007acc"  # Blue (default)

            self.status_label.setStyleSheet(f"""
                QLabel {{
                    background: {color};
                    border: none;
                    border-radius: 12px;
                    font-size: 10px;
                    font-weight: 600;
                    color: #ffffff;
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                }}
            """)

    def _update_tts_toggle_state(self):
        """Update the TTS toggle visual state based on current TTS state."""
        if hasattr(self, 'tts_toggle') and self.voice_manager:
            try:
                current_state = str(self.voice_manager.get_state() or "").strip().lower()
                if current_state not in {"idle", "speaking", "paused"}:
                    current_state = "idle"
                if not bool(getattr(self, "tts_enabled", False)):
                    current_state = "idle"
                try:
                    self.tts_toggle.set_tts_state(current_state)
                except Exception:
                    pass
            except Exception as e:
                if self.debug:
                    if self.debug:
                        print(f"❌ Error updating TTS toggle state: {e}")

    # Voice control panel methods removed - not needed

    def setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for voice control."""
        try:
            from PyQt5.QtWidgets import QShortcut
            from PyQt5.QtGui import QKeySequence

            # Space bar - Pause/Resume TTS
            self.space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
            self.space_shortcut.activated.connect(self.handle_space_shortcut)

            # Escape - Stop TTS
            self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
            self.escape_shortcut.activated.connect(self.handle_escape_shortcut)

            if self.debug:
                if self.debug:
                    print("✅ Keyboard shortcuts setup: Space (pause/resume), Escape (stop)")

        except Exception as e:
            if self.debug:
                if self.debug:
                    print(f"❌ Error setting up keyboard shortcuts: {e}")

    def handle_space_shortcut(self):
        """Handle space bar shortcut for pause/resume."""
        # Only handle if TTS is active and input field doesn't have focus
        if (self.voice_manager and self.voice_manager.get_state() in ['speaking', 'paused'] and
            not self.input_text.hasFocus()):
            self.on_tts_single_click()
            if self.debug:
                if self.debug:
                    print("🔊 Space shortcut triggered pause/resume")

    def handle_escape_shortcut(self):
        """Handle escape key shortcut for stop."""
        if self.voice_manager and self.voice_manager.get_state() in ['speaking', 'paused']:
            self.on_tts_double_click()
            if self.debug:
                if self.debug:
                    print("🔊 Escape shortcut triggered stop")
    
    def _clean_response_for_voice(self, text: str) -> str:
        """Clean response text for voice synthesis - remove formatting and make conversational."""
        import re
        
        # Remove markdown headers
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        
        # Remove markdown formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # Italic
        text = re.sub(r'_([^_]+)_', r'\1', text)        # Underscore
        
        # Remove code blocks completely
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        
        # Remove bullet points and lists
        text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
        
        # Remove markdown links
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Replace special characters with words
        replacements = {
            '&': ' and ',
            '@': ' at ',
            '#': ' hash ',
            '$': ' dollar ',
            '%': ' percent ',
            '→': ' to ',
            '←': ' from ',
            '+': ' plus ',
            '/': ' or ',
            '|': ' or ',
        }
        
        for symbol, word in replacements.items():
            text = text.replace(symbol, word)
        
        # Clean up whitespace and line breaks
        text = re.sub(r'\n+', ' ', text)  # Replace line breaks with spaces
        text = re.sub(r'\s+', ' ', text)  # Collapse multiple spaces
        text = text.strip()
        
        # NO TRUNCATION - let the LLM decide response length based on system prompt
        
        if self.debug:
            if self.debug:
                print(f"🔊 Cleaned text for TTS: {text[:100]}{'...' if len(text) > 100 else ''}")
        
        return text
    
    @pyqtSlot(str)
    def on_error_occurred(self, error):
        """Handle LLM error."""
        self.send_button.setEnabled(True)
        self.send_button.setText("→")
        self._set_session_controls_enabled(True)
        self.status_label.setText("error")
        self.status_label.setObjectName("status_error")
        self.status_label.setStyleSheet("""
            QLabel {
                background: rgba(243, 139, 168, 0.2);
                border: 1px solid rgba(243, 139, 168, 0.3);
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #f38ba8;
            }
        """)
        
        if self.debug:
            if self.debug:
                print(f"Error occurred: {error}")
        
        # Stop any tray icon "working" animation (ensure we don't spin forever on errors).
        try:
            if self.status_callback:
                self.status_callback("ready")
        except Exception:
            pass

        # Show chat history instead of error toast
        if self.debug:
            if self.debug:
                print(f"❌ AI Error: {error}")

        # Surface the error immediately in a modal (like tool approval prompts).
        # In full voice mode, avoid modal UI (voice-only): just resume listening.
        if not self._is_full_voice_running():
            err_txt = str(error or "").strip() or "Unknown error"
            informative = err_txt.splitlines()[0].strip() if err_txt else "Unknown error"
            lower = err_txt.lower()
            if "model unloaded" in lower:
                informative = (
                    "LM Studio says the model is unloaded. Load the model in LM Studio (or pick another model) "
                    "and try again."
                )
            elif "connection" in lower and ("refused" in lower or "failed" in lower):
                informative = "Couldn't reach the provider. Check that it is running and reachable, then try again."

            try:
                # Bring bubble forward so the modal isn't lost behind other windows.
                self.show()
                self.raise_()
                self.activateWindow()
            except Exception:
                pass

            try:
                box = QMessageBox(self)
                box.setWindowTitle("Request failed")
                box.setIcon(QMessageBox.Icon.Critical)
                box.setText("The assistant hit an error while generating a response.")
                box.setInformativeText(informative)
                box.setDetailedText(err_txt)
                box.exec()
            except Exception:
                pass

            # Show history so user can see the error context (only if voice mode is OFF).
            try:
                self._show_history_if_voice_mode_off()
            except Exception:
                pass

        # If we're in full voice mode, unblock the STT loop.
        if self._is_full_voice_running():
            self._voice_busy = False
            try:
                try:
                    if hasattr(self, "full_voice_toggle") and self.full_voice_toggle:
                        self.full_voice_toggle.set_listening_state("listening")
                except Exception:
                    pass
                self.update_status("LISTENING")
            except Exception:
                pass
        
        # Call error callback
        if self.error_callback:
            self.error_callback(error)
    
    def set_response_callback(self, callback):
        """Set response callback."""
        self.response_callback = callback
    
    def set_error_callback(self, callback):
        """Set error callback."""
        self.error_callback = callback
    
    def set_status_callback(self, callback):
        """Set status callback function."""
        self.status_callback = callback

    def _set_session_controls_enabled(self, enabled: bool) -> None:
        for attr in (
            "session_combo",
            "sessions_button",
            "new_session_button",
            "clear_session_button",
            "import_session_button",
            "export_session_button",
            "history_button",
        ):
            w = getattr(self, attr, None)
            if w is None:
                continue
            try:
                w.setEnabled(bool(enabled))
            except Exception:
                pass

    def _active_session_id(self) -> Optional[str]:
        try:
            sid = str(getattr(self.llm_manager, "active_session_id", "") or "").strip()
        except Exception:
            sid = ""
        return sid or self._selected_session_id()

    def _save_tool_prefs_for_session(self, session_id: Optional[str] = None) -> None:
        sid = str(session_id or self._active_session_id() or "").strip()
        if not sid:
            return
        self._session_auto_approve_tools_by_session[sid] = set(self._session_auto_approve_tools)
        self._session_force_ask_tools_by_session[sid] = set(self._session_force_ask_tools)

    def _load_tool_prefs_for_session(self, session_id: Optional[str] = None) -> None:
        sid = str(session_id or self._active_session_id() or "").strip()
        if not sid:
            self._session_auto_approve_tools = set()
            self._session_force_ask_tools = set()
            return
        self._session_auto_approve_tools = set(self._session_auto_approve_tools_by_session.get(sid, set()))
        self._session_force_ask_tools = set(self._session_force_ask_tools_by_session.get(sid, set()))

    def _selected_session_id(self) -> Optional[str]:
        combo = getattr(self, "session_combo", None)
        if combo is None:
            return None
        try:
            sid = combo.currentData()
        except Exception:
            sid = None
        sid = str(sid or "").strip()
        return sid or None

    def _reload_session_combo(self, *, select_session_id: Optional[str] = None) -> None:
        combo = getattr(self, "session_combo", None)
        if combo is None:
            return
        if not self.llm_manager or not hasattr(self.llm_manager, "list_sessions"):
            try:
                combo.clear()
                combo.addItem("Session")
                combo.setEnabled(False)
            except Exception:
                pass
            return

        try:
            sessions = list(self.llm_manager.list_sessions() or [])
        except Exception:
            sessions = []

        active = select_session_id or self._selected_session_id()
        if not active:
            try:
                active = str(getattr(self.llm_manager, "active_session_id", "") or "").strip()
            except Exception:
                active = None

        try:
            combo.blockSignals(True)
            combo.clear()

            select_index = 0
            items = 0
            for rec in sessions:
                if not isinstance(rec, dict):
                    continue
                sid = str(rec.get("session_id") or "").strip()
                if not sid:
                    continue
                title = str(rec.get("title") or "New session").strip() or "New session"
                label = title
                if title.strip().lower() == "new session":
                    stamp = str(rec.get("updated_at") or rec.get("created_at") or "").strip()
                    human = None
                    if stamp:
                        try:
                            dt = datetime.fromisoformat(stamp)
                            human = dt.astimezone().strftime("%b %d %H:%M")
                        except Exception:
                            human = None
                    label = f"{title} • {human}" if human else f"{title} • {sid[-6:]}"
                combo.addItem(label, sid)
                try:
                    idx = combo.count() - 1
                    role = getattr(Qt, "ToolTipRole", None) or getattr(getattr(Qt, "ItemDataRole", object), "ToolTipRole", None)
                    if role is not None:
                        tip_lines = [title, sid]
                        updated = str(rec.get("updated_at") or "").strip()
                        if updated:
                            tip_lines.append(f"Updated: {updated}")
                        combo.setItemData(idx, "\n".join(tip_lines), role)
                except Exception:
                    pass
                if active and sid == active:
                    select_index = items
                items += 1

            if combo.count() <= 0:
                combo.addItem("New session")
                combo.setEnabled(False)
            else:
                combo.setEnabled(True)
                combo.setCurrentIndex(select_index)
        finally:
            try:
                combo.blockSignals(False)
            except Exception:
                pass

    def _switch_session_via_combo(self, session_id: str) -> None:
        """Switch sessions by selecting the matching hidden combo entry (reuses existing logic)."""
        sid = str(session_id or "").strip()
        if not sid:
            return

        combo = getattr(self, "session_combo", None)
        if combo is None:
            return

        def _find_index() -> Optional[int]:
            try:
                n = int(combo.count())
            except Exception:
                n = 0
            for i in range(max(0, n)):
                try:
                    data = combo.itemData(i)
                except Exception:
                    data = None
                if str(data or "").strip() == sid:
                    return i
            return None

        idx = _find_index()
        if idx is None:
            try:
                self._reload_session_combo()
            except Exception:
                pass
            idx = _find_index()

        if idx is None:
            return

        try:
            combo.setCurrentIndex(int(idx))
        except Exception:
            pass

    def open_sessions_dialog(self) -> None:
        """Open the Sessions dialog (replaces the header dropdown)."""
        if not self.llm_manager or not hasattr(self.llm_manager, "list_sessions"):
            return
        try:
            self._reload_session_combo(select_session_id=getattr(self.llm_manager, "active_session_id", None))
        except Exception:
            pass
        dlg = SessionsDialog(parent=self, bubble=self)
        try:
            dlg.exec()
        except Exception:
            try:
                dlg.exec_()  # type: ignore[attr-defined]
            except Exception:
                pass

    def _is_run_in_progress(self) -> bool:
        try:
            if self.worker is not None and hasattr(self.worker, "isRunning") and self.worker.isRunning():
                return True
        except Exception:
            pass
        try:
            return not bool(self.send_button.isEnabled())
        except Exception:
            return False

    def _on_session_combo_changed(self, index: int) -> None:
        if not self.llm_manager or not hasattr(self.llm_manager, "switch_session"):
            return

        combo = getattr(self, "session_combo", None)
        if combo is None:
            return

        try:
            sid = combo.itemData(int(index))
        except Exception:
            sid = None
        sid = str(sid or "").strip()
        if not sid:
            return

        try:
            current = str(getattr(self.llm_manager, "active_session_id", "") or "").strip()
        except Exception:
            current = ""
        if sid == current:
            return

        if self._is_run_in_progress():
            QMessageBox.information(self, "Session switch", "Please wait for the current response to finish.")
            self._reload_session_combo(select_session_id=current or None)
            return

        try:
            self._save_tool_prefs_for_session(current or None)
            self.llm_manager.switch_session(sid)
        except Exception as e:
            QMessageBox.warning(self, "Session switch", f"Failed to switch session:\n{e}")
            self._reload_session_combo(select_session_id=current or None)
            return

        try:
            if hasattr(self.llm_manager, "refresh"):
                self.llm_manager.refresh()
        except Exception:
            pass

        self._reload_session_combo(select_session_id=sid)
        self._load_tool_prefs_for_session(sid)
        self._refresh_tool_inventory()

        # Reset per-session UI caches.
        self.attached_files.clear()
        self.message_file_attachments.clear()
        self.update_attached_files_display()

        self._update_message_history_from_session()
        self._update_token_count_from_session()
        self._rebuild_chat_display()

        # If the history window is open but the new session is empty, hide it.
        if self.history_dialog and self.history_dialog.isVisible() and not self.message_history:
            try:
                self.history_dialog.hide()
                self._update_history_button_appearance(False)
            except Exception:
                pass

    def _start_new_session(self) -> None:
        if not self.llm_manager or not hasattr(self.llm_manager, "create_new_session"):
            return

        if self._is_run_in_progress():
            QMessageBox.information(self, "New session", "Please wait for the current response to finish.")
            return

        old_id = self._active_session_id()
        if old_id:
            self._save_tool_prefs_for_session(old_id)

        try:
            new_id = str(self.llm_manager.create_new_session() or "").strip()
        except Exception as e:
            QMessageBox.warning(self, "New session", f"Failed to create a new session:\n{e}")
            return

        self._load_tool_prefs_for_session(new_id or None)
        self._refresh_tool_inventory()

        # Reset per-session UI caches.
        self.attached_files.clear()
        self.message_file_attachments.clear()
        self.update_attached_files_display()

        self._update_message_history_from_session()
        self._update_token_count_from_session()
        self._rebuild_chat_display()

        if self.history_dialog and self.history_dialog.isVisible():
            try:
                self.history_dialog.hide()
                self._update_history_button_appearance(False)
            except Exception:
                pass

        self._reload_session_combo(select_session_id=new_id or None)

    @pyqtSlot()
    def _refresh_session_combo_ui(self) -> None:
        try:
            self._reload_session_combo()
        except Exception:
            pass

    def _show_more_menu(self) -> None:
        btn = getattr(self, "more_button", None)
        if btn is None:
            return
        menu = QMenu(self)
        menu.addAction("Load…", self.load_session)
        menu.addAction("Save…", self.save_session)
        if bool(getattr(self, "debug", False)):
            menu.addSeparator()
            menu.addAction("Run trace (debug)…", self.show_trace)

        try:
            pos = btn.mapToGlobal(QPoint(0, btn.height()))
        except Exception:
            pos = None

        try:
            if pos is None:
                if hasattr(menu, "exec_"):
                    menu.exec_()
                else:
                    menu.exec()
            else:
                if hasattr(menu, "exec_"):
                    menu.exec_(pos)
                else:
                    menu.exec(pos)
        except Exception:
            return

    def clear_active_session_contents(self) -> None:
        """Clear all messages/attachments in the active session (does not create a new session)."""
        if self._is_run_in_progress():
            QMessageBox.information(self, "Clear session", "Please wait for the current response to finish.")
            return

        if not self.llm_manager:
            return

        has_anything = bool(self.message_history) or bool(getattr(self, "attached_files", []))
        if not has_anything:
            QMessageBox.information(self, "Clear session", "This session is already empty.")
            return

        reply = QMessageBox.question(
            self,
            "Clear Session",
            "Clear this session?\n\nThis removes all messages and attachments from the current session.\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            reset = getattr(self.llm_manager, "reset_active_session", None)
            if callable(reset):
                reset(tts_mode=bool(getattr(self, "tts_enabled", False)))
            else:
                clear = getattr(self.llm_manager, "clear_session", None)
                if callable(clear):
                    clear()
        except Exception as e:
            QMessageBox.critical(self, "Clear session", f"Failed to clear this session:\n{e}")
            return

        try:
            if hasattr(self.llm_manager, "refresh"):
                self.llm_manager.refresh()
        except Exception:
            pass

        # Reset per-session UI caches.
        try:
            self.attached_files.clear()
            self.message_file_attachments.clear()
            self.update_attached_files_display()
        except Exception:
            pass

        self._update_message_history_from_session()
        self._update_token_count_from_session()
        self._rebuild_chat_display()

        # If the history window is open, refresh it to reflect the cleared session.
        if self.history_dialog and self.history_dialog.isVisible():
            try:
                self.history_dialog.refresh_messages(self.message_history)
            except Exception:
                pass

        # Keep the header/session list up to date (message counts, updated_at).
        try:
            self._reload_session_combo(select_session_id=self._active_session_id())
        except Exception:
            pass
    
    def clear_session(self):
        """Start a new session (prior sessions remain available)."""
        reply = QMessageBox.question(
            self,
            "New Session",
            "Start a new session?\nYour previous sessions will remain available in the session dropdown.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._start_new_session()
    
    def compact_session(self):
        """Compact the current session using AbstractCore's summarizer functionality."""
        if not self.message_history:
            QMessageBox.information(
                self,
                "No Session",
                "No conversation history to compact. Start a conversation first."
            )
            return
        
        # Check if session is too short to compact
        if len(self.message_history) < 4:  # Need at least 2 exchanges to be worth compacting
            QMessageBox.information(
                self,
                "Session Too Short",
                "Session is too short to compact. Need at least 2 exchanges (4 messages)."
            )
            return
        
        reply = QMessageBox.question(
            self, 
            "Compact Session", 
            "This will summarize the conversation history into a concise system message, "
            "keeping only the most recent 2 exchanges for context.\n\n"
            "This action cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Show progress
                self.status_label.setText("compacting")
                self.status_label.setStyleSheet("""
                    QLabel {
                        background: rgba(250, 179, 135, 0.2);
                        border: 1px solid rgba(250, 179, 135, 0.3);
                        border-radius: 12px;
                        padding: 4px 12px;
                        font-size: 11px;
                        font-weight: 600;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        color: #fab387;
                    }
                """)
                
                # Notify main app about status change
                if self.status_callback:
                    self.status_callback("compacting")
                
                # Create conversation text for summarization
                conversation_text = self._format_conversation_for_summarization()
                
                # Use AbstractCore's summarizer functionality through LLMManager
                summary = self._generate_conversation_summary(conversation_text)
                
                if summary:
                    # Keep the last 2 exchanges (4 messages) for context
                    recent_messages = self.message_history[-4:] if len(self.message_history) >= 4 else self.message_history[-2:]
                    
                    # Create new session with summary as system context
                    self._create_compacted_session(summary, recent_messages)
                    
                    # Update UI
                    self.token_count = 0  # Reset token count
                    self.update_token_display()
                    
                    # Show success message
                    QMessageBox.information(
                        self,
                        "Session Compacted",
                        f"Session successfully compacted!\n\n"
                        f"Original: {len(self.message_history)} messages\n"
                        f"Compacted: Summary + {len(recent_messages)} recent messages"
                    )
                    
                    if self.debug:
                        print(f"🗜️ Session compacted: {len(self.message_history)} -> summary + {len(recent_messages)} recent")
                else:
                    raise Exception("Failed to generate summary")
                    
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Compaction Error",
                    f"Failed to compact session:\n{str(e)}"
                )
                if self.debug:
                    print(f"❌ Failed to compact session: {e}")
                    import traceback
                    traceback.print_exc()
            finally:
                # Reset status
                self.status_label.setText("ready")
                self.status_label.setStyleSheet("""
                    QLabel {
                        background: rgba(166, 227, 161, 0.2);
                        border: 1px solid rgba(166, 227, 161, 0.3);
                        border-radius: 12px;
                        padding: 4px 12px;
                        font-size: 11px;
                        font-weight: 600;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        color: #a6e3a1;
                    }
                """)
                if self.status_callback:
                    self.status_callback("ready")
    
    def _format_conversation_for_summarization(self) -> str:
        """Format the conversation history for summarization."""
        lines = []
        lines.append("=== CONVERSATION HISTORY ===\n")
        
        for i, msg in enumerate(self.message_history):
            role = "USER" if msg.get('type') == 'user' else "ASSISTANT"
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            
            # Add timestamp if available
            if timestamp:
                try:
                    from datetime import datetime
                    if isinstance(timestamp, str):
                        dt = datetime.fromisoformat(timestamp)
                        time_str = dt.strftime("%Y-%m-%d %H:%M")
                        lines.append(f"[{time_str}] {role}:")
                    else:
                        lines.append(f"{role}:")
                except:
                    lines.append(f"{role}:")
            else:
                lines.append(f"{role}:")
            
            lines.append(content)
            lines.append("")  # Empty line between messages
        
        return "\n".join(lines)
    
    def _generate_conversation_summary(self, conversation_text: str) -> str:
        """Generate a conversation summary using AbstractCore's summarizer functionality."""
        try:
            # Use the current LLM to generate a summary
            # This mimics what the AbstractCore summarizer CLI does
            summary_prompt = f"""Please provide a comprehensive but concise summary of the following conversation. 
Focus on:
- Key topics discussed
- Important decisions or conclusions reached
- Relevant context that should be preserved
- Any ongoing tasks or questions

The summary should be detailed enough to provide context for continuing the conversation, but concise enough to save tokens.

Conversation to summarize:
{conversation_text}

Please provide the summary in a clear, structured format:"""

            if self.llm_manager and self.llm_manager.llm:
                # Generate summary using current LLM
                response = self.llm_manager.llm.generate(summary_prompt)
                
                if hasattr(response, 'content'):
                    return response.content
                else:
                    return str(response)
            else:
                raise Exception("No LLM available for summarization")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error generating summary: {e}")
            raise
    
    def _create_compacted_session(self, summary: str, recent_messages: list):
        """Create a new session with the summary and recent messages."""
        try:
            # Create new session with summary embedded in the system prompt.
            final_system_prompt = f"""You are a helpful AI assistant who has access to tools to help the user.
Always be a critical and creative thinker who leverage constructive skepticism to progress and evolve its reasoning and answers.
Always answer in nicely formatted markdown.

=== CONVERSATION CONTEXT ===
The following is a summary of our previous conversation:

{summary}

=== END CONTEXT ===

Continue the conversation naturally, referring to the context above when relevant."""

            # Create new session with the composed system prompt
            if self.llm_manager:
                # Create new session with custom system prompt
                from abstractcore import BasicSession
                
                # Prepare tools list (same as in LLMManager)
                tools = []
                try:
                    from abstractcore.tools.common_tools import (
                        list_files, search_files, read_file, edit_file, 
                        write_file, execute_command, web_search
                    )
                    tools = [
                        list_files, search_files, read_file, edit_file,
                        write_file, execute_command, web_search
                    ]
                except ImportError:
                    pass
                
                # Create new session with summary in system prompt
                new_session = BasicSession(
                    self.llm_manager.llm,
                    system_prompt=final_system_prompt,
                    tools=tools
                )
                
                # Add recent messages to the new session
                for msg in recent_messages:
                    if msg.get('type') == 'user':
                        # Add user message without generating response
                        from abstractcore.messages import UserMessage
                        user_msg = UserMessage(content=msg.get('content', ''))
                        new_session.messages.append(user_msg)
                    elif msg.get('type') == 'assistant':
                        # Add assistant message
                        from abstractcore.messages import AssistantMessage
                        assistant_msg = AssistantMessage(content=msg.get('content', ''))
                        new_session.messages.append(assistant_msg)
                
                # Replace current session
                self.llm_manager.current_session = new_session
                
                # Update local message history to reflect the compacted state
                # Create a special "system" message to represent the summary
                compacted_history = [
                    {
                        'timestamp': datetime.now().isoformat(),
                        'type': 'system',
                        'content': f"📋 **Session Compacted**\n\n{summary}",
                        'provider': self.current_provider,
                        'model': self.current_model,
                        'attached_files': []
                    }
                ]
                
                # Add recent messages
                compacted_history.extend(recent_messages)
                
                # Update message history
                self.message_history = compacted_history
                
                if self.debug:
                    print(f"✅ Created compacted session with enhanced system prompt")
                    
        except Exception as e:
            if self.debug:
                print(f"❌ Error creating compacted session: {e}")
            raise
    
    def load_session(self):
        """Load a session using AbstractCore via LLMManager."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Session",
            str(Path.home() / "Documents"),
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                # Use AbstractCore session loading via LLMManager
                success = self.llm_manager.load_session(file_path)

                if success:
                    # Get session info from AbstractCore
                    if self.llm_manager.current_session:
                        # Estimate message count from session
                        session_data = self.llm_manager.current_session
                        message_count = len(getattr(session_data, 'messages', []))

                        # Update token display
                        self.update_token_display()

                        # Update our local message history from AbstractCore
                        self._update_message_history_from_session()
                        self._update_token_count_from_session()
                        self._reload_session_combo()
                        self._rebuild_chat_display()

                        QMessageBox.information(
                            self,
                            "Session Loaded",
                            f"Successfully loaded session via AbstractCore.\nMessages: {message_count}"
                        )

                        if self.debug:
                            if self.debug:
                                print(f"📂 Loaded session via AbstractCore from {file_path}")
                    else:
                        raise Exception("Session loaded but not available in LLMManager")
                else:
                    raise Exception("AbstractCore session loading failed")

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Load Error",
                    f"Failed to load session via AbstractCore:\n{str(e)}"
                )
                if self.debug:
                    if self.debug:
                        print(f"❌ Failed to load session: {e}")
    
    def save_session(self):
        """Save the current session using AbstractCore via LLMManager."""
        if not self.llm_manager.current_session:
            QMessageBox.information(
                self,
                "No Session",
                "No active session to save. Start a conversation first."
            )
            return

        # Generate default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"abstractcore_session_{timestamp}.json"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session",
            str(Path.home() / "Documents" / default_filename),
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                # Use AbstractCore session saving via LLMManager
                success = self.llm_manager.save_session(file_path)

                if success:
                    QMessageBox.information(
                        self,
                        "Session Saved",
                        f"Session saved successfully via AbstractCore to:\n{file_path}"
                    )

                    if self.debug:
                        if self.debug:
                            print(f"💾 Saved session via AbstractCore to {file_path}")
                else:
                    raise Exception("AbstractCore session saving failed")

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Save Error",
                    f"Failed to save session via AbstractCore:\n{str(e)}"
                )
                if self.debug:
                    if self.debug:
                        print(f"❌ Failed to save session: {e}")
    
    def _is_voice_mode_active(self):
        """Centralized source of truth: Check if ANY voice mode is active."""
        # Check Full Voice Mode (listening/speaking conversations)
        if hasattr(self, 'full_voice_toggle') and self.full_voice_toggle and self.full_voice_toggle.is_enabled():
            return True

        # Check if TTS is currently speaking
        if hasattr(self, 'voice_manager') and self.voice_manager:
            try:
                if self.voice_manager.is_speaking():
                    return True
            except:
                pass

        return False

    def _should_show_chat_history(self):
        """Centralized source of truth: Should chat history be visible?"""
        # chat_history_visible = is_voice_mode_off
        return not self._is_voice_mode_active()

    def _update_message_history_from_session(self):
        """Update local message history from the durable agent snapshot (preferred).

        Notes:
        - Runtime-backed agents include role="tool" observations in the transcript so the
          model can continue tool loops. Those are hidden from the user-visible history
          and replaced with a compact per-answer tool summary + resource links.
        """
        if not self.llm_manager:
            return

        from ..core.transcript_summary import build_display_messages

        raw_messages = None
        try:
            host = getattr(self.llm_manager, "agent_host", None)
            snap = getattr(host, "snapshot", None) if host is not None else None
            raw_messages = getattr(snap, "messages", None) if snap is not None else None
        except Exception:
            raw_messages = None

        messages: List[Dict] = []
        if isinstance(raw_messages, list):
            messages = [dict(m) for m in raw_messages if isinstance(m, dict)]
        elif getattr(self.llm_manager, "current_session", None) is not None:
            try:
                session_messages = getattr(self.llm_manager.current_session, "messages", [])
                for msg in session_messages:
                    role = getattr(msg, "role", "unknown")
                    content = getattr(msg, "content", str(msg))
                    messages.append({"role": str(role), "content": str(content)})
            except Exception:
                messages = []

        try:
            rendered = build_display_messages(messages)

            self.message_history = []
            for m in rendered:
                role = str(m.get("role") or "unknown")
                content = str(m.get("content") or "")
                timestamp = m.get("timestamp")
                if not isinstance(timestamp, (str, int, float)) or (isinstance(timestamp, str) and not timestamp.strip()):
                    timestamp = datetime.now().isoformat()

                entry: Dict[str, Any] = {
                    "timestamp": timestamp,
                    "type": role,
                    "content": content,
                    "provider": self.current_provider,
                    "model": self.current_model,
                    "attached_files": self.message_file_attachments.get(len(self.message_history), []),
                }

                ui_kind = m.get("ui_kind")
                if isinstance(ui_kind, str) and ui_kind.strip():
                    entry["ui_kind"] = ui_kind.strip()

                tool_summary = m.get("tool_summary")
                if isinstance(tool_summary, str) and tool_summary.strip():
                    entry["tool_summary"] = tool_summary.strip()
                tool_links = m.get("tool_links")
                if isinstance(tool_links, list) and tool_links:
                    entry["tool_links"] = [dict(x) for x in tool_links if isinstance(x, dict)]

                image_thumbnails = m.get("image_thumbnails")
                if isinstance(image_thumbnails, list) and image_thumbnails:
                    entry["image_thumbnails"] = [dict(x) for x in image_thumbnails if isinstance(x, dict)]

                self.message_history.append(entry)

            if self.debug:
                print(f"📚 Updated message history: {len(self.message_history)} messages")

        except Exception as e:
            if self.debug:
                print(f"❌ Error updating message history from snapshot/session: {e}")

    def _rebuild_chat_display(self):
        """Rebuild chat display after session loading.
        
        Since the main bubble doesn't have a chat display area, this method
        updates the history dialog if it's currently open.
        """
        try:
            # If history dialog is open, refresh it with new message history
            if self.history_dialog and self.history_dialog.isVisible():
                self.history_dialog.refresh_messages(self.message_history)
                if self.debug:
                    print("🔄 Refreshed history dialog with loaded session messages")
            
            # No action needed if history dialog is closed since main bubble has no chat display
            if self.debug:
                print("✅ Chat display rebuild completed")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error rebuilding chat display: {e}")

    def _update_token_count_from_session(self):
        """Update token count from AbstractCore session."""
        try:
            if self.llm_manager and self.llm_manager.current_session:
                token_estimate = self.llm_manager.current_session.get_token_estimate()
                self.token_count = token_estimate
                self.update_token_display()

                if self.debug:
                    if self.debug:
                        print(f"📊 Updated token count from AbstractCore: {self.token_count}")
        except Exception as e:
            if self.debug:
                if self.debug:
                    print(f"❌ Error updating token count from session: {e}")

    def show_trace(self):
        """Show a lightweight debug trace for the last run."""
        host = getattr(self.llm_manager, "agent_host", None)
        run_id = None
        try:
            snap = getattr(host, "snapshot", None)
            run_id = getattr(snap, "last_run_id", None) if snap else None
        except Exception:
            run_id = None

        rid = str(run_id or "").strip()
        if not host or not rid:
            QMessageBox.information(self, "Run trace", "No run is available yet.")
            return

        try:
            ensure = getattr(host, "_ensure_ready", None)
            if callable(ensure):
                ensure()
        except Exception:
            pass

        rt = getattr(host, "_runtime", None)
        if rt is None:
            QMessageBox.information(self, "Run trace", "Runtime is not initialized yet.")
            return

        try:
            state = rt.get_state(rid)
            payload = {
                "run_id": getattr(state, "run_id", rid),
                "status": str(getattr(state, "status", "")),
                "workflow_id": getattr(state, "workflow_id", None),
                "actor_id": getattr(state, "actor_id", None),
                "session_id": getattr(state, "session_id", None),
                "waiting": str(getattr(state, "waiting", None) or ""),
                "error": str(getattr(state, "error", None) or ""),
                "vars_keys": sorted(list(getattr(state, "vars", {}).keys())) if isinstance(getattr(state, "vars", None), dict) else [],
                "output_keys": sorted(list(getattr(state, "output", {}).keys())) if isinstance(getattr(state, "output", None), dict) else [],
            }

            details_obj = {
                "summary": payload,
                "vars": getattr(state, "vars", None),
                "output": getattr(state, "output", None),
            }
            details_txt = json.dumps(details_obj, ensure_ascii=False, indent=2, default=str)
            if len(details_txt) > 20000:
                details_txt = details_txt[:20000] + "\n…(truncated)…"

            box = QMessageBox(self)
            box.setWindowTitle("Run trace")
            box.setIcon(QMessageBox.Icon.Information)
            box.setText("Last run trace (summary).")
            box.setInformativeText(
                "\n".join(
                    [
                        f"Run ID: {payload['run_id']}",
                        f"Status: {payload['status']}",
                        f"Workflow: {payload['workflow_id']}",
                        f"Actor: {payload['actor_id']}",
                    ]
                )
            )
            box.setDetailedText(details_txt)
            box.exec()
        except Exception as e:
            QMessageBox.warning(self, "Run trace", f"Failed to load trace:\n{e}")

    def _show_history_if_voice_mode_off(self):
        """Show chat history only if voice mode is OFF."""
        if not self._should_show_chat_history():
            if self.debug:
                print("🎙️ Chat history blocked - Voice mode is active")
            return

        # Voice mode is off, show history
        self.show_history()

    def show_history(self):
        """Toggle message history dialog visibility."""
        # Use centralized logic to check if chat history should be shown
        if not self._should_show_chat_history():
            if self.debug:
                print("🎙️ Chat history blocked - Voice mode is active")
            return

        if not self.message_history:
            QMessageBox.information(
                self,
                "No History",
                "No message history available. Start a conversation first."
            )
            return

        # Toggle behavior: create dialog if doesn't exist, toggle visibility if it does
        if iPhoneMessagesDialog:
            if self.history_dialog is None:
                # Create dialog first time with deletion support
                self.history_dialog = iPhoneMessagesDialog.create_dialog(
                    self.message_history, 
                    self, 
                    delete_callback=self._handle_message_deletion
                )
                # Set callback to update button when dialog is hidden via Back button
                self.history_dialog.set_hide_callback(lambda: self._update_history_button_appearance(False))
                self.history_dialog.show()
                self._update_history_button_appearance(True)
            else:
                # Toggle visibility
                if self.history_dialog.isVisible():
                    self.history_dialog.hide()
                    self._update_history_button_appearance(False)
                else:
                    # Update dialog with latest messages before showing
                    self.history_dialog = iPhoneMessagesDialog.create_dialog(
                        self.message_history, 
                        self, 
                        delete_callback=self._handle_message_deletion
                    )
                    # Set callback to update button when dialog is hidden via Back button
                    self.history_dialog.set_hide_callback(lambda: self._update_history_button_appearance(False))
                    self.history_dialog.show()
                    self._update_history_button_appearance(True)
        else:
            # Fallback if the module isn't available
            QMessageBox.information(
                self,
                "History Unavailable",
                "History dialog module not available."
            )

    def _update_history_button_appearance(self, is_active: bool):
        """Update history button appearance to show toggle state."""
        if hasattr(self, 'history_button'):
            if is_active:
                # Active state - highlighted
                self.history_button.setStyleSheet("""
                    QPushButton {
                        background: rgba(0, 122, 255, 0.8);
                        border: none;
                        border-radius: 11px;
                        font-size: 10px;
                        color: #ffffff;
                        font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                        padding: 0 10px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background: rgba(0, 122, 255, 1.0);
                    }
                """)
            else:
                # Inactive state - normal
                self.history_button.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.06);
                        border: none;
                        border-radius: 11px;
                        font-size: 10px;
                        color: rgba(255, 255, 255, 0.7);
                        font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                        padding: 0 10px;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.1);
                        color: rgba(255, 255, 255, 0.9);
                    }
                """)

    def _handle_message_deletion(self, indices_to_delete: List[int]):
        """Handle deletion of messages from the history dialog."""
        try:
            if not indices_to_delete:
                return

            # Validate indices
            for index in indices_to_delete:
                if not (0 <= index < len(self.message_history)):
                    QMessageBox.critical(
                        self,
                        "Invalid Selection",
                        f"Invalid message index {index}. Please refresh and try again."
                    )
                    return
            
            # Delete messages from local history (indices are sorted in reverse order)
            original_count = len(self.message_history)
            
            for index in indices_to_delete:
                if 0 <= index < len(self.message_history):
                    del self.message_history[index]
            
            # Update AbstractCore session to reflect deletions
            self._update_abstractcore_session_after_deletion()
            
            # Update token count
            self._update_token_count_from_session()
            
            # Update history dialog if it's open (keep it open!)
            if self.history_dialog and self.history_dialog.isVisible():
                try:
                    # Update the dialog content without closing it
                    self.history_dialog.update_message_history(self.message_history)
                except Exception as dialog_error:
                    import traceback
                    traceback.print_exc()
                    # Fallback: recreate dialog if update fails
                    try:
                        if len(self.message_history) == 0:
                            self.history_dialog.hide()
                            self._update_history_button_appearance(False)
                        else:
                            new_dialog = iPhoneMessagesDialog.create_dialog(
                                self.message_history, 
                                self, 
                                delete_callback=self._handle_message_deletion
                            )
                            if new_dialog:
                                old_pos = self.history_dialog.pos()
                                self.history_dialog.hide()
                                self.history_dialog = new_dialog
                                self.history_dialog.move(old_pos)  # Keep same position
                                self.history_dialog.set_hide_callback(lambda: self._update_history_button_appearance(False))
                                self.history_dialog.show()
                    except:
                        try:
                            self.history_dialog.hide()
                            self._update_history_button_appearance(False)
                        except:
                            pass
            
            # Log success (no popup)
            deleted_count = original_count - len(self.message_history)
            
            if self.debug:
                print(f"🗑️ Deleted {deleted_count} messages from history")
                
        except Exception as e:
            print(f"❌ Critical error in _handle_message_deletion: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                QMessageBox.critical(
                    self,
                    "Deletion Error",
                    f"Failed to delete messages:\n{str(e)}\n\nCheck console for details."
                )
            except:
                print("❌ Could not show error dialog")
            
            if self.debug:
                print(f"❌ Failed to delete messages: {e}")
                import traceback
                traceback.print_exc()

    def _update_abstractcore_session_after_deletion(self):
        """Update AbstractCore session to reflect message deletions."""
        try:
            if not self.llm_manager or not self.llm_manager.current_session:
                return
            
            # Get current system prompt
            current_session = self.llm_manager.current_session
            system_prompt = getattr(current_session, 'system_prompt', None) or """
                You are a helpful AI assistant who has access to tools to help the user.
                Always be a critical and creative thinker who leverage constructive skepticism to progress and evolve its reasoning and answers.
                Always answer in nicely formatted markdown.
            """
            
            # Prepare tools list (same as in LLMManager)
            tools = []
            try:
                from abstractcore.tools.common_tools import (
                    list_files, search_files, read_file, edit_file, 
                    write_file, execute_command, web_search
                )
                tools = [
                    list_files, search_files, read_file, edit_file,
                    write_file, execute_command, web_search
                ]
            except ImportError as import_error:
                pass
                pass
            
            # Create new session with updated message history
            from abstractcore import BasicSession
            new_session = BasicSession(
                self.llm_manager.llm,
                system_prompt=system_prompt,
                tools=tools
            )
            
            # Add remaining messages to the new session
            for i, msg in enumerate(self.message_history):
                try:
                    if msg.get('type') == 'user':
                        from abstractcore.messages import UserMessage
                        user_msg = UserMessage(content=msg.get('content', ''))
                        new_session.messages.append(user_msg)
                    elif msg.get('type') == 'assistant':
                        from abstractcore.messages import AssistantMessage
                        assistant_msg = AssistantMessage(content=msg.get('content', ''))
                        new_session.messages.append(assistant_msg)
                    elif msg.get('type') == 'system':
                        # Skip system messages (handled by system_prompt)
                        pass
                    else:
                        # Unknown message type
                        pass
                except Exception as msg_error:
                    # Continue with other messages
                    pass
            
            # Replace current session
            self.llm_manager.current_session = new_session
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            # Don't raise - this is not critical for the UI operation

    def close_app(self):
        """Close the entire application completely."""
        if self.debug:
            if self.debug:
                print("🔄 Close button clicked - shutting down application")

        # Stop TTS if running
        if hasattr(self, 'voice_manager') and self.voice_manager:
            self.voice_manager.cleanup()

        # Close the chat bubble
        self.hide()

        # Close history dialog if open
        if hasattr(self, 'history_dialog') and self.history_dialog:
            self.history_dialog.hide()

        # ALWAYS try to call the app quit callback first
        if hasattr(self, 'app_quit_callback') and self.app_quit_callback:
            if self.debug:
                if self.debug:
                    print("🔄 Calling app quit callback")
            try:
                self.app_quit_callback()
            except Exception as e:
                if self.debug:
                    if self.debug:
                        print(f"❌ App callback failed: {e}")

        # ALWAYS force quit as well to ensure the app terminates
        if self.debug:
            if self.debug:
                print("🔄 Force quitting application")

        # Get the QApplication instance
        app = QApplication.instance()
        if app:
            # Try graceful quit first
            app.quit()
            # Process any pending events
            app.processEvents()

        # Force exit if the app is still running
        import sys
        import os
        if self.debug:
            if self.debug:
                print("🔄 Force exit with sys.exit and os._exit")
        try:
            sys.exit(0)
        except:
            # Ultimate fallback - force process termination
            os._exit(0)
    
    def set_app_quit_callback(self, callback):
        """Set callback to properly quit the main application."""
        self.app_quit_callback = callback
    
    @pyqtSlot()
    def _on_speech_started_main_thread(self):
        """Handle speech start on main thread (called via QMetaObject.invokeMethod)."""
        if self.debug:
            print("🔊 QtChatBubble: Speech started - updating status on main thread")
        try:
            if hasattr(self, "tts_toggle") and self.tts_toggle:
                self.tts_toggle.set_tts_state("speaking")
        except Exception:
            pass
        # In full voice mode, accurately reflect that we are speaking (not listening).
        if self._is_full_voice_running():
            try:
                if hasattr(self, "full_voice_toggle") and self.full_voice_toggle:
                    self.full_voice_toggle.set_listening_state("idle")
            except Exception:
                pass
            try:
                self.update_status("SPEAKING")
            except Exception:
                pass
        if self.status_callback:
            self.status_callback("speaking")
    
    @pyqtSlot()
    def _on_speech_ended_main_thread(self):
        """Handle speech end on main thread (called via QMetaObject.invokeMethod)."""
        if self.debug:
            print("🔊 QtChatBubble: Speech ended - handling completion on main thread")
        
        # Update toggle state when speech completes
        self._update_tts_toggle_state()
        try:
            if hasattr(self, "tts_toggle") and self.tts_toggle:
                self.tts_toggle.set_tts_state("idle")
        except Exception:
            pass
        
        # Call response callback now that TTS is done
        if self.response_callback and hasattr(self, '_pending_response'):
            if self.debug:
                print(f"🔄 QtChatBubble: TTS completed, calling response callback...")
            self.response_callback(self._pending_response)
            delattr(self, '_pending_response')
        
        # Notify main app that speaking is done (back to ready)
        if self.status_callback:
            if self.debug:
                print("🔊 QtChatBubble: Speech ended, setting ready status")
            self.status_callback("ready")

        # Voice loop: allow next transcription after speaking ends.
        if self._is_full_voice_running():
            self._voice_busy = False
            try:
                try:
                    if hasattr(self, "full_voice_toggle") and self.full_voice_toggle:
                        self.full_voice_toggle.set_listening_state("listening")
                except Exception:
                    pass
                self.update_status("LISTENING")
            except Exception:
                pass
    
    @pyqtSlot()
    def _execute_tts_completion_callbacks(self):
        """Execute TTS completion callbacks on the main thread."""
        if hasattr(self, '_tts_completion_callback') and self._tts_completion_callback:
            if self.debug:
                print("🔊 QtChatBubble: Executing TTS completion callbacks on main thread...")
            
            # Execute the stored callback
            try:
                self._tts_completion_callback()
            except Exception as e:
                if self.debug:
                    print(f"❌ Error executing TTS completion callback: {e}")
            finally:
                # Clear the callback
                self._tts_completion_callback = None
    
    
    # NOTE: The message input row now owns sizing of the square action buttons via `_MessageInputRow`.

    def closeEvent(self, event):
        """Handle close event."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        
        # Clean up voice manager
        if self.voice_manager:
            try:
                self.voice_manager.cleanup()
            except Exception as e:
                if self.debug:
                    if self.debug:
                        print(f"❌ Error cleaning up voice manager: {e}")
        
        event.accept()


class QtBubbleManager:
    """Manager for Qt chat bubble."""
    
    def __init__(self, llm_manager, config=None, debug=False, listening_mode="wait"):
        self.llm_manager = llm_manager
        self.config = config
        self.debug = debug
        self.listening_mode = listening_mode
        
        self.app = None
        self.bubble = None
        self.response_callback = None
        self.error_callback = None
        self.status_callback = None
        
        if not QT_AVAILABLE:
            raise RuntimeError("No Qt library available. Install PyQt5, PySide2, or PyQt6")
        
        if self.debug:
            if self.debug:
                print(f"✅ QtBubbleManager initialized with {QT_AVAILABLE}")

    def _prepare_bubble(self):
        """Pre-initialize the bubble for instant display later."""
        if not self.app:
            # Always use existing QApplication instance (never create a new one)
            self.app = QApplication.instance()
            if not self.app:
                raise RuntimeError("No QApplication instance found. This should be created by the main app first.")

        if not self.bubble:
            if self.debug:
                if self.debug:
                    print("🔄 Pre-creating QtChatBubble...")

            # Create the bubble but don't show it yet
            self.bubble = QtChatBubble(self.llm_manager, self.config, self.debug, self.listening_mode)

            # Set up callbacks
            if self.response_callback:
                self.bubble.set_response_callback(self.response_callback)
            if self.error_callback:
                self.bubble.set_error_callback(self.error_callback)
            if self.status_callback:
                self.bubble.set_status_callback(self.status_callback)

            if self.debug:
                if self.debug:
                    print("✅ QtChatBubble pre-created and ready")

    def show(self):
        """Show the chat bubble (instantly if pre-initialized)."""
        # Ensure bubble is prepared (will be instant if already pre-initialized)
        if not self.bubble:
            self._prepare_bubble()

        # Set app quit callback if not already set during preparation
        if hasattr(self, 'app_quit_callback') and self.app_quit_callback:
            if hasattr(self.bubble, 'set_app_quit_callback'):
                self.bubble.set_app_quit_callback(self.app_quit_callback)
        
        self.bubble.show()
        self.bubble.raise_()
        self.bubble.activateWindow()
        
        if self.debug:
            if self.debug:
                print("💬 Qt chat bubble shown")
    
    def hide(self):
        """Hide the chat bubble."""
        if self.bubble:
            self.bubble.hide()
            
            if self.debug:
                if self.debug:
                    print("💬 Qt chat bubble hidden")
    
    def destroy(self):
        """Destroy the chat bubble."""
        if self.bubble:
            self.bubble.close()
            self.bubble = None
            
            if self.debug:
                if self.debug:
                    print("💬 Qt chat bubble destroyed")
    
    def set_response_callback(self, callback):
        """Set response callback."""
        self.response_callback = callback
        if self.bubble:
            self.bubble.set_response_callback(callback)
    
    def set_error_callback(self, callback):
        """Set error callback."""
        self.error_callback = callback
        if self.bubble:
            self.bubble.set_error_callback(callback)
    
    def set_status_callback(self, callback):
        """Set status callback."""
        self.status_callback = callback
        if self.bubble:
            self.bubble.set_status_callback(callback)
    
    def set_app_quit_callback(self, callback):
        """Set app quit callback."""
        self.app_quit_callback = callback
        if self.bubble:
            self.bubble.set_app_quit_callback(callback)
