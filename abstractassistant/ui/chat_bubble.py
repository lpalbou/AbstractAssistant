"""
Chat Bubble UI for AbstractAssistant.

A modern, glassy chat interface that appears as a floating bubble,
taking approximately 1/6th of the screen space with elegant design.
"""

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from typing import Callable, Optional
import threading

from ..core.llm_manager import LLMManager


class ChatBubble:
    """Modern chat bubble interface with glassy design."""
    
    def __init__(self, llm_manager: LLMManager, on_close: Callable, on_send: Callable, config=None):
        """Initialize the chat bubble.
        
        Args:
            llm_manager: LLM manager instance
            on_close: Callback when bubble is closed
            on_send: Callback when message is sent (message, provider, model)
            config: Configuration object
        """
        self.llm_manager = llm_manager
        self.on_close = on_close
        self.on_send = on_send
        
        # Import config here to avoid circular imports
        if config is None:
            from ..config import Config
            config = Config.default()
        self.config = config
        
        # Window state
        self.window: Optional[ctk.CTk] = None
        self.is_visible = False
        self.is_sending = False
        
        # UI components
        self.text_input: Optional[ctk.CTkTextbox] = None
        self.provider_dropdown: Optional[ctk.CTkComboBox] = None
        self.model_dropdown: Optional[ctk.CTkComboBox] = None
        self.send_button: Optional[ctk.CTkButton] = None
        self.status_label: Optional[ctk.CTkLabel] = None
        self.token_label: Optional[ctk.CTkLabel] = None
        
        # Configure CustomTkinter appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
    
    def create_window(self):
        """Create the chat bubble window."""
        if self.window is not None:
            return
        
        # Create main window
        self.window = ctk.CTk()
        self.window.title("AbstractAssistant")
        
        # Calculate size based on configuration
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        
        width = int(screen_width * self.config.ui.bubble_size_ratio)
        height = int(screen_height / 4)  # Slightly taller for better UX
        
        # Position in top-right area (near menu bar)
        x = screen_width - width - 50
        y = 50
        
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        
        # Window properties for modern look
        if self.config.ui.always_on_top:
            self.window.attributes('-topmost', True)  # Always on top
        self.window.resizable(False, False)
        
        # Configure window style
        self.window.configure(fg_color=("gray95", "gray10"))
        
        # Bind close event
        self.window.protocol("WM_DELETE_WINDOW", self.hide)
        
        # Create UI elements
        self._create_ui_elements()
        
        # Update initial state
        self._update_provider_models()
        self._update_status_display()
    
    def _create_ui_elements(self):
        """Create all UI elements with modern styling."""
        # Main container with padding
        main_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Text input area (takes most space)
        input_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        input_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Input label
        input_label = ctk.CTkLabel(
            input_frame,
            text="What can I help you with?",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        input_label.pack(anchor="w", pady=(0, 5))
        
        # Text input with modern styling
        self.text_input = ctk.CTkTextbox(
            input_frame,
            height=120,
            font=ctk.CTkFont(size=13),
            wrap="word",
            corner_radius=10
        )
        self.text_input.pack(fill="both", expand=True)
        
        # Bind keyboard shortcuts for message sending
        # Enter = send message, Shift+Enter = new line
        self.text_input.bind("<Return>", self._handle_enter_key)
        self.text_input.bind("<KP_Enter>", self._handle_enter_key)  # Numpad Enter
        
        # Controls frame
        controls_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        controls_frame.pack(fill="x", pady=(0, 10))
        
        # Provider and model selection
        selection_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        selection_frame.pack(fill="x", pady=(0, 8))
        
        # Provider dropdown
        provider_frame = ctk.CTkFrame(selection_frame, fg_color="transparent")
        provider_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkLabel(
            provider_frame,
            text="Provider:",
            font=ctk.CTkFont(size=11)
        ).pack(anchor="w")
        
        providers = list(self.llm_manager.get_providers().keys())
        self.provider_dropdown = ctk.CTkComboBox(
            provider_frame,
            values=[self.llm_manager.get_providers()[p].display_name for p in providers],
            command=self._on_provider_changed,
            height=28,
            font=ctk.CTkFont(size=11)
        )
        self.provider_dropdown.pack(fill="x")
        
        # Model dropdown
        model_frame = ctk.CTkFrame(selection_frame, fg_color="transparent")
        model_frame.pack(side="right", fill="x", expand=True, padx=(5, 0))
        
        ctk.CTkLabel(
            model_frame,
            text="Model:",
            font=ctk.CTkFont(size=11)
        ).pack(anchor="w")
        
        self.model_dropdown = ctk.CTkComboBox(
            model_frame,
            values=[],
            command=self._on_model_changed,
            height=28,
            font=ctk.CTkFont(size=11)
        )
        self.model_dropdown.pack(fill="x")
        
        # Status and token info
        info_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        info_frame.pack(fill="x", pady=(0, 8))
        
        self.token_label = ctk.CTkLabel(
            info_frame,
            text="0 / 128k tokens",
            font=ctk.CTkFont(size=10),
            text_color="gray60"
        )
        self.token_label.pack(side="left")
        
        self.status_label = ctk.CTkLabel(
            info_frame,
            text="● Ready",
            font=ctk.CTkFont(size=10),
            text_color="green"
        )
        self.status_label.pack(side="right")
        
        # Send button with modern styling
        self.send_button = ctk.CTkButton(
            controls_frame,
            text="Send Message",
            command=self._send_message,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8
        )
        self.send_button.pack(fill="x")
    
    def _on_provider_changed(self, provider_display_name: str):
        """Handle provider selection change."""
        # Find provider key by display name
        for key, info in self.llm_manager.get_providers().items():
            if info.display_name == provider_display_name:
                self.llm_manager.set_provider(key)
                self._update_provider_models()
                self._update_status_display()
                break
    
    def _on_model_changed(self, model: str):
        """Handle model selection change."""
        self.llm_manager.set_model(model)
        self._update_status_display()
    
    def _update_provider_models(self):
        """Update model dropdown based on selected provider."""
        if self.model_dropdown is None:
            return
        
        models = self.llm_manager.get_models(self.llm_manager.current_provider)
        self.model_dropdown.configure(values=models)
        
        # Set current model
        if self.llm_manager.current_model in models:
            self.model_dropdown.set(self.llm_manager.current_model)
        elif models:
            self.model_dropdown.set(models[0])
    
    def _update_status_display(self):
        """Update status and token information display."""
        if self.status_label is None or self.token_label is None:
            return
        
        status_info = self.llm_manager.get_status_info()
        token_usage = self.llm_manager.get_token_usage()
        
        # Update token display
        current_tokens = token_usage.current_session
        max_tokens = token_usage.max_context
        
        if max_tokens >= 1000:
            max_display = f"{max_tokens // 1000}k"
        else:
            max_display = str(max_tokens)
        
        self.token_label.configure(text=f"{current_tokens} / {max_display} tokens")
        
        # Update status display
        status = status_info.get("status", "ready")
        status_colors = {
            "ready": "green",
            "generating": "orange",
            "executing": "red",
            "error": "red"
        }
        
        status_text = {
            "ready": "● Ready",
            "generating": "● Generating...",
            "executing": "● Executing...",
            "error": "● Error"
        }
        
        self.status_label.configure(
            text=status_text.get(status, "● Unknown"),
            text_color=status_colors.get(status, "gray")
        )
    
    def _handle_enter_key(self, event):
        """Handle Enter key press in text input."""
        # Check if Shift is held down
        if event.state & 0x1:  # Shift modifier
            # Shift+Enter: Allow default behavior (new line)
            return None
        else:
            # Plain Enter: Send message
            self._send_message()
            return "break"  # Prevent default behavior
    
    def _send_message(self):
        """Send the current message."""
        if self.is_sending or self.text_input is None:
            return
        
        message = self.text_input.get("1.0", "end-1c").strip()
        if not message:
            return
        
        # Get current provider and model
        provider = self.llm_manager.current_provider
        model = self.llm_manager.current_model
        
        # Clear input
        self.text_input.delete("1.0", "end")
        
        # Update UI state
        self.is_sending = True
        self.send_button.configure(text="Cancel", fg_color="red")
        
        # Call send callback
        self.on_send(message, provider, model)
    
    def update_status(self, status: str):
        """Update the status display."""
        if status == "ready":
            self.is_sending = False
            if self.send_button:
                self.send_button.configure(text="Send Message", fg_color=None)
        
        # Update status display
        self._update_status_display()
    
    def show(self):
        """Show the chat bubble."""
        if not self.is_visible:
            if self.window is None:
                self.create_window()
            
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()
            
            # Focus on text input
            if self.text_input:
                self.text_input.focus_set()
            
            self.is_visible = True
    
    def hide(self):
        """Hide the chat bubble."""
        if self.is_visible and self.window:
            self.window.withdraw()
            self.is_visible = False
            self.on_close()
    
    def destroy(self):
        """Destroy the chat bubble window."""
        if self.window:
            self.window.destroy()
            self.window = None
        self.is_visible = False
