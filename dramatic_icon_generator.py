"""
Dramatic Icon Generator with rotating elements and solid colors.
This is a replacement for the subtle heartbeat effects.
"""

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import math
import time


def apply_dramatic_effect(base_icon: Image.Image, status: str = "ready") -> Image.Image:
    """Apply DRAMATIC animated effect with solid colors and rotating elements.
    
    Args:
        base_icon: Base icon image to apply effect to
        status: Status for animation type ('ready', 'thinking', 'speaking')
        
    Returns:
        Icon with dramatic animated effect applied
    """
    
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
    if status == 'thinking':
        # Fast rotating bars with red color
        rotation_speed = 4.0  # 4 rotations per second
        angle = (current_time * rotation_speed * 360) % 360
        
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
        _draw_rotating_bars(draw, center, size, angle, base_color, intensity)
        
    elif status == 'speaking':
        # Medium rotating circle segments with blue color
        rotation_speed = 1.0  # 1 rotation per second
        angle = (current_time * rotation_speed * 360) % 360
        
        # Smooth pulse
        pulse = 0.5 + 0.5 * math.sin(current_time * 2 * math.pi)  # 1Hz pulse
        intensity = 0.6 + pulse * 0.4
        
        # Draw rotating segments
        _draw_rotating_segments(draw, center, size, angle, base_color, intensity)
        
    elif status == 'ready':
        # Slow breathing circle with green color
        breath = 0.5 + 0.5 * math.sin(current_time * 0.6 * math.pi)  # 0.3Hz breathing
        intensity = 0.4 + breath * 0.3
        
        # Draw breathing circle (no rotation)
        _draw_breathing_circle(draw, center, size, base_color, intensity)
        
    else:
        # Default: static circle
        _draw_breathing_circle(draw, center, size, base_color, 0.5)
    
    return result


def _draw_rotating_bars(draw, center, size, angle, color, intensity):
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
        _draw_thick_line(draw, start_x, start_y, end_x, end_y, bar_width, bar_color)


def _draw_rotating_segments(draw, center, size, angle, color, intensity):
    """Draw rotating segments for speaking status."""
    # Adjust color intensity
    r, g, b = color
    r = int(min(255, r * intensity))
    g = int(min(255, g * intensity))
    b = int(min(255, b * intensity))
    segment_color = (r, g, b, 255)
    
    # Draw 6 segments around a circle
    radius = size * 0.25
    segment_width = 30  # degrees
    
    for i in range(6):
        segment_angle = angle + (i * 60)
        start_angle = segment_angle - segment_width // 2
        end_angle = segment_angle + segment_width // 2
        
        # Draw arc segment
        bbox = [center - radius, center - radius, center + radius, center + radius]
        draw.pieslice(bbox, start_angle, end_angle, fill=segment_color)


def _draw_breathing_circle(draw, center, size, color, intensity):
    """Draw breathing circle for ready status."""
    # Adjust color intensity
    r, g, b = color
    r = int(min(255, r * intensity))
    g = int(min(255, g * intensity))
    b = int(min(255, b * intensity))
    circle_color = (r, g, b, 255)
    
    # Draw pulsing circle
    radius = size * 0.2 * (0.8 + 0.4 * intensity)
    bbox = [center - radius, center - radius, center + radius, center + radius]
    draw.ellipse(bbox, fill=circle_color)


def _draw_thick_line(draw, x1, y1, x2, y2, width, color):
    """Draw a thick line between two points."""
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
