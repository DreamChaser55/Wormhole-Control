import pygame
import math
from pygame import Color
from geometry import Position


def draw_dotted_line(surface: pygame.Surface, color: Color, start, end, width: int = 1,
                     dot_len: int = 6, gap_len: int = 12):
    """Draw a dotted (dashed) line from start to end.

    Args:
        surface: Pygame surface to draw on.
        color:   Line colour.
        start:   (x, y) or Position-like start point.
        end:     (x, y) or Position-like end point.
        width:   Line width in pixels.
        dot_len: Length of each drawn dash in pixels.
        gap_len: Length of each gap between dashes in pixels.
    """
    sx = start[0] if not isinstance(start, Position) else start.x
    sy = start[1] if not isinstance(start, Position) else start.y
    ex = end[0] if not isinstance(end, Position) else end.x
    ey = end[1] if not isinstance(end, Position) else end.y

    dx = ex - sx
    dy = ey - sy
    total_len = math.sqrt(dx * dx + dy * dy)
    if total_len == 0:
        return

    ux = dx / total_len
    uy = dy / total_len

    pos = 0.0
    drawing = True  # start with a drawn segment
    while pos < total_len:
        segment = dot_len if drawing else gap_len
        segment = min(segment, total_len - pos)
        if drawing:
            x1 = sx + ux * pos
            y1 = sy + uy * pos
            x2 = sx + ux * (pos + segment)
            y2 = sy + uy * (pos + segment)
            pygame.draw.line(surface, color, (x1, y1), (x2, y2), width)
        pos += segment
        drawing = not drawing

def draw_shape(surface: pygame.Surface, shape_type: str, color: Color, center_pos: 'Position', radius: float):
    """Helper function to draw different shapes based on type."""
    draw_radius = int(max(1, radius))

    if shape_type == 'circle':
        pygame.draw.circle(surface, color, (center_pos.x, center_pos.y), draw_radius)
    elif shape_type == 'square':
        rect = pygame.Rect(center_pos.x - draw_radius, center_pos.y - draw_radius, draw_radius * 2, draw_radius * 2)
        pygame.draw.rect(surface, color, rect)
    elif shape_type == 'strikecraft_wing':
        cx, cy = center_pos.x, center_pos.y
        r = draw_radius
        
        # Define the vertices of the three smaller triangles arranged into a triangle
        t1_p1 = (cx, cy - r)
        t1_p2 = (cx - int(r * 0.4), cy - int(r * 0.2))
        t1_p3 = (cx + int(r * 0.4), cy - int(r * 0.2))
        
        t2_p1 = (cx - int(r * 0.4), cy - int(r * 0.2))
        t2_p2 = (cx - int(r * 0.8), cy + int(r * 0.6))
        t2_p3 = (cx, cy + int(r * 0.6))
        
        t3_p1 = (cx + int(r * 0.4), cy - int(r * 0.2))
        t3_p2 = (cx, cy + int(r * 0.6))
        t3_p3 = (cx + int(r * 0.8), cy + int(r * 0.6))
        
        pygame.draw.polygon(surface, color, [t1_p1, t1_p2, t1_p3])
        pygame.draw.polygon(surface, color, [t2_p1, t2_p2, t2_p3])
        pygame.draw.polygon(surface, color, [t3_p1, t3_p2, t3_p3])
    elif shape_type == 'triangle':
        p1 = (center_pos.x, center_pos.y - draw_radius) 
        p2 = (center_pos.x - int(draw_radius * 0.8), center_pos.y + int(draw_radius * 0.6)) 
        p3 = (center_pos.x + int(draw_radius * 0.8), center_pos.y + int(draw_radius * 0.6)) 
        pygame.draw.polygon(surface, color, [p1, p2, p3])
    else:
        pygame.draw.circle(surface, color, (center_pos.x, center_pos.y), draw_radius)
