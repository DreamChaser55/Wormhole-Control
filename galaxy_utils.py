import pygame
from geometry import Vector, Position
from constants import LOGICAL_GALAXY_SIZE

def logical_to_screen_galaxy(logical_pos: Vector, render_rect: pygame.Rect) -> Vector:
    """
    Maps a logical galaxy coordinate to a screen pixel coordinate within the given render_rect.
    Maintains aspect ratio and centers the logical space within the rect.
    """
    if render_rect is None:
        # Fallback if no rect is provided
        return Vector(logical_pos.x, logical_pos.y)

    x_scale = render_rect.width / LOGICAL_GALAXY_SIZE.x
    y_scale = render_rect.height / LOGICAL_GALAXY_SIZE.y
    scale = min(x_scale, y_scale)

    scaled_width = LOGICAL_GALAXY_SIZE.x * scale
    scaled_height = LOGICAL_GALAXY_SIZE.y * scale

    offset_x = render_rect.left + (render_rect.width - scaled_width) / 2
    offset_y = render_rect.top + (render_rect.height - scaled_height) / 2

    screen_x = offset_x + logical_pos.x * scale
    screen_y = offset_y + logical_pos.y * scale
    return Vector(screen_x, screen_y)

def screen_to_logical_galaxy(screen_pos: Position, render_rect: pygame.Rect) -> Vector:
    """
    Maps a screen pixel coordinate within the render_rect back to a logical galaxy coordinate.
    """
    if render_rect is None:
        return Vector(screen_pos.x, screen_pos.y)

    x_scale = render_rect.width / LOGICAL_GALAXY_SIZE.x
    y_scale = render_rect.height / LOGICAL_GALAXY_SIZE.y
    scale = min(x_scale, y_scale)

    scaled_width = LOGICAL_GALAXY_SIZE.x * scale
    scaled_height = LOGICAL_GALAXY_SIZE.y * scale

    offset_x = render_rect.left + (render_rect.width - scaled_width) / 2
    offset_y = render_rect.top + (render_rect.height - scaled_height) / 2

    logical_x = (screen_pos.x - offset_x) / scale
    logical_y = (screen_pos.y - offset_y) / scale
    return Vector(logical_x, logical_y)
