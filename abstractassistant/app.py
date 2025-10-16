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


class ClickableIcon(pystray.Icon):
    """Custom pystray Icon that handles direct clicks without menu."""
    
    def __init__(self, name, image, text=None, click_handler=None):
        # Store our handler before calling super().__init__
        self.click_handler = click_handler
        self._stored_menu = None
        print(f"🔄 ClickableIcon created with handler: {click_handler is not None}")
        
        # Create with no menu initially
        super().__init__(name, image, text, menu=None)
    
    @property
    def _menu(self):
        """Override _menu property to intercept access and launch chat bubble."""
        print(f"🔍 _menu property accessed!")
        
        if self.click_handler:
            print("✅ Intercepting _menu property access, launching chat bubble!")
            # Call handler directly in main thread (Qt requirement)
            try:
                self.click_handler()
            except Exception as e:
                print(f"❌ Click handler error: {e}")
            
            # Return None so no menu is displayed
            return None
        
        # Fall back to stored menu
        return self._stored_menu
    
    @_menu.setter
    def _menu(self, value):
        """Allow setting _menu during initialization."""
        print(f"🔍 _menu property set to: {value}")
        self._stored_menu = value


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
        # Generate a modern, clean icon - start with ready state (green, steady)
        icon_image = self.icon_generator.create_app_icon(
            color_scheme="green",  # Ready state: steady green
            animated=False         # Ready state: no animation
        )
        
        if self.debug:
            print("🔄 Creating custom system tray icon with direct click handler")
        
        # Use our custom ClickableIcon for direct click handling
        return ClickableIcon(
            "AbstractAssistant",
            icon_image,
            "AbstractAssistant - AI at your fingertips",
            click_handler=self.show_chat_bubble
        )
    
    def update_icon_status(self, status: str):
        """Update the system tray icon based on application status.
        
        Args:
            status: 'ready', 'generating', 'executing', 'thinking'
        """
        if not self.icon:
            return
            
        try:
            if status == "ready":
                # Ready: steady green
                icon_image = self.icon_generator.create_app_icon(
                    color_scheme="green",
                    animated=False
                )
                # Stop any working animation timer
                self._stop_working_animation()
            elif status in ["generating", "executing", "thinking"]:
                # Working: start continuous animation with cycling colors
                self._start_working_animation()
                return  # Don't update icon here, let the timer handle it
            else:
                # Default: steady green
                icon_image = self.icon_generator.create_app_icon(
                    color_scheme="green",
                    animated=False
                )
            
            # Update the icon
            self.icon.icon = icon_image
            
            if self.debug:
                print(f"🎨 Updated icon status to: {status}")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error updating icon status: {e}")
    
    def _start_working_animation(self):
        """Start the working animation timer for continuous icon updates."""
        try:
            import threading
            import time
            
            # Stop any existing timer
            self._stop_working_animation()
            
            # Create a timer that updates the icon every 500ms for smooth animation
            def update_working_icon():
                if self.icon:
                    try:
                        icon_image = self.icon_generator.create_app_icon(
                            color_scheme="working",
                            animated=True
                        )
                        self.icon.icon = icon_image
                    except Exception as e:
                        if self.debug:
                            print(f"❌ Error updating working icon: {e}")
            
            # Use a simple timer approach
            def timer_loop():
                while hasattr(self, 'working_active') and self.working_active:
                    update_working_icon()
                    time.sleep(0.5)  # Update every 500ms
            
            self.working_active = True
            self.working_timer = threading.Thread(target=timer_loop, daemon=True)
            self.working_timer.start()
            
            if self.debug:
                print("🎨 Started working animation")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error starting working animation: {e}")
    
    def _stop_working_animation(self):
        """Stop the working animation."""
        if hasattr(self, 'working_active'):
            self.working_active = False
        if self.debug:
            print("🎨 Stopped working animation")
    
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
                    self.bubble_manager.set_status_callback(self.update_icon_status)
                    
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
        
        # Update icon back to ready state (steady green)
        self.update_icon_status("ready")
        
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
