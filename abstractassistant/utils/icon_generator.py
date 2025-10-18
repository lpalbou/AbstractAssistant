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
        """Draw a gradient circle background with color options."""
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
            # Ready state: much more visible heartbeat
            base_color = colors["green"]
            if animated:
                import time
                # More noticeable pulse every 1.5 seconds
                pulse_cycle = (time.time() * 0.67) % 1  # Faster, 1.5-second cycle
                if pulse_cycle < 0.2:  # Strong beat
                    intensity = 2.0  # Much brighter
                elif pulse_cycle < 0.4:  # Fade down
                    intensity = 1.2
                else:  # Rest period - much dimmer
                    intensity = 0.4  # Much darker for contrast
            else:
                intensity = 1.0
        else:
            base_color = colors.get(color_scheme, colors["blue"])
            intensity = 1.0
            if animated:
                import time
                pulse = abs(math.sin(time.time() * 2)) * 0.2 + 0.9
                intensity *= pulse
        
        # Enhanced gradient effect - much more visible from center to edge
        for i in range(radius):
            # Create stronger gradient with more dramatic falloff
            gradient_factor = (1 - (i / radius) ** 0.5)  # Square root for more dramatic gradient
            alpha = int(255 * gradient_factor * intensity)
            
            # Ensure alpha is within bounds
            alpha = max(0, min(255, alpha))
            
            # Create more vibrant color with better gradient
            color = (*base_color, alpha)
            draw.ellipse(
                [center - radius + i, center - radius + i,
                 center + radius - i, center + radius - i],
                fill=color
            )
        
        # Add bright center core for more dramatic effect
        core_radius = max(1, radius // 4)
        core_alpha = int(255 * intensity * 1.2)  # Extra bright center
        core_alpha = max(0, min(255, core_alpha))
        core_color = (*base_color, core_alpha)
        draw.ellipse(
            [center - core_radius, center - core_radius,
             center + core_radius, center + core_radius],
            fill=core_color
        )
    
    def _draw_neural_nodes(self, draw: ImageDraw.Draw, center: int, radius: int, animated: bool = False):
        """Draw neural network-style nodes."""
        # Animation effect for nodes - more visible
        node_alpha = 255  # Increased from 200 for full opacity
        small_node_alpha = 220  # Increased from 150 for better visibility
        if animated:
            import time
            pulse = abs(math.sin(time.time() * 3)) * 0.2 + 0.8  # Pulse between 0.8 and 1.0
            node_alpha = int(node_alpha * pulse)
            small_node_alpha = int(small_node_alpha * pulse)
        
        # Central node (larger)
        node_radius = int(radius * 0.15)
        draw.ellipse(
            [center - node_radius, center - node_radius,
             center + node_radius, center + node_radius],
            fill=(255, 255, 255, node_alpha)
        )
        
        # Surrounding nodes
        num_nodes = 6
        outer_radius = int(radius * 0.7)
        
        for i in range(num_nodes):
            angle = (2 * math.pi * i) / num_nodes
            x = center + int(outer_radius * math.cos(angle))
            y = center + int(outer_radius * math.sin(angle))
            
            small_radius = int(radius * 0.08)
            draw.ellipse(
                [x - small_radius, y - small_radius,
                 x + small_radius, y + small_radius],
                fill=(255, 255, 255, small_node_alpha)
            )
    
    def _draw_neural_connections(self, draw: ImageDraw.Draw, center: int, radius: int, animated: bool = False):
        """Draw connections between neural nodes."""
        num_nodes = 6
        outer_radius = int(radius * 0.7)
        
        # Animation effect for connections - more visible
        line_alpha = 180  # Increased from 100 for better visibility
        connection_alpha = 120  # Increased from 60 for better visibility
        if animated:
            import time
            pulse = abs(math.sin(time.time() * 2.5)) * 0.3 + 0.7  # Pulse between 0.7 and 1.0
            line_alpha = int(line_alpha * pulse)
            connection_alpha = int(connection_alpha * pulse)
        
        # Draw lines from center to outer nodes
        for i in range(num_nodes):
            angle = (2 * math.pi * i) / num_nodes
            x = center + int(outer_radius * math.cos(angle))
            y = center + int(outer_radius * math.sin(angle))
            
            draw.line(
                [center, center, x, y],
                fill=(255, 255, 255, line_alpha),
                width=2
            )
        
        # Draw some connections between outer nodes
        for i in range(0, num_nodes, 2):
            angle1 = (2 * math.pi * i) / num_nodes
            angle2 = (2 * math.pi * ((i + 2) % num_nodes)) / num_nodes
            
            x1 = center + int(outer_radius * math.cos(angle1))
            y1 = center + int(outer_radius * math.sin(angle1))
            x2 = center + int(outer_radius * math.cos(angle2))
            y2 = center + int(outer_radius * math.sin(angle2))
            
            draw.line(
                [x1, y1, x2, y2],
                fill=(255, 255, 255, connection_alpha),
                width=1
            )
    
    def _add_glow_effect(self, img: Image.Image, color_scheme: str = "blue") -> Image.Image:
        """Add a subtle glow effect to the icon."""
        # Create a slightly larger version for the glow
        glow_size = self.size + 8
        glow_img = Image.new('RGBA', (glow_size, glow_size), (0, 0, 0, 0))
        
        # Paste the original image in the center
        offset = 4
        glow_img.paste(img, (offset, offset), img)
        
        # Apply blur for glow effect
        glow_img = glow_img.filter(ImageFilter.GaussianBlur(radius=2))
        
        # Crop back to original size
        return glow_img.crop((offset, offset, offset + self.size, offset + self.size))
    
    def create_status_icon(self, status: str) -> Image.Image:
        """Create a status indicator icon.
        
        Args:
            status: Status string ('ready', 'generating', 'executing')
            
        Returns:
            Small status icon image
        """
        size = 16
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        colors = {
            'ready': (0, 255, 0, 200),      # Green
            'generating': (255, 165, 0, 200),  # Orange
            'executing': (255, 0, 0, 200),     # Red
            'error': (255, 0, 0, 200)          # Red
        }
        
        color = colors.get(status, (128, 128, 128, 200))  # Gray default
        
        # Draw status circle
        draw.ellipse([2, 2, size-2, size-2], fill=color)
        
        return img
