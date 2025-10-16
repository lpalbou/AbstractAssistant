"""
Modern chat bubble window using webview for cross-platform compatibility.

This module creates a small, positioned window that displays the chat bubble
interface using HTML/CSS/JS for a modern, responsive design.
"""

import json
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional, Callable
import logging

try:
    import webview
    WEBVIEW_AVAILABLE = True
except ImportError:
    WEBVIEW_AVAILABLE = False
    print("Warning: pywebview not available. Install with: pip install pywebview")

try:
    import tkinter as tk
    from tkinter import messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False


class BubbleWindow:
    """Modern chat bubble window with webview."""
    
    def __init__(self, llm_manager, config=None, debug: bool = False):
        """Initialize the bubble window.
        
        Args:
            llm_manager: LLM manager instance
            config: Configuration object
            debug: Enable debug mode
        """
        self.llm_manager = llm_manager
        self.config = config
        self.debug = debug
        
        # Window state
        self.window: Optional[webview.Window] = None
        self.is_visible = False
        self.api = None
        
        # Callbacks
        self.on_response_callback: Optional[Callable] = None
        self.on_error_callback: Optional[Callable] = None
        
        # Paths
        self.web_dir = Path(__file__).parent.parent.parent / "web"
        self.bubble_html = self.web_dir / "bubble.html"
        
        if debug:
            logging.basicConfig(level=logging.DEBUG)
            self.logger = logging.getLogger(__name__)
        else:
            self.logger = logging.getLogger(__name__)
    
    def create_window(self):
        """Create the webview window."""
        if not WEBVIEW_AVAILABLE:
            self.logger.error("pywebview not available. Falling back to browser.")
            self._fallback_to_browser()
            return
        
        try:
            # Create API for communication between JS and Python
            self.api = BubbleAPI(self.llm_manager, self)
            
            # Calculate window size (approximately 1/6th of screen)
            import tkinter as tk
            root = tk.Tk()
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            root.destroy()
            
            # Bubble dimensions
            bubble_width = min(400, int(screen_width * 0.25))
            bubble_height = min(300, int(screen_height * 0.3))
            
            # Position near top-right (system tray area)
            x = screen_width - bubble_width - 50
            y = 50
            
            # Create window
            self.window = webview.create_window(
                title="AbstractAssistant",
                url=str(self.bubble_html),
                width=bubble_width,
                height=bubble_height,
                x=x,
                y=y,
                min_size=(300, 250),
                resizable=True,
                on_top=True,
                shadow=True,
                js_api=self.api
            )
            
            if self.debug:
                self.logger.info(f"Created bubble window: {bubble_width}x{bubble_height} at ({x}, {y})")
        
        except Exception as e:
            self.logger.error(f"Failed to create webview window: {e}")
            self._fallback_to_browser()
    
    def show(self):
        """Show the bubble window."""
        if not self.window:
            self.create_window()
        
        if self.window and WEBVIEW_AVAILABLE:
            def run_webview():
                try:
                    webview.start(debug=self.debug)
                except Exception as e:
                    self.logger.error(f"Error running webview: {e}")
                    self._fallback_to_browser()
            
            # Run webview in a separate thread
            webview_thread = threading.Thread(target=run_webview, daemon=True)
            webview_thread.start()
            
            self.is_visible = True
            
            if self.debug:
                self.logger.info("Bubble window shown")
        else:
            self._fallback_to_browser()
    
    def hide(self):
        """Hide the bubble window."""
        if self.window and WEBVIEW_AVAILABLE:
            try:
                self.window.hide()
                self.is_visible = False
                
                if self.debug:
                    self.logger.info("Bubble window hidden")
            except Exception as e:
                self.logger.error(f"Error hiding window: {e}")
    
    def destroy(self):
        """Destroy the bubble window."""
        if self.window and WEBVIEW_AVAILABLE:
            try:
                self.window.destroy()
                self.is_visible = False
                
                if self.debug:
                    self.logger.info("Bubble window destroyed")
            except Exception as e:
                self.logger.error(f"Error destroying window: {e}")
    
    def set_response_callback(self, callback: Callable):
        """Set callback for AI responses."""
        self.on_response_callback = callback
    
    def set_error_callback(self, callback: Callable):
        """Set callback for errors."""
        self.on_error_callback = callback
    
    def _fallback_to_browser(self):
        """Fallback to opening bubble in browser."""
        try:
            url = f"file://{self.bubble_html.absolute()}"
            webbrowser.open(url)
            
            if self.debug:
                self.logger.info(f"Opened bubble in browser: {url}")
        except Exception as e:
            self.logger.error(f"Failed to open browser fallback: {e}")
            self._show_error_dialog("Failed to open chat interface")
    
    def _show_error_dialog(self, message: str):
        """Show error dialog as last resort."""
        if TKINTER_AVAILABLE:
            try:
                root = tk.Tk()
                root.withdraw()  # Hide main window
                messagebox.showerror("AbstractAssistant Error", message)
                root.destroy()
            except Exception:
                pass
        
        # Print to console as final fallback
        print(f"AbstractAssistant Error: {message}")


class BubbleAPI:
    """API for communication between JavaScript and Python."""
    
    def __init__(self, llm_manager, bubble_window):
        """Initialize the API.
        
        Args:
            llm_manager: LLM manager instance
            bubble_window: Bubble window instance
        """
        self.llm_manager = llm_manager
        self.bubble_window = bubble_window
    
    def send_message(self, message: str, provider: str, model: str):
        """Handle message from the bubble interface.
        
        Args:
            message: User message
            provider: LLM provider
            model: Model name
        """
        try:
            # Update provider and model if different
            if provider != self.llm_manager.current_provider:
                self.llm_manager.set_provider(provider)
            
            if model != self.llm_manager.current_model:
                self.llm_manager.set_model(model)
            
            # Generate response in background thread
            def generate_response():
                try:
                    response = self.llm_manager.generate_response(
                        message=message,
                        provider=provider,
                        model=model
                    )
                    
                    # Call response callback if set
                    if self.bubble_window.on_response_callback:
                        self.bubble_window.on_response_callback(response)
                    
                    return response
                    
                except Exception as e:
                    error_msg = f"Error generating response: {str(e)}"
                    
                    # Call error callback if set
                    if self.bubble_window.on_error_callback:
                        self.bubble_window.on_error_callback(error_msg)
                    
                    return error_msg
            
            # Run in background thread
            thread = threading.Thread(target=generate_response, daemon=True)
            thread.start()
            
        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            if self.bubble_window.on_error_callback:
                self.bubble_window.on_error_callback(error_msg)
    
    def get_providers(self):
        """Get available providers and models."""
        try:
            providers = self.llm_manager.get_providers()
            
            provider_data = {}
            for key, info in providers.items():
                provider_data[key] = {
                    'name': info.display_name,
                    'models': info.models,
                    'default_model': info.default_model
                }
            
            return provider_data
            
        except Exception as e:
            print(f"Error getting providers: {e}")
            return {}
    
    def get_status(self):
        """Get current status information."""
        try:
            status_info = self.llm_manager.get_status_info()
            return status_info
        except Exception as e:
            print(f"Error getting status: {e}")
            return {
                'provider': 'unknown',
                'model': 'unknown',
                'tokens_current': 0,
                'tokens_max': 0
            }
    
    def hide_bubble(self):
        """Hide the bubble window."""
        self.bubble_window.hide()
    
    def show_response(self, content: str):
        """Show AI response (placeholder for toast notification)."""
        # This would trigger a toast notification in the main app
        print(f"AI Response: {content}")
    
    def show_error(self, message: str):
        """Show error message (placeholder for error notification)."""
        # This would trigger an error notification in the main app
        print(f"Error: {message}")


class FallbackBubble:
    """Fallback bubble implementation using tkinter."""
    
    def __init__(self, llm_manager, config=None, debug: bool = False):
        """Initialize fallback bubble."""
        self.llm_manager = llm_manager
        self.config = config
        self.debug = debug
        self.window = None
        self.is_visible = False
    
    def show(self):
        """Show fallback bubble."""
        if not TKINTER_AVAILABLE:
            print("No UI framework available. Please install pywebview or ensure tkinter is available.")
            return
        
        if self.window:
            self.window.deiconify()
            self.window.lift()
            return
        
        # Create simple tkinter window
        self.window = tk.Toplevel()
        self.window.title("AbstractAssistant")
        self.window.geometry("400x300")
        self.window.resizable(True, True)
        
        # Position near top-right
        self.window.geometry("+{}+{}".format(
            self.window.winfo_screenwidth() - 450,
            50
        ))
        
        # Create simple interface
        frame = tk.Frame(self.window, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text="AbstractAssistant", font=("Arial", 16, "bold")).pack(pady=(0, 10))
        
        # Text input
        self.text_input = tk.Text(frame, height=8, wrap=tk.WORD)
        self.text_input.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Send button
        send_btn = tk.Button(frame, text="Send", command=self._send_message)
        send_btn.pack(pady=(0, 10))
        
        # Status
        self.status_label = tk.Label(frame, text="Ready", fg="green")
        self.status_label.pack()
        
        self.is_visible = True
        
        # Focus on text input
        self.text_input.focus_set()
    
    def hide(self):
        """Hide fallback bubble."""
        if self.window:
            self.window.withdraw()
            self.is_visible = False
    
    def destroy(self):
        """Destroy fallback bubble."""
        if self.window:
            self.window.destroy()
            self.window = None
            self.is_visible = False
    
    def _send_message(self):
        """Send message from fallback interface."""
        message = self.text_input.get("1.0", tk.END).strip()
        if not message:
            return
        
        self.text_input.delete("1.0", tk.END)
        self.status_label.config(text="Generating...", fg="orange")
        
        def generate_response():
            try:
                response = self.llm_manager.generate_response(message)
                
                # Show response in a simple dialog
                self.window.after(0, lambda: self._show_response(response))
                
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                self.window.after(0, lambda: self._show_response(error_msg))
        
        # Run in background thread
        thread = threading.Thread(target=generate_response, daemon=True)
        thread.start()
        
        # Hide window after sending
        self.hide()
    
    def _show_response(self, response: str):
        """Show response in dialog."""
        self.status_label.config(text="Ready", fg="green")
        
        # Simple response dialog
        response_window = tk.Toplevel(self.window)
        response_window.title("AI Response")
        response_window.geometry("500x400")
        
        text_widget = tk.Text(response_window, wrap=tk.WORD, padx=10, pady=10)
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert("1.0", response)
        text_widget.config(state=tk.DISABLED)
        
        # Close button
        close_btn = tk.Button(response_window, text="Close", command=response_window.destroy)
        close_btn.pack(pady=10)
