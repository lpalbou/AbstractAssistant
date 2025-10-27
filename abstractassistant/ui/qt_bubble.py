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

# Import AbstractVoice-compatible TTS manager (required dependency)
from ..core.tts_manager import VoiceManager

# Import our new manager classes (required dependencies)
from .provider_manager import ProviderManager
from .ui_styles import UIStyles
from .tts_state_manager import TTSStateManager, TTSState
from .history_dialog import iPhoneMessagesDialog

# Since these are required dependencies, set availability to True
TTS_AVAILABLE = True
MANAGERS_AVAILABLE = True

try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QTextEdit, QPushButton, QComboBox, QLabel, QFrame,
        QFileDialog, QMessageBox
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot, QRect, QMetaObject
    from PyQt5.QtGui import QFont, QPalette, QColor, QPainter, QPen, QBrush
    from PyQt5.QtCore import QPoint
    QT_AVAILABLE = "PyQt5"
except ImportError:
    try:
        from PySide2.QtWidgets import (
            QApplication, QWidget, QVBoxLayout, QHBoxLayout,
            QTextEdit, QPushButton, QComboBox, QLabel, QFrame,
            QFileDialog, QMessageBox
        )
        from PySide2.QtCore import Qt, QTimer, Signal as pyqtSignal, QThread, Slot as pyqtSlot, QMetaObject
        from PySide2.QtGui import QFont, QPalette, QColor, QPainter, QPen, QBrush
        from PySide2.QtCore import QPoint
        QT_AVAILABLE = "PySide2"
    except ImportError:
        try:
            from PyQt6.QtWidgets import (
                QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                QTextEdit, QPushButton, QComboBox, QLabel, QFrame,
                QFileDialog, QMessageBox
            )
            from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
            from PyQt6.QtGui import QFont, QPalette, QColor, QPainter, QPen, QBrush
            from PyQt6.QtCore import QPoint
            QT_AVAILABLE = "PyQt6"
        except ImportError:
            QT_AVAILABLE = None


class TTSToggle(QPushButton):
    """TTS toggle button with speaker icon and single/double click detection."""

    toggled = pyqtSignal(bool)
    single_clicked = pyqtSignal()    # New signal for single click (pause/resume)
    double_clicked = pyqtSignal()    # New signal for double click (stop + chat)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 24)  # Slightly wider for button
        self.setToolTip("Single click: Pause/Resume TTS, Double click: Stop and open chat")
        self._enabled = False
        self.setCheckable(True)

        # Click detection for single/double click
        self._click_count = 0
        self._click_timer = QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._handle_single_click)
        self._double_click_interval = 300  # ms

        self._update_appearance()
        
    def is_enabled(self) -> bool:
        """Check if TTS is enabled."""
        return self._enabled
    
    def set_enabled(self, enabled: bool):
        """Set TTS enabled state - USER CONTROL ONLY."""
        if self._enabled != enabled:
            self._enabled = enabled
            self.setChecked(enabled)
            self._update_appearance()
            self.toggled.emit(enabled)

    def mousePressEvent(self, event):
        """Handle mouse press for single/double click detection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._click_count += 1

            if self._click_count == 1:
                # Start timer for single click
                self._click_timer.start(self._double_click_interval)
            elif self._click_count == 2:
                # Double click detected
                self._click_timer.stop()
                self._click_count = 0
                self._handle_double_click()

        super().mousePressEvent(event)

    def _handle_single_click(self):
        """Handle single click - toggle TTS on/off."""
        self._click_count = 0
        # Simple toggle: if enabled, disable it; if disabled, enable it
        new_state = not self._enabled
        self.set_enabled(new_state)

    def _handle_double_click(self):
        """Handle double click - stop TTS and open chat."""
        self.double_clicked.emit()

    def _update_appearance(self):
        """Update button appearance based on user's toggle state ONLY."""
        # SIMPLE USER CONTROL - only shows enabled/disabled state
        if self._enabled:
            # User has enabled TTS
            icon = "🔉"  # Speaker icon when enabled
            bg_color = "rgba(0, 102, 204, 0.8)"  # Blue
            text_color = "#ffffff"
        else:
            # User has disabled TTS
            icon = "🔇"  # Muted speaker when disabled
            bg_color = "rgba(255, 255, 255, 0.06)"
            text_color = "rgba(255, 255, 255, 0.7)"

        self.setText(icon)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                border: none;
                border-radius: 12px;
                font-size: 12px;
                color: {text_color};
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(0, 122, 255, 0.8);
            }}
            QPushButton:pressed {{
                background: rgba(0, 122, 255, 0.6);
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
            self.toggled.emit(enabled)


    def _update_appearance(self):
        """Update button appearance based on user's toggle state ONLY."""
        # SIMPLE USER CONTROL - only shows enabled/disabled state
        if self._enabled:
            # User has enabled Full Voice Mode
            icon = "🎙️"  # Microphone when enabled
            bg_color = "rgba(0, 122, 204, 0.8)"  # Blue
            text_color = "#ffffff"
        else:
            # User has disabled Full Voice Mode
            icon = "🎤"  # Muted microphone when disabled
            bg_color = "rgba(255, 255, 255, 0.06)"
            text_color = "rgba(255, 255, 255, 0.7)"

        self.setText(icon)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                border: none;
                border-radius: 12px;
                font-size: 12px;
                color: {text_color};
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {bg_color.replace('0.8', '1.0') if '0.8' in bg_color else bg_color};
            }}
            QPushButton:pressed {{
                background: {bg_color.replace('0.8', '0.6') if '0.8' in bg_color else bg_color};
            }}
        """)




class LLMWorker(QThread):
    """Worker thread for LLM processing."""

    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, llm_manager, message, provider, model, media=None):
        super().__init__()
        self.llm_manager = llm_manager
        self.message = message
        self.provider = provider
        self.model = model
        self.media = media or []

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


class QtChatBubble(QWidget):
    """Modern Qt-based chat bubble."""
    
    def __init__(self, llm_manager, config=None, debug=False, listening_mode="wait"):
        super().__init__()
        self.llm_manager = llm_manager
        self.config = config
        self.debug = debug
        self.listening_mode = listening_mode
        
        # State - default to LMStudio with qwen/qwen3-next-80b
        self.current_provider = 'lmstudio'  # Default to LMStudio
        self.current_model = 'qwen/qwen3-next-80b'  # Default to qwen/qwen3-next-80b
        self.token_count = 0
        self.max_tokens = 128000
        
        # Message history for session management
        self.message_history: List[Dict] = []

        # History dialog instance for toggle behavior
        self.history_dialog = None

        # Attached files for media handling (AbstractCore 2.4.5+)
        self.attached_files: List[str] = []
        
        # Track file attachments per message for history display
        self.message_file_attachments: Dict[int, List[str]] = {}
        
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
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        # Set optimal size for modern chat interface - much wider to nearly touch screen edge
        # Initial size - will be adjusted dynamically based on file attachments
        self.base_width = 630
        self.base_height = 196
        self.setFixedSize(self.base_width, self.base_height)
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
        self.close_button = QPushButton("⨯")  # Better close icon - geometric multiplication symbol
        self.close_button.setFixedSize(24, 24)  # Increased from 18x18 to 24x24 for better visibility
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
        header_layout.addWidget(self.close_button)
        
        # Session buttons (minimal, rounded)
        session_buttons = [
            ("Clear", self.clear_session),
            ("Load", self.load_session), 
            ("Save", self.save_session),
            # ("Compact", self.compact_session),  # Hidden for now - functionality preserved
            ("History", self.show_history)
        ]
        
        for text, handler in session_buttons:
            btn = QPushButton(text)
            btn.setFixedHeight(22)
            btn.clicked.connect(handler)

            # Store reference to history button for toggle appearance
            if text == "History":
                self.history_button = btn
            btn.setStyleSheet("""
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
                    background: rgba(255, 255, 255, 0.12);
                    color: rgba(255, 255, 255, 0.9);
                }
            """)
            header_layout.addWidget(btn)
        
        # TTS toggle (if available)
        if self.voice_manager and self.voice_manager.is_available():
            self.tts_toggle = TTSToggle()
            self.tts_toggle.toggled.connect(self.on_tts_toggled)
            self.tts_toggle.single_clicked.connect(self.on_tts_single_click)
            self.tts_toggle.double_clicked.connect(self.on_tts_double_click)
            header_layout.addWidget(self.tts_toggle)

            # Full Voice Mode toggle (STT + TTS)
            self.full_voice_toggle = FullVoiceToggle()
            self.full_voice_toggle.toggled.connect(self.on_full_voice_toggled)
            header_layout.addWidget(self.full_voice_toggle)

            # Voice control panel removed - not needed
        
        header_layout.addStretch()
        
        # Status (Cursor-style, enlarged to show full text including "Processing")
        self.status_label = QLabel("READY")
        self.status_label.setFixedSize(120, 24)  # Increased from 80x24 to 120x24 for "Processing" text
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
        header_layout.addWidget(self.status_label)
        
        layout.addLayout(header_layout)
        
        # Input section with modern card design
        self.input_container = QFrame()
        self.input_container.setStyleSheet("""
            QFrame {
                background: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 8px;
                padding: 4px;
            }
        """)
        input_layout = QVBoxLayout(self.input_container)
        input_layout.setContentsMargins(4, 4, 4, 4)
        input_layout.setSpacing(4)
        
        # Input field with inline send button
        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        # File attachment button - modern paperclip icon
        self.attach_button = QPushButton("📎")
        self.attach_button.clicked.connect(self.attach_files)
        self.attach_button.setFixedSize(36, 36)
        self.attach_button.setToolTip("Attach files (images, PDFs, Office docs, etc.)")
        self.attach_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid #404040;
                border-radius: 18px;
                font-size: 14px;
                color: rgba(255, 255, 255, 0.7);
                text-align: center;
                padding: 0px;
            }

            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid #0066cc;
                color: rgba(255, 255, 255, 0.9);
            }

            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.06);
            }
        """)
        input_row.addWidget(self.attach_button)

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

        # Attached files display area (initially hidden)
        self.attached_files_container = QFrame()
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
        
        self.setLayout(layout)

        # Setup keyboard shortcuts for voice control
        self.setup_keyboard_shortcuts()

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
                background: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 8px;
                padding: 12px 16px;
                font-size: 14px;
                font-weight: 400;
                color: #ffffff;
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                selection-background-color: #0066cc;
                line-height: 1.4;
            }
            
            QTextEdit:focus {
                border: 1px solid #0066cc;
                background: #333333;
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
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
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
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
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
                    font-family: "Helvetica Neue", "Helvetica", "Segoe UI", Arial, sans-serif;
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
                font-family: "Helvetica Neue", "Helvetica", 'Segoe UI', Arial, sans-serif;
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
                font-family: "Helvetica Neue", "Helvetica", "Segoe UI", Arial, sans-serif;
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
                font-family: "Helvetica Neue", "Helvetica", "Segoe UI", Arial, sans-serif;
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
                font-family: "Helvetica Neue", "Helvetica", "Segoe UI", Arial, sans-serif;
            }
            
            QLabel#token_label {
                background: #2d3748;
                border: 1px solid #4a5568;
                border-radius: 8px;
                padding: 10px 12px;
                font-family: "Helvetica Neue", "Helvetica", "Segoe UI", Arial, sans-serif;
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
                    display_name = self.provider_manager.create_model_display_name(model, max_length=25)
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
                    display_name = model.split('/')[-1] if '/' in model else model
                    if len(display_name) > 25:
                        display_name = display_name[:22] + "..."
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
    

    def attach_files(self):
        """Open file dialog to attach files (AbstractCore 2.4.5+ media handling)."""
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter(
            "All supported files (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff "
            "*.pdf *.docx *.xlsx *.pptx *.txt *.md *.csv *.tsv *.json);;"
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff);;"
            "Documents (*.pdf *.docx *.xlsx *.pptx *.txt *.md);;"
            "Data files (*.csv *.tsv *.json);;"
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
            file_chip.setStyleSheet("""
                QFrame {
                    background: rgba(0, 102, 204, 0.2);
                    border: 1px solid rgba(0, 102, 204, 0.4);
                    border-radius: 6px;
                    padding: 1px 4px;
                }
            """)

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
            else:
                icon = "📎"

            file_label = QLabel(f"{icon} {file_name[:20]}{'...' if len(file_name) > 20 else ''}")
            file_label.setStyleSheet("background: transparent; border: none; color: rgba(255, 255, 255, 0.9); font-size: 8px;")
            chip_layout.addWidget(file_label)

            # Remove button
            remove_btn = QPushButton("✕")
            remove_btn.setFixedSize(12, 12)
            remove_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    color: rgba(255, 255, 255, 0.6);
                    font-size: 8px;
                    padding: 0px;
                }
                QPushButton:hover {
                    color: rgba(255, 60, 60, 0.9);
                }
            """)
            remove_btn.clicked.connect(lambda checked, fp=file_path: self.remove_attached_file(fp))
            chip_layout.addWidget(remove_btn)

            self.attached_files_layout.addWidget(file_chip)

        self.attached_files_layout.addStretch()
        
        # Adjust window size to accommodate file attachments
        self._adjust_window_size_for_attachments()

    def _adjust_window_size_for_attachments(self):
        """Dynamically adjust window size based on file attachments presence."""
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
        self.worker = LLMWorker(
            self.llm_manager,
            message,
            self.current_provider,
            self.current_model,
            media=media_files if media_files else None
        )
        self.worker.response_ready.connect(self.on_response_ready)
        self.worker.error_occurred.connect(self.on_error_occurred)

        if self.debug:
            print("🔄 QtChatBubble: Starting worker thread...")
        self.worker.start()

        if self.debug:
            print("🔄 QtChatBubble: Worker thread started, hiding bubble...")
        # Hide bubble after sending (like the original design)
        QTimer.singleShot(500, self.hide)
    
    @pyqtSlot(str)
    def on_response_ready(self, response):
        """Handle LLM response."""
        if self.debug:
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
        
        # Notify main app about status change (for icon animation)
        if self.status_callback:
            self.status_callback("ready")
        
        # Get updated message history from AbstractCore session
        self._update_message_history_from_session()

        # Update token count from AbstractCore
        self._update_token_count_from_session()
        
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
                self.voice_manager.speak(clean_response)

                # Update toggle state to 'speaking'
                self._update_tts_toggle_state()
                
                # Store response for callback when TTS completes
                self._pending_response = response

                # Show chat history after TTS starts (small delay) - only if voice mode is OFF
                QTimer.singleShot(800, self._show_history_if_voice_mode_off)

            except Exception as e:
                if self.debug:
                    if self.debug:
                        print(f"❌ TTS error: {e}")
                # Show chat history as fallback - only if voice mode is OFF
                QTimer.singleShot(100, self._show_history_if_voice_mode_off)
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
        """Handle Full Voice Mode toggle state change."""
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

            # Hide text input UI
            self.hide_text_ui()

            # Enable TTS automatically
            if not self.tts_enabled:
                self.tts_toggle.set_enabled(True)

            # Set up voice mode based on CLI parameter
            self.voice_manager.set_voice_mode(self.listening_mode)

            # Update LLM session mode for voice-optimized responses (preserve history)
            if self.llm_manager:
                self.llm_manager.update_session_mode(tts_mode=True)

            # Start listening
            self.voice_manager.listen(
                on_transcription=self.handle_voice_input,
                on_stop=self.handle_voice_stop
            )

            # No longer updating voice toggle appearance - it's a simple user control
            self.update_status("LISTENING")

            # Greet the user
            self.voice_manager.speak("Full voice mode activated. I'm listening...")

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
            self.full_voice_toggle.set_enabled(False)
            self.show_text_ui()

    def stop_full_voice_mode(self):
        """Stop Full Voice Mode and return to normal text mode."""
        try:
            if self.debug:
                if self.debug:
                    print("🛑 Stopping Full Voice Mode...")

            # Stop listening
            if self.voice_manager:
                self.voice_manager.stop_listening()
                self.voice_manager.stop_speaking()

            # Show text input UI
            self.show_text_ui()

            # No longer updating voice toggle appearance - it's a simple user control
            self.update_status("READY")

            if self.debug:
                if self.debug:
                    print("✅ Full Voice Mode stopped")

        except Exception as e:
            if self.debug:
                if self.debug:
                    print(f"❌ Error stopping Full Voice Mode: {e}")
                import traceback
                traceback.print_exc()

    def handle_voice_input(self, transcribed_text: str):
        """Handle speech-to-text input from the user."""
        try:
            if self.debug:
                if self.debug:
                    print(f"👤 Voice input: {transcribed_text}")

            # No longer updating voice toggle appearance - it's a simple user control
            self.update_status("PROCESSING")

            # Generate AI response (AbstractCore will handle message logging automatically)
            response = self.llm_manager.generate_response(
                transcribed_text,
                self.current_provider,
                self.current_model
            )

            # Update message history from AbstractCore session
            self._update_message_history_from_session()

            if self.debug:
                if self.debug:
                    print(f"🤖 AI response: {response[:100]}...")

            # Speak the response
            self.voice_manager.speak(response)

            # No longer updating voice toggle appearance - it's a simple user control
            self.update_status("LISTENING")

        except Exception as e:
            if self.debug:
                if self.debug:
                    print(f"❌ Error handling voice input: {e}")
                import traceback
                traceback.print_exc()

            # No longer updating voice toggle appearance - it's a simple user control
            self.update_status("LISTENING")

    def handle_voice_stop(self):
        """Handle when user says 'stop' to exit Full Voice Mode."""
        if self.debug:
            if self.debug:
                print("🛑 User said 'stop' - exiting Full Voice Mode")

        # Disable Full Voice Mode
        self.full_voice_toggle.set_enabled(False)

    def hide_text_ui(self):
        """Hide the text input interface during Full Voice Mode."""
        # Hide the input container and other text-related UI elements
        if hasattr(self, 'input_container'):
            self.input_container.hide()

        # Update window size to be smaller but maintain wider width
        voice_base_height = 120
        attachment_height = 28 if (self.attached_files and self.attached_files_container.isVisible()) else 0
        voice_height = voice_base_height + attachment_height
        self.setFixedSize(self.base_width, voice_height)  # Dynamic height for voice mode

    def show_text_ui(self):
        """Show the text input interface when exiting Full Voice Mode."""
        # Show the input container and other text-related UI elements
        if hasattr(self, 'input_container'):
            self.input_container.show()

        # Restore normal window size with wider width - use dynamic sizing
        self._adjust_window_size_for_attachments()

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
                current_state = self.voice_manager.get_state()
                # No longer updating tts_toggle appearance - it's a simple user control

                # Voice control panel removed - no longer needed

                if self.debug:
                    if self.debug:
                        print(f"🔊 TTS toggle state updated to: {current_state}")
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
        
        # Show chat history instead of error toast
        if self.debug:
            if self.debug:
                print(f"❌ AI Error: {error}")

        # Show history so user can see the error context - only if voice mode is OFF
        QTimer.singleShot(100, self._show_history_if_voice_mode_off)
        
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
            "Are you sure you want to clear the current session?\nThis will remove all messages, attached files, and reset the token count.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if hasattr(self, 'chat_display'):
                self.chat_display.clear()
                self.chat_display.hide()

            # Clear AbstractCore session and create a new one
            if self.llm_manager:
                self.llm_manager.create_new_session()
                if self.debug:
                    if self.debug:
                        print("🧹 AbstractCore session cleared and recreated")

            self.message_history.clear()
            self.token_count = 0
            self.update_token_display()

            # Clear attached files as part of session clearing
            self.attached_files.clear()
            self.message_file_attachments.clear()
            self.update_attached_files_display()

            if self.debug:
                if self.debug:
                    print("🧹 Session cleared (including attached files and file tracking)")
    
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
            # Create new session with summary as enhanced system prompt
            enhanced_system_prompt = f"""You are a helpful AI assistant who has access to tools to help the user.
Always be a critical and creative thinker who leverage constructive skepticism to progress and evolve its reasoning and answers.
Always answer in nicely formatted markdown.

=== CONVERSATION CONTEXT ===
The following is a summary of our previous conversation:

{summary}

=== END CONTEXT ===

Continue the conversation naturally, referring to the context above when relevant."""

            # Create new session with enhanced system prompt
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
                    system_prompt=enhanced_system_prompt,
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
        """Update local message history from AbstractCore session."""
        if self.llm_manager and self.llm_manager.current_session:
            try:
                # Get messages from AbstractCore session
                session_messages = getattr(self.llm_manager.current_session, 'messages', [])

                # Convert AbstractCore messages to our format
                self.message_history = []
                for i, msg in enumerate(session_messages):
                    # Skip system messages
                    if hasattr(msg, 'role') and msg.role == 'system':
                        continue

                    message = {
                        'timestamp': datetime.now().isoformat(),  # AbstractCore doesn't store timestamps
                        'type': getattr(msg, 'role', 'unknown'),
                        'content': getattr(msg, 'content', str(msg)),
                        'provider': self.current_provider,
                        'model': self.current_model,
                        'attached_files': self.message_file_attachments.get(len(self.message_history), [])
                    }
                    self.message_history.append(message)

                if self.debug:
                    if self.debug:
                        print(f"📚 Updated message history from AbstractCore: {len(self.message_history)} messages")

            except Exception as e:
                if self.debug:
                    if self.debug:
                        print(f"❌ Error updating message history from session: {e}")

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
            print(f"🗑️ _handle_message_deletion called with indices: {indices_to_delete}")
            print(f"📊 Current message_history length: {len(self.message_history)}")

            if not indices_to_delete:
                print("❌ No indices to delete")
                return

            # Validate indices
            for index in indices_to_delete:
                if not (0 <= index < len(self.message_history)):
                    print(f"❌ Invalid index {index}, message_history length: {len(self.message_history)}")
                    QMessageBox.critical(
                        self,
                        "Invalid Selection",
                        f"Invalid message index {index}. Please refresh and try again."
                    )
                    return
            
            print(f"✅ All indices valid. Proceeding with deletion of {len(indices_to_delete)} messages")
            
            # Show which messages will be deleted
            for index in indices_to_delete:
                msg = self.message_history[index]
                print(f"🗑️ Will delete index {index}: {msg.get('type')} - {msg.get('content', '')[:50]}...")
            
            # Delete messages from local history (indices are sorted in reverse order)
            original_count = len(self.message_history)
            print(f"📊 Original message count: {original_count}")
            
            for index in indices_to_delete:
                if 0 <= index < len(self.message_history):
                    deleted_msg = self.message_history[index]
                    print(f"🗑️ Deleting message at index {index}: {deleted_msg.get('content', '')[:50]}...")
                    del self.message_history[index]
                else:
                    print(f"⚠️ Skipping invalid index {index}")
            
            print(f"📊 Messages after deletion: {len(self.message_history)}")
            
            # Update AbstractCore session to reflect deletions
            print("🔄 Updating AbstractCore session...")
            self._update_abstractcore_session_after_deletion()
            
            # Update token count
            print("🔄 Updating token count...")
            self._update_token_count_from_session()
            
            # Update history dialog if it's open (keep it open!)
            if self.history_dialog and self.history_dialog.isVisible():
                print(f"🔄 Updating history dialog content with {len(self.message_history)} remaining messages...")
                try:
                    # Update the dialog content without closing it
                    self.history_dialog.update_message_history(self.message_history)
                    print("✅ History dialog updated successfully")
                except Exception as dialog_error:
                    print(f"❌ Error updating dialog: {dialog_error}")
                    import traceback
                    traceback.print_exc()
                    # Fallback: recreate dialog if update fails
                    try:
                        print("🔄 Fallback: recreating dialog...")
                        if len(self.message_history) == 0:
                            print("📭 No messages remaining - closing history dialog")
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
                                print("✅ History dialog recreated")
                    except:
                        print("❌ Fallback failed - closing dialog")
                        try:
                            self.history_dialog.hide()
                            self._update_history_button_appearance(False)
                        except:
                            pass
            
            # Log success (no popup)
            deleted_count = original_count - len(self.message_history)
            print(f"✅ Successfully deleted {deleted_count} messages")
            
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
            print("🔄 Starting AbstractCore session update...")
            
            if not self.llm_manager or not self.llm_manager.current_session:
                print("⚠️ No LLM manager or current session - skipping AbstractCore update")
                return
            
            # Get current system prompt
            current_session = self.llm_manager.current_session
            system_prompt = getattr(current_session, 'system_prompt', None) or """
                You are a helpful AI assistant who has access to tools to help the user.
                Always be a critical and creative thinker who leverage constructive skepticism to progress and evolve its reasoning and answers.
                Always answer in nicely formatted markdown.
            """
            print("✅ Got system prompt")
            
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
                print(f"✅ Loaded {len(tools)} tools")
            except ImportError as import_error:
                print(f"⚠️ Could not import tools: {import_error}")
                pass
            
            # Create new session with updated message history
            print("🔄 Creating new AbstractCore session...")
            from abstractcore import BasicSession
            new_session = BasicSession(
                self.llm_manager.llm,
                system_prompt=system_prompt,
                tools=tools
            )
            print("✅ New session created")
            
            # Add remaining messages to the new session
            print(f"🔄 Adding {len(self.message_history)} messages to new session...")
            for i, msg in enumerate(self.message_history):
                try:
                    if msg.get('type') == 'user':
                        from abstractcore.messages import UserMessage
                        user_msg = UserMessage(content=msg.get('content', ''))
                        new_session.messages.append(user_msg)
                        print(f"✅ Added user message {i}")
                    elif msg.get('type') == 'assistant':
                        from abstractcore.messages import AssistantMessage
                        assistant_msg = AssistantMessage(content=msg.get('content', ''))
                        new_session.messages.append(assistant_msg)
                        print(f"✅ Added assistant message {i}")
                    elif msg.get('type') == 'system':
                        print(f"⚠️ Skipping system message {i} (handled by system_prompt)")
                    else:
                        print(f"⚠️ Unknown message type at {i}: {msg.get('type')}")
                except Exception as msg_error:
                    print(f"❌ Error adding message {i}: {msg_error}")
                    # Continue with other messages
            
            # Replace current session
            print("🔄 Replacing current session...")
            self.llm_manager.current_session = new_session
            
            print(f"✅ Updated AbstractCore session after message deletion")
                
        except Exception as e:
            print(f"❌ Error updating AbstractCore session after deletion: {e}")
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
        if self.status_callback:
            self.status_callback("speaking")
    
    @pyqtSlot()
    def _on_speech_ended_main_thread(self):
        """Handle speech end on main thread (called via QMetaObject.invokeMethod)."""
        if self.debug:
            print("🔊 QtChatBubble: Speech ended - handling completion on main thread")
        
        # Update toggle state when speech completes
        self._update_tts_toggle_state()
        
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
