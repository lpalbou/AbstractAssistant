"""
Qt-based chat bubble for AbstractAssistant.

A simple, modern chat bubble using PyQt5/PySide2 that opens near the system tray.
"""

import sys
import threading
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List, Dict

# Import VoiceLLM-compatible TTS manager
try:
    from ..core.tts_manager import VoiceManager
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    VoiceManager = None

try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
        QTextEdit, QPushButton, QComboBox, QLabel, QFrame,
        QFileDialog, QMessageBox, QDialog, QScrollArea, QTextBrowser
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
    from PyQt5.QtGui import QFont, QPalette, QColor, QPainter, QPen, QBrush
    from PyQt5.QtCore import QPoint
    QT_AVAILABLE = "PyQt5"
except ImportError:
    try:
        from PySide2.QtWidgets import (
            QApplication, QWidget, QVBoxLayout, QHBoxLayout,
            QTextEdit, QPushButton, QComboBox, QLabel, QFrame,
            QFileDialog, QMessageBox, QDialog, QScrollArea, QTextBrowser
        )
        from PySide2.QtCore import Qt, QTimer, Signal as pyqtSignal, QThread, Slot as pyqtSlot
        from PySide2.QtGui import QFont, QPalette, QColor, QPainter, QPen, QBrush
        from PySide2.QtCore import QPoint
        QT_AVAILABLE = "PySide2"
    except ImportError:
        try:
            from PyQt6.QtWidgets import (
                QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                QTextEdit, QPushButton, QComboBox, QLabel, QFrame,
                QFileDialog, QMessageBox, QDialog, QScrollArea, QTextBrowser
            )
            from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
            from PyQt6.QtGui import QFont, QPalette, QColor, QPainter, QPen, QBrush
            from PyQt6.QtCore import QPoint
            QT_AVAILABLE = "PyQt6"
        except ImportError:
            QT_AVAILABLE = None


class TTSToggle(QWidget):
    """Custom TTS toggle switch with elongated cone design."""
    
    toggled = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(33, 24)  # Reduced width by 1.8x (60/1.8 ≈ 33)
        self.setToolTip("Toggle Text-to-Speech")
        self._enabled = False
        self._hover = False
        
    def is_enabled(self) -> bool:
        """Check if TTS is enabled."""
        return self._enabled
    
    def set_enabled(self, enabled: bool):
        """Set TTS enabled state."""
        if self._enabled != enabled:
            self._enabled = enabled
            self.update()
            self.toggled.emit(enabled)
    
    def mousePressEvent(self, event):
        """Handle mouse press to toggle state."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_enabled(not self._enabled)
        super().mousePressEvent(event)
    
    def enterEvent(self, event):
        """Handle mouse enter for hover effect."""
        self._hover = True
        self.update()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leave to remove hover effect."""
        self._hover = False
        self.update()
        super().leaveEvent(event)
    
    def paintEvent(self, event):
        """Custom paint event for the toggle switch."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Colors
        bg_color = QColor("#404040") if not self._enabled else QColor("#00aa00")
        if self._hover:
            bg_color = bg_color.lighter(120)
        
        track_color = QColor("#2a2a2a")
        thumb_color = QColor("#ffffff")
        
        # Draw track (elongated rounded rectangle)
        track_rect = self.rect().adjusted(2, 4, -2, -4)
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(track_rect, 8, 8)
        
        # Draw background fill
        fill_rect = track_rect.adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(fill_rect, 7, 7)
        
        # Draw thumb (circle)
        thumb_radius = 6
        if self._enabled:
            thumb_x = self.width() - thumb_radius - 6
        else:
            thumb_x = thumb_radius + 4
        
        thumb_y = self.height() // 2
        
        # Thumb shadow
        shadow_color = QColor(0, 0, 0, 50)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow_color))
        painter.drawEllipse(thumb_x - thumb_radius + 1, thumb_y - thumb_radius + 1, 
                          thumb_radius * 2, thumb_radius * 2)
        
        # Thumb
        painter.setBrush(QBrush(thumb_color))
        painter.drawEllipse(thumb_x - thumb_radius, thumb_y - thumb_radius, 
                          thumb_radius * 2, thumb_radius * 2)
        
        # Draw speaker icon on thumb
        if self._enabled:
            # Draw simple speaker icon
            icon_color = QColor("#00aa00")
            painter.setPen(QPen(icon_color, 2))
            
            # Speaker cone
            cone_points = [
                (thumb_x - 3, thumb_y - 2),
                (thumb_x - 1, thumb_y - 3),
                (thumb_x + 1, thumb_y - 3),
                (thumb_x + 1, thumb_y + 3),
                (thumb_x - 1, thumb_y + 3),
                (thumb_x - 3, thumb_y + 2)
            ]
            
            painter.drawPolyline([QPoint(x, y) for x, y in cone_points])
            
            # Sound waves
            painter.setPen(QPen(icon_color, 1))
            painter.drawArc(thumb_x + 2, thumb_y - 4, 6, 8, 0, 180 * 16)
            painter.drawArc(thumb_x + 3, thumb_y - 2, 4, 4, 0, 180 * 16)


class HistoryDialog(QDialog):
    """Dialog to display message history."""
    
    def __init__(self, message_history: List[Dict], parent=None):
        super().__init__(parent)
        self.message_history = message_history
        self.setup_ui()
        self.setup_styling()
    
    def setup_ui(self):
        """Set up iPhone Messages-style history dialog UI."""
        self.setWindowTitle("Messages")
        self.setModal(True)
        self.resize(512, 600)  # Decreased by 10% (680 * 0.9 = 612)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header bar - iPhone style
        header_bar = QFrame()
        header_bar.setFixedHeight(44)  # iOS standard header height
        header_bar.setStyleSheet("""
            QFrame {
                background: rgba(28, 28, 30, 0.95);
                border: none;
                border-bottom: 0.5px solid rgba(84, 84, 88, 0.6);
            }
        """)
        
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(16, 0, 16, 0)
        
        # Back/Close button (iOS style)
        close_button = QPushButton("Done")
        close_button.setFixedHeight(32)
        close_button.clicked.connect(self.accept)
        close_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 17px;
                font-weight: 400;
                color: #007AFF;
                font-family: -apple-system, system-ui, sans-serif;
                padding: 0px 8px;
            }
            QPushButton:hover {
                color: #0051D5;
            }
            QPushButton:pressed {
                color: #004CCC;
            }
        """)
        header_layout.addWidget(close_button)
        
        header_layout.addStretch()
        
        # Title
        header_label = QLabel("Messages")
        header_label.setStyleSheet("""
            QLabel {
                font-size: 17px;
                font-weight: 600;
                color: #ffffff;
                font-family: -apple-system, system-ui, sans-serif;
            }
        """)
        header_layout.addWidget(header_label)
        
        header_layout.addStretch()
        
        # Message count (subtle)
        count_label = QLabel(f"{len(self.message_history)}")
        count_label.setStyleSheet("""
            QLabel {
                font-size: 15px;
                font-weight: 400;
                color: rgba(255, 255, 255, 0.6);
                font-family: -apple-system, system-ui, sans-serif;
            }
        """)
        header_layout.addWidget(count_label)
        
        layout.addWidget(header_bar)
        
        # Messages area - iPhone style
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # Hide scrollbar like iOS
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background: #000000;
                border: none;
            }
        """)
        
        # Content widget
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 12, 0, 12)
        content_layout.setSpacing(2)  # Very tight spacing like iPhone Messages
        
        # Add messages to content
        for i, msg in enumerate(self.message_history):
            message_frame = self._create_message_frame(msg, i)
            content_layout.addWidget(message_frame)
        
        content_layout.addStretch()
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.setLayout(layout)
    
    def _create_message_frame(self, msg: Dict, index: int) -> QFrame:
        """Create iPhone Messages-style message bubble."""
        container = QFrame()
        container.setStyleSheet("QFrame { background: transparent; border: none; }")
        
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(16, 1, 16, 1)  # iPhone-style margins
        container_layout.setSpacing(0)
        
        is_user = msg['type'] == 'user'
        
        if is_user:
            # User messages: right-aligned, blue bubble
            container_layout.addStretch()  # Push to right
            
            bubble = QFrame()
            bubble.setStyleSheet("""
                QFrame {
                    background: #007AFF;
                    border: none;
                    border-radius: 8px;
                    min-width: 300px;
                    max-width: 532px;
                }
            """)
            
            bubble_layout = QVBoxLayout(bubble)
            bubble_layout.setContentsMargins(12, 8, 12, 8)
            bubble_layout.setSpacing(2)
            
        else:
            # AI messages: left-aligned, grey bubble (much wider for fewer lines)
            bubble = QFrame()
            bubble.setStyleSheet("""
                QFrame {
                    background: #1C1C1E;
                    border: none;
                    border-radius: 8px;
                    min-width: 450px;
                    max-width: 550px;
                }
            """)
            
            bubble_layout = QVBoxLayout(bubble)
            bubble_layout.setContentsMargins(12, 8, 12, 8)
            bubble_layout.setSpacing(2)
        
        # Message content
        if is_user:
            # User messages: simple text label
            content_widget = QLabel(msg['content'])
            content_widget.setWordWrap(True)
            content_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            content_widget.setStyleSheet("""
                QLabel {
                    background: transparent;
                    border: none;
                    font-size: 16px;
                    font-weight: 400;
                    color: #ffffff;
                    font-family: -apple-system, system-ui, sans-serif;
                    line-height: 1.3;
                    padding: 0px;
                }
            """)
        else:
            # AI messages: markdown-enabled text browser
            content_widget = QTextBrowser()
            content_widget.setMarkdown(msg['content'])
            content_widget.setOpenExternalLinks(False)
            content_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            content_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            content_widget.setFrameStyle(QFrame.Shape.NoFrame)
            content_widget.setStyleSheet("""
                QTextBrowser {
                    background: transparent;
                    border: none;
                    font-size: 16px;
                    font-weight: 400;
                    color: #ffffff;
                    font-family: -apple-system, system-ui, sans-serif;
                    line-height: 1.3;
                    padding: 0px;
                }
                QTextBrowser h1, QTextBrowser h2, QTextBrowser h3 {
                    color: #ffffff;
                    font-weight: 600;
                }
                QTextBrowser code {
                    background: rgba(255, 255, 255, 0.1);
                    padding: 2px 4px;
                    border-radius: 3px;
                    font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace;
                }
                QTextBrowser pre {
                    background: rgba(255, 255, 255, 0.05);
                    padding: 8px;
                    border-radius: 6px;
                    border-left: 3px solid #007AFF;
                }
            """)
            
            # Auto-resize to content
            content_widget.document().setTextWidth(content_widget.width())
            content_widget.setFixedHeight(int(content_widget.document().size().height()))
        
        bubble_layout.addWidget(content_widget)
        
        if is_user:
            container_layout.addWidget(bubble)
        else:
            container_layout.addWidget(bubble)
            container_layout.addStretch()  # Push to left
        
        # Timestamp below bubble (iPhone style)
        timestamp_container = QFrame()
        timestamp_container.setStyleSheet("QFrame { background: transparent; border: none; }")
        timestamp_layout = QHBoxLayout(timestamp_container)
        timestamp_layout.setContentsMargins(16, 0, 16, 4)
        
        # Format timestamp
        dt = datetime.fromisoformat(msg['timestamp'])
        today = datetime.now().date()
        msg_date = dt.date()
        
        if msg_date == today:
            time_str = dt.strftime("%I:%M %p").lower().lstrip('0')  # "2:34 pm"
        elif (today - msg_date).days == 1:
            time_str = f"Yesterday {dt.strftime('%I:%M %p').lower().lstrip('0')}"
        else:
            time_str = dt.strftime("%b %d, %I:%M %p").lower().replace(' 0', ' ').lstrip('0')
        
        timestamp_label = QLabel(time_str)
        timestamp_label.setStyleSheet("""
            QLabel {
                background: transparent;
                border: none;
                font-size: 13px;
                font-weight: 400;
                color: rgba(255, 255, 255, 0.6);
                font-family: -apple-system, system-ui, sans-serif;
                padding: 0px;
            }
        """)
        
        if is_user:
            timestamp_layout.addStretch()
            timestamp_layout.addWidget(timestamp_label)
        else:
            timestamp_layout.addWidget(timestamp_label)
            timestamp_layout.addStretch()
        
        # Main container for bubble + timestamp
        main_container = QFrame()
        main_container.setStyleSheet("QFrame { background: transparent; border: none; }")
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)
        
        main_layout.addWidget(container)
        
        # Only show timestamp for every few messages or different times (like iPhone)
        prev_msg = self.message_history[index - 1] if index > 0 else None
        show_timestamp = (index == 0 or 
                         prev_msg is None or 
                         index % 5 == 0 or  # Every 5th message
                         abs(datetime.fromisoformat(msg['timestamp']) - 
                             datetime.fromisoformat(prev_msg['timestamp'])).total_seconds() > 300)  # 5+ minutes apart
        
        if show_timestamp:
            main_layout.addWidget(timestamp_container)
        
        return main_container
    
    def setup_styling(self):
        """Set up iPhone Messages-style dialog styling."""
        self.setStyleSheet("""
            QDialog {
                background: #000000;
                color: #ffffff;
                border: none;
                border-radius: 12px;
            }
            QScrollArea {
                background: #000000;
                border: none;
            }
            /* Hide scrollbars completely like iOS */
            QScrollBar:vertical {
                width: 0px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: transparent;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: transparent;
            }
        """)


class LLMWorker(QThread):
    """Worker thread for LLM processing."""
    
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, llm_manager, message, provider, model):
        super().__init__()
        self.llm_manager = llm_manager
        self.message = message
        self.provider = provider
        self.model = model
    
    def run(self):
        """Run LLM processing in background."""
        try:
            # Use LLMManager session for context persistence
            response = self.llm_manager.generate_response(self.message, self.provider, self.model)
            
            # Response is already a string from LLMManager
            response_text = str(response)
            
            self.response_ready.emit(response_text)
            
        except Exception as e:
            print(f"❌ LLM Error: {e}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))


class QtChatBubble(QWidget):
    """Modern Qt-based chat bubble."""
    
    def __init__(self, llm_manager, config=None, debug=False):
        super().__init__()
        self.llm_manager = llm_manager
        self.config = config
        self.debug = debug
        
        # State - default to LMStudio with qwen/qwen3-next-80b
        self.current_provider = 'lmstudio'  # Default to LMStudio
        self.current_model = 'qwen/qwen3-next-80b'  # Default to qwen/qwen3-next-80b
        self.token_count = 0
        self.max_tokens = 128000
        
        # Message history for session management
        self.message_history: List[Dict] = []
        
        # TTS functionality (VoiceLLM-compatible)
        self.voice_manager = None
        self.tts_enabled = False
        if TTS_AVAILABLE:
            try:
                self.voice_manager = VoiceManager(debug_mode=debug)
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
        
        if self.debug:
            print("✅ QtChatBubble initialized")
    
    def setup_ui(self):
        """Set up the modern user interface with SOTA UX practices."""
        self.setWindowTitle("AbstractAssistant")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        # Set optimal size for modern chat interface - wider and shorter
        self.setFixedSize(540, 196)  # Increased by 40px (156 + 40 = 196)
        self.position_near_tray()
        
        # Main layout with minimal spacing
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 4, 8, 8)  # Strict minimum margins
        layout.setSpacing(4)  # Minimal spacing
        
        # Simple header like Cursor
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(8)
        
        # Close button (minimal)
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(18, 18)
        self.close_button.clicked.connect(self.close_app)
        self.close_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                border: none;
                border-radius: 9px;
                font-size: 11px;
                font-weight: 600;
                color: rgba(255, 255, 255, 0.9);
                font-family: -apple-system, system-ui, sans-serif;
            }
            QPushButton:hover {
                background: rgba(255, 60, 60, 0.8);
                color: #ffffff;
            }
        """)
        header_layout.addWidget(self.close_button)
        
        # Session buttons (minimal, rounded)
        session_buttons = [
            ("Clear", self.clear_session),
            ("Load", self.load_session), 
            ("Save", self.save_session),
            ("History", self.show_history)
        ]
        
        for text, handler in session_buttons:
            btn = QPushButton(text)
            btn.setFixedHeight(22)
            btn.clicked.connect(handler)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.06);
                    border: none;
                    border-radius: 11px;
                    font-size: 10px;
                    color: rgba(255, 255, 255, 0.7);
                    font-family: -apple-system, system-ui, sans-serif;
                    padding: 0 10px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.12);
                    color: rgba(255, 255, 255, 0.9);
                }
            """)
            header_layout.addWidget(btn)
        
        # TTS toggle (if available)
        if self.voice_manager and self.voice_manager.is_available():
            self.tts_toggle = TTSToggle()
            self.tts_toggle.toggled.connect(self.on_tts_toggled)
            header_layout.addWidget(self.tts_toggle)
        
        header_layout.addStretch()
        
        # Status (Cursor-style, enlarged to show full text)
        self.status_label = QLabel("READY")
        self.status_label.setFixedSize(80, 24)  # Increased from 50x22 to 80x24
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                background: #22c55e;
                border: none;
                border-radius: 12px;
                font-size: 10px;
                font-weight: 600;
                color: #ffffff;
                font-family: -apple-system, system-ui, sans-serif;
            }
        """)
        header_layout.addWidget(self.status_label)
        
        layout.addLayout(header_layout)
        
        # Input section with modern card design
        input_container = QFrame()
        input_container.setStyleSheet("""
            QFrame {
                background: #1e1e1e;
                border: 1px solid #404040;
                border-radius: 8px;
                padding: 4px;
            }
        """)
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(4, 4, 4, 4)
        input_layout.setSpacing(4)
        
        # Input field with inline send button
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        
        # Text input - larger, primary focus
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Ask me anything... (Shift+Enter to send)")
        self.input_text.setMaximumHeight(100)  # Increased to better use available space
        self.input_text.setMinimumHeight(70)   # Increased to better use available space
        input_row.addWidget(self.input_text)
        
        # Send button - primary action with special styling
        self.send_button = QPushButton("→")
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setFixedSize(40, 40)
        self.send_button.setStyleSheet("""
            QPushButton {
                background: #0066cc;
                border: 1px solid #0080ff;
                border-radius: 20px;
                font-size: 16px;
                font-weight: bold;
                color: white;
                text-align: center;
                padding: 0px;
            }
            
            QPushButton:hover {
                background: #0080ff;
                border: 1px solid #0099ff;
            }
            
            QPushButton:pressed {
                background: #0052a3;
            }
            
            QPushButton:disabled {
                background: #404040;
                color: #666666;
                border: 1px solid #333333;
            }
        """)
        input_row.addWidget(self.send_button)
        
        input_layout.addLayout(input_row)
        layout.addWidget(input_container)
        
        # Bottom controls - Cursor style (minimal, clean)
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(12, 6, 12, 8)
        controls_layout.setSpacing(8)
        
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
                padding: 0 12px;
                font-size: 11px;
                color: rgba(255, 255, 255, 0.9);
                font-family: -apple-system, system-ui, sans-serif;
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
        self.model_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 14px;
                padding: 0 12px;
                font-size: 11px;
                color: rgba(255, 255, 255, 0.9);
                font-family: -apple-system, system-ui, sans-serif;
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
        self.token_label.setFixedHeight(28)
        self.token_label.setMinimumWidth(60)
        self.token_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.token_label.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 14px;
                font-size: 10px;
                color: rgba(255, 255, 255, 0.6);
                font-family: -apple-system, system-ui, sans-serif;
            }
        """)
        controls_layout.addWidget(self.token_label)
        
        # Add a simple chat display area between header and input
        # No chat display in main bubble - messages only appear in History dialog
        
        layout.addLayout(controls_layout)
        
        self.setLayout(layout)
        
        # Focus on input
        self.input_text.setFocus()
        
        # Enter key handling
        self.input_text.keyPressEvent = self.handle_key_press
    
    def setup_styling(self):
        """Set up Cursor-style clean theme."""
        self.setStyleSheet("""
            /* Main Window - Cursor Style */
            QWidget {
                background: #1e1e1e;
                border: none;
                border-radius: 12px;
                color: #ffffff;
            }
            
            /* Input Field - Modern Grey Design */
            QTextEdit {
                background: #1e1e1e;
                border: 1px solid #404040;
                border-radius: 8px;
                padding: 12px 16px;
                font-size: 14px;
                font-weight: 400;
                color: #ffffff;
                font-family: system-ui, -apple-system, sans-serif;
                selection-background-color: #0066cc;
                line-height: 1.4;
            }
            
            QTextEdit:focus {
                border: 1px solid #0066cc;
                background: #252525;
            }
            
            QTextEdit::placeholder {
                color: rgba(255, 255, 255, 0.6);
            }
            
            /* Buttons - Grey Theme */
            QPushButton {
                background: #404040;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 500;
                color: #ffffff;
                font-family: system-ui, -apple-system, sans-serif;
            }
            
            QPushButton:hover {
                background: #505050;
                border: 1px solid #0066cc;
            }
            
            QPushButton:pressed {
                background: #353535;
            }
            
            QPushButton:disabled {
                background: #2a2a2a;
                color: #666666;
                border: 1px solid #333333;
            }
            
            /* Dropdown Menus - Grey Theme */
                QComboBox {
                    background: #1e1e1e;
                    border: 1px solid #404040;
                    border-radius: 6px;
                    padding: 6px 10px;
                    min-width: 80px;
                    font-size: 12px;
                    font-weight: 400;
                    color: #ffffff;
                    font-family: system-ui, -apple-system, sans-serif;
                    letter-spacing: 0.01em;
                }
            
            QComboBox:hover {
                border: 1px solid #0066cc;
                background: #252525;
            }
            
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid rgba(255, 255, 255, 0.7);
                width: 0px;
                height: 0px;
            }
            
                QComboBox QAbstractItemView {
                    background: #1a202c;
                    border: 1px solid #4a5568;
                    border-radius: 8px;
                    selection-background-color: #4299e1;
                    color: #e2e8f0;
                    padding: 4px;
                    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
                }
                
                QComboBox QAbstractItemView::item {
                    height: 36px;
                    padding: 8px 12px;
                    border: none;
                    font-size: 12px;
                    font-weight: 400;  /* Changed from 500 to 400 (normal weight) */
                    color: #e2e8f0;
                    border-radius: 4px;
                    margin: 2px;
                }
                
                QComboBox QAbstractItemView::item:selected {
                    background: #4299e1;
                    color: #ffffff;
                }
                
                QComboBox QAbstractItemView::item:hover {
                    background: #374151;
                }
            
            QComboBox QAbstractItemView::item:selected {
                background: #4299e1;
            }
            
            /* Labels - Clean Typography */
            QLabel {
                color: rgba(255, 255, 255, 0.8);
                font-size: 12px;
                font-weight: 500;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                letter-spacing: 0.3px;
            }
            
            /* Status and Token Labels - Accent Colors */
            QLabel#status_ready {
                background: rgba(166, 227, 161, 0.15);
                border: 1px solid rgba(166, 227, 161, 0.3);
                border-radius: 12px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #a6e3a1;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
            }
            
            QLabel#status_generating {
                background: rgba(250, 179, 135, 0.15);
                border: 1px solid rgba(250, 179, 135, 0.3);
                border-radius: 12px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #fab387;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
            }
            
            QLabel#status_error {
                background: rgba(243, 139, 168, 0.15);
                border: 1px solid rgba(243, 139, 168, 0.3);
                border-radius: 12px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #f38ba8;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
            }
            
            QLabel#token_label {
                background: #2d3748;
                border: 1px solid #4a5568;
                border-radius: 8px;
                padding: 10px 12px;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
                font-size: 11px;
                font-weight: 500;
                color: #cbd5e0;
                text-align: center;
                letter-spacing: 0.025em;
            }
            
            /* Frames - Invisible Containers */
            QFrame {
                border: none;
                background: transparent;
            }
            
            /* Separator Lines */
            QLabel#separator {
                color: rgba(255, 255, 255, 0.3);
                font-size: 14px;
                font-weight: 300;
            }
        """)
    
    def position_near_tray(self):
        """Position the bubble near the system tray."""
        # Get screen geometry
        screen = QApplication.primaryScreen().geometry()
        
        # Position closer to the tray area but not at the very edge
        # Leave more space from the right edge for better visibility
        x = screen.width() - self.width() - 150  # More space from right edge
        y = 50
        
        self.move(x, y)
        
        if self.debug:
            print(f"Positioned bubble at ({x}, {y})")
    
    def load_providers(self):
        """Load available providers using AbstractCore's provider discovery system."""
        try:
            # Use AbstractCore's provider discovery system
            from abstractcore.providers import list_available_providers
            
            # Get list of available provider names
            available_providers = list_available_providers()
            
            if self.debug:
                print(f"🔍 Provider discovery found {len(available_providers)} available providers: {available_providers}")
            
            # Clear and populate provider combo
            self.provider_combo.clear()
            
            # Provider display names mapping
            provider_display_names = {
                'openai': 'OpenAI',
                'anthropic': 'Anthropic', 
                'ollama': 'Ollama',
                'lmstudio': 'LMStudio',
                'mlx': 'MLX',
                'huggingface': 'HuggingFace',
                'mock': 'Mock'
            }
            
            # Add each available provider to dropdown (excluding mock)
            for provider_name in available_providers:
                # Explicitly exclude mock provider
                if provider_name == 'mock':
                    if self.debug:
                        print(f"    ⏭️  Skipping mock provider")
                    continue
                    
                display_name = provider_display_names.get(provider_name, provider_name.title())
                self.provider_combo.addItem(display_name, provider_name)
                
                if self.debug:
                    print(f"    ✅ Added to dropdown: {display_name} ({provider_name})")
            
            if self.debug:
                print(f"🔍 Total providers added to dropdown: {len(available_providers)}")
            
            # Set current provider - prefer lmstudio if available, otherwise use first
            provider_found = False
            preferred_provider = 'lmstudio'  # Prefer lmstudio as default
            
            # First try to find preferred provider
            for i in range(self.provider_combo.count()):
                if self.provider_combo.itemData(i) == preferred_provider:
                    self.provider_combo.setCurrentIndex(i)
                    self.current_provider = preferred_provider
                    provider_found = True
                    if self.debug:
                        print(f"✅ Using preferred provider: {preferred_provider}")
                    break
            
            # If preferred not found, use the first available one
            if not provider_found and self.provider_combo.count() > 0:
                self.current_provider = self.provider_combo.itemData(0)
                self.provider_combo.setCurrentIndex(0)
                if self.debug:
                    print(f"🔄 Preferred provider not found, using first available: {self.current_provider}")
            
            if self.debug:
                print(f"🔍 Final selected provider: {self.current_provider}")
            
            # Load models for current provider
            self.update_models()
            
        except Exception as e:
            if self.debug:
                print(f"❌ Error loading providers: {e}")
                import traceback
                traceback.print_exc()
            
            # Fallback: add current provider manually if discovery fails
            if self.provider_combo.count() == 0:
                self.provider_combo.addItem("LMStudio (Local)", "lmstudio")
                self.current_provider = "lmstudio"
                if self.debug:
                    print("🔄 Using fallback provider list")
    
    def update_models(self):
        """Update model dropdown using provider.list_available_models() method."""
        try:
            # Create provider instance and get available models using list_available_models()
            from abstractcore import create_llm
            
            # Create provider instance with a minimal/default model to get the provider object
            provider_default_models = {
                'openai': 'gpt-4o-mini',
                'anthropic': 'claude-3-5-haiku-20241022', 
                'ollama': 'qwen3:4b-instruct-2507-q4_K_M',
                'lmstudio': 'qwen/qwen3-next-80b',
                'mlx': 'mlx-community/Qwen3-4B-4bit',
                'huggingface': 'microsoft/DialoGPT-medium'
            }
            
            default_model = provider_default_models.get(self.current_provider, 'default-model')
            provider_llm = create_llm(self.current_provider, model=default_model)
            models = provider_llm.list_available_models()
            
            if self.debug:
                print(f"📋 Loaded {len(models)} models for {self.current_provider}")
            
            self.model_combo.clear()
            for model in models:
                # Create display name - keep the full model name but make it readable
                display_name = model.split('/')[-1] if '/' in model else model
                # Limit display name length for better UI
                if len(display_name) > 25:
                    display_name = display_name[:22] + "..."
                
                self.model_combo.addItem(display_name, model)
            
            # Set current model - prefer qwen/qwen3-next-80b if available
            model_found = False
            preferred_model = 'qwen/qwen3-next-80b'
            
            # First try to find preferred model
            for i in range(self.model_combo.count()):
                if self.model_combo.itemData(i) == preferred_model:
                    self.model_combo.setCurrentIndex(i)
                    self.current_model = preferred_model
                    model_found = True
                    if self.debug:
                        print(f"✅ Using preferred model: {preferred_model}")
                    break
            
            # If preferred not found, try current model
            if not model_found and self.current_model:
                for i in range(self.model_combo.count()):
                    if self.model_combo.itemData(i) == self.current_model:
                        self.model_combo.setCurrentIndex(i)
                        model_found = True
                        if self.debug:
                            print(f"✅ Using current model: {self.current_model}")
                        break
            
            # If neither found, use the first available one
            if not model_found and self.model_combo.count() > 0:
                self.current_model = self.model_combo.itemData(0)
                self.model_combo.setCurrentIndex(0)
            self.update_token_limits()
            
        except Exception as e:
            if self.debug:
                print(f"❌ Error loading models for '{self.current_provider}': {e}")
            
            # Fallback: use the registry method if provider instantiation fails
            try:
                from abstractcore.providers import get_available_models_for_provider
                models = get_available_models_for_provider(self.current_provider)
                
                if self.debug:
                    print(f"📋 Fallback: Loaded {len(models)} models from registry")
                
                self.model_combo.clear()
                for model in models:
                    display_name = model.split('/')[-1] if '/' in model else model
                    if len(display_name) > 25:
                        display_name = display_name[:22] + "..."
                    self.model_combo.addItem(display_name, model)
                
                if self.model_combo.count() > 0:
                    self.current_model = self.model_combo.itemData(0)
                    self.model_combo.setCurrentIndex(0)
                    
            except Exception as fallback_error:
                if self.debug:
                    print(f"❌ Fallback also failed: {fallback_error}")
                
                # Final fallback: add provider-specific default models
                self.model_combo.clear()
                fallback_models = {
                    'lmstudio': ['qwen/qwen3-next-80b', 'qwen/qwen3-coder-30b', 'qwen/qwen3-4b-2507'],
                    'ollama': ['qwen3:4b-instruct', 'llama3.2:3b', 'mistral:7b'],
                    'openai': ['gpt-4o-mini', 'gpt-4o', 'gpt-3.5-turbo'],
                    'anthropic': ['claude-3-5-haiku-20241022', 'claude-3-5-sonnet-20241022'],
                    'mlx': ['mlx-community/Qwen3-4B-4bit', 'mlx-community/Qwen3-4B-Instruct-2507-4bit'],
                    'huggingface': ['microsoft/DialoGPT-medium', 'microsoft/DialoGPT-large']
                }
                
                provider_fallbacks = fallback_models.get(self.current_provider, ['default-model'])
                for model in provider_fallbacks:
                    display_name = model.split('/')[-1] if '/' in model else model
                    if len(display_name) > 25:
                        display_name = display_name[:22] + "..."
                    self.model_combo.addItem(display_name, model)
                
                if self.model_combo.count() > 0:
                    self.current_model = self.model_combo.itemData(0)
                    self.model_combo.setCurrentIndex(0)
                    if self.debug:
                        print(f"🔄 Using final fallback model: {self.current_model}")
    
    def update_token_limits(self):
        """Update token limits using AbstractCore's built-in detection."""
        # Get token limits from LLMManager (which uses AbstractCore's detection)
        if self.llm_manager and self.llm_manager.llm:
            self.max_tokens = self.llm_manager.llm.max_tokens
            
            if self.debug:
                print(f"📊 Token limits from AbstractCore: {self.max_tokens}")
        else:
            # Fallback if LLM not initialized
            self.max_tokens = 128000
            
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
            # Shift+Enter or Ctrl+Enter or Cmd+Enter should send message
            if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier or 
                event.modifiers() & Qt.KeyboardModifier.ControlModifier or 
                event.modifiers() & Qt.KeyboardModifier.MetaModifier):
                self.send_message()
                return
            # Plain Enter should add a new line (default behavior)
        
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
    

    def send_message(self):
        """Send message to LLM."""
        message = self.input_text.toPlainText().strip()
        if not message:
            return
        
        if self.debug:
            print(f"💬 Sending message: '{message[:50]}...' to {self.current_provider}/{self.current_model}")
        
        # 1. Clear input immediately
        self.input_text.clear()
        
        # 2. Add message to history only (not to chat display)
        self.message_history.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'user',
            'content': message,
            'provider': self.current_provider,
            'model': self.current_model
        })
        
        # 3. Update UI for sending state
        self.send_button.setEnabled(False)
        self.send_button.setText("⏳")
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
        
        print("🔄 QtChatBubble: UI updated, creating worker thread...")
        
        # 4. Start worker thread to send request
        self.worker = LLMWorker(self.llm_manager, message, self.current_provider, self.current_model)
        self.worker.response_ready.connect(self.on_response_ready)
        self.worker.error_occurred.connect(self.on_error_occurred)
        
        print("🔄 QtChatBubble: Starting worker thread...")
        self.worker.start()
        
        print("🔄 QtChatBubble: Worker thread started, hiding bubble...")
        # Hide bubble after sending (like the original design)
        QTimer.singleShot(500, self.hide)
    
    @pyqtSlot(str)
    def on_response_ready(self, response):
        """Handle LLM response."""
        print(f"✅ QtChatBubble: on_response_ready called with response: {response[:100]}...")
        
        self.send_button.setEnabled(True)
        self.send_button.setText("→")
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
        
        # Add AI response to message history
        self.message_history.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'assistant',
            'content': response,
            'provider': self.current_provider,
            'model': self.current_model
        })
        
        # Update token count (approximate)
        self.token_count += len(response.split()) * 1.3  # Rough estimate
        self.update_token_display()
        
        # Handle TTS if enabled (VoiceLLM integration)
        if self.tts_enabled and self.voice_manager and self.voice_manager.is_available():
            if self.debug:
                print("🔊 TTS enabled, speaking response...")
            
            # Don't show toast when TTS is enabled
            try:
                # Clean response for voice synthesis
                clean_response = self._clean_response_for_voice(response)
                
                # Speak the cleaned response using VoiceLLM-compatible interface
                self.voice_manager.speak(clean_response)
                
                # Wait for speech to complete in a separate thread
                def wait_for_speech():
                    while self.voice_manager.is_speaking():
                        time.sleep(0.1)
                    if self.debug:
                        print("🔊 TTS completed")
                
                speech_thread = threading.Thread(target=wait_for_speech, daemon=True)
                speech_thread.start()
                
            except Exception as e:
                if self.debug:
                    print(f"❌ TTS error: {e}")
                # Fallback to toast if TTS fails
                try:
                    from .toast_window import show_toast_notification
                    show_toast_notification(response, debug=self.debug)
                except:
                    pass
        else:
            # Show toast notification when TTS is disabled
            try:
                from .toast_window import show_toast_notification
                toast = show_toast_notification(response, debug=self.debug)
                
                if self.debug:
                    print(f"🍞 Toast notification created and shown")
            except Exception as e:
                if self.debug:
                    print(f"❌ Failed to show toast: {e}")
                # Fallback to console
                print(f"✅ AI Response: {response}")
        
        # Also call response callback if set
        if self.response_callback:
            print(f"🔄 QtChatBubble: Response callback exists, calling it...")
            self.response_callback(response)
    
    def on_tts_toggled(self, enabled: bool):
        """Handle TTS toggle state change."""
        self.tts_enabled = enabled
        if self.debug:
            print(f"🔊 TTS {'enabled' if enabled else 'disabled'}")
        
        # Stop any current speech when disabling
        if not enabled and self.voice_manager:
            try:
                self.voice_manager.stop()
            except Exception as e:
                if self.debug:
                    print(f"❌ Error stopping TTS: {e}")
        
        # Update LLM session with TTS-appropriate system prompt
        if self.llm_manager:
            try:
                self.llm_manager.create_new_session(tts_mode=enabled)
                if self.debug:
                    print(f"🔄 LLM session updated for {'TTS' if enabled else 'normal'} mode")
            except Exception as e:
                if self.debug:
                    print(f"❌ Error updating LLM session: {e}")
    
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
            print(f"🔊 Cleaned text for TTS: {text[:100]}{'...' if len(text) > 100 else ''}")
        
        return text
    
    @pyqtSlot(str)
    def on_error_occurred(self, error):
        """Handle LLM error."""
        self.send_button.setEnabled(True)
        self.send_button.setText("→")
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
            print(f"Error occurred: {error}")
        
        # Show error toast notification
        try:
            from .toast_window import show_toast_notification
            error_message = f"❌ Error: {error}"
            toast = show_toast_notification(error_message, debug=self.debug)
            
            if self.debug:
                print(f"🍞 Error toast notification shown")
        except Exception as e:
            if self.debug:
                print(f"❌ Failed to show error toast: {e}")
            # Fallback to console
            print(f"❌ AI Error: {error}")
        
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
    
    def clear_session(self):
        """Clear the current session."""
        reply = QMessageBox.question(
            self, 
            "Clear Session", 
            "Are you sure you want to clear the current session?\nThis will remove all messages and reset the token count.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if hasattr(self, 'chat_display'):
                self.chat_display.clear()
                self.chat_display.hide()
            
            self.message_history.clear()
            self.token_count = 0
            self.update_token_display()
            
            if self.debug:
                print("🧹 Session cleared")
    
    def load_session(self):
        """Load a session from a JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Session",
            str(Path.home() / "Documents"),
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                
                # Validate session data
                if not isinstance(session_data, dict) or 'messages' not in session_data:
                    raise ValueError("Invalid session file format")
                
                # Load the session
                self.message_history = session_data['messages']
                self.token_count = session_data.get('token_count', 0)
                
                # Update UI
                self.update_token_display()
                self._rebuild_chat_display()
                
                QMessageBox.information(
                    self,
                    "Session Loaded",
                    f"Successfully loaded session with {len(self.message_history)} messages."
                )
                
                if self.debug:
                    print(f"📂 Loaded session from {file_path}")
                    
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Load Error",
                    f"Failed to load session:\n{str(e)}"
                )
                if self.debug:
                    print(f"❌ Failed to load session: {e}")
    
    def save_session(self):
        """Save the current session to a JSON file."""
        if not self.message_history:
            QMessageBox.information(
                self,
                "No Messages",
                "No messages to save. Start a conversation first."
            )
            return
        
        # Generate default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"chat_session_{timestamp}.json"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session",
            str(Path.home() / "Documents" / default_filename),
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            try:
                session_data = {
                    'timestamp': datetime.now().isoformat(),
                    'provider': self.current_provider,
                    'model': self.current_model,
                    'token_count': self.token_count,
                    'messages': self.message_history
                }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, indent=2, ensure_ascii=False)
                
                QMessageBox.information(
                    self,
                    "Session Saved",
                    f"Session saved successfully to:\n{file_path}"
                )
                
                if self.debug:
                    print(f"💾 Saved session to {file_path}")
                    
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Save Error",
                    f"Failed to save session:\n{str(e)}"
                )
                if self.debug:
                    print(f"❌ Failed to save session: {e}")
    
    def show_history(self):
        """Show message history in a dedicated window."""
        if not self.message_history:
            QMessageBox.information(
                self,
                "No History",
                "No message history available. Start a conversation first."
            )
            return
        
        # Create history dialog
        history_dialog = HistoryDialog(self.message_history, self)
        history_dialog.exec()
    
    def close_app(self):
        """Close the entire application completely."""
        if self.debug:
            print("🔄 Close button clicked - shutting down application")
        
        # Stop TTS if running
        if hasattr(self, 'voice_manager') and self.voice_manager:
            self.voice_manager.cleanup()
        
        # Close the chat bubble
        self.hide()
        
        # Try to call the main app's quit method if available
        if hasattr(self, 'app_quit_callback') and self.app_quit_callback:
            if self.debug:
                print("🔄 Calling app quit callback")
            self.app_quit_callback()
        else:
            # Fallback: force quit the application
            if self.debug:
                print("🔄 No app callback, forcing quit")
            app = QApplication.instance()
            if app:
                app.quit()
            
            # Force exit if needed
            import sys
            sys.exit(0)
    
    def set_app_quit_callback(self, callback):
        """Set callback to properly quit the main application."""
        self.app_quit_callback = callback
    
    
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
                    print(f"❌ Error cleaning up voice manager: {e}")
        
        event.accept()


class QtBubbleManager:
    """Manager for Qt chat bubble."""
    
    def __init__(self, llm_manager, config=None, debug=False):
        self.llm_manager = llm_manager
        self.config = config
        self.debug = debug
        
        self.app = None
        self.bubble = None
        self.response_callback = None
        self.error_callback = None
        self.status_callback = None
        
        if not QT_AVAILABLE:
            raise RuntimeError("No Qt library available. Install PyQt5, PySide2, or PyQt6")
        
        if self.debug:
            print(f"✅ QtBubbleManager initialized with {QT_AVAILABLE}")
    
    def show(self):
        """Show the chat bubble."""
        if not self.app:
            # Create QApplication if it doesn't exist
            if not QApplication.instance():
                self.app = QApplication(sys.argv)
            else:
                self.app = QApplication.instance()
        
        if not self.bubble:
            self.bubble = QtChatBubble(self.llm_manager, self.config, self.debug)
            
            # Set up callbacks
            if self.response_callback:
                self.bubble.set_response_callback(self.response_callback)
            if self.error_callback:
                self.bubble.set_error_callback(self.error_callback)
            if self.status_callback:
                self.bubble.set_status_callback(self.status_callback)
            if hasattr(self, 'app_quit_callback') and self.app_quit_callback:
                self.bubble.set_app_quit_callback(self.app_quit_callback)
        
        self.bubble.show()
        self.bubble.raise_()
        self.bubble.activateWindow()
        
        if self.debug:
            print("💬 Qt chat bubble shown")
    
    def hide(self):
        """Hide the chat bubble."""
        if self.bubble:
            self.bubble.hide()
            
            if self.debug:
                print("💬 Qt chat bubble hidden")
    
    def destroy(self):
        """Destroy the chat bubble."""
        if self.bubble:
            self.bubble.close()
            self.bubble = None
            
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
