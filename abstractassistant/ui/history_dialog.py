"""
iPhone Messages-style history dialog for AbstractAssistant.

This module provides an authentic iPhone Messages UI for displaying chat history.
"""
import re
import time
from datetime import datetime
from typing import Dict, List, Callable, Optional
import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.nl2br import Nl2BrExtension
from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter

try:
    from PyQt6.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QGridLayout,
        QScrollArea,
        QWidget,
        QLabel,
        QFrame,
        QPushButton,
        QApplication,
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
    from PyQt6.QtGui import QFont, QCursor, QPixmap, QIcon
except ImportError:
    try:
        from PyQt5.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QHBoxLayout,
            QGridLayout,
            QScrollArea,
            QWidget,
            QLabel,
            QFrame,
            QPushButton,
            QApplication,
        )
        from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize
        from PyQt5.QtGui import QFont, QCursor, QPixmap, QIcon
    except ImportError:
        from PySide2.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QHBoxLayout,
            QGridLayout,
            QScrollArea,
            QWidget,
            QLabel,
            QFrame,
            QPushButton,
            QApplication,
        )
        from PySide2.QtCore import Qt, QTimer, Signal as pyqtSignal, QSize
        from PySide2.QtGui import QFont, QCursor, QPixmap, QIcon


class ClickableBubble(QFrame):
    """Clickable message bubble that copies content to clipboard and supports deletion."""

    clicked = pyqtSignal()
    delete_requested = pyqtSignal(int)  # Signal with message index
    selection_changed = pyqtSignal(int, bool)  # Signal with message index and selection state

    def __init__(self, content: str, is_user: bool, message_index: int, parent=None):
        super().__init__(parent)
        self.content = content
        self.is_user = is_user
        self.message_index = message_index
        self.is_selected = False
        self.selection_mode = False
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # Store original colors for animation
        if is_user:
            self.normal_bg = "#007AFF"
            self.clicked_bg = "#0066CC"
            self.selected_bg = "#FF3B30"  # Red for selection
        else:
            self.normal_bg = "#3a3a3c"
            self.clicked_bg = "#4a4a4c"
            self.selected_bg = "#FF3B30"  # Red for selection
        
        # Long press timer for selection mode
        self.long_press_timer = QTimer()
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self._start_selection_mode)
        self.press_start_time = None

    def mousePressEvent(self, event):
        """Handle mouse press with visual feedback and long press detection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_start_time = time.time()
            
            if self.selection_mode:
                # In selection mode, toggle selection
                self.toggle_selection()
            else:
                # Normal mode - start long press timer and apply clicked style
                self.long_press_timer.start(800)  # 800ms for long press
                self.setStyleSheet(f"""
                    QFrame {{
                        background: {self.clicked_bg};
                        border: none;
                        border-radius: 18px;
                        max-width: 490px;
                    }}
                """)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release - copy to clipboard, handle selection, and restore style."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Stop long press timer
            self.long_press_timer.stop()
            
            if self.selection_mode:
                # In selection mode, just restore style
                self._update_visual_state()
            else:
                # Check if this was a quick tap (not long press)
                if self.press_start_time and (time.time() - self.press_start_time) < 0.5:
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
                            max-width: 490px;
                        }}
                    """)

                    # Restore normal color after brief delay
                    QTimer.singleShot(200, self._restore_normal_style)

                    self.clicked.emit()
                else:
                    # Long press - restore style immediately
                    self._restore_normal_style()
        super().mouseReleaseEvent(event)

    def _start_selection_mode(self):
        """Start selection mode on long press."""
        self.selection_mode = True
        self.is_selected = True
        self._update_visual_state()
        self.selection_changed.emit(self.message_index, True)
        
        # Provide haptic-like feedback by briefly changing color
        self.setStyleSheet(f"""
            QFrame {{
                background: {self.selected_bg};
                border: 2px solid #FFFFFF;
                border-radius: 18px;
                max-width: 490px;
            }}
        """)
        
        # Add selection indicator
        QTimer.singleShot(100, self._update_visual_state)

    def toggle_selection(self):
        """Toggle selection state in selection mode."""
        self.is_selected = not self.is_selected
        self._update_selection_circle()
        self._update_visual_state()
        self.selection_changed.emit(self.message_index, self.is_selected)

    def set_selection_mode(self, enabled: bool):
        """Set selection mode state."""
        self.selection_mode = enabled
        if not enabled:
            self.is_selected = False
        
        # Show/hide selection circle
        if hasattr(self, 'selection_circle'):
            if enabled:
                self.selection_circle.show()
            else:
                self.selection_circle.hide()
        
        self._update_selection_circle()
        self._update_visual_state()

    def set_selected(self, selected: bool):
        """Set selection state."""
        self.is_selected = selected
        self._update_selection_circle()
        self._update_visual_state()

    def _update_selection_circle(self):
        """Update selection circle appearance."""
        if hasattr(self, 'selection_circle') and self.selection_mode:
            if self.is_selected:
                # Selected state - filled circle with checkmark
                self.selection_circle.setStyleSheet("""
                    QPushButton {
                        background: #007AFF;
                        border: 2px solid #007AFF;
                        border-radius: 11px;
                        margin: 0px;
                        padding: 0px;
                        color: white;
                        font-size: 12px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: #0066CC;
                        border: 2px solid #0066CC;
                    }
                """)
                self.selection_circle.setText("✓")
            else:
                # Unselected state - empty circle
                self.selection_circle.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: 2px solid rgba(255, 255, 255, 0.6);
                        border-radius: 11px;
                        margin: 0px;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        border: 2px solid rgba(255, 255, 255, 0.8);
                    }
                """)
                self.selection_circle.setText("")

    def _update_visual_state(self):
        """Update visual state based on selection - no visual changes to bubble itself."""
        # In authentic iPhone Messages, the bubble appearance doesn't change
        # Only the selection circle changes state - bubble stays the same
        self.setStyleSheet(f"""
            QFrame {{
                background: {self.normal_bg};
                border: none;
                border-radius: 18px;
                max-width: 490px;
            }}
        """)

    def _restore_normal_style(self):
        """Restore normal bubble style."""
        self.setStyleSheet(f"""
            QFrame {{
                background: {self.normal_bg};
                border: none;
                border-radius: 18px;
                max-width: 490px;
            }}
        """)


class SafeDialog(QDialog):
    """Dialog that only hides instead of closing to prevent app termination."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide_callback = None
        self.delete_callback = None
        self.selection_mode = False
        self.selected_messages = set()
        self.message_bubbles = []
        self.trash_button = None
        self.edit_button = None

    def set_hide_callback(self, callback):
        """Set callback to call when dialog is hidden."""
        self.hide_callback = callback

    def set_delete_callback(self, callback):
        """Set callback to call when messages are deleted."""
        self.delete_callback = callback

    def enter_selection_mode(self):
        """Enter selection mode for message deletion."""
        self.selection_mode = True
        self.selected_messages.clear()
        
        # Update all bubbles to selection mode
        for bubble in self.message_bubbles:
            bubble.set_selection_mode(True)
        
        # Update navigation bar
        self._update_navbar_for_selection_mode()

    def exit_selection_mode(self):
        """Exit selection mode."""
        self.selection_mode = False
        self.selected_messages.clear()
        
        # Update all bubbles to normal mode
        for bubble in self.message_bubbles:
            bubble.set_selection_mode(False)
        
        # Update navigation bar
        self._update_navbar_for_normal_mode()

    def _update_navbar_for_selection_mode(self):
        """Update navbar for selection mode."""
        if hasattr(self, 'edit_button'):
            self.edit_button.setText("Cancel")
            self.edit_button.clicked.disconnect()
            self.edit_button.clicked.connect(self.exit_selection_mode)
        
        # Hide trash button initially (will show when messages are selected)
        if hasattr(self, 'trash_button'):
            self.trash_button.hide()

    def _update_navbar_for_normal_mode(self):
        """Update navbar for normal mode."""
        if hasattr(self, 'edit_button'):
            self.edit_button.setText("Edit")
            self.edit_button.clicked.disconnect()
            self.edit_button.clicked.connect(self.enter_selection_mode)
        
        # Hide trash button
        if hasattr(self, 'trash_button'):
            self.trash_button.hide()

    def on_selection_changed(self, message_index: int, selected: bool):
        """Handle selection change from a bubble."""
        if selected:
            self.selected_messages.add(message_index)
        else:
            self.selected_messages.discard(message_index)
        
        # Show/hide trash button based on selection
        if hasattr(self, 'trash_button'):
            if len(self.selected_messages) > 0:
                self.trash_button.show()
            else:
                self.trash_button.hide()

    def delete_selected_messages(self):
        """Delete selected messages with iPhone-style bottom action sheet."""
        try:
            if not self.selected_messages or not self.delete_callback:
                return

            # Show iPhone-style bottom action sheet
            count = len(self.selected_messages)
            self._show_delete_action_sheet(count)

        except Exception as e:
            import traceback
            traceback.print_exc()

    def _show_delete_action_sheet(self, count: int):
        """Show iPhone-style bottom action sheet for deletion confirmation."""
        # Create overlay widget that covers the entire dialog
        overlay = QWidget(self)
        overlay.setStyleSheet("background: rgba(0, 0, 0, 0.4);")
        overlay.resize(self.size())
        overlay.move(0, 0)
        
        # Create action sheet container
        action_sheet = QWidget(overlay)
        action_sheet.setStyleSheet("""
            QWidget {
                background: #2C2C2E;
                border-radius: 13px;
                border: none;
            }
        """)
        
        # Layout for action sheet
        layout = QVBoxLayout(action_sheet)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        
        # Delete button (red, destructive)
        delete_btn = QPushButton(f"Delete {count} Message{'s' if count > 1 else ''}")
        delete_btn.setStyleSheet("""
            QPushButton {
                background: #FF3B30;
                color: white;
                border: none;
                padding: 16px;
                font-size: 17px;
                font-weight: 400;
                text-align: center;
            }
            QPushButton:hover {
                background: #D70015;
            }
        """)
        delete_btn.clicked.connect(lambda: self._confirm_deletion(overlay))
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #48484A;
                color: #007AFF;
                border: none;
                padding: 16px;
                font-size: 17px;
                font-weight: 600;
                text-align: center;
                border-radius: 13px;
                margin-top: 8px;
            }
            QPushButton:hover {
                background: #5A5A5C;
            }
        """)
        cancel_btn.clicked.connect(lambda: self._cancel_deletion(overlay))
        
        layout.addWidget(delete_btn)
        layout.addWidget(cancel_btn)
        
        # Position action sheet at bottom
        action_sheet.setFixedWidth(self.width() - 40)
        action_sheet.adjustSize()
        action_sheet.move(20, self.height() - action_sheet.height() - 20)
        
        # Show overlay and action sheet
        overlay.show()
        overlay.raise_()
        
        # Store reference for cleanup
        self.current_overlay = overlay

    def _confirm_deletion(self, overlay):
        """Confirm deletion and execute it."""
        try:
            # Hide overlay
            overlay.hide()
            overlay.deleteLater()
            self.current_overlay = None
            
            # Convert to sorted list for consistent deletion
            indices_to_delete = sorted(list(self.selected_messages), reverse=True)

            # Call the delete callback with error handling
            if self.delete_callback:
                self.delete_callback(indices_to_delete)

            # Exit selection mode after deletion
            self.exit_selection_mode()

        except Exception as e:
            import traceback
            traceback.print_exc()
            
            # Try to exit selection mode even if deletion failed
            try:
                self.exit_selection_mode()
            except:
                pass

    def _cancel_deletion(self, overlay):
        """Cancel deletion and hide action sheet."""
        overlay.hide()
        overlay.deleteLater()
        self.current_overlay = None

    def update_message_history(self, new_message_history: List[Dict]):
        """Update the dialog with new message history without closing it."""
        try:
            # Exit selection mode if active
            if self.selection_mode:
                self.exit_selection_mode()
            
            # Clear existing content completely using correct widget references
            if hasattr(self, 'messages_layout'):
                layout = self.messages_layout
                
                # Remove all widgets except the stretch at the end
                while layout.count() > 0:
                    child = layout.takeAt(0)
                    if child.widget():
                        widget = child.widget()
                        widget.setParent(None)
                        widget.deleteLater()
                
                # Force immediate processing of deleteLater calls
                from PyQt5.QtCore import QCoreApplication
                QCoreApplication.processEvents()
                
                # Recreate messages with new history
                if new_message_history:
                    # Re-add messages using the same method as original creation
                    iPhoneMessagesDialog._add_authentic_iphone_messages(layout, new_message_history, self)
                else:
                    # Add placeholder for empty state
                    placeholder = QLabel("No messages")
                    placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    placeholder.setStyleSheet("""
                        QLabel {
                            color: rgba(255, 255, 255, 0.5);
                            font-size: 16px;
                            padding: 40px;
                        }
                    """)
                    layout.addWidget(placeholder)
                
                # Re-add stretch to push messages to top
                layout.addStretch()
                
                # Force complete UI update
                if hasattr(self, 'messages_widget'):
                    self.messages_widget.adjustSize()
                    self.messages_widget.update()
                    self.messages_widget.repaint()
                
                if hasattr(self, 'scroll_area'):
                    self.scroll_area.update()
                    self.scroll_area.repaint()
                    # Scroll to bottom to show latest messages
                    QTimer.singleShot(100, lambda: self.scroll_area.verticalScrollBar().setValue(
                        self.scroll_area.verticalScrollBar().maximum()
                    ))
                
                # Update the entire dialog
                self.update()
                self.repaint()
                
            else:
                raise Exception("Dialog structure not found")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise  # Re-raise to trigger fallback in qt_bubble.py

    def _populate_messages(self, message_history: List[Dict]):
        """Populate the scroll area with message bubbles."""
        if not hasattr(self, 'scroll_content'):
            return
            
        layout = self.scroll_content.layout()
        if not layout:
            layout = QVBoxLayout(self.scroll_content)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(8)
        
        # Add messages as bubbles (only if there are messages)
        if message_history:
            for i, message in enumerate(message_history):
                if message.get('type') in ['user', 'assistant']:
                    bubble = ClickableBubble(
                        message.get('content', ''),
                        message.get('type') == 'user',
                        i,
                        self
                    )
                    layout.addWidget(bubble)
        else:
            # If no messages, add a placeholder
            placeholder = QLabel("No messages")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("""
                QLabel {
                    color: rgba(255, 255, 255, 0.5);
                    font-size: 16px;
                    padding: 40px;
                }
            """)
            layout.addWidget(placeholder)
        
        # Add stretch to push messages to top
        layout.addStretch()
        
        # Force layout update
        self.scroll_content.update()
        if hasattr(self, 'scroll_area'):
            self.scroll_area.update()


    def closeEvent(self, event):
        """Override close event to hide instead of close."""
        if self.selection_mode:
            self.exit_selection_mode()
        event.ignore()
        self.hide()
        if self.hide_callback:
            self.hide_callback()

    def reject(self):
        """Override reject to hide instead of close."""
        if self.selection_mode:
            self.exit_selection_mode()
        self.hide()
        if self.hide_callback:
            self.hide_callback()


class iPhoneMessagesDialog:
    """Create authentic iPhone Messages-style chat history dialog."""

    @staticmethod
    def create_dialog(message_history: List[Dict], parent=None, delete_callback: Optional[Callable] = None) -> QDialog:
        """Create AUTHENTIC iPhone Messages dialog with deletion support."""
        # Safety check for empty message history
        if not message_history:
            return None
        
        dialog = SafeDialog(parent)
        dialog.setWindowTitle("Messages")
        dialog.setModal(False)
        dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        dialog.resize(617, 553)  # ~15% smaller than the previous 726x650
        try:
            dialog.setWindowOpacity(0.97)
        except Exception:
            pass

        # Set delete callback
        if delete_callback:
            dialog.set_delete_callback(delete_callback)

        # Position dialog near right edge of screen like iPhone
        iPhoneMessagesDialog._position_dialog_right(dialog)

        # Main layout - zero margins like iPhone
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # iPhone navigation bar with delete button
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

        # Store references for updating
        dialog.scroll_area = scroll_area
        dialog.messages_widget = messages_widget
        dialog.messages_layout = messages_layout

        # Add messages with authentic iPhone styling and deletion support
        iPhoneMessagesDialog._add_authentic_iphone_messages(messages_layout, message_history, dialog)

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
    def _create_authentic_navbar(dialog: SafeDialog) -> QFrame:
        """Create AUTHENTIC iPhone Messages navigation bar with delete functionality."""
        navbar = QFrame()
        navbar.setFixedHeight(44)  # Compact header (about half the previous height)
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
        nav_layout.setContentsMargins(16, 0, 16, 0)

        # Back button
        back_btn = QPushButton("‹ Back")
        back_btn.clicked.connect(dialog.reject)
        back_btn.setStyleSheet("""
            QPushButton {
                color: #007AFF;
                font-size: 13px;
                font-weight: 400;
                background: transparent;
                border: none;
                text-align: left;
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
        """)
        nav_layout.addWidget(back_btn)

        nav_layout.addStretch()

        # Title - Messages
        title = QLabel("Messages")
        title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 13px;
                font-weight: 600;
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
        """)
        nav_layout.addWidget(title)

        nav_layout.addStretch()

        # Trash icon (initially hidden, appears when messages are selected)
        trash_btn = QPushButton("🗑️")
        trash_btn.setFixedSize(24, 24)
        trash_btn.clicked.connect(dialog.delete_selected_messages)
        trash_btn.setStyleSheet("""
            QPushButton {
                color: #FF3B30;
                font-size: 14px;
                background: transparent;
                border: none;
                text-align: center;
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
            QPushButton:hover {
                background: rgba(255, 59, 48, 0.1);
                border-radius: 12px;
            }
        """)
        trash_btn.hide()  # Initially hidden
        dialog.trash_button = trash_btn  # Store reference
        nav_layout.addWidget(trash_btn)

        # Delete button (Edit in iPhone style)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(dialog.enter_selection_mode)
        edit_btn.setStyleSheet("""
            QPushButton {
                color: #007AFF;
                font-size: 13px;
                font-weight: 400;
                background: transparent;
                border: none;
                text-align: right;
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
        """)
        dialog.edit_button = edit_btn  # Store reference
        nav_layout.addWidget(edit_btn)

        layout.addWidget(nav_frame)
        return navbar

    @staticmethod
    def _add_authentic_iphone_messages(layout: QVBoxLayout, message_history: List[Dict], dialog: SafeDialog):
        """Add messages with AUTHENTIC iPhone Messages styling and deletion support."""
        for index, msg in enumerate(message_history):
            message_type = msg.get('type', msg.get('role', 'unknown'))
            is_user = message_type in ['user', 'human']

            # Create authentic iPhone bubble with deletion support
            bubble_container = iPhoneMessagesDialog._create_authentic_iphone_bubble(msg, is_user, index, message_history, dialog)
            layout.addWidget(bubble_container)

            # Add spacing between messages (6px like iPhone)
            if index < len(message_history) - 1:
                spacer = QFrame()
                spacer.setFixedHeight(6)
                spacer.setStyleSheet("background: transparent;")
                layout.addWidget(spacer)

    @staticmethod
    def _create_authentic_iphone_bubble(msg: Dict, is_user: bool, index: int, message_history: List[Dict], dialog: SafeDialog) -> QFrame:
        """Create AUTHENTIC iPhone Messages bubble with deletion support."""
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

        # Create selection circle (initially hidden)
        selection_circle = QPushButton()
        selection_circle.setFixedSize(22, 22)
        selection_circle.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 2px solid rgba(255, 255, 255, 0.6);
                border-radius: 11px;
                margin: 0px;
                padding: 0px;
            }
            QPushButton:hover {
                border: 2px solid rgba(255, 255, 255, 0.8);
            }
        """)
        selection_circle.hide()  # Initially hidden
        
        # Create clickable bubble with deletion support
        bubble = ClickableBubble(msg['content'], is_user, index)
        bubble.selection_changed.connect(dialog.on_selection_changed)
        bubble.selection_circle = selection_circle  # Store reference
        dialog.message_bubbles.append(bubble)  # Track bubbles for selection mode
        
        # Connect selection circle click
        selection_circle.clicked.connect(bubble.toggle_selection)
        
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
                    max-width: 490px;
                }
            """)
            content_label.setStyleSheet("""
                QLabel {
                    background: transparent;
                    color: #FFFFFF;
                    font-size: 14px;
                    font-weight: 400;
                    line-height: 18px;
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                }
            """)
            # Right align - selection circle on the left of bubble (towards center)
            layout.addStretch()
            layout.addWidget(selection_circle, 0, Qt.AlignmentFlag.AlignCenter)
            layout.addSpacing(8)  # Small gap between circle and bubble
            layout.addWidget(bubble)
        else:
            # Received bubble: Light gray with black text
            bubble.setStyleSheet("""
                QFrame {
                    background: #3a3a3c;
                    border: none;
                    border-radius: 18px;
                    max-width: 490px;
                }
            """)
            content_label.setStyleSheet("""
                QLabel {
                    background: transparent;
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: 400;
                    line-height: 18px;
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                }
            """)
            # Left align - selection circle on the right of bubble (towards center)
            layout.addWidget(bubble)
            layout.addSpacing(8)  # Small gap between bubble and circle
            layout.addWidget(selection_circle, 0, Qt.AlignmentFlag.AlignCenter)
            layout.addStretch()

        bubble_layout.addWidget(content_label)
        
        # Add file attachment indicator if files were attached to this message
        attached_files = msg.get('attached_files', [])
        if attached_files:
            file_indicator = QLabel(f"📎 {len(attached_files)} file{'s' if len(attached_files) > 1 else ''}")
            file_indicator.setStyleSheet("""
                QLabel {
                    background: transparent;
                    color: rgba(255, 255, 255, 0.7);
                    font-size: 11px;
                    font-weight: 500;
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                    padding: 2px 0px;
                    margin: 0px;
                }
            """)
            bubble_layout.addWidget(file_indicator)

        # Images: render thumbnails under the message when present.
        image_thumbnails = msg.get("image_thumbnails")
        if not isinstance(image_thumbnails, list):
            image_thumbnails = []
        thumbs: List[Dict] = [dict(x) for x in image_thumbnails if isinstance(x, dict)]
        thumb_targets = {
            str(x.get("target") or "").strip()
            for x in thumbs
            if isinstance(x, dict) and str(x.get("target") or "").strip()
        }

        # Add a compact tool execution summary (attached to assistant messages).
        tool_summary = msg.get("tool_summary")
        tool_links = msg.get("tool_links")
        if not isinstance(tool_links, list):
            tool_links = []
        # Don't duplicate image resources as both chips and thumbnails.
        if thumb_targets:
            tool_links = [
                link for link in tool_links
                if isinstance(link, dict) and str(link.get("target") or "").strip() not in thumb_targets
            ]
        tool_summary_text = str(tool_summary or "").strip()
        if tool_summary_text or tool_links:
            tools_container = QFrame()
            tools_container.setStyleSheet("QFrame { background: transparent; border: none; }")
            tools_layout = QVBoxLayout(tools_container)
            tools_layout.setContentsMargins(0, 2, 0, 0)
            tools_layout.setSpacing(4)

            if tool_summary_text:
                tools_label = QLabel(tool_summary_text)
                tools_label.setWordWrap(True)
                tools_label.setStyleSheet("""
                    QLabel {
                        background: transparent;
                        color: rgba(255, 255, 255, 0.65);
                        font-size: 11px;
                        font-weight: 500;
                        font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                        padding: 0px;
                        margin: 0px;
                    }
                """)
                tools_layout.addWidget(tools_label)

            if tool_links:
                max_chips = 6
                chips_per_row = 3
                shown = tool_links[:max_chips]
                extra = max(0, len(tool_links) - len(shown))

                links_frame = QFrame()
                links_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
                links_layout = QGridLayout(links_frame)
                links_layout.setContentsMargins(0, 0, 0, 0)
                links_layout.setHorizontalSpacing(6)
                links_layout.setVerticalSpacing(6)

                def _mk_chip(link: Dict) -> QPushButton:
                    kind = str(link.get("kind") or "url")
                    target = str(link.get("target") or "").strip()
                    label = str(link.get("label") or target).strip() or target
                    icon = "🌐" if kind == "url" else "📄"
                    btn = QPushButton(f"{icon} {label}")
                    btn.setToolTip(target)
                    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    btn.setStyleSheet("""
                        QPushButton {
                            background: rgba(255, 255, 255, 0.08);
                            border: 1px solid rgba(255, 255, 255, 0.14);
                            border-radius: 10px;
                            padding: 2px 8px;
                            font-size: 11px;
                            color: rgba(255, 255, 255, 0.85);
                            font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                            text-align: left;
                        }
                        QPushButton:hover {
                            background: rgba(255, 255, 255, 0.12);
                            border: 1px solid rgba(0, 122, 255, 0.6);
                            color: rgba(255, 255, 255, 0.95);
                        }
                    """)
                    btn.clicked.connect(
                        lambda _checked=False, k=kind, t=target: iPhoneMessagesDialog._open_tool_link(k, t)
                    )
                    return btn

                for idx, link in enumerate(shown):
                    if not isinstance(link, dict):
                        continue
                    row = idx // chips_per_row
                    col = idx % chips_per_row
                    links_layout.addWidget(_mk_chip(link), row, col)

                if extra > 0:
                    more_btn = QPushButton(f"+{extra}")
                    more_btn.setToolTip("Show all tool links")
                    more_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    more_btn.setStyleSheet("""
                        QPushButton {
                            background: rgba(255, 255, 255, 0.06);
                            border: 1px solid rgba(255, 255, 255, 0.12);
                            border-radius: 10px;
                            padding: 2px 8px;
                            font-size: 11px;
                            color: rgba(255, 255, 255, 0.75);
                            font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                        }
                        QPushButton:hover {
                            background: rgba(255, 255, 255, 0.10);
                            border: 1px solid rgba(0, 122, 255, 0.45);
                            color: rgba(255, 255, 255, 0.9);
                        }
                    """)
                    more_btn.clicked.connect(lambda: iPhoneMessagesDialog._show_tool_links_dialog(tool_links, parent=dialog))
                    row = len(shown) // chips_per_row
                    col = len(shown) % chips_per_row
                    links_layout.addWidget(more_btn, row, col)

                tools_layout.addWidget(links_frame)

            bubble_layout.addWidget(tools_container)

        if thumbs:
            thumb_container = QFrame()
            thumb_container.setStyleSheet("QFrame { background: transparent; border: none; }")
            thumb_layout = QHBoxLayout(thumb_container)
            thumb_layout.setContentsMargins(0, 2, 0, 0)
            thumb_layout.setSpacing(6)

            max_thumbs = 3
            shown_thumbs = thumbs[:max_thumbs]
            for th in shown_thumbs:
                kind = str(th.get("kind") or "url")
                target = str(th.get("target") or "").strip()
                label = str(th.get("label") or target).strip()
                if not target:
                    continue
                thumb_layout.addWidget(
                    iPhoneMessagesDialog._make_thumbnail_button(
                        kind=kind,
                        target=target,
                        label=label,
                        parent=dialog,
                    )
                )

            extra_thumbs = max(0, len(thumbs) - len(shown_thumbs))
            if extra_thumbs > 0:
                more_btn = QPushButton(f"+{extra_thumbs}")
                more_btn.setToolTip("Show all images")
                more_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                more_btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.06);
                        border: 1px solid rgba(255, 255, 255, 0.12);
                        border-radius: 12px;
                        padding: 2px 10px;
                        font-size: 12px;
                        color: rgba(255, 255, 255, 0.75);
                        font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.10);
                        border: 1px solid rgba(0, 122, 255, 0.45);
                        color: rgba(255, 255, 255, 0.9);
                    }
                """)
                more_btn.clicked.connect(lambda: iPhoneMessagesDialog._show_tool_links_dialog(thumbs, parent=dialog))
                thumb_layout.addWidget(more_btn)

            bubble_layout.addWidget(thumb_container)
        
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
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
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
    def _make_thumbnail_button(*, kind: str, target: str, label: str, parent=None) -> QPushButton:
        """Create a clickable thumbnail button for a local file or remote image URL."""
        k = str(kind or "").strip().lower()
        t = str(target or "").strip()
        lbl = str(label or "").strip()

        btn = QPushButton("🖼")
        btn.setToolTip(t or lbl)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        thumb_w, thumb_h = 150, 94
        btn.setFixedSize(thumb_w, thumb_h)
        btn.setIconSize(QSize(thumb_w - 6, thumb_h - 6))
        btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 12px;
                color: rgba(255, 255, 255, 0.75);
                font-size: 20px;
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(0, 122, 255, 0.6);
                color: rgba(255, 255, 255, 0.9);
            }
        """)
        btn.clicked.connect(lambda _checked=False: iPhoneMessagesDialog._open_tool_link(k, t))

        def _apply_pixmap(pix: QPixmap) -> None:
            if pix.isNull():
                return
            try:
                try:
                    aspect = Qt.AspectRatioMode.KeepAspectRatio
                    transform = Qt.TransformationMode.SmoothTransformation
                except Exception:
                    aspect = Qt.KeepAspectRatio  # type: ignore[attr-defined]
                    transform = Qt.SmoothTransformation  # type: ignore[attr-defined]
                scaled = pix.scaled(thumb_w - 6, thumb_h - 6, aspect, transform)
            except Exception:
                scaled = pix
            btn.setText("")
            btn.setIcon(QIcon(scaled))

        # Local file thumbnail
        if k == "file" and t:
            try:
                pix = QPixmap(t)
                if not pix.isNull():
                    _apply_pixmap(pix)
            except Exception:
                pass
            return btn

        # Remote image thumbnail (download + cache).
        if k != "url" or not t:
            return btn

        cache_path = iPhoneMessagesDialog._thumbnail_cache_path(t)
        try:
            if cache_path is not None and cache_path.exists():
                data = cache_path.read_bytes()
                pix = QPixmap()
                if data and pix.loadFromData(data):
                    _apply_pixmap(pix)
                    return btn
        except Exception:
            pass

        import threading

        def _download() -> None:
            data = iPhoneMessagesDialog._fetch_image_bytes(t)
            if not data:
                return

            def _set_on_ui() -> None:
                try:
                    pix = QPixmap()
                    if pix.loadFromData(data):
                        _apply_pixmap(pix)
                except Exception:
                    return

            try:
                QTimer.singleShot(0, _set_on_ui)
            except Exception:
                _set_on_ui()

        threading.Thread(target=_download, daemon=True).start()
        return btn

    @staticmethod
    def _thumbnail_cache_path(url: str):
        """Return a filesystem cache path for a remote image URL (under ~/.abstractassistant/cache/images/)."""
        u = str(url or "").strip()
        if not u:
            return None
        try:
            import hashlib
            from pathlib import Path
            from urllib.parse import urlparse

            parsed = urlparse(u)
            suffix = Path(parsed.path or "").suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}:
                suffix = ".img"

            h = hashlib.sha256(u.encode("utf-8")).hexdigest()[:32]
            base = Path.home() / ".abstractassistant" / "cache" / "images"
            base.mkdir(parents=True, exist_ok=True)
            return base / f"{h}{suffix}"
        except Exception:
            return None

    @staticmethod
    def _fetch_image_bytes(url: str, *, timeout_s: float = 4.0, max_bytes: int = 4_000_000) -> Optional[bytes]:
        """Download an image URL (bounded) and cache it; returns bytes or None."""
        u = str(url or "").strip()
        if not u:
            return None

        cache_path = iPhoneMessagesDialog._thumbnail_cache_path(u)
        if cache_path is not None:
            try:
                if cache_path.exists() and cache_path.stat().st_size > 0:
                    return cache_path.read_bytes()
            except Exception:
                pass

        try:
            import urllib.request

            req = urllib.request.Request(
                u,
                headers={
                    "User-Agent": "AbstractAssistant/1.0",
                    "Accept": "image/*,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
                ct = str(resp.headers.get("Content-Type") or "").lower()
                if ct and not ct.startswith("image/"):
                    return None
                try:
                    clen = resp.headers.get("Content-Length")
                    if clen is not None and int(clen) > int(max_bytes):
                        return None
                except Exception:
                    pass
                data = resp.read(int(max_bytes))
        except Exception:
            return None

        if not data:
            return None

        if cache_path is not None:
            try:
                tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
                tmp.write_bytes(data)
                tmp.replace(cache_path)
            except Exception:
                pass
        return data

    @staticmethod
    def _open_tool_link(kind: str, target: str) -> None:
        """Open a tool-produced resource (URL or file path) using the OS default handler."""
        k = str(kind or "").strip().lower()
        t = str(target or "").strip()
        if not t:
            return

        try:
            if k == "url":
                import webbrowser

                webbrowser.open(t)
                return

            # Default: treat as a file path (best-effort).
            from urllib.parse import unquote, urlparse

            if t.startswith("file://"):
                parsed = urlparse(t)
                t = unquote(parsed.path)

            import os
            import sys
            import subprocess

            if sys.platform == "darwin":
                subprocess.Popen(["open", t])
            elif sys.platform.startswith("win"):
                os.startfile(t)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", t])
        except Exception:
            return

    @staticmethod
    def _show_tool_links_dialog(tool_links: List[Dict], parent=None) -> None:
        """Show a small dialog listing all tool links for quick access."""
        links: List[Dict] = [dict(x) for x in (tool_links or []) if isinstance(x, dict)]
        if not links:
            return

        dlg = QDialog(parent)
        dlg.setWindowTitle("Tool Links")
        dlg.setModal(True)
        dlg.resize(560, 320)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        for link in links:
            kind = str(link.get("kind") or "url")
            target = str(link.get("target") or "").strip()
            label = str(link.get("label") or target).strip() or target
            icon = "🌐" if kind == "url" else "📄"
            btn = QPushButton(f"{icon} {label}")
            btn.setToolTip(target)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    border-radius: 10px;
                    padding: 6px 10px;
                    font-size: 12px;
                    color: rgba(255, 255, 255, 0.9);
                    font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
                    text-align: left;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.12);
                    border: 1px solid rgba(0, 122, 255, 0.6);
                }
            """)
            btn.clicked.connect(lambda _checked=False, k=kind, t=target: iPhoneMessagesDialog._open_tool_link(k, t))
            layout.addWidget(btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 12px;
                padding: 8px 12px;
                font-size: 12px;
                color: rgba(255, 255, 255, 0.9);
                font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.14);
                border: 1px solid rgba(0, 122, 255, 0.6);
            }
        """)
        layout.addWidget(close_btn)

        dlg.exec()

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
