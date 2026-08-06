import math
import random
from geometry import Vector, distance, Position, Circle, is_point_in_circle, clamp_point_to_circle
from constants import SECTOR_CIRCLE_RADIUS_LOGICAL, SECTOR_CIRCLE_CENTER_IN_PX, SECTOR_CIRCLE_RADIUS_IN_PX

# --- Sector Utility Functions ---

def move_towards_position(current: Position, target: Position, max_distance: float) -> Position:
    """Moves from current position towards target position, limited by max_distance.
    Returns the new position after movement."""
    dist = distance(current, target)
    
    # If we're already close enough, return the target position
    if dist <= max_distance:
        return target
    
    # Calculate the direction vector
    dx = target.x - current.x
    dy = target.y - current.y
    
    # Normalize and scale by max_distance
    scale = max_distance / dist
    return Position(current.x + dx * scale, current.y + dy * scale)

def random_point_in_circle(radius: float) -> Position:
    """Generates a random Position within a circle of the given radius."""
    # Use sqrt for uniform distribution
    r_val = math.sqrt(random.random()) * radius
    angle = random.random() * 2 * math.pi
    x = r_val * math.cos(angle)
    y = r_val * math.sin(angle)
    return Position(x, y)

def random_point_in_sector() -> Position:
    """Generates a random Position within a sector circle (in logical coordinates)."""
    return random_point_in_circle(SECTOR_CIRCLE_RADIUS_LOGICAL)

def get_sector_pixel_center(pan_offset: Position = None) -> Position:
    """Returns the center of the sector view circle in screen pixel coordinates, incorporating pan offset."""
    if pan_offset is None:
        pan_offset = Position(0, 0)
    return Position(SECTOR_CIRCLE_CENTER_IN_PX.x + pan_offset.x, SECTOR_CIRCLE_CENTER_IN_PX.y + pan_offset.y)

def get_sector_pixel_radius(zoom: float = 1.0) -> float:
    """Returns the radius of the sector view circle in screen pixel coordinates for a given zoom level."""
    return SECTOR_CIRCLE_RADIUS_IN_PX * zoom

def get_sector_pixel_circle(zoom: float = 1.0, pan_offset: Position = None) -> Circle:
    """Returns a Circle object representing the sector view boundary in screen pixel coordinates."""
    return Circle(get_sector_pixel_center(pan_offset), get_sector_pixel_radius(zoom))

def sector_radius_to_pixels(logical_radius: float, zoom: float = 1.0) -> float:
    """Converts a logical sector distance/radius to screen pixels."""
    return logical_radius * (SECTOR_CIRCLE_RADIUS_IN_PX * zoom) / SECTOR_CIRCLE_RADIUS_LOGICAL

def pixels_to_sector_radius(pixel_radius: float, zoom: float = 1.0) -> float:
    """Converts a screen pixel distance/radius to logical sector distance."""
    return (pixel_radius / (SECTOR_CIRCLE_RADIUS_IN_PX * zoom)) * SECTOR_CIRCLE_RADIUS_LOGICAL

def sector_coords_to_pixels(sector_pos: Position, zoom: float = 1.0, pan_offset: Position = None) -> Position:
    """Converts logical sector coordinates (e.g., x,y from +-SECTOR_CIRCLE_RADIUS_LOGICAL) to screen pixel coordinates."""
    center = get_sector_pixel_center(pan_offset)
    scale = (SECTOR_CIRCLE_RADIUS_IN_PX * zoom) / SECTOR_CIRCLE_RADIUS_LOGICAL
    pixel_x = int(center.x + sector_pos.x * scale)
    pixel_y = int(center.y + sector_pos.y * scale)
    return Position(pixel_x, pixel_y)

def pixels_to_sector_coords(pixel_pos: Position, zoom: float = 1.0, pan_offset: Position = None) -> Position:
    """Converts screen pixel coordinates to logical sector coordinates."""
    center = get_sector_pixel_center(pan_offset)
    relative_x = pixel_pos.x - center.x
    relative_y = pixel_pos.y - center.y
    scale = SECTOR_CIRCLE_RADIUS_LOGICAL / (SECTOR_CIRCLE_RADIUS_IN_PX * zoom)
    logical_x = relative_x * scale
    logical_y = relative_y * scale
    return Position(logical_x, logical_y)

def is_pixel_in_sector(pixel_pos: Position, zoom: float = 1.0, pan_offset: Position = None) -> bool:
    """Checks if a screen pixel coordinate falls within the visible sector circle."""
    return is_point_in_circle(pixel_pos, get_sector_pixel_circle(zoom, pan_offset))

def is_position_in_sector(sector_pos: Position) -> bool:
    """Checks if a logical sector coordinate falls within the logical sector circle boundary."""
    return is_point_in_circle(sector_pos, Circle(Position(0, 0), SECTOR_CIRCLE_RADIUS_LOGICAL))

def clamp_position_to_sector(sector_pos: Position) -> Position:
    """Clamps logical sector coordinates to stay within SECTOR_CIRCLE_RADIUS_LOGICAL."""
    return clamp_point_to_circle(sector_pos, Circle(Position(0, 0), SECTOR_CIRCLE_RADIUS_LOGICAL))

