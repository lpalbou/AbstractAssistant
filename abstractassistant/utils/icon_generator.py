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
        
    def create_app_icon(self) -> Image.Image:
        """Create the main application icon with a modern, AI-inspired design."""
        # Create base image with transparency
        img = Image.new('RGBA', (self.size, self.size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Calculate dimensions
        center = self.size // 2
        radius = int(self.size * 0.35)
        
        # Create gradient background circle (neural network inspired)
        self._draw_gradient_circle(draw, center, radius)
        
        # Add neural network nodes
        self._draw_neural_nodes(draw, center, radius)
        
        # Add connecting lines
        self._draw_neural_connections(draw, center, radius)
        
        # Apply subtle glow effect
        img = self._add_glow_effect(img)
        
        return img
    
    def _draw_gradient_circle(self, draw: ImageDraw.Draw, center: int, radius: int):
        """Draw a gradient circle background."""
        # Main circle with subtle gradient effect
        for i in range(radius):
            alpha = int(255 * (1 - i / radius) * 0.8)
            color = (100, 150, 255, alpha)  # Blue gradient
            draw.ellipse(
                [center - radius + i, center - radius + i,
                 center + radius - i, center + radius - i],
                fill=color
            )
    
    def _draw_neural_nodes(self, draw: ImageDraw.Draw, center: int, radius: int):
        """Draw neural network-style nodes."""
        # Central node (larger)
        node_radius = int(radius * 0.15)
        draw.ellipse(
            [center - node_radius, center - node_radius,
             center + node_radius, center + node_radius],
            fill=(255, 255, 255, 200)
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
                fill=(255, 255, 255, 150)
            )
    
    def _draw_neural_connections(self, draw: ImageDraw.Draw, center: int, radius: int):
        """Draw connections between neural nodes."""
        num_nodes = 6
        outer_radius = int(radius * 0.7)
        
        # Draw lines from center to outer nodes
        for i in range(num_nodes):
            angle = (2 * math.pi * i) / num_nodes
            x = center + int(outer_radius * math.cos(angle))
            y = center + int(outer_radius * math.sin(angle))
            
            draw.line(
                [center, center, x, y],
                fill=(255, 255, 255, 100),
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
                fill=(255, 255, 255, 60),
                width=1
            )
    
    def _add_glow_effect(self, img: Image.Image) -> Image.Image:
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
