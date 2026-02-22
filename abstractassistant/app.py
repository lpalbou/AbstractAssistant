"""
Main application class for AbstractAssistant.

Handles system tray integration, UI coordination, and application lifecycle.
"""

import faulthandler
import threading
import time
import signal
import sys
import traceback
from pathlib import Path
from typing import Optional
from enum import Enum

faulthandler.enable()

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
            if hasattr(self, 'debug') and self.debug:
                print(f"🔄 EnhancedClickableIcon created with single_click: {single_click_handler is not None}, double_click: {double_click_handler is not None}")

        # Create with no menu initially
        super().__init__(name, image, text, menu=None)

    @property
    def _menu(self):
        """Override _menu property to intercept access and handle click timing."""
        if self.debug:
            if hasattr(self, 'debug') and self.debug:
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
                if hasattr(self, 'debug') and self.debug:
                    print("🔄 First click detected, starting timer...")

        elif self.click_count == 2:
            # Second click - cancel timer and execute double click
            if self.click_timer is not None:
                self.click_timer.cancel()
                self.click_timer = None

            self.click_count = 0  # Reset immediately
            self._execute_double_click()

            if self.debug:
                if hasattr(self, 'debug') and self.debug:
                    print("🔄 Double click detected!")

    def _execute_single_click(self):
        """Execute single click handler after timeout."""
        self.click_count = 0  # Reset click count
        self.click_timer = None

        if self.debug:
            if hasattr(self, 'debug') and self.debug:
                print("✅ Single click detected on system tray icon!")

        if self.single_click_handler:
            try:
                self.single_click_handler()
            except Exception as e:
                if hasattr(self, 'debug') and self.debug:
                    print(f"❌ Single click handler error: {e}")
                if self.debug:
                    import traceback
                    traceback.print_exc()

    def _execute_double_click(self):
        """Execute double click handler immediately."""
        if self.debug:
            if hasattr(self, 'debug') and self.debug:
                print("✅ Double click detected on system tray icon!")

        if self.double_click_handler:
            try:
                self.double_click_handler()
            except Exception as e:
                if hasattr(self, 'debug') and self.debug:
                    print(f"❌ Double click handler error: {e}")
                if self.debug:
                    import traceback
                    traceback.print_exc()


    @_menu.setter
    def _menu(self, value):
        """Allow setting _menu during initialization."""
        if self.debug:
            if hasattr(self, 'debug') and self.debug:
                print(f"🔍 _menu property set to: {value}")
        self._stored_menu = value


class BubbleVisibility(str, Enum):
    """Actual bubble visibility state (derived from Qt widget state)."""

    UNINITIALIZED = "uninitialized"
    HIDDEN = "hidden"
    VISIBLE = "visible"
    MINIMIZED = "minimized"


class AbstractAssistantApp:
    """Main application class coordinating all components."""
    
    def __init__(
        self,
        config: Optional[Config] = None,
        debug: bool = False,
        listening_mode: str = "wait",
        *,
        data_dir: Optional[Path] = None,
    ):
        """Initialize the AbstractAssistant application.

        Args:
            config: Configuration object (uses default if None)
            debug: Enable debug mode
            listening_mode: Voice listening mode (none, stop, wait, full)
            data_dir: Assistant base data dir (sessions + runtime stores)
        """
        self.config = config or Config.default()
        self.debug = debug
        self.listening_mode = listening_mode
        self.data_dir = Path(data_dir).expanduser() if data_dir is not None else None
        
        # Validate configuration
        if not self.config.validate():
            if self.debug:
                print("Warning: Configuration validation failed, using defaults")
            self.config = Config.default()
        
        # Initialize components
        self.icon: Optional[pystray.Icon] = None
        self.bubble_manager: Optional[QtBubbleManager] = None
        self.llm_manager: LLMManager = LLMManager(config=self.config, debug=self.debug, data_dir=self.data_dir)
        self.icon_generator: IconGenerator = IconGenerator(size=self.config.system_tray.icon_size)
        self.animation_fps: int = self._resolve_animation_fps()
        self.animation_interval_ms: int = max(1, int(1000 / self.animation_fps))
        self.animation_interval_s: float = self.animation_interval_ms / 1000.0
        
        # Application state
        self.is_running: bool = False
        
        # Icon animation state
        self.base_icon: Optional[Image.Image] = None
        self.animation_timer: Optional[threading.Timer] = None
        self.current_status: str = "ready"
        self._voice_meter: float | list[float] = 0.0
        self._voice_meter_ts: float = 0.0
        self._voice_meter_decay_s: float = 0.35
        self._voice_meter_lock = threading.Lock()
        
        if self.debug:
            print(f"AbstractAssistant initialized with config: {self.config.to_dict()}")
            print(f"🎛️  Tray animation: {self.animation_fps} FPS ({self.animation_interval_ms} ms)")

    def _resolve_animation_fps(self) -> int:
        """Resolve tray animation FPS with safe clamping."""
        fps_raw = getattr(getattr(self.config, "system_tray", None), "animation_fps", 30)
        try:
            fps = int(fps_raw)
        except Exception:
            print(f"#FALLBACK: invalid animation_fps={fps_raw}; using 30")
            fps = 30
        if fps < 10:
            print(f"#FALLBACK: animation_fps={fps} too low; using 10")
            fps = 10
        if fps > 30:
            print(f"#FALLBACK: animation_fps={fps} too high; using 30")
            fps = 30
        return fps
        
    def create_system_tray_icon(self) -> pystray.Icon:
        """Create and configure the system tray icon."""
        # Try to use the app bundle icon first, fallback to generated icon
        self.base_icon = self._load_app_bundle_icon()
        if not self.base_icon:
            # Generate a modern, clean icon - start with ready state (green, steady)
            self.base_icon = self.icon_generator.create_app_icon(
                color_scheme="green",  # Ready state: steady green
                animated=False         # Ready state: no animation
            )

        # Apply initial heartbeat effect
        icon_image = self.icon_generator.apply_heartbeat_effect(self.base_icon, "ready")

        if self.debug:
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
    
    def _load_app_bundle_icon(self) -> Optional[Image.Image]:
        """Load the icon from the app bundle if available."""
        try:
            from pathlib import Path
            # Try to find the app bundle icon
            app_bundle_icon = Path("/Applications/AbstractAssistant.app/Contents/Resources/icon.png")
            
            if self.debug:
                if self.debug:
                    print(f"🔍 Looking for app bundle icon at: {app_bundle_icon}")
                    print(f"   Exists: {app_bundle_icon.exists()}")
            
            if app_bundle_icon.exists():
                base_icon = Image.open(app_bundle_icon)
                
                if self.debug:
                    if self.debug:
                        print(f"✅ Loaded app bundle icon: {base_icon.size} {base_icon.mode}")
                
                # Resize to system tray size if needed
                target_size = (self.config.system_tray.icon_size, self.config.system_tray.icon_size)
                if base_icon.size != target_size:
                    if self.debug:
                        if self.debug:
                            print(f"🔄 Resizing from {base_icon.size} to {target_size}")
                    base_icon = base_icon.resize(target_size, Image.Resampling.LANCZOS)
                
                return base_icon
        except Exception as e:
            if self.debug:
                if self.debug:
                    print(f"❌ Could not load app bundle icon: {e}")
        return None
    
    def update_icon_status(self, status: str):
        """Update the system tray icon based on application status.
        
        Args:
            status: 'ready', 'generating', 'executing', 'thinking', 'speaking'
        """
        if self.debug:
            print(f"🔄 update_icon_status called with: {status}")
            print(f"   Previous status: {self.current_status}")
        
        if not self.icon and not (hasattr(self, 'qt_tray_icon') and self.qt_tray_icon):
            if self.debug:
                print("⚠️  No icon available for status update")
            return
        
        if not self.base_icon:
            if self.debug:
                print("⚠️  No base icon available for status update")
            return
        
        try:
            # Stop any existing animation timer
            self._stop_animation_timer()
            
            # Map status to animation type
            animation_status = status
            if status in ["thinking", "generating", "executing", "offline", "reconnecting"]:
                animation_status = "thinking"  # All working states use thinking animation
            elif status == "speaking":
                animation_status = "speaking"
            else:
                animation_status = "ready"  # Default to ready

            if animation_status != "speaking":
                self.update_voice_meter(0.0)
            
            # Update current status AFTER determining animation type
            self.current_status = animation_status
            
            # Start appropriate animation
            self._start_heartbeat_animation(animation_status)
            try:
                self._update_tray_tooltip(status=animation_status)
            except Exception:
                pass
            
            if self.debug:
                print(f"🎨 Updated icon status: {status} -> animation: {animation_status}")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error updating icon status: {e}")

    def update_voice_meter(self, level: float | list[float]) -> None:
        """Update the live voice meter (0..1) for speaking animation."""
        if isinstance(level, (list, tuple)):
            try:
                vals = [max(0.0, min(1.0, float(v))) for v in level]
            except Exception:
                return
            with self._voice_meter_lock:
                self._voice_meter = vals
                self._voice_meter_ts = time.monotonic()
            return
        try:
            val = float(level)
        except Exception:
            return
        val = max(0.0, min(1.0, val))
        with self._voice_meter_lock:
            self._voice_meter = val
            self._voice_meter_ts = time.monotonic()

    def _get_voice_meter(self) -> float | list[float]:
        """Return a decayed voice meter value."""
        with self._voice_meter_lock:
            level = self._voice_meter
            ts = float(self._voice_meter_ts)
        if ts <= 0.0:
            return 0.0
        dt = max(0.0, time.monotonic() - ts)
        decay = max(0.1, float(self._voice_meter_decay_s))
        if isinstance(level, list):
            if not level:
                return 0.0
            if dt <= 0.0:
                return level
            if dt >= decay:
                return [0.0 for _ in level]
            scale = max(0.0, 1.0 - (dt / decay))
            return [max(0.0, float(v) * scale) for v in level]
        try:
            val = float(level)
        except Exception:
            return 0.0
        if val <= 0.0:
            return 0.0
        if dt <= 0.0:
            return val
        if dt >= decay:
            return 0.0
        # Linear decay for a crisp falloff.
        return max(0.0, val * (1.0 - (dt / decay)))
    
    def _start_heartbeat_animation(self, status: str):
        """Start smooth heartbeat animation for the given status."""
        if self.debug:
            print(f"🎬 Starting smooth heartbeat animation for: {status}")
            print(f"   pystray icon available: {self.icon is not None}")
            print(f"   Qt icon available: {hasattr(self, 'qt_tray_icon') and self.qt_tray_icon is not None}")
            print(f"   Base icon available: {self.base_icon is not None}")
        
        # Stop any existing animation
        self._stop_animation_timer()
        
        # Use Qt timer if we're in Qt mode, otherwise use threading timer
        if hasattr(self, 'qt_tray_icon') and self.qt_tray_icon is not None:
            self._start_qt_animation(status)
        else:
            self._start_threading_animation(status)
    
    def _start_qt_animation(self, status: str):
        """Start Qt-based animation using QTimer."""
        try:
            from PyQt5.QtCore import QTimer
            
            def update_icon():
                try:
                    if self.base_icon and self.current_status == status and hasattr(self, 'qt_tray_icon'):
                        # Apply smooth heartbeat effect
                        meter = self._get_voice_meter() if status == "speaking" else None
                        icon_image = self.icon_generator.apply_heartbeat_effect(self.base_icon, status, voice_meter=meter)
                        self._update_qt_icon(icon_image)
                    elif self.debug:
                        print(f"⚠️  Qt animation stopped - status_match:{self.current_status == status}")
                        if hasattr(self, 'qt_animation_timer'):
                            self.qt_animation_timer.stop()
                except Exception as e:
                    if self.debug:
                        print(f"❌ Error in Qt animation: {e}")
            
            # Create Qt timer for smooth animation
            self.qt_animation_timer = QTimer()
            self.qt_animation_timer.timeout.connect(update_icon)
            self.qt_animation_timer.start(self.animation_interval_ms)
            
            if self.debug:
                print("✅ Qt animation timer started")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error starting Qt animation: {e}")
    
    def _start_threading_animation(self, status: str):
        """Start threading-based animation using threading.Timer."""
        def update_icon():
            try:
                if self.icon and self.base_icon and self.current_status == status:
                    # Apply smooth heartbeat effect
                    meter = self._get_voice_meter() if status == "speaking" else None
                    icon_image = self.icon_generator.apply_heartbeat_effect(self.base_icon, status, voice_meter=meter)
                    self.icon.icon = icon_image
                    
                    # Schedule next update at configured FPS
                    self.animation_timer = threading.Timer(self.animation_interval_s, update_icon)
                    self.animation_timer.start()
                elif self.debug:
                    print(f"⚠️  Threading animation stopped - status_match:{self.current_status == status}")
            except Exception as e:
                if self.debug:
                    print(f"❌ Error in threading animation: {e}")
        
        # Start the threading animation
        update_icon()
    
    def _update_qt_icon(self, icon_image):
        """Update Qt system tray icon with new image."""
        try:
            from PyQt5.QtGui import QIcon, QPixmap
            import io
            
            # Convert PIL image to QPixmap
            img_buffer = io.BytesIO()
            icon_image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            pixmap = QPixmap()
            pixmap.loadFromData(img_buffer.getvalue())
            qt_icon = QIcon(pixmap)
            
            # Update the Qt tray icon
            self.qt_tray_icon.setIcon(qt_icon)
            
        except Exception as e:
            if self.debug:
                print(f"❌ Error updating Qt icon: {e}")
    
    def _stop_animation_timer(self):
        """Stop the current animation timer (both Qt and threading)."""
        # Stop Qt timer if it exists
        if hasattr(self, 'qt_animation_timer') and self.qt_animation_timer:
            self.qt_animation_timer.stop()
            self.qt_animation_timer = None
        
        # Stop threading timer if it exists
        if hasattr(self, 'animation_timer') and self.animation_timer:
            self.animation_timer.cancel()
            self.animation_timer = None
    

    
    # ── Application state machine ────────────────────────────────────
    #
    # States (derived from self.current_status set by update_icon_status):
    #   "ready"    — idle, green icon
    #   "thinking" — gateway run active, pulsing icon
    #   "speaking" — TTS playing, animated icon
    #
    # Tray click rules:
    #   READY    + click  → SHOW the app (always, unconditionally)
    #   READY    + dblclk → SHOW the app (always, unconditionally)
    #   RUNNING  + click  → ignore (run in progress)
    #   RUNNING  + dblclk → ignore (run in progress)
    #   SPEAKING + click  → PAUSE / RESUME voice (no UI change)
    #   SPEAKING + dblclk → STOP voice, reset to READY
    #
    # After STOP: state resets to "ready" so the next click shows the app.

    def _app_state(self) -> str:
        """Return the canonical app state: 'ready', 'running', or 'speaking'."""
        s = str(self.current_status or "").strip().lower()
        if s == "speaking":
            return "speaking"
        if s in {"thinking", "running", "executing", "waiting"}:
            return "running"
        return "ready"

    def show_chat_bubble(self, icon=None, item=None):
        """Show / raise / focus the chat bubble.  Never refuses."""
        try:
            state = self._bubble_visibility_state()
            bubble = self._get_bubble()

            if state == BubbleVisibility.VISIBLE:
                if bubble is not None:
                    bubble.raise_()
                    bubble.activateWindow()
                return

            if state == BubbleVisibility.MINIMIZED:
                if bubble is not None:
                    bubble.showNormal()
                    bubble.raise_()
                    bubble.activateWindow()
                return

            if self.bubble_manager:
                self.bubble_manager.show()
            else:
                self.bubble_manager = QtBubbleManager(
                    llm_manager=self.llm_manager,
                    config=self.config,
                    debug=self.debug,
                    listening_mode=self.listening_mode,
                )
                self.bubble_manager.set_response_callback(self.handle_bubble_response)
                self.bubble_manager.set_error_callback(self.handle_bubble_error)
                self.bubble_manager.set_status_callback(self.update_icon_status)
                self.bubble_manager.set_voice_meter_callback(self.update_voice_meter)
                self.bubble_manager.set_app_quit_callback(self.quit_application)
                self.bubble_manager.show()

        except Exception as e:
            if self.debug:
                print(f"❌ show_chat_bubble error: {e}")

    # ── Tray click handlers ───────────────────────────────────────────

    def handle_single_click(self):
        """Single click on tray icon."""
        state = self._app_state()
        if self.debug:
            print(f"🔄 Single click: state={state}")

        if state == "speaking":
            try:
                vm = self._get_voice_manager()
                if vm is not None:
                    paused = False
                    try:
                        paused = bool(vm.is_paused())
                    except Exception:
                        pass
                    if paused:
                        vm.resume()
                    else:
                        vm.pause()
            except Exception:
                pass
            return

        if state == "running":
            return

        # ready → show
        self.show_chat_bubble()

    def handle_double_click(self):
        """Double click on tray icon."""
        state = self._app_state()
        if self.debug:
            print(f"🔄 Double click: state={state}")

        if state == "speaking":
            try:
                vm = self._get_voice_manager()
                if vm is not None:
                    vm.stop()
                bubble = self._get_bubble()
                if bubble is not None:
                    try:
                        bubble.notify_manual_voice_stop()
                    except Exception:
                        pass
            except Exception:
                pass
            self.update_icon_status("ready")
            return

        if state == "running":
            return

        # ready → show
        self.show_chat_bubble()

    def _get_voice_manager(self):
        """Return the voice manager if available, else None."""
        bubble = self._get_bubble()
        if bubble is None:
            return None
        return getattr(bubble, "voice_manager", None)

    def hide_chat_bubble(self):
        """Hide the chat bubble interface."""
        if self.bubble_manager:
            self.bubble_manager.hide()
            
            if self.debug:
                print("💬 Chat bubble hidden")

    def _bubble_visibility_state(self) -> BubbleVisibility:
        """Derive the bubble visibility from the actual Qt widget state."""
        bubble = self._get_bubble()
        if bubble is None:
            return BubbleVisibility.UNINITIALIZED
        try:
            # Visible + minimized are distinct (minimized should restore).
            if not bubble.isVisible():
                return BubbleVisibility.HIDDEN
            try:
                if hasattr(bubble, "isMinimized") and bubble.isMinimized():
                    return BubbleVisibility.MINIMIZED
            except Exception:
                pass
            try:
                from PyQt5.QtCore import Qt

                if bubble.windowState() & Qt.WindowMinimized:
                    return BubbleVisibility.MINIMIZED
            except Exception:
                pass
            return BubbleVisibility.VISIBLE
        except Exception:
            return BubbleVisibility.HIDDEN

    def _bubble_is_visible(self) -> bool:
        """Return True if the chat bubble is actually visible."""
        return self._bubble_visibility_state() == BubbleVisibility.VISIBLE

    def _get_bubble(self):
        try:
            if self.bubble_manager and getattr(self.bubble_manager, "bubble", None):
                return self.bubble_manager.bubble
        except Exception:
            return None
        return None

    def _run_is_active(self) -> bool:
        bubble = self._get_bubble()
        if bubble is None:
            return False
        try:
            return bool(getattr(bubble, "is_run_active", lambda: False)())
        except Exception:
            return False

    def _get_run_activity_summary(self) -> str:
        bubble = self._get_bubble()
        if bubble is None:
            return ""
        try:
            return str(getattr(bubble, "get_run_activity_summary", lambda: "")() or "").strip()
        except Exception:
            return ""

    def _update_tray_tooltip(self, *, status: Optional[str] = None) -> None:
        base = "AbstractAssistant"
        summary = self._get_run_activity_summary()
        if summary:
            tip = f"{base} — {summary}"
        else:
            state = str(status or "").strip().lower()
            if state in {"thinking", "running", "executing", "waiting"}:
                tip = f"{base} — Running"
            elif state in {"speaking"}:
                tip = f"{base} — Speaking"
            else:
                tip = f"{base} — Ready"
        try:
            if hasattr(self, "qt_tray_icon") and self.qt_tray_icon is not None:
                self.qt_tray_icon.setToolTip(tip)
        except Exception:
            pass
        try:
            if self.icon is not None:
                self.icon.title = tip
        except Exception:
            pass

    def _notify_run_active(self) -> None:
        summary = self._get_run_activity_summary() or "A run is in progress."
        try:
            if hasattr(self, "qt_tray_icon") and self.qt_tray_icon is not None:
                from PyQt5.QtWidgets import QSystemTrayIcon

                self.qt_tray_icon.showMessage(
                    "AbstractAssistant running",
                    summary,
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
                return
        except Exception:
            pass
        try:
            if self.icon is not None and hasattr(self.icon, "notify"):
                self.icon.notify(summary, "AbstractAssistant running")
        except Exception:
            pass
    
    def handle_bubble_response(self, response: str):
        """Handle AI response from bubble (informational only — never hide the UI)."""
        if self.debug:
            print(f"🔄 App: handle_bubble_response called with: {response[:100]}...")

    def handle_bubble_error(self, error: str):
        """Handle error from bubble (informational only — never hide the UI)."""
        if self.debug:
            print(f"❌ App: handle_bubble_error: {error}")
    
    def show_toast_notification(self, message: str, type: str = "info"):
        """Show a toast notification."""
        icon = "✅" if type == "success" else "❌" if type == "error" else "ℹ️"
        if self.debug:
            print(f"{icon} {message}")
        
        if self.debug:
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
            def _escape_applescript_string(txt: str) -> str:
                txt = str(txt or "")
                txt = txt.replace("\\", "\\\\")
                txt = txt.replace('"', '\\"')
                txt = txt.replace("\r\n", "\n").replace("\r", "\n")
                txt = txt.replace("\n", "\\n")
                return txt

            script = (
                'display notification "'
                + _escape_applescript_string(display_message)
                + '" with title "'
                + _escape_applescript_string(title)
                + '" subtitle "'
                + _escape_applescript_string(subtitle)
                + '"'
            )
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
            if self.debug:
                print(f"Status update: {status}")
    
    def clear_session(self, icon=None, item=None):
        """Clear the current session with user confirmation."""
        try:
            if self.debug:
                print("🔄 System tray clear session requested...")
            
            # CRITICAL: System tray actions MUST have user confirmation
            # Use the bubble's clear_session method which includes confirmation dialog
            if hasattr(self, 'bubble_manager') and self.bubble_manager:
                # Delegate to bubble manager which has proper user confirmation
                bubble = self.bubble_manager.get_current_bubble()
                if bubble:
                    bubble.clear_session()  # This includes user confirmation dialog
                    return
            
            # Fallback: Show notification that clearing requires UI interaction
            try:
                from .ui.toast_window import show_toast_notification
                show_toast_notification(
                    "To clear session, please use the Clear button in the chat interface", 
                    debug=self.debug
                )
            except:
                print("💬 To clear session, please use the Clear button in the chat interface")
                
            if self.debug:
                print("⚠️  System tray clear session requires user confirmation via UI")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error in clear session request: {e}")
    
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
        """Load a session from file with user confirmation."""
        try:
            if self.debug:
                print("🔄 System tray load session requested...")
            
            # CRITICAL: System tray actions MUST NOT automatically replace sessions
            # Use the bubble's load_session method which includes proper file picker
            if hasattr(self, 'bubble_manager') and self.bubble_manager:
                # Delegate to bubble manager which has proper user file selection
                bubble = self.bubble_manager.get_current_bubble()
                if bubble:
                    bubble.load_session()  # This includes user file picker dialog
                    return
            
            # Fallback: Show notification that loading requires UI interaction
            try:
                from .ui.toast_window import show_toast_notification
                show_toast_notification(
                    "To load session, please use the Load button in the chat interface", 
                    debug=self.debug
                )
            except:
                print("💬 To load session, please use the Load button in the chat interface")
                
            if self.debug:
                print("⚠️  System tray load session requires user file selection via UI")
                
        except Exception as e:
            if self.debug:
                print(f"❌ Error in load session request: {e}")

    def _preflight_initialization(self):
        """Pre-initialize components for instant bubble display on first click."""
        if self.debug:
            print("🚀 Starting preflight initialization...")

        try:
            # Pre-create bubble manager (this is the main bottleneck)
            if self.bubble_manager is None:
                if self.debug:
                    print("🔄 Pre-creating bubble manager...")

                self.bubble_manager = QtBubbleManager(
                    llm_manager=self.llm_manager,
                    config=self.config,
                    debug=self.debug,
                    listening_mode=self.listening_mode
                )

                # Set up callbacks
                self.bubble_manager.set_response_callback(self.handle_bubble_response)
                self.bubble_manager.set_error_callback(self.handle_bubble_error)
                # Note: Status callback will be set after preflight initialization to avoid TTS init interference
                self.bubble_manager.set_app_quit_callback(self.quit_application)

                if self.debug:
                    print("✅ Bubble manager pre-created successfully")

            # Pre-initialize the bubble itself (this loads UI components, TTS/STT, etc.)
            if self.debug:
                print("🔄 Pre-initializing chat bubble...")

            # This creates the bubble without showing it
            self.bubble_manager._prepare_bubble()

            # Now set the status callback after TTS initialization is complete
            if self.bubble_manager:
                self.bubble_manager.set_status_callback(self.update_icon_status)
                self.bubble_manager.set_voice_meter_callback(self.update_voice_meter)
                if self.debug:
                    print("✅ Status callback set after TTS initialization")

            if self.debug:
                print("✅ Preflight initialization completed - bubble ready for instant display")

        except Exception as e:
            if self.debug:
                print(f"⚠️  Preflight initialization failed: {e}")
                print("   First click will still work but with delay")
            
            # Still set status callback even if preflight failed
            if self.bubble_manager:
                self.bubble_manager.set_status_callback(self.update_icon_status)
                self.bubble_manager.set_voice_meter_callback(self.update_voice_meter)

    def quit_application(self, icon=None, item=None):
        """Quit the application gracefully."""
        if self.debug:
            print("🔄 Quitting AbstractAssistant...")
        
        self.is_running = False
        
        # Stop animation timer
        self._stop_animation_timer()
        
        if self.icon:
            self.icon.stop()

        # Stop/hide Qt tray icon if we are running in Qt mode.
        try:
            if hasattr(self, "qt_tray_icon") and self.qt_tray_icon is not None:
                self.qt_tray_icon.hide()
        except Exception:
            pass

        # Stop click timer used for single/double click detection (Qt mode).
        try:
            if hasattr(self, "click_timer") and self.click_timer is not None:
                self.click_timer.stop()
        except Exception:
            pass
        
        # Clean up bubble manager
        if self.bubble_manager:
            try:
                self.bubble_manager.destroy()
            except Exception as e:
                if self.debug:
                    print(f"Error destroying bubble manager: {e}")
        
        if self.debug:
            print("✅ AbstractAssistant quit successfully")

    def _request_qt_quit(self) -> None:
        """Request a graceful quit on the Qt event loop (safe to call from SIGINT handler)."""
        # Always run cleanup first; then quit the Qt event loop.
        try:
            self.quit_application()
        except Exception:
            pass

        try:
            if hasattr(self, "qt_app") and self.qt_app:
                self.qt_app.quit()
        except Exception:
            pass

    def run(self):
        """Start the application using Qt event loop for proper threading."""
        self.is_running = True

        # Global exception hooks so crashes are never silent.
        _orig_excepthook = sys.excepthook

        def _excepthook(exc_type, exc_value, exc_tb):
            sys.stderr.write("\n=== UNCAUGHT EXCEPTION ===\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)
            sys.stderr.write("=== END UNCAUGHT EXCEPTION ===\n")
            sys.stderr.flush()
            _orig_excepthook(exc_type, exc_value, exc_tb)

        sys.excepthook = _excepthook

        def _thread_excepthook(args):
            sys.stderr.write(f"\n=== UNCAUGHT THREAD EXCEPTION ({args.thread}) ===\n")
            traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=sys.stderr)
            sys.stderr.write("=== END UNCAUGHT THREAD EXCEPTION ===\n")
            sys.stderr.flush()

        threading.excepthook = _thread_excepthook

        try:
            # Import Qt here to avoid conflicts
            from PyQt5.QtWidgets import QApplication, QSystemTrayIcon
            from PyQt5.QtCore import QTimer
            from PyQt5.QtGui import QIcon

            # Create Qt application in main thread
            if not QApplication.instance():
                self.qt_app = QApplication(sys.argv)
            else:
                self.qt_app = QApplication.instance()

            # Check if system tray is available
            if not QSystemTrayIcon.isSystemTrayAvailable():
                print("❌ System tray is not available on this system")  # Always show this error
                return

            # Create Qt-based system tray icon
            self.qt_icon = self._create_qt_system_tray_icon()

            # Preflight initialization: Pre-load bubble manager for instant display
            self._preflight_initialization()

            if not self.debug:
                print("AbstractAssistant started. Check your menu bar!")
                print("Click the icon to open the chat interface.")
            else:
                print("AbstractAssistant started. Check your menu bar!")
                print("Click the icon to open the chat interface.")

            # Ctrl+C / SIGTERM should shut down cleanly (avoid macOS "python quit unexpectedly").
            # We schedule the quit on the Qt loop to keep teardown ordered.
            def _handle_sigint(_signum, _frame):
                try:
                    QTimer.singleShot(0, self._request_qt_quit)
                except Exception:
                    self._request_qt_quit()

            try:
                signal.signal(signal.SIGINT, _handle_sigint)
                signal.signal(signal.SIGTERM, _handle_sigint)
            except Exception:
                # If signals are not available/allowed in this context, we still handle KeyboardInterrupt below.
                pass

            # Run Qt event loop (this blocks until quit)
            try:
                self.qt_app.exec_()
            except KeyboardInterrupt:
                # Ensure a graceful shutdown when Ctrl+C interrupts the event loop.
                self._request_qt_quit()
                return

        except ImportError:
            if self.debug:
                print("❌ PyQt5 not available. Falling back to pystray...")
            # Fallback to original pystray implementation
            self.icon = self.create_system_tray_icon()
            try:
                self.icon.run()
            except KeyboardInterrupt:
                self.quit_application()
                return

    def _create_qt_system_tray_icon(self):
        """Create Qt-based system tray icon with smooth animations."""
        from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
        from PyQt5.QtCore import QTimer
        from PyQt5.QtGui import QIcon, QPixmap
        from PIL import Image
        import io

        # Load base icon (same as pystray version)
        self.base_icon = self._load_app_bundle_icon()
        if not self.base_icon:
            # Generate a base icon if app bundle icon not available
            self.base_icon = self.icon_generator.create_app_icon(
                color_scheme="green",  # Ready state: steady green
                animated=False         # Ready state: no animation
            )

        # Apply initial smooth heartbeat effect
        icon_image = self.icon_generator.apply_heartbeat_effect(self.base_icon, "ready")

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

        # macOS: some tray clicks only surface via the context menu.
        try:
            context_menu.aboutToShow.connect(self._qt_on_context_menu_show)
        except Exception:
            pass

        tray_icon.setContextMenu(context_menu)

        # Store reference for animations
        self.qt_tray_icon = tray_icon
        
        # Show the tray icon
        tray_icon.show()

        # Start initial animation
        if self.debug:
            print(f"🎨 Starting initial animation with status: ready")
            print(f"   Current status in app: {self.current_status}")
        self._start_heartbeat_animation("ready")

        if self.debug:
            print("✅ Qt-based system tray icon created with smooth animations")

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

        # Resolve ActivationReason enums (fallback to numeric codes).
        try:
            from PyQt5.QtWidgets import QSystemTrayIcon

            Trigger = QSystemTrayIcon.ActivationReason.Trigger
            DoubleClick = QSystemTrayIcon.ActivationReason.DoubleClick
            Context = QSystemTrayIcon.ActivationReason.Context
            MiddleClick = QSystemTrayIcon.ActivationReason.MiddleClick
            Unknown = QSystemTrayIcon.ActivationReason.Unknown
        except Exception:
            Trigger, DoubleClick, Context, MiddleClick, Unknown = 3, 2, 1, 4, 0

        # Defensive: if timers aren't ready, just treat as a single click.
        if not hasattr(self, "click_timer") or self.click_timer is None:
            if self.debug:
                print("#FALLBACK: click timer missing; treating as single click")
            self._qt_handle_single_click()
            return

        if reason == Trigger:  # Single click (or first part of double click)
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

        elif reason == DoubleClick:  # Double click confirmation
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

        elif reason == Context:
            # On macOS, some tray clicks arrive as "Context".
            if sys.platform == "darwin":
                if self.debug:
                    print("🔄 Context activation on macOS; treating as single click")
                self._qt_handle_single_click()
            else:
                if self.debug:
                    print("ℹ️  Context activation; leaving to context menu")

        elif reason in (MiddleClick, Unknown):
            if self.debug:
                print("#FALLBACK: Unknown/middle click; treating as single click")
            self._qt_handle_single_click()

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

        # Route through the same cleanup path (menu Quit should behave like Ctrl+C).
        self._request_qt_quit()

    def _qt_on_context_menu_show(self):
        """Best-effort: treat macOS context menu activation as a click.

        On macOS a single tray click fires both reason=3 (Trigger) AND
        aboutToShow.  If a Trigger-based pending click is already queued
        we must not fire a second one — that would pause then immediately
        resume the voice.
        """
        if sys.platform != "darwin":
            return
        if getattr(self, "pending_single_click", False):
            if self.debug:
                print("🖱️  Context menu on macOS; skipping (Trigger already pending)")
            return
        if self.debug:
            print("🖱️  Context menu on macOS; treating as single click")
        try:
            self._qt_handle_single_click()
        except Exception:
            pass
