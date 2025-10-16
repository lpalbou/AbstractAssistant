"""
Toast Notification Manager for AbstractAssistant.

Handles elegant toast notifications that appear in the top-right corner,
with markdown rendering and copy-to-clipboard functionality.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import customtkinter as ctk
from typing import Optional, List
import threading
import time
import pyperclip
import markdown
from html.parser import HTMLParser


class MarkdownRenderer(HTMLParser):
    """Simple markdown to plain text renderer for display."""
    
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.in_code = False
        self.in_bold = False
        
    def handle_starttag(self, tag, attrs):
        if tag in ['code', 'pre']:
            self.in_code = True
        elif tag in ['b', 'strong']:
            self.in_bold = True
    
    def handle_endtag(self, tag):
        if tag in ['code', 'pre']:
            self.in_code = False
        elif tag in ['b', 'strong']:
            self.in_bold = False
        elif tag in ['p', 'br']:
            self.text_parts.append('\n')
    
    def handle_data(self, data):
        self.text_parts.append(data)
    
    def get_text(self):
        return ''.join(self.text_parts)


class ToastNotification:
    """Individual toast notification window."""
    
    def __init__(self, message: str, is_error: bool = False, auto_hide_delay: int = 5):
        """Initialize a toast notification.
        
        Args:
            message: Message content (supports markdown)
            is_error: Whether this is an error notification
            auto_hide_delay: Seconds before auto-hiding (0 = no auto-hide)
        """
        self.message = message
        self.is_error = is_error
        self.auto_hide_delay = auto_hide_delay
        
        # Window state
        self.window: Optional[ctk.CTkToplevel] = None
        self.is_expanded = False
        self.is_visible = False
        
        # Dimensions
        self.collapsed_width = 300
        self.collapsed_height = 120
        self.expanded_width = 500
        self.expanded_height = 400
        
        # Create window
        self._create_window()
        
        # Auto-hide timer
        if auto_hide_delay > 0:
            threading.Timer(auto_hide_delay, self.hide).start()
    
    def _create_window(self):
        """Create the toast notification window."""
        # Create toplevel window
        self.window = ctk.CTkToplevel()
        self.window.title("AbstractAssistant")
        
        # Configure window
        self.window.attributes('-topmost', True)
        self.window.resizable(False, False)
        
        # Position in top-right corner
        screen_width = self.window.winfo_screenwidth()
        x = screen_width - self.collapsed_width - 20
        y = 50
        
        self.window.geometry(f"{self.collapsed_width}x{self.collapsed_height}+{x}+{y}")
        
        # Configure colors based on type
        if self.is_error:
            self.window.configure(fg_color=("gray95", "gray15"))
            accent_color = "red"
        else:
            self.window.configure(fg_color=("gray95", "gray10"))
            accent_color = "blue"
        
        # Bind close event
        self.window.protocol("WM_DELETE_WINDOW", self.hide)
        
        # Create UI in collapsed mode
        self._create_collapsed_ui(accent_color)
        
        self.is_visible = True
    
    def _create_collapsed_ui(self, accent_color: str):
        """Create the collapsed (preview) UI."""
        # Main frame
        main_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Header with icon and title
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 8))
        
        # Status icon
        icon_text = "⚠️" if self.is_error else "🤖"
        icon_label = ctk.CTkLabel(
            header_frame,
            text=icon_text,
            font=ctk.CTkFont(size=16)
        )
        icon_label.pack(side="left")
        
        # Title
        title_text = "Error" if self.is_error else "Response Ready"
        title_label = ctk.CTkLabel(
            header_frame,
            text=title_text,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title_label.pack(side="left", padx=(8, 0))
        
        # Close button
        close_button = ctk.CTkButton(
            header_frame,
            text="×",
            width=24,
            height=24,
            command=self.hide,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="transparent",
            text_color="gray60",
            hover_color="gray30"
        )
        close_button.pack(side="right")
        
        # Preview text (first few lines)
        preview_text = self._get_preview_text()
        preview_label = ctk.CTkLabel(
            main_frame,
            text=preview_text,
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="nw"
        )
        preview_label.pack(fill="both", expand=True, pady=(0, 8))
        
        # Action buttons
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x")
        
        # Expand button
        expand_button = ctk.CTkButton(
            button_frame,
            text="View Full",
            command=self.expand,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=accent_color
        )
        expand_button.pack(side="left", padx=(0, 5))
        
        # Copy button
        copy_button = ctk.CTkButton(
            button_frame,
            text="Copy",
            command=self.copy_to_clipboard,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="gray50"
        )
        copy_button.pack(side="right")
    
    def _create_expanded_ui(self, accent_color: str):
        """Create the expanded (full) UI."""
        # Clear existing content
        for widget in self.window.winfo_children():
            widget.destroy()
        
        # Main frame with scrolling
        main_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Header
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))
        
        # Title
        title_text = "Error Details" if self.is_error else "AI Response"
        title_label = ctk.CTkLabel(
            header_frame,
            text=title_text,
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(side="left")
        
        # Close button
        close_button = ctk.CTkButton(
            header_frame,
            text="×",
            width=28,
            height=28,
            command=self.hide,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="transparent",
            text_color="gray60",
            hover_color="gray30"
        )
        close_button.pack(side="right")
        
        # Content area with scrolling
        content_frame = ctk.CTkScrollableFrame(main_frame)
        content_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Render markdown content
        self._render_markdown_content(content_frame)
        
        # Action buttons
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x")
        
        # Collapse button
        collapse_button = ctk.CTkButton(
            button_frame,
            text="Collapse",
            command=self.collapse,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="gray50"
        )
        collapse_button.pack(side="left", padx=(0, 10))
        
        # Copy button
        copy_button = ctk.CTkButton(
            button_frame,
            text="Copy to Clipboard",
            command=self.copy_to_clipboard,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=accent_color
        )
        copy_button.pack(side="right")
    
    def _get_preview_text(self) -> str:
        """Get preview text (first few lines)."""
        lines = self.message.split('\n')
        preview_lines = lines[:3]  # First 3 lines
        
        preview = '\n'.join(preview_lines)
        if len(lines) > 3:
            preview += "\n..."
        
        # Limit length
        if len(preview) > 150:
            preview = preview[:147] + "..."
        
        return preview
    
    def _render_markdown_content(self, parent):
        """Render markdown content in the parent frame."""
        # For now, use simple text rendering
        # TODO: Implement proper markdown rendering with formatting
        
        text_widget = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(size=13),
            wrap="word"
        )
        text_widget.pack(fill="both", expand=True)
        
        # Insert content
        text_widget.insert("1.0", self.message)
        text_widget.configure(state="disabled")  # Read-only
    
    def expand(self):
        """Expand the toast to full view."""
        if not self.is_expanded:
            self.is_expanded = True
            
            # Update window size and position
            screen_width = self.window.winfo_screenwidth()
            x = screen_width - self.expanded_width - 20
            y = 50
            
            self.window.geometry(f"{self.expanded_width}x{self.expanded_height}+{x}+{y}")
            self.window.resizable(True, True)
            
            # Recreate UI
            accent_color = "red" if self.is_error else "blue"
            self._create_expanded_ui(accent_color)
    
    def collapse(self):
        """Collapse the toast to preview mode."""
        if self.is_expanded:
            self.is_expanded = False
            
            # Update window size
            screen_width = self.window.winfo_screenwidth()
            x = screen_width - self.collapsed_width - 20
            y = 50
            
            self.window.geometry(f"{self.collapsed_width}x{self.collapsed_height}+{x}+{y}")
            self.window.resizable(False, False)
            
            # Recreate UI
            accent_color = "red" if self.is_error else "blue"
            self._create_collapsed_ui(accent_color)
    
    def copy_to_clipboard(self):
        """Copy message content to clipboard."""
        try:
            pyperclip.copy(self.message)
            
            # Show brief feedback
            if hasattr(self, 'copy_button'):
                original_text = self.copy_button.cget("text")
                self.copy_button.configure(text="Copied!")
                
                def reset_button():
                    time.sleep(1)
                    if self.window and self.window.winfo_exists():
                        self.copy_button.configure(text=original_text)
                
                threading.Thread(target=reset_button, daemon=True).start()
        
        except Exception as e:
            print(f"Failed to copy to clipboard: {e}")
    
    def hide(self):
        """Hide and destroy the toast notification."""
        if self.window and self.is_visible:
            self.window.destroy()
            self.is_visible = False


class ToastManager:
    """Manages toast notifications for the application."""
    
    def __init__(self, config=None):
        """Initialize the toast manager.
        
        Args:
            config: Configuration object
        """
        # Import config here to avoid circular imports
        if config is None:
            from ..config import Config
            config = Config.default()
        self.config = config
        
        self.active_toasts: List[ToastNotification] = []
        
        # Configure CustomTkinter for toasts
        ctk.set_appearance_mode(self.config.ui.theme)
    
    def show_response(self, message: str, auto_hide_delay: int = None):
        """Show a response toast notification.
        
        Args:
            message: Response message content
            auto_hide_delay: Seconds before auto-hiding (uses config default if None)
        """
        if auto_hide_delay is None:
            auto_hide_delay = self.config.ui.auto_hide_delay
            
        toast = ToastNotification(
            message=message,
            is_error=False,
            auto_hide_delay=auto_hide_delay
        )
        
        self.active_toasts.append(toast)
        self._cleanup_hidden_toasts()
    
    def show_error(self, error_message: str, auto_hide_delay: int = 10):
        """Show an error toast notification.
        
        Args:
            error_message: Error message content
            auto_hide_delay: Seconds before auto-hiding
        """
        toast = ToastNotification(
            message=error_message,
            is_error=True,
            auto_hide_delay=auto_hide_delay
        )
        
        self.active_toasts.append(toast)
        self._cleanup_hidden_toasts()
    
    def _cleanup_hidden_toasts(self):
        """Remove hidden toasts from active list."""
        self.active_toasts = [
            toast for toast in self.active_toasts
            if toast.is_visible
        ]
    
    def hide_all(self):
        """Hide all active toast notifications."""
        for toast in self.active_toasts:
            toast.hide()
        self.active_toasts.clear()
    
    def cleanup(self):
        """Clean up all toast notifications."""
        self.hide_all()
