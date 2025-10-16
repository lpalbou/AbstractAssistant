"""
Main application class for AbstractAssistant.

Handles system tray integration, UI coordination, and application lifecycle.
"""

import threading
import time
from typing import Optional

import pystray
from PIL import Image, ImageDraw

from .ui.qt_bubble import QtBubbleManager
from .core.llm_manager import LLMManager
from .utils.icon_generator import IconGenerator
from .config import Config


class AbstractAssistantApp:
    """Main application class coordinating all components."""
    
    def __init__(self, config: Optional[Config] = None, debug: bool = False):
        """Initialize the AbstractAssistant application.
        
        Args:
            config: Configuration object (uses default if None)
            debug: Enable debug mode
        """
        self.config = config or Config.default()
        self.debug = debug
        
        # Validate configuration
        if not self.config.validate():
            print("Warning: Configuration validation failed, using defaults")
            self.config = Config.default()
        
        # Initialize components
        self.icon: Optional[pystray.Icon] = None
        self.bubble_manager: Optional[QtBubbleManager] = None
        self.llm_manager: LLMManager = LLMManager(config=self.config)
        self.icon_generator: IconGenerator = IconGenerator(size=self.config.system_tray.icon_size)
        
        # Application state
        self.is_running: bool = False
        self.bubble_visible: bool = False
        
        if self.debug:
            print(f"AbstractAssistant initialized with config: {self.config.to_dict()}")
        
    def create_system_tray_icon(self) -> pystray.Icon:
        """Create and configure the system tray icon."""
        # Generate a modern, clean icon
        icon_image = self.icon_generator.create_app_icon()
        
        # Simple menu with just Open Chat and Quit
        menu = pystray.Menu(
            pystray.MenuItem("Open Chat", self.show_chat_bubble, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sessions", pystray.Menu(
                pystray.MenuItem("Clear Session", self.clear_session),
                pystray.MenuItem("Save Session...", self.save_session),
                pystray.MenuItem("Load Session...", self.load_session)
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit_application)
        )
        
        return pystray.Icon(
            "AbstractAssistant",
            icon_image,
            "AbstractAssistant - AI at your fingertips",
            menu=menu
        )
    
    def show_chat_bubble(self, icon=None, item=None):
        """Show the Qt chat bubble interface."""
        try:
            if self.debug:
                print("🔄 show_chat_bubble called")
            
            # Create bubble manager if not exists
            if self.bubble_manager is None:
                if self.debug:
                    print("🔄 Creating Qt bubble manager...")
                
                try:
                    self.bubble_manager = QtBubbleManager(
                        llm_manager=self.llm_manager,
                        config=self.config,
                        debug=self.debug
                    )
                    
                    # Set up callbacks for responses and errors
                    self.bubble_manager.set_response_callback(self.handle_bubble_response)
                    self.bubble_manager.set_error_callback(self.handle_bubble_error)
                    
                    if self.debug:
                        print("✅ Qt bubble manager created successfully")
                    
                except Exception as e:
                    if self.debug:
                        print(f"❌ Failed to create Qt bubble manager: {e}")
                        import traceback
                        traceback.print_exc()
                    print("💬 AbstractAssistant: Error creating chat bubble")
                    return
            
            # Show the bubble
            if self.bubble_manager:
                if self.debug:
                    print("🔄 Showing Qt bubble...")
                self.bubble_manager.show()
                self.bubble_visible = True
                
                if self.debug:
                    print("💬 Qt chat bubble opened")
            else:
                if self.debug:
                    print("❌ No bubble manager available")
                    
        except Exception as e:
            if self.debug:
                print(f"❌ Error in show_chat_bubble: {e}")
                import traceback
                traceback.print_exc()
            print("💬 AbstractAssistant: Error opening chat bubble")
    
    def hide_chat_bubble(self):
        """Hide the chat bubble interface."""
        self.bubble_visible = False
        if self.bubble_manager:
            self.bubble_manager.hide()
            
            if self.debug:
                print("💬 Chat bubble hidden")
    
    def handle_bubble_response(self, response: str):
        """Handle AI response from bubble."""
        if self.debug:
            print(f"🔄 App: handle_bubble_response called with: {response[:100]}...")
        
        # Show toast notification with response
        self.show_toast_notification(response, "success")
        
        # Hide bubble after response
        self.hide_chat_bubble()
    
    def handle_bubble_error(self, error: str):
        """Handle error from bubble."""
        # Show error toast notification
        self.show_toast_notification(error, "error")
        
        # Hide bubble after error
        self.hide_chat_bubble()
    
    def show_toast_notification(self, message: str, type: str = "info"):
        """Show a toast notification."""
        icon = "✅" if type == "success" else "❌" if type == "error" else "ℹ️"
        print(f"{icon} {message}")
        
        if self.debug:
            print(f"Toast notification: {type} - {message}")
        
        # Show a proper macOS notification
        try:
            import subprocess
            title = "AbstractAssistant"
            subtitle = "AI Response" if type == "success" else "Error"
            
            # Truncate message for notification
            display_message = message[:200] + "..." if len(message) > 200 else message
            
            # Use osascript to show macOS notification
            script = f'''
            display notification "{display_message}" with title "{title}" subtitle "{subtitle}"
            '''
            subprocess.run(["osascript", "-e", script], check=False)
            
            if self.debug:
                print(f"📱 macOS notification shown: {display_message[:50]}...")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Failed to show notification: {e}")
            # Fallback - just print
            print(f"💬 {title}: {message}")
    
    def set_provider(self, provider: str):
        """Set the active LLM provider."""
        self.llm_manager.set_provider(provider)
    
    def update_status(self, status: str):
        """Update application status."""
        # Status is now handled by the web interface
        if self.debug:
            print(f"Status update: {status}")
    
    def clear_session(self, icon=None, item=None):
        """Clear the current session."""
        try:
            if self.debug:
                print("🔄 Clearing session...")
            
            self.llm_manager.clear_session()
            
            if self.debug:
                print("✅ Session cleared")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error clearing session: {e}")
    
    def save_session(self, icon=None, item=None):
        """Save the current session to file."""
        try:
            if self.debug:
                print("🔄 Saving session...")
            
            # Create sessions directory if it doesn't exist
            import os
            sessions_dir = os.path.join(os.path.expanduser("~"), ".abstractassistant", "sessions")
            os.makedirs(sessions_dir, exist_ok=True)
            
            # Generate filename with timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_{timestamp}.json"
            filepath = os.path.join(sessions_dir, filename)
            
            # Save session
            success = self.llm_manager.save_session(filepath)
            
            if success:
                if self.debug:
                    print(f"✅ Session saved to: {filepath}")
                # Show notification
                try:
                    from .ui.toast_window import show_toast_notification
                    show_toast_notification(f"Session saved to:\n{filename}", debug=self.debug)
                except:
                    print(f"💾 Session saved: {filename}")
            else:
                if self.debug:
                    print("❌ Failed to save session")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error saving session: {e}")
    
    def load_session(self, icon=None, item=None):
        """Load a session from file."""
        try:
            if self.debug:
                print("🔄 Loading session...")
            
            # Get sessions directory
            import os
            sessions_dir = os.path.join(os.path.expanduser("~"), ".abstractassistant", "sessions")
            
            if not os.path.exists(sessions_dir):
                if self.debug:
                    print("❌ No sessions directory found")
                return
            
            # Get list of session files
            session_files = [f for f in os.listdir(sessions_dir) if f.endswith('.json')]
            
            if not session_files:
                if self.debug:
                    print("❌ No session files found")
                try:
                    from .ui.toast_window import show_toast_notification
                    show_toast_notification("No saved sessions found", debug=self.debug)
                except:
                    print("📂 No saved sessions found")
                return
            
            # For now, load the most recent session
            # TODO: Add proper file picker dialog
            session_files.sort(reverse=True)  # Most recent first
            latest_session = session_files[0]
            filepath = os.path.join(sessions_dir, latest_session)
            
            # Load session
            success = self.llm_manager.load_session(filepath)
            
            if success:
                if self.debug:
                    print(f"✅ Session loaded from: {filepath}")
                # Show notification
                try:
                    from .ui.toast_window import show_toast_notification
                    show_toast_notification(f"Session loaded:\n{latest_session}", debug=self.debug)
                except:
                    print(f"📂 Session loaded: {latest_session}")
            else:
                if self.debug:
                    print("❌ Failed to load session")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error loading session: {e}")

    def quit_application(self, icon=None, item=None):
        """Quit the application gracefully."""
        self.is_running = False
        if self.icon:
            self.icon.stop()
        
        # Clean up bubble manager
        if self.bubble_manager:
            try:
                self.bubble_manager.destroy()
            except Exception as e:
                if self.debug:
                    print(f"Error destroying bubble manager: {e}")
    
    def run(self):
        """Start the application."""
        self.is_running = True
        
        # Create and run system tray icon
        self.icon = self.create_system_tray_icon()
        
        print("AbstractAssistant started. Check your menu bar!")
        print("Click the icon to open the chat interface.")
        
        # Run the icon (this blocks until quit)
        self.icon.run()
