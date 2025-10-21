"""
iPhone Messages-style history dialog for AbstractAssistant.

This module provides an authentic iPhone Messages UI for displaying chat history.
"""
import re
from datetime import datetime
from typing import Dict, List

try:
    from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QScrollArea,
                                 QWidget, QLabel, QFrame, QPushButton)
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QFont
except ImportError:
    try:
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QScrollArea,
                                     QWidget, QLabel, QFrame, QPushButton)
        from PyQt5.QtCore import Qt, QTimer
        from PyQt5.QtGui import QFont
    except ImportError:
        from PySide2.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QScrollArea,
                                       QWidget, QLabel, QFrame, QPushButton)
        from PySide2.QtCore import Qt, QTimer
        from PySide2.QtGui import QFont


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
                font-family: -apple-system;
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
                font-family: -apple-system;
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
        layout.setContentsMargins(16, 0, 16, 0)  # iPhone margins
        layout.setSpacing(0)

        # Create bubble
        bubble = QFrame()
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(13, 8, 13, 8)  # iPhone padding
        bubble_layout.setSpacing(0)

        # Process content with FULL markdown support
        content = iPhoneMessagesDialog._process_full_markdown(msg['content'])
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_label.setTextFormat(Qt.TextFormat.RichText)

        if is_user:
            # User bubble: Blue with white text
            bubble.setStyleSheet("""
                QFrame {
                    background: #007AFF;
                    border: none;
                    border-radius: 18px;
                    max-width: 320px;
                }
            """)
            content_label.setStyleSheet("""
                QLabel {
                    background: transparent;
                    color: #FFFFFF;
                    font-size: 17px;
                    font-weight: 400;
                    line-height: 22px;
                    font-family: -apple-system;
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
                    max-width: 320px;
                }
            """)
            content_label.setStyleSheet("""
                QLabel {
                    background: transparent;
                    color: #ffffff;
                    font-size: 17px;
                    font-weight: 400;
                    line-height: 22px;
                    font-family: -apple-system;
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
                font-family: -apple-system;
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
        """Process markdown formatting for iPhone Messages display."""
        # Convert **bold** to <strong>bold</strong>
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)

        # Convert *italic* to <em>italic</em>
        text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)

        # Convert `code` to inline code
        text = re.sub(r'`([^`]+)`', r'<code style="background: rgba(0,0,0,0.1); padding: 2px 4px; border-radius: 3px; font-family: monospace;">\1</code>', text)

        # Convert headers
        text = re.sub(r'^#### (.*$)', r'<h4 style="margin: 8px 0 4px 0; font-weight: 600;">\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'^### (.*$)', r'<h3 style="margin: 10px 0 5px 0; font-weight: 600;">\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.*$)', r'<h2 style="margin: 12px 0 6px 0; font-weight: 600;">\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.*$)', r'<h1 style="margin: 14px 0 7px 0; font-weight: 600;">\1</h1>', text, flags=re.MULTILINE)

        # Convert bullet points
        text = re.sub(r'^[•\-\*] (.*)$', r'<p style="margin: 2px 0; padding-left: 16px;">• \1</p>', text, flags=re.MULTILINE)

        # Convert line breaks to HTML
        text = text.replace('\n', '<br>')

        return text

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