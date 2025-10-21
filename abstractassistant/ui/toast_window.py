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

    def __init__(self, message: str, debug: bool = False, voice_manager=None):
        super().__init__()
        self.message = message
        self.debug = debug
        self.is_expanded = False
        self.voice_manager = voice_manager  # Reference to voice manager for playback control
        
        # Window properties - doubled height and increased width by 50%
        self.collapsed_height = 240  # Reduced back since no reply panel
        self.expanded_height = 800   # Reduced back since no reply panel
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
        layout.setContentsMargins(8, 6, 8, 8)  # Reduced margins
        layout.setSpacing(6)  # Reduced spacing
        
        # Header with title and buttons - Cursor style
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(8)
        
        # Title (clean, minimal)
        title_label = QLabel("AI Response")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: 500;
                color: rgba(255, 255, 255, 0.9);
                background: transparent;
                border: none;
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
        """)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()

        # TTS playback controls (if voice manager available)
        if self.voice_manager:
            # Pause/Play button
            self.pause_play_button = QPushButton("⏸")
            self.pause_play_button.setFixedSize(24, 24)
            self.pause_play_button.setToolTip("Pause/Resume TTS")
            self.pause_play_button.clicked.connect(self.toggle_pause_resume)
            self.pause_play_button.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.08);
                    border: none;
                    border-radius: 12px;
                    font-size: 11px;
                    color: rgba(255, 255, 255, 0.7);
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.15);
                    color: rgba(255, 255, 255, 0.9);
                }
            """)
            header_layout.addWidget(self.pause_play_button)

            # Stop button
            self.stop_button = QPushButton("⏹")
            self.stop_button.setFixedSize(24, 24)
            self.stop_button.setToolTip("Stop TTS")
            self.stop_button.clicked.connect(self.stop_tts)
            self.stop_button.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.08);
                    border: none;
                    border-radius: 12px;
                    font-size: 11px;
                    color: rgba(255, 255, 255, 0.7);
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.15);
                    color: rgba(255, 255, 255, 0.9);
                }
            """)
            header_layout.addWidget(self.stop_button)

            # Update button states based on TTS state
            self._update_playback_buttons()

        # Copy button (Cursor style)
        self.copy_button = QPushButton("📋")
        self.copy_button.setFixedSize(24, 24)
        self.copy_button.setToolTip("Copy to clipboard")
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        self.copy_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 12px;
                font-size: 11px;
                color: rgba(255, 255, 255, 0.7);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.15);
                color: rgba(255, 255, 255, 0.9);
            }
        """)
        header_layout.addWidget(self.copy_button)
        
        # Close button (Cursor style)
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(24, 24)
        self.close_button.setToolTip("Close")
        self.close_button.clicked.connect(self.hide_toast)
        self.close_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 12px;
                font-size: 11px;
                color: rgba(255, 255, 255, 0.7);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.15);
                color: rgba(255, 255, 255, 0.9);
            }
        """)
        header_layout.addWidget(self.close_button)
        
        layout.addLayout(header_layout)
        
        # Message content (scrollable) with markdown rendering
        self.content_area = QTextBrowser()
        self.content_area.setReadOnly(True)
        self.content_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Font styling handled by CSS stylesheet
        
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
        
        # No reply panel - use main chat bubble for new messages
        
        self.setLayout(layout)
    
    # Reply panel functionality removed - use main chat bubble for new messages
    
    def setup_styling(self):
        """Apply Cursor-style clean theme to match the chat bubble."""
        self.setStyleSheet("""
            /* Main Window - Cursor Style */
            QWidget {
                background: #1e1e1e;
                border: none;
                border-radius: 12px;
                color: #ffffff;
            }
            
            /* Labels - Clean Typography */
            QLabel {
                color: rgba(255, 255, 255, 0.9);
                background: transparent;
                border: none;
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                font-size: 11px;
                font-weight: 500;
            }
            
            /* Buttons - Cursor Style */
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 11px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: 500;
                color: rgba(255, 255, 255, 0.8);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
            
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.15);
                color: rgba(255, 255, 255, 1.0);
            }
            
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.06);
            }
            
            /* Content Area - Cursor Style */
            QTextBrowser {
                background: rgba(255, 255, 255, 0.03);
                border: none;
                border-radius: 8px;
                padding: 16px 20px;
                font-size: 13px;
                font-weight: 400;
                color: rgba(255, 255, 255, 0.95);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                selection-background-color: rgba(34, 197, 94, 0.3);
                line-height: 1.5;
            }
            
            QTextBrowser:focus {
                background: rgba(255, 255, 255, 0.05);
            }
            
            /* Scrollbar - Hidden like iOS */
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
            
            /* Frames - Invisible Containers */
            QFrame {
                border: none;
                background: transparent;
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

    def toggle_pause_resume(self):
        """Toggle pause/resume TTS playback."""
        if not self.voice_manager:
            return

        try:
            current_state = self.voice_manager.get_state()

            if current_state == 'speaking':
                # Pause the speech - use retry logic for timing issues
                success = self._attempt_pause_with_retry()
                if success and self.debug:
                    print("🔊 TTS paused via toast button")
                elif self.debug:
                    print("🔊 TTS pause failed via toast button - audio stream may not be ready")
            elif current_state == 'paused':
                # Resume the speech
                success = self.voice_manager.resume()
                if success and self.debug:
                    print("🔊 TTS resumed via toast button")
                elif self.debug:
                    print("🔊 TTS resume failed via toast button")
            elif current_state == 'idle':
                # Re-speak the message if idle
                self.voice_manager.speak(self.message)
                if self.debug:
                    print("🔊 TTS restarted via toast button")

            # Update button states
            self._update_playback_buttons()

        except Exception as e:
            if self.debug:
                print(f"❌ Error toggling pause/resume: {e}")

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
                print(f"🔊 Toast pause attempt {attempt + 1}/{max_attempts} failed, retrying...")

            # Short delay before retry
            time.sleep(0.1)

        return False

    def stop_tts(self):
        """Stop TTS playback."""
        if not self.voice_manager:
            return

        try:
            self.voice_manager.stop()
            self._update_playback_buttons()
            if self.debug:
                print("🔊 TTS stopped via toast button")
        except Exception as e:
            if self.debug:
                print(f"❌ Error stopping TTS: {e}")

    def _update_playback_buttons(self):
        """Update playback button states based on current TTS state."""
        if not self.voice_manager or not hasattr(self, 'pause_play_button'):
            return

        try:
            current_state = self.voice_manager.get_state()

            if current_state == 'speaking':
                # Show pause button
                self.pause_play_button.setText("⏸")
                self.pause_play_button.setToolTip("Pause TTS")
            elif current_state == 'paused':
                # Show play button
                self.pause_play_button.setText("▶")
                self.pause_play_button.setToolTip("Resume TTS")
            else:
                # Show play button (idle state)
                self.pause_play_button.setText("▶")
                self.pause_play_button.setToolTip("Play TTS")

        except Exception as e:
            if self.debug:
                print(f"❌ Error updating playback buttons: {e}")

    # All reply functionality removed - use main chat bubble for new messages

    # Removed mousePressEvent to prevent accidental closing


class ToastManager:
    """Manager for toast notifications."""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.current_toast: Optional[ToastWindow] = None
        
        # Always use existing QApplication instance (never create a new one)
        self.app = QApplication.instance()
        if not self.app:
            raise RuntimeError("No QApplication instance found. This should be created by the main app first.")
        
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
def show_toast_notification(message: str, debug: bool = False, voice_manager=None):
    """Standalone function to show a toast notification - stays visible until manually closed."""
    try:
        # Always use existing QApplication instance (never create a new one)
        app = QApplication.instance()
        if not app:
            raise RuntimeError("No QApplication instance found. This should be created by the main app first.")

        # Create and show toast (no auto-hide)
        toast = ToastWindow(message, debug=debug, voice_manager=voice_manager)
        
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
        
        # Reply functionality removed - use main chat bubble for new messages
        
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
