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


class EnhancedClickableIcon(pystray.Icon):
    """Custom pystray Icon that handles single/double click differentiation."""

    def __init__(self, name, image, text=None, single_click_handler=None, double_click_handler=None, debug=False):
        # Store our handlers before calling super().__init__
        self.single_click_handler = single_click_handler
        self.double_click_handler = double_click_handler
        self.debug = debug
        self._stored_menu = None

        # Click timing management
        self.click_count = 0
        self.click_timer = None
        self.DOUBLE_CLICK_TIMEOUT = 300  # milliseconds

        if self.debug:
            print(f"🔄 EnhancedClickableIcon created with single_click: {single_click_handler is not None}, double_click: {double_click_handler is not None}")

        # Create with no menu initially
        super().__init__(name, image, text, menu=None)

    @property
    def _menu(self):
        """Override _menu property to intercept access and handle click timing."""
        if self.debug:
            print(f"🔍 _menu property accessed! Click count: {self.click_count}")

        self._handle_click_timing()
        # Return None so no menu is displayed
        return None

    def _handle_click_timing(self):
        """Handle single/double click timing logic."""
        import threading

        self.click_count += 1

        if self.click_count == 1:
            # First click - start timer for single click
            if self.click_timer is not None:
                self.click_timer.cancel()

            self.click_timer = threading.Timer(
                self.DOUBLE_CLICK_TIMEOUT / 1000.0,  # Convert to seconds
                self._execute_single_click
            )
            self.click_timer.start()

            if self.debug:
                print("🔄 First click detected, starting timer...")

        elif self.click_count == 2:
            # Second click - cancel timer and execute double click
            if self.click_timer is not None:
                self.click_timer.cancel()
                self.click_timer = None

            self.click_count = 0  # Reset immediately
            self._execute_double_click()

            if self.debug:
                print("🔄 Double click detected!")

    def _execute_single_click(self):
        """Execute single click handler after timeout."""
        self.click_count = 0  # Reset click count
        self.click_timer = None

        if self.debug:
            print("✅ Single click detected on system tray icon!")

        if self.single_click_handler:
            try:
                self.single_click_handler()
            except Exception as e:
                print(f"❌ Single click handler error: {e}")
                if self.debug:
                    import traceback
                    traceback.print_exc()

    def _execute_double_click(self):
        """Execute double click handler immediately."""
        if self.debug:
            print("✅ Double click detected on system tray icon!")

        if self.double_click_handler:
            try:
                self.double_click_handler()
            except Exception as e:
                print(f"❌ Double click handler error: {e}")
                if self.debug:
                    import traceback
                    traceback.print_exc()

    @_menu.setter
    def _menu(self, value):
        """Allow setting _menu during initialization."""
        if self.debug:
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
        self.llm_manager: LLMManager = LLMManager(config=self.config, debug=self.debug)
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
            print("🔄 Creating enhanced system tray icon with single/double click detection")

        # Use our enhanced ClickableIcon for single/double click handling
        return EnhancedClickableIcon(
            "AbstractAssistant",
            icon_image,
            "AbstractAssistant - AI at your fingertips",
            single_click_handler=self.handle_single_click,
            double_click_handler=self.handle_double_click,
            debug=self.debug
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
                # Ready: gentle heartbeat green
                self._stop_working_animation()
                self._start_ready_animation()
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
            
            # Create a heartbeat-like animation with dynamic timing
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
            
            # Heartbeat-like timer with dynamic intervals
            def heartbeat_timer_loop():
                while hasattr(self, 'working_active') and self.working_active:
                    # Fast heartbeat pattern: beat-beat-pause
                    update_working_icon()
                    time.sleep(0.1)  # First beat
                    update_working_icon()
                    time.sleep(0.1)  # Second beat
                    update_working_icon()
                    time.sleep(0.8)  # Longer pause between heartbeats
            
            self.working_active = True
            self.working_timer = threading.Thread(target=heartbeat_timer_loop, daemon=True)
            self.working_timer.start()
            
            if self.debug:
                print("🎨 Started working animation")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error starting working animation: {e}")
    
    def _start_ready_animation(self):
        """Start the gentle ready state heartbeat animation."""
        try:
            import threading
            import time
            
            # Stop any existing animations
            self._stop_working_animation()
            self._stop_ready_animation()
            
            def update_ready_icon():
                if self.icon:
                    try:
                        icon_image = self.icon_generator.create_app_icon(
                            color_scheme="green",
                            animated=True
                        )
                        self.icon.icon = icon_image
                    except Exception as e:
                        if self.debug:
                            print(f"❌ Error updating ready icon: {e}")
            
            # Gentle heartbeat timer - slower, more subtle
            def ready_timer_loop():
                while hasattr(self, 'ready_active') and self.ready_active:
                    update_ready_icon()
                    time.sleep(0.1)  # Update every 100ms for smooth animation
            
            self.ready_active = True
            self.ready_timer = threading.Thread(target=ready_timer_loop, daemon=True)
            self.ready_timer.start()
            
            if self.debug:
                print("🎨 Started ready heartbeat animation")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error starting ready animation: {e}")
    
    def _stop_ready_animation(self):
        """Stop the ready animation."""
        if hasattr(self, 'ready_active'):
            self.ready_active = False
        if self.debug:
            print("🎨 Stopped ready animation")
    
    def _stop_working_animation(self):
        """Stop the working animation."""
        if hasattr(self, 'working_active'):
            self.working_active = False
        self._stop_ready_animation()  # Also stop ready animation
        if self.debug:
            print("🎨 Stopped working animation")

    
    def show_chat_bubble(self, icon=None, item=None):
        """Show the Qt chat bubble interface."""
        try:
            if self.debug:
                print("🔄 show_chat_bubble called")

            # Check if TTS is currently speaking and stop it
            if self.bubble_manager and hasattr(self.bubble_manager, 'bubble') and self.bubble_manager.bubble:
                bubble = self.bubble_manager.bubble
                if (hasattr(bubble, 'voice_manager') and bubble.voice_manager and
                    bubble.voice_manager.is_speaking()):
                    if self.debug:
                        print("🔊 TTS is speaking, stopping voice...")
                    bubble.voice_manager.stop()

                    # Always show bubble after stopping TTS
                    if not self.bubble_visible:
                        if self.debug:
                            print("🔄 Showing bubble after stopping TTS...")
                        self.bubble_manager.show()
                        self.bubble_visible = True
                        if self.debug:
                            print("💬 Qt chat bubble opened after TTS stop")
                    return
            
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
                    self.bubble_manager.set_app_quit_callback(self.quit_application)
                    
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

    def handle_single_click(self):
        """Handle single click on system tray icon.

        Behavior:
        - If voice is speaking → pause voice (stay hidden)
        - If voice is paused → resume voice (stay hidden)
        - If voice is idle → show chat bubble
        """
        try:
            if self.debug:
                print("🔄 Single click handler called")

            # Check if we have voice manager available
            if (self.bubble_manager and
                hasattr(self.bubble_manager, 'bubble') and
                self.bubble_manager.bubble and
                hasattr(self.bubble_manager.bubble, 'voice_manager') and
                self.bubble_manager.bubble.voice_manager):

                voice_manager = self.bubble_manager.bubble.voice_manager
                voice_state = voice_manager.get_state()

                if self.debug:
                    print(f"🔊 Voice state: {voice_state}")

                if voice_state == 'speaking':
                    # Pause voice, don't show bubble
                    success = voice_manager.pause()
                    if self.debug:
                        print(f"⏸ Voice pause: {'success' if success else 'failed'}")
                    return

                elif voice_state == 'paused':
                    # Resume voice, don't show bubble
                    success = voice_manager.resume()
                    if self.debug:
                        print(f"▶ Voice resume: {'success' if success else 'failed'}")
                    return

            # Voice is idle or not available - show chat bubble
            if self.debug:
                print("💬 Voice idle or unavailable, showing chat bubble")
            self.show_chat_bubble()

        except Exception as e:
            if self.debug:
                print(f"❌ Error in handle_single_click: {e}")
                import traceback
                traceback.print_exc()
            # Fallback - just show chat bubble
            self.show_chat_bubble()

    def handle_double_click(self):
        """Handle double click on system tray icon.

        Behavior:
        - If voice is speaking/paused → stop voice + show chat bubble
        - If voice is idle → show chat bubble
        """
        try:
            if self.debug:
                print("🔄 Double click handler called")

            # Check if we have voice manager available
            if (self.bubble_manager and
                hasattr(self.bubble_manager, 'bubble') and
                self.bubble_manager.bubble and
                hasattr(self.bubble_manager.bubble, 'voice_manager') and
                self.bubble_manager.bubble.voice_manager):

                voice_manager = self.bubble_manager.bubble.voice_manager
                voice_state = voice_manager.get_state()

                if self.debug:
                    print(f"🔊 Voice state: {voice_state}")

                if voice_state in ['speaking', 'paused']:
                    # Stop voice
                    voice_manager.stop()
                    if self.debug:
                        print("⏹ Voice stopped")

            # Always show chat bubble on double click
            if self.debug:
                print("💬 Showing chat bubble after double click")
            self.show_chat_bubble()

        except Exception as e:
            if self.debug:
                print(f"❌ Error in handle_double_click: {e}")
                import traceback
                traceback.print_exc()
            # Fallback - just show chat bubble
            self.show_chat_bubble()

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
        """Start the application using Qt event loop for proper threading."""
        self.is_running = True

        try:
            # Import Qt here to avoid conflicts
            from PyQt5.QtWidgets import QApplication, QSystemTrayIcon
            from PyQt5.QtCore import QTimer
            from PyQt5.QtGui import QIcon
            import sys

            # Create Qt application in main thread
            if not QApplication.instance():
                self.qt_app = QApplication(sys.argv)
            else:
                self.qt_app = QApplication.instance()

            # Check if system tray is available
            if not QSystemTrayIcon.isSystemTrayAvailable():
                print("❌ System tray is not available on this system")
                return

            # Create Qt-based system tray icon
            self.qt_icon = self._create_qt_system_tray_icon()

            print("AbstractAssistant started. Check your menu bar!")
            print("Click the icon to open the chat interface.")

            # Run Qt event loop (this blocks until quit)
            self.qt_app.exec_()

        except ImportError:
            print("❌ PyQt5 not available. Falling back to pystray...")
            # Fallback to original pystray implementation
            self.icon = self.create_system_tray_icon()
            self.icon.run()

    def _create_qt_system_tray_icon(self):
        """Create Qt-based system tray icon with proper click detection."""
        from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
        from PyQt5.QtCore import QTimer
        from PyQt5.QtGui import QIcon, QPixmap
        from PIL import Image
        import io

        # Generate icon using our icon generator
        icon_image = self.icon_generator.create_app_icon(
            color_scheme="green",  # Ready state: steady green
            animated=False         # Ready state: no animation
        )

        # Convert PIL image to QPixmap
        img_buffer = io.BytesIO()
        icon_image.save(img_buffer, format='PNG')
        img_buffer.seek(0)

        pixmap = QPixmap()
        pixmap.loadFromData(img_buffer.getvalue())
        qt_icon = QIcon(pixmap)

        # Create system tray icon
        tray_icon = QSystemTrayIcon(qt_icon)
        tray_icon.setToolTip("AbstractAssistant - AI at your fingertips")

        # Click detection variables
        self.click_timer = QTimer()
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self._qt_handle_single_click)
        self.pending_single_click = False
        self.DOUBLE_CLICK_TIMEOUT = 200  # milliseconds (short period to detect double click)

        # Connect click signal
        tray_icon.activated.connect(self._qt_on_tray_activated)

        # Create context menu (right-click)
        context_menu = QMenu()

        show_action = QAction("Show Chat", None)
        show_action.triggered.connect(self.show_chat_bubble)
        context_menu.addAction(show_action)

        context_menu.addSeparator()

        quit_action = QAction("Quit", None)
        quit_action.triggered.connect(self._qt_quit_application)
        context_menu.addAction(quit_action)

        tray_icon.setContextMenu(context_menu)

        # Show the tray icon
        tray_icon.show()

        if self.debug:
            print("✅ Qt-based system tray icon created successfully")

        return tray_icon

    def _qt_on_tray_activated(self, reason):
        """Handle Qt system tray activation (clicks) with proper delay-based detection.

        Logic:
        - Single click: reason == 3 only
        - Double click: reason == 3 followed quickly by reason == 2

        Strategy:
        - When reason == 3: Wait 200ms to see if reason == 2 follows
        - If no reason == 2 within 200ms: Execute single click
        - If reason == 2 arrives within 200ms: Execute ONLY double click
        """
        if self.debug:
            print(f"🖱️  Click detected - reason: {reason}")

        if reason == 3:  # Single click (or first part of double click)
            if self.pending_single_click:
                # Already have a pending single click, ignore this one
                if self.debug:
                    print("⚠️  Ignoring additional reason=3 (already pending)")
                return

            # Mark that we have a pending single click
            self.pending_single_click = True

            # Start timer to wait for possible reason=2 (double click confirmation)
            self.click_timer.start(self.DOUBLE_CLICK_TIMEOUT)

            if self.debug:
                print(f"🔄 Qt: reason=3 detected, waiting {self.DOUBLE_CLICK_TIMEOUT}ms for possible reason=2...")

        elif reason == 2:  # Double click confirmation
            if self.pending_single_click and self.click_timer.isActive():
                # We have a pending single click and timer is still running
                # This means reason=2 arrived within the timeout period

                # Cancel the pending single click
                self.click_timer.stop()
                self.pending_single_click = False

                if self.debug:
                    print("✅ Qt: reason=2 detected - cancelling single click, executing double click!")

                # Execute ONLY the double click
                self._qt_handle_double_click()
            else:
                # Unexpected reason=2 without pending single click
                if self.debug:
                    print("⚠️  Unexpected reason=2 without pending single click")

                # Execute double click anyway (fallback)
                self._qt_handle_double_click()

    def _qt_handle_single_click(self):
        """Handle single click after timeout (no reason=2 detected) in Qt main thread."""
        # Clear the pending flag
        self.pending_single_click = False

        if self.debug:
            print("✅ Qt: Single click confirmed (no reason=2 within 200ms) - executing action!")

        # This runs in Qt main thread, so it's safe to create Qt widgets
        # Execute single click action (pause/resume voice or show bubble)
        self.handle_single_click()

    def _qt_handle_double_click(self):
        """Handle double click immediately in Qt main thread."""
        if self.debug:
            print("✅ Qt: Double click detected!")

        # This runs in Qt main thread, so it's safe to create Qt widgets
        self.handle_double_click()

    def _qt_quit_application(self):
        """Quit the Qt application."""
        if self.debug:
            print("🔄 Qt: Quit requested")

        if hasattr(self, 'qt_app') and self.qt_app:
            self.qt_app.quit()
