"""
Qt-based chat bubble for AbstractAssistant.

A simple, modern chat bubble using PyQt5/PySide2 that opens near the system tray.
"""

import sys
import threading
from pathlib import Path
from typing import Optional, Callable

try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
        QTextEdit, QPushButton, QComboBox, QLabel, QFrame
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
    from PyQt5.QtGui import QFont, QPalette, QColor
    QT_AVAILABLE = "PyQt5"
except ImportError:
    try:
        from PySide2.QtWidgets import (
            QApplication, QWidget, QVBoxLayout, QHBoxLayout,
            QTextEdit, QPushButton, QComboBox, QLabel, QFrame
        )
        from PySide2.QtCore import Qt, QTimer, Signal as pyqtSignal, QThread, Slot as pyqtSlot
        from PySide2.QtGui import QFont, QPalette, QColor
        QT_AVAILABLE = "PySide2"
    except ImportError:
        try:
            from PyQt6.QtWidgets import (
                QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                QTextEdit, QPushButton, QComboBox, QLabel, QFrame
            )
            from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
            from PyQt6.QtGui import QFont, QPalette, QColor
            QT_AVAILABLE = "PyQt6"
        except ImportError:
            QT_AVAILABLE = None


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
            print(f"🔄 LLMWorker: Processing message: {self.message[:50]}...")
            print(f"🔄 LLMWorker: Provider: {self.provider}, Model: {self.model}")
            
            # Use LLMManager session for context persistence
            print("🔄 LLMWorker: Using LLMManager session for context...")
            response = self.llm_manager.generate_response(self.message, self.provider, self.model)
            
            # Response is already a string from LLMManager
            response_text = str(response)
            
            print(f"✅ LLMWorker: Got response: {response_text[:100]}...")
            self.response_ready.emit(response_text)
            
        except Exception as e:
            print(f"❌ LLMWorker: Error occurred: {e}")
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
        
        # State
        self.current_provider = 'lmstudio'
        self.current_model = 'qwen/qwen3-next-80b'
        self.token_count = 0
        self.max_tokens = 128000
        
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
        self.resize(540, 260)  # Reduced from 280 to 260
        self.position_near_tray()
        
        # Main layout with optimized spacing
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 8, 16, 16)  # Reduced top margin
        layout.setSpacing(10)  # Tighter spacing for better density
        
        # Compact header - status only (remove redundant title)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 0, 4, 0)
        
        header_layout.addStretch()
        
        # Status indicator - larger and more prominent
        self.status_label = QLabel("READY")
        self.status_label.setObjectName("status_ready")
        self.status_label.setStyleSheet("""
            QLabel {
                background: rgba(166, 227, 161, 0.25);
                border: 1px solid rgba(166, 227, 161, 0.4);
                border-radius: 12px;
                padding: 6px 16px;
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 1px;
                color: #a6e3a1;
            }
        """)
        header_layout.addWidget(self.status_label)
        
        layout.addLayout(header_layout)
        
        # Input section with modern card design
        input_container = QFrame()
        input_container.setStyleSheet("""
            QFrame {
                background: #374151;
                border: 2px solid #4a5568;
                border-radius: 18px;
                padding: 4px;
            }
        """)
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(8)
        
        # Input field with inline send button
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        
        # Text input - larger, primary focus
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Ask me anything... (Shift+Enter to send)")
        self.input_text.setMaximumHeight(180)  # Increased from 140
        self.input_text.setMinimumHeight(120)  # Increased from 100
        input_row.addWidget(self.input_text)
        
        # Send button - larger and more prominent
        self.send_button = QPushButton("→")
        self.send_button.clicked.connect(lambda: self.debug_send_message("button"))
        self.send_button.setFixedSize(50, 50)  # Increased from 40x40
        self.send_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea,
                    stop:1 #764ba2);
                border: none;
                border-radius: 25px;
                font-size: 18px;  /* Reduced to prevent truncation */
                font-weight: bold;
                color: white;
                text-align: center;  /* Ensure proper centering */
                padding: 0px;  /* Remove any padding that might cause truncation */
            }
            
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a6fd8,
                    stop:1 #6a4190);
            }
            
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4e63c6,
                    stop:1 #5e397e);
            }
            
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.4);
            }
        """)
        input_row.addWidget(self.send_button)
        
        input_layout.addLayout(input_row)
        layout.addWidget(input_container)
        
        # Controls section with card design
        controls_container = QFrame()
        controls_container.setStyleSheet("""
            QFrame {
                background: #374151;
                border: 2px solid #4a5568;
                border-radius: 16px;
                padding: 4px;  /* Reduced from 8px to 4px */
            }
        """)
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(8, 4, 8, 4)  # Reduced from (12, 8, 12, 8)
        controls_layout.setSpacing(6)  # Reduced from 8 to 6
        
        # Compact single row for provider, model, and tokens
        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)  # Reduced from 12 to 8
        
        # Provider dropdown - larger and more accessible
        self.provider_combo = QComboBox()
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        self.provider_combo.setMinimumWidth(110)  # Increased from 80
        self.provider_combo.setMinimumHeight(40)  # Increased from 32
        controls_row.addWidget(self.provider_combo)
        
        # Model dropdown - larger and more accessible
        self.model_combo = QComboBox()
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        self.model_combo.setMinimumWidth(130)  # Increased from 100
        self.model_combo.setMinimumHeight(40)  # Increased from 32
        controls_row.addWidget(self.model_combo)
        
        # Token info - larger to match dropdowns
        self.token_label = QLabel("0 / 128k")
        self.token_label.setObjectName("token_label")
        self.token_label.setMinimumHeight(40)  # Match dropdown height
        self.token_label.setMinimumWidth(90)   # Set minimum width
        self.token_label.setStyleSheet("""
            QLabel {
                background: #2d3748;
                border: 1px solid #4a5568;
                border-radius: 8px;
                padding: 10px 14px;  /* Increased padding */
                font-family: 'SF Mono', Monaco, monospace;
                font-size: 12px;  /* Increased from 10px */
                font-weight: 600;  /* Increased from 500 */
                color: #ffffff;
                text-align: center;
            }
        """)
        controls_row.addWidget(self.token_label)
        controls_row.addStretch()
        
        controls_layout.addLayout(controls_row)
        layout.addWidget(controls_container)
        
        self.setLayout(layout)
        
        # Focus on input
        self.input_text.setFocus()
        
        # Enter key handling
        self.input_text.keyPressEvent = self.handle_key_press
    
    def setup_styling(self):
        """Set up modern dark theme styling with solid backgrounds."""
        self.setStyleSheet("""
            /* Main Window - Modern Dark Theme */
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2d3748,
                    stop:0.5 #1a202c,
                    stop:1 #171923);
                border: 2px solid #4a5568;
                border-radius: 20px;
                color: #ffffff;
            }
            
            /* Input Field - Modern Solid Design */
            QTextEdit {
                background: #2d3748;
                border: 2px solid #4a5568;
                border-radius: 16px;
                padding: 16px 20px;
                font-size: 15px;
                font-weight: 400;
                color: #ffffff;
                font-family: system-ui, -apple-system, sans-serif;
                selection-background-color: #4299e1;
                line-height: 1.4;
            }
            
            QTextEdit:focus {
                border: 2px solid #4299e1;
                background: #374151;
            }
            
            QTextEdit::placeholder {
                color: rgba(255, 255, 255, 0.6);
            }
            
            /* Send Button - Premium Gradient with Hover Effects */
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea,
                    stop:1 #764ba2);
                border: none;
                border-radius: 14px;
                padding: 14px 28px;
                font-size: 15px;
                font-weight: 600;
                color: white;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                letter-spacing: 0.5px;
            }
            
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a6fd8,
                    stop:1 #6a4190);
                transform: translateY(-1px);
                box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
            }
            
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4e63c6,
                    stop:1 #5e397e);
                transform: translateY(0px);
            }
            
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.4);
            }
            
            /* Dropdown Menus - Compact Design */
            QComboBox {
                background: #2d3748;
                border: 1px solid #4a5568;
                border-radius: 8px;
                padding: 8px 12px;  /* Increased padding */
                min-width: 80px;
                font-size: 13px;  /* Increased from 11px */
                font-weight: 600;  /* Increased from 500 */
                color: #ffffff;
                font-family: system-ui, -apple-system, sans-serif;
            }
            
            QComboBox:hover {
                border: 1px solid #4299e1;
                background: #374151;
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
                border: 2px solid #4a5568;
                border-radius: 10px;
                selection-background-color: #4299e1;
                color: #ffffff;
                padding: 5px;
            }
            
            QComboBox QAbstractItemView::item {
                height: 40px;  /* Increased from 32px */
                padding: 12px 16px;  /* Increased padding */
                border: none;
                font-size: 13px;  /* Larger text */
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
                color: #a6e3a1;
                font-weight: 600;
            }
            
            QLabel#status_generating {
                color: #fab387;
                font-weight: 600;
            }
            
            QLabel#status_error {
                color: #f38ba8;
                font-weight: 600;
            }
            
            QLabel#token_label {
                color: rgba(255, 255, 255, 0.9);
                font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
                font-size: 11px;
                font-weight: 500;
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
        """Load available providers and models."""
        try:
            providers = self.llm_manager.get_providers()
            
            # Populate provider combo
            self.provider_combo.clear()
            for key, info in providers.items():
                self.provider_combo.addItem(info.display_name, key)
            
            # Set current provider
            for i in range(self.provider_combo.count()):
                if self.provider_combo.itemData(i) == self.current_provider:
                    self.provider_combo.setCurrentIndex(i)
                    break
            
            # Load models for current provider
            self.update_models()
            
        except Exception as e:
            if self.debug:
                print(f"Error loading providers: {e}")
    
    def update_models(self):
        """Update model dropdown based on current provider."""
        try:
            models = self.llm_manager.get_models(self.current_provider)
            
            self.model_combo.clear()
            for model in models:
                # Create display name
                display_name = model.split('/')[-1] if '/' in model else model
                self.model_combo.addItem(display_name, model)
            
            # Set current model
            for i in range(self.model_combo.count()):
                if self.model_combo.itemData(i) == self.current_model:
                    self.model_combo.setCurrentIndex(i)
                    break
            
            self.update_token_limits()
            
        except Exception as e:
            if self.debug:
                print(f"Error updating models: {e}")
    
    def update_token_limits(self):
        """Update token limits based on current model."""
        token_limits = {
            'qwen/qwen3-next-80b': 128000,
            'qwen/qwen3-next-32b': 128000,
            'qwen/qwen3-next-14b': 128000,
            'gpt-4o': 128000,
            'gpt-4o-mini': 128000,
            'gpt-3.5-turbo': 16000,
            'claude-3-5-sonnet-20241022': 200000,
            'claude-3-haiku-20240307': 200000,
            'qwen3:4b-instruct': 32000,
            'llama3.2:3b': 8000,
            'mistral:7b': 8000
        }
        
        self.max_tokens = token_limits.get(self.current_model, 128000)
        self.update_token_display()
    
    def update_token_display(self):
        """Update token count display."""
        max_display = f"{self.max_tokens // 1000}k" if self.max_tokens >= 1000 else str(self.max_tokens)
        current_display = f"{int(self.token_count)}" if self.token_count < 1000 else f"{int(self.token_count // 1000)}k"
        self.token_label.setText(f"{current_display} / {max_display}")
    
    def handle_key_press(self, event):
        """Handle key press events in text input."""
        print(f"🔄 Key pressed: {event.key()}, modifiers: {event.modifiers()}")
        
        # Check for Enter/Return key
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # Shift+Enter or Ctrl+Enter or Cmd+Enter should send message
            if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier or 
                event.modifiers() & Qt.KeyboardModifier.ControlModifier or 
                event.modifiers() & Qt.KeyboardModifier.MetaModifier):
                print("🔄 Shift/Ctrl/Cmd+Enter detected, calling send_message")
                self.debug_send_message("keyboard")
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
    
    def debug_send_message(self, source):
        """Debug wrapper for send_message."""
        print(f"🔄 QtChatBubble: debug_send_message called from {source}")
        self.send_message()
    
    def send_message(self):
        """Send message to LLM."""
        print("🔄 QtChatBubble: send_message called")
        
        message = self.input_text.toPlainText().strip()
        if not message:
            print("❌ QtChatBubble: Empty message, returning")
            return
        
        print(f"🔄 QtChatBubble: Message: '{message}'")
        print(f"🔄 QtChatBubble: Provider: {self.current_provider}, Model: {self.current_model}")
        
        # Clear input and update UI
        self.input_text.clear()
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
        
        # Start worker thread
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
        
        # Update token count (approximate)
        self.token_count += len(response.split()) * 1.3  # Rough estimate
        self.update_token_display()
        
        print(f"🔄 QtChatBubble: Showing toast notification...")
        
        # Show dedicated toast notification
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
    
    def closeEvent(self, event):
        """Handle close event."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
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
