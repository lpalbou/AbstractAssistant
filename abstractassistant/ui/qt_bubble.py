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

# Import our new manager classes
try:
    from .provider_manager import ProviderManager
    from .ui_styles import UIStyles
    from .tts_state_manager import TTSStateManager, TTSState
    from .history_dialog import iPhoneMessagesDialog
    MANAGERS_AVAILABLE = True
except ImportError:
    MANAGERS_AVAILABLE = False
    ProviderManager = None
    UIStyles = None
    TTSStateManager = None
    TTSState = None
    iPhoneMessagesDialog = None

try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QTextEdit, QPushButton, QComboBox, QLabel, QFrame,
        QFileDialog, QMessageBox
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot, QRect
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
        from PySide2.QtCore import Qt, QTimer, Signal as pyqtSignal, QThread, Slot as pyqtSlot
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
        self._tts_state = 'idle'  # 'idle', 'speaking', 'paused'
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
        """Set TTS enabled state."""
        if self._enabled != enabled:
            self._enabled = enabled
            self.setChecked(enabled)
            self._update_appearance()
            self.toggled.emit(enabled)

    def set_tts_state(self, state: str):
        """Set TTS state for visual feedback.

        Args:
            state: One of 'idle', 'speaking', 'paused'
        """
        if self._tts_state != state:
            self._tts_state = state
            self._update_appearance()

    def get_tts_state(self) -> str:
        """Get current TTS state."""
        return self._tts_state

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
        """Handle single click - pause/resume or toggle."""
        self._click_count = 0

        if self._enabled:
            # TTS is enabled, handle pause/resume
            self.single_clicked.emit()
        else:
            # TTS is disabled, toggle it on
            self.set_enabled(True)

    def _handle_double_click(self):
        """Handle double click - stop TTS and open chat."""
        self.double_clicked.emit()

    def _update_appearance(self):
        """Update button appearance based on TTS state."""
        # Set icon text based on state
        if not self._enabled:
            icon = "🔇"  # Muted speaker when disabled
            bg_color = "rgba(255, 255, 255, 0.06)"
            text_color = "rgba(255, 255, 255, 0.7)"
        elif self._tts_state == 'speaking':
            icon = "🔊"  # Loud speaker when speaking
            bg_color = "rgba(0, 170, 0, 0.8)"  # Green
            text_color = "#ffffff"
        elif self._tts_state == 'paused':
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

        # TTS functionality (VoiceLLM-compatible)
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
    
    def setup_ui(self):
        """Set up the modern user interface with SOTA UX practices."""
        self.setWindowTitle("AbstractAssistant")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        # Set optimal size for modern chat interface - much wider to nearly touch screen edge
        self.setFixedSize(630, 196)  # Increased width from 540 to 700 for better text display
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
            self.tts_toggle.single_clicked.connect(self.on_tts_single_click)
            self.tts_toggle.double_clicked.connect(self.on_tts_double_click)
            header_layout.addWidget(self.tts_toggle)

            # Full Voice Mode toggle (STT + TTS)
            self.full_voice_toggle = FullVoiceToggle()
            self.full_voice_toggle.toggled.connect(self.on_full_voice_toggled)
            header_layout.addWidget(self.full_voice_toggle)

            # Add prominent voice control panel when TTS is active
            self.voice_control_panel = self.create_voice_control_panel()
            header_layout.addWidget(self.voice_control_panel)
            self.voice_control_panel.hide()  # Hidden initially
        
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
                font-family: -apple-system, system-ui, sans-serif;
            }
        """)
        header_layout.addWidget(self.status_label)
        
        layout.addLayout(header_layout)
        
        # Input section with modern card design
        self.input_container = QFrame()
        self.input_container.setStyleSheet("""
            QFrame {
                background: #1e1e1e;
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
        layout.addWidget(self.input_container)
        
        # Bottom controls - Cursor style (minimal, clean)
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(12, 3, 12, 4)
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
        self.token_label.setFixedHeight(36)  # Increased by 30% (28 * 1.3 = 36.4 ≈ 36)
        self.token_label.setMinimumWidth(104)  # Increased by 30% (80 * 1.3 = 104)
        self.token_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.token_label.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 14px;
                font-size: 12px;
                color: rgba(255, 255, 255, 0.6);
                font-family: -apple-system, system-ui, sans-serif;
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
        
        # Position at the right corner with no gap
        x = screen.width() - self.width()  # 0px from right edge - touching the corner
        y = 50
        
        self.move(x, y)
        
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
                    print(f"🔍 ProviderManager found {len(available_providers)} available providers")

                # Add providers to dropdown
                for display_name, provider_key in available_providers:
                    self.provider_combo.addItem(display_name, provider_key)
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
                print(f"🔍 Final selected provider: {self.current_provider}")

            # Load models for current provider
            self.update_models()

        except Exception as e:
            if self.debug:
                print(f"❌ Error loading providers: {e}")
                import traceback
                traceback.print_exc()

            # Final fallback
            if self.provider_combo.count() == 0:
                self.provider_combo.addItem("LMStudio (Local)", "lmstudio")
                self.current_provider = "lmstudio"
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
                print(f"✅ Final selected model: {self.current_model}")

            self.update_token_limits()

        except Exception as e:
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

                # Update toggle state to 'speaking'
                self._update_tts_toggle_state()

                # Wait for speech to complete in a separate thread
                def wait_for_speech():
                    while self.voice_manager.is_speaking():
                        time.sleep(0.1)
                    # Update toggle state when speech completes
                    self._update_tts_toggle_state()
                    if self.debug:
                        print("🔊 TTS completed")
                
                speech_thread = threading.Thread(target=wait_for_speech, daemon=True)
                speech_thread.start()

                # Show chat history after TTS starts (small delay)
                QTimer.singleShot(800, self.show_history)

            except Exception as e:
                if self.debug:
                    print(f"❌ TTS error: {e}")
                # Show chat history as fallback
                QTimer.singleShot(100, self.show_history)
        else:
            # Show chat history instead of toast when TTS is disabled
            self.show_history()
        
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
                self._update_tts_toggle_state()
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
                    print("🔊 TTS paused via single click")
                elif self.debug:
                    print("🔊 TTS pause failed - audio stream may not be ready yet")
            elif current_state == 'paused':
                # Resume the speech
                success = self.voice_manager.resume()
                if success and self.debug:
                    print("🔊 TTS resumed via single click")
                elif self.debug:
                    print("🔊 TTS resume failed")
            else:
                # If idle, do nothing or could show a message
                if self.debug:
                    print("🔊 TTS single click - no active speech to pause/resume")

            # Update visual state
            self._update_tts_toggle_state()

        except Exception as e:
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
                print(f"🔊 Pause attempt {attempt + 1}/{max_attempts} failed, retrying...")

            # Short delay before retry
            time.sleep(0.1)

        return False

    def on_tts_double_click(self):
        """Handle double click on TTS toggle - stop TTS and open chat bubble."""
        if self.debug:
            print("🔊 TTS double click - stopping speech and showing chat")

        # Stop any current speech
        if self.voice_manager and self.tts_enabled:
            try:
                self.voice_manager.stop()
                self._update_tts_toggle_state()
            except Exception as e:
                if self.debug:
                    print(f"❌ Error stopping TTS on double click: {e}")

        # Show the chat bubble
        self.show()
        self.raise_()
        self.activateWindow()

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
                print("❌ Voice manager not available for Full Voice Mode")
                self.full_voice_toggle.set_enabled(False)
                return

            if self.debug:
                print("🚀 Starting Full Voice Mode...")

            # Hide text input UI
            self.hide_text_ui()

            # Enable TTS automatically
            if not self.tts_enabled:
                self.tts_toggle.set_enabled(True)

            # Set up voice mode based on CLI parameter
            self.voice_manager.set_voice_mode(self.listening_mode)

            # Update LLM session for voice-optimized responses
            if self.llm_manager:
                self.llm_manager.create_new_session(tts_mode=True)

            # Start listening
            self.voice_manager.listen(
                on_transcription=self.handle_voice_input,
                on_stop=self.handle_voice_stop
            )

            # Update UI state
            self.full_voice_toggle.set_listening_state('listening')
            self.update_status("LISTENING")

            # Greet the user
            self.voice_manager.speak("Full voice mode activated. I'm listening...")

            if self.debug:
                print("✅ Full Voice Mode started successfully")

        except Exception as e:
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
                print("🛑 Stopping Full Voice Mode...")

            # Stop listening
            if self.voice_manager:
                self.voice_manager.stop_listening()
                self.voice_manager.stop_speaking()

            # Show text input UI
            self.show_text_ui()

            # Update UI state
            self.full_voice_toggle.set_listening_state('idle')
            self.update_status("READY")

            if self.debug:
                print("✅ Full Voice Mode stopped")

        except Exception as e:
            if self.debug:
                print(f"❌ Error stopping Full Voice Mode: {e}")
                import traceback
                traceback.print_exc()

    def handle_voice_input(self, transcribed_text: str):
        """Handle speech-to-text input from the user."""
        try:
            if self.debug:
                print(f"👤 Voice input: {transcribed_text}")

            # Update UI state
            self.full_voice_toggle.set_listening_state('processing')
            self.update_status("PROCESSING")

            # Log the message to history (but don't show in UI)
            user_message = {
                "role": "user",
                "content": transcribed_text,
                "timestamp": datetime.now().isoformat()
            }
            self.message_history.append(user_message)

            # Generate AI response
            response = self.llm_manager.generate_response(
                transcribed_text,
                self.current_provider,
                self.current_model
            )

            # Log AI response to history
            ai_message = {
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat()
            }
            self.message_history.append(ai_message)

            if self.debug:
                print(f"🤖 AI response: {response[:100]}...")

            # Speak the response
            self.voice_manager.speak(response)

            # Update UI state back to listening
            self.full_voice_toggle.set_listening_state('listening')
            self.update_status("LISTENING")

        except Exception as e:
            if self.debug:
                print(f"❌ Error handling voice input: {e}")
                import traceback
                traceback.print_exc()

            # Reset to listening state
            self.full_voice_toggle.set_listening_state('listening')
            self.update_status("LISTENING")

    def handle_voice_stop(self):
        """Handle when user says 'stop' to exit Full Voice Mode."""
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
        self.setFixedSize(630, 120)  # Reduced width by 10% to match normal size

    def show_text_ui(self):
        """Show the text input interface when exiting Full Voice Mode."""
        # Show the input container and other text-related UI elements
        if hasattr(self, 'input_container'):
            self.input_container.show()

        # Restore normal window size with wider width
        self.setFixedSize(630, 196)

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
                    font-family: -apple-system, system-ui, sans-serif;
                }}
            """)

    def _update_tts_toggle_state(self):
        """Update the TTS toggle visual state based on current TTS state."""
        if hasattr(self, 'tts_toggle') and self.voice_manager:
            try:
                current_state = self.voice_manager.get_state()
                self.tts_toggle.set_tts_state(current_state)

                # Show/hide voice control panel based on TTS state
                if hasattr(self, 'voice_control_panel'):
                    if current_state in ['speaking', 'paused']:
                        self.voice_control_panel.show()
                        self._update_voice_control_panel(current_state)
                    else:
                        self.voice_control_panel.hide()

                if self.debug:
                    print(f"🔊 TTS toggle state updated to: {current_state}")
            except Exception as e:
                if self.debug:
                    print(f"❌ Error updating TTS toggle state: {e}")

    def create_voice_control_panel(self):
        """Create a prominent voice control panel that appears when TTS is active."""
        panel = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        # Pause/Resume button
        self.voice_pause_button = QPushButton("⏸")
        self.voice_pause_button.setFixedSize(24, 24)
        self.voice_pause_button.setToolTip("Pause/Resume TTS (Space)")
        self.voice_pause_button.clicked.connect(self.on_tts_single_click)
        self.voice_pause_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 12px;
                font-size: 12px;
                color: rgba(255, 255, 255, 0.9);
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.3);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.05);
            }
        """)
        layout.addWidget(self.voice_pause_button)

        # Stop button
        self.voice_stop_button = QPushButton("⏹")
        self.voice_stop_button.setFixedSize(24, 24)
        self.voice_stop_button.setToolTip("Stop TTS (Escape)")
        self.voice_stop_button.clicked.connect(self.on_tts_double_click)
        self.voice_stop_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 100, 100, 0.1);
                border: 1px solid rgba(255, 100, 100, 0.3);
                border-radius: 12px;
                font-size: 12px;
                color: rgba(255, 200, 200, 0.9);
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 100, 100, 0.2);
                border: 1px solid rgba(255, 100, 100, 0.4);
            }
            QPushButton:pressed {
                background: rgba(255, 100, 100, 0.05);
            }
        """)
        layout.addWidget(self.voice_stop_button)

        # Status text
        self.voice_status_label = QLabel("Speaking...")
        self.voice_status_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.8);
                font-size: 10px;
                font-weight: 500;
                padding: 2px 4px;
            }
        """)
        layout.addWidget(self.voice_status_label)

        panel.setLayout(layout)
        return panel

    def _update_voice_control_panel(self, state):
        """Update the voice control panel based on TTS state."""
        if not hasattr(self, 'voice_control_panel'):
            return

        if state == 'speaking':
            self.voice_pause_button.setText("⏸")
            self.voice_pause_button.setToolTip("Pause TTS (Space)")
            self.voice_status_label.setText("Speaking...")
        elif state == 'paused':
            self.voice_pause_button.setText("▶")
            self.voice_pause_button.setToolTip("Resume TTS (Space)")
            self.voice_status_label.setText("Paused")

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
                print("✅ Keyboard shortcuts setup: Space (pause/resume), Escape (stop)")

        except Exception as e:
            if self.debug:
                print(f"❌ Error setting up keyboard shortcuts: {e}")

    def handle_space_shortcut(self):
        """Handle space bar shortcut for pause/resume."""
        # Only handle if TTS is active and input field doesn't have focus
        if (self.voice_manager and self.voice_manager.get_state() in ['speaking', 'paused'] and
            not self.input_text.hasFocus()):
            self.on_tts_single_click()
            if self.debug:
                print("🔊 Space shortcut triggered pause/resume")

    def handle_escape_shortcut(self):
        """Handle escape key shortcut for stop."""
        if self.voice_manager and self.voice_manager.get_state() in ['speaking', 'paused']:
            self.on_tts_double_click()
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
        
        # Show chat history instead of error toast
        if self.debug:
            print(f"❌ AI Error: {error}")

        # Show history so user can see the error context
        QTimer.singleShot(100, self.show_history)
        
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

                        # Clear our local message history (let AbstractCore handle it)
                        self.message_history = []
                        self._rebuild_chat_display()

                        QMessageBox.information(
                            self,
                            "Session Loaded",
                            f"Successfully loaded session via AbstractCore.\nMessages: {message_count}"
                        )

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
                    print(f"❌ Failed to save session: {e}")
    
    def show_history(self):
        """Toggle message history dialog visibility."""
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
                # Create dialog first time
                self.history_dialog = iPhoneMessagesDialog.create_dialog(self.message_history, self)
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
                    self.history_dialog = iPhoneMessagesDialog.create_dialog(self.message_history, self)
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
                        font-family: -apple-system, system-ui, sans-serif;
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
                        font-family: -apple-system, system-ui, sans-serif;
                        padding: 0 10px;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.1);
                        color: rgba(255, 255, 255, 0.9);
                    }
                """)

    def close_app(self):
        """Close the entire application completely."""
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
                print("🔄 Calling app quit callback")
            try:
                self.app_quit_callback()
            except Exception as e:
                if self.debug:
                    print(f"❌ App callback failed: {e}")

        # ALWAYS force quit as well to ensure the app terminates
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
            print("🔄 Force exit with sys.exit and os._exit")
        try:
            sys.exit(0)
        except:
            # Ultimate fallback - force process termination
            os._exit(0)
    
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
            print(f"✅ QtBubbleManager initialized with {QT_AVAILABLE}")

    def _prepare_bubble(self):
        """Pre-initialize the bubble for instant display later."""
        if not self.app:
            # Create QApplication if it doesn't exist
            if not QApplication.instance():
                self.app = QApplication(sys.argv)
            else:
                self.app = QApplication.instance()

        if not self.bubble:
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
