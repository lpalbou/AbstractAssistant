"""
Dedicated toast notification window for AbstractAssistant responses.

A standalone Qt window that shows AI responses in a toast format,
positioned in the top-right corner with expand/collapse functionality.
"""

import sys
from typing import Optional
import pyperclip

# Import markdown renderer
try:
    from ..utils.markdown_renderer import render_markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    try:
        # Try absolute import as fallback
        from abstractassistant.utils.markdown_renderer import render_markdown
        MARKDOWN_AVAILABLE = True
    except ImportError:
        MARKDOWN_AVAILABLE = False
        def render_markdown(text):
            return f"<pre>{text}</pre>"

print(f"🔍 Toast Window: MARKDOWN_AVAILABLE = {MARKDOWN_AVAILABLE}")

try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
        QTextEdit, QTextBrowser, QPushButton, QLabel, QFrame, QScrollArea
    )
    from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QEasingCurve
    from PyQt5.QtGui import QFont, QPalette, QColor, QTextCursor
    QT_AVAILABLE = "PyQt5"
except ImportError:
    try:
        from PySide2.QtWidgets import (
            QApplication, QWidget, QVBoxLayout, QHBoxLayout,
            QTextEdit, QTextBrowser, QPushButton, QLabel, QFrame, QScrollArea
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
        
        # Window properties - doubled height and increased width by 50%
        self.collapsed_height = 240  # Was 120, now doubled
        self.expanded_height = 800   # Was 400, now doubled
        self.window_width = 525      # Was 350, now increased by 50%
        
        self.setup_window()
        self.setup_ui()
        self.setup_styling()
        self.position_window()
        
        # No auto-hide timer - toast stays visible until manually closed
        
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
        
        # Message content (scrollable) with markdown rendering
        self.content_area = QTextBrowser()
        self.content_area.setReadOnly(True)
        self.content_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_area.setFont(QFont("SF Pro Text", 14))  # Increased from 11 to 14
        
        # Configure QTextBrowser for proper HTML rendering
        self.content_area.setOpenExternalLinks(False)  # Don't open external links
        self.content_area.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        
        # Set the message content with markdown rendering
        if MARKDOWN_AVAILABLE:
            try:
                html_content = render_markdown(self.message)
                self.content_area.setHtml(html_content)
                if self.debug:
                    print(f"🎨 Markdown rendered successfully, HTML length: {len(html_content)}")
                    print(f"🎨 HTML preview: {html_content[:200]}...")
                    print(f"🎨 Message preview: {self.message[:100]}...")
            except Exception as e:
                if self.debug:
                    print(f"❌ Markdown rendering failed: {e}")
                self.content_area.setPlainText(self.message)
        else:
            if self.debug:
                print("❌ Markdown not available, using plain text")
            self.content_area.setPlainText(self.message)
        
        # Content area is read-only, no click-to-expand (only close button closes)
        
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
            
            QTextBrowser {
                background-color: #1a202c;
                border: 1px solid #4a5568;
                border-radius: 8px;
                padding: 12px;
                color: #e2e8f0;
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
    
    def show_toast(self, auto_hide_seconds: int = 0):
        """Show the toast notification - stays visible until manually closed."""
        self.show()
        self.raise_()
        self.activateWindow()
        
        # No auto-hide - toast stays visible until user closes it
        
        if self.debug:
            print(f"🍞 Toast shown, stays visible until manually closed")
    
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
    
    # Removed mousePressEvent to prevent accidental closing


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
    
    def show_response(self, message: str, auto_hide_seconds: int = 0):
        """Show a response toast notification - stays visible until manually closed."""
        # Close existing toast
        if self.current_toast:
            self.current_toast.hide()
            self.current_toast.deleteLater()
        
        # Create new toast
        self.current_toast = ToastWindow(message, debug=self.debug)
        self.current_toast.show_toast()  # No auto-hide
        
        if self.debug:
            print(f"🍞 Response toast created and shown")
    
    def show_error(self, error_message: str):
        """Show an error toast notification - stays visible until manually closed."""
        self.show_response(f"Error: {error_message}")
    
    def hide_current_toast(self):
        """Hide the current toast if any."""
        if self.current_toast:
            self.current_toast.hide_toast()


# Global reference to keep toast windows alive and prevent garbage collection
_active_toasts = []

# Standalone function to show a toast (can be called from anywhere)
def show_toast_notification(message: str, debug: bool = False):
    """Standalone function to show a toast notification - stays visible until manually closed."""
    try:
        # Create a minimal QApplication if none exists
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        
        # Create and show toast (no auto-hide)
        toast = ToastWindow(message, debug=debug)
        
        # Keep a global reference to prevent garbage collection
        _active_toasts.append(toast)
        
        # Connect close event to remove from active list
        def on_toast_closed():
            if toast in _active_toasts:
                _active_toasts.remove(toast)
            if debug:
                print(f"🍞 Toast removed from active list, {len(_active_toasts)} remaining")
        
        # Override the hide_toast method to call our cleanup
        original_hide = toast.hide_toast
        def hide_with_cleanup():
            original_hide()
            on_toast_closed()
        toast.hide_toast = hide_with_cleanup
        
        toast.show_toast()
        
        if debug:
            print(f"🍞 Standalone toast shown: {message[:50]}... (Active toasts: {len(_active_toasts)})")
        
        return toast
        
    except Exception as e:
        if debug:
            print(f"❌ Failed to show standalone toast: {e}")
        # Fallback to console
        print(f"💬 AI Response: {message}")
        return None
