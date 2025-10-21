"""
iPhone Messages-style history dialog for AbstractAssistant.

This module provides an authentic iPhone Messages UI for displaying chat history.
"""
import re
from datetime import datetime
from typing import Dict, List
import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.nl2br import Nl2BrExtension
from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter

try:
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QScrollArea,
                                 QWidget, QLabel, QFrame, QPushButton, QApplication)
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QFont, QCursor
except ImportError:
    try:
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QScrollArea,
                                     QWidget, QLabel, QFrame, QPushButton, QApplication)
        from PyQt5.QtCore import Qt, QTimer, pyqtSignal
        from PyQt5.QtGui import QFont, QCursor
    except ImportError:
        from PySide2.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QScrollArea,
                                       QWidget, QLabel, QFrame, QPushButton, QApplication)
        from PySide2.QtCore import Qt, QTimer, Signal as pyqtSignal
        from PySide2.QtGui import QFont, QCursor


class ClickableBubble(QFrame):
    """Clickable message bubble that copies content to clipboard."""

    clicked = pyqtSignal()

    def __init__(self, content: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.content = content
        self.is_user = is_user
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # Store original colors for animation
        if is_user:
            self.normal_bg = "#007AFF"
            self.clicked_bg = "#0066CC"
        else:
            self.normal_bg = "#3a3a3c"
            self.clicked_bg = "#4a4a4c"

    def mousePressEvent(self, event):
        """Handle mouse press with visual feedback."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Apply clicked style (darker)
            self.setStyleSheet(f"""
                QFrame {{
                    background: {self.clicked_bg};
                    border: none;
                    border-radius: 18px;
                    max-width: 400px;
                }}
            """)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release - copy to clipboard and restore style."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Copy to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(self.content)

            # Visual feedback: glossy effect (lighter color briefly)
            glossy_color = "#0080FF" if self.is_user else "#5a5a5c"
            self.setStyleSheet(f"""
                QFrame {{
                    background: {glossy_color};
                    border: none;
                    border-radius: 18px;
                    max-width: 400px;
                }}
            """)

            # Restore normal color after brief delay
            QTimer.singleShot(200, self._restore_normal_style)

            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _restore_normal_style(self):
        """Restore normal bubble style."""
        self.setStyleSheet(f"""
            QFrame {{
                background: {self.normal_bg};
                border: none;
                border-radius: 18px;
                max-width: 400px;
            }}
        """)


class SafeDialog(QDialog):
    """Dialog that only hides instead of closing to prevent app termination."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide_callback = None

    def set_hide_callback(self, callback):
        """Set callback to call when dialog is hidden."""
        self.hide_callback = callback

    def closeEvent(self, event):
        """Override close event to hide instead of close."""
        event.ignore()
        self.hide()
        if self.hide_callback:
            self.hide_callback()

    def reject(self):
        """Override reject to hide instead of close."""
        self.hide()
        if self.hide_callback:
            self.hide_callback()


class iPhoneMessagesDialog:
    """Create authentic iPhone Messages-style chat history dialog."""

    @staticmethod
    def create_dialog(message_history: List[Dict], parent=None) -> QDialog:
        """Create AUTHENTIC iPhone Messages dialog - EXACTLY like the real app."""
        dialog = SafeDialog(parent)
        dialog.setWindowTitle("Messages")
        dialog.setModal(False)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        dialog.resize(504, 650)  # Increased width by 20% (420 * 1.2 = 504)

        # Position dialog near right edge of screen like iPhone
        iPhoneMessagesDialog._position_dialog_right(dialog)

        # Main layout - zero margins like iPhone
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # iPhone navigation bar
        navbar = iPhoneMessagesDialog._create_authentic_navbar(dialog)
        main_layout.addWidget(navbar)

        # Messages container with pure white background
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { background: #000000; border: none; }")

        # Messages content
        messages_widget = QWidget()
        messages_layout = QVBoxLayout(messages_widget)
        messages_layout.setContentsMargins(0, 16, 0, 16)  # iPhone spacing
        messages_layout.setSpacing(0)

        # Add messages with authentic iPhone styling
        iPhoneMessagesDialog._add_authentic_iphone_messages(messages_layout, message_history)

        messages_layout.addStretch()
        scroll_area.setWidget(messages_widget)
        main_layout.addWidget(scroll_area)

        # Apply authentic iPhone styling
        dialog.setStyleSheet(iPhoneMessagesDialog._get_authentic_iphone_styles())

        # Auto-scroll to bottom to show the latest messages
        QTimer.singleShot(100, lambda: scroll_area.verticalScrollBar().setValue(scroll_area.verticalScrollBar().maximum()))

        return dialog

    @staticmethod
    def _position_dialog_right(dialog):
        """Position dialog near the right edge of the screen."""
        try:
            from PyQt6.QtWidgets import QApplication
        except ImportError:
            try:
                from PyQt5.QtWidgets import QApplication
            except ImportError:
                from PySide2.QtWidgets import QApplication

        # Get screen geometry
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()

        # Position dialog very close to top-right corner
        dialog_width = dialog.width()
        dialog_height = dialog.height()

        x = screen_geometry.width() - dialog_width - 10  # Only 10px from right edge
        y = screen_geometry.y() + 5  # Only 5px below the system tray/navbar

        dialog.move(x, y)

    @staticmethod
    def _create_authentic_navbar(dialog: QDialog) -> QFrame:
        """Create AUTHENTIC iPhone Messages navigation bar."""
        navbar = QFrame()
        navbar.setFixedHeight(94)  # iPhone status bar + nav bar
        navbar.setStyleSheet("""
            QFrame {
                background: #1c1c1e;
                border-bottom: 0.5px solid #38383a;
            }
        """)

        layout = QVBoxLayout(navbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Minimal status bar space
        status_spacer = QFrame()
        status_spacer.setFixedHeight(0)
        layout.addWidget(status_spacer)

        # Navigation bar proper
        nav_frame = QFrame()
        nav_frame.setFixedHeight(44)
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(20, 0, 20, 0)

        # Back button
        back_btn = QPushButton("‹ Back")
        back_btn.clicked.connect(dialog.reject)
        back_btn.setStyleSheet("""
            QPushButton {
                color: #007AFF;
                font-size: 17px;
                font-weight: 400;
                background: transparent;
                border: none;
                text-align: left;
                font-family: "SF Pro Text", "Helvetica Neue", sans-serif;
            }
        """)
        nav_layout.addWidget(back_btn)

        nav_layout.addStretch()

        # Title - Messages
        title = QLabel("Messages")
        title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 17px;
                font-weight: 600;
                font-family: "SF Pro Text", "Helvetica Neue", sans-serif;
            }
        """)
        nav_layout.addWidget(title)

        nav_layout.addStretch()

        layout.addWidget(nav_frame)
        return navbar

    @staticmethod
    def _add_authentic_iphone_messages(layout: QVBoxLayout, message_history: List[Dict]):
        """Add messages with AUTHENTIC iPhone Messages styling."""
        for index, msg in enumerate(message_history):
            message_type = msg.get('type', msg.get('role', 'unknown'))
            is_user = message_type in ['user', 'human']

            # Create authentic iPhone bubble
            bubble_container = iPhoneMessagesDialog._create_authentic_iphone_bubble(msg, is_user, index, message_history)
            layout.addWidget(bubble_container)

            # Add spacing between messages (6px like iPhone)
            if index < len(message_history) - 1:
                spacer = QFrame()
                spacer.setFixedHeight(6)
                spacer.setStyleSheet("background: transparent;")
                layout.addWidget(spacer)

    @staticmethod
    def _create_authentic_iphone_bubble(msg: Dict, is_user: bool, index: int, message_history: List[Dict]) -> QFrame:
        """Create AUTHENTIC iPhone Messages bubble - exactly like real iPhone."""
        main_container = QFrame()
        main_container.setStyleSheet("background: transparent; border: none;")
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        # Message bubble container
        container = QFrame()
        container.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 0, 12, 0)  # Tighter margins for more width
        layout.setSpacing(0)

        # Create clickable bubble
        bubble = ClickableBubble(msg['content'], is_user)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 7, 12, 7)  # More compact padding
        bubble_layout.setSpacing(0)

        # Process content with FULL markdown support
        content = iPhoneMessagesDialog._process_full_markdown(msg['content'])
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)  # No text selection, bubble handles clicks
        content_label.setTextFormat(Qt.TextFormat.RichText)

        if is_user:
            # User bubble: Blue with white text
            bubble.setStyleSheet("""
                QFrame {
                    background: #007AFF;
                    border: none;
                    border-radius: 18px;
                    max-width: 400px;
                }
            """)
            content_label.setStyleSheet("""
                QLabel {
                    background: transparent;
                    color: #FFFFFF;
                    font-size: 14px;
                    font-weight: 400;
                    line-height: 18px;
                    font-family: "SF Pro Text", "Helvetica Neue", sans-serif;
                }
            """)
            # Right align
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            # Received bubble: Light gray with black text
            bubble.setStyleSheet("""
                QFrame {
                    background: #3a3a3c;
                    border: none;
                    border-radius: 18px;
                    max-width: 400px;
                }
            """)
            content_label.setStyleSheet("""
                QLabel {
                    background: transparent;
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: 400;
                    line-height: 18px;
                    font-family: "SF Pro Text", "Helvetica Neue", sans-serif;
                }
            """)
            # Left align
            layout.addWidget(bubble)
            layout.addStretch()

        bubble_layout.addWidget(content_label)
        main_layout.addWidget(container)

        # Add timestamp below bubble (iPhone style)
        timestamp_container = QFrame()
        timestamp_container.setStyleSheet("QFrame { background: transparent; border: none; }")
        timestamp_layout = QHBoxLayout(timestamp_container)
        timestamp_layout.setContentsMargins(16, 0, 16, 4)

        # Format timestamp - handle both ISO string and unix timestamp formats
        from datetime import datetime
        timestamp = msg['timestamp']
        if isinstance(timestamp, (int, float)):
            # Convert unix timestamp to datetime
            dt = datetime.fromtimestamp(timestamp)
        else:
            # Parse ISO format string
            dt = datetime.fromisoformat(timestamp)
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
                font-family: "SF Pro Text", "Helvetica Neue", sans-serif;
                padding: 0px;
            }
        """)

        if is_user:
            timestamp_layout.addStretch()
            timestamp_layout.addWidget(timestamp_label)
        else:
            timestamp_layout.addWidget(timestamp_label)
            timestamp_layout.addStretch()

        # Only show timestamp for every few messages or different times (like iPhone)
        prev_msg = message_history[index - 1] if index > 0 else None
        show_timestamp = (index == 0 or
                         prev_msg is None or
                         index % 5 == 0)  # Every 5th message like iPhone

        if show_timestamp:
            main_layout.addWidget(timestamp_container)

        return main_container

    @staticmethod
    def _process_full_markdown(text: str) -> str:
        """Process markdown using proper markdown library with syntax highlighting."""
        # Configure markdown with extensions
        md = markdown.Markdown(
            extensions=[
                FencedCodeExtension(),
                TableExtension(),
                'nl2br',  # Convert newlines to <br>
            ],
            extension_configs={
                'fenced_code': {
                    'lang_prefix': 'language-',
                }
            }
        )

        # Convert markdown to HTML
        html = md.convert(text)

        # Apply custom styling to the generated HTML
        # Style code blocks
        html = html.replace('<pre>', '<pre style="margin: 6px 0; background: rgba(0,0,0,0.3); border-radius: 6px; padding: 8px; overflow-x: auto;">')
        html = html.replace('<code>', '<code style="font-family: \'SF Mono\', \'Menlo\', \'Monaco\', \'Courier New\', monospace; font-size: 12px; line-height: 1.4; color: #e8e8e8;">')

        # Style tables
        html = html.replace('<table>', '<table style="margin: 6px 0; border-collapse: collapse; width: 100%; font-size: 12px;">')
        html = html.replace('<thead>', '<thead style="background: rgba(0,0,0,0.2);">')
        html = html.replace('<th>', '<th style="padding: 4px 8px; text-align: left; font-weight: 600; border-bottom: 1px solid rgba(255,255,255,0.2);">')
        html = html.replace('<td>', '<td style="padding: 4px 8px; border-bottom: 1px solid rgba(255,255,255,0.1);">')

        # Style headers with minimal spacing
        html = html.replace('<h1>', '<h1 style="margin: 6px 0 2px 0; font-weight: 600; font-size: 17px;">')
        html = html.replace('<h2>', '<h2 style="margin: 5px 0 2px 0; font-weight: 600; font-size: 16px;">')
        html = html.replace('<h3>', '<h3 style="margin: 4px 0 1px 0; font-weight: 600; font-size: 15px;">')
        html = html.replace('<h4>', '<h4 style="margin: 3px 0 1px 0; font-weight: 600; font-size: 14px;">')

        # Style lists with minimal spacing
        html = html.replace('<ul>', '<ul style="margin: 4px 0; padding-left: 20px;">')
        html = html.replace('<ol>', '<ol style="margin: 4px 0; padding-left: 20px;">')
        html = html.replace('<li>', '<li style="margin: 1px 0; line-height: 1.3;">')

        # Style paragraphs with minimal spacing
        html = html.replace('<p>', '<p style="margin: 2px 0; line-height: 1.3;">')

        return html

    @staticmethod
    def _get_authentic_iphone_styles() -> str:
        """Get AUTHENTIC iPhone Messages styles - dark background like real iPhone."""
        return """
            QDialog {
                background: #000000;
                color: #ffffff;
            }

            QFrame {
                background: transparent;
                border: none;
            }

            QWidget {
                background: transparent;
            }
        """