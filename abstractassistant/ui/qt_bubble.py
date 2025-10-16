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
        
        # Worker thread
        self.worker = None
        
        self.setup_ui()
        self.setup_styling()
        self.load_providers()
        
        if self.debug:
            print("✅ QtChatBubble initialized")
    
    def setup_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("AbstractAssistant")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        # Set size and position
        self.resize(400, 300)
        self.position_near_tray()
        
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Input area
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Ask me anything...")
        self.input_text.setMaximumHeight(100)
        self.input_text.setFont(QFont("SF Pro Text", 14))
        layout.addWidget(self.input_text)
        
        # Send button
        self.send_button = QPushButton("Send")
        self.send_button.setFont(QFont("SF Pro Text", 12, QFont.Weight.Bold))
        self.send_button.clicked.connect(lambda: self.debug_send_message("button"))
        layout.addWidget(self.send_button)
        
        # Controls section
        controls_frame = QFrame()
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(0, 10, 0, 0)
        
        # Provider dropdown
        self.provider_combo = QComboBox()
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        controls_layout.addWidget(QLabel("Provider:"))
        controls_layout.addWidget(self.provider_combo)
        
        # Separator
        controls_layout.addWidget(QLabel("|"))
        
        # Model dropdown
        self.model_combo = QComboBox()
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        controls_layout.addWidget(QLabel("Model:"))
        controls_layout.addWidget(self.model_combo)
        
        # Separator
        controls_layout.addWidget(QLabel("|"))
        
        # Token info
        self.token_label = QLabel("0 / 128k tk")
        self.token_label.setFont(QFont("SF Mono", 10))
        controls_layout.addWidget(self.token_label)
        
        # Separator
        controls_layout.addWidget(QLabel("|"))
        
        # Status
        self.status_label = QLabel("ready")
        self.status_label.setFont(QFont("SF Pro Text", 10))
        controls_layout.addWidget(self.status_label)
        
        layout.addWidget(controls_frame)
        
        self.setLayout(layout)
        
        # Focus on input
        self.input_text.setFocus()
        
        # Enter key handling
        self.input_text.keyPressEvent = self.handle_key_press
    
    def setup_styling(self):
        """Set up modern styling."""
        # Dark theme styling
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border-radius: 12px;
            }
            
            QTextEdit {
                background-color: #313244;
                border: 2px solid #45475a;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
                color: #cdd6f4;
            }
            
            QTextEdit:focus {
                border-color: #89b4fa;
            }
            
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #89b4fa, stop:1 #74c7ec);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #74c7ec, stop:1 #89b4fa);
            }
            
            QPushButton:pressed {
                background: #585b70;
            }
            
            QPushButton:disabled {
                background: #585b70;
                color: #6c7086;
            }
            
            QComboBox {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 80px;
            }
            
            QComboBox:hover {
                border-color: #74c7ec;
            }
            
            QComboBox::drop-down {
                border: none;
            }
            
            QComboBox::down-arrow {
                width: 12px;
                height: 12px;
            }
            
            QLabel {
                color: #a6adc8;
                font-size: 11px;
            }
            
            QFrame {
                border: none;
                background: transparent;
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
        self.token_label.setText(f"{self.token_count} / {max_display} tk")
    
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
        self.send_button.setText("Generating...")
        self.status_label.setText("generating")
        self.status_label.setStyleSheet("color: #fab387;")
        
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
        self.send_button.setText("Send")
        self.status_label.setText("ready")
        self.status_label.setStyleSheet("color: #a6e3a1;")
        
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
        self.send_button.setText("Send")
        self.status_label.setText("error")
        self.status_label.setStyleSheet("color: #f38ba8;")
        
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
