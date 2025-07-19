import pygame
from pygame import Color
from geometry import Position

def draw_shape(surface: pygame.Surface, shape_type: str, color: Color, center_pos: 'Position', radius: float):
    """Helper function to draw different shapes based on type."""
    draw_radius = int(max(1, radius))

    if shape_type == 'circle':
        pygame.draw.circle(surface, color, (center_pos.x, center_pos.y), draw_radius)
    elif shape_type == 'square':
        rect = pygame.Rect(center_pos.x - draw_radius, center_pos.y - draw_radius, draw_radius * 2, draw_radius * 2)
        pygame.draw.rect(surface, color, rect)
    elif shape_type == 'triangle':
        p1 = (center_pos.x, center_pos.y - draw_radius) 
        p2 = (center_pos.x - int(draw_radius * 0.8), center_pos.y + int(draw_radius * 0.6)) 
        p3 = (center_pos.x + int(draw_radius * 0.8), center_pos.y + int(draw_radius * 0.6)) 
        pygame.draw.polygon(surface, color, [p1, p2, p3])
    else:
        pygame.draw.circle(surface, color, (center_pos.x, center_pos.y), draw_radius)
