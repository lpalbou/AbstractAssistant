"""
Dedicated toast notification window for AbstractAssistant responses.

A standalone Qt window that shows AI responses in a toast format,
positioned in the top-right corner with expand/collapse functionality.
"""

import sys
from typing import Optional
import pyperclip

try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
        QTextEdit, QPushButton, QLabel, QFrame, QScrollArea
    )
    from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QEasingCurve
    from PyQt5.QtGui import QFont, QPalette, QColor, QTextCursor
    QT_AVAILABLE = "PyQt5"
except ImportError:
    try:
        from PySide2.QtWidgets import (
            QApplication, QWidget, QVBoxLayout, QHBoxLayout,
            QTextEdit, QPushButton, QLabel, QFrame, QScrollArea
        )
        from PySide2.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QEasingCurve
        from PySide2.QtGui import QFont, QPalette, QColor, QTextCursor
        QT_AVAILABLE = "PySide2"
    except ImportError:
        QT_AVAILABLE = None


class ToastWindow(QWidget):
    """Standalone toast notification window for AI responses."""
    
    def __init__(self, message: str, debug: bool = False):
        super().__init__()
        self.message = message
        self.debug = debug
        self.is_expanded = False
        
        # Window properties
        self.collapsed_height = 120
        self.expanded_height = 400
        self.window_width = 350
        
        self.setup_window()
        self.setup_ui()
        self.setup_styling()
        self.position_window()
        
        # Auto-hide timer
        self.auto_hide_timer = QTimer()
        self.auto_hide_timer.timeout.connect(self.hide_toast)
        self.auto_hide_timer.setSingleShot(True)
        
        if self.debug:
            print(f"✅ ToastWindow created for message: {message[:50]}...")
    
    def setup_window(self):
        """Configure window properties."""
        self.setWindowTitle("AbstractAssistant Response")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        # Start collapsed
        self.resize(self.window_width, self.collapsed_height)
        
        # Make sure it's always visible
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)
        
        # Header with title and buttons
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title_label = QLabel("AI Response")
        title_label.setFont(QFont("SF Pro Text", 12, QFont.Weight.Bold))
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Copy button
        self.copy_button = QPushButton("📋")
        self.copy_button.setFixedSize(30, 30)
        self.copy_button.setToolTip("Copy to clipboard")
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        header_layout.addWidget(self.copy_button)
        
        # Close button
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setToolTip("Close")
        self.close_button.clicked.connect(self.hide_toast)
        header_layout.addWidget(self.close_button)
        
        layout.addLayout(header_layout)
        
        # Message content (scrollable)
        self.content_area = QTextEdit()
        self.content_area.setReadOnly(True)
        self.content_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_area.setFont(QFont("SF Pro Text", 11))
        
        # Set the message content
        self.content_area.setPlainText(self.message)
        
        # Make content area clickable to expand
        self.content_area.mousePressEvent = self.toggle_expand
        
        layout.addWidget(self.content_area)
        
        self.setLayout(layout)
    
    def setup_styling(self):
        """Apply modern dark theme styling."""
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border-radius: 12px;
            }
            
            QLabel {
                color: #cdd6f4;
                background: transparent;
                border: none;
            }
            
            QPushButton {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
                color: #cdd6f4;
                font-weight: bold;
            }
            
            QPushButton:hover {
                background-color: #45475a;
                border-color: #74c7ec;
            }
            
            QPushButton:pressed {
                background-color: #585b70;
            }
            
            QTextEdit {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 8px;
                color: #cdd6f4;
                selection-background-color: #74c7ec;
            }
            
            QScrollBar:vertical {
                background-color: #313244;
                width: 8px;
                border-radius: 4px;
            }
            
            QScrollBar::handle:vertical {
                background-color: #585b70;
                border-radius: 4px;
                min-height: 20px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: #74c7ec;
            }
        """)
    
    def position_window(self):
        """Position window in top-right corner."""
        screen = QApplication.primaryScreen().geometry()
        
        # Position in top-right with some margin
        x = screen.width() - self.window_width - 20
        y = 60  # Below menu bar
        
        self.move(x, y)
        
        if self.debug:
            print(f"Toast positioned at ({x}, {y})")
    
    def show_toast(self, auto_hide_seconds: int = 8):
        """Show the toast notification."""
        self.show()
        self.raise_()
        self.activateWindow()
        
        # Start auto-hide timer
        if auto_hide_seconds > 0:
            self.auto_hide_timer.start(auto_hide_seconds * 1000)
        
        if self.debug:
            print(f"🍞 Toast shown, will auto-hide in {auto_hide_seconds}s")
    
    def hide_toast(self):
        """Hide the toast notification."""
        self.hide()
        
        if self.debug:
            print("🍞 Toast hidden")
    
    def toggle_expand(self, event=None):
        """Toggle between collapsed and expanded view."""
        if self.is_expanded:
            # Collapse
            self.resize(self.window_width, self.collapsed_height)
            self.is_expanded = False
            if self.debug:
                print("🍞 Toast collapsed")
        else:
            # Expand
            self.resize(self.window_width, self.expanded_height)
            self.is_expanded = True
            # Stop auto-hide when expanded
            self.auto_hide_timer.stop()
            if self.debug:
                print("🍞 Toast expanded")
        
        # Reposition to stay in top-right
        self.position_window()
    
    def copy_to_clipboard(self):
        """Copy message content to clipboard."""
        try:
            pyperclip.copy(self.message)
            
            # Brief visual feedback
            original_text = self.copy_button.text()
            self.copy_button.setText("✓")
            QTimer.singleShot(1000, lambda: self.copy_button.setText(original_text))
            
            if self.debug:
                print("📋 Message copied to clipboard")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Failed to copy to clipboard: {e}")
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging or expanding."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is in content area (for expanding)
            content_rect = self.content_area.geometry()
            if content_rect.contains(event.pos()):
                self.toggle_expand()
        
        super().mousePressEvent(event)


class ToastManager:
    """Manager for toast notifications."""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.current_toast: Optional[ToastWindow] = None
        
        # Ensure QApplication exists
        if not QApplication.instance():
            self.app = QApplication(sys.argv)
        else:
            self.app = QApplication.instance()
        
        if self.debug:
            print("✅ ToastManager initialized")
    
    def show_response(self, message: str, auto_hide_seconds: int = 8):
        """Show a response toast notification."""
        # Close existing toast
        if self.current_toast:
            self.current_toast.hide()
            self.current_toast.deleteLater()
        
        # Create new toast
        self.current_toast = ToastWindow(message, debug=self.debug)
        self.current_toast.show_toast(auto_hide_seconds)
        
        if self.debug:
            print(f"🍞 Response toast created and shown")
    
    def show_error(self, error_message: str):
        """Show an error toast notification."""
        self.show_response(f"Error: {error_message}", auto_hide_seconds=10)
    
    def hide_current_toast(self):
        """Hide the current toast if any."""
        if self.current_toast:
            self.current_toast.hide_toast()


# Standalone function to show a toast (can be called from anywhere)
def show_toast_notification(message: str, debug: bool = False):
    """Standalone function to show a toast notification."""
    try:
        # Create a minimal QApplication if none exists
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        
        # Create and show toast
        toast = ToastWindow(message, debug=debug)
        toast.show_toast()
        
        if debug:
            print(f"🍞 Standalone toast shown: {message[:50]}...")
        
        return toast
        
    except Exception as e:
        if debug:
            print(f"❌ Failed to show standalone toast: {e}")
        # Fallback to console
        print(f"💬 AI Response: {message}")
        return None
