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
            "green": (80, 255, 120),     # More vibrant green
            "purple": (180, 80, 255),    # Brighter purple
            "orange": (255, 140, 80),    # More vibrant orange
            "red": (255, 80, 100),       # Brighter red
            "cyan": (80, 255, 255),      # More vibrant cyan
            "yellow": (255, 255, 80)     # Brighter yellow
        }
        
        # Special working mode: cycle between purple, orange, and yellow
        if color_scheme == "working":
            import time
            # Cycle every 2 seconds between the three colors
            cycle_time = time.time() % 6  # 6 seconds total cycle
            if cycle_time < 2:
                base_color = colors["purple"]
            elif cycle_time < 4:
                base_color = colors["orange"]
            else:
                base_color = colors["yellow"]
        else:
            base_color = colors.get(color_scheme, colors["blue"])
        
        # Animation effect - more visible pulse
        intensity = 1.0  # Increased from 0.8 for better visibility
        if animated:
            import time
            pulse = abs(math.sin(time.time() * 2)) * 0.2 + 0.9  # Pulse between 0.9 and 1.1
            intensity *= pulse
        
        # Main circle with gradient effect - more opaque
        for i in range(radius):
            alpha = int(255 * (1 - i / radius * 0.6) * intensity)  # Less transparency
            color = (*base_color, min(255, alpha))  # Ensure alpha doesn't exceed 255
            draw.ellipse(
                [center - radius + i, center - radius + i,
                 center + radius - i, center + radius - i],
                fill=color
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
