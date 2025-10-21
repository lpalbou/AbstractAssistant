"""
Icon generator utility for creating modern, clean system tray icons.

Generates icons with a modern, minimalist design suitable for macOS menu bar.
"""

from PIL import Image, ImageDraw, ImageFilter
import math


class IconGenerator:
    """Generates modern icons for the system tray application."""
    
    def __init__(self, size: int = 64):
        """Initialize the icon generator.
        
        Args:
            size: Icon size in pixels (default: 64 for high-DPI displays)
        """
        self.size = size
        
    def create_app_icon(self, color_scheme: str = "blue", animated: bool = False) -> Image.Image:
        """Create the main application icon with a modern, AI-inspired design.
        
        Args:
            color_scheme: Color scheme ('blue', 'green', 'purple', 'orange', 'red')
            animated: Whether to create an animated version (adds subtle pulse effect)
        """
        # Create base image with transparency
        img = Image.new('RGBA', (self.size, self.size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Calculate dimensions
        center = self.size // 2
        radius = int(self.size * 0.35)
        
        # Create gradient background circle (neural network inspired)
        self._draw_gradient_circle(draw, center, radius, color_scheme, animated)
        
        # Add neural network nodes
        self._draw_neural_nodes(draw, center, radius, animated)
        
        # Add connecting lines
        self._draw_neural_connections(draw, center, radius, animated)
        
        # Apply subtle glow effect
        img = self._add_glow_effect(img, color_scheme)
        
        return img
    
    def _draw_gradient_circle(self, draw: ImageDraw.Draw, center: int, radius: int, color_scheme: str = "blue", animated: bool = False):
        
        # Color schemes - more vibrant and visible
        colors = {
            "blue": (64, 150, 255),      # Brighter blue
            "green": (40, 180, 60),      # Much deeper, more visible green
            "purple": (180, 80, 255),    # Brighter purple
            "orange": (255, 140, 80),    # More vibrant orange
            "red": (255, 60, 80),        # Brighter red for working
            "cyan": (80, 255, 255),      # More vibrant cyan
            "yellow": (255, 255, 80)     # Brighter yellow
        }
        
        # Special working mode: dynamic heartbeat with red/purple cycling
        if color_scheme == "working":
            import time
            # Fast heartbeat pattern with red/purple cycling
            cycle_time = time.time() % 2  # 2 seconds total cycle (faster)
            heartbeat_phase = (time.time() * 8) % 1  # Very fast heartbeat
            
            # Color cycling between red and purple
            if cycle_time < 1:
                base_color = colors["red"]      # Strong red
            else:
                base_color = colors["purple"]   # Strong purple
            
            # Much more dramatic heartbeat intensity
            if heartbeat_phase < 0.1:  # First beat - very strong
                intensity = 2.5
            elif heartbeat_phase < 0.15:  # Quick fade
                intensity = 0.3
            elif heartbeat_phase < 0.25:  # Second beat - strongest
                intensity = 3.0
            elif heartbeat_phase < 0.35:  # Quick fade
                intensity = 0.3
            else:  # Long rest period - very dim
                intensity = 0.2
                
        elif color_scheme == "green":
            base_color = colors["green"]
            if animated:
                import time
                # Gentle breathing for ready state
                intensity = 0.8 + 0.4 * math.sin(time.time() * 0.5)  # Slower breathing
            else:
                intensity = 1.0
        else:
            base_color = colors.get(color_scheme, colors["blue"])
            intensity = 1.0
        
        # Apply intensity to color
        final_color = tuple(int(c * intensity) for c in base_color)
        
        # Draw main circle with gradient effect
        for i in range(radius, 0, -2):
            alpha = int(255 * (i / radius) * 0.8)
            circle_color = final_color + (alpha,)
            draw.ellipse([center-i, center-i, center+i, center+i], fill=circle_color)
    
    def _draw_neural_nodes(self, draw: ImageDraw.Draw, center: int, radius: int, animated: bool = False):
        """Draw neural network nodes around the circle."""
        node_positions = [
            (center + radius * 0.6, center - radius * 0.3),
            (center + radius * 0.3, center + radius * 0.6),
            (center - radius * 0.4, center + radius * 0.4),
            (center - radius * 0.6, center - radius * 0.2),
            (center - radius * 0.1, center - radius * 0.7)
        ]
        
        for i, (x, y) in enumerate(node_positions):
            node_radius = 3 + (i % 2)  # Varying sizes
            if animated:
                import time
                # Subtle pulsing
                pulse = 1 + 0.3 * math.sin(time.time() * 2 + i)
                node_radius *= pulse
            
            draw.ellipse([x-node_radius, y-node_radius, x+node_radius, y+node_radius], 
                        fill=(255, 255, 255, 180))
    
    def _draw_neural_connections(self, draw: ImageDraw.Draw, center: int, radius: int, animated: bool = False):
        """Draw connecting lines between nodes."""
        connections = [
            ((center + radius * 0.6, center - radius * 0.3), (center + radius * 0.3, center + radius * 0.6)),
            ((center + radius * 0.3, center + radius * 0.6), (center - radius * 0.4, center + radius * 0.4)),
            ((center - radius * 0.4, center + radius * 0.4), (center - radius * 0.6, center - radius * 0.2)),
            ((center - radius * 0.1, center - radius * 0.7), (center + radius * 0.6, center - radius * 0.3))
        ]
        
        for (x1, y1), (x2, y2) in connections:
            draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, 120), width=2)
    
    def _add_glow_effect(self, img: Image.Image, color_scheme: str) -> Image.Image:
        """Add a subtle glow effect around the icon."""
        # Create glow layer
        glow = img.filter(ImageFilter.GaussianBlur(radius=3))
        
        # Composite original on top of glow
        result = Image.alpha_composite(glow, img)
        return result
    
    def create_status_icon(self, status: str) -> Image.Image:
        """Create a simple status indicator icon.
        
        Args:
            status: Status type ('ready', 'working', 'error', 'warning')
        """
        size = self.size
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Status colors
        colors = {
            'ready': (52, 199, 89),      # Green
            'working': (255, 149, 0),    # Orange
            'error': (255, 59, 48),      # Red
            'warning': (255, 204, 0),    # Yellow
            'thinking': (175, 82, 222),  # Purple
            'speaking': (0, 122, 255)    # Blue
        }
        
        color = colors.get(status, colors['ready'])
        
        # Draw status circle
        draw.ellipse([2, 2, size-2, size-2], fill=color)
        
        return img
    
    def apply_heartbeat_effect(self, base_icon: Image.Image, status: str = "ready") -> Image.Image:
        """Apply DRAMATIC animated effect with solid colors and rotating elements.
        
        Args:
            base_icon: Base icon image to apply effect to
            status: Status for animation type ('ready', 'thinking', 'speaking')
            
        Returns:
            Icon with dramatic animated effect applied
        """
        import time
        import math
        from PIL import ImageFilter, ImageEnhance, ImageDraw
        
        # Debug: Print status occasionally (only in debug mode)
        if hasattr(self, 'debug') and self.debug:
            if hasattr(self, '_last_debug_time'):
                if time.time() - self._last_debug_time > 3:  # Every 3 seconds
                    print(f"🎨 Icon animation status: {status}")
                    self._last_debug_time = time.time()
            else:
                print(f"🎨 Icon animation status: {status}")
                self._last_debug_time = time.time()
        
        # Print status changes only in debug mode
        if not hasattr(self, '_last_status') or self._last_status != status:
            if hasattr(self, 'debug') and self.debug:
                print(f"🔄 Icon status changed: {getattr(self, '_last_status', 'none')} → {status}")
            self._last_status = status
        
        # SOLID background colors for maximum visibility
        solid_colors = {
            'ready': (0, 255, 80),        # Bright green
            'thinking': (255, 60, 100),   # Bright red
            'speaking': (60, 150, 255),   # Bright blue
            'generating': (255, 160, 0)   # Bright orange
        }
        
        # Create a new dramatic icon instead of modifying the base
        size = base_icon.size[0]
        center = size // 2
        
        # Create new image with transparent background
        result = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(result)
        
        # Get current time for animation
        current_time = time.time()
        
        # Get base color for this status
        base_color = solid_colors.get(status, solid_colors['ready'])
        
        # Status-specific animation patterns with rotation
        # Debug output disabled for clean terminal
        # print(f"🎯 Animation logic: status='{status}', base_color={base_color}")
        
        if status == 'thinking':
            # print("🔴 THINKING: Drawing rotating red bars")  # Debug disabled
            # Fast rotating bars with red color - CLOCKWISE rotation
            rotation_speed = 4.0  # 4 rotations per second
            angle = -(current_time * rotation_speed * 360) % 360  # Negative for clockwise
            
            # Double-heartbeat intensity
            heartbeat = (current_time * 3.0) % 1  # 3Hz heartbeat
            if heartbeat < 0.1:
                intensity = 1.0
            elif heartbeat < 0.2:
                intensity = 0.3
            elif heartbeat < 0.3:
                intensity = 1.2
            else:
                intensity = 0.2
            
            # Draw rotating bars
            self._draw_rotating_bars(draw, center, size, angle, base_color, intensity)
            
        elif status == 'speaking':
            # print("🔵 SPEAKING: Drawing vibrating blue bars")  # Debug disabled
            # print(f"🔵 SPEAKING: Using color {base_color} (should be blue)")  # Debug disabled
            
            # Create voice frequency-like vibration pattern
            freq1 = 8.0  # High frequency vibration
            freq2 = 3.0  # Medium frequency modulation
            freq3 = 1.5  # Low frequency envelope
            
            # Complex vibration pattern mimicking voice
            vibration = (math.sin(current_time * freq1 * 2 * math.pi) * 0.3 +
                        math.sin(current_time * freq2 * 2 * math.pi) * 0.4 +
                        math.sin(current_time * freq3 * 2 * math.pi) * 0.3)
            intensity = 0.7 + vibration * 0.3
            
            # Draw vibrating voice bars (vertical bars that vibrate)
            self._draw_voice_bars(draw, center, size, base_color, intensity, current_time)
            
        elif status == 'ready':
            # print("🟢 READY: Drawing breathing green circle")  # Debug disabled
            # Slow breathing circle with green color
            breath = 0.5 + 0.5 * math.sin(current_time * 0.6 * math.pi)  # 0.3Hz breathing
            intensity = 0.4 + breath * 0.3
            
            # Draw breathing circle (no rotation)
            self._draw_breathing_circle(draw, center, size, base_color, intensity)
            
        else:
            # print(f"❓ UNKNOWN STATUS: '{status}' - using default circle")  # Debug disabled
            # Default: static circle
            self._draw_breathing_circle(draw, center, size, base_color, 0.5)
        
        return result
    
    def _draw_rotating_bars(self, draw, center, size, angle, color, intensity):
        """Draw rotating bars for thinking status."""
        # Adjust color intensity
        r, g, b = color
        r = int(min(255, r * intensity))
        g = int(min(255, g * intensity))
        b = int(min(255, b * intensity))
        bar_color = (r, g, b, 255)
        
        # Draw 4 bars rotating around center
        bar_length = size * 0.3
        bar_width = size * 0.08
        
        for i in range(4):
            bar_angle = angle + (i * 90)
            rad = math.radians(bar_angle)
            
            # Calculate bar endpoints
            start_x = center + math.cos(rad) * (size * 0.15)
            start_y = center + math.sin(rad) * (size * 0.15)
            end_x = center + math.cos(rad) * (size * 0.35)
            end_y = center + math.sin(rad) * (size * 0.35)
            
            # Draw thick line as bar
            self._draw_thick_line(draw, start_x, start_y, end_x, end_y, bar_width, bar_color)
    
    def _draw_voice_bars(self, draw, center, size, color, intensity, current_time):
        """Draw vibrating voice bars for speaking status."""
        import math
        
        # Adjust color intensity
        r, g, b = color
        r = int(min(255, r * intensity))
        g = int(min(255, g * intensity))
        b = int(min(255, b * intensity))
        bar_color = (r, g, b, 255)
        
        # Draw 5 vertical bars with different vibration frequencies (like voice visualizer)
        bar_count = 5
        bar_width = size * 0.08
        bar_spacing = size * 0.12
        
        for i in range(bar_count):
            # Each bar has slightly different frequency for realistic voice effect
            bar_freq = 6.0 + i * 1.5  # Different frequencies per bar
            bar_vibration = math.sin(current_time * bar_freq * 2 * math.pi)
            
            # Bar height varies with vibration (like audio visualizer)
            base_height = size * 0.15
            vibration_height = size * 0.25 * abs(bar_vibration)
            total_height = base_height + vibration_height
            
            # Position bars horizontally across the icon
            x = center - (bar_count - 1) * bar_spacing / 2 + i * bar_spacing
            y_top = center - total_height / 2
            y_bottom = center + total_height / 2
            
            # Draw vertical bar
            bbox = [x - bar_width/2, y_top, x + bar_width/2, y_bottom]
            draw.rectangle(bbox, fill=bar_color)
    
    def _draw_breathing_circle(self, draw, center, size, color, intensity):
        """Draw breathing circle for ready status."""
        # Adjust color intensity
        r, g, b = color
        r = int(min(255, r * intensity))
        g = int(min(255, g * intensity))
        b = int(min(255, b * intensity))
        circle_color = (r, g, b, 255)
        
        # Draw MUCH LARGER pulsing circle to match menu bar icon size
        base_radius = size * 0.35  # Much larger base size
        radius = base_radius * (0.8 + 0.4 * intensity)
        bbox = [center - radius, center - radius, center + radius, center + radius]
        draw.ellipse(bbox, fill=circle_color)
    
    def _draw_thick_line(self, draw, x1, y1, x2, y2, width, color):
        """Draw a thick line between two points."""
        import math
        # Calculate perpendicular offset for thickness
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx*dx + dy*dy)
        if length == 0:
            return
            
        # Normalize and get perpendicular
        dx /= length
        dy /= length
        px = -dy * width / 2
        py = dx * width / 2
        
        # Draw polygon for thick line
        points = [
            (x1 + px, y1 + py),
            (x1 - px, y1 - py),
            (x2 - px, y2 - py),
            (x2 + px, y2 + py)
        ]
        draw.polygon(points, fill=color)